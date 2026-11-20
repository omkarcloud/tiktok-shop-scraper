"""TikTok Shop transport: plain curl_cffi with chrome TLS on the data links
of the US storefront's own pages. No browser, no login, no token, and no
cookie is carried from one call to the next. One session per request
thread on the exit config.TIKTOK_SHOP_EXIT names (the server's own IP in
production); a retryable failure drops the session.

The upstream
------------
shop.tiktok.com is a server-rendered app, and each of its pages has a data
link that answers the JSON the page is built from instead of the HTML
(about 2.5 times smaller):

    GET https://shop.tiktok.com/us/<page path>?__loader=<the page's route id>

    /us/pdp/<product id>               a product: record, SKUs with stock, shipping,
                                       shop, rating breakdown, its first 5 reviews.
                                       Redirects to /us/pdp/<slug>/<id>.
    /us/s?q=<text>                     a search: up to 30 products, matching shops,
                                       facets, related searches and categories
    /us/store/<slug>/<seller id>       a shop: profile, its 20 best sellers
    /us/c/<slug>/<category id>         a category: its record, its children, 10 to
                                       15 products (a different sample on every
                                       call) and 10 recent reviews

Every answer also carries `category_hierarchy`, the storefront's category
tree. The slug in a link is decoration (`x` answers the same record).

The JSON calls a page makes after it has loaded (/api/shop/...: more
reviews, a next page, a sort, a filter, suggestions) are NOT used: without
the token the page's own script adds they answer {"code": 10000} (a
captcha is due) or {"code": 100000} on every exit (2026-11-20, 0 of 26
review calls passed), so nothing here pages, sorts or filters. Two calls
of the store page are the exception, because they answer without that
token: store_info (the shop's record) and product_list (the products the
page opens with). They read a shop whose page will not open (fetch_shop).

How the site refuses, always with HTTP 200
------------------------------------------
  * the "Security Check" page, an HTML page with a captcha, where JSON was
    asked for                                         -> TikTokShopBlocked
  * another HTML page (TikTok's own home page, when the exit is not in
    the US)                                           -> TikTokShopBlocked
  * a search answered with a FALLBACK list: 5 rows, no facets, no token
    for a next page. About 6 answers in 10 are this one, on every exit and
    on one session alike (pod probe 2026-11-20: 4 or 5 of 9 on the server's
    own IP). It is a verdict per request, so a search is asked up to
    config.TIKTOK_SHOP_SEARCH_TRIES times and the first full answer wins;
    when none comes, the fallback rows are returned and flagged partial.
A storefront answers only its own country: the US search is HTTP 404 from
a British address. A 404 is therefore an exit's fault, and retryable.

Not found is ambiguous on this site, so it is confirmed
-------------------------------------------------------
  * a product that does not exist answers one of three things, at random:
    error_code 23002102, error_code 23004014 ("crawler traffic detected by
    anti-crawler team", with `waf_type` 3) or a bare
    {"message": "The product is not currently available in your country or
    region."}. 23004014 reads like a block, but it came for unknown ids
    only and never for a product that exists (25+ tries). A product is
    reported missing when config.TIKTOK_SHOP_NOT_FOUND_TRIES answers in a
    row, each on a fresh session, are one of the three.
  * a shop's page proves nothing either way. TikTok Shop answers its
    Security Check, on every exit, for a seller id that does not exist AND
    for some real shops (4 shops a "dog toys" search showed: 1 page in 180
    tries, gateway, datacenter and US residential, 2026-11-20). The store
    page's own store_info call tells them apart: it answers a real shop's
    record (the gated shops included, 11 of 12 tries; refused with
    {"code": 100000} otherwise) and {"code": 0} WITHOUT a record for an
    unknown seller id (5 of 6). So a shop whose page will not open is read
    from store_info and product_list, reported missing after
    config.TIKTOK_SHOP_NOT_FOUND_TRIES record-less answers, and
    unavailable (503 with Retry-After) when neither answer came.
  * a category id that does not exist answers a normal page whose
    `categoryInfo` is null. So did a category that exists, once in about
    50 answers (the build's smoke run, 2026-11-20), so this one is
    confirmed the same way: the same number of such pages in a row.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  TikTokShopUpstreamError  transport failure / 5xx / 404 / unexpected body   retryable
  TikTokShopBlocked        the Security Check page, another HTML page,
                           403 / 429, a JSON call's refusal                  retryable
  TikTokShopUnavailable    a shop neither its page nor its JSON calls
                           answered for: 503 + Retry-After                   retry in minutes
  TikTokShopNotFound       unknown product / shop / category                 never retried
"""
import threading

