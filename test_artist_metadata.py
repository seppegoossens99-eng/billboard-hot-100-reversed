import contextlib
import csv
import io
import json
import sys
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from artist_identities import VERIFIED_ARTIST_IDS
from collect_band_members import memberships
from enrich_band_members import age
from build_mobile_page import render_band_members
import collect_artist_profiles as profiles

class MetadataRegressionTests(unittest.TestCase):
    def test_ambiguous_artist_never_reuses_namesake_profile(self):
        cache = {}
        for name, identifier in VERIFIED_ARTIST_IDS.items():
            cache[identifier] = {'data': {'id':identifier, 'type':'Person' if name=='Steve Lacy' else 'Group', 'life-span':{'begin':'1998-05-23' if name=='Steve Lacy' else '1993'}, 'relations':[{'type':'wikidata','url':{'resource':'https://www.wikidata.org/wiki/Q56733980'}}]}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'band_members_cache.json').write_text(json.dumps(cache),encoding='utf-8')
            with (root/'billboard_hot_100_artists.csv').open('w',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=['Artiest','Bron herkomst','Nummer'])
                writer.writeheader()
                for name in ('Steve Lacy','boa','Justice'):
                    writer.writerow({'Artiest':name,'Bron herkomst':'https://musicbrainz.org/artist/wrong-namesake','Nummer':'test'})
            with (root/'billboard_artist_profiles.csv').open('w',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=profiles.FIELDS)
                writer.writeheader()
                writer.writerow({'Artiest':'Steve Lacy','Type':'Person','Geboortedatum':'1934-07-23','Leeftijd':'92','Afbeelding':'https://wrong.example/photo.jpg','Bron afbeelding':'https://www.wikidata.org/wiki/Q504641','Bron leeftijd':'https://musicbrainz.org/artist/wrong-namesake'})
            response=types.SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'entities':{}})
            with patch.object(profiles,'ROOT',root),patch.object(profiles,'CACHE',root/'band_members_cache.json'),patch.object(profiles,'OUT',root/'billboard_artist_profiles.csv'),patch.object(profiles,'spotify_token',return_value=''),patch.object(profiles.requests,'get',return_value=response),contextlib.redirect_stdout(io.StringIO()):
                profiles.main()
            with (root/'billboard_artist_profiles.csv').open(encoding='utf-8-sig') as f:
                rows={r['Artiest']:r for r in csv.DictReader(f)}
            self.assertEqual(rows['Steve Lacy']['Geboortedatum'],'1998-05-23')
            self.assertEqual(rows['Steve Lacy']['Leeftijd'],profiles.age_at('1998-05-23'))
            self.assertEqual(rows['boa']['Type'],'Group')
            self.assertEqual(rows['Justice']['Type'],'Group')
            self.assertNotIn('wrong',rows['Steve Lacy']['Afbeelding'])

    def test_membership_direction_excludes_bands_person_belongs_to(self):
        relations=[{'type':'member of band','target-type':'artist','direction':direction,'artist':{'id':direction,'name':direction,'type':'Person'}} for direction in ('forward','backward')]
        self.assertEqual(set(memberships({'relations':relations})),{'backward'})

    def test_age_before_and_on_birthday(self):
        self.assertEqual(age('1998-05-23',date(2026,5,22)),'27')
        self.assertEqual(age('1998-05-23',date(2026,5,23)),'28')

    def test_member_information_visible_without_extra_toggle(self):
        rendered=render_band_members([{'Lid':'A < B','Leeftijd lid':'28','Functie/instrument':'Gitaar','Status':'Huidig','Bron':'https://example.com','Volledigheid':'Gecontroleerd'}, {'Lid':'Second','Leeftijd lid':'','Functie/instrument':'Drums','Status':'Huidig'}])
        self.assertIn('A &lt; B',rendered)
        self.assertIn('28 jaar',rendered)
        self.assertIn('Instrument/rol: Gitaar',rendered)
        self.assertIn('Leeftijd niet bevestigd',rendered)
        self.assertNotIn('<details',rendered)

if __name__=='__main__':
    unittest.main()
