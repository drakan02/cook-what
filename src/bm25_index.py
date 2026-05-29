"""
src/bm25_index.py

Load BM25 index đã build sẵn và thực hiện search.
Index được cache trong memory sau lần load đầu tiên (singleton).
"""

import json
import pickle
from pathlib import Path

# ---------- Config ----------
BM25_INDEX_PATH = "data/bm25/bm25_index.pkl"
BM25_META_PATH  = "data/bm25/bm25_meta.json"

# ---------- Singleton cache ----------
_bm25_cache = None     # {"bm25": BM25Okapi, "ordered_ids": [...]}
_meta_cache = None     # {doc_id: {"index", "document", "metadata"}}


def _load_index(
    index_path: str = BM25_INDEX_PATH,
    meta_path: str  = BM25_META_PATH,
) -> tuple:
    """Load index + meta từ disk, cache vào memory."""
    global _bm25_cache, _meta_cache

    if _bm25_cache is not None and _meta_cache is not None:
        return _bm25_cache, _meta_cache

    idx_file  = Path(index_path)
    meta_file = Path(meta_path)

    if not idx_file.exists():
        raise FileNotFoundError(
            f"Không tìm thấy BM25 index: {index_path}\n"
            "Hãy chạy: python -m scripts.build_bm25"
        )
    if not meta_file.exists():
        raise FileNotFoundError(
            f"Không tìm thấy BM25 meta: {meta_path}\n"
            "Hãy chạy: python -m scripts.build_bm25"
        )

    print("[bm25] Loading BM25 index từ disk...")
    with open(idx_file, "rb") as f:
        _bm25_cache = pickle.load(f)

    with open(meta_file, encoding="utf-8") as f:
        _meta_cache = json.load(f)

    total = len(_bm25_cache["ordered_ids"])
    print(f"[bm25] Loaded {total} documents.")

    return _bm25_cache, _meta_cache


def simple_tokenize(text: str) -> list[str]:
    """
    Tokenize giống hệt lúc build index.
    QUAN TRỌNG: phải dùng cùng tokenizer với build_bm25.py.
    """
    text = text.lower()
    cleaned = ""
    for ch in text:
        if ch.isalnum() or ch == " ":
            cleaned += ch
        else:
            cleaned += " "
    tokens = [t for t in cleaned.split() if len(t) > 1]
    return tokens


def bm25_search(
    query: str,
    n: int = 25,
    index_path: str = BM25_INDEX_PATH,
    meta_path: str  = BM25_META_PATH,
) -> list[dict]:
    """
    Tìm kiếm BM25 cho query, trả về top-n kết quả.

    Args:
        query : câu query (vd: "gà, trứng, hành lá")
        n     : số kết quả trả về

    Returns:
        list[dict] với keys: id, score, document, metadata, title, url
    """
    bm25_data, meta_map = _load_index(index_path, meta_path)

    bm25        = bm25_data["bm25"]
    ordered_ids = bm25_data["ordered_ids"]

    # Tokenize query
    query_tokens = simple_tokenize(query)
    if not query_tokens:
        return []

    # Lấy scores cho toàn bộ corpus
    scores = bm25.get_scores(query_tokens)  # numpy array, len = corpus size

    # Lấy top-n indices (argsort descending)
    import numpy as np
    top_indices = np.argsort(scores)[::-1][:n]

    results = []
    for idx in top_indices:
        score = float(scores[idx])
        if score <= 0:
            break   # BM25 score = 0 nghĩa là không liên quan

        doc_id = ordered_ids[idx]
        info   = meta_map.get(doc_id)
        if not info:
            continue

        results.append({
            "id"       : doc_id,
            "score"    : round(score, 4),
            "document" : info["document"],
            "metadata" : info["metadata"],
            "title"    : info["metadata"].get("title", ""),
            "url"      : info["metadata"].get("url", ""),
        })

    return results


# ---------- Entry point để test ----------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test BM25 search")
    parser.add_argument("query", help="Câu query tìm kiếm")
    parser.add_argument("--n", type=int, default=5, help="Số kết quả")
    args = parser.parse_args()

    results = bm25_search(args.query, n=args.n)
    for i, r in enumerate(results, 1):
        print(f"\n{'─'*50}")
        print(f"#{i} [BM25={r['score']:.4f}] {r['title']}")
        print(f"    URL: {r['url']}")
        print(f"    NER: {r['metadata'].get('ner', '')}")
