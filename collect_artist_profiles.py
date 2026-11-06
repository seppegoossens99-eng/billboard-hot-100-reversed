"""Artist portraits (Wikidata/Commons) and ages (MusicBrainz), no guessed identities."""
import csv
import json
import os
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

def spotify_id(data):
    """Only trust Spotify IDs linked to the verified MusicBrainz artist."""
    for rel in data.get("relations", []):
        url = (rel.get("url") or {}).get("resource", "")
        if "open.spotify.com/artist/" in url:
            identifier = url.split("/artist/", 1)[1].split("?", 1)[0].strip("/")
            if len(identifier) == 22 and identifier.isalnum():
                return identifier
    return ""

# Artist IDs cross-checked against the corresponding public Spotify profiles
# and independent artist biographies; do not use name-only fuzzy matches.
VERIFIED_SPOTIFY_IDS = {
    "John Morgan": "7FetIwKD9uIJFiUwdHfq6g",
    "Blake Whiten": "1BjlNhp6EsDG0UMroeJbRM",
    "Rockwell": "3xs0LEzcPXtgNfMNcHzLIP",
    "Alyssa Grace": "4eZer1QvRM8Pna0rLToV1K",
    "Thekidszn": "138UAIyJocdHT5PpR0iTJE",
    "comehelpglo": "5Z9nWuFMEQ97O7ixur2c8l",
    "Yebba": "1ooV8YZC1KbpEcrmI8WH0F",
}

# Exact birth dates corroborated by independent artist biographies.
VERIFIED_BIRTHDATES = {
    "Greylan James": ("1996-06-18", "https://www.allmusic.com/artist/greylan-james-mn0002828742"),
    "Zach John King": ("1997-03-25", "https://en.wikipedia.org/wiki/Zach_John_King"),
}

