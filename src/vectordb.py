import json
import numpy as np
from pathlib import Path
from typing import Optional, Dict, List, Any

import chromadb
from chromadb.config import Settings

from src.embedding import encode_query

# ---------- Configuration ----------
CHROMA_PATH = "./chroma_db"       # thư mục lưu ChromaDB persistent
COLLECTION_NAME  = "recipes"
BATCH_SIZE = 512                  # số documents nạp vào Chroma mỗi lần

# ---------- Client & Collection ----------
def get_collection(chroma_path: str = CHROMA_PATH,
                   collection_name: str = COLLECTION_NAME) -> chromadb.Collection:
    """
    Trả về ChromaDB collection (tạo mới nếu chưa có).
    Dùng cosine similarity vì BGE được train với normalized vectors.
    """
    client = chromadb.PersistentClient(
        path=chroma_path,
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},   # cosine cho BGE
    )
    return collection

# ---------- Ingest: nạp embeddings vào ChromaDB ----------
def ingest(embeddings_dir: str,
           chroma_path: str = CHROMA_PATH,
           collection_name: str = COLLECTION_NAME,
           reset: bool = False) -> None:
    """
    Đọc embeddings.npy + ids.json + documents.jsonl từ embeddings_dir,
    nạp toàn bộ vào ChromaDB theo batch.
 
    Args:
        embeddings_dir : thư mục output của embedding.py
        chroma_path    : nơi lưu ChromaDB
        collection_name: tên collection
        reset          : nếu True, xóa collection cũ trước khi nạp
    """
    out_dir  = Path(embeddings_dir)
    emb_path = out_dir / "embeddings.npy"
    ids_path = out_dir / "ids.json"
    doc_path = out_dir / "documents.jsonl"

    for p in [emb_path, ids_path, doc_path]:
        if not p.exists():
            raise FileNotFoundError(f"Thiếu file: {p}")
 
    # Load dữ liệu
    embeddings = np.load(str(emb_path))     # (N, dim)
    ids = json.loads(ids_path.read_text(encoding="utf-8"))

    chunks = []
    with open(doc_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))
 
    assert len(embeddings) == len(ids) == len(chunks), \
        "Số lượng embeddings / ids / chunks không khớp!"
 
    print(f"[vectordb] Chuẩn bị nạp {len(ids)} documents vào ChromaDB ...")

    # Lấy / reset collection
    client = chromadb.PersistentClient(
        path=chroma_path,
        settings=Settings(anonymized_telemetry=False),
    )
    if reset:
        try:
            client.delete_collection(collection_name)
            print(f"[vectordb] Đã xóa collection cũ: {collection_name}")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    # Nạp theo batch
    total = len(ids)
    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)
 
        batch_ids   = ids[start:end]
        batch_embs  = embeddings[start:end].tolist()
        batch_docs  = [c["document"] for c in chunks[start:end]]
        batch_metas = [c["metadata"] for c in chunks[start:end]]
 
        # ChromaDB upsert: bỏ qua nếu id đã tồn tại, cập nhật nếu khác
        collection.upsert(
            ids = batch_ids,
            embeddings = batch_embs,
            documents = batch_docs,
            metadatas = batch_metas,
        )
        print(f"[vectordb]  Đã nạp {end}/{total} documents ...")
 
    print(f"[vectordb] Hoàn thành! Collection '{collection_name}' "
          f"có {collection.count()} documents.")
    
# ---------- Search ----------
def search(query: str,
           n_results: int = 5,
           filter_ingredient: Optional[str] = None,
           filter_location: Optional[str] = None,
           chroma_path: str = CHROMA_PATH,
           collection_name: str = COLLECTION_NAME) -> List[Dict[str, Any]]:
    """
    Tìm kiếm recipe theo câu query tự nhiên.
 
    Args:
        query              : câu hỏi/tìm kiếm (vd: "món ăn nhẹ bụng từ cá")
        n_results          : số kết quả trả về
        filter_ingredient  : lọc theo nguyên liệu (vd: "rau muống")
        filter_location    : lọc theo vùng tác giả (vd: "Hồ Chí Minh")
 
    Returns:
        list các dict với keys: id, title, url, document, distance, metadata
    """
    collection = get_collection(chroma_path, collection_name)
 
    # Encode query (có prefix BGE)
    query_emb = encode_query(query).tolist()

    # Xây dựng where filter (ChromaDB dùng $and để kết hợp nhiều điều kiện)
    where = _build_where(filter_ingredient, filter_location)

    results = collection.query(
        query_embeddings=[query_emb],
        n_results=n_results,
        where=where if where else None,
        include=["documents", "metadatas", "distances"],
    )
 
    # Format output
    output = []
    ids_       = results["ids"][0]
    documents_ = results["documents"][0]
    metadatas_ = results["metadatas"][0]
    distances_ = results["distances"][0]

    for rid, doc, meta, dist in zip(ids_, documents_, metadatas_, distances_):
        output.append({
            "id"       : rid,
            "title"    : meta.get("title", ""),
            "url"      : meta.get("url", ""),
            "score"    : round(1 - dist, 4),   # cosine distance → similarity
            "document" : doc,
            "metadata" : meta,
        })

    return output

def _build_where(ingredient: Optional[str], location: Optional[str]) -> Optional[Dict[str, Any]]:
    """Tạo ChromaDB where clause từ các filter."""
    conditions = []

    if ingredient:
        # NER được lưu dạng string "rau muống, cá nục, ..."
        conditions.append({"ner": {"$contains": ingredient}})
 
    if location:
        conditions.append({"author_location": {"$contains": location}})
 
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}

# ---------- Entry point ----------
if __name__ == "__main__":
    import argparse
 
    parser = argparse.ArgumentParser(description="Nạp và search ChromaDB.")
    subparsers = parser.add_subparsers(dest="command")
 
    # Sub-command: ingest
    ingest_parser = subparsers.add_parser("ingest", help="Nạp embeddings vào ChromaDB")
    ingest_parser.add_argument("--embeddings-dir", default="data/embeddings")
    ingest_parser.add_argument("--chroma-path",    default=CHROMA_PATH)
    ingest_parser.add_argument("--reset", action="store_true",
                               help="Xóa collection cũ trước khi nạp")
 
    # Sub-command: search
    search_parser = subparsers.add_parser("search", help="Tìm kiếm recipe")
    search_parser.add_argument("query")
    search_parser.add_argument("--n",           type=int, default=5)
    search_parser.add_argument("--ingredient",  default=None)
    search_parser.add_argument("--location",    default=None)
    search_parser.add_argument("--chroma-path", default=CHROMA_PATH)
 
    args = parser.parse_args()

    if args.command == "ingest":
        ingest(
            embeddings_dir=args.embeddings_dir,
            chroma_path=args.chroma_path,
            reset=args.reset,
        )
 
    elif args.command == "search":
        results = search(
            query=args.query,
            n_results=args.n,
            filter_ingredient=args.ingredient,
            filter_location=args.location,
            chroma_path=args.chroma_path,
        )
        for i, r in enumerate(results, 1):
            print(f"\n{'─'*50}")
            print(f"#{i} [{r['score']:.4f}] {r['title']}")
            print(f"    URL: {r['url']}")
            print(f"    NER: {r['metadata'].get('ner', '')}")
 
    else:
        parser.print_help()