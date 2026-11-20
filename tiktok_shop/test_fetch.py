"""Offline tests for tiktok_shop/fetch.py: the request it sends, how it
reads the site's refusals (all of them HTTP 200), the search retry, how a
missing product or shop is told from a block, and how a shop whose page is
guarded is read from the page's own JSON calls. Nothing here touches the
network (the session is a stand-in).

    python -m pytest tiktok_shop/test_fetch.py -q
"""
import gzip
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from scraper_errors import Blocked, NotFound, Unavailable, UpstreamError  # noqa: E402
from tiktok_shop import fetch, parsers  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
GOLI, GOLI_SHOP = "1729527313880355335", "7495794203056835079"
GUARDED_SHOP = "7494894286294844644"           # AllWELL MARKET: its page answers the Security Check on every exit


def raw(name):
    path = os.path.join(FIXTURES, name)
    if name.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return f.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


PRODUCT, PRODUCT_MISSING, PRODUCT_UNAVAILABLE = (raw("product_1729527313880355335.json.gz"), raw("product_not_found.json.gz"),
                                                 raw("product_unavailable.json"))
SEARCH, SEARCH_FALLBACK = raw("search_dog_toys.json.gz"), raw("search_fallback.json.gz")
SHOP, CATEGORY, CATEGORY_MISSING = (raw("shop_7495794203056835079.json.gz"), raw("category_601450.json.gz"),
                                    raw("category_not_found.json.gz"))
VERIFICATION = raw("verification_page.html")
# the store page's own JSON calls, for the guarded shop and for a seller id without a shop
RECORD, NO_RECORD = raw("store_info_7494894286294844644.json"), raw("store_info_no_shop.json")
PRODUCTS, NO_PRODUCTS = raw("store_products_7494894286294844644.json.gz"), raw("store_products_empty.json")
REFUSED = '{"code":100000}'
PAGE_WITHOUT_A_SHOP = raw("shop_without_a_shop.json.gz")
HOME_PAGE = "<html><head><title>TikTok - Make Your Day</title></head><body></body></html>"
SHOP_WITHOUT_A_SHOP = '{"basic_info": {"risk_level": "medium"}, "page_config": {"components_map": [{"component_name": "shop_info", "component_data": {}}]}}'


class Response:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status


class Cookies:
    def __init__(self):
        self.cleared = 0

    def clear(self):
        self.cleared += 1


class Session:
    def __init__(self, wire):
        self.wire, self.cookies, self.closed = wire, Cookies(), False

    def get(self, url, params=None, headers=None, timeout=None):
        return self._answer({"method": "GET", "url": url, "params": params, "headers": headers, "timeout": timeout})

    def post(self, url, data=None, headers=None, timeout=None, params=None):
        return self._answer({"method": "POST", "url": url, "params": params, "data": data, "headers": headers, "timeout": timeout})

    def _answer(self, request):
        self.wire.sent.append({**request, "session": self})
        answer = self.wire.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, Response) else Response(answer)

    def close(self):
        self.closed = True


class Wire:
    """Stand-in for the exits: every session answers from one queue."""

    def __init__(self):
        self.answers, self.sent, self.sessions, self.exits = [], [], [], []

    def build(self, exit=None, impersonate="chrome", **kw):
        self.exits.append((exit, impersonate))
        self.sessions.append(Session(self))
        return self.sessions[-1]


@pytest.fixture
def wire(monkeypatch):
    wire = Wire()
    monkeypatch.setattr(config, "RETRY_BACKOFF", 0)
    monkeypatch.setattr(fetch.egress, "exit_session", wire.build)
    fetch._drop_session()
    yield wire
    fetch._drop_session()


# ---- the request ---------------------------------------------------------------

def test_a_product_call_goes_out_as_the_pages_data_link(wire):
    wire.answers = [PRODUCT]
    payload = fetch.fetch_product(GOLI)
    assert payload["route_info"]["route_product_id"] == GOLI
    sent = wire.sent[0]
    assert sent["url"] == f"https://shop.tiktok.com/us/pdp/{GOLI}"
    assert sent["params"] == {"__loader": "(region)/pdp/(product_name_slug$)/(product_id)/page"}
    assert sent["headers"] == fetch.PAGE_HEADERS and sent["timeout"] == fetch.TIMEOUT
    assert sent["headers"]["sec-fetch-dest"] == "document" and sent["headers"]["upgrade-insecure-requests"] == "1"
    # the session's own headers stay the session's: nothing here names a browser or a language
    assert not {"user-agent", "accept-language", "accept-encoding", "cookie"} & set(sent["headers"])
    assert not any(name.startswith("sec-ch-ua") for name in sent["headers"])
    assert wire.exits == [(config.TIKTOK_SHOP_EXIT, "chrome")]


