# Ouedkniss Car Tracker

Scrapes car ads from Ouedkniss every 6 hours (GitHub Actions), keeps them in `cars.csv`,
and rebuilds `dashboard.html` (filters + charts).

## Files

| File | What it does |
|---|---|
| `config.json` | Search URL (`{page}` = page number) and page limits. **Change filters here.** |
| `scraper.py` | Opens each results page, scrolls, reads ads, merges into `cars.csv`, rebuilds dashboard |
| `models.py` | Brand/model lookup from the title. Add models here when the dashboard shows `Other` |
| `build_dashboard.py` | Embeds `cars.csv` into `dashboard_template.html` -> `dashboard.html` |
| `.github/workflows/scrape.yml` | Runs the scraper every 6 h and commits the results |
| `scrape.log` | One line per page per run |

## How a run works

1. Load pages 1, 2, 3... of the search URL (French UI forced).
2. New ad id -> add a row. Known ad -> update `last_seen` and price (original kept in `first_price_millions`).
3. Stop when a whole page has no new ads (`stop_after_known_pages`), or at `max_pages_per_run`.
   The first run (empty CSV) grabs up to `first_run_max_pages`.

## Changing filters

Set up the search on ouedkniss.com, copy the URL, paste it into `config.json` as `search_url`,
and replace the page number in the path with `{page}`:

```
https://www.ouedkniss.com/automobiles_vehicules/{page}?priceUnit=MILLION&...
```

Old rows stay in the CSV; use the dashboard filters to narrow them.

## Run locally

```
pip install -r requirements.txt
python -m playwright install chromium
python scraper.py            # normal run
python scraper.py --pages 3  # cap pages
python build_dashboard.py    # rebuild dashboard only
```
