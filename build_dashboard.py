"""Embed cars.csv into dashboard_template.html -> dashboard.html (opens by double-click, no server)."""
import csv
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent

NUMERIC = {"year", "price_millions", "first_price_millions", "km", "photos"}


def build():
    with (ROOT / "cars.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in NUMERIC:
            try:
                r[k] = float(r[k]) if "." in r[k] else int(r[k])
            except (ValueError, TypeError):
                r[k] = None
    payload = json.dumps({"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "rows": rows},
                         ensure_ascii=False).replace("</", "<\\/")
    html = (ROOT / "dashboard_template.html").read_text(encoding="utf-8")
    (ROOT / "dashboard.html").write_text(html.replace("__DATA__", payload), encoding="utf-8")
    print(f"dashboard.html rebuilt with {len(rows)} ads")


if __name__ == "__main__":
    build()