import fastjson

import config
import egress
from scraper_errors import Blocked, NotFound, Unavailable, UpstreamError
from scraper_utils import retry, sessions
from scraper_utils.pages import page_title
from scraper_utils.values import as_dict, as_list, to_int
from tiktok_shop import parsers, refs
from tiktok_shop.refs import STOREFRONT

IMPERSONATE = "chrome"
TIMEOUT = 25            # the largest answer (a 4 MB search) took 2.1 s from the pod

# The page's route ids, as its own router names them in `?__loader=`.
ROUTE_PRODUCT = "(region)/pdp/(product_name_slug$)/(product_id)/page"
ROUTE_SEARCH = "(region)/(route_page_name)/page"
ROUTE_SHOP = "(region)/store/(route_keyword)/(route_keyword_2)/page"
ROUTE_CATEGORY = "(region)/c/(category_name)/(category_id)/page"

# What Chrome sends for a page of this site (samples/pages/*.request.json
# of the research, 2026-11-20). The session adds its own user-agent, client
# hints, accept-encoding and the accept-language of its exit.
PAGE_HEADERS = {
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,image/jxl,image/avif,image/webp,"
               "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"),
    "priority": "u=0, i",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}

VERIFICATION_TITLE = "Security Check"

# A shop's page is asked this many times, each on a fresh session, before
# the shop is read from the store page's own JSON calls: a page that
# answers does so at once, and a guarded one answered 1 time in 180
# (2026-11-20), so a third try buys nothing.
PAGE_TRIES = 2

# The store page's own JSON calls that answer without the page's token
# (research samples/calls/p10-*; measured from the pod 2026-11-20 16:33 UTC,
# `make_new_scraper.py --exits`: both pass on direct, gateway and
# datacenter). store_info is the call the search page's shop cards make.
STORE_INFO = "/api/shop/brandy_desktop/s/store_info"
STORE_PRODUCTS = "/api/shop/brandy_desktop/store/product_list"
# what the store page sends for its product feed's first page: the products
# the page opens with, in the page's own order (best sellers first)
STORE_FEED = {
    "component_type": "feed_list",
    "component_name": "feed_list_store_list_product",
    "fe_config": {"is_main_feed": True, "is_fmp_significant": True, "show_structure_data": True, "show_empty_page": True,
                  "empty_text": {"title": "No results found", "sub_title": "Try another search"},
                  "data_source": {"type": "store_list_product", "params": {"count": 20, "clamp": False}}},
}
STORE_FEED_SORT = {"sort_field": 4, "sort_order": 1}
# What Chrome sends with the page's JSON calls (samples/calls/p10-04.request.json
# of the research); the session adds its user-agent, client hints,
# accept-encoding and the accept-language of its exit.
CALL_HEADERS = {
    "accept": "application/json,*/*;q=0.8",
    "content-type": "application/json",
    "origin": refs.SITE,
    "priority": "u=1, i",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}


class TikTokShopUpstreamError(UpstreamError):
    """Transport failure, 5xx, a 404 or an unexpected payload — retryable."""


class TikTokShopBlocked(TikTokShopUpstreamError, Blocked):
    """The Security Check page, another HTML page, 403 / 429, a JSON call's refusal — retryable."""


class TikTokShopVerification(TikTokShopBlocked):
    """The Security Check page itself (also what an unknown shop answers)."""


