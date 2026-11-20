"""Offline tests for tiktok_shop/parsers.py against the raw captures in
fixtures/ (taken 2026-11-20 through US exits, untrimmed; the large ones
are gzip-packed).

    python -m pytest tiktok_shop/test_parsers.py -q
"""
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tiktok_shop import fetch, parsers  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
GOLI, GOLI_SHOP = "1729527313880355335", "7495794203056835079"


def raw(name):
    path = os.path.join(FIXTURES, name)
    if name.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return f.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def load(name):
    return json.loads(raw(name))


def snake_keys(value, path=""):
    """Every dict key in a result is snake_case; none is `url`."""
    if isinstance(value, dict):
        for key, item in value.items():
            assert key == key.lower() and " " not in key and key != "url", f"{path}.{key}"
            snake_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for item in value:
            snake_keys(item, path + "[]")


# ---- the page ----------------------------------------------------------------

def test_component_and_page_checks():
    page = load("product_1729527313880355335.json.gz")
    assert parsers.is_page(page)
    assert parsers.component(page, "product_info")["error_code"] == 0
    assert parsers.component(page, "no_such_part") == {}
    assert parsers.component({}, "product_info") == {}
    assert parsers.component(None, "product_info") == {}
    assert not parsers.is_page({"message": "x"}) and not parsers.is_page(None) and not parsers.is_page([])


def test_product_missing_forms():
    missing = load("product_not_found.json.gz")
    assert parsers.is_page(missing)
    assert parsers.product_error(missing) == 23004014
    assert parsers.product_error(missing) in parsers.PRODUCT_NOT_FOUND_CODES
    assert missing["waf_decision"]["waf_type"] == 3
    unavailable = load("product_unavailable.json")
    assert parsers.is_unavailable(unavailable) and not parsers.is_page(unavailable)
    assert not parsers.is_unavailable({"message": "something else"})
    assert not parsers.is_unavailable(load("product_1729527313880355335.json.gz"))
    assert parsers.product_error(load("product_1729527313880355335.json.gz")) == 0
    assert parsers.product_error(load("product_no_reviews.json.gz")) == 0


def test_search_full_or_fallback():
    assert parsers.search_is_full(load("search_dog_toys.json.gz")) is True
    assert parsers.search_is_full(load("search_fallback.json.gz")) is False
    assert parsers.search_is_full({}) is False


# ---- a product ---------------------------------------------------------------

def test_product_in_full():
    product = parsers.parse_product(load("product_1729527313880355335.json.gz"))
    snake_keys(product)
    assert product["id"] == GOLI
    assert product["title"].startswith("Goli Ashwagandha & Vitamin D Gummy - Mixed Berry")
    assert product["link"] == f"https://shop.tiktok.com/us/pdp/ashwagandha-gummies-by-goli-ksm-66-mixed-berry-vegan-non-gmo/{GOLI}"
    assert product["brand"] == "Goli"
    assert product["seo_title"] == "Goli Ashwagandha & Vitamin D Gummy - Vegan Berry Supplement"
    assert len(product["keywords"]) == 7 and product["keywords"][0] == "Goli Ashwagandha Gummies"
    assert (product["price"], product["original_price"], product["discount_percent"], product["currency"]) == (19.47, 24.7, 21, "USD")
    assert product["has_price_range"] is False and product["is_in_stock"] is True
    assert product["sold_count"] == 1308473
    assert (product["rating"], product["review_count"]) == (4.5, 94704)
    assert product["rating_counts"] == [{"stars": 5, "count": 75819}, {"stars": 4, "count": 7836}, {"stars": 3, "count": 3745},
                                        {"stars": 2, "count": 1520}, {"stars": 1, "count": 5784}]
    assert sum(row["count"] for row in product["rating_counts"]) == product["review_count"]
    assert product["labels"] == ["Flash sale", "Black Friday", "Free shipping"]
    assert product["sale_ends_at"] == "2026-11-20T23:59:59Z"            # the flash sale's countdown
    assert len(product["images"]) == 8 and all(link.startswith("https://") for link in product["images"])
    assert len(product["description_images"]) == 4
    assert [c["id"] for c in product["categories"]] == ["700645", "700646", "700650", "1298960"]
    assert product["categories"][-1] == {"id": "1298960", "name": "Vitamins Supplements", "level": 4, "is_leaf": True}
    assert len(product["specifications"]) == 9 and product["specifications"][0] == {"name": "Brand", "value": "Goli"}


