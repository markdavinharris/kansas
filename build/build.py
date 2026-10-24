#!/usr/bin/env python3
"""Assemble the Kansas Early Vote dashboard: template.html + data/*.json -> dashboard.html

Usage: python3 build.py [data_dir] [out_file]
Expects in data_dir: daily.json, county_daily_2026.json, county_daily_2024.json,
county_daily_2022.json, precinct_2026.json, heat_2026.json, heat_2022.json, counties.json (formats in SPEC.md).
Optional: proj.json (projected final electorate, from make_proj.py / Query M in PROJECTION.md). Without it the gated
projection section is hidden.
"""
import json, sys, os, datetime

here = os.path.dirname(os.path.abspath(__file__))
data_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, 'data')
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, 'dashboard.html')

ED = {'2026': '2026-11-03', '2024': '2024-11-05', '2022': '2022-11-08'}
STATE = {
    'name': 'Kansas', 'abbr': 'KS', 'fips': '20', 'counties': 105,
    'party_label': 'registered party', 'other_label': 'Unaffiliated / other', 'no_requests': False,
    'party_note': 'Party is the voter’s registered party on Kansas’s voter file (Republican, Democratic, or unaffiliated / other, which includes Libertarian and other minor-party registrants), from the voter file as it stood in each year.',
    'pacing_note': 'Kansas’s feed begins the day before in-person advance voting opens, so every mail ballot requested before then is dated to that first day (Oct 14, 2026; Oct 16, 2024; Oct 19, 2022) and the “requested” line jumps on that day rather than building up over the weeks before. In-person advance voting opens about three weeks before Election Day (Oct 15 – Nov 2, 2026; Oct 18 – Nov 4, 2024; Oct 20 – Nov 7, 2022) and ends at noon the day before Election Day. Mail ballots postmarked by Election Day count if they arrive within three days after it.',
    'other_note': 'Unaffiliated / other includes unaffiliated voters and minor-party registrants, plus the few records that did not match a voter.',
    'unmatched_pct': None,  # filled from daily.json below
}

def load(name):
    with open(os.path.join(data_dir, name)) as f:
        return json.load(f)

daily = load('daily.json')
county = {y: load(f'county_daily_{y}.json') for y in ('2026', '2024', '2022')}
precinct = load('precinct_2026.json')
heat = {'2026': load('heat_2026.json'), '2022': load('heat_2022.json')}  # party x vote-history cells (Query H)
geo = load('counties.json')  # static: county outlines as SVG paths (made by geo/make_geo.py)

# Kansas county-name normalisation: the ABEV feed says "Johnson County" (stripped and upper-cased in SQL; 2024 and 2022
# also carry one case variant of a county name, which UPPER() merges), the voter file says JOHNSON, the Census NAME.upper()
# is also JOHNSON (McPherson -> MCPHERSON).
# No aliases are needed, but the hook is kept so a spelling change in the feed is a one-line fix.
ALIAS = {}
def _norm(dct):
    out = {}
    for k, v in dct.items():
        k2 = ALIAS.get(k, k)
        if k2 in out:
            out[k2] = (out[k2] + v) if isinstance(v, list) else {**out[k2], **v}
        else:
            out[k2] = v
    return out
precinct = _norm(precinct)
for y in county: county[y] = _norm(county[y])
for y in heat: heat[y]['data'] = _norm(heat[y]['data'])
# Rows with no county would be 'UNKNOWN' (none in Kansas: even blank-ID rows carry a Jurisname); the hook is kept
# so a NULL Jurisname in a future feed stays in the statewide file and is dropped from the county file.
_all = {c for c in precinct}
for y in county: county[y].pop('UNKNOWN', None)
for y in county:
    for c in _all - set(county[y]):
        county[y][c] = []

# As-of = last complete day in 2026: smallest d whose returns+EIP exceed 500.
rows26 = sorted(daily['2026']['rows'])
asof_d = None
for r in rows26:
    if sum(r[4:10]) > 500:
        asof_d = r[0]; break
if asof_d is None:
    raise SystemExit('could not determine as-of day')
ed26 = datetime.date.fromisoformat(ED['2026'])
asof_date = ed26 - datetime.timedelta(days=asof_d)

# Partial-day rows dropped from headline figures (d < asof_d)
partial = [r for r in rows26 if r[0] < asof_d]
partial_tot = [sum(r[i] for r in partial) for i in range(1, 10)]

