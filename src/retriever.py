"""
src/retriever.py

Orchestrator cho hybrid retrieval pipeline:

  Query
    ├─► Dense search  (ChromaDB / BGE-M3)      → top-N candidates
    ├─► Sparse search (BM25)                   → top-N candidates
    └─► NER overlap score                      → bonus signal

          ↓ Reciprocal Rank Fusion (RRF)
     Merged candidate pool

          ↓ Cross-encoder Rerank (bge-reranker-v2-m3)
     Final top-k contexts

Đây là file DUY NHẤT mà main.py cần import thay cho src.vectordb.search.
"""

from src.bm25_index import bm25_search
from src.reranker   import rerank
from src.vectordb   import search as dense_search

# ---------- Config ----------
DENSE_CANDIDATES  = 25   # số candidates lấy từ dense search
SPARSE_CANDIDATES = 25   # số candidates lấy từ BM25
RRF_K             = 60   # hằng số RRF, thường dùng 60
NER_BONUS_WEIGHT  = 0.3  # trọng số của NER overlap bonus


# ---------- NER overlap ----------

def _parse_ner(ner_string: str) -> set[str]:
    """
    Parse trường ner từ metadata.
    Format: "gà góc tư rút xương, phở khô, bột nghệ, hành phi, ..."
    → {"gà góc tư rút xương", "phở khô", "bột nghệ", "hành phi", ...}
    """
    if not ner_string:
        return set()
    items = [item.strip().lower() for item in ner_string.split(",")]
    return {item for item in items if item}


def _compute_ner_overlap(
    query_ingredients: list[str],
    doc_ner_string: str,
) -> float:
    """
    Tính tỉ lệ nguyên liệu user có mà món này cần.

    Returns:
        float trong [0, 1]:
          0   = không khớp nguyên liệu nào
          1   = tất cả nguyên liệu user có đều xuất hiện trong món
          0.5 = một nửa nguyên liệu user có xuất hiện trong món
    """
    if not query_ingredients:
        return 0.0

    doc_ner = _parse_ner(doc_ner_string)
    if not doc_ner:
        return 0.0

    query_set = {ing.strip().lower() for ing in query_ingredients if ing.strip()}
    if not query_set:
        return 0.0

    # Đếm nguyên liệu user có mà xuất hiện trong NER của món
    # Dùng partial match: "gà" match với "gà góc tư rút xương"
    matched = 0
    for user_ing in query_set:
        for doc_ing in doc_ner:
            if user_ing in doc_ing or doc_ing in user_ing:
                matched += 1
                break   # mỗi user ingredient chỉ đếm 1 lần

    return matched / len(query_set)


# ---------- RRF Fusion ----------

def _reciprocal_rank_fusion(
    dense_results : list[dict],
    sparse_results: list[dict],
    query_ingredients: list[str],
    k: int = RRF_K,
) -> list[dict]:
    """
    Kết hợp dense + sparse bằng RRF, cộng thêm NER bonus.

    RRF score = Σ 1/(k + rank_i)
    Final     = RRF + NER_BONUS_WEIGHT * ner_overlap

    Returns:
        list[dict] đã merge và sort theo final score (descending)
    """
    # Map: doc_id → rrf_score tích lũy
    rrf_scores: dict[str, float] = {}

    # Map: doc_id → thông tin document (để reconstruct kết quả)
    doc_info: dict[str, dict] = {}

    # Tính RRF từ dense results
    for rank, doc in enumerate(dense_results, start=1):
        doc_id = doc["id"]
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)
        doc_info[doc_id]   = doc

    # Tính RRF từ sparse results
    for rank, doc in enumerate(sparse_results, start=1):
        doc_id = doc["id"]
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)
        if doc_id not in doc_info:
            doc_info[doc_id] = doc

    # Cộng NER bonus
    final_scores: dict[str, float] = {}
    for doc_id, rrf_score in rrf_scores.items():
        info = doc_info[doc_id]
        ner_string = info.get("metadata", {}).get("ner", "")
        ner_overlap = _compute_ner_overlap(query_ingredients, ner_string)
        final_scores[doc_id] = rrf_score + NER_BONUS_WEIGHT * ner_overlap

    # Sort descending
    sorted_ids = sorted(final_scores.keys(), key=lambda x: final_scores[x], reverse=True)

    # Reconstruct list kết quả với fusion score
    fused = []
    for doc_id in sorted_ids:
        info = dict(doc_info[doc_id])
        info["fusion_score"] = round(final_scores[doc_id], 6)
        fused.append(info)

    return fused


# ---------- Main entry point ----------

def hybrid_search(
    query: str,
    ingredients: list[str] | None = None,
    top_k: int = 5,
) -> list[dict]:
    """
    Hybrid retrieval: Dense + BM25 + NER boost → RRF → Rerank.

    Args:
        query       : câu query (thường là ", ".join(ingredients))
        ingredients : list nguyên liệu đã extract, dùng cho NER boost
                      Nếu None thì NER bonus = 0
        top_k       : số kết quả cuối cùng trả về (giống top_k cũ)

    Returns:
        list[dict] top_k, mỗi dict có keys:
          id, title, url, score, document, metadata, rerank_score
        (format tương thích với vectordb.search() cũ)
    """
    ingredients = ingredients or []

    # --- Bước 1: Dense search ---
    print(f"[retriever] Dense search: '{query[:60]}...' " if len(query) > 60
          else f"[retriever] Dense search: '{query}'")
    dense_results = dense_search(query=query, n_results=DENSE_CANDIDATES)

    # --- Bước 2: Sparse (BM25) search ---
    print(f"[retriever] BM25 search...")
    sparse_results = bm25_search(query=query, n=SPARSE_CANDIDATES)

    print(f"[retriever] Dense={len(dense_results)} | BM25={len(sparse_results)} candidates")

    # --- Bước 3: RRF Fusion + NER boost ---
    fused = _reciprocal_rank_fusion(
        dense_results=dense_results,
        sparse_results=sparse_results,
        query_ingredients=ingredients,
    )
    print(f"[retriever] Sau fusion: {len(fused)} unique candidates")

    # --- Bước 4: Rerank top-25 (giới hạn để tiết kiệm CPU) ---
    candidates_for_rerank = fused[:25]
    print(f"[retriever] Reranking {len(candidates_for_rerank)} candidates...")
    final_results = rerank(
        query=query,
        candidates=candidates_for_rerank,
        top_k=top_k,
    )

    print(f"[retriever] Trả về {len(final_results)} kết quả cuối.")

    # Đảm bảo format output tương thích với code cũ (có key "score")
    for r in final_results:
        if "score" not in r:
            r["score"] = r.get("fusion_score", 0.0)

    return final_results


# ---------- Entry point để test ----------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test hybrid search")
    parser.add_argument("query",                      help="Câu query")
    parser.add_argument("--ingredients", nargs="*",   help="Danh sách nguyên liệu")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    results = hybrid_search(
        query=args.query,
        ingredients=args.ingredients or [],
        top_k=args.top_k,
    )

    print(f"\n{'='*60}")
    print(f"TOP {len(results)} KẾT QUẢ:")
    print(f"{'='*60}")
    for i, r in enumerate(results, 1):
        print(f"\n#{i} [rerank={r.get('rerank_score', 0):.4f}] {r['title']}")
        print(f"    URL      : {r['url']}")
        print(f"    NER      : {r['metadata'].get('ner', '')[:80]}...")
        print(f"    Fusion   : {r.get('fusion_score', 0):.6f}")