def test_product_description_is_plain_text():
    product = parsers.parse_product(load("product_1729527313880355335.json.gz"))
    lines = product["description"].split("\n")
    assert lines[0] == "- Goli Nutrition has sold over 90 Million bottles of gummy vitamins."
    assert len(lines) == 5 and all(line.startswith("- ") for line in lines)
    assert "<" not in product["description"] and "{{" not in product["description"]


def test_product_options_skus_and_shipping():
    product = parsers.parse_product(load("product_1729527313880355335.json.gz"))
    assert product["options"] == [{"id": "6936867571236914946", "name": "Size",
                                   "values": [{"id": "7021563638729410310", "value": "1 Bottle", "image": None}]}]
    assert product["default_sku_id"] == "1729527298861535751"
    assert product["skus"] == [{
        "id": "1729527298861535751", "options": [{"name": "Size", "value": "1 Bottle"}], "price": 19.47,
        "original_price": 24.7, "discount_percent": 21, "currency": "USD", "stock": 321387, "is_in_stock": True,
        "purchase_limit": 200, "warehouse_id": "7382962063776565034"}]
    assert product["shipping"] == {
        "method": "Standard shipping", "is_free": True, "fee": 0, "original_fee": 4.95, "currency": "USD",
        "is_deliverable": True, "min_days": 7, "max_days": 10, "estimated_delivery": "Nov 27 - Nov 30",
        "ships_within_days": 3, "ships_from": "local", "summary": "Free shipping",
        "notes": ["Free shipping", "Estimated delivery Nov 27 – 30", "Shipped by Goli Nutrition"]}
    assert product["warnings"][0]["title"] == "WARNING: Disclaimer"
    assert product["warnings"][0]["text"].startswith("Product safety information\nDisclaimer\nThis statement has not been evaluated")
    assert product["seller_information"] == [
        {"name": "Business name", "value": "Goli Nutrition Inc."},
        {"name": "Business address", "value": "8430 Santa Monica Blvd,West Hollywood,California,90069"}]


def test_product_shop_and_first_reviews():
    product = parsers.parse_product(load("product_1729527313880355335.json.gz"))
    shop = product["shop"]
    assert (shop["id"], shop["name"]) == (GOLI_SHOP, "Goli Nutrition")
    assert shop["link"] == f"https://shop.tiktok.com/us/store/goli-nutrition/{GOLI_SHOP}"
    assert (shop["badge"], shop["is_official"], shop["is_brand"], shop["is_verified"]) == ("OFFICIAL SHOP", True, True, True)
    assert (shop["rating"], shop["review_count"], shop["sold_count"]) == (4.6, 412646, 5842726)
    assert (shop["product_count"], shop["follower_count"], shop["video_count"]) == (57, 600512, 5954)
    assert shop["scores"][0] == {"name": "Positive feedback", "value": "89%", "score": 0.89, "grade": "Good"}
    assert [s["name"] for s in shop["scores"]] == ["Positive feedback", "Issue resolution", "Chat satisfaction"]
    assert product["has_more_reviews"] is True and len(product["reviews"]) == 5
    review = product["reviews"][0]
    assert review["id"] == "7660539805688432398"
    assert (review["rating"], review["created_at"], review["reviewer_name"]) == (5, "2026-07-09T14:46:53Z", "M**")
    assert (review["country"], review["is_verified_purchase"], review["is_incentivized"]) == ("US", True, False)
    assert review["text"].startswith("More straight, more healthy than ever")
    assert len(review["images"]) == 5 and review["variant"] == "1 Bottle" and review["sku_id"] == "1729527298861535751"
    assert "product" not in review                       # a product's own reviews do not repeat it
    assert product["reviews"][1]["reviewer_avatar"] is None