def test_every_call_forgets_the_cookies_it_was_given(wire):
    wire.answers = [PRODUCT, CATEGORY]
    fetch.fetch_product(GOLI)
    fetch.fetch_category("601450")
    assert len(wire.sessions) == 1 and wire.sessions[0].cookies.cleared == 2      # one thread session, a new visitor per call


def test_the_other_pages_links(wire):
    wire.answers = [SEARCH, SHOP, CATEGORY]
    fetch.fetch_search("dog toys")
    fetch.fetch_shop(GOLI_SHOP)
    fetch.fetch_category("601450")
    search, shop, category = wire.sent
    assert search["url"] == "https://shop.tiktok.com/us/s"
    assert search["params"] == {"q": "dog toys", "__loader": "(region)/(route_page_name)/page"}
    assert shop["url"] == f"https://shop.tiktok.com/us/store/shop/{GOLI_SHOP}"
    assert shop["params"] == {"__loader": "(region)/store/(route_keyword)/(route_keyword_2)/page"}
    assert category["url"] == "https://shop.tiktok.com/us/c/category/601450"
    assert category["params"] == {"__loader": "(region)/c/(category_name)/(category_id)/page"}


# ---- reading an answer -----------------------------------------------------------

def test_read_tells_the_refusals_apart():
    assert fetch._read(200, PRODUCT, "x")["basic_info"]
    assert fetch._read(200, PRODUCT_UNAVAILABLE, "x")["message"].startswith("The product is not currently available")
    with pytest.raises(fetch.TikTokShopVerification, match="Security Check"):
        fetch._read(200, VERIFICATION, "shop 1")
    with pytest.raises(fetch.TikTokShopBlocked, match="TikTok - Make Your Day"):
        fetch._read(200, HOME_PAGE, "search")
    for status in (403, 429):
        with pytest.raises(fetch.TikTokShopBlocked):
            fetch._read(status, "", "x")
    for status in (404, 500, 502):
        with pytest.raises(fetch.TikTokShopUpstreamError) as failure:
            fetch._read(status, "<html>404 Not Found</html>", "x")
        assert not isinstance(failure.value, Blocked)
    with pytest.raises(fetch.TikTokShopUpstreamError):
        fetch._read(200, '{"code": 100000}', "x")            # the JSON calls' refusal is not a page
    with pytest.raises(fetch.TikTokShopUpstreamError):
        fetch._read(200, "{not json", "x")


def test_error_classes_map_to_the_shared_taxonomy():
    assert issubclass(fetch.TikTokShopBlocked, Blocked) and issubclass(fetch.TikTokShopBlocked, fetch.TikTokShopUpstreamError)
    assert issubclass(fetch.TikTokShopVerification, fetch.TikTokShopBlocked)
    assert issubclass(fetch.TikTokShopUpstreamError, UpstreamError) and issubclass(fetch.TikTokShopNotFound, NotFound)
    # route_glue answers Unavailable with 503 + Retry-After, before it looks for an UpstreamError (502)
    assert issubclass(fetch.TikTokShopUnavailable, Unavailable) and fetch.TikTokShopUnavailable.retry_after > 0
    assert not issubclass(fetch.TikTokShopUnavailable, NotFound)


def test_read_call_tells_a_record_from_no_record_and_from_a_refusal():
    assert fetch._read_call(200, RECORD, "x")["shop_name"] == "AllWELL MARKET"
    assert fetch._read_call(200, NO_RECORD, "x") == {}                             # success without a record
    for refusal in (REFUSED, '{"code":10000}', '{"code":0.5}', "[]"):
        with pytest.raises(fetch.TikTokShopBlocked):
            fetch._read_call(200, refusal, "x")
    with pytest.raises(fetch.TikTokShopVerification):
        fetch._read_call(200, VERIFICATION, "x")
    with pytest.raises(fetch.TikTokShopBlocked):
        fetch._read_call(403, "", "x")
    with pytest.raises(fetch.TikTokShopUpstreamError) as failure:
        fetch._read_call(500, "", "x")
    assert not isinstance(failure.value, Blocked)


