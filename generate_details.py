"""Generate a reverse Billboard chart CSV, preserving verified metadata."""
import csv
import io
from pathlib import Path
import requests

CHART_URL = "https://raw.githubusercontent.com/mhollingshead/billboard-hot-100/main/recent.json"
OUTPUT = Path("billboard_hot_100_details.csv")
FIELDS = [
    "Billboard-positie", "Artiest", "Nummer", "Land",
    "Staat/regio", "Stad", "Eerste officiële releasedatum",
    "Bron herkomst", "Bron releasedatum",
]

def main():
    response = requests.get(CHART_URL, timeout=40)
    response.raise_for_status()
    chart = response.json()
    entries = chart.get("data", [])
    positions = [s.get("this_week") for s in entries]
    if len(entries) != 100 or sorted(positions) != list(range(1, 101)):
        raise RuntimeError("Chart must contain all 100 positions; CSV unchanged.")

    existing = {}
    if OUTPUT.exists():
        with OUTPUT.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                key = (row.get("Artiest", "").casefold(), row.get("Nummer", "").casefold())
                existing[key] = row

    rows = []
    for song in sorted(entries, key=lambda s: s["this_week"], reverse=True):
        artist, title = song["artist"], song["song"]
        prior = existing.get((artist.casefold(), title.casefold()), {})
        row = {"Billboard-positie": song["this_week"], "Artiest": artist, "Nummer": title}
        for field in FIELDS[3:]:
            row[field] = prior.get(field, "")
        rows.append(row)

    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Created {OUTPUT}: 100 songs, #100 to #1; chart date {chart.get('date')}")
    print("Unknown artist origins and first-release dates intentionally remain blank.")

if __name__ == "__main__":
    main()