def test_sparse_product():
    """No review, no discount, no specification, a description made of one picture."""
    product = parsers.parse_product(load("product_no_reviews.json.gz"))
    snake_keys(product)
    assert product["id"] == "1729478157111563471"
    assert (product["price"], product["original_price"], product["discount_percent"]) == (68, None, None)
    assert (product["rating"], product["review_count"], product["reviews"], product["has_more_reviews"]) == (None, 0, [], False)
    assert all(row["count"] == 0 for row in product["rating_counts"]) and len(product["rating_counts"]) == 5
    assert product["brand"] is None and product["specifications"] == [] and product["warnings"] == []
    assert product["description"] is None and len(product["description_images"]) == 1
    assert product["labels"] == ["Free shipping"] and product["sale_ends_at"] is None
    assert product["shipping"]["summary"] == "Free shipping · Usually ships next day"
    assert product["summary"].startswith("Natural Thick False Eyelashes are designed")
    assert product["highlights"][0] == "Natural thick false eyelashes for a fuller lash look" and len(product["highlights"]) == 5
    assert product["faq"][0] == {"question": "What type of product is this?",
                                 "answer": "This is a pair of natural thick false eyelashes in the fashion accessories category."}
    assert len(product["faq"]) == 5
    assert product["shop"]["name"] == "Caleber Hair" and product["shop"]["cover_image"] is None     # the default cover is not a picture of the shop
    assert product["seller_information"][0] == {"name": "Business name", "value": "Xuchang Qiaopei Trading Co., Ltd."}


def test_missing_product_pages_parse_to_an_empty_record():
    """fetch.py reports these as not found; the parser must not break on them."""
    for name in ("product_not_found.json.gz", "product_unavailable.json"):
        product = parsers.parse_product(load(name))
        assert product["id"] is None and product["title"] is None and product["reviews"] == [] and product["skus"] == []
        assert product["shop"] is None and product["shipping"] is None


# ---- search --------------------------------------------------------------------

def test_search_full_page():
    result = parsers.parse_search(load("search_dog_toys.json.gz"), "dog toys")
    snake_keys(result)
    assert (result["query"], result["link"]) == ("dog toys", "https://shop.tiktok.com/us/s?q=dog%20toys")
    assert (result["is_partial"], result["count"], result["has_more"]) == (False, 30, True)
    assert len(result["products"]) == 30 and len({row["id"] for row in result["products"]}) == 30
    first = result["products"][0]
    assert first["id"] == "1732351377060171992"
    assert first["link"].startswith("https://shop.tiktok.com/us/pdp/random-20-piece-dog-plush-toy-set") and first["link"].endswith(first["id"])
    assert (first["price"], first["original_price"], first["discount_percent"], first["savings"], first["currency"]) == (14.99, 28.8, 48, 13.81, "USD")
    assert (first["rating"], first["review_count"], first["sold_count"]) == (4.1, 7, 40)
    assert first["labels"] == ["Limited time deal", "Free shipping"] and first["is_free_shipping"] is True
    assert first["skus"] == [{"id": "1732351384080781528", "price": 14.99, "original_price": 28.8, "discount_percent": 48,
                              "savings": 13.81, "currency": "USD"}]
    assert first["shop"]["id"] == "7496117110551513304" and first["shop"]["name"] == "Happy Cute pet Depot"
    assert first["shop"]["link"] == "https://shop.tiktok.com/us/store/happy-cute-pet-depot/7496117110551513304"
    assert first["shop"]["is_verified"] is False and first["video"] is None
    bark = next(row for row in result["products"] if row["id"] == "1732610330457707245")
    assert (bark["brand"], bark["price"], bark["original_price"], bark["discount_percent"], bark["savings"]) == ("BARK", 52, None, None, None)
    assert bark["link"] == "https://shop.tiktok.com/us/pdp/1732610330457707245"          # the site gave no slug for it
    assert bark["shop"]["is_verified"] is True
    for row in result["products"]:
        assert row["id"] and row["title"] and row["price"] is not None and row["currency"] == "USD" and row["image"].startswith("https://")


