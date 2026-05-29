"""
src/reranker.py

Cross-encoder reranker dùng BAAI/bge-reranker-v2-m3.
Load model 1 lần, cache vào memory (singleton).

Model: BAAI/bge-reranker-v2-m3
  - Hỗ trợ tiếng Việt tốt (cùng họ M3)
  - ~570MB, chạy CPU được
  - Nhận cặp (query, document) → relevance score
"""

from sentence_transformers import CrossEncoder

# ---------- Config ----------
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
MAX_LENGTH     = 512    # truncate document nếu quá dài

# ---------- Singleton ----------
_reranker = None


def _load_reranker() -> CrossEncoder:
    """Load CrossEncoder model, cache vào memory."""
    global _reranker
    if _reranker is not None:
        return _reranker

    print(f"[reranker] Loading model '{RERANKER_MODEL}'...")
    _reranker = CrossEncoder(
        RERANKER_MODEL,
        max_length=MAX_LENGTH,
        device="cpu",
    )
    print("[reranker] Model loaded!")
    return _reranker


def rerank(
    query: str,
    candidates: list[dict],
    top_k: int = 5,
) -> list[dict]:
    """
    Rerank candidates bằng cross-encoder.

    Args:
        query      : câu query gốc của user
        candidates : list[dict] từ hybrid_search (sau RRF fusion).
                     Mỗi dict phải có key "document".
        top_k      : số kết quả cuối cùng trả về

    Returns:
        list[dict] top_k candidates đã được rerank,
        mỗi dict có thêm key "rerank_score".
    """
    if not candidates:
        return []

    reranker = _load_reranker()

    # Tạo pairs (query, document) cho cross-encoder
    pairs = [(query, c["document"]) for c in candidates]

    # Score tất cả pairs
    # predict() trả về list float, thứ tự tương ứng với pairs
    scores = reranker.predict(pairs, show_progress_bar=False)

    # Gắn rerank score vào candidates
    scored = []
    for candidate, score in zip(candidates, scores):
        c = dict(candidate)          # copy để không mutate original
        c["rerank_score"] = round(float(score), 4)
        scored.append(c)

    # Sort descending theo rerank score
    scored.sort(key=lambda x: x["rerank_score"], reverse=True)

    return scored[:top_k]


# ---------- Entry point để test ----------
if __name__ == "__main__":
    # Test nhanh
    query = "món gà chiên bơ tỏi"
    fake_candidates = [
        {
            "id": "1",
            "title": "Gà chiên bơ tỏi",
            "document": "Ten mon: Gà Chiên Bơ Tỏi. Nguyen lieu: gà, bơ, tỏi, muối.",
            "url": "http://example.com/1",
            "metadata": {},
        },
        {
            "id": "2",
            "title": "Cá kho riềng",
            "document": "Ten mon: Cá Kho Riềng. Nguyen lieu: cá, riềng, mắm.",
            "url": "http://example.com/2",
            "metadata": {},
        },
    ]
    results = rerank(query, fake_candidates, top_k=2)
    for r in results:
        print(f"[{r['rerank_score']:.4f}] {r['title']}")
