"""Build a standalone, mobile-friendly HTML view of the Billboard CSV files."""
import csv
import html
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def read_csv(filename):
    with (ROOT / filename).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def safe_url(url):
    return html.escape(url, quote=True) if url.startswith("https://musicbrainz.org/") else ""

def main():
    tracks = read_csv("billboard_hot_100_details.csv")
    artists = read_csv("billboard_hot_100_artists.csv")
    if len(tracks) != 100 or [int(x["Billboard-positie"]) for x in tracks] != list(range(100, 0, -1)):
        raise RuntimeError("Invalid chart order; HTML unchanged.")
    grouped = defaultdict(list)
    for artist in artists:
        grouped[(artist["Billboard-positie"], artist["Nummer"])].append(artist)
    blocks = []
    for track in tracks:
        pos = track["Billboard-positie"]
        name = track["Nummer"]
        credited = grouped[(pos, name)]
        people = []
        for person in credited:
            place = ", ".join(p for p in (person["Stad"], person["Staat/regio"], person["Land"]) if p)
            origin = html.escape(place or "Herkomst onbekend")
            source = safe_url(person["Bron herkomst"])
            source_link = f' <a href="{source}" target="_blank" rel="noopener">Bron</a>' if source else ""
            people.append(f'<li><strong>{html.escape(person["Artiest"])}</strong><span>{origin}{source_link}</span></li>')
        date = track["Eerste officiële releasedatum"]
        date_display = html.escape(date) if date else "Nog niet gevonden"
        date_source = safe_url(track["Bron releasedatum"])
        date_link = f'<a href="{date_source}" target="_blank" rel="noopener">MusicBrainz-bron</a>' if date_source else ""
        status = "Voorlopige datum" if date else "Datum onbekend"
        search = html.escape((pos + " " + name + " " + track["Artiest"] + " " + " ".join(p["Artiest"] for p in credited)).casefold(), quote=True)
        blocks.append(f"""
        <article class="song" data-search="{search}">
          <div class="heading"><span class="rank">#{pos}</span><div><h2>{html.escape(name)}</h2><p class="credit">{html.escape(track["Artiest"])}</p></div></div>
          <div class="info"><div><div class="label">Releasedatum</div><strong>{date_display}</strong><small>{status} · {date_link}</small></div>
          <div><div class="label">Herkomst per artiest</div><ul>{''.join(people)}</ul></div></div>
        </article>""")
    document = """<!doctype html><html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Billboard Hot 100 · Reversed</title>
<style>
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#f2f4f8;background:#0c101b}
*{box-sizing:border-box}body{margin:0}main{max-width:1050px;margin:auto;padding:24px 16px 70px}
header{padding:28px 0 18px}h1{font-size:clamp(30px,6vw,48px);letter-spacing:-.045em;margin:0}
.sub{color:#b4bfd1;line-height:1.55}.pill{display:inline-block;color:#d4e5ff;background:#243c63;border-radius:30px;padding:6px 12px;font-size:13px}
input{width:100%;font:inherit;padding:15px 17px;border:1px solid #4a566e;border-radius:12px;background:#182235;color:white;margin:18px 0 10px}
#count{color:#aab9cc;font-size:14px;margin:0 0 15px}.songs{display:grid;gap:12px}
.song{border:1px solid #29354a;border-radius:17px;background:#151d2c;padding:18px}
.heading{display:flex;gap:14px;align-items:start}.rank{flex:none;font-weight:800;color:#9dc3ff;background:#263a59;border-radius:9px;padding:8px 10px}
h2{font-size:19px;margin:2px 0 5px;line-height:1.2}.credit{margin:0;color:#b9c7d8}
.info{display:grid;grid-template-columns:minmax(150px,1fr) minmax(0,2fr);gap:18px;margin-top:16px;border-top:1px solid #2b3648;padding-top:14px}
.label{font-size:12px;text-transform:uppercase;letter-spacing:.09em;color:#91a2b8;margin-bottom:8px}
small{display:block;color:#aab9cc;margin-top:5px}ul{list-style:none;padding:0;margin:0}li{display:flex;flex-wrap:wrap;gap:5px 12px;margin-bottom:9px}li span{color:#b5c6d8}
a{color:#99c4ff;text-decoration:none}a:hover{text-decoration:underline}
.note{background:#222c3f;padding:14px;border-radius:12px;color:#c9d3e2;font-size:14px;line-height:1.5}
@media(max-width:620px){main{padding:18px 12px 55px}.song{padding:15px}.info{grid-template-columns:1fr;gap:15px}h2{font-size:18px}}
</style></head><body><main><header><span class="pill">#100 → #1</span>
<h1>Billboard Hot 100</h1><p class="sub">Reversed · artiesten, steden, staten en releasedata</p>
<div class="note">De releasedata zijn voorlopig: MusicBrainz geeft de vroegste daar bekende opname-uitgave, maar bevestigt niet altijd de eerste officiële single-release. Lege gegevens worden niet gegokt. De herkomst van een groep kan de oprichtingsplaats zijn.</div>
</header><label for="search">Zoek artiest, nummer of positie</label><input id="search" type="search" placeholder="Bijv. Drake, Olivia Rodrigo, #88">
<p id="count">100 nummers</p><section class="songs" id="songs">
""" + "\n".join(blocks) + """</section></main>
<script>
const input=document.getElementById('search'),songs=[...document.querySelectorAll('.song')],count=document.getElementById('count');
input.addEventListener('input',()=>{const q=input.value.trim().toLocaleLowerCase();let visible=0;
for(const song of songs){const show=song.dataset.search.includes(q);song.hidden=!show;if(show)visible++;}
count.textContent=visible+' van '+songs.length+' nummers';});
</script></body></html>"""
    (ROOT / "billboard_hot_100.html").write_text(document, encoding="utf-8")
    print("Created billboard_hot_100.html with",len(tracks),"songs and",len(artists),"artist credits")

if __name__ == "__main__":
    main()
