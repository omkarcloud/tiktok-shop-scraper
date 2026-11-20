"""Page data -> clean dicts for every /tiktok-shop/* endpoint.

Pure functions, no I/O. The input is always the JSON a storefront page is
built from (fetch.py's `?__loader=` answer): a `page_config` whose
`components_map` lists the page's parts by `component_name`, each with its
`component_data`. Every page answer also carries `category_hierarchy`, the
storefront's category tree.

Fixtures (fixtures/, raw answers captured 2026-11-20 through US exits):
  product_1729527313880355335.json.gz   a product in full (94,704 reviews, a flash sale, 9 description blocks)
  product_no_reviews.json.gz            a sparse product: no review, no discount, no specifications
  product_not_found.json.gz             an id that does not exist: error 23004014, `waf_type` 3
  product_unavailable.json              the 80-byte answer of a product the site no longer sells
  search_dog_toys.json.gz               a full search answer: 30 rows, 6 facets, 2 shops
  search_fallback.json.gz               the 5-row fallback answer of the same kind of query
  shop_7495794203056835079.json.gz      a shop page: profile, 20 best sellers, its own categories
  shop_without_a_shop.json.gz           the store page drawn without a shop (an unknown seller id, now and then)
  store_info_7494894286294844644.json   store_info's answer: the record of a shop whose page is guarded
  store_info_no_shop.json               store_info's answer for a seller id that has no shop: success, no record
  store_products_7494894286294844644.json.gz   product_list's first page for that shop: its 20 products
  store_products_empty.json             product_list's empty answer (an unknown seller id; a real shop now and then)
  category_601450.json.gz               a top category: 12 children, 15 products, 10 reviews
  category_601616_leaf.json.gz          a leaf category (level 3, no children)
  category_not_found.json.gz            an unknown category id: `categoryInfo` is null
  verification_page.html                the "Security Check" page: fetch.py's block signal, and what an
                                        unknown seller id and some real shops' pages answer
No fixture: a product answered with error 23002102 (seen once, 6.7 KB, not
kept).

Units, as the site sends them: prices are decimal strings in US dollars
("19.47", "52"), counts are often strings ("94704"), a review's time is
epoch milliseconds as a string, and a description is a list of text and
picture blocks, not HTML. Picture and video links are signed and expire.
"""
import re

from scraper_utils.dates import epoch_utc
from scraper_utils.text import clean, multiline
from scraper_utils.values import amount, as_dict, as_list, count, g, rating, to_int
from tiktok_shop import refs

# what an unknown or withdrawn product answers (fetch.py tells them from a refusal)
PRODUCT_NOT_FOUND_CODES = (23002102, 23004014)
PRODUCT_UNAVAILABLE_TEXT = "not currently available"


# ---- the page --------------------------------------------------------------

def component(payload, name):
    """The `component_data` of the page part called `name` ({} when the
    page has no such part or the part came empty)."""
    for part in as_list(g(payload, "page_config", "components_map")):
        if isinstance(part, dict) and part.get("component_name") == name:
            return as_dict(part.get("component_data"))
    return {}


def has_component(payload, name):
    """True when the page carries a part called `name`, even an empty one."""
    return any(isinstance(part, dict) and part.get("component_name") == name
               for part in as_list(g(payload, "page_config", "components_map")))


def is_page(payload):
    """True for a storefront page's data (it always names its visitor)."""
    return isinstance(payload, dict) and isinstance(payload.get("basic_info"), dict)


def is_unavailable(payload):
    """True for the bare {"message": "The product is not currently available
    in your country or region."} answer."""
    return (isinstance(payload, dict) and "basic_info" not in payload
            and PRODUCT_UNAVAILABLE_TEXT in str(payload.get("message") or ""))


def product_error(payload):
    """The error code a product page carries instead of a product (0 / None
    when the product is there)."""
    return to_int(component(payload, "product_info").get("error_code")) or 0


