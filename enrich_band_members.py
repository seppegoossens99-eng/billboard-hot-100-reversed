"""Resolve member ages by explicit IDs; keep unknown ages visibly unknown."""
import csv
import json
import time
from datetime import date, timedelta
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent
PATH = ROOT / 'billboard_band_members.csv'
CACHE = ROOT / 'band_member_ages_cache.json'
ROLES = {'lead vocals':'lead-zang','background vocals':'achtergrondzang','vocals':'zang','guitar':'gitaar','bass':'basgitaar','bass guitar':'basgitaar','drums (drum set)':'drums','drums':'drums','keyboards':'toetsen','keyboard':'toetsen','flute':'fluit','original':'','task':'','piano':'piano'}
HEADERS = {'User-Agent':'BillboardReverseMetadata/1.0 (https://github.com/seppegoossens99-eng/billboard-hot-100-reversed)'}

def age(value, today=None):
    today = today or date.today()
    try:
        born = date.fromisoformat(value)
        return str(today.year-born.year-((today.month,today.day)<(born.month,born.day))) if born <= today else ''
    except (ValueError, TypeError):
        return ''

def age_display(birth):
    exact = age(birth)
    if exact:
        return exact
    if isinstance(birth, str) and len(birth) == 4 and birth.isdigit():
        upper = date.today().year - int(birth)
        return f'{upper-1}–{upper}' if upper > 0 else ''
    return ''

def main():
    with PATH.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    cache = json.loads(CACHE.read_text(encoding='utf-8')) if CACHE.exists() else {}
    group_cache = json.loads((ROOT / 'band_members_cache.json').read_text(encoding='utf-8'))
    rosters = json.loads((ROOT / 'band_member_overrides.json').read_text(encoding='utf-8'))
    overrides = {(band, member['name']): member for band, roster in rosters.items() for member in roster['members']}
    birthdates = json.loads((ROOT / 'band_member_birthdates.json').read_text(encoding='utf-8'))
    session = requests.Session()
    session.mount('https://', HTTPAdapter(max_retries=Retry(total=2,backoff_factor=1,status_forcelist=[429,502,503,504])))
    session.headers.update(HEADERS)
    cutoff = (date.today()-timedelta(days=30)).isoformat()
    for row in rows:
        roles = [ROLES.get(x.strip().casefold(), x.strip()) for x in row['Functie/instrument'].split(',')]
        row['Functie/instrument'] = ', '.join(x for x in roles if x) or 'Niet bevestigd'
        row['Leeftijd lid'] = ''
        row['Bron lid'] = ''
        member = overrides.get((row['Artiest'], row['Lid']), {})
        key = row['Artiest'] + '|' + row['Lid']
        member = {**member, **birthdates.get(key, {})}
        group_id = row['Bron'].rsplit('/',1)[-1] if row['Bron'].startswith('https://musicbrainz.org/artist/') else ''
        old = cache.get(key, cache.get(group_id+'|'+row['Lid'], {}))
        identifier = member.get('id') or old.get('id')
        if not identifier and group_id:
            group = group_cache.get(group_id, {}).get('data', {})
            ids = {rel.get('artist', {}).get('id') for rel in group.get('relations', [])
                   if rel.get('type')=='member of band' and rel.get('direction')=='backward' and rel.get('artist',{}).get('name')==row['Lid']}
            ids.discard(None)
            identifier = next(iter(ids)) if len(ids)==1 else ''
        info = dict(old) if old.get('id') == identifier else {}
        if member.get('birth'):
            info.update(birth=member['birth'], source=member['birth_source'])
        if identifier and not age(info.get('birth')) and info.get('checked','') < cutoff:
            try:
                time.sleep(1.2)
                response = session.get('https://musicbrainz.org/ws/2/artist/'+identifier, params={'inc':'url-rels','fmt':'json'}, timeout=20)
                response.raise_for_status()
                person = response.json()
                if person.get('id') != identifier or person.get('type') != 'Person':
                    raise ValueError('Member identity mismatch')
                info.update(id=identifier, birth=(person.get('life-span') or {}).get('begin'), checked=date.today().isoformat(), source='https://musicbrainz.org/artist/'+identifier)
                for rel in person.get('relations', []):
                    if rel.get('type') != 'wikidata' or age(info.get('birth')):
                        continue
                    qid = rel.get('url',{}).get('resource','').rsplit('/',1)[-1]
                    if not (qid.startswith('Q') and qid[1:].isdigit()):
                        continue
                    response = session.get('https://www.wikidata.org/wiki/Special:EntityData/'+qid+'.json',timeout=20)
                    response.raise_for_status()
                    entity = response.json().get('entities',{}).get(qid,{})
                    for claim in entity.get('claims',{}).get('P569',[]):
                        value=claim.get('mainsnak',{}).get('datavalue',{}).get('value',{})
                        raw=value.get('time','')
                        if value.get('precision')==11 and raw.startswith('+') and age(raw[1:11]):
                            info.update(birth=raw[1:11], source='https://www.wikidata.org/wiki/'+qid)
                            break
            except (requests.RequestException,ValueError) as exc:
                print('Member lookup unavailable:',row['Lid'],exc,flush=True)
        if identifier:
            info['id'] = identifier
        cache[key] = info
        row['Leeftijd lid'] = age_display(info.get('birth'))
        row['Bron lid'] = info.get('source') or ('https://musicbrainz.org/artist/'+identifier if identifier else '')
        row['Leeftijdsinfo'] = member.get('age_context','') if not row['Leeftijd lid'] else ''
        if row['Leeftijdsinfo']:
            row['Bron lid'] = member['age_source']
        print(row['Artiest'], row['Lid'], row['Leeftijd lid'] or 'Niet bevestigd',flush=True)
    fields = list(rows[0].keys()) if rows else []
    for field in ('Leeftijd lid','Bron lid'):
        if field not in fields:
            fields.append(field)
    with PATH.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    CACHE.write_text(json.dumps(cache,ensure_ascii=False),encoding='utf-8')
    print('Member ages:',sum(bool(r['Leeftijd lid']) for r in rows),'of',len(rows),flush=True)

if __name__=='__main__':
    main()
