import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import billboard
import spotipy
from spotipy.oauth2 import SpotifyOAuth

PLAYLIST_NAME = "Billboard Hot 100 Reversed"
SCOPES = "playlist-modify-private playlist-modify-public playlist-read-private"
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

def required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing GitHub secret: {name}")
    return value

def main():
    # Scheduled runs execute at 10:00 and 11:00 UTC to cover both DST offsets.
    if os.getenv("GITHUB_EVENT_NAME") == "schedule":
        local = datetime.now(ZoneInfo("Europe/Brussels"))
        if local.weekday() != 2 or local.hour != 12:
            print("Not Wednesday noon in Belgium; skipping.")
            return

    client_id = required("SPOTIFY_CLIENT_ID")
    client_secret = required("SPOTIFY_CLIENT_SECRET")
    refresh_token = required("SPOTIFY_REFRESH_TOKEN")
    playlist_id = required("SPOTIFY_PLAYLIST_ID")

    chart = billboard.ChartData("hot-100")
    entries = list(chart)
    if len(entries) != 100:
        raise RuntimeError(f"Expected 100 Billboard entries, received {len(entries)}. Playlist unchanged.")

    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=REDIRECT_URI,
        scope=SCOPES,
        open_browser=False,
        cache_path=None,
    )
    token = auth.refresh_access_token(refresh_token)["access_token"]
    spotify = spotipy.Spotify(auth=token, requests_timeout=30, retries=3)

    track_ids = []
    missing = []
    for entry in reversed(entries):
        title = entry.title
        artist = entry.artist
        clean_title = re.sub(r"\s*\([^)]*(feat|ft\.|with)[^)]*\)", "", title, flags=re.I)
        queries = [
            f'track:"{title}" artist:"{artist.split(" Featuring ")[0].split(" & ")[0]}"',
            f"{clean_title} {artist}",
        ]
        found = None
        for query in queries:
            result = spotify.search(q=query, type="track", limit=10)
            candidates = result.get("tracks", {}).get("items", [])
            if candidates:
                found = candidates[0]["id"]
                break
        if found and found not in track_ids:
            track_ids.append(found)
        elif not found:
            missing.append(f"{entry.rank}: {artist} - {title}")

    print(f"Chart date: {chart.date}; matched: {len(track_ids)}; missing: {len(missing)}")
    if missing:
        print("Missing tracks:\n" + "\n".join(missing))
    if len(track_ids) < 90:
        raise RuntimeError("Too few Spotify matches. Playlist unchanged.")

    # Spotify replace endpoint accepts at most 100 IDs.
    spotify.playlist_replace_items(playlist_id, track_ids)
    print(f"Updated {PLAYLIST_NAME} with {len(track_ids)} songs, in 100-to-1 order.")

if __name__ == "__main__":
    main()