def search_is_full(payload):
    """True when a search answer is the real result page. The site answers
    about 6 searches in 10 with a fallback list instead: 5 rows, no facets
    and no token for a next page."""
    feed = component(payload, "feed_list_search_word")
    return bool(as_list(feed.get("filter_sections")) or g(feed, "load_more_params", "page_token"))


# ---- small values ----------------------------------------------------------

def _image(value):
    """{url_list: [...]} -> its first link."""
    for link in as_list(as_dict(value).get("url_list")):
        if isinstance(link, str) and link.startswith("http"):
            return link
    return None


def _percent(value):
    """'48%' / '-21%' / '0.21' -> 48 / 21 / 21; None when there is none."""
    if value is None:
        return None
    text = str(value).strip()
    match = re.search(r"\d+(\.\d+)?", text)
    if not match:
        return None
    number = float(match.group(0))
    if "%" not in text and number <= 1:
        number *= 100
    return to_int(round(number)) or None


def _milliseconds_utc(value):
    """'1783608413879' -> '2026-07-09T…Z'."""
    millis = to_int(value)
    return epoch_utc(millis // 1000) if millis else None


def _labels(marketing):
    """The promotion labels on a product, in the site's order, each once
    ('Flash sale', 'Free shipping', 'Black Friday')."""
    seen = []
    placements = as_dict(as_dict(marketing).get("placement_labels"))
    for key in sorted(placements, key=lambda k: to_int(k) or 0):
        for label in as_list(placements[key]):
            text = clean(as_dict(label).get("text"))
            if text and text not in seen:
                seen.append(text)
    return seen


def _link_id(link):
    """The id a category link ends in."""
    match = re.search(r"/(\d+)/?(?:\?.*)?$", link or "")
    return match.group(1) if match else None


def _named_links(value, with_id=False):
    """[{name, link}] of a related-links part."""
    rows = []
    for item in as_list(as_dict(value).get("related_links")):
        name, link = clean(as_dict(item).get("name")), as_dict(item).get("link")
        if not name or not link:
            continue
        rows.append({"id": _link_id(link), "name": name, "link": link} if with_id else {"name": name, "link": link})
    return rows


# ---- a product row (search, shop and category listings) ----------------------

def _row_shop(seller):
    seller = as_dict(seller)
    seller_id = clean(seller.get("seller_id"))
    name = clean(seller.get("shop_name"))
    return {
        "id": seller_id,
        "name": name,
        "link": refs.shop_link(seller_id, name),
        "logo": _image(seller.get("shop_logo")),
        "is_verified": bool(seller.get("store_blueV_label")),
    }


def _row_price(price):
    """The price block of a row or of one of its SKUs -> price, original
    price, discount and saving. The original price is given only when the
    product is discounted."""
    price = as_dict(price)
    sale = amount(price.get("sale_price_decimal"))
    original = amount(price.get("origin_price_decimal"))
    if original is None or sale is None or original <= sale:
        original = None
    return {
        "price": sale,
        "original_price": original,
        "discount_percent": _percent(price.get("discount_format") or price.get("discount_decimal")) if original else None,
        "savings": amount(g(price, "promotion_deduction_details", "seller_subtotal_deduction_decimal")) if original else None,
        "currency": clean(price.get("currency_name")),
    }


def parse_video(video):
    """The creator video the site pins to a product row. None without one."""
    video = as_dict(video)
    if not video.get("item_id"):
        return None
    duration = to_int(video.get("duration"))
    return {
        "id": clean(video.get("item_id")),
        "title": clean(video.get("title")),
        "link": video.get("content_url") or None,
        "cover_image": video.get("cover_image_url") or None,
        "duration_seconds": round(duration / 1000, 1) if duration else None,
        "width": to_int(video.get("width")),
        "height": to_int(video.get("height")),
        "play_count": count(to_int(video.get("play_count"))) if video.get("play_count") is not None else None,
        "like_count": count(to_int(video.get("like_count"))) if video.get("like_count") is not None else None,
        "posted_at": epoch_utc(to_int(video.get("upload_time"))),
        "author": {
            "id": clean(video.get("author_id")),
            "name": clean(video.get("author_name")),
            "avatar": video.get("author_avatar_url") or None,
        },
        "disclosure": clean(video.get("bc_ad_label_text")),
    }


def parse_product_row(row):
    """One product of a listing."""
    row = as_dict(row)
    product_id = clean(row.get("product_id"))
    labels = _labels(row.get("product_marketing_info"))
    variants = []
    for sku in as_list(row.get("sku_info")):
        sku_id = clean(as_dict(sku).get("SkuId"))
        if sku_id:
            variants.append({"id": sku_id, **_row_price(as_dict(sku).get("PriceInfo"))})
    return {
        "id": product_id,
        "title": clean(row.get("title")),
        "link": g(row, "seo_url", "canonical_url") or refs.product_link(product_id, g(row, "seo_url", "slug")),
        "image": _image(row.get("image")),
        "transparent_image": _image(row.get("transparent_image")),
        "brand": clean(g(row, "brand_info", "brand_name")),
        **_row_price(row.get("product_price_info")),
        "rating": rating(g(row, "rate_info", "score")),
        "review_count": count(to_int(g(row, "rate_info", "review_count"))) if g(row, "rate_info", "review_count") is not None else None,
        "sold_count": count(to_int(g(row, "sold_info", "sold_count"))) if g(row, "sold_info", "sold_count") is not None else None,
        "is_free_shipping": "Free shipping" in labels,
        "labels": labels,
        "skus": variants,
        "shop": _row_shop(row.get("seller_info")),
        "video": parse_video(row.get("bind_video")),
    }


def _rows(products):
    return [parse_product_row(row) for row in as_list(products) if as_dict(row).get("product_id")]


# ---- shops -------------------------------------------------------------------

def _scores(info):
    """The shop's service scores as the site labels them."""
    rows = []
    for item in as_list(as_dict(info).get("shop_exp_scores")):
        item = as_dict(item)
        name = clean(item.get("score_description"))
        if not name:
            continue
        rows.append({
            "name": name,
            "value": clean(item.get("format_score")),
            "score": amount(item.get("score")),
            "grade": clean(item.get("experience_format_description")),
        })
    return rows


def parse_shop(info):
    """A shop's profile (the shop page's `shopInfo`, a product page's
    `shop_info`, a search page's featured shop). None without a seller id."""
    info = as_dict(info)
    seller_id = clean(info.get("seller_id"))
    if not seller_id:
        return None
    name = clean(info.get("shop_name"))
    label = as_dict(info.get("shop_identity_label"))
    background = as_dict(info.get("background"))

    def number(key):
        return count(to_int(info.get(key))) if info.get(key) is not None else None

    return {
        "id": seller_id,
        "name": name,
        "link": refs.shop_link(seller_id, name),
        "logo": _image(info.get("shop_logo")),
        "cover_image": None if background.get("is_default") else _image(background.get("image")),
        "description": clean(info.get("desc")),
        "creator_name": clean(info.get("creator_name")),
        "creator_id": clean(info.get("official_creator_uid")),
        "region": clean(info.get("region")),
        "badge": clean(label.get("identity_label_text")),
        "is_official": label.get("ShopIdentityLabelKey") == "official",
        "is_brand": bool(g(label, "brand_info", "is_brand")),
        "is_verified": bool(info.get("store_brand_show")),
        "rating": rating(info.get("shop_rating")),
        "review_count": number("review_count"),
        "sold_count": number("sold_count"),
        "product_count": number("on_sell_product_count"),
        "follower_count": number("followers_count"),
        "video_count": number("video_count"),
        "scores": _scores(info),
    }


def _shop_categories(nodes):
    """The shop's own category tree with its product counts."""
    rows = []
    for node in as_list(nodes):
        node = as_dict(node)
        category_id = clean(node.get("category_id"))
        if not category_id:
            continue
        rows.append({
            "id": category_id,
            "name": clean(node.get("name")),
            "level": to_int(node.get("level")),
            "product_count": count(to_int(node.get("product_count"))) if node.get("product_count") is not None else None,
            "subcategories": _shop_categories(node.get("children")),
        })
    return rows


def parse_shop_page(payload):
    """A shop page -> {shop, promotions, categories, products, has_more}.
    `shop` is None when the page carries no shop. A shop read from the
    page's JSON calls (fetch._shop_parts) has no tab: its `promotions` and
    `categories` are None (unknown, not empty), and so are its `products`
    when its product list did not answer."""
    part = component(payload, "shop_info")
    feed = component(payload, "feed_list_store_list_product")
    tab = part.get("shopTab")
    promotions = None
    if isinstance(tab, dict):
        promotions = []
        for item in as_list(tab.get("promotion_filters")):
            name = clean(as_dict(item).get("promotion_name"))
            if name and name not in promotions:
                promotions.append(name)
    has_feed = has_component(payload, "feed_list_store_list_product")
    return {
        "shop": parse_shop(part.get("shopInfo")),
        "promotions": promotions,
        "categories": _shop_categories(tab.get("category_filter_list")) if isinstance(tab, dict) else None,
        "products": _rows(feed.get("products")) if has_feed else None,
        "has_more": bool(feed.get("has_more")),
    }


# ---- search --------------------------------------------------------------------

def _facets(feed):
    """The refinements a result page offers, without the sort menu (the
    site applies them only inside its own page, so they describe the
    result; they are not request params)."""
    rows = []
    for section in as_list(as_dict(feed).get("filter_sections")):
        section = as_dict(section)
        name = clean(section.get("title"))
        if not name or to_int(section.get("filterGroupType")) == 8:        # 8 = "Sort by"
            continue
        groups = {}
        for group in as_list(section.get("optionGroups")):
            for option in as_dict(as_dict(group).get("options")):
                groups[option] = clean(as_dict(group).get("title"))
        options = []
        for option, token in as_dict(section.get("options")).items():
            category_id = token.rsplit("|", 1)[-1] if isinstance(token, str) and "category" in token else None
            options.append({
                "name": clean(option),
                "group": groups.get(option),
                "category_id": category_id if category_id and category_id.isdigit() else None,
                "color": g(section, "optionBackgroundColors", option, "value"),
            })
        rows.append({"name": name, "is_multiple_choice": section.get("type") == "checkbox", "options": options})
    return rows


def parse_search(payload, query, is_partial=False):
    feed = component(payload, "feed_list_search_word")
    featured = component(payload, "recommended_shops")
    featured_shop = parse_shop(featured.get("default_shop_info"))
    if featured_shop:
        featured_shop["products"] = _rows(featured.get("default_shop_products"))
    products = _rows(feed.get("products"))
    return {
        "query": query,
        "link": refs.search_link(query),
        "is_partial": bool(is_partial),
        "count": len(products),
        "has_more": bool(feed.get("has_more")),
        "products": products,
        "shops": [_row_shop(shop) for shop in as_list(feed.get("shops")) if as_dict(shop).get("seller_id")],
        "featured_shop": featured_shop,
        "facets": _facets(feed),
        "related_searches": _named_links(component(payload, "related_link_search_words")),
        "related_categories": _named_links(component(payload, "related_link_categories"), with_id=True),
        "recommended_products": _rows(component(payload, "feed_list_recommended_for_you").get("products")),
    }


# ---- reviews -------------------------------------------------------------------

def parse_review(review, with_product=True):
    """One review. `with_product=False` leaves out the product's id and
    name (a product's own reviews would repeat them on every row)."""
    review = as_dict(review)
    pictures = [link for link in as_list(review.get("review_images")) if isinstance(link, str) and link]
    row = {
        "id": clean(review.get("review_id")),
        "rating": to_int(review.get("review_rating")),
        "text": multiline(review.get("review_text")),
        "created_at": _milliseconds_utc(review.get("review_time")),
        "reviewer_name": clean(review.get("reviewer_name")),
        "reviewer_avatar": review.get("reviewer_avatar_url") or None,
        "country": clean(review.get("review_country")),
        "is_verified_purchase": review.get("is_verified_purchase") if isinstance(review.get("is_verified_purchase"), bool) else None,
        "is_incentivized": review.get("is_incentivized_review") if isinstance(review.get("is_incentivized_review"), bool) else None,
        "images": pictures or ([review["display_image_url"]] if review.get("display_image_url") else []),
        "sku_id": clean(review.get("sku_id")),
        "variant": clean(review.get("sku_specification")),
    }
    if with_product:
        row["product"] = {"id": clean(review.get("product_id")), "name": clean(review.get("product_name")),
                          "link": refs.product_link(clean(review.get("product_id")))}
    return row


def _rating_counts(result):
    """{"1": "5784", ...} -> [{stars: 5, count: 75819}, ...], 5 stars first."""
    result = as_dict(result)
    return [{"stars": stars, "count": count(to_int(result.get(str(stars))))} for stars in (5, 4, 3, 2, 1) if str(stars) in result]


# ---- a product -----------------------------------------------------------------

def _description(blocks):
    """The description's text blocks as plain text (a list item gets a
    dash) and its pictures, in the page's order."""
    lines, pictures = [], []
    for block in as_list(blocks):
        block = as_dict(block)
        picture = _image(block.get("image"))
        if picture:
            pictures.append(picture)
        for text in as_list(block.get("content")):
            text = multiline(text)
            if text:
                lines.append(f"- {text}" if block.get("type") in ("ul", "ol") else text)
    return ("\n".join(lines) or None), pictures


def _options(props):
    rows = []
    for prop in as_list(props):
        prop = as_dict(prop)
        values = []
        for value in as_list(prop.get("sale_prop_values")):
            value = as_dict(value)
            values.append({"id": clean(value.get("prop_value_id")), "value": clean(value.get("prop_value")),
                           "image": _image(value.get("image"))})
        rows.append({"id": clean(prop.get("prop_id")), "name": clean(prop.get("prop_name")), "values": values})
    return rows


def _skus(skus):
    rows = []
    for sku in as_list(skus):
        sku = as_dict(sku)
        price = as_dict(sku.get("price"))
        sale = amount(price.get("sale_price_decimal"))
        original = amount(price.get("origin_price_decimal"))
        if original is None or sale is None or original <= sale:
            original = None
        stock = to_int(sku.get("stock"))
        rows.append({
            "id": clean(sku.get("sku_id")),
            "options": [{"name": clean(as_dict(p).get("prop_name")), "value": clean(as_dict(p).get("prop_value"))}
                        for p in as_list(sku.get("sku_sale_props"))],
            "price": sale,
            "original_price": original,
            "discount_percent": _percent(price.get("discount_format") or price.get("discount_decimal")) if original else None,
            "currency": clean(price.get("currency_name")),
            "stock": count(stock) if stock is not None else None,
            "is_in_stock": (stock > 0) if stock is not None else None,
            "purchase_limit": to_int(sku.get("purchase_limit")),
            "warehouse_id": clean(sku.get("warehouse_id")),
        })
    return rows


def _shipping(product):
    logistic = as_dict(product.get("logistic"))
    if not logistic:
        return None
    tracking = as_dict(logistic.get("event_tracking"))
    notes = [clean(as_dict(item).get("text")) for key in ("description_list", "appendix_list")
             for item in as_list(g(product, "shipping_module", key))]
    return {
        "method": clean(logistic.get("delivery_name")),
        "is_free": logistic.get("free_shipping") if isinstance(logistic.get("free_shipping"), bool) else None,
        "fee": amount(g(logistic, "shipping_fee", "price_val")),
        "original_fee": amount(logistic.get("original_shipping_val")),
        "currency": clean(g(logistic, "shipping_fee", "currency")),
        "is_deliverable": logistic.get("reachable") if isinstance(logistic.get("reachable"), bool) else None,
        "min_days": to_int(logistic.get("delivery_min_days")),
        "max_days": to_int(logistic.get("delivery_max_days")),
        "estimated_delivery": clean(logistic.get("lead_time")),
        "ships_within_days": to_int(tracking.get("ships_days")),
        "ships_from": clean(tracking.get("ship_from")),
        "summary": next((text for text in (clean(as_dict(item).get("text")) for item in as_list(product.get("lock_up_shipping"))) if text), None),
        "notes": [note for note in notes if note],
    }


def _named_values(lines):
    """['Business name: Goli Nutrition Inc.'] -> [{name, value}]."""
    rows = []
    for line in as_list(lines):
        line = clean(line)
        if not line:
            continue
        name, sep, value = line.partition(":")
        rows.append({"name": name.strip(), "value": value.strip()} if sep and value.strip() else {"name": None, "value": line})
    return rows


def _highlights(text):
    """'• one\n• two' -> ['one', 'two']."""
    if not isinstance(text, str):
        return []
    return [line for line in (clean(raw.lstrip("•*- ")) for raw in text.splitlines()) if line]


def _faq(text):
    """'Q:…\nA:…\n\nQ:…' -> [{question, answer}]."""
    rows = []
    for block in re.split(r"\n\s*\n", text) if isinstance(text, str) else []:
        match = re.match(r"\s*Q\s*[:：]\s*(.+?)\s*\n\s*A\s*[:：]\s*(.+)", block, re.S)
        if match:
            rows.append({"question": clean(match.group(1)), "answer": multiline(match.group(2))})
    return rows


def parse_product(payload):
    """A product page -> the product in full, with its shop and the first
    reviews the page shows."""
    part = component(payload, "product_info")
    product = as_dict(part.get("product_info"))
    price = as_dict(product.get("price"))
    reviews = as_dict(part.get("review_info"))
    seo = as_dict(part.get("aigc_info"))
    product_id = clean(product.get("product_id"))
    description, description_images = _description(product.get("desc_blocks"))
    sale = amount(price.get("min_sku_price"))
    original = amount(price.get("min_sku_original_price"))
    if original is None or sale is None or original <= sale:
        original = None
    total_reviews = reviews.get("total_reviews") if reviews.get("total_reviews") is not None else g(product, "review", "review_count")
    stocks = [to_int(as_dict(sku).get("stock")) for sku in as_list(product.get("skus"))]
    stocks = [stock for stock in stocks if stock is not None]
    categories = []
    for node in as_list(part.get("categories")):
        node = as_dict(node)
        categories.append({"id": clean(node.get("category_id")), "name": clean(node.get("category_name")),
                           "level": to_int(node.get("level")),
                           "is_leaf": node.get("is_leaf") if isinstance(node.get("is_leaf"), bool) else None})
    warnings = []
    for item in as_list(product.get("legit_warnings")):
        title, text = clean(as_dict(item).get("short_content")), multiline(as_dict(item).get("long_content"))
        if title or text:
            warnings.append({"title": title, "text": text})
    brand = next((clean(as_dict(spec).get("value")) for spec in as_list(product.get("specifications"))
                  if clean(as_dict(spec).get("name")) == "Brand"), None)
    shop = parse_shop(part.get("shop_info"))
    if shop is None and product.get("seller_id"):           # the page's short seller block, when the shop part is missing
        seller = as_dict(product.get("seller"))
        shop = parse_shop({"seller_id": product.get("seller_id"), "shop_name": seller.get("name"),
                           "shop_logo": seller.get("avatar"), "shop_rating": seller.get("rating"),
                           "on_sell_product_count": seller.get("product_count"), "followers_count": seller.get("follower_count")})
    return {
        "id": product_id,
        "title": clean(product.get("title")),
        "link": g(payload, "route_info", "canonical_url") or refs.product_link(product_id),
        "brand": brand,
        "seo_title": clean(seo.get("aigc_title")),
        "seo_description": clean(seo.get("aigc_description")),
        "keywords": [k for k in (clean(as_dict(item).get("keyword")) for item in as_list(seo.get("aigc_keywords"))) if k],
        "summary": multiline(seo.get("long_text")),
        "highlights": _highlights(seo.get("bullet_points")),
        "faq": _faq(seo.get("faq")),
        "description": description,
        "images": [link for link in (_image(picture) for picture in as_list(product.get("images"))) if link],
        "description_images": description_images,
        "price": sale,
        "original_price": original,
        "discount_percent": _percent(price.get("discount")) if original else None,
        "currency": clean(price.get("currency")),
        "has_price_range": price.get("is_interval_price") if isinstance(price.get("is_interval_price"), bool) else None,
        "is_in_stock": any(stock > 0 for stock in stocks) if stocks else None,
        "sold_count": count(to_int(product.get("sold_count"))) if product.get("sold_count") is not None else None,
        "rating": rating(g(reviews, "review_ratings", "overall_score") or g(product, "review", "product_rating")),
        "review_count": count(to_int(total_reviews)) if total_reviews is not None else None,
        "rating_counts": _rating_counts(g(reviews, "review_ratings", "rating_result")),
        "labels": _labels(part.get("promotion_tag")),
        "sale_ends_at": epoch_utc(to_int(g(product, "waist_banner", "tail", "countdown", "target_time"))),
        "categories": categories,
        "specifications": [{"name": clean(as_dict(spec).get("name")), "value": clean(as_dict(spec).get("value"))}
                           for spec in as_list(product.get("specifications")) if clean(as_dict(spec).get("name"))],
        "options": _options(product.get("sale_props")),
        "default_sku_id": clean(product.get("default_sku_id")),
        "skus": _skus(product.get("skus")),
        "shipping": _shipping(product),
        "warnings": warnings,
        "seller_information": _named_values(g(product, "compliance", "contents")),
        "shop": shop,
        "reviews": [parse_review(review, with_product=False) for review in as_list(reviews.get("product_reviews"))],
        "has_more_reviews": bool(reviews.get("has_more")),
    }


# ---- categories ------------------------------------------------------------------

def parse_category(node):
    """One category record ({category_id, category_name, category_name_en,
    category_level, is_leaf, parent_category_id, image_url}). None without an id."""
    node = as_dict(node)
    category_id = clean(node.get("category_id"))
    if not category_id:
        return None
    parent = clean(node.get("parent_category_id"))
    return {
        "id": category_id,
        "name": clean(node.get("category_name")),
        "link": refs.category_link(category_id, clean(node.get("category_name_en"))),
        "image": node.get("image_url") or None,
        "level": to_int(node.get("category_level")),
        "is_leaf": node.get("is_leaf") if isinstance(node.get("is_leaf"), bool) else None,
        "parent_id": parent if parent and parent != "0" else None,
    }


def parse_category_tree(payload):
    """The storefront's category tree, as every page answer carries it:
    the top categories, each with its children."""
    tree = []
    for node in as_list(as_dict(payload).get("category_hierarchy")):
        top = parse_category(as_dict(node).get("self"))
        if not top:
            continue
        top["subcategories"] = [child for child in (parse_category(as_dict(c).get("self") or c)
                                                    for c in as_list(as_dict(node).get("children"))) if child]
        tree.append(top)
    return tree


def parse_category_page(payload):
    """A category page -> {category, parents, subcategories, products,
    has_more, reviews}. `category` is None for an id the site does not have."""
    part = component(payload, "homepage_products")
    data = as_dict(part.get("categoryProductsData"))
    category = parse_category(part.get("categoryInfo"))
    path = [node for node in (parse_category(segment) for segment in as_list(component(payload, "bread_crumbs").get("segments"))) if node]
    parents = [{"id": node["id"], "name": node["name"], "link": node["link"]}
               for node in path if not category or node["id"] != category["id"]]
    children = [child for child in (parse_category(c) for c in as_list(component(payload, "categories_tab").get("children"))) if child]
    return {
        "category": category,
        "parents": parents,
        "subcategories": children,
        "products": _rows(data.get("productList")),
        "has_more": bool(data.get("hasMore")),
        "reviews": [parse_review(review) for review in as_list(data.get("categoryReviews"))],
    }
