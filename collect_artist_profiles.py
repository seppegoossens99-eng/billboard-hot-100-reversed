"""Artist portraits (Wikidata/Commons) and ages (MusicBrainz), no guessed identities."""
import csv
import json
import time
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
    if not isinstance(birth, str) or not birth:
        return ""
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
    unique = {(r["Artiest"], r["Bron herkomst"]) for r in artists if r.get("Artiest")}
    entries = []
    qids = set()
    for name, source in sorted(unique):
        artist_id = source.rsplit("/", 1)[-1] if source.startswith("https://musicbrainz.org/artist/") else ""
        data = cache.get(artist_id, {}).get("data", {})
        # A valid MusicBrainz match may be new and absent from the band cache.
        # Fetch its identity and Wikidata link rather than leaving the portrait blank.
        if artist_id and (not data or not wikidata_id(data)):
            time.sleep(1.1)  # MusicBrainz public API rate limit
            try:
                response = requests.get(
                    f"https://musicbrainz.org/ws/2/artist/{artist_id}",
                    params={"inc": "url-rels", "fmt": "json"},
                    headers=HEADERS, timeout=20,
                )
                response.raise_for_status()
                fresh = response.json()
                if fresh.get("id") == artist_id:
                    data = {**data, **fresh}
            except (requests.RequestException, ValueError) as exc:
                print(f"MusicBrainz profile unavailable for {name}: {exc}", flush=True)
        qid = wikidata_id(data)
        if artist_id and qid:
            print(f"Verified Wikidata link: {name} -> {qid}", flush=True)
        if qid:
            qids.add(qid)
        birth = (data.get("life-span") or {}).get("begin", "") if data.get("type") == "Person" else ""
        entries.append((name, data.get("type", ""), birth, age_at(birth), qid, source))
    # Preserve previously verified photos if Wikidata temporarily fails.
    previous = {}
    if OUT.exists():
        with OUT.open(encoding="utf-8-sig", newline="") as old_file:
            previous = {row["Artiest"]: row for row in csv.DictReader(old_file)}
    images = {}
    wikidata_births = {}
    wikipedia_pages = {}
    ids = sorted(qids)
    for offset in range(0, len(ids), 50):
        try:
            response = requests.get("https://www.wikidata.org/w/api.php", params={
                "action": "wbgetentities", "ids": "|".join(ids[offset:offset + 50]),
                "props": "claims|sitelinks", "format": "json"}, headers=HEADERS, timeout=30)
            response.raise_for_status()
            for qid, entity in response.json().get("entities", {}).items():
                enwiki = entity.get("sitelinks", {}).get("enwiki", {}).get("title", "")
                if enwiki:
                    wikipedia_pages[qid] = enwiki
                for claim in entity.get("claims", {}).get("P569", []):
                    value = (claim.get("mainsnak", {}).get("datavalue") or {}).get("value", {})
                    if not isinstance(value, dict) or value.get("precision") != 11:
                        continue
                    raw = value.get("time", "")
                    candidate = raw[1:11] if raw.startswith("+") else ""
                    if age_at(candidate):
                        wikidata_births[qid] = candidate
                        break
                claims = entity.get("claims", {}).get("P18", [])
                if claims:
                    filename = claims[0].get("mainsnak", {}).get("datavalue", {}).get("value", "")
                    if isinstance(filename, str) and filename:
                        images[qid] = "https://commons.wikimedia.org/wiki/Special:FilePath/" + quote(filename.replace(" ", "_"), safe="")
        except (requests.RequestException, ValueError) as exc:
            print(f"Wikidata batch unavailable: {exc}", flush=True)
    wikipedia_images = {}
    for qid, title in wikipedia_pages.items():
        if qid in images:
            continue
        try:
            response = requests.get("https://en.wikipedia.org/w/api.php", params={
                "action": "query", "titles": title, "prop": "pageimages",
                "pithumbsize": 600, "format": "json"
            }, headers=HEADERS, timeout=15)
            response.raise_for_status()
            for page in response.json().get("query", {}).get("pages", {}).values():
                url = page.get("thumbnail", {}).get("source", "")
                if url.startswith("https://upload.wikimedia.org/"):
                    wikipedia_images[qid] = url
        except (requests.RequestException, ValueError) as exc:
            print(f"Wikipedia thumbnail unavailable for {qid}: {exc}", flush=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(FIELDS)
        for name, kind, birth, age, qid, source in entries:
            prior = previous.get(name, {})
            photo = images.get(qid, "") or wikipedia_images.get(qid, "") or (prior.get("Afbeelding", "") if prior.get("Bron afbeelding", "") and (not qid or prior.get("Bron afbeelding", "").endswith("/" + qid)) else "")
            photo_source = ("https://www.wikidata.org/wiki/" + qid if images.get(qid) else ("https://en.wikipedia.org/wiki/" + quote(wikipedia_pages[qid].replace(" ", "_"), safe="()_") if wikipedia_images.get(qid) else (prior.get("Bron afbeelding", "") if photo else "")))
            age_source = source if age else ""
            if kind == "Person" and not age and qid and qid in wikidata_births:
                birth = wikidata_births[qid]
                age = age_at(birth)
                age_source = "https://www.wikidata.org/wiki/" + qid
            # Keep an earlier sourced birth date if the current provider is
            # temporarily missing it; recompute age on every weekly run.
            if kind == "Person" and not age:
                old_birth = prior.get("Geboortedatum", "")
                old_source = prior.get("Bron leeftijd", "")
                old_age = age_at(old_birth)
                if old_age and old_source:
                    birth, age, age_source = old_birth, old_age, old_source
            writer.writerow([name, kind, birth if age else "", age, photo, photo_source, age_source])
    print(f"Profiles: {len(entries)}, photos: {sum(bool(images.get(e[4])) for e in entries)}, ages: {sum(bool(e[3]) for e in entries)}", flush=True)

if __name__ == "__main__":
    main()
