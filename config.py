"""Configuration for the TikTok Shop Scraper. Everything can be set with an environment
variable; the defaults work out of the box.

    PORT                port the API listens on (default 8000)
    TIKTOK_SHOP_PROXY   proxy URL for every request, e.g. http://user:pass@host:port
                        (default: none, requests go out from your own connection).
                        TikTok Shop answers US addresses only: in the US, leave it
                        unset; anywhere else, use a US datacenter proxy.

Everything else below is a plain constant with a working default.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

TIKTOK_SHOP_PROXY = os.environ.get("TIKTOK_SHOP_PROXY") or None


# ---- what the code reads off config: defaults for a direct run ----
MAX_RETRIES = 3
RETRY_BACKOFF = 2
TIKTOK_SHOP_CATEGORY_TREE_PAGE = '601450'
TIKTOK_SHOP_EXIT = TIKTOK_SHOP_PROXY      # the exit every session leaves through: your proxy, or direct
TIKTOK_SHOP_NOT_FOUND_TRIES = 3
TIKTOK_SHOP_SEARCH_TRIES = 6
