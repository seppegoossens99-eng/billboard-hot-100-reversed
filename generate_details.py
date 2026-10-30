"""Enrich Billboard CSV from MusicBrainz. Unknown/ambiguous fields stay blank."""
import csv
import re
import time
import unicodedata
from pathlib import Path
import requests

CHART_URL = "https://raw.githubusercontent.com/mhollingshead/billboard-hot-100/main/recent.json"
MB = "https://musicbrainz.org/ws/2"
OUTPUT = Path("billboard_hot_100_details.csv")
FIELDS = ["Billboard-positie", "Artiest", "Nummer", "Land", "Staat/regio", "Stad",
          "Eerste officiële releasedatum", "Bron herkomst", "Bron releasedatum"]
HEADERS = {"User-Agent": "BillboardReverseMetadata/1.0 (https://github.com/seppegoossens99-eng/billboard-hot-100-reversed)"}
session = requests.Session()
session.headers.update(HEADERS)
last_call = 0.0

def norm(value):
    value = unicodedata.normalize("NFKD", value.casefold())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in value if not unicodedata.combining(c))).strip()

def main_artist(value):
    return re.split(r"\s+(?:featuring|feat\.?|ft\.?|with|x)\s+|\s*&\s*|,", value, 1, re.I)[0].strip()

def mb_get(entity, params):
    global last_call
    wait = 1.15 - (time.monotonic() - last_call)
    if wait > 0:
        time.sleep(wait)
    try:
        last_call = time.monotonic()
        response = session.get(f"{MB}/{entity}", params={**params, "fmt": "json"}, timeout=18)
        if response.status_code in (429, 503):
            time.sleep(4)
            last_call = time.monotonic()
            response = session.get(f"{MB}/{entity}", params={**params, "fmt": "json"}, timeout=18)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"MusicBrainz unavailable for {entity}: {exc}", flush=True)
        return {}

artist_cache = {}
recording_cache = {}

def artist_details(name):
    key = norm(name)
    if key in artist_cache:
        return artist_cache[key]
    result = ("", "", "", "")
    data = mb_get("artist", {"query": f'artist:"{name}"', "limit": 8})
    candidates = [a for a in data.get("artists", []) if norm(a.get("name", "")) == key
                  and int(a.get("score", 0)) >= 90]
    # Multiple identically named artists: do not guess.
    if len(candidates) == 1:
        artist = candidates[0]
        country = artist.get("country", "")
        begin = artist.get("begin-area") or {}
        area = artist.get("area") or {}
        city = begin.get("name", "")
        region = ""
        if country == "US":
            if area.get("name", "") != "United States":
                region = area.get("name", "")
            country = "Verenigde Staten"
        elif country:
            country = country  # ISO country code is retained unambiguously.
        # Begin-area can itself be a state or country, not necessarily a city.
        if city and (city == area.get("name") or city == country or city == region):
            city = ""
        result = (country, region, city, f"https://musicbrainz.org/artist/{artist['id']}")
    artist_cache[key] = result
    return result

def earliest_recording_date(title, artist):
    key = (norm(title), norm(artist))
    if key in recording_cache:
        return recording_cache[key]
    result = ("", "")
    data = mb_get("recording", {"query": f'recording:"{title}" AND artist:"{artist}"', "limit": 25})
    dates = []
    for rec in data.get("recordings", []):
        if norm(rec.get("title", "")) != norm(title):
            continue
        credited = rec.get("artist-credit", [])
        names = [norm(a.get("artist", {}).get("name", "")) for a in credited if isinstance(a, dict)]
        if norm(artist) not in names:
            continue
        date = rec.get("first-release-date", "")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            dates.append((date, rec["id"]))
    # This is the earliest known MusicBrainz recording date, not proof of the
    # first-ever official release. Keep source so it can be manually verified.
    if dates:
        date, rec_id = min(dates)
        result = (date, f"https://musicbrainz.org/recording/{rec_id}")
    recording_cache[key] = result
    return result

def main():
    response = session.get(CHART_URL, timeout=40)
    response.raise_for_status()
    chart = chart_data = response.json()
    songs = chart_data.get("data", [])
    if len(songs) != 100 or sorted(s.get("this_week") for s in songs) != list(range(1, 101)):
        raise RuntimeError("Incomplete Billboard chart; existing CSV unchanged.")

    existing = {}
    if OUTPUT.exists():
        with OUTPUT.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                existing[(norm(row.get("Artiest", "")), norm(row.get("Nummer", "")))] = row

    rows = []
    for i, song in enumerate(sorted(songs, key=lambda s: s["this_week"], reverse=True), 1):
        artist, title = song["artist"], song["song"]
        prior = existing.get((norm(artist), norm(title)), {})
        row = {"Billboard-positie": song["this_week"], "Artiest": artist, "Nummer": title}
        row.update({field: prior.get(field, "") for field in FIELDS[3:]})
        lead = main_artist(artist)
        if not row["Bron herkomst"]:
            country, region, city, source = artist_details(lead)
            if source:
                row.update({"Land": country, "Staat/regio": region, "Stad": city,
                            "Bron herkomst": source})
        if not row["Bron releasedatum"]:
            date, source = earliest_recording_date(title, lead)
            if source:
                row["Eerste officiële releasedatum"] = date
                row["Bron releasedatum"] = source
        rows.append(row)
        print(f"{i}/100: #{song['this_week']} {artist} - {title}", flush=True)

    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print("Saved 100 chart rows. MusicBrainz dates are provisional and need verification.", flush=True)

if __name__ == "__main__":
    main()
