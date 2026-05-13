import csv
import logging
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, List, Any

logger = logging.getLogger(__name__)


BASE_DIR = Path(__file__).resolve().parent.parent

# Vietnamese ingredients dataset path
VIETNAMESE_CSV_ENV = os.getenv("VIETNAMESE_INGREDIENTS_CSV")
if VIETNAMESE_CSV_ENV:
    VIETNAMESE_CSV = Path(VIETNAMESE_CSV_ENV)
else:
    VIETNAMESE_CSV = BASE_DIR / "data" / "Vietnamese_ingredients.csv"

# Scoring thresholds (configurable)
SCORE_PREFIX_BONUS = 0.4  # Bonus for prefix match
SCORE_CONTAINS_BONUS = 0.25  # Bonus for substring match
SCORE_FRESH_BONUS = 0.2  # Bonus for raw/fresh items
SCORE_PROCESSED_PENALTY = 0.35  # Penalty for processed items
SCORE_MIN_THRESHOLD = 0.6  # Minimum score to accept match

def _normalize(value: str) -> str:
    """Normalize string for comparison: lowercase, remove accents and special chars."""
    value = unicodedata.normalize("NFKD", value.lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return " ".join(value.split())


def _query_variants(query: str) -> List[str]:
    """Generate query variants for matching."""
    normalized = _normalize(query)
    return [normalized]


def _safe_float(value: str) -> Optional[float]:
    """Safely convert value to float, return None on error."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def _load_vietnamese_index() -> List[Dict[str, Any]]:
    """Load and index Vietnamese food nutrition data from CSV."""
    if not VIETNAMESE_CSV.exists():
        logger.warning(f"Vietnamese ingredients CSV not found at {VIETNAMESE_CSV}")
        return []

    index = []
    try:
        with VIETNAMESE_CSV.open(newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Parse food name and nutrients
                food_name = row.get("TÊN THỨC ĂN", "").strip()
                if not food_name:
                    continue

                # Parse calories and macronutrients
                # Note: Vietnamese CSV uses commas as decimal separators in some places
                def parse_value(val: str) -> Optional[float]:
                    if not val:
                        return None
                    # Replace Vietnamese comma with dot
                    val = val.replace(",", ".")
                    return _safe_float(val)

                kcal = parse_value(row.get("Calories (kcal)", ""))
                protein = parse_value(row.get("Protein (g)", ""))
                fat = parse_value(row.get("Fat (g)", ""))
                carb = parse_value(row.get("Carbonhydrates (g)", ""))

                if not kcal:
                    continue

                index.append({
                    "name": food_name,
                    "normalized_name": _normalize(food_name),
                    "kcal": kcal,
                    "protein_g": protein,
                    "fat_g": fat,
                    "carb_g": carb,
                    "category": row.get("Loại", ""),
                })
    except Exception as e:
        logger.exception(f"Error loading Vietnamese ingredients CSV: {e}")
        return []

    logger.info(f"Loaded {len(index)} Vietnamese food items")
    return index


def _match_score(query: str, food_name: str) -> float:
    """Calculate matching score between query and food name.
    
    Score components:
    - Base: overlap ratio of tokens (0-1)
    - Prefix bonus: +0.4 if exact prefix match
    - Contains bonus: +0.25 if substring match
    - Fresh bonus: +0.2 for raw/uncooked items
    - Processed penalty: -0.35 for processed items
    """
    query_tokens = set(query.split())
    food_tokens = set(food_name.split())
    food_tokens.update(token[:-1] for token in list(food_tokens) if token.endswith("s") and len(token) > 3)
    if not query_tokens or not food_tokens:
        return 0

    overlap = len(query_tokens & food_tokens)
    if not overlap:
        return 0

    score = overlap / len(query_tokens)
    if food_name.startswith(query):
        score += SCORE_PREFIX_BONUS
    if query in food_name:
        score += SCORE_CONTAINS_BONUS
    if any(term in food_name for term in [" raw", " fresh", " uncooked"]):
        score += SCORE_FRESH_BONUS
    if any(term in food_name for term in ["breaded", "fried", "rings", "frozen", "prepared", "canned"]):
        score -= SCORE_PROCESSED_PENALTY
    return score


def lookup_nutrition(query: str) -> Optional[Dict[str, Any]]:
    """Look up nutrition information for a food item.
    
    Args:
        query: Food name to look up
        
    Returns:
        Dict with nutrition data or None if not found
    """
    best = None
    best_score = 0
    variants = _query_variants(query)

    for item in _load_vietnamese_index():
        food_name = item["normalized_name"]
        for variant in variants:
            score = _match_score(variant, food_name)
            if score > best_score:
                best = item
                best_score = score

    if not best or best_score < SCORE_MIN_THRESHOLD:
        return None

    return {
        "source": "Vietnamese Ingredients Dataset",
        "matched_name": best["name"],
        "kcal_per_100g": best.get("kcal"),
        "protein_g_per_100g": best.get("protein_g"),
        "fat_g_per_100g": best.get("fat_g"),
        "carb_g_per_100g": best.get("carb_g"),
    }


def lookup_many(queries: List[str]) -> Dict[str, Dict[str, Any]]:
    """Look up nutrition information for multiple food items.
    
    Args:
        queries: List of food names to look up
        
    Returns:
        Dict mapping food names to their nutrition data
    """
    results = {}
    for query in queries:
        match = lookup_nutrition(query)
        if match:
            results[query] = match
    return results
