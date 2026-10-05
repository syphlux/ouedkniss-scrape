"""Scrape Ouedkniss car listings into cars.csv, then rebuild dashboard.html.

Usage:  python scraper.py            (normal run)
        python scraper.py --pages 5  (override page limit)
"""
import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

from models import infer_brand_model

ROOT = Path(__file__).parent
CSV_PATH = ROOT / "cars.csv"
LOG_PATH = ROOT / "scrape.log"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

FIELDS = ["id", "title", "brand", "model", "year", "price_millions", "first_price_millions", "engine", "fuel",
          "km", "gearbox", "location", "wilaya", "seller", "photos", "posted_at", "first_seen", "last_seen",
          "category", "url"]

FUELS = {"Essence", "Diesel", "GPL", "Hybride", "Electrique", "Électrique", "Hybride rechargeable"}
GEARS = {"Manuelle", "Automatique", "Semi Automatique"}

# Runs in the page: one entry per regular (non-sponsored) ad card.
EXTRACT_JS = r"""
() => {
  const out = new Map();
  for (const a of document.querySelectorAll('main a[href]')) {
    const h = a.getAttribute('href');
    if (!/-d\d+$/.test(h) || out.has(h)) continue;
    let c = a;
    while (c.parentElement && c.innerText.split('\n').length < 6) c = c.parentElement;
    out.set(h, c.innerText.split('\n').map(s => s.trim()).filter(Boolean));
  }
  return [...out].map(([href, lines]) => ({href, lines}));
}
"""


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def relative_to_datetime(text, now):
    """'9 minutes' / '1 heure' / '3 jours' -> approximate datetime."""
    m = re.match(r"(\d+)\s*(\w+)", text or "")
    if not m:
        return ""
    n, unit = int(m.group(1)), m.group(2).lower()
    delta = {"s": timedelta(seconds=n), "m": timedelta(minutes=n), "h": timedelta(hours=n), "j": timedelta(days=n)}
    if unit.startswith("mois"):
        d = timedelta(days=30 * n)
    elif unit.startswith("an"):
        d = timedelta(days=365 * n)
    elif unit.startswith("sem"):
        d = timedelta(weeks=n)
    else:
        d = delta.get(unit[0], timedelta())
    return (now - d).strftime("%Y-%m-%d %H:%M")


def parse_card(href, lines, now):
    lines = [x for x in lines if x not in ("Appeler", "Message", "Sponsorisée", "Sponsorisé", "Boostée")]
    if lines.count("Millions") != 1 or not any(re.search(r"km$", x, re.I) for x in lines):
        return None  # sponsored carousel, card without price, or non-vehicle ad
    photos = lines.pop(0) if re.fullmatch(r"\d+", lines[0]) else ""
    mi = lines.index("Millions")
    title, price = lines[0], lines[mi - 1].replace(" ", "")
    rest = lines[mi + 1:]
    try:
        if float(price) < CONFIG.get("min_price_millions", 0):
            return None  # placeholder prices like "1 Million"
    except ValueError:
        return None

    km = fuel = gear = ""
    engine, other = [], []
    for x in rest:
        if re.fullmatch(r"[\d.\s]+km", x, re.I):
            km = re.sub(r"\D", "", x)
        elif x in FUELS:
            fuel = x
        elif x in GEARS:
            gear = x
        else:
            other.append(x)

    # Remaining order: [engine...] location posted [seller]
    loc_idx = next((i for i, x in enumerate(other) if re.search(r",\s*\d+$", x)), None)
    location = posted = seller = ""
    if loc_idx is not None:
        engine = other[:loc_idx]
        location = other[loc_idx]
        posted = other[loc_idx + 1] if loc_idx + 1 < len(other) else ""
        seller = " ".join(other[loc_idx + 2:])
    else:
        engine = other

    brand, model = infer_brand_model(title)
    year = (re.search(r"\b(19|20)\d{2}\b", title) or [""])[0]
    ad_id = re.search(r"-d(\d+)$", href).group(1)
    return {
        "id": ad_id, "title": title, "brand": brand, "model": model, "year": year,
        "price_millions": price, "first_price_millions": price, "engine": " ".join(engine), "fuel": fuel,
        "km": km, "gearbox": gear, "location": location.split(",")[0].strip(),
        "wilaya": location.split(",")[-1].strip() if "," in location else "", "seller": seller,
        "photos": photos, "posted_at": relative_to_datetime(posted, now),
        "first_seen": now.strftime("%Y-%m-%d %H:%M"), "last_seen": now.strftime("%Y-%m-%d %H:%M"),
        "category": href.strip("/").split("-")[0], "url": "https://www.ouedkniss.com" + href,
    }