# Sanity: county sums should match statewide (apart from UNKNOWN-county rows, which are reported)
for y in county:
    s = [0]*9
    for rows in county[y].values():
        for r in rows:
            for i in range(9): s[i] += r[i+1]
    t = [sum(r[i+1] for r in daily[y]['rows']) for i in range(9)]
    if s != t:
        print(f'WARNING {y}: county sums {s} != statewide {t} (difference {[t[i]-s[i] for i in range(9)]} = UNKNOWN-county rows, expected to be small)', file=sys.stderr)
assert len(precinct) == STATE['counties'], len(precinct)
assert all(len(county[y]) == STATE['counties'] for y in county), {y: len(county[y]) for y in county}
STATE['unmatched_pct'] = round(100 * daily['2026']['unmatched_rows'] / daily['2026']['rows_total'], 1)

# Projected final electorate (optional). Must be computed at the same as-of day as the rest of the page.
proj = None
if os.path.exists(os.path.join(data_dir, 'proj.json')):
    proj = load('proj.json')
    if proj.get('dbe') != asof_d:
        print(f"WARNING proj.json is as of d={proj.get('dbe')} but the page is as of d={asof_d}; re-run Query M "
              f"and make_proj.py with ASOF={asof_d}. Projection section hidden.", file=sys.stderr)
        proj = None

def _built_et():
    """Build time in US Eastern, e.g. 'Oct 24, 2026 9:05 AM ET' (matches the GitHub Action's stamp)."""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.datetime.now(ZoneInfo('America/New_York'))
    except Exception:
        utc = datetime.datetime.now(datetime.timezone.utc)
        now = utc + datetime.timedelta(hours=-4 if utc < datetime.datetime(2026, 11, 1, 6, tzinfo=datetime.timezone.utc) else -5)
    return now.strftime('%b ') + str(now.day) + now.strftime(', %Y ') + now.strftime('%I:%M %p').lstrip('0') + ' ET'

payload = {
    'ed': ED,
    'asof': {'d': asof_d, 'date': asof_date.isoformat()},
    'partial': partial_tot,
    'meta': {y: {k: v for k, v in daily[y].items() if k != 'rows'} for y in daily},
    'daily': {y: sorted(daily[y]['rows']) for y in daily},
    'county': county,
    'precinct': precinct,
    'heat': heat,
    'geo': geo,
    'state': STATE,
    'built': _built_et(),
}

with open(os.path.join(here, 'template.html')) as f:
    tpl = f.read()
js = json.dumps(payload, separators=(',', ':')).replace('</', '<\\/')
assert '/*__DATA__*/' in tpl and '/*__JS__*/' in tpl
with open(os.path.join(here, 'app.js')) as f:
    appjs = f.read()
pjs = json.dumps(proj, separators=(',', ':')).replace('</', '<\\/') if proj else 'null'
html = tpl.replace('/*__DATA__*/', js).replace('/*__JS__*/', appjs).replace('/*__PROJ__*/null', pjs).replace('__TITLE__', STATE['name'] + ' Early Vote 2026').replace('__STATE__', STATE['name']).replace('__PARTY_LABEL__', STATE.get('party_label','registered party')).replace('__OTHER_NOTE__', STATE.get('other_note','Other / unaffiliated includes voters with no party on file.'))
with open(out, 'w') as f:
    f.write(html)
# Standalone copy for self-hosting (the artifact adds its own document skeleton; a web host does not)
cut = html.index('<header class="mast">')
head, body = html[:cut], html[cut:]
standalone = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
              '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
              '<meta name="description" content="' + STATE['name'] + ' 2026 mail and early in-person vote tracker from ColdSpark: pacing against 2024 and 2022, partisan split, and county and precinct detail, updated daily.">\n'
              + head.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', '')
              + '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}img{max-width:100%}[hidden]{display:none!important}</style>\n'
              '</head>\n<body>\n' + body + '\n</body>\n</html>\n')
with open(os.path.join(os.path.dirname(out), 'index.html'), 'w') as f:
    f.write(standalone)
print(f'wrote {out} ({len(html)/1e6:.2f} MB); as of {asof_date} (d={asof_d}); partial-day rows dropped: {partial_tot}; '
      + (f"projection {proj['early_net']:+.1f} -> {proj['proj_net']:+.1f}" if proj else 'no projection'))
