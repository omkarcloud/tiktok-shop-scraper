"""The /tiktok-shop/* endpoint functions (route_glue's route_table calls
them with the schema's loaded kwargs).

Caching (cache.cached_call) sits here, so endpoints that read the same
page pay one fetch:

  tiktok_shop.shop        the parsed shop page: shops/details and
                          shops/products are two views of it
  tiktok_shop.search      a search answer; a partial one (the site's
                          fallback rows) is kept for two minutes only
  tiktok_shop.product     a product in full
  tiktok_shop.categories  the category tree
  tiktok_shop.category    a category page

Every listing is ONE page: what the site's own page shows before its
script loads more (see fetch.py). `has_more` says the site has more than
the answer carries.
"""
from cache import cached_call
from tiktok_shop import cache_config as ttl
from tiktok_shop import parsers
from tiktok_shop.fetch import (TikTokShopNotFound, TikTokShopUnavailable, fetch_category, fetch_category_tree, fetch_product,
                               fetch_search, fetch_shop)


# ---- products/search ---------------------------------------------------------

def _products_search(query):
    payload, is_partial = fetch_search(query)
    return parsers.parse_search(payload, query, is_partial)


def _search_ttl(data, result):
    return ttl.SEARCH_PARTIAL_CACHE if result.get("is_partial") else ttl.SEARCH_CACHE


def products_search(**data):
    """The first result page of a search: up to 30 products with the shops,
    facets and related searches the page shows. `is_partial` is true when
    the site gave only its short fallback list after every try."""
    return cached_call("tiktok_shop.search", data, _products_search, _search_ttl)


# ---- products/details --------------------------------------------------------

def _products_details(product):
    return parsers.parse_product(fetch_product(product))


def products_details(**data):
    return cached_call("tiktok_shop.product", data, _products_details, ttl.PRODUCT_CACHE)


# ---- shops -------------------------------------------------------------------

def _shop_page(shop):
    page = parsers.parse_shop_page(fetch_shop(shop))
    if not page["shop"]:
        raise TikTokShopNotFound(f"shop {shop} not found")
    return page


def _shop_ttl(data, page):
    """A shop read from its page's JSON calls (its page was guarded) lacks
    its promotions and categories, and maybe its products: kept briefly."""
    if page["promotions"] is None or page["products"] is None:
        return ttl.SHOP_PARTIAL_CACHE
    return ttl.SHOP_CACHE


def _page_of(shop):
    return cached_call("tiktok_shop.shop", {"shop": shop}, _shop_page, _shop_ttl)


def shops_details(shop):
    """The shop's profile, the promotions it runs and its own categories
    (None, not [], when TikTok Shop guarded the shop's page: only the page
    shows them)."""
    page = _page_of(shop)
    return {**page["shop"], "promotions": page["promotions"], "categories": page["categories"]}


def shops_products(shop):
    """The shop's best sellers: the 20 products its page opens with."""
    page = _page_of(shop)
    if page["products"] is None:
        raise TikTokShopUnavailable(f"TikTok Shop guards shop {shop}'s page and its product list did not answer; "
                                    "try again in a few minutes")
    profile = page["shop"]
    return {
        "shop": {"id": profile["id"], "name": profile["name"], "link": profile["link"]},
        "count": len(page["products"]),
        "has_more": page["has_more"],
        "products": page["products"],
    }


# ---- categories --------------------------------------------------------------

def _categories_list():
    tree = parsers.parse_category_tree(fetch_category_tree())
    return {"count": sum(1 + len(top["subcategories"]) for top in tree), "categories": tree}


def categories_list(**data):
    """The storefront's category tree: the top categories with their children."""
    return cached_call("tiktok_shop.categories", data, _categories_list, ttl.CATEGORIES_CACHE)


def _categories_products(category):
    page = parsers.parse_category_page(fetch_category(category))
    if not page["category"]:
        raise TikTokShopNotFound(f"category {category} not found")
    return {
        "category": page["category"],
        "parents": page["parents"],
        "subcategories": page["subcategories"],
        "count": len(page["products"]),
        "has_more": page["has_more"],
        "products": page["products"],
        "reviews": page["reviews"],
    }


def categories_products(**data):
    """A sample of the category's products (the site answers a different
    10 to 15 on every call) with its recent reviews and child categories."""
    return cached_call("tiktok_shop.category", data, _categories_products, ttl.CATEGORY_PRODUCTS_CACHE)
