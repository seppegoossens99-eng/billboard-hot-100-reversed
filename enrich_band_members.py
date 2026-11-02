"""Add verified ages to documented band members and translate common roles."""
import csv
import json
import time
from datetime import date
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "billboard_band_members.csv"
CACHE = ROOT / "band_member_ages_cache.json"
ROLES = {"lead vocals":"lead-zang","background vocals":"achtergrondzang","vocals":"zang","guitar":"gitaar","bass":"basgitaar","drums (drum set)":"drums","drums":"drums","keyboards":"toetsen","original":"","piano":"piano"}
HEADERS = {"User-Agent":"BillboardReverseMetadata/1.0 (https://github.com/seppegoossens99-eng/billboard-hot-100-reversed)"}

def age(value):
    if not isinstance(value, str):
        return ""
    try:
        born = date.fromisoformat(value)
        today = date.today()
        return str(today.year-born.year-((today.month,today.day)<(born.month,born.day)))
    except ValueError:
        return ""

def main():
    with PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    session = requests.Session()
    session.headers.update(HEADERS)
    updated = 0
    for row in rows:
        roles = [ROLES.get(x.strip().casefold(), x.strip()) for x in row["Functie/instrument"].split(",")]
        row["Functie/instrument"] = ", ".join(x for x in roles if x) or "Niet vermeld"
        row["Leeftijd lid"] = ""
        row["Bron lid"] = ""
        if not row["Lid"] or not row["Bron"].startswith("https://musicbrainz.org/artist/"):
            continue
        group_id = row["Bron"].rsplit("/",1)[-1]
        key = group_id + "|" + row["Lid"]
        info = cache.get(key)
        if info is None:
            # Match member against group relations by exact credited name.
            group_cache = json.loads((ROOT / "band_members_cache.json").read_text(encoding="utf-8"))
            group = group_cache.get(group_id, {}).get("data", {})
            matches = [rel.get("artist", {}) for rel in group.get("relations", [])
                       if rel.get("type")=="member of band" and rel.get("artist",{}).get("name")==row["Lid"]]
            ids = set(x.get("id") for x in matches if x.get("id"))
            info = {"id":next(iter(ids))} if len(ids)==1 else {}
            if info.get("id"):
                try:
                    response=session.get("https://musicbrainz.org/ws/2/artist/"+info["id"],params={"fmt":"json"},timeout=20)
                    response.raise_for_status()
                    info["birth"]=(response.json().get("life-span") or {}).get("begin")
                except (requests.RequestException,ValueError) as exc:
                    print("Member lookup unavailable:",exc,flush=True)
                time.sleep(1.1)
            cache[key]=info
        row["Leeftijd lid"] = age(info.get("birth"))
        if row["Leeftijd lid"]:
            row["Bron lid"] = "https://musicbrainz.org/artist/"+info["id"]
            updated+=1
    fields = list(rows[0].keys()) if rows else ["Artiest","Band","Leden (bevestigd huidig)","Volledigheid","Lid","Functie/instrument","Status","Bron","Leeftijd lid","Bron lid"]
    for field in ("Leeftijd lid","Bron lid"):
        if field not in fields:
            fields.append(field)
    with PATH.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    CACHE.write_text(json.dumps(cache,ensure_ascii=False),encoding="utf-8")
    print("Verified member ages:",updated,flush=True)

if __name__=="__main__":
    main()