def test_search_shops_facets_and_related():
    result = parsers.parse_search(load("search_dog_toys.json.gz"), "dog toys")
    assert [shop["name"] for shop in result["shops"]] == ["BARK", "Lesure Pet"]
    assert result["shops"][0]["link"] == "https://shop.tiktok.com/us/store/bark/7495272158383868653"
    featured = result["featured_shop"]
    assert (featured["id"], featured["name"], featured["creator_id"]) == ("7495272158383868653", "BARK", "6644515443921485829")
    assert (featured["sold_count"], featured["follower_count"], featured["product_count"]) == (55767, 319146, 33)
    assert len(featured["products"]) == 6 and featured["products"][0]["shop"]["id"] == featured["id"]
    assert [facet["name"] for facet in result["facets"]] == ["Promotions", "Categories", "Color", "Price Range", "Rating"]     # no "Sort by"
    categories = result["facets"][1]
    assert categories["is_multiple_choice"] is True
    assert categories["options"][0] == {"name": "Dog & Cat Accessories", "group": "Pet Supplies", "category_id": "818696", "color": None}
    color = result["facets"][2]
    assert color["options"][0] == {"name": "White", "group": None, "category_id": None, "color": "#FFFFFF"} and len(color["options"]) == 9
    assert [o["name"] for o in result["facets"][3]["options"]] == ["Under $20", "$20 - $40", "$40 - $50", "Over $50"]
    assert result["facets"][3]["is_multiple_choice"] is False
    assert result["related_searches"][0] == {"name": "dog toys to keep them busy", "link": "https://shop.tiktok.com/us/k/dog-toys-to-keep-them-busy"}
    assert result["related_categories"][0] == {"id": "819080", "name": "Dog Toys", "link": "https://shop.tiktok.com/us/c/dog-toys/819080"}
    assert len(result["recommended_products"]) == 10


def test_search_fallback_page():
    result = parsers.parse_search(load("search_fallback.json.gz"), "dog toys", is_partial=True)
    snake_keys(result)
    assert (result["is_partial"], result["count"], result["has_more"]) == (True, 5, False)
    assert result["shops"] == [] and result["facets"] == [] and result["featured_shop"] is None
    assert len(result["products"]) == 5 and all(row["id"] and row["title"] for row in result["products"])


def test_search_of_an_empty_page():
    result = parsers.parse_search({"basic_info": {}, "page_config": {"components_map": []}}, "zzz")
    assert result["products"] == [] and result["count"] == 0 and result["has_more"] is False and result["facets"] == []


# ---- shops ---------------------------------------------------------------------

def test_shop_page():
    page = parsers.parse_shop_page(load("shop_7495794203056835079.json.gz"))
    snake_keys(page)
    shop = page["shop"]
    assert (shop["id"], shop["name"], shop["region"]) == (GOLI_SHOP, "Goli Nutrition", "US")
    assert (shop["creator_name"], shop["creator_id"]) == ("Goli® Nutrition", "6990310143721063429")
    assert shop["description"].startswith("Shop Goli Nutrition on TikTok Shop! 5.8M sold")
    assert shop["cover_image"].startswith("https://") and shop["logo"].startswith("https://")
    assert (shop["rating"], shop["review_count"], shop["sold_count"], shop["product_count"]) == (4.6, 412646, 5842726, 57)
    assert page["promotions"] == ["Campaign", "Buy 2 get 10% off", "Deals", "Free shipping"]
    assert page["categories"][1] == {"id": "1345813", "name": "Health & Household", "level": 1, "product_count": 55,
                                     "subcategories": [{"id": "942221", "name": "Nutrition & Wellness", "level": 2,
                                                        "product_count": 55, "subcategories": []}]}
    assert len(page["products"]) == 20 and page["has_more"] is True
    best = page["products"][0]
    assert (best["id"], best["price"], best["original_price"], best["sold_count"], best["review_count"], best["rating"]) == (
        GOLI, 19.47, 24.7, 1308473, 94704, 4.5)
    assert all(row["shop"]["id"] == GOLI_SHOP for row in page["products"])


