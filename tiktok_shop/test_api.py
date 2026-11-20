"""Offline tests for the endpoint logic (tiktok_shop/api.py), with the
fetch layer and the cache replaced by fakes: the answers are the fixtures.

    python -m pytest tiktok_shop/test_api.py -q
"""
import gzip
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper_errors import NotFound, Unavailable  # noqa: E402
from tiktok_shop import api, fetch  # noqa: E402
from tiktok_shop import cache_config as ttl  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
GOLI, GOLI_SHOP = "1729527313880355335", "7495794203056835079"


def load(name):
    path = os.path.join(FIXTURES, name)
    opener = gzip.open if name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(autouse=True)
def cache(monkeypatch):
    """cached_call runs the function every time and records the namespace,
    the key and the TTL it would have stored the answer for."""
    calls = []

    def cached_call(namespace, data, fn, row_ttl, **kw):
        result = fn(**data)
        calls.append({"namespace": namespace, "key": dict(data), "ttl": row_ttl(data, result) if callable(row_ttl) else row_ttl})
        return result
    monkeypatch.setattr(api, "cached_call", cached_call)
    return calls


@pytest.fixture
def site(monkeypatch):
    """The fetch layer answers from fixtures and records what was asked."""
    asked = []
    answers = {"search": (load("search_dog_toys.json.gz"), False), "product": load("product_1729527313880355335.json.gz"),
               "shop": load("shop_7495794203056835079.json.gz"), "category": load("category_601450.json.gz")}

    def fake(kind):
        def call(value):
            asked.append((kind, value))
            answer = answers[kind]
            if isinstance(answer, Exception):
                raise answer
            return answer
        return call
    for kind in answers:
        monkeypatch.setattr(api, f"fetch_{kind}", fake(kind))
    monkeypatch.setattr(api, "fetch_category_tree", lambda: fake("category")("tree"))
    return answers, asked


def test_products_search(site, cache):
    result = api.products_search(query="dog toys")
    assert list(result)[:6] == ["query", "link", "is_partial", "count", "has_more", "products"]
    assert (result["query"], result["is_partial"], result["count"], len(result["products"])) == ("dog toys", False, 30, 30)
    assert site[1] == [("search", "dog toys")]
    assert cache == [{"namespace": "tiktok_shop.search", "key": {"query": "dog toys"}, "ttl": ttl.SEARCH_CACHE}]


def test_a_partial_search_is_flagged_and_kept_only_briefly(site, cache):
    site[0]["search"] = (load("search_fallback.json.gz"), True)
    result = api.products_search(query="dog toys")
    assert (result["is_partial"], result["count"], result["has_more"]) == (True, 5, False)
    assert cache[0]["ttl"] == ttl.SEARCH_PARTIAL_CACHE and ttl.SEARCH_PARTIAL_CACHE < ttl.SEARCH_CACHE


def test_products_details(site, cache):
    result = api.products_details(product=GOLI)
    assert result["id"] == GOLI and len(result["reviews"]) == 5 and result["shop"]["id"] == GOLI_SHOP
    assert list(result)[:3] == ["id", "title", "link"]
    assert site[1] == [("product", GOLI)]
    assert cache == [{"namespace": "tiktok_shop.product", "key": {"product": GOLI}, "ttl": ttl.PRODUCT_CACHE}]


def test_the_two_shop_endpoints_are_views_of_one_cached_page(site, cache):
    details = api.shops_details(shop=GOLI_SHOP)
    products = api.shops_products(shop=GOLI_SHOP)
    assert [c["namespace"] for c in cache] == ["tiktok_shop.shop", "tiktok_shop.shop"]
    assert cache[0]["key"] == cache[1]["key"] == {"shop": GOLI_SHOP}                     # one cache row serves both
    assert cache[0]["ttl"] == ttl.SHOP_CACHE                                              # the full page: the long TTL
    assert (details["id"], details["name"], details["product_count"]) == (GOLI_SHOP, "Goli Nutrition", 57)
    assert details["promotions"] == ["Campaign", "Buy 2 get 10% off", "Deals", "Free shipping"]
    assert details["categories"][1]["name"] == "Health & Household" and "products" not in details
    assert list(products) == ["shop", "count", "has_more", "products"]
    assert products["shop"] == {"id": GOLI_SHOP, "name": "Goli Nutrition",
                                "link": f"https://shop.tiktok.com/us/store/goli-nutrition/{GOLI_SHOP}"}
    assert (products["count"], products["has_more"], products["products"][0]["id"]) == (20, True, GOLI)


