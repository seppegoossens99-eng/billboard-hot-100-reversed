import os
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth

CHART_URL = "https://raw.githubusercontent.com/mhollingshead/billboard-hot-100/main/recent.json"
API = "https://api.spotify.com/v1"
SCOPES = "playlist-modify-public playlist-modify-private playlist-read-private"

# Verified Spotify tracks. Used only if the chart artist + title match.
# These songs were not found by the basic Spotify search in the first run.
OVERRIDES = {
    ("karol g", "ahi"): "6DoUDG1GJrJf6eGQLUBBnm",
    ("beyonce", "morning dew donk"): "4ZYlzwjjAJrflwWg4DJTlT",
    ("boa", "duvet"): "7urtwZEtOypb3r8HNi42dT",
    ("shakira", "dai dai fifa world cup official song 2026"): "0kosUz0jePvjiz4ctmR6wL",
    ("stella lefty", "something to lose"): "78lR1li9wdwunwNoVYiBpE",
    ("jhene aiko", "so good"): "3Yd3J42s3GZaYty4Iy4ewT",
    ("adela", "ain t in la"): "02HyFYmpzt02VJ8k0CqxKj",
    ("karol g", "bby wow"): "3h5T5JypYU7huFiVYhv1dr",
    ("adela", "nicole kidman"): "70cHKK8bHAfJrOGVnfRG9J",
}

def need_env(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError("Missing GitHub secret: " + name)
    return value

def normalize(s):
    s = unicodedata.normalize("NFKD", s.casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

def main_artist(artist):
    return re.split(r"\s+(?:featuring|feat\.?|ft\.?|with|x)\s+|\s*&\s*|,", artist, 1, re.I)[0].strip()

def query_variants(song, artist):
    title_without_suffix = re.sub(r"\s*\([^)]*\)", "", song).strip()
    variants = [
        f'track:"{song}" artist:"{main_artist(artist)}"',
        f"{song} {main_artist(artist)}",
        f"{title_without_suffix} {main_artist(artist)}",
        f"{song} {artist}",
    ]
    return list(dict.fromkeys(v for v in variants if v.strip()))

def find_spotify_track(spotify, title, artist):
    main = normalize(main_artist(artist))
    wanted = normalize(title)
    short_title = normalize(re.sub(r"\s*\([^)]*\)", "", title))
    best = None
    best_score = -1
    for query in query_variants(title, artist):
        found = spotify.search(q=query, type="track", limit=10)["tracks"]["items"]
        for track in found:
            candidate = normalize(track["name"])
            artist_names = [normalize(a["name"]) for a in track["artists"]]
            if main not in artist_names:
                continue
            if candidate == wanted:
                score = 100
            elif candidate == short_title:
                score = 95
            elif candidate.startswith(wanted + " "):
                score = 85
            elif candidate.startswith(short_title + " "):
                score = 80
            else:
                continue
            if score > best_score:
                best, best_score = track["id"], score
        if best_score == 100:
            break
    return best

def main():
    if os.getenv("GITHUB_EVENT_NAME") == "schedule":
        now = datetime.now(ZoneInfo("Europe/Brussels"))
        if now.weekday() != 2 or now.hour != 12:
            print("Outside Wednesday 12:00 Belgium schedule. Skipping.")
            return

    chart_response = requests.get(CHART_URL, timeout=40)
    chart_response.raise_for_status()
    chart = chart_response.json()
    songs = chart.get("data", [])
    positions = [s.get("this_week") for s in songs]
    if len(songs) != 100 or sorted(positions) != list(range(1, 101)):
        raise RuntimeError("Chart is not a complete 1-100 ranking. Playlist unchanged.")
    print("Billboard chart date:", chart.get("date"))

    oauth = SpotifyOAuth(
        client_id=need_env("SPOTIFY_CLIENT_ID"),
        client_secret=need_env("SPOTIFY_CLIENT_SECRET"),
        redirect_uri="http://127.0.0.1:8888/callback",
        scope=SCOPES,
        open_browser=False,
        cache_path=None,
    )
    access_token = oauth.refresh_access_token(need_env("SPOTIFY_REFRESH_TOKEN"))["access_token"]
    spotify = spotipy.Spotify(auth=access_token, requests_timeout=30, retries=3)
    target = need_env("SPOTIFY_PLAYLIST_ID")

    result_ids = []
    unresolved = []
    for s in sorted(songs, key=lambda x: x["this_week"], reverse=True):
        title, artist, pos = s["song"], s["artist"], s["this_week"]
        key = (normalize(main_artist(artist)), normalize(title))
        track_id = OVERRIDES.get(key)
        if not track_id:
            track_id = find_spotify_track(spotify, title, artist)
        if track_id and track_id not in result_ids:
            result_ids.append(track_id)
        else:
            unresolved.append(f"{pos}: {artist} - {title}")

    print(f"Matched: {len(result_ids)}/100. Missing or duplicates: {len(unresolved)}")
    for entry in unresolved:
        print("UNMATCHED:", entry)

    # Never delete or replace the existing playlist with an incomplete chart.
    if len(result_ids) != 100:
        raise RuntimeError("Expected 100 unique matched tracks. Playlist left unchanged.")

    # The February 2026 Spotify API uses PUT /items, not the old PUT /tracks.
    uris = [f"spotify:track:{track_id}" for track_id in result_ids]
    reply = requests.put(
        f"{API}/playlists/{target}/items",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"uris": uris},
        timeout=60,
    )
    reply.raise_for_status()
    print("SUCCESS: 100 songs written in reverse chart order (#100 first, #1 last).")

if __name__ == "__main__":
    main()