def test_shop_page_without_a_shop():
    """What an unknown seller id answers now and then instead of the verification page: the store
    page drawn without a shop (no record, no tab, an empty feed)."""
    page = parsers.parse_shop_page(load("shop_without_a_shop.json.gz"))
    assert page == {"shop": None, "promotions": None, "categories": None, "products": [], "has_more": False}
    page = parsers.parse_shop_page({"basic_info": {}, "page_config": {"components_map": [
        {"component_name": "shop_info", "component_data": {}}]}})
    assert page == {"shop": None, "promotions": None, "categories": None, "products": None, "has_more": False}
    assert parsers.parse_shop(None) is None and parsers.parse_shop({"shop_name": "no id"}) is None


def test_shop_read_from_its_json_calls():
    """A shop whose page is guarded: fetch._shop_parts puts store_info's record and product_list's first
    page where the page keeps them, so the same parser reads them. The page's tab is not among them."""
    record = load("store_info_7494894286294844644.json")["data"]
    feed = load("store_products_7494894286294844644.json.gz")["data"]
    page = parsers.parse_shop_page(fetch._shop_parts(record, feed))
    snake_keys(page)
    shop = page["shop"]
    assert (shop["id"], shop["name"], shop["region"], shop["creator_name"]) == ("7494894286294844644", "AllWELL MARKET", "US",
                                                                                "AllWELL MARKET")
    assert (shop["rating"], shop["review_count"], shop["sold_count"], shop["product_count"]) == (4.0, 8, 180, 38)
    assert (shop["follower_count"], shop["video_count"], shop["is_official"], shop["badge"]) == (8, 0, False, None)
    assert shop["description"].startswith("Shop AllWELL MARKET on TikTok Shop! 180 sold")
    assert page["promotions"] is None and page["categories"] is None
    assert len(page["products"]) == 20 and page["has_more"] is True
    first = page["products"][0]
    assert (first["id"], first["price"], first["sold_count"]) == ("1732789824092606692", 9.99, 65)
    assert all(row["shop"]["id"] == "7494894286294844644" for row in page["products"])
    assert parsers.parse_shop_page(fetch._shop_parts(record, None))["products"] is None     # the product list did not answer


# ---- categories ----------------------------------------------------------------

def test_category_tree():
    tree = parsers.parse_category_tree(load("category_601450.json.gz"))
    snake_keys(tree)
    assert len(tree) == 28 and sum(len(top["subcategories"]) for top in tree) == 212
    beauty = tree[0]
    assert (beauty["id"], beauty["name"], beauty["level"], beauty["is_leaf"], beauty["parent_id"]) == (
        "601450", "Beauty & Personal Care", 1, False, None)
    assert beauty["link"] == "https://shop.tiktok.com/us/c/beauty-personal-care/601450"
    assert len(beauty["subcategories"]) == 12
    assert beauty["subcategories"][0] == {
        "id": "849032", "name": "Hand & Foot Care", "link": "https://shop.tiktok.com/us/c/hand-foot-care/849032",
        "image": beauty["subcategories"][0]["image"], "level": 2, "is_leaf": False, "parent_id": "601450"}
    # every page answer carries the same tree, the page of an unknown category included
    assert [top["id"] for top in parsers.parse_category_tree(load("category_not_found.json.gz"))] == [top["id"] for top in tree]
    assert parsers.parse_category_tree({}) == []


