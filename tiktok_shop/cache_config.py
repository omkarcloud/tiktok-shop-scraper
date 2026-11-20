"""Cache TTL per /tiktok-shop/* surface (cache.py, keyed on the validated
params). Stock, prices and promotion labels move through the day (flash
sales run for hours), so nothing that carries a price is kept long.
"""
from datetime import timedelta

# products/search, a FULL answer: the ranking and the prices in it move
# with the day's promotions
SEARCH_CACHE = timedelta(hours=1)
# products/search, a PARTIAL answer (the site's 5-row fallback list after
# every try): kept just long enough to spare the site the same six calls
# from a caller who retries at once; the next call may get the full page
SEARCH_PARTIAL_CACHE = timedelta(minutes=2)
# products/details: price, the exact stock of every SKU, the sold count
# and the first reviews
PRODUCT_CACHE = timedelta(hours=1)
# the shop page behind shops/details and shops/products: follower and sold
# counts creep, the 20 best sellers carry prices
SHOP_CACHE = timedelta(hours=2)
# a shop read from its page's JSON calls because TikTok Shop guarded the
# page (fetch.fetch_shop): its promotions and categories are unknown, maybe
# its products too. A guarded page can open again within the hour (one of
# the 7 guarded shops of a "dog toys" search answered its page about 20
# minutes after a refusal, 2026-11-20), so a later call gets its chance at
# the full page
SHOP_PARTIAL_CACHE = timedelta(minutes=20)
# categories/list: the storefront's category tree changes with
# merchandising, a few times a year
CATEGORIES_CACHE = timedelta(hours=24)
# categories/products: the site answers a different sample of the category
# on every call, so a short TTL keeps a caller's repeated calls varied
CATEGORY_PRODUCTS_CACHE = timedelta(minutes=10)