class TikTokShopUnavailable(TikTokShopUpstreamError, Unavailable):
    """Nothing answered either way for a shop (its page, its record, its
    products): the routes answer 503 with Retry-After, never 404."""


class TikTokShopNotFound(NotFound):
    """No such product, shop or category — never retried."""


# ---- sessions ------------------------------------------------------------------------

# One curl session per request thread (a curl handle must not be shared
# across threads). It carries nothing: the cookies an answer sets (ttwid,
# dkms-token) are forgotten after every call, so each call is a new visitor,
# which is how every rate in this module was measured.
_local = threading.local()


def _session():
    return sessions.thread_session(
        _local, lambda: egress.exit_session(config.TIKTOK_SHOP_EXIT, impersonate=IMPERSONATE))


def _drop_session():
    """Close the thread's session so the retry rides a fresh connection / exit."""
    sessions.drop(_local)


def _forget_cookies(session):
    try:
        session.cookies.clear()
    except Exception:
        pass


def _retrying(fn):
    """fn() under the shared retry policy: only TikTokShopUpstreamError
    (Blocked included) is retried; NotFound surfaces at once."""
    return retry.run(fn, config, TikTokShopUpstreamError, lambda e: _drop_session())


# ---- one request ---------------------------------------------------------------------

def _read(status, text, label):
    """An answer -> the decoded page data (or the bare {"message": ...}
    answer of an unavailable product, which the caller recognises)."""
    if status in (403, 429):
        raise TikTokShopBlocked(f"HTTP {status} for {label}")
    if status != 200:
        raise TikTokShopUpstreamError(f"HTTP {status} for {label}")
    if text[:1] != "{":
        title = page_title(text)
        if VERIFICATION_TITLE in title:
            raise TikTokShopVerification(f"the Security Check page for {label}")
        raise TikTokShopBlocked(f"a page instead of data for {label}: {title[:80]!r}")
    try:
        payload = fastjson.loads(text)
    except Exception:
        raise TikTokShopUpstreamError(f"unreadable JSON for {label}: {text[:120]!r}")
    if parsers.is_page(payload) or parsers.is_unavailable(payload):
        return payload
    raise TikTokShopUpstreamError(f"unexpected payload for {label}: {text[:120]!r}")


def _load(path, route, label, params=None):
    """One GET of a page's data link. No retry here."""
    session = _session()
    try:
        resp = session.get(STOREFRONT + path, params={**(params or {}), "__loader": route},
                           headers=PAGE_HEADERS, timeout=TIMEOUT)
    except Exception as e:
        raise TikTokShopUpstreamError(f"request failed for {label}: {type(e).__name__}: {e}")
    finally:
        _forget_cookies(session)
    return _read(resp.status_code, resp.text, label)


def _read_call(status, text, label):
    """A page's JSON call answer -> its `data` ({} when the call answered
    success with nothing: store_info's answer for an unknown seller id).
    Any other code is a refusal: {"code": 100000}, or 10000 (a captcha is
    due)."""
    if status in (403, 429):
        raise TikTokShopBlocked(f"HTTP {status} for {label}")
    if status != 200:
        raise TikTokShopUpstreamError(f"HTTP {status} for {label}")
    if text[:1] != "{":
        title = page_title(text)
        if VERIFICATION_TITLE in title:
            raise TikTokShopVerification(f"the Security Check page for {label}")
        raise TikTokShopBlocked(f"a page instead of data for {label}: {title[:80]!r}")
    try:
        payload = fastjson.loads(text)
    except Exception:
        raise TikTokShopUpstreamError(f"unreadable JSON for {label}: {text[:120]!r}")
    if not isinstance(payload, dict) or payload.get("code") != 0:
        raise TikTokShopBlocked(f"{label} refused: {text[:80]!r}")
    return as_dict(payload.get("data"))