# ---- retries ---------------------------------------------------------------------

def test_a_block_is_retried_on_a_fresh_session(wire):
    wire.answers = [VERIFICATION, RuntimeError("connection reset"), CATEGORY]
    assert fetch.fetch_category("601450")["basic_info"]
    assert len(wire.sent) == 3 and len(wire.sessions) == 3
    assert wire.sessions[0].closed and wire.sessions[1].closed and not wire.sessions[2].closed


def test_a_block_on_every_try_surfaces_as_blocked(wire):
    wire.answers = [VERIFICATION] * config.MAX_RETRIES
    with pytest.raises(fetch.TikTokShopBlocked):
        fetch.fetch_category("601450")
    assert len(wire.sent) == config.MAX_RETRIES


# ---- a missing category ----------------------------------------------------------

def test_a_category_without_its_record_three_times_is_not_found(wire):
    wire.answers = [CATEGORY_MISSING] * 3
    with pytest.raises(fetch.TikTokShopNotFound, match="category 999999999 not found"):
        fetch.fetch_category("999999999")
    assert len(wire.sent) == config.TIKTOK_SHOP_NOT_FOUND_TRIES and len(wire.sessions) == 3


def test_a_category_that_answers_after_an_empty_page_is_returned(wire):
    """The site gave a category that exists an empty page once in about 50 answers."""
    wire.answers = [CATEGORY_MISSING, VERIFICATION, CATEGORY]
    payload = fetch.fetch_category("601450")
    assert fetch.parsers.component(payload, "homepage_products")["categoryInfo"]["category_id"] == "601450"
    assert len(wire.sent) == 3


def test_the_category_tree_comes_with_any_page(wire):
    wire.answers = [CATEGORY_MISSING]
    assert len(fetch.fetch_category_tree()["category_hierarchy"]) == 28 and len(wire.sent) == 1
    assert wire.sent[0]["url"] == f"https://shop.tiktok.com/us/c/category/{config.TIKTOK_SHOP_CATEGORY_TREE_PAGE}"
    wire.answers = ['{"basic_info": {}, "page_config": {}}'] * config.MAX_RETRIES
    with pytest.raises(fetch.TikTokShopUpstreamError, match="without the category tree"):
        fetch.fetch_category_tree()


# ---- search: full answer or fallback ---------------------------------------------

def test_search_returns_the_first_full_answer(wire):
    wire.answers = [SEARCH_FALLBACK, SEARCH_FALLBACK, SEARCH]
    payload, is_partial = fetch.fetch_search("dog toys")
    assert is_partial is False and len(wire.sent) == 3
    assert fetch.parsers.search_is_full(payload)
    assert len(wire.sessions) == 1                               # a fallback answer is not an exit's fault: the session stays


def test_search_gives_the_fallback_rows_when_no_full_answer_comes(wire):
    wire.answers = [SEARCH_FALLBACK] * config.TIKTOK_SHOP_SEARCH_TRIES
    payload, is_partial = fetch.fetch_search("dog toys")
    assert is_partial is True and len(wire.sent) == config.TIKTOK_SHOP_SEARCH_TRIES == 6
    assert not fetch.parsers.search_is_full(payload)


def test_search_rides_through_blocks(wire):
    wire.answers = [VERIFICATION, HOME_PAGE, SEARCH_FALLBACK, Response("", 404), SEARCH]
    payload, is_partial = fetch.fetch_search("dog toys")
    assert is_partial is False and len(wire.sent) == 5
    assert len(wire.sessions) == 4                               # each failure drops the session, the fallback answer does not


def test_search_that_never_answers_is_blocked(wire):
    wire.answers = [VERIFICATION] * config.TIKTOK_SHOP_SEARCH_TRIES
    with pytest.raises(fetch.TikTokShopBlocked):
        fetch.fetch_search("dog toys")
    assert len(wire.sent) == config.TIKTOK_SHOP_SEARCH_TRIES


def test_search_keeps_a_fallback_over_a_later_block(wire):
    wire.answers = [SEARCH_FALLBACK] + [VERIFICATION] * (config.TIKTOK_SHOP_SEARCH_TRIES - 1)
    payload, is_partial = fetch.fetch_search("dog toys")
    assert is_partial is True and payload["basic_info"]