def load_csv():
    if not CSV_PATH.exists():
        return {}
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def save_csv(rows):
    for r in rows.values():  # re-infer so edits to models.py apply to old rows too
        r["brand"], r["model"] = infer_brand_model(r["title"])
    ordered = sorted(rows.values(), key=lambda r: r["first_seen"] + r["posted_at"], reverse=True)
    tmp = CSV_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(ordered)
    tmp.replace(CSV_PATH)


def new_page(browser):
    """Page with the site's language forced to French (it defaults to Arabic for new visitors)."""
    ctx = browser.new_context(locale="fr-FR", viewport={"width": 1280, "height": 900},
                              extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9"})
    ctx.add_init_script("""
      try {
        const k = 'ok-auth-frame', v = JSON.parse(localStorage.getItem(k) || '{}');
        if (v.locale !== 'fr') { v.locale = 'fr'; localStorage.setItem(k, JSON.stringify(v)); }
      } catch (e) {}
    """)
    return ctx.new_page()


def scrape_page(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("main a[href*='-d']", timeout=30000)
    last = -1
    for _ in range(25):  # scroll until card count stops growing
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(700)
        n = page.evaluate("document.querySelectorAll('main a[href]').length")
        if n == last:
            break
        last = n
    return page.evaluate(EXTRACT_JS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, help="max pages this run")
    args = ap.parse_args()

    rows = load_csv()
    first_run = not rows
    max_pages = args.pages or (CONFIG["first_run_max_pages"] if first_run else CONFIG["max_pages_per_run"])
    stop_after = CONFIG["stop_after_known_pages"]
    log(f"Run start: {len(rows)} ads in CSV, up to {max_pages} pages{' (first run)' if first_run else ''}")

    new_count = updated = known_streak = 0
    now = datetime.now()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=CONFIG.get("headless", True))
        page = new_page(browser)
        for n in range(1, max_pages + 1):
            url = CONFIG["search_url"].format(page=n)
            try:
                cards = scrape_page(page, url)
            except Exception as e:
                log(f"Page {n}: failed ({e.__class__.__name__}: {e}); stopping")
                break
            parsed = [r for c in cards if (r := parse_card(c["href"], c["lines"], now))]
            if not parsed:
                log(f"Page {n}: no ads found; stopping")
                break

            page_new = 0
            for r in parsed:
                old = rows.get(r["id"])
                if old is None:
                    rows[r["id"]] = r
                    page_new += 1
                else:
                    old["last_seen"] = r["last_seen"]
                    if old["price_millions"] != r["price_millions"]:
                        old["price_millions"] = r["price_millions"]
                        updated += 1
            new_count += page_new
            log(f"Page {n}: {len(parsed)} ads, {page_new} new")
            save_csv(rows)

            known_streak = known_streak + 1 if page_new == 0 else 0
            if not first_run and known_streak >= stop_after:
                log(f"Page {n}: nothing new on {known_streak} page(s); caught up")
                break
            time.sleep(2)  # be polite to the site
        browser.close()

    log(f"Run end: {new_count} new, {updated} price changes, {len(rows)} total")

    from build_dashboard import build
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
