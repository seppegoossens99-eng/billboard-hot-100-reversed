"""Collect sourced band memberships from MusicBrainz; unknown counts stay unknown."""
import csv
import json
import time
from datetime import date, timedelta
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "band_members_cache.json"
OUTPUT = ROOT / "billboard_band_members.csv"
HEADERS = ["Artiest", "Band", "Leden (bevestigd huidig)", "Volledigheid", "Lid", "Functie/instrument", "Status", "Bron"]
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "BillboardReverseMetadata/1.0 (https://github.com/seppegoossens99-eng/billboard-hot-100-reversed)"})
last_request = 0.0

def get_artist(artist_id):
    global last_request
    delay = 1.2 - (time.monotonic() - last_request)
    if delay > 0:
        time.sleep(delay)
    for attempt in range(2):
        try:
            last_request = time.monotonic()
            response = SESSION.get(f"https://musicbrainz.org/ws/2/artist/{artist_id}",
                                   params={"inc": "artist-rels", "fmt": "json"}, timeout=20)
            if response.status_code in (429, 503):
                time.sleep(5)
                continue
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"Artist {artist_id}: {exc}", flush=True)
            if attempt == 0:
                time.sleep(2)
    return {}

def memberships(data):
    members = {}
    for relation in data.get("relations", []):
        if relation.get("type") != "member of band" or relation.get("target-type") != "artist":
            continue
        person = relation.get("artist") or {}
        if person.get("type") != "Person" or not person.get("id"):
            continue
        member_id = person["id"]
        entry = members.setdefault(member_id, {"name": person.get("name", ""), "roles": set(), "current": False, "former": False})
        ended = bool(relation.get("ended") or (relation.get("end") or relation.get("end-date")))
        entry["former" if ended else "current"] = True
        for role in relation.get("attributes") or []:
            if role:
                entry["roles"].add(role)
    return members

def main():
    with (ROOT / "billboard_hot_100_artists.csv").open(encoding="utf-8-sig", newline="") as file:
        artists = list(csv.DictReader(file))
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    output = []
    for name, url in sorted({(row["Artiest"], row["Bron herkomst"]) for row in artists if row["Bron herkomst"].startswith("https://musicbrainz.org/artist/")}):
        artist_id = url.rsplit("/", 1)[-1]
        item = cache.get(artist_id, {})
        if item.get("checked", "") < cutoff or not item.get("data"):
            data = get_artist(artist_id)
            if data:
                cache[artist_id] = {"checked": date.today().isoformat(), "data": data}
            else:
                data = item.get("data", {})
        else:
            data = item["data"]
        if data.get("type") != "Group":
            continue
        members = memberships(data)
        current = sorted((v for v in members.values() if v["current"]), key=lambda v: v["name"].casefold())
        former = sorted((v for v in members.values() if v["former"] and not v["current"]), key=lambda v: v["name"].casefold())
        # A group may have undocumented members; never claim a definitive total.
        count = str(len(current)) if current else ""
        for person, status in [(p, "Huidig (volgens MusicBrainz)") for p in current] + [(p, "Voormalig") for p in former]:
            output.append([name, "Ja", count, "Aantal gedocumenteerde huidige leden; mogelijk onvolledig",
                           person["name"], ", ".join(sorted(person["roles"])) or "Niet vermeld", status, url])
        if not current and not former:
            output.append([name, "Ja", "", "Geen ledengegevens beschikbaar", "", "", "", url])
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(HEADERS)
        writer.writerows(output)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Band members: {len(output)} rows, {len(cache)} cached artists", flush=True)

if __name__ == "__main__":
    main()