def test_a_guarded_shop_is_answered_from_its_json_calls(site, cache):
    """Its page answered the Security Check: the record and the products came from the page's own
    calls. Promotions and categories are unknown (None), and the answer is kept for a short time."""
    record = load("store_info_7494894286294844644.json")["data"]
    feed = load("store_products_7494894286294844644.json.gz")["data"]
    site[0]["shop"] = fetch._shop_parts(record, feed)
    details = api.shops_details(shop="7494894286294844644")
    products = api.shops_products(shop="7494894286294844644")
    assert (details["name"], details["sold_count"], details["promotions"], details["categories"]) == ("AllWELL MARKET", 180, None, None)
    assert (products["shop"]["name"], products["count"], products["has_more"]) == ("AllWELL MARKET", 20, True)
    assert [c["ttl"] for c in cache] == [ttl.SHOP_PARTIAL_CACHE, ttl.SHOP_PARTIAL_CACHE]
    assert ttl.SHOP_PARTIAL_CACHE < ttl.SHOP_CACHE


def test_a_guarded_shop_whose_products_did_not_answer(site, cache):
    """shops/details still answers; shops/products answers 503 (Unavailable), never an empty list."""
    site[0]["shop"] = fetch._shop_parts(load("store_info_7494894286294844644.json")["data"], None)
    assert api.shops_details(shop="7494894286294844644")["product_count"] == 38
    with pytest.raises(Unavailable, match="try again in a few minutes"):
        api.shops_products(shop="7494894286294844644")


def test_a_shop_page_without_a_shop_is_not_found(site):
    site[0]["shop"] = {"basic_info": {}, "page_config": {"components_map": []}}
    with pytest.raises(NotFound, match="shop 1234567890123 not found"):
        api.shops_details(shop="1234567890123")
    with pytest.raises(NotFound):
        api.shops_products(shop="1234567890123")


def test_categories_list_reads_the_tree_from_the_configured_page(site, cache):
    result = api.categories_list()
    assert site[1] == [("category", "tree")]
    assert result["count"] == 240 and len(result["categories"]) == 28
    assert result["categories"][0]["name"] == "Beauty & Personal Care" and len(result["categories"][0]["subcategories"]) == 12
    assert cache == [{"namespace": "tiktok_shop.categories", "key": {}, "ttl": ttl.CATEGORIES_CACHE}]


def test_categories_list_survives_the_configured_page_going_away(site):
    """Every page answer carries the tree, the page of an unknown category too."""
    site[0]["category"] = load("category_not_found.json.gz")
    assert api.categories_list()["count"] == 240


def test_categories_products(site, cache):
    result = api.categories_products(category="601450")
    assert list(result) == ["category", "parents", "subcategories", "count", "has_more", "products", "reviews"]
    assert result["category"]["name"] == "Beauty & Personal Care" and result["count"] == 15 == len(result["products"])
    assert len(result["subcategories"]) == 12 and len(result["reviews"]) == 10 and result["has_more"] is True
    assert cache == [{"namespace": "tiktok_shop.category", "key": {"category": "601450"}, "ttl": ttl.CATEGORY_PRODUCTS_CACHE}]


def test_an_unknown_category_is_not_found(site):
    site[0]["category"] = api.TikTokShopNotFound("category 999999999 not found")
    with pytest.raises(NotFound, match="category 999999999 not found"):
        api.categories_products(category="999999999")
    site[0]["category"] = load("category_not_found.json.gz")          # and a page without the record, should one get through
    with pytest.raises(NotFound, match="category 999999999 not found"):
        api.categories_products(category="999999999")


def test_a_missing_product_surfaces_as_not_found(site):
    site[0]["product"] = api.TikTokShopNotFound("product 1 not found")
    with pytest.raises(NotFound, match="product 1 not found"):
        api.products_details(product="1")
