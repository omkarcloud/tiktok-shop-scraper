"""Marshmallow request schemas for every /tiktok-shop/* route.

ONE param per input (never a sibling `url` / `id` pair):

    product    a product id (1729527313880355335) OR any TikTok Shop product link
    shop       a seller id (7495794203056835079) OR a store link
    category   a category id (601450) OR a category link

Only the US storefront is served, so there is no country param, and the
site's own pages give one result page per search, shop or category (see
fetch.py), so there is no page, sort or filter param either: an unknown
param is a 400 (BaseSchema), not a silently unfiltered answer.
"""
from schema_fields import BaseSchema, QueryField, RefField
from tiktok_shop import refs

MAX_QUERY_LENGTH = 100      # the storefront's own search box takes more; nobody searches a product with a longer text


class ProductRefField(RefField):
    resolver = staticmethod(refs.resolve_product)


class ShopRefField(RefField):
    resolver = staticmethod(refs.resolve_shop)


class CategoryRefField(RefField):
    resolver = staticmethod(refs.resolve_category)


class ProductsSearchSchema(BaseSchema):
    query = QueryField(max_length=MAX_QUERY_LENGTH, metadata={
        "description": "What to search the US TikTok Shop for, e.g. `dog toys`. The answer is the first result page: "
                       "up to 30 products."})


class ProductsDetailsSchema(BaseSchema):
    product = ProductRefField(metadata={
        "description": "A TikTok Shop product id (`1729527313880355335`) or a product link "
                       "(`https://shop.tiktok.com/us/pdp/<name>/1729527313880355335`, "
                       "`https://www.tiktok.com/shop/pdp/...`, `https://shop.tiktok.com/view/product/<id>`)."})


class ShopSchema(BaseSchema):
    shop = ShopRefField(metadata={
        "description": "A TikTok Shop seller id (`7495794203056835079`) or a store link "
                       "(`https://shop.tiktok.com/us/store/<name>/7495794203056835079`). A product's `shop.id` is one."})


class CategoriesListSchema(BaseSchema):
    """categories/list takes no parameter."""


class CategoriesProductsSchema(BaseSchema):
    category = CategoryRefField(metadata={
        "description": "A TikTok Shop category id (`601450`) or a category link "
                       "(`https://shop.tiktok.com/us/c/<name>/601450`). categories/list returns the ids."})
