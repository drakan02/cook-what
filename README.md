# CookWhat

CookWhat là ứng dụng gợi ý món ăn bằng tiếng Việt. Người dùng nhập các nguyên liệu đang có, hệ thống tìm công thức liên quan trong ChromaDB, dùng LLM để trả lời tự nhiên như chatbot, và lưu lịch sử trò chuyện vào PostgreSQL.

## Tính năng

- Giao diện chat web tương tự ChatGPT.
- Gợi ý món ăn dựa trên nguyên liệu người dùng nhập.
- Hỏi tiếp trong cùng một hội thoại, ví dụ món nào nhanh hơn, healthy hơn, dễ làm hơn.
- Tìm lại món theo yêu cầu mới, ví dụ món Nhật, món Hàn, món hấp, món ít calo.
- Thêm nguyên liệu vào ngữ cảnh hiện tại.
- Lưu lịch sử chat vào PostgreSQL.
- Fallback sang bộ nhớ tạm nếu PostgreSQL chưa được cấu hình.
- Tìm kiếm công thức bằng ChromaDB và sentence embedding.

## Kiến trúc

```text
Browser UI
  -> FastAPI backend
      -> Intent router
      -> Ingredient extractor
      -> ChromaDB recipe search
      -> LLM response via OpenRouter
      -> PostgreSQL chat history
```

Các phần chính:

```text
main.py                 FastAPI app, API chat, API lịch sử, static frontend
frontend/               HTML/CSS/JS giao diện chat
app/db.py               PostgreSQL storage cho chat_sessions và chat_messages
app/llm_service.py      Gọi OpenRouter LLM
app/intent_router.py    Phân loại ý định user
app/ingredient_extract.py
app/prompt_builder.py   Tạo prompt trả lời gợi ý món ăn
src/vectordb.py         ChromaDB ingest/search
src/embedding.py        Encode query/document bằng sentence-transformers
scripts/                Script tải dữ liệu, build/search vector DB
docker-compose.yml      PostgreSQL local bằng Docker
```

## Yêu cầu

- Python 3.9+.
- Docker Desktop nếu muốn chạy PostgreSQL bằng Docker.
- OpenRouter API key.
- ChromaDB data trong thư mục `chroma_db/`, hoặc tự build lại bằng pipeline.

## Cài đặt Python

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Nếu PowerShell chặn activate script:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Cấu hình môi trường

Tạo file `.env` từ `.env.example`:

```powershell
Copy-Item .env.example .env
```

Cấu hình:

```env
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=openai/gpt-oss-120b
DATABASE_URL=postgresql://cookwhat:cookwhat_password@localhost:5432/cookwhat
```

Không commit file `.env`. File này đã nằm trong `.gitignore`.

## PostgreSQL

Repo này dùng PostgreSQL qua Docker, không cài PostgreSQL native vào Windows.

Khởi động database:

```powershell
docker compose up -d postgres
```

Kiểm tra container:

```powershell
docker ps --filter name=cookwhat-postgres
```

Kiểm tra version:

```powershell
docker exec cookwhat-postgres postgres --version
```

Version đang dùng trong `docker-compose.yml`:

```text
postgres:16-alpine
```

Connection string:

```env
DATABASE_URL=postgresql://cookwhat:cookwhat_password@localhost:5432/cookwhat
```

Khi backend khởi động, app tự tạo hai bảng:

```text
chat_sessions
chat_messages
```

Kiểm tra bảng:

```powershell
docker exec cookwhat-postgres psql -U cookwhat -d cookwhat -c "\dt"
```

Dừng database:

```powershell
docker compose stop postgres
```

Xóa container nhưng giữ data volume:

```powershell
docker compose down
```

Xóa cả container và dữ liệu PostgreSQL:

```powershell
docker compose down -v
```

## Chạy ứng dụng

Khởi động PostgreSQL trước nếu muốn lưu lịch sử:

```powershell
docker compose up -d postgres
```

Chạy FastAPI:

```powershell
.\.venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 8000 --reload
```

Mở UI:

```text
http://127.0.0.1:8000
```

Kiểm tra backend:

```text
http://127.0.0.1:8000/health
```

Response mẫu khi PostgreSQL hoạt động:

```json
{
  "status": "running",
  "message": "CookWhat API is running",
  "postgres_history": true
}
```

Nếu `postgres_history` là `false`, app vẫn chạy nhưng lịch sử chỉ lưu trong memory và sẽ mất khi restart server.

## API

### Health

```http
GET /health
```

### Chat

```http
POST /chat
Content-Type: application/json
```

Body:

```json
{
  "message": "Mình có gà, trứng, hành lá",
  "session_id": "optional-session-id",
  "top_k": 5
}
```

Response mẫu:

```json
{
  "type": "new_search",
  "session_id": "session-id",
  "ingredients": ["gà", "trứng", "hành lá"],
  "response": "..."
}
```

### Lịch sử chat

Lấy danh sách hội thoại:

