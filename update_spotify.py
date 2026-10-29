import os
from datetime import datetime
from zoneinfo import ZoneInfo

import spotipy
from spotipy.oauth2 import SpotifyOAuth

SOURCE_PLAYLIST_ID = "6UeSakyzhiEt4NB3UAd6NQ"
SCOPES = "playlist-modify-private playlist-modify-public playlist-read-private"

def secret(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError("Missing GitHub secret: " + name)
    return value

def main():
    if os.getenv("GITHUB_EVENT_NAME") == "schedule":
        local = datetime.now(ZoneInfo("Europe/Brussels"))
        if local.weekday() != 2 or local.hour != 12:
            print("Not Wednesday at noon in Belgium; skipping.")
            return

    oauth = SpotifyOAuth(
        client_id=secret("SPOTIFY_CLIENT_ID"),
        client_secret=secret("SPOTIFY_CLIENT_SECRET"),
        redirect_uri="http://127.0.0.1:8888/callback",
        scope=SCOPES,
        open_browser=False,
        cache_path=None,
    )
    token = oauth.refresh_access_token(secret("SPOTIFY_REFRESH_TOKEN"))["access_token"]
    spotify = spotipy.Spotify(auth=token, requests_timeout=30, retries=3)

    target_id = secret("SPOTIFY_PLAYLIST_ID")
    if target_id == SOURCE_PLAYLIST_ID:
        raise RuntimeError("Source and destination playlists must be different.")

    source = spotify.playlist(SOURCE_PLAYLIST_ID, fields="id,name,items(total)")
    print("Source:", source["name"], "Total:", source["items"]["total"])
    if source["tracks"]["total"] != 100:
        raise RuntimeError("Source playlist does not contain exactly 100 entries; destination unchanged.")

    tracks = []
    offset = 0
    while True:
        page = spotify.playlist_items(
            SOURCE_PLAYLIST_ID,
            offset=offset,
            limit=100,
            fields="items(track(id,type,is_local)),next,total",
            additional_types=("track",),
        )
        for entry in page["items"]:
            track = entry.get("track")
            if not track or track.get("type") != "track" or track.get("is_local") or not track.get("id"):
                raise RuntimeError("Source contains unavailable/non-track item; destination unchanged.")
            tracks.append(track["id"])
        if not page.get("next"):
            break
        offset += len(page["items"])

    if len(tracks) != 100 or len(set(tracks)) != 100:
        raise RuntimeError("Expected exactly 100 unique playable track IDs; destination unchanged.")

    reversed_tracks = list(reversed(tracks))
    spotify.playlist_replace_items(target_id, reversed_tracks)
    print("Successfully updated destination with 100 tracks, positions 100 through 1.")

if __name__ == "__main__":
    main()
