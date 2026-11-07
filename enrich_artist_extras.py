"""Fill missing artist gender and genre using verified Wikidata IDs; preserve sourced debut years."""
import csv
import json
import re
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
FIELDS = ["Artiest", "Debuutalbum", "Gender", "Genre", "Bron debuutalbum", "Bron genre"]
HEADERS = {"User-Agent": "BillboardReverseMetadata/1.0 (https://github.com/seppegoossens99-eng/billboard-hot-100-reversed)"}
GENDERS = {"Q6581097": "Man", "Q6581072": "Vrouw"}
GENRES = {
    "Q11401": "Rock", "Q37073": "Pop", "Q13151": "Hip-hop",
    "Q8341": "Jazz", "Q9759": "Blues", "Q213714": "Country",
    "Q45981": "R&B", "Q208239": "Reggae", "Q932586": "K-pop",
    "Q6010": "Rap", "Q9778": "Elektronische muziek",
    "Q373342": "Dance", "Q187854": "Folk",
    "Q10922": "Soul", "Q638": "Klassieke muziek",
    "Q11399": "Rock-'n-roll", "Q204929": "Latin pop",
}

def qid_from_profile(row):
    for field in ("Bron afbeelding", "Bron leeftijd"):
        value = row.get(field, "")
        match = re.fullmatch(r"https://www.wikidata.org/wiki/(Q\d+)", value)
        if match:
            return match.group(1)
    return ""

def claim_ids(entity, prop):
    values = []
    for claim in entity.get("claims", {}).get(prop, []):
        if claim.get("rank") == "deprecated":
            continue
        value = (claim.get("mainsnak", {}).get("datavalue") or {}).get("value", {})
        if isinstance(value, dict) and value.get("entity-type") == "item":
            values.append(value.get("id", ""))
    return values

def main():
    with (ROOT / "billboard_artist_profiles.csv").open(encoding="utf-8-sig", newline="") as f:
        profiles = list(csv.DictReader(f))
    path = ROOT / "billboard_artist_extra.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        old = {row["Artiest"]: row for row in csv.DictReader(f)}
    cache_file = ROOT / "band_members_cache.json"
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    with (ROOT / "billboard_hot_100_artists.csv").open(encoding="utf-8-sig", newline="") as f:
        credits = list(csv.DictReader(f))
    linked = {}
    for row in credits:
        source = row.get("Bron herkomst", "")
        mbid = source.rsplit("/", 1)[-1] if source.startswith("https://musicbrainz.org/artist/") else ""
        for relation in cache.get(mbid, {}).get("data", {}).get("relations", []):
            url = (relation.get("url") or {}).get("resource", "")
            match = re.fullmatch(r"https?://www.wikidata.org/wiki/(Q\d+)", url)
            if relation.get("type") == "wikidata" and match:
                linked[row["Artiest"]] = match.group(1)
    by_name = {r["Artiest"]: r for r in profiles}
    # Every credited artist receives a stable row, including newly charting acts
    # without an established Wikidata identity. Never fabricate unknown values.
    for name in by_name:
        old.setdefault(name, {"Artiest": name, **{field: "" for field in FIELDS if field != "Artiest"}})
    for name, profile in by_name.items():
        if not old[name].get("Gender") and profile.get("Type") == "Group":
            old[name]["Gender"] = "Groep"
    qids = {name: q for name, q in linked.items()}
    for row in profiles:
        qid = qid_from_profile(row)
        if qid:
            qids[row["Artiest"]] = qid
    # Some artist names are ambiguous across Wikidata (e.g. bôa and Steve Lacy).
    # Do not auto-enrich these until their identity is explicitly cross-checked.
    AMBIGUOUS_NAMES = {"boa", "Steve Lacy"}
    needed = {name: q for name, q in qids.items() if name not in AMBIGUOUS_NAMES and (not old.get(name, {}).get("Gender") or not old.get(name, {}).get("Genre"))}
    entities = {}
    ids = sorted(set(needed.values()))
    for i in range(0, len(ids), 40):
        try:
            response = requests.get("https://www.wikidata.org/w/api.php", params={
                "action": "wbgetentities", "ids": "|".join(ids[i:i+40]),
                "props": "claims", "format": "json"}, headers=HEADERS, timeout=35)
            response.raise_for_status()
            entities.update(response.json().get("entities", {}))
        except (requests.RequestException, ValueError) as exc:
            print("Wikidata unavailable:", exc, flush=True)
    added_gender = added_genre = 0
    for name, qid in needed.items():
        entity = entities.get(qid, {})
        if not entity or "missing" in entity:
            continue
        row = old.setdefault(name, dict.fromkeys(FIELDS, ""))
        row["Artiest"] = name
        if not row.get("Gender"):
            if by_name[name].get("Type") == "Group":
                row["Gender"] = "Groep"
            else:
                for value in claim_ids(entity, "P21"):
                    if value in GENDERS:
                        row["Gender"] = GENDERS[value]
                        added_gender += 1
                        break
        if not row.get("Genre"):
            genres = list(dict.fromkeys(GENRES[q] for q in claim_ids(entity, "P136") if q in GENRES))
            if genres:
                row["Genre"] = " / ".join(genres[:3])
                row["Bron genre"] = "https://www.wikidata.org/wiki/" + qid
                added_genre += 1
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in FIELDS} for row in sorted(old.values(), key=lambda r: r["Artiest"].casefold()))
    print(f"Wikidata enrichment: {added_gender} genders, {added_genre} genres; {len(old)} artist profiles.", flush=True)

if __name__ == "__main__":
    main()