def _post(path, body, label, referer):
    """One POST of a page's JSON call, sent as the page sends it. No retry here."""
    session = _session()
    try:
        resp = session.post(refs.SITE + path, data=fastjson.dumps(body), headers={**CALL_HEADERS, "referer": referer},
                            timeout=TIMEOUT)
    except Exception as e:
        raise TikTokShopUpstreamError(f"request failed for {label}: {type(e).__name__}: {e}")
    finally:
        _forget_cookies(session)
    return _read_call(resp.status_code, resp.text, label)


# ---- the pages -----------------------------------------------------------------------

def _product_page(product_id, label):
    payload = _load(f"/pdp/{product_id}", ROUTE_PRODUCT, label)
    if parsers.is_unavailable(payload):
        return payload, "unavailable"
    error = parsers.product_error(payload)
    if error in parsers.PRODUCT_NOT_FOUND_CODES:
        return payload, f"error {error}"
    if error:
        raise TikTokShopUpstreamError(f"{label} answered error {error}")
    if not parsers.component(payload, "product_info").get("product_info"):
        raise TikTokShopUpstreamError(f"{label} answered a page without a product")
    return payload, None


def fetch_product(product_id):
    """A product page's data. An id the site answers as missing
    config.TIKTOK_SHOP_NOT_FOUND_TRIES times in a row -> TikTokShopNotFound."""
    label = f"product {product_id}"
    for _ in range(config.TIKTOK_SHOP_NOT_FOUND_TRIES):
        payload, missing = _retrying(lambda: _product_page(product_id, label))
        if not missing:
            return payload
        _drop_session()                 # the next answer comes on a fresh session
    raise TikTokShopNotFound(f"{label} not found")


def fetch_search(query):
    """A search page's data -> (payload, is_partial). Asked up to
    config.TIKTOK_SHOP_SEARCH_TRIES times: the first full answer is
    returned; when only fallback answers came, the last of them, flagged
    partial; when nothing answered at all, the last failure is raised."""
    label = f"search {query!r}"
    fallback, failure = None, None
    for _ in range(config.TIKTOK_SHOP_SEARCH_TRIES):
        try:
            payload = _load("/s", ROUTE_SEARCH, label, params={"q": query})
        except TikTokShopUpstreamError as e:
            failure = e
            _drop_session()
            continue
        if parsers.is_unavailable(payload):
            failure = TikTokShopUpstreamError(f"unexpected payload for {label}")
            continue
        if parsers.search_is_full(payload):
            return payload, False
        fallback = payload
    if fallback is not None:
        return fallback, True
    raise failure


def _shop_record(payload):
    """The shop record of a shop page (falsy when the page has none)."""
    return parsers.is_page(payload) and parsers.component(payload, "shop_info").get("shopInfo")


def _shop_card(seller_id, label):
    """The shop's record from store_info: the same fields as the shop
    page's `shopInfo`. It answers for a shop whose page is guarded, and
    answers success WITHOUT a record for a seller id that has no shop.
    -> the record; TikTokShopNotFound after config.TIKTOK_SHOP_NOT_FOUND_TRIES
    record-less answers, each on a fresh session (a refusal between them
    neither counts nor starts the count again); TikTokShopUnavailable after
    config.MAX_RETRIES refusals."""
    missing = refused = 0
    failure = None
    while missing < config.TIKTOK_SHOP_NOT_FOUND_TRIES and refused < config.MAX_RETRIES:
        try:
            data = _post(STORE_INFO, {"seller_id": seller_id, "component_name": "recommended_shops"},
                         f"{label}'s record", refs.shop_link(seller_id))
        except TikTokShopUpstreamError as e:
            refused, failure = refused + 1, e
        else:
            if not data:
                missing += 1
            elif str(data.get("seller_id") or "") == seller_id:
                return data
            else:
                refused, failure = refused + 1, TikTokShopUpstreamError(f"{label}'s record names seller {data.get('seller_id')}")
        _drop_session()
    if missing >= config.TIKTOK_SHOP_NOT_FOUND_TRIES:
        raise TikTokShopNotFound(f"{label} not found")
    raise TikTokShopUnavailable(f"TikTok Shop answered neither {label}'s page nor its record ({failure}); "
                                "try again in a few minutes")


