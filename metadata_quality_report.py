"""Weekly quality report for the 100 Billboard songs and credited artists."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def read(name):
    with (ROOT / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def main():
    songs = read("billboard_hot_100_details.csv")
    artists = read("billboard_hot_100_artists.csv")
    profiles = {r["Artiest"]:r for r in read("billboard_artist_profiles.csv")}
    bands = read("billboard_band_members.csv")
    unique = sorted(set(r["Artiest"] for r in artists))
    # Fictional soundtrack ensembles have no real-world hometown and may have
    # no representative artist portrait. Report them separately, not as errors.
    NON_APPLICABLE = {"The Citizens of Halloween"}
    not_applicable = sorted(name for name in unique if name in NON_APPLICABLE)
    missing_photo = [name for name in unique if name not in NON_APPLICABLE and not profiles.get(name,{}).get("Afbeelding")]
    missing_identity = [name for name in unique if not any(r["Bron herkomst"].startswith(("https://musicbrainz.org/artist/", "https://www.opry.com/artists/", "https://www.allmusic.com/artist/", "https://press.warnerrecords.com/", "https://www.missinglinkmusic.com/", "https://www.famousbirthdays.com/people/", "https://www.power1061.com/lsp/artist/bio/", "https://music.apple.com/us/artist/")) for r in artists if r["Artiest"] == name)]
    missing_age = [name for name in unique if profiles.get(name,{}).get("Type")=="Person" and not profiles[name].get("Leeftijd")]
    confirmed_birth = [name for name in unique if profiles.get(name, {}).get("Type") == "Person" and len(profiles[name].get("Geboortedatum", "")) == 10]
    missing_birth_source = [name for name in confirmed_birth if not profiles[name].get("Bron leeftijd", "").startswith("https://")]
    # A reported age or birth year is useful but not an exact verified date.
    partial_birth_info = {
        "Belly Gang Kushington": "Verjaardag 4 februari (Famous Birthdays); 35 jaar gemeld in juli 2026 (XXL); geboortejaar onbevestigd",
        "Mack Geiger": "21 jaar gemeld op artiestenwebsite (datum van vermelding niet vastgelegd)",
        "rusowsky": "Geboortejaar 1999 gemeld; dag en maand onbekend",
    }
    partial_birth = [f"{name}: {partial_birth_info[name]}" for name in missing_age if name in partial_birth_info]
    no_birth_info = [name for name in missing_age if name not in partial_birth_info]
    missing_origin = [name for name in unique if name not in NON_APPLICABLE and not any(r["Land"] for r in artists if r["Artiest"]==name)]
    missing_dates = [f'#{r["Billboard-positie"]} {r["Artiest"]} - {r["Nummer"]}' for r in songs if not r["Eerste officiële releasedatum"]]
    # A populated date is not automatically proof of the earliest official
    # release. Make provenance gaps explicit rather than claiming completeness.
    missing_release_sources = [
        f'#{r["Billboard-positie"]} {r["Artiest"]} - {r["Nummer"]}'
        for r in songs if r["Eerste officiële releasedatum"] and not r.get("Bron releasedatum", "").startswith("https://")
    ]
    provisional_release_dates = [
        f'#{r["Billboard-positie"]} {r["Artiest"]} - {r["Nummer"]}'
        for r in songs if r["Eerste officiële releasedatum"]
    ]
    undocumented = sorted(set(r["Artiest"] for r in bands if not r["Lid"]))
    lines = [
        "# Billboard Hot 100 — controle ontbrekende gegevens",
        "",
        "Dit overzicht wordt automatisch vernieuwd bij een website-update.",
        "Een ingevulde releasedatum blijft voorlopig totdat de eerste officiële uitgave is geverifieerd.",
        "",
        f"- Nummers: {len(songs)}",
        f"- Unieke vermelde artiesten: {len(unique)}",
        f"- Artiesten zonder foto: {len(missing_photo)}",
        f"- Artiesten zonder gedocumenteerde identiteit: {len(missing_identity)}",
        f"- Soloartiesten met ingevulde volledige geboortedatum: {len(confirmed_birth)}",
        f"- Volledige geboortedata zonder bronlink: {len(missing_birth_source)}",
        f"- Soloartiesten zonder bevestigde leeftijd: {len(missing_age)}",
        f"- Daarvan met gedeeltelijke geboorte- of leeftijdsinformatie: {len(partial_birth)}",
        f"- Zonder bruikbare geboorte- of leeftijdsinformatie: {len(no_birth_info)}",
        f"- Artiesten zonder land: {len(missing_origin)}",
        f"- Nummers zonder voorlopige releasedatum: {len(missing_dates)}",
        f"- Voorlopige releasedata nog niet als eerste officiële uitgave bevestigd: {len(provisional_release_dates)}",
        f"- Ingevulde releasedata zonder bronlink: {len(missing_release_sources)}",
        f"- Soundtrackensembles met niet-toepasselijke foto/herkomst: {len(not_applicable)}",
    ]
    for heading, values in [
        ("Ontbrekende foto's",missing_photo),
        ("Ontbrekende leeftijden",missing_age),
        ("Volledige geboortedata zonder bronlink",missing_birth_source),
        ("Gedeeltelijke leeftijdsinformatie (geen exacte geboortedatum)",partial_birth),
        ("Zonder geboorte- of leeftijdsinformatie",no_birth_info),
        ("Artiesten zonder gedocumenteerde identiteit",missing_identity),
        ("Ontbrekende landen",missing_origin),
        ("Ontbrekende releasedata",missing_dates),
        ("Ingevulde releasedata zonder bronlink",missing_release_sources),
        ("Bands zonder gedocumenteerde leden",undocumented),
        ("Niet van toepassing: fictieve soundtrackensembles",not_applicable)
    ]:
        lines += ["", "## "+heading, ""] + (["- "+v for v in values] if values else ["Geen."])
    (ROOT/"metadata_quality_report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("Quality report generated; missing photos:",len(missing_photo))

if __name__=="__main__":
    main()