# ---- a missing product -----------------------------------------------------------

def test_a_product_missing_three_times_is_not_found(wire):
    wire.answers = [PRODUCT_MISSING, PRODUCT_UNAVAILABLE, PRODUCT_MISSING]
    with pytest.raises(fetch.TikTokShopNotFound, match="product 1729527313880355999 not found"):
        fetch.fetch_product("1729527313880355999")
    assert len(wire.sent) == config.TIKTOK_SHOP_NOT_FOUND_TRIES == 3
    assert len(wire.sessions) == 3                               # each confirmation on a fresh session


def test_a_product_that_answers_after_a_missing_answer_is_returned(wire):
    wire.answers = [PRODUCT_MISSING, PRODUCT]
    assert fetch.fetch_product(GOLI)["route_info"]["route_product_id"] == GOLI
    assert len(wire.sent) == 2


def test_a_blocked_product_is_blocked_not_missing(wire):
    wire.answers = [VERIFICATION] * config.MAX_RETRIES
    with pytest.raises(fetch.TikTokShopBlocked):
        fetch.fetch_product(GOLI)


def test_an_unknown_product_error_is_an_upstream_failure(wire):
    odd = PRODUCT_MISSING.replace("23004014", "99999999")
    wire.answers = [odd] * config.MAX_RETRIES
    with pytest.raises(fetch.TikTokShopUpstreamError, match="error 99999999"):
        fetch.fetch_product(GOLI)


# ---- a shop: its page, else its JSON calls ---------------------------------------

def test_a_shop_whose_page_answers_is_read_from_the_page(wire):
    wire.answers = [VERIFICATION, SHOP]
    assert fetch.fetch_shop(GOLI_SHOP)["route_info"]["seller_id"] == GOLI_SHOP
    assert [sent["method"] for sent in wire.sent] == ["GET", "GET"] and len(wire.sessions) == 2


def test_a_guarded_shop_is_read_from_its_record_and_its_product_list(wire):
    """AllWELL MARKET's page answers the Security Check on every exit; the page's own JSON calls answer."""
    wire.answers = [VERIFICATION] * fetch.PAGE_TRIES + [RECORD, PRODUCTS]
    page = parsers.parse_shop_page(fetch.fetch_shop(GUARDED_SHOP))
    shop = page["shop"]
    assert (shop["id"], shop["name"], shop["sold_count"], shop["product_count"], shop["rating"]) == (
        GUARDED_SHOP, "AllWELL MARKET", 180, 38, 4.0)
    assert shop["scores"] == [{"name": "Positive feedback", "value": "83%", "score": 0.83, "grade": "Good"}]
    assert page["promotions"] is None and page["categories"] is None                   # only the page shows them
    assert len(page["products"]) == 20 and page["has_more"] is True
    assert all(row["shop"]["id"] == GUARDED_SHOP for row in page["products"])
    record, products = wire.sent[fetch.PAGE_TRIES:]
    store = f"https://shop.tiktok.com/us/store/shop/{GUARDED_SHOP}"
    assert (record["method"], record["url"]) == ("POST", "https://shop.tiktok.com/api/shop/brandy_desktop/s/store_info")
    assert json.loads(record["data"]) == {"seller_id": GUARDED_SHOP, "component_name": "recommended_shops"}
    assert (products["method"], products["url"]) == ("POST", "https://shop.tiktok.com/api/shop/brandy_desktop/store/product_list")
    body = json.loads(products["data"])
    assert json.loads(body["component_info"])["component_name"] == "feed_list_store_list_product"
    assert json.loads(body["load_more_params"]) == {"sort_param": {"sort_field": 4, "sort_order": 1}, "offset": 0, "seller_id": GUARDED_SHOP}
    for sent in (record, products):
        assert sent["headers"]["content-type"] == "application/json" and sent["headers"]["referer"] == store
        assert sent["headers"]["origin"] == "https://shop.tiktok.com" and sent["headers"]["sec-fetch-mode"] == "cors"
        assert not {"user-agent", "accept-language", "cookie"} & set(sent["headers"])