def _shop_products(seller_id, label, listed):
    """The products the shop's page opens with, from product_list (the
    page's own feed call): {"products": [...], "has_more": bool}, or None
    when no answer came. An empty list from a shop that lists products
    (`listed`) is asked again on a fresh session: the call answered a real
    shop an empty list 2 times in 6 (2026-11-20)."""
    body = {"component_info": fastjson.dumps(STORE_FEED),
            "load_more_params": fastjson.dumps({"sort_param": STORE_FEED_SORT, "offset": 0, "seller_id": seller_id})}
    for _ in range(config.MAX_RETRIES):
        try:
            data = _post(STORE_PRODUCTS, body, f"{label}'s products", refs.shop_link(seller_id))
        except TikTokShopUpstreamError:
            _drop_session()
            continue
        products = as_list(data.get("products"))
        if products or not listed:
            return {"products": products, "has_more": bool(data.get("has_more"))}
        _drop_session()
    return None


def _shop_parts(record, feed):
    """A shop page's data rebuilt from its JSON calls: the shop's record
    and, when product_list answered, its products, as the parts the page
    is built from. The page's tab (promotions, the shop's categories) has
    no call that answers from the pod (page_data, refused on every exit,
    2026-11-20), so that part is left out: parsers.parse_shop_page then
    reports the promotions and categories unknown (None), as it does the
    products when `feed` is None."""
    parts = [{"component_name": "shop_info", "component_data": {"shopInfo": record}}]
    if feed is not None:
        parts.append({"component_name": "feed_list_store_list_product", "component_data": feed})
    return {"basic_info": {}, "page_config": {"components_map": parts}}


def fetch_shop(seller_id):
    """A shop's page data. The page is asked PAGE_TRIES times; when it
    will not open (TikTok Shop's Security Check, which some real shops'
    pages get on every exit, a 404, a page without a shop), the shop is
    read from the page's own JSON calls (_shop_card, _shop_products) and
    returned in the page's shape without its tab (_shop_parts).
    TikTokShopNotFound when store_info says there is no such shop,
    TikTokShopUnavailable when neither the page nor store_info answered."""
    label = f"shop {seller_id}"
    for _ in range(PAGE_TRIES):
        try:
            payload = _load(f"/store/shop/{seller_id}", ROUTE_SHOP, label)
        except TikTokShopUpstreamError:
            pass
        else:
            if _shop_record(payload):
                return payload
        _drop_session()
    record = _shop_card(seller_id, label)
    listed = to_int(record.get("on_sell_product_count")) or 0
    return _shop_parts(record, _shop_products(seller_id, label, listed > 0))


def _category_page(category_id, label):
    def once():
        payload = _load(f"/c/category/{category_id}", ROUTE_CATEGORY, label)
        if not parsers.is_page(payload):
            raise TikTokShopUpstreamError(f"unexpected payload for {label}")
        return payload
    return _retrying(once)


def fetch_category(category_id):
    """A category page's data. A page without the category's record
    config.TIKTOK_SHOP_NOT_FOUND_TRIES times in a row, each on a fresh
    session -> TikTokShopNotFound."""
    label = f"category {category_id}"
    for _ in range(config.TIKTOK_SHOP_NOT_FOUND_TRIES):
        payload = _category_page(category_id, label)
        if parsers.component(payload, "homepage_products").get("categoryInfo"):
            return payload
        _drop_session()                 # the next answer comes on a fresh session
    raise TikTokShopNotFound(f"{label} not found")


def fetch_category_tree():
    """A page answer that carries the storefront's category tree (every
    one does, the page of an unknown category included)."""
    payload = _category_page(config.TIKTOK_SHOP_CATEGORY_TREE_PAGE, "the category tree")
    if not payload.get("category_hierarchy"):
        raise TikTokShopUpstreamError("the category page answered without the category tree")
    return payload
