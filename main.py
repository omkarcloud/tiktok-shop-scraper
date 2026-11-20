"""Use the scraper straight from Python, no server needed.

    python main.py

Each call validates its params with the same schema the API uses (so the
defaults apply) and returns the same JSON the API does, except that a list
keeps its `pagination` block instead of next / previous links. The results
are written to output/*.json.
"""
import json
import os

from tiktok_shop import api, schemas
from schema_fields import load_query

os.makedirs("output", exist_ok=True)


def run(schema_cls, impl, **params):
    data, error = load_query(schema_cls, {k: str(v) for k, v in params.items()})
    if error:
        raise ValueError(error)
    return impl(**data)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # the full record of PAVOI's 14K Gold Plated Tennis Bracelet (an id or any product link): price,
    # every SKU with its stock, shipping dates, rating breakdown, specs, the shop and its first 5 reviews
    save("products_details.json", run(schemas.ProductsDetailsSchema, api.products_details, product='1729554646471512584'))

    # the first result page of a "dog toys" search: up to 30 products with price, rating and units
    # sold, plus the shops, filters and related searches the page shows
    save("products_search.json", run(schemas.ProductsSearchSchema, api.products_search, query='dog toys'))

    # the storefront's category tree: every top category with its subcategories, ids and links
    save("categories_list.json", run(schemas.CategoriesListSchema, api.categories_list))