def test_a_seller_id_without_a_shop_is_not_found(wire):
    """store_info answers success WITHOUT a record for a seller id that has no shop (5 of 6 tries, 2026-11-20)."""
    wire.answers = [VERIFICATION] * fetch.PAGE_TRIES + [NO_RECORD] * config.TIKTOK_SHOP_NOT_FOUND_TRIES
    with pytest.raises(fetch.TikTokShopNotFound, match="shop 7495794203056835999 not found"):
        fetch.fetch_shop("7495794203056835999")
    assert len(wire.sent) == fetch.PAGE_TRIES + config.TIKTOK_SHOP_NOT_FOUND_TRIES == 5
    assert len(wire.sessions) == len(wire.sent)                                    # every answer on a fresh session


def test_the_store_page_without_a_shop_is_confirmed_by_the_record(wire):
    wire.answers = [PAGE_WITHOUT_A_SHOP, VERIFICATION] + [NO_RECORD] * config.TIKTOK_SHOP_NOT_FOUND_TRIES
    with pytest.raises(fetch.TikTokShopNotFound):
        fetch.fetch_shop("7495794203056835999")
    wire.answers = [PAGE_WITHOUT_A_SHOP, SHOP]                                    # once, between real answers: nothing
    assert fetch.fetch_shop(GOLI_SHOP)["route_info"]["seller_id"] == GOLI_SHOP


def test_refusals_between_missing_records_neither_count_nor_start_the_count_again(wire):
    wire.answers = [VERIFICATION] * fetch.PAGE_TRIES + [NO_RECORD, REFUSED, NO_RECORD, Response("", 404), NO_RECORD]
    with pytest.raises(fetch.TikTokShopNotFound):
        fetch.fetch_shop("7495794203056835999")
    assert len(wire.sent) == fetch.PAGE_TRIES + 5


def test_a_record_after_a_missing_answer_wins(wire):
    wire.answers = [VERIFICATION] * fetch.PAGE_TRIES + [NO_RECORD, RECORD, PRODUCTS]
    assert parsers.parse_shop_page(fetch.fetch_shop(GUARDED_SHOP))["shop"]["name"] == "AllWELL MARKET"


def test_a_shop_nothing_answers_for_is_unavailable_never_missing(wire):
    """The page refused and store_info refused every try: nothing says the shop is gone -> 503, not 404."""
    wire.answers = [VERIFICATION, RuntimeError("timeout")] + [REFUSED, VERIFICATION, Response("", 429)]
    with pytest.raises(fetch.TikTokShopUnavailable, match="try again in a few minutes") as failure:
        fetch.fetch_shop(GUARDED_SHOP)
    assert isinstance(failure.value, Unavailable) and not isinstance(failure.value, NotFound)
    assert len(wire.sent) == fetch.PAGE_TRIES + config.MAX_RETRIES


def test_a_record_naming_another_seller_is_not_trusted(wire):
    wire.answers = [VERIFICATION] * fetch.PAGE_TRIES + [RECORD] * config.MAX_RETRIES
    with pytest.raises(fetch.TikTokShopUnavailable, match="names seller 7494894286294844644"):
        fetch.fetch_shop("7494894286294844000")


def test_an_empty_product_list_of_a_shop_that_lists_products_is_asked_again(wire):
    """product_list answered a real shop an empty list 2 times in 6 (2026-11-20)."""
    wire.answers = [VERIFICATION] * fetch.PAGE_TRIES + [RECORD, NO_PRODUCTS, REFUSED, PRODUCTS]
    page = parsers.parse_shop_page(fetch.fetch_shop(GUARDED_SHOP))
    assert len(page["products"]) == 20 and len(wire.sent) == fetch.PAGE_TRIES + 4


def test_products_that_never_answer_are_unknown_not_empty(wire):
    wire.answers = [VERIFICATION] * fetch.PAGE_TRIES + [RECORD] + [NO_PRODUCTS, REFUSED, NO_PRODUCTS]
    page = parsers.parse_shop_page(fetch.fetch_shop(GUARDED_SHOP))
    assert page["shop"]["name"] == "AllWELL MARKET" and page["products"] is None and page["has_more"] is False


def test_a_shop_that_lists_no_product_has_an_empty_list(wire):
    record = RECORD.replace('"on_sell_product_count":38', '"on_sell_product_count":0')
    assert record != RECORD
    wire.answers = [VERIFICATION] * fetch.PAGE_TRIES + [record, NO_PRODUCTS]
    page = parsers.parse_shop_page(fetch.fetch_shop(GUARDED_SHOP))
    assert page["products"] == [] and len(wire.sent) == fetch.PAGE_TRIES + 2
