"""Reference resolvers and link builders for /tiktok-shop/*.

ONE param per input: `product` accepts a product id OR any TikTok Shop
product link; `shop` a seller id OR a store link; `category` a category id
OR a category link. Resolvers raise ValueError with a user-facing message
(RefField turns it into a 400).

Identifier shapes (shop.tiktok.com, 2026-11-20):
  * product   a 19-digit number (1729527313880355335), the last segment of
              a product link. The site writes product links four ways and
              every one leads to the same page:
                shop.tiktok.com/us/pdp/<slug>/<id>     (the canonical link)
                shop.tiktok.com/us/pdp/<id>            (redirects to it)
                www.tiktok.com/shop/pdp/<slug>/<id>
                shop.tiktok.com/view/product/<id>      (the app's share link)
  * shop      the seller id, a 19-digit number (7495794203056835079), the
              last segment of a store link
              (shop.tiktok.com/us/store/<slug>/<seller id>).
  * category  a 6 or 7 digit number (601450), the last segment of a
              category link (shop.tiktok.com/us/c/<slug>/<id>).
  The slug in a link is decoration: the site answers the same record for
  any slug (measured with `x`), so only the id is kept.

Only the US storefront is served. A storefront answers only a visitor from
its own country (the US search answers 404 to a British address, and the
Singapore one a verification page to an American one), so a link that
names another country's storefront (shop.tiktok.com/gb/..., a
shop-<country>.tiktok.com host, a share link's ?region=GB) is refused with
a message instead of being looked up in the wrong catalog.
"""
import re
from urllib.parse import parse_qs, quote, unquote, urlparse

SITE = "https://shop.tiktok.com"
REGION = "us"
STOREFRONT = f"{SITE}/{REGION}"

# hosts that carry the US storefront's links
HOSTS = ("shop.tiktok.com", "www.tiktok.com", "tiktok.com", "m.tiktok.com", "www.tiktokshop.com", "tiktokshop.com")
# another country's storefront has a host of its own
_OTHER_STOREFRONT_HOST_RE = re.compile(r"^shop-[a-z]{2}\.(tiktok\.com|tiktokw\.eu|tokopedia\.com)$")

PRODUCT_ID_RE = re.compile(r"^[0-9]{12,22}$")
SELLER_ID_RE = re.compile(r"^[0-9]{12,22}$")
CATEGORY_ID_RE = re.compile(r"^[0-9]{4,10}$")
_REGION_RE = re.compile(r"^[a-z]{2}$")

_US_ONLY = "Only the US storefront of TikTok Shop is served."
_PRODUCT_HELP = ("Must be a TikTok Shop product id (1729527313880355335) or a product link "
                 "(https://shop.tiktok.com/us/pdp/<name>/1729527313880355335).")
_SHOP_HELP = ("Must be a TikTok Shop seller id (7495794203056835079) or a store link "
              "(https://shop.tiktok.com/us/store/<name>/7495794203056835079).")
_CATEGORY_HELP = ("Must be a TikTok Shop category id (601450) or a category link "
                  "(https://shop.tiktok.com/us/c/<name>/601450).")


def _link_segments(value, help_text):
    """The path segments of a TikTok Shop link, with the `shop` prefix of a
    www.tiktok.com link and the storefront's country dropped. None when the
    value is not a link at all. A link of another site, or of another
    country's storefront, raises ValueError."""
    if not re.match(r"^(https?:)?//|^[a-z0-9.-]*tiktok(shop)?\.com/|^[a-z0-9.-]*(tiktokw\.eu|tokopedia\.com)/", value, re.I):
        return None
    url = value
    if url.startswith("//"):
        url = "https:" + url
    elif not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if _OTHER_STOREFRONT_HOST_RE.match(host):
        raise ValueError(_US_ONLY)
    if host not in HOSTS:
        raise ValueError(help_text)
    segments = [s for s in unquote(parsed.path or "").split("/") if s]
    if segments and segments[0] == "shop":          # www.tiktok.com/shop/pdp/...
        segments = segments[1:]
    if segments and _REGION_RE.match(segments[0]):  # the page names are one letter (c, s, k) or longer (pdp, store)
        if segments[0] != REGION:
            raise ValueError(_US_ONLY)
        segments = segments[1:]
    else:                                           # the app's share link names its storefront in the query: /view/product/<id>?region=GB
        named = parse_qs(parsed.query).get("region")
        if named and named[-1].strip().lower() != REGION:
            raise ValueError(_US_ONLY)
    return segments


def _resolve(value, id_re, help_text, id_after):
    """A bare id, or the id a link carries: `id_after(segments)` reads it
    from the link's path segments (None when the link is of another kind)."""
    value = (value or "").strip()
    segments = _link_segments(value, help_text)
    if segments is None:
        if id_re.match(value):
            return value
        raise ValueError(help_text)
    found = id_after(segments)
    if found and id_re.match(found):
        return found
    raise ValueError(help_text)


def _product_id(segments):
    if len(segments) in (2, 3) and segments[0] == "pdp":
        return segments[-1]
    if len(segments) == 3 and segments[:2] == ["view", "product"]:
        return segments[2]
    return None


def _shop_id(segments):
    return segments[-1] if len(segments) in (2, 3) and segments[0] == "store" else None


def _category_id(segments):
    return segments[-1] if len(segments) in (2, 3) and segments[0] == "c" else None


def resolve_product(value):
    """Product id or product link -> the product id."""
    return _resolve(value, PRODUCT_ID_RE, _PRODUCT_HELP, _product_id)


def resolve_shop(value):
    """Seller id or store link -> the seller id."""
    return _resolve(value, SELLER_ID_RE, _SHOP_HELP, _shop_id)


def resolve_category(value):
    """Category id or category link -> the category id."""
    return _resolve(value, CATEGORY_ID_RE, _CATEGORY_HELP, _category_id)


# ---- links -------------------------------------------------------------------

def slug(text):
    """'Goli Nutrition' -> 'goli-nutrition', the way the site writes the
    name part of a link. None when nothing readable is left."""
    if not isinstance(text, str):
        return None
    made = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return made or None


def product_link(product_id, name_slug=None):
    """The canonical product link; without a slug, the short link the site
    redirects to it."""
    if not product_id:
        return None
    middle = f"{quote(name_slug, safe='-')}/" if name_slug else ""
    return f"{STOREFRONT}/pdp/{middle}{product_id}"


def shop_link(seller_id, name=None):
    """A store link, written the way the site writes it: the shop's name as
    a slug, then the seller id (the site reads only the id)."""
    if not seller_id:
        return None
    return f"{STOREFRONT}/store/{slug(name) or 'shop'}/{seller_id}"


def category_link(category_id, name_slug=None):
    if not category_id:
        return None
    return f"{STOREFRONT}/c/{quote(name_slug, safe='-') if name_slug else 'category'}/{category_id}"


def search_link(query):
    return f"{STOREFRONT}/s?q={quote(query, safe='')}" if query else None
