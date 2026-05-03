import json
from pathlib import Path
from functools import lru_cache

_DATA_DIR = Path(__file__).parent.parent / "data" / "mock"


@lru_cache(maxsize=None)
def load_categories() -> list[dict]:
    with open(_DATA_DIR / "categories.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def load_products() -> list[dict]:
    with open(_DATA_DIR / "products.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def load_reviews() -> list[dict]:
    with open(_DATA_DIR / "reviews.json", encoding="utf-8") as f:
        return json.load(f)


def get_product_by_id(product_id: str) -> dict | None:
    return next((p for p in load_products() if p["id"] == product_id), None)


def get_category_by_id(category_id: str) -> dict | None:
    return next((c for c in load_categories() if c["id"] == category_id), None)


def get_products_by_category(category_id: str) -> list[dict]:
    return [p for p in load_products() if p["category_id"] == category_id]


def get_reviews_by_product(product_id: str) -> list[dict]:
    return [r for r in load_reviews() if r["product_id"] == product_id]


def get_sale_products() -> list[dict]:
    return [p for p in load_products() if p.get("is_on_sale")]


def get_popular_products() -> list[dict]:
    return [p for p in load_products() if p.get("is_popular")]
