# 🚀 TikTok Shop Scraper

TikTok Shop Scraper is a **free and open-source** scraper that gets you **unlimited** detailed TikTok Shop data for free.

## ✨ What Can I Get?

- 🛒 **Full details of 70M+ products** — price, every SKU with live stock, shipping dates, rating breakdown, specs, FAQ, the seller's business address & the first 5 reviews
- 🔍 **30 products per search** — price, discount, rating, units sold & shop, plus the featured shop, filters, related searches & categories
- 🏪 **500,000+ US shops & their 20 best sellers** — rating, followers, units sold, product & video counts, performance scores & promotions
- 📂 **All 28 categories & 212 subcategories** — the full category tree, plus products & 10 recent reviews from any category

## 🛒 Example: A Full TikTok Shop Product

```json
{
  "id": "1729554646471512584",
  "title": "PAVOI 14K Gold Plated 3mm Cubic Zirconia Classic Tennis Bracelet - Hypoallergenic Gold Bracelets for Women - Size 6.5-7.5 Inch - Simulated Diamond Tennis Bracelets",
  "link": "https://shop.tiktok.com/us/pdp/pavoi-14k-gold-plated-tennis-bracelet-hypoallergenic-3mm-cz/1729554646471512584",
  "brand": "PAVOI",
  "price": 33.28,
  "currency": "USD",
  "is_in_stock": true,
  "sold_count": 65542,
  "rating": 4.6,
  "review_count": 7683,
  "rating_counts": [{ "stars": 5, "count": 6598 }, { "stars": 4, "count": 390 }],
  "highlights": ["3mm AAAAA cubic zirconia stones for a diamond-like sparkle", "Available in 14K yellow gold, rose gold, or rhodium plating"],
  "categories": [{ "id": "953224", "name": "Jewelry Accessories & Derivatives", "level": 1 }, { "id": "955784", "name": "Platinum & Carat Gold Bracelets & Anklets", "level": 3 }],
  "skus": [
    { "id": "1732412449677152776", "options": [{ "name": "Color", "value": "Yellow Gold" }, { "name": "Length", "value": "6.5 Inches" }], "price": 40.83, "original_price": 45.37, "discount_percent": 10, "stock": 416 }
  ],
  "shipping": { "method": "3-day delivery", "is_free": true, "original_fee": 5.99, "min_days": 1, "max_days": 3 },
  "seller_information": [{ "name": "Business name", "value": "Akofiko Inc." }],
  "shop": { "id": "7494842749961013768", "name": "PAVOI", "badge": "OFFICIAL SHOP", "rating": 4.6, "sold_count": 2041870, "follower_count": 444980 },
  "reviews": [
    { "rating": 5, "text": "Beautiful!!!! And it’s great quality! The seller had the beautiful jewelry to me the next day. It was super fast delivery!…", "reviewer_name": "E**n S**n", "is_verified_purchase": true }
  ]
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free TikTok Shop Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/tiktok-shop-scraper
cd tiktok-shop-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

**TikTok Shop answers US addresses only: in the US, your own connection works; anywhere else, use a US datacenter proxy.** Set it like this: `TIKTOK_SHOP_PROXY=http://user:pass@host:port python run.py`.

Now and then TikTok Shop answers a search with a short 5-product list. The scraper asks again, up to 6 times, and marks a short answer with `is_partial: true`.

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/products/details?product=1729554646471512584"
```

```json
{
  "id": "1729554646471512584",
  "title": "PAVOI 14K Gold Plated 3mm Cubic Zirconia Classic Tennis Bracelet - Hypoallergenic Gold Bracelets for Women - Size 6.5-7.5 Inch - Simulated Diamond Tennis Bracelets",
  "brand": "PAVOI",
  "price": 33.28,
  "currency": "USD",
  "is_in_stock": true,
  "sold_count": 65545,
  "rating": 4.6,
  "review_count": 7683,
  "highlights": ["3mm AAAAA cubic zirconia stones for a diamond-like sparkle"],
  "skus": [
    { "id": "1732412449677152776", "options": [{ "name": "Color", "value": "Yellow Gold" }, { "name": "Length", "value": "6.5 Inches" }], "price": 40.83, "stock": 416 }
  ],
  "shipping": { "method": "3-day delivery", "is_free": true, "min_days": 1, "max_days": 3 },
  "shop": { "id": "7494842749961013768", "name": "PAVOI", "badge": "OFFICIAL SHOP", "follower_count": 444987 },
  "reviews": [{ "rating": 5, "reviewer_name": "E**n S**n", "is_verified_purchase": true }]
}
```

All 6 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

6 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Product Details | `/products/details` | The whole product: every SKU with stock, shipping, specs and reviews |
| Search Products | `/products/search` | 30 products per search, plus matching shops, filters and related searches |
| Categories / Category Products | `/categories/list`, `/categories/products` | The full category tree, plus products and reviews from any category |
| Shop Details / Shop Products | `/shops/details`, `/shops/products` | A shop's profile, scores and promotions, plus its 20 best sellers |


## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-tiktok-shop-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-tiktok-shop-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-tiktok-shop-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/products/details",
    params={"product": "1729554646471512584"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about TikTok Shop Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://www.omkar.cloud/l/tiktok-shop-scraper-github-whatsapp)

[![Ask Us by Email about TikTok Shop Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20TikTok%20Shop%20Scraper%20API&body=I%20need%20help%20using%20the%20TikTok%20Shop%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/tiktok-shop-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/tiktok-shop-scraper)
