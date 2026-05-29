"""
Script build BM25 index từ documents.jsonl đã có sẵn.
Chạy 1 lần: python -m scripts.build_bm25

Output:
  data/bm25/bm25_index.pkl   - BM25 index
  data/bm25/bm25_meta.json   - mapping id → metadata + document
"""

import json
import pickle
from pathlib import Path

from rank_bm25 import BM25Okapi

# ---------- Config ----------
DOCUMENTS_PATH = "data/embeddings/documents.jsonl"
OUTPUT_DIR     = "data/bm25"
INDEX_FILE     = "bm25_index.pkl"
META_FILE      = "bm25_meta.json"


def simple_tokenize(text: str) -> list[str]:
    """
    Tokenize đơn giản: lowercase + tách khoảng trắng + bỏ ký tự đặc biệt.
    Không dùng thư viện NLP nặng, phù hợp tiếng Việt vì tiếng Việt
    đã tách từ bằng khoảng trắng.
    """
    text = text.lower()
    # Giữ chữ cái, số, khoảng trắng (bỏ dấu câu)
    cleaned = ""
    for ch in text:
        if ch.isalnum() or ch == " ":
            cleaned += ch
        else:
            cleaned += " "
    tokens = [t for t in cleaned.split() if len(t) > 1]
    return tokens


def build_bm25_index(
    documents_path: str = DOCUMENTS_PATH,
    output_dir: str = OUTPUT_DIR,
) -> None:
    doc_file = Path(documents_path)
    if not doc_file.exists():
        raise FileNotFoundError(
            f"Không tìm thấy: {documents_path}\n"
            "Đảm bảo đã chạy pipeline embedding trước."
        )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------- Đọc documents ----------
    chunks = []
    with open(doc_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))

    print(f"[build_bm25] Đọc được {len(chunks)} documents từ {documents_path}")

    # ---------- Tokenize ----------
    print("[build_bm25] Tokenizing...")
    tokenized_corpus = []
    for chunk in chunks:
        tokens = simple_tokenize(chunk["document"])
        tokenized_corpus.append(tokens)

    # ---------- Build BM25 ----------
    print("[build_bm25] Building BM25Okapi index...")
    bm25 = BM25Okapi(tokenized_corpus)

    # ---------- Build metadata mapping ----------
    # Lưu id + metadata + document để lookup khi search
    meta_map = {}
    ordered_ids = []
    for i, chunk in enumerate(chunks):
        doc_id = chunk["id"]
        ordered_ids.append(doc_id)
        meta_map[doc_id] = {
            "index"    : i,           # vị trí trong BM25 corpus
            "document" : chunk["document"],
            "metadata" : chunk["metadata"],
        }

    # ---------- Save ----------
    index_path = out_dir / INDEX_FILE
    meta_path  = out_dir / META_FILE

    # Lưu BM25 object + ordered_ids cùng nhau
    with open(index_path, "wb") as f:
        pickle.dump({"bm25": bm25, "ordered_ids": ordered_ids}, f)

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_map, f, ensure_ascii=False, indent=2)

    print(f"[build_bm25] Hoàn thành!")
    print(f"  Index  → {index_path}  ({index_path.stat().st_size / 1e6:.1f} MB)")
    print(f"  Meta   → {meta_path}  ({meta_path.stat().st_size / 1e6:.1f} MB)")
    print(f"[build_bm25] Tổng: {len(chunks)} documents đã được index.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build BM25 index từ documents.jsonl")
    parser.add_argument("--input",      default=DOCUMENTS_PATH, help="Path tới documents.jsonl")
    parser.add_argument("--output-dir", default=OUTPUT_DIR,     help="Thư mục lưu output")
    args = parser.parse_args()

    build_bm25_index(
        documents_path=args.input,
        output_dir=args.output_dir,
    )
