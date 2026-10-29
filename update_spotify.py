import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth

SOURCE = "https://raw.githubusercontent.com/mhollingshead/billboard-hot-100/main/recent.json"
SCOPES = "playlist-modify-private playlist-modify-public playlist-read-private"

def secret(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError("Missing GitHub secret: " + name)
    return value

def normalize(text):
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()

def main():
    if os.getenv("GITHUB_EVENT_NAME") == "schedule":
        local = datetime.now(ZoneInfo("Europe/Brussels"))
        if local.weekday() != 2 or local.hour != 12:
            print("Not Wednesday at 12:00 Belgian time; skipping.")
            return

    response = requests.get(SOURCE, timeout=40)
    response.raise_for_status()
    chart = response.json()
    songs = chart.get("data", [])
    positions = [item.get("this_week") for item in songs]
    if len(songs) != 100 or sorted(positions) != list(range(1, 101)):
        raise RuntimeError("Invalid chart positions; playlist unchanged.")
    print("Billboard chart date:", chart.get("date"))

    oauth = SpotifyOAuth(
        client_id=secret("SPOTIFY_CLIENT_ID"),
        client_secret=secret("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"),
        scope=SCOPES,
        open_browser=False,
        cache_path=None,
    )
    access = oauth.refresh_access_token(secret("SPOTIFY_REFRESH_TOKEN"))["access_token"]
    spotify = spotipy.Spotify(auth=access, requests_timeout=30, retries=3)
    playlist_id = secret("SPOTIFY_PLAYLIST_ID")

    ids = []
    missing = []
    for song in sorted(songs, key=lambda x: x["this_week"], reverse=True):
        title, artist = song["song"], song["artist"]
        lead_artist = re.split(r" Featuring | feat\.? | ft\.? | & |, ", artist, maxsplit=1, flags=re.I)[0]
        queries = [
            f'track:"{title}" artist:"{lead_artist}"',
            f"{title} {artist}",
        ]
        chosen = None
        for query in queries:
            results = spotify.search(q=query, type="track", limit=10)["tracks"]["items"]
            title_norm = normalize(title)
            artist_norm = normalize(lead_artist)
            for item in results:
                found_title = normalize(item["name"])
                found_artists = " ".join(normalize(a["name"]) for a in item["artists"])
                if (found_title == title_norm or found_title.startswith(title_norm + " ")) and artist_norm in found_artists:
                    chosen = item["id"]
                    break
            if chosen:
                break
        if chosen and chosen not in ids:
            ids.append(chosen)
        else:
            missing.append(f'{song["this_week"]}: {artist} - {title}')

    print("Matched:", len(ids), "Unmatched/duplicate:", len(missing))
    for item in missing:
        print("UNMATCHED:", item)
    if len(ids) < 95:
        raise RuntimeError("Fewer than 95 matches; playlist unchanged.")
    spotify.playlist_replace_items(playlist_id, ids)
    print("Playlist updated, reversed positions 100 to 1.")

if __name__ == "__main__":
    main()