def test_top_category_page():
    page = parsers.parse_category_page(load("category_601450.json.gz"))
    snake_keys(page)
    assert page["category"]["id"] == "601450" and page["category"]["parent_id"] is None and page["parents"] == []
    assert len(page["subcategories"]) == 12 and page["subcategories"][0]["id"] == "849032"
    assert len(page["products"]) == 15 and page["has_more"] is True
    assert all(row["id"] and row["price"] is not None for row in page["products"])
    assert len(page["reviews"]) == 10
    review = page["reviews"][0]
    assert (review["id"], review["rating"], review["created_at"], review["reviewer_name"]) == (
        "7707192310626780941", 5, "2026-11-12T08:04:40Z", "D**h")
    assert review["product"]["id"] == "1729508370969629931"
    assert review["product"]["name"].startswith("[medicube] PDRN Pink Collagen Volume Multi Balm")
    assert review["product"]["link"] == "https://shop.tiktok.com/us/pdp/1729508370969629931"
    assert len(review["images"]) == 1 and review["is_verified_purchase"] is None


def test_leaf_category_page():
    page = parsers.parse_category_page(load("category_601616_leaf.json.gz"))
    assert page["category"] == {
        "id": "601616", "name": "Face Masks", "link": "https://shop.tiktok.com/us/c/face-masks/601616",
        "image": page["category"]["image"], "level": 3, "is_leaf": True, "parent_id": "848776"}
    assert page["parents"] == [
        {"id": "601450", "name": "Beauty & Personal Care", "link": "https://shop.tiktok.com/us/c/beauty-personal-care/601450"},
        {"id": "848776", "name": "Skincare", "link": "https://shop.tiktok.com/us/c/skincare/848776"}]
    assert page["subcategories"] == [] and len(page["products"]) == 15


def test_unknown_category_page():
    page = parsers.parse_category_page(load("category_not_found.json.gz"))
    assert page == {"category": None, "parents": [], "subcategories": [], "products": [], "has_more": False, "reviews": []}


# ---- small values --------------------------------------------------------------

def test_video_of_a_row():
    """The creator video the site pins to some rows (seen on its keyword pages)."""
    video = parsers.parse_video({
        "item_id": "7593494835428953357", "height": 1920, "width": 1080, "duration": 8474, "author_id": "6921029601293517830",
        "play_count": "560123", "like_count": "58531", "upload_time": "1767998322", "title": "mood ✨ #2026 ",
        "cover_image_url": "https://p19-common-sign.tiktokcdn-us.com/c.jpg", "content_url": "https://v16m-default.tiktokcdn-us.com/v.mp4",
        "author_name": "Natalia", "author_avatar_url": "https://p16-common-sign.tiktokcdn-us.com/a.jpg",
        "bc_ad_label_text": "Creator earns commission"})
    assert video == {
        "id": "7593494835428953357", "title": "mood ✨ #2026", "link": "https://v16m-default.tiktokcdn-us.com/v.mp4",
        "cover_image": "https://p19-common-sign.tiktokcdn-us.com/c.jpg", "duration_seconds": 8.5, "width": 1080, "height": 1920,
        "play_count": 560123, "like_count": 58531, "posted_at": "2026-01-09T22:38:42Z",
        "author": {"id": "6921029601293517830", "name": "Natalia", "avatar": "https://p16-common-sign.tiktokcdn-us.com/a.jpg"},
        "disclosure": "Creator earns commission"}
    assert parsers.parse_video(None) is None and parsers.parse_video({}) is None


def test_percent_and_dates():
    assert parsers._percent("48%") == 48 and parsers._percent("-21%") == 21 and parsers._percent("0.21") == 21
    assert parsers._percent(None) is None and parsers._percent("") is None and parsers._percent("free") is None
    assert parsers._milliseconds_utc("1783608413879") == "2026-07-09T14:46:53Z"
    assert parsers._milliseconds_utc(None) is None and parsers._milliseconds_utc("junk") is None and parsers._milliseconds_utc("0") is None


def test_parsers_tolerate_junk():
    for junk in (None, {}, [], "text", 5):
        assert parsers.parse_product(junk)["id"] is None
        assert parsers.parse_search(junk, "q")["products"] == []
        assert parsers.parse_shop_page(junk)["shop"] is None
        assert parsers.parse_category_page(junk)["category"] is None
        assert parsers.parse_category_tree(junk) == []
        assert parsers.parse_product_row(junk)["id"] is None
        assert parsers.parse_review(junk)["id"] is None