```http
GET /api/sessions
```

Lấy tin nhắn của một hội thoại:

```http
GET /api/sessions/{session_id}/messages
```

Xóa một hội thoại:

```http
DELETE /api/sessions/{session_id}
```

## ChromaDB và dữ liệu công thức

Backend cần thư mục `chroma_db/` để tìm kiếm công thức. Thư mục này đang bị ignore trong Git vì có thể lớn.

### Cách 1: Tải ChromaDB có sẵn

Linux/macOS hoặc Git Bash:

```bash
chmod +x scripts/download_chromadb.sh
./scripts/download_chromadb.sh
```

Script sẽ:

- Cài `gdown` nếu thiếu.
- Tải ChromaDB từ Google Drive.
- Giải nén và thay thế thư mục `chroma_db/`.

### Cách 2: Build lại pipeline từ dữ liệu thô

Linux/macOS hoặc Git Bash:

```bash
chmod +x scripts/run_pipeline.sh
./scripts/run_pipeline.sh
```

Pipeline gồm:

| Bước | Module | Mục đích |
| --- | --- | --- |
| 1 | `src.chunking` | Chia dữ liệu công thức thành các đoạn nhỏ |
| 2 | `src.embedding` | Tạo embedding cho từng đoạn |
| 3 | `src.vectordb` | Nạp embedding vào ChromaDB |

Output chính:

```text
data/chunks.jsonl
data/embeddings/
chroma_db/
```

## Test nhanh vector search

Windows:

```powershell
.\.venv\Scripts\python.exe -m scripts.query_vectordb
```

Linux/macOS:

```bash
.venv/bin/python -m scripts.query_vectordb
```

Script mặc định query `"gà kho gừng"` và in ra 5 kết quả gần nhất.

Bạn cũng có thể dùng trực tiếp `src.vectordb`:

```powershell
.\.venv\Scripts\python.exe -m src.vectordb search "gà kho gừng" --n 5
```

## Luồng chat

Backend phân loại message thành các intent:

```text
NEW_SEARCH       User nhập nguyên liệu mới
FOLLOW_UP        User hỏi tiếp về món đã gợi ý
RESEARCH         User muốn đổi style hoặc tìm món khác
ADD_INGREDIENT   User thêm nguyên liệu vào ngữ cảnh
SMALL_TALK       Chào hỏi, cảm ơn, tạm biệt
```

Ngữ cảnh hiện tại gồm:

```text
ingredients
recipes
```

Nếu PostgreSQL bật, ngữ cảnh và tin nhắn được lưu theo `session_id`. Nếu không, ngữ cảnh được giữ trong memory.

## Dùng PostgreSQL cho dự án khác

PostgreSQL hiện chạy trong Docker và expose ra:

```text
localhost:5432
```

Dự án khác có thể kết nối tới cùng server nếu Docker container đang chạy. Tuy nhiên không nên dùng chung database `cookwhat` cho nhiều dự án. Nên tạo database riêng:

```powershell
docker exec cookwhat-postgres createdb -U cookwhat project_name
```

Connection string cho database mới:

```env
DATABASE_URL=postgresql://cookwhat:cookwhat_password@localhost:5432/project_name
```

## Xử lý lỗi thường gặp

| Lỗi | Cách xử lý |
| --- | --- |
| `postgres_history: false` | Kiểm tra `DATABASE_URL`, chạy `docker compose up -d postgres`, restart FastAPI |
| Không mở được `localhost:8000` | Kiểm tra server uvicorn có đang chạy không |
| Port `8000` đã bị dùng | Chạy uvicorn với port khác, ví dụ `--port 8001` |
| Port `5432` đã bị dùng | Đổi mapping trong `docker-compose.yml`, ví dụ `"5433:5432"` |
| `ModuleNotFoundError` | Chạy lại `python -m pip install -r requirements.txt` trong `.venv` |
| Không có kết quả món ăn | Kiểm tra thư mục `chroma_db/` đã tồn tại và có collection `recipes` |
| Lỗi OpenRouter/API key | Kiểm tra `OPENROUTER_API_KEY` và `OPENROUTER_MODEL` trong `.env` |
| Docker daemon chưa chạy | Mở Docker Desktop rồi chạy lại lệnh Docker |

## Ghi chú bảo mật

- Không đưa `OPENROUTER_API_KEY` lên Git.
- Frontend không chứa API key; frontend chỉ gọi backend nội bộ.
- `cookwhat_password` trong `docker-compose.yml` chỉ phù hợp cho local development. Khi deploy thật cần đổi password và dùng secret manager hoặc biến môi trường an toàn.

## Lệnh hay dùng

```powershell
# Start database
docker compose up -d postgres

# Start backend and UI
.\.venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 8000 --reload

# Check health
Invoke-RestMethod http://127.0.0.1:8000/health

# Check PostgreSQL tables
docker exec cookwhat-postgres psql -U cookwhat -d cookwhat -c "\dt"

# Stop database
docker compose stop postgres
```
