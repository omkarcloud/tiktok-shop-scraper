"""Offline tests for the /tiktok-shop/* request schemas and the reference
resolvers behind them.

    python -m pytest tiktok_shop/test_schemas.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schema_fields import load_query  # noqa: E402
from tiktok_shop import refs, schemas  # noqa: E402

GOLI, GOLI_SHOP, BEAUTY = "1729527313880355335", "7495794203056835079", "601450"


def ok(schema, **query):
    data, error = load_query(schema, query)
    assert error is None, error
    return data


def bad(schema, **query):
    data, error = load_query(schema, query)
    assert data is None
    return error


# ---- product -----------------------------------------------------------------

@pytest.mark.parametrize("value", [
    GOLI,
    f"  {GOLI}  ",
    f"https://shop.tiktok.com/us/pdp/ashwagandha-gummies-by-goli-ksm-66-mixed-berry-vegan-non-gmo/{GOLI}",
    f"https://shop.tiktok.com/us/pdp/{GOLI}",
    f"https://shop.tiktok.com/us/pdp/x/{GOLI}?source=product_detail&enter_method=url_semantic_301",
    f"https://www.tiktok.com/shop/pdp/honlink-5x-vitamin-c-skincare-set/{GOLI}",
    f"https://www.tiktok.com/shop/pdp/{GOLI}",
    f"https://shop.tiktok.com/view/product/{GOLI}",
    f"https://www.tiktok.com/view/product/{GOLI}?region=US",
    f"https://shop.tiktok.com/view/product/{GOLI}?region=us&locale=en",
    f"https://shop.tiktok.com/us/pdp/x/{GOLI}?region=",
    f"shop.tiktok.com/us/pdp/{GOLI}",
    f"//shop.tiktok.com/us/pdp/{GOLI}/",
    f"https://www.tiktokshop.com/pdp/some-name/{GOLI}",
])
def test_product_accepts_an_id_or_any_product_link(value):
    assert ok(schemas.ProductsDetailsSchema, product=value) == {"product": GOLI}


@pytest.mark.parametrize("value", [
    "goli gummies",                                             # a name is not an id
    "12345",                                                    # too short for a product id
    f"https://www.amazon.com/dp/{GOLI}",                        # another site
    f"https://shop.tiktok.com/us/store/goli-nutrition/{GOLI_SHOP}",     # a store link, not a product
    "https://shop.tiktok.com/us/c/beauty-personal-care/601450",          # a category link
    "https://shop.tiktok.com/us/pdp/some-name/not-an-id",
    "https://vm.tiktok.com/ZTabc123/",                          # a short share link carries no id
])
def test_product_rejects_what_is_not_a_product(value):
    error = bad(schemas.ProductsDetailsSchema, product=value)
    assert "product id" in error["errors"]["product"][0]
    assert "product" in error["error"]


@pytest.mark.parametrize("value", [
    f"https://shop.tiktok.com/gb/pdp/x/{GOLI}",
    f"https://www.tiktok.com/shop/my/pdp/x/{GOLI}",
    f"https://shop-my.tiktok.com/pdp/x/{GOLI}",
    f"https://shop-id.tokopedia.com/pdp/x/{GOLI}",
    f"https://shop-uk.tiktokw.eu/pdp/{GOLI}",
    f"https://shop.tiktok.com/view/product/{GOLI}?region=GB&locale=en-GB",       # the app's share link names its storefront in the query
    f"https://www.tiktok.com/view/product/{GOLI}?locale=ms-MY&region=MY",
])
def test_another_countrys_storefront_is_refused_by_name(value):
    error = bad(schemas.ProductsDetailsSchema, product=value)
    assert error["errors"]["product"] == ["Only the US storefront of TikTok Shop is served."]


def test_product_is_required_and_unknown_params_are_refused():
    assert "product" in bad(schemas.ProductsDetailsSchema)["errors"]
    assert "product" in bad(schemas.ProductsDetailsSchema, product="")["errors"]
    error = bad(schemas.ProductsDetailsSchema, product=GOLI, country="gb")
    assert "country" in error["errors"]


# ---- shop --------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    GOLI_SHOP,
    f"https://shop.tiktok.com/us/store/goli-nutrition/{GOLI_SHOP}",
    f"https://www.tiktok.com/shop/store/goli-nutrition/{GOLI_SHOP}",
    f"https://shop.tiktok.com/us/store/x/{GOLI_SHOP}?seller_id=1",
    f"shop.tiktok.com/us/store/goli-nutrition/{GOLI_SHOP}/",
])
def test_shop_accepts_a_seller_id_or_a_store_link(value):
    assert ok(schemas.ShopSchema, shop=value) == {"shop": GOLI_SHOP}


@pytest.mark.parametrize("value", [
    "Goli Nutrition", "@golinutrition", "123",
    f"https://shop.tiktok.com/us/pdp/x/{GOLI}",
    "https://www.tiktok.com/@golinutrition",
])
def test_shop_rejects_what_is_not_a_shop(value):
    assert "seller id" in bad(schemas.ShopSchema, shop=value)["errors"]["shop"][0]


def test_shop_of_another_storefront():
    assert bad(schemas.ShopSchema, shop=f"https://shop.tiktok.com/gb/store/x/{GOLI_SHOP}")["errors"]["shop"] == [
        "Only the US storefront of TikTok Shop is served."]


# ---- category ----------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    (BEAUTY, BEAUTY),
    ("1298960", "1298960"),
    ("https://shop.tiktok.com/us/c/beauty-personal-care/601450", BEAUTY),
    ("https://www.tiktok.com/shop/c/beauty-personal-care/601450", BEAUTY),
    ("https://shop.tiktok.com/us/c/x/601616?page=2", "601616"),
])
def test_category_accepts_an_id_or_a_category_link(value, expected):
    assert ok(schemas.CategoriesProductsSchema, category=value) == {"category": expected}


@pytest.mark.parametrize("value", ["beauty", "12", "https://shop.tiktok.com/us/c", f"https://shop.tiktok.com/us/pdp/x/{GOLI}"])
def test_category_rejects_what_is_not_a_category(value):
    assert "category id" in bad(schemas.CategoriesProductsSchema, category=value)["errors"]["category"][0]


def test_categories_list_takes_nothing():
    assert ok(schemas.CategoriesListSchema) == {}
    assert "region" in bad(schemas.CategoriesListSchema, region="US")["errors"]


# ---- search ------------------------------------------------------------------

def test_search_query():
    assert ok(schemas.ProductsSearchSchema, query="  dog   toys ") == {"query": "dog toys"}
    assert ok(schemas.ProductsSearchSchema, query="原神") == {"query": "原神"}
    assert "query" in bad(schemas.ProductsSearchSchema)["errors"]
    assert "query" in bad(schemas.ProductsSearchSchema, query="   ")["errors"]
    assert "query" in bad(schemas.ProductsSearchSchema, query="x" * (schemas.MAX_QUERY_LENGTH + 1))["errors"]


@pytest.mark.parametrize("param", ["page", "sort", "limit", "country", "min_price"])
def test_search_refuses_the_params_the_site_cannot_apply(param):
    """One result page, no sort, no filter (fetch.py): asking for one is a
    400, not a silently unfiltered answer."""
    assert param in bad(schemas.ProductsSearchSchema, query="dog toys", **{param: "2"})["errors"]


def test_every_field_has_a_description():
    for schema in (schemas.ProductsSearchSchema, schemas.ProductsDetailsSchema, schemas.ShopSchema,
                   schemas.CategoriesListSchema, schemas.CategoriesProductsSchema):
        for name, field in schema().fields.items():
            assert field.metadata.get("description"), f"{schema.__name__}.{name}"


# ---- links -------------------------------------------------------------------

def test_link_builders():
    assert refs.product_link(GOLI) == f"https://shop.tiktok.com/us/pdp/{GOLI}"
    assert refs.product_link(GOLI, "some-name") == f"https://shop.tiktok.com/us/pdp/some-name/{GOLI}"
    assert refs.product_link(None) is None
    assert refs.shop_link(GOLI_SHOP, "Goli® Nutrition") == f"https://shop.tiktok.com/us/store/goli-nutrition/{GOLI_SHOP}"
    assert refs.shop_link(GOLI_SHOP) == f"https://shop.tiktok.com/us/store/shop/{GOLI_SHOP}"
    assert refs.shop_link(None, "x") is None
    assert refs.category_link(BEAUTY, "beauty-personal-care") == "https://shop.tiktok.com/us/c/beauty-personal-care/601450"
    assert refs.category_link(BEAUTY) == "https://shop.tiktok.com/us/c/category/601450"
    assert refs.search_link("dog toys & more") == "https://shop.tiktok.com/us/s?q=dog%20toys%20%26%20more"
    assert refs.slug("  Happy Cute pet Depot ") == "happy-cute-pet-depot" and refs.slug("***") is None and refs.slug(None) is None


def test_built_links_resolve_back():
    assert refs.resolve_product(refs.product_link(GOLI, "a-b")) == GOLI
    assert refs.resolve_shop(refs.shop_link(GOLI_SHOP, "Goli Nutrition")) == GOLI_SHOP
    assert refs.resolve_category(refs.category_link(BEAUTY, "beauty-personal-care")) == BEAUTY
