import json
import os
from pathlib import Path
from typing import List, Dict, Any

# ---------- Helpers ----------
def truncate_description(desc: str, max_chars: int = 200) -> str:
    """Cắt description dài (vd: recipe có story dài) xuống max_chars ký tự."""
    if not desc:
        return ""
    desc = desc.strip()
    if len(desc) <= max_chars:
        return desc
    return desc[:max_chars].rsplit(" ", 1)[0] + "..."

def recipe_to_text(recipe: Dict[str, Any]) -> str:
    """
    Flatten toàn bộ thông tin recipe thành một đoạn text có cấu trúc.
    Đây là nội dung sẽ được embed và lưu vào ChromaDB (documents field).
    """
    title       = recipe.get("title", "").strip()
    description = truncate_description(recipe.get("description", ""))
    cook_time   = recipe.get("cook_time", "")
    servings    = recipe.get("servings", "")
    ner_tags    = ", ".join(recipe.get("ner", []))
 
    ingredients_list = recipe.get("ingredients", [])
    ingredients_text = "\n".join(f"- {i}" for i in ingredients_list)
 
    steps_list  = recipe.get("steps", [])
    steps_text  = "\n".join(s.get("text", "") for s in steps_list if s.get("text"))
 
    chunk = f"""Tên món: {title}
Mô tả: {description}
Thời gian nấu: {cook_time} | Khẩu phần: {servings}
Nguyên liệu chính: {ner_tags}
 
Nguyên liệu chi tiết:
{ingredients_text}
 
Cách làm:
{steps_text}"""
    
    return chunk.strip()

def build_metadata(recipe: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tạo metadata dict để lưu kèm trong ChromaDB.
    ChromaDB chỉ chấp nhận str | int | float | bool trong metadata,
    nên list phải được join thành string.
    """
    return {
        "recipe_id"       : str(recipe.get("id", "")),
        "title"           : recipe.get("title", ""),
        "url"             : recipe.get("url", ""),
        "cook_time"       : recipe.get("cook_time", ""),
        "servings"        : recipe.get("servings", ""),
        "ner"             : ", ".join(recipe.get("ner", [])),   # list → str
        "author"          : recipe.get("author", ""),
        "author_location" : recipe.get("author_location", ""),
    }

# ---------- Main processor ----------
def process_recipes(input_path: str) -> List[Dict[str, Any]]:
    """
    Đọc file JSONL (mỗi dòng 1 recipe JSON) hoặc JSON array,
    trả về list các chunk dict sẵn sàng để embed.
 
    Mỗi phần tử trả về có dạng:
    {
        "id"      : str,   # recipe_id, dùng làm ChromaDB document id
        "document": str,   # text chunk để embed
        "metadata": dict,  # metadata để filter sau này
    }
    """
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {input_path}")
 
    raw_text = path.read_text(encoding="utf-8").strip()

    # Hỗ trợ cả JSON array lẫn JSONL
    if raw_text.startswith("["):
        recipes = json.loads(raw_text)
    else:
        recipes = [json.loads(line) for line in raw_text.splitlines() if line.strip()]
 
    chunks = []
    skipped = 0
 
    for recipe in recipes:
        recipe_id = str(recipe.get("id", "")).strip()
        if not recipe_id:
            skipped += 1
            continue
 
        chunks.append({
            "id"      : recipe_id,
            "document": recipe_to_text(recipe),
            "metadata": build_metadata(recipe),
        })
 
    print(f"[chunking] Tổng recipe: {len(recipes)} | "
          f"Chunks tạo được: {len(chunks)} | Bỏ qua: {skipped}")
    return chunks

def save_chunks(chunks: List[Dict[str, Any]], output_path: str) -> None:
    """Lưu chunks ra file JSONL để embedding.py đọc lại."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    print(f"[chunking] Đã lưu {len(chunks)} chunks → {output_path}")

# ---------- Entry point ----------
if __name__ == "__main__":
    import argparse
 
    parser = argparse.ArgumentParser(description="Chunk recipe JSON thành text.")
    parser.add_argument("--input",  default="data/data.jsonl",
                        help="File JSONL hoặc JSON array đầu vào")
    parser.add_argument("--output", default="data/chunks.jsonl",
                        help="File JSONL chunks đầu ra")
    args = parser.parse_args()
 
    chunks = process_recipes(args.input)
    save_chunks(chunks, args.output)