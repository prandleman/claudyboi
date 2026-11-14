"""Scrape eBay *sold* listings for a search query and report price range and average.

Usage:
    uv run ebay_sold.py "nintendo switch oled" --pages 2
    uv run ebay_sold.py "nintendo switch oled" --json

Notes:
    * Uses eBay's search with LH_Sold=1 (sold items) and LH_Complete=1 (completed).
    * Prices are the item price only (shipping is excluded).
    * Price ranges such as "$10.00 to $20.00" use the low end.
    * Respects eBay's terms: keep --pages small and don't run this in a tight loop.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

BASE_URL = "https://www.ebay.com/sch/i.html"
CHROMIUM_PATH = "/opt/pw-browsers/chromium"  # pre-installed in this environment

# Current eBay markup uses "s-card"; older markup used "s-item". Support both.
ITEM_SELECTOR = "li.s-card, li.s-item"
TITLE_SELECTORS = ".s-card__title, .s-item__title"
PRICE_SELECTORS = ".s-card__price, .s-item__price"

PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")


@dataclass
class SoldItem:
    title: str
    price: float


def parse_price(text: str) -> float | None:
    """Return the item price in dollars, using the low end of a range."""
    match = PRICE_RE.search(text or "")
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def parse_items(items: list[tuple[str, str]]) -> list[SoldItem]:
    """Convert (title, price_text) pairs into SoldItems, skipping placeholders."""
    results: list[SoldItem] = []
    for title, price_text in items:
        title = (title or "").strip()
        if not title or title.lower().startswith("shop on ebay"):
            continue  # eBay inserts a "Shop on eBay" placeholder card
        price = parse_price(price_text)
        if price is None or price <= 0:
            continue
        results.append(SoldItem(title=title, price=price))
    return results


def build_url(query: str, page: int) -> str:
    params = {"_nkw": query, "LH_Sold": "1", "LH_Complete": "1", "_ipg": "240"}
    if page > 1:
        params["_pgn"] = str(page)
    return f"{BASE_URL}?{urlencode(params)}"


def scrape_page(page, url: str) -> list[tuple[str, str]]:
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    try:
        page.wait_for_selector(ITEM_SELECTOR, timeout=15_000)
    except Exception:
        return []  # no results, or a block/CAPTCHA page
    rows = []
    for item in page.query_selector_all(ITEM_SELECTOR):
        title_el = item.query_selector(TITLE_SELECTORS)
        price_el = item.query_selector(PRICE_SELECTORS)
        title = title_el.inner_text() if title_el else ""
        price = price_el.inner_text() if price_el else ""
        rows.append((title, price))
    return rows


def scrape_sold(query: str, pages: int, headed: bool, delay: float) -> list[SoldItem]:
    items: list[SoldItem] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROMIUM_PATH,
            headless=not headed,
            args=["--no-sandbox"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = context.new_page()
        try:
            for n in range(1, pages + 1):
                rows = scrape_page(page, build_url(query, n))
                if not rows:
                    break
                items.extend(parse_items(rows))
                if n < pages:
                    time.sleep(delay)
        finally:
            browser.close()
    return items


def summarize(items: list[SoldItem]) -> dict:
    if not items:
        return {"count": 0}
    prices = [i.price for i in items]
    return {
        "count": len(prices),
        "min": min(prices),
        "max": max(prices),
        "average": round(statistics.fmean(prices), 2),
        "median": round(statistics.median(prices), 2),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="eBay sold-listing price summary")
    ap.add_argument("query", help="search text, e.g. 'nintendo switch oled'")
    ap.add_argument("--pages", type=int, default=1, help="result pages to read (default 1)")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between pages")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args(argv)

    items = scrape_sold(args.query, args.pages, args.headed, args.delay)
    summary = summarize(items)

    if args.json:
        print(json.dumps({"query": args.query, "summary": summary,
                          "items": [asdict(i) for i in items]}, indent=2))
        return 0 if items else 1

    if not items:
        print("No sold listings found (or eBay blocked the request).", file=sys.stderr)
        return 1
    print(f"Query:   {args.query}")
    print(f"Sold listings: {summary['count']}")
    print(f"Range:   ${summary['min']:,.2f} – ${summary['max']:,.2f}")
    print(f"Average: ${summary['average']:,.2f}")
    print(f"Median:  ${summary['median']:,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