def spotify_token():
    client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
    secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    if not client_id or not secret:
        return ""
    try:
        response = requests.post("https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, secret), timeout=20)
        response.raise_for_status()
        return response.json().get("access_token", "")
    except (requests.RequestException, ValueError) as exc:
        print(f"Spotify photo token unavailable: {exc}", flush=True)
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
    spotify_ids = dict(VERIFIED_SPOTIFY_IDS)
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
        sid = spotify_id(data)
        if sid:
            spotify_ids[name] = sid
        if artist_id and qid:
            print(f"Verified Wikidata link: {name} -> {qid}", flush=True)
        if qid:
            qids.add(qid)
        birth = (data.get("life-span") or {}).get("begin", "") if data.get("type") == "Person" else ""
        kind = data.get("type", "")
        if name in VERIFIED_BIRTHDATES and not age_at(birth):
            birth = VERIFIED_BIRTHDATES[name][0]
            kind = "Person"
        entries.append((name, kind, birth, age_at(birth), qid, source))
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
    print(f"Wikidata portraits: {len(images)}, Wikipedia fallback portraits: {len(wikipedia_images)}", flush=True)
    spotify_images = {}
    token = spotify_token() if spotify_ids else ""
    if token:
        for name, sid in spotify_ids.items():
            try:
                response = requests.get("https://api.spotify.com/v1/artists/" + sid,
                    headers={"Authorization": "Bearer " + token}, timeout=15)
                response.raise_for_status()
                artist = response.json()
                if artist.get("id") == sid and artist.get("images"):
                    url = artist["images"][0].get("url", "")
                    if url.startswith("https://"):
                        spotify_images[name] = (url, "https://open.spotify.com/artist/" + sid)
            except (requests.RequestException, ValueError) as exc:
                print(f"Spotify artist photo unavailable for {name}: {exc}", flush=True)
    # For artist identities confirmed by independent editorial/label sources,
    # resolve a Spotify portrait only if the exact artist name is unique.
    editorial_sources = (
        "https://www.allmusic.com/artist/",
        "https://press.warnerrecords.com/",
        "https://www.missinglinkmusic.com/",
        "https://www.opry.com/artists/",
    )
    if token:
        for name, source in sorted(unique):
            if name in spotify_images or not source.startswith(editorial_sources):
                continue
            try:
                response = requests.get("https://api.spotify.com/v1/search",
                    params={"q": 'artist:"' + name + '"', "type": "artist", "limit": 50},
                    headers={"Authorization": "Bearer " + token}, timeout=20)
                response.raise_for_status()
                candidates = response.json().get("artists", {}).get("items", [])
                exact = [a for a in candidates if a.get("name", "").casefold() == name.casefold()]
                if len(exact) == 1 and exact[0].get("images"):
                    artist = exact[0]
                    url = artist["images"][0].get("url", "")
                    sid = artist.get("id", "")
                    if url.startswith("https://") and len(sid) == 22 and sid.isalnum():
                        spotify_images[name] = (url, "https://open.spotify.com/artist/" + sid)
                        print(f"Unique exact Spotify artist match: {name}", flush=True)
                else:
                    print(f"Ambiguous or missing Spotify artist search: {name} ({len(exact)} exact)", flush=True)
            except (requests.RequestException, ValueError) as exc:
                print(f"Spotify search unavailable for {name}: {exc}", flush=True)
    # Resolve Rockwell through the verified 1984 recording, not a potentially
    # ambiguous artist-name search. Spotify's track artist ID is authoritative.
    if token and "Rockwell" not in spotify_images:
        try:
            response = requests.get("https://api.spotify.com/v1/tracks/2gGdO0zLa9W8ce1Ig0BzFK",
                headers={"Authorization": "Bearer " + token}, timeout=20)
            response.raise_for_status()
            track = response.json()
            if track.get("name", "").casefold().startswith("somebody's watching me"):
                matches = [a for a in track.get("artists", [])
                           if a.get("name", "").casefold() == "rockwell"]
                if len(matches) == 1:
                    sid = matches[0]["id"]
                    detail = requests.get("https://api.spotify.com/v1/artists/" + sid,
                        headers={"Authorization": "Bearer " + token}, timeout=20)
                    detail.raise_for_status()
                    artist = detail.json()
                    if artist.get("id") == sid and artist.get("images"):
                        url = artist["images"][0].get("url", "")
                        if url.startswith("https://"):
                            spotify_images["Rockwell"] = (
                                url, "https://open.spotify.com/artist/" + sid)
                            spotify_ids["Rockwell"] = sid
                            print("Verified Rockwell portrait through Somebody's Watching Me", flush=True)
        except (requests.RequestException, ValueError, KeyError) as exc:
            print(f"Rockwell recording match unavailable: {exc}", flush=True)
    # Resolve missing portraits through an exact Billboard song+artist match.
    chart_songs = {}
    for row in artists:
        chart_songs.setdefault(row["Artiest"], set()).add(row["Nummer"])
    if token:
        for name in ("Alyssa Grace", "Thekidszn", "Yebba", "comehelpglo"):
            if name in spotify_images:
                continue
            for title in sorted(chart_songs.get(name, ())):
                try:
                    response = requests.get("https://api.spotify.com/v1/search",
                        params={"q": 'track:"' + title + '" artist:"' + name + '"',
                                "type": "track", "limit": 20},
                        headers={"Authorization": "Bearer " + token}, timeout=20)
                    response.raise_for_status()
                    tracks = response.json().get("tracks", {}).get("items", [])
                    matched = {
                        artist.get("id")
                        for track in tracks
                        if track.get("name", "").casefold() == title.casefold()
                        for artist in track.get("artists", [])
                        if artist.get("name", "").casefold() == name.casefold()
                        and artist.get("id")
                    }
                    if len(matched) != 1:
                        continue
                    sid = matched.pop()
                    detail = requests.get("https://api.spotify.com/v1/artists/" + sid,
                        headers={"Authorization": "Bearer " + token}, timeout=20)
                    detail.raise_for_status()
                    profile = detail.json()
                    if profile.get("id") == sid and profile.get("images"):
                        url = profile["images"][0].get("url", "")
                        if url.startswith("https://"):
                            spotify_images[name] = (
                                url, "https://open.spotify.com/artist/" + sid)
                            spotify_ids[name] = sid
                            print(f"Verified track-to-artist portrait: {title} / {name}", flush=True)
                            break
                except (requests.RequestException, ValueError) as exc:
                    print(f"Spotify chart track match unavailable for {name}: {exc}", flush=True)
    # Spotify's public oEmbed metadata can provide a thumbnail when the
    # authenticated artist endpoint omits images. Use verified artist IDs only.
    for name, sid in spotify_ids.items():
        if name in spotify_images:
            continue
        try:
            response = requests.get("https://open.spotify.com/oembed",
                params={"url": "https://open.spotify.com/artist/" + sid},
                headers=HEADERS, timeout=15)
            response.raise_for_status()
            metadata = response.json()
            thumbnail = metadata.get("thumbnail_url", "")
            if (metadata.get("type") == "rich"
                    and metadata.get("title", "").casefold() == name.casefold()
                    and thumbnail.startswith("https://")):
                spotify_images[name] = (
                    thumbnail, "https://open.spotify.com/artist/" + sid)
                print(f"Verified Spotify oEmbed thumbnail: {name}", flush=True)
        except (requests.RequestException, ValueError) as exc:
            print(f"Spotify oEmbed unavailable for {name}: {exc}", flush=True)
    print(f"Spotify verified artist portraits: {len(spotify_images)}", flush=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(FIELDS)
        for name, kind, birth, age, qid, source in entries:
            prior = previous.get(name, {})
            prior_source = prior.get("Bron afbeelding", "")
            wikidata_match = bool(qid and prior_source == "https://www.wikidata.org/wiki/" + qid)
            spotify_match = bool(name in spotify_ids and prior_source ==
                "https://open.spotify.com/artist/" + spotify_ids[name])
            wikipedia_match = bool(qid and qid in wikipedia_pages and prior_source == (
                "https://en.wikipedia.org/wiki/" + quote(wikipedia_pages[qid].replace(" ", "_"), safe="()_")))
            photo = images.get(qid, "") or wikipedia_images.get(qid, "") or spotify_images.get(name, ("", ""))[0] or (
                prior.get("Afbeelding", "") if wikidata_match or wikipedia_match or spotify_match else "")
            photo_source = ("https://www.wikidata.org/wiki/" + qid if images.get(qid) else ("https://en.wikipedia.org/wiki/" + quote(wikipedia_pages[qid].replace(" ", "_"), safe="()_") if wikipedia_images.get(qid) else (spotify_images[name][1] if name in spotify_images else (prior.get("Bron afbeelding", "") if photo else ""))))
            age_source = (VERIFIED_BIRTHDATES[name][1] if name in VERIFIED_BIRTHDATES and birth == VERIFIED_BIRTHDATES[name][0] else source) if age else ""
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
