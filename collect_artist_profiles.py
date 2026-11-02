"""Artist portraits (Wikidata/Commons) and ages (MusicBrainz), no guessed identities."""
import csv
import json
from datetime import date
from pathlib import Path
from urllib.parse import quote
import requests

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "band_members_cache.json"
OUT = ROOT / "billboard_artist_profiles.csv"
FIELDS = ["Artiest", "Type", "Geboortedatum", "Leeftijd", "Afbeelding", "Bron afbeelding", "Bron leeftijd"]
HEADERS = {"User-Agent": "BillboardReverseMetadata/1.0 (https://github.com/seppegoossens99-eng/billboard-hot-100-reversed)"}

def wikidata_id(data):
    for rel in data.get("relations", []):
        if rel.get("type") == "wikidata":
            url = (rel.get("url") or {}).get("resource", "")
            qid = url.rstrip("/").split("/")[-1]
            if qid.startswith("Q") and qid[1:].isdigit():
                return qid
    return ""

def age_at(birth):
    try:
        born = date.fromisoformat(birth)
        today = date.today()
        return str(today.year - born.year - ((today.month, today.day) < (born.month, born.day)))
    except ValueError:
        return ""

def main():
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    with (ROOT / "billboard_hot_100_artists.csv").open(encoding="utf-8-sig", newline="") as f:
        artists = list(csv.DictReader(f))
    unique = {(r["Artiest"], r["Bron herkomst"]) for r in artists if r["Bron herkomst"].startswith("https://musicbrainz.org/artist/")}
    entries = []
    qids = set()
    for name, source in sorted(unique):
        artist_id = source.rsplit("/", 1)[-1]
        data = cache.get(artist_id, {}).get("data", {})
        if not data:
            continue
        qid = wikidata_id(data)
        if qid:
            qids.add(qid)
        birth = (data.get("life-span") or {}).get("begin", "") if data.get("type") == "Person" else ""
        entries.append((name, data.get("type", ""), birth, age_at(birth), qid, source))
    images = {}
    ids = sorted(qids)
    for offset in range(0, len(ids), 50):
        try:
            response = requests.get("https://www.wikidata.org/w/api.php", params={
                "action": "wbgetentities", "ids": "|".join(ids[offset:offset + 50]),
                "props": "claims", "format": "json"}, headers=HEADERS, timeout=30)
            response.raise_for_status()
            for qid, entity in response.json().get("entities", {}).items():
                claims = entity.get("claims", {}).get("P18", [])
                if claims:
                    filename = claims[0].get("mainsnak", {}).get("datavalue", {}).get("value", "")
                    if isinstance(filename, str) and filename:
                        images[qid] = "https://commons.wikimedia.org/wiki/Special:FilePath/" + quote(filename.replace(" ", "_"), safe="")
        except (requests.RequestException, ValueError) as exc:
            print(f"Wikidata batch unavailable: {exc}", flush=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(FIELDS)
        for name, kind, birth, age, qid, source in entries:
            writer.writerow([name, kind, birth if age else "", age, images.get(qid, ""),
                             "https://www.wikidata.org/wiki/" + qid if images.get(qid) else "", source if age else ""])
    print(f"Profiles: {len(entries)}, photos: {sum(bool(images.get(e[4])) for e in entries)}, ages: {sum(bool(e[3]) for e in entries)}", flush=True)

if __name__ == "__main__":
    main()
