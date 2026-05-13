import json
import logging
import numpy as np
import os
import requests
import time
from pathlib import Path
from typing import List, Optional

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ---------- Config ----------
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "bge-m3:567m")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "32"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))
RETRY_MAX = int(os.getenv("RETRY_MAX", "3"))
RETRY_DELAY = 2         # seconds giữa các retry

# ---------- BGE-M3 qua Ollama không cần prefix ----------
QUERY_PREFIX = ""


# ---------- Ollama client ----------
def check_ollama_connection() -> None:
    """Kiểm tra Ollama đang chạy và model đã được pull."""
    try: 
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]

        # available = [m.split(":")[0] for m in models]
        if OLLAMA_MODEL not in models:
            raise RuntimeError(
                f"Model '{OLLAMA_MODEL}' chưa được pull.\n"
                f"Chạy: ollama pull {OLLAMA_MODEL}\n"
                f"Các model hiện có: {models}"
            )
        print(f"[embedding] Ollama OK — model '{OLLAMA_MODEL}' sẵn sàng.")
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Không kết nối được Ollama tại {OLLAMA_BASE_URL}.\n"
            "Đảm bảo Ollama đang chạy: ollama serve"
        )
    

def _embed_batch_with_retry(texts: List[str]) -> List[List[float]]:
    """
    Gọi Ollama /api/embed cho một batch texts.
    Tự động retry nếu lỗi tạm thời.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "input": texts,
    }

    for attempt in range(1, RETRY_MAX + 1):
        try:
            resp = requests.post(
                f"{OLLAMA_BASE_URL}/api/embed",
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            # Ollama trả về {"embeddings": [[...], [...]]}
            embeddings = data.get("embeddings")
            if not embeddings:
                raise ValueError(f"Response thiếu 'embeddings': {data}")
            
            return embeddings
        
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError) as e:
            if attempt < RETRY_MAX:
                print(f"[embedding] Lỗi kết nối (lần {attempt}), "
                      f"thử lại sau {RETRY_DELAY}s: {e}")
                time.sleep(RETRY_DELAY)
            else:
                raise RuntimeError(f"Ollama không phản hồi sau {RETRY_MAX} lần: {e}")
            
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"Ollama HTTP error: {e}\nResponse: {resp.text}")
        
# ---------- Core encode ----------
def _normalize(vectors: np.ndarray) -> np.ndarray:
    """L2 normalize — bắt buộc với BGE để cosine similarity đúng."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-10, norms)      # tránh chia 0
    return vectors / norms

def encode_documents(texts: List[str]) -> np.ndarray:
    """
    Encode list text thành ma trận embedding (N, dim).
    Xử lý theo batch, normalize kết quả.
    """
    all_embeddings = []
    total = len(texts)

    for start in range(0, total, BATCH_SIZE):
        end   = min(start + BATCH_SIZE, total)
        batch = texts[start:end]
 
        batch_embs = _embed_batch_with_retry(batch)
        all_embeddings.extend(batch_embs)
 
        print(f"[embedding]  Encoded {end}/{total} texts ...")
    
    matrix = np.array(all_embeddings, dtype=np.float32)
    matrix = _normalize(matrix)
    return matrix

def encode_query(query: str) -> np.ndarray:
    """
    Encode một câu query duy nhất.
    Dùng khi search trong vectordb.py.
    """
    prefixed = QUERY_PREFIX + query if QUERY_PREFIX else query
    result   = _embed_batch_with_retry([prefixed])
    vector   = np.array(result[0], dtype=np.float32)
    vector   = vector / (np.linalg.norm(vector) + 1e-10)
    return vector

# ---------- Main: đọc chunks → encode → lưu ----------
def embed_chunks(chunks_path: str, output_dir: str) -> None:
    """
    Đọc file JSONL chunks, encode toàn bộ qua Ollama, lưu ra:
      - {output_dir}/embeddings.npy   : ma trận float32 (N, dim)
      - {output_dir}/ids.json         : list recipe_id theo thứ tự
      - {output_dir}/documents.jsonl  : bản sao chunks (để vectordb.py dùng)
    """
    # Kiểm tra kết nối
    check_ollama_connection()

    chunks_file = Path(chunks_path)
    if not chunks_file.exists():
        raise FileNotFoundError(f"Không tìm thấy: {chunks_path}")
 
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Đọc chunks
    chunks = []
    with open(chunks_file, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))

    print(f"[embedding] Đọc được {len(chunks)} chunks từ {chunks_path}")
 
    ids       = [c["id"] for c in chunks]
    documents = [c["document"] for c in chunks]

    # Encode
    print(f"[embedding] Bắt đầu encode "
          f"(model={OLLAMA_MODEL}, batch={BATCH_SIZE}) ...")
    t0 = time.time()
    embeddings = encode_documents(documents)
    elapsed = time.time() - t0
    print(f"[embedding] Xong! Shape: {embeddings.shape} "
          f"| Thời gian: {elapsed:.1f}s "
          f"| Tốc độ: {len(chunks)/elapsed:.1f} texts/s")
    
    # Save the results
    emb_path = out_dir / "embeddings.npy"
    ids_path = out_dir / "ids.json"
    doc_path = out_dir / "documents.jsonl"

    np.save(str(emb_path), embeddings)
    ids_path.write_text(json.dumps(ids, ensure_ascii=False), encoding="utf-8")
    with open(doc_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
 
    print(f"[embedding] Đã lưu:")
    print(f"  embeddings → {emb_path}  ({embeddings.nbytes / 1e6:.1f} MB)")
    print(f"  ids        → {ids_path}")
    print(f"  documents  → {doc_path}")

# ---------- Entry point ----------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Encode chunks bằng BGE-M3 qua Ollama."
    )
    parser.add_argument("--input",       default="data/chunks.jsonl",
                        help="File JSONL chunks (output của chunking.py)")
    parser.add_argument("--output-dir",  default="data/embeddings",
                        help="Thư mục lưu embeddings và metadata")
    parser.add_argument("--ollama-url",  default=OLLAMA_BASE_URL,
                        help="Base URL của Ollama (default: http://localhost:11434)")
    parser.add_argument("--batch-size",  type=int, default=BATCH_SIZE,
                        help="Số texts mỗi request (default: 32)")
    args = parser.parse_args()
 
    OLLAMA_BASE_URL = args.ollama_url
    BATCH_SIZE      = args.batch_size
 
    embed_chunks(args.input, args.output_dir)