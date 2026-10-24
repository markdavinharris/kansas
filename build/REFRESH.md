# Kansas Early Vote 2026 dashboard — daily refresh runbook

Published artifact (update in place, never create a new one):
**https://claude.ai/artifact/2h77myFs6AcQuDoXVRbmX5** — title "Kansas Early Vote 2026". First published 2026-10-24
with data through 2026-10-23. Sixth member of the Ohio / Iowa / Texas / Michigan / North Carolina family.

The page is a single self-contained HTML file built by `build.py` from `template.html`, `app.js`, seven JSON
data files and one static geometry file `data/counties.json` (KS county outlines as SVG paths, made once from the
Census cb_2023_us_county_20m shapefile by `geo/make_geo.py`; it never changes). All source files plus `SPEC.md`,
the merge helpers and `counties.json` are stored in this Project under `claude/kansas-ev-dashboard/`.

## Steps (about 15 minutes; the BigQuery queries are the slow part)

1. Make a working folder in the scratchpad, e.g. `kansas/` with `data/` and `bq/` subfolders. Fetch the project docs
   `claude/kansas-ev-dashboard/{SPEC.md,build.py,template.html,app.js,merge_county.py,merge_precinct.py,heat_merge.py,make_daily.py,cte.py,counties.json,REFRESH.md}`
   with `project_read` and write each to the working folder under its own file name (`build.py` expects
   `template.html` and `app.js` beside it, and `counties.json` inside `data/` with the query outputs; `cte.py` goes in `bq/`).
   (If an earlier session's `kansas/` or `northcarolina/` folder is still in the scratchpad, the shared `template.html`
   and `app.js` can be copied from there — only `build.py`'s STATE block differs between states.)
2. Re-run the queries in `SPEC.md`. Only 2026 data changes day to day, but `voters` is rebuilt occasionally, so
   re-run everything each time. Run the queries yourself with `mcp__Google_Cloud_BigQuery__execute_sql_readonly`
   (parameter name is `query`). Every result must be SAVED TO A FILE by the harness (automatic for results with a
   `pad` column; the harness names them `.../tool-results/mcp-Google_Cloud_BigQuery-execute_sql_readonly-<id>.txt`,
   copy each to `bq/` under a clear name), then converted with the helper scripts — never retype numbers:
   - `daily.json`: Query S ×3 years (+ pad) and the totals query → paste the three totals rows into `make_daily.py`'s TOT dict, then `make_daily.py data/daily.json bq/S_2026.json bq/S_2024.json bq/S_2022.json`
   - `county_daily_{2026,2024,2022}.json`: Query C, ONE query per year in Kansas (`bq/cte.py YEAR "county >= 'A'"` prints the SQL; 756 / 1,736 / 1,813 rows on 2026-10-24 — split `< 'M'` / `>= 'M'` if a year nears 3,000) → `merge_county.py out.json c1`
   - `heat_2026.json`, `heat_2022.json`: Query H, one query each (ASOF = the as-of day; 11 on 2026-10-24) → `heat_merge.py out.json result`
   - `precinct_2026.json`: Query P in 2 chunks → `merge_precinct.py out.json c1 c2`
   Cross-check: merge_county.py's sums for 2026 must equal make_daily.py's (they did exactly on 2026-10-24: 100,839 / 32,174 / 121,936).
   In Kansas the county sums equal the statewide sums in every year (blank-ID rows still carry a county), so a
   build.py WARNING about county sums is a real problem here, not the expected UNKNOWN difference the NC kit describes.
3. `python3 build.py` → `dashboard.html` and `index.html`. It prints the as-of date (last complete day). If the
   as-of date did not move since the last run, the feed has not updated — republishing is harmless, but say so.
4. Spot-check one number independently, e.g.
   `SELECT COUNTIF(Rejected=0 AND ReturnDate BETWEEN '2026-01-01' AND '<asof>') + COUNTIF(EarlyVoted BETWEEN '2026-01-01' AND '<asof>') FROM abev_2026 WHERE State='KS'`
   must equal the "Early votes cast" tile (154,110 on 2026-10-23; Johnson County 69,592).
5. Screenshot once with Playwright (`shot.py index.html out.png`, light, 1200 wide; it also prints the KPI tiles) and look
   at it; then publish with the Artifact tool:
   `action: publish`, `url: https://claude.ai/artifact/2h77myFs6AcQuDoXVRbmX5`, `file_path: <dashboard.html>`,
   `label: "Data through <as-of date>"`, and `files: {"site/index.html": {"from": "<abs path to index.html>", "contentType": "text/html"}}`.
   Read the artifact first if the tool says it has not been read in this conversation. Do not pass `icon`.
   A publish that passes only these keeps the 105 `precincts/*.json` files already on the artifact.
6. If `template.html` or `app.js` had to change, write the changed file back to the Project at the same path
   (the Ohio, Iowa, Texas, Michigan, North Carolina and Kansas kits share them; only `build.py`'s STATE block differs).
7. Report: as-of date, statewide early votes (and change vs 2024 and 2022 at the same point), net R−D, requested /
   outstanding, anything odd (rejected rows appearing, a change in the county list, a query that hit the 3,000-row cap).

## Data notes that matter
- Kansas has party registration: party = `PartyRollUp` (`Republican` / `Democrat`; `Unaffiliated/DTS` and
  `Independent/Other` — where Kansas Libertarians land — both go to the "Unaffiliated / other" bucket), from the voter
  file of each year. Do not use the ABEV party flags (zero on about 60% of KS rows). KS registration on 2026-10-24:
  891,658 R, 499,877 D, 597,516 unaffiliated, 23,849 other, 2,012,900 total.
- Kansas DOES have real request data (`STATE['no_requests'] = False`): the "Mail ballots outstanding" tile and the
  "Requested" pacing measure are live (100,839 requested, 32,174 returned, 68,665 outstanding on 2026-10-23).
- The feed starts the day before in-person advance voting opens and dates every earlier request to that first day:
  2026-10-14 (82,532 rows, d=20), 2024-10-16 (123,705, d=20), 2022-10-19 (107,327, d=20). So the cumulative "requested"
  line is a step at d=20 in every year rather than a 60-day build-up, and the usual 60-day cap date holds no rows.
  `pacing_note` in build.py explains this on the page.
- In-person advance voting: 2026-10-15 to 2026-11-02 noon (d=19 to d=1); 2024-10-18 to 2024-11-04 (d=18 to d=1);
  2022-10-20 to 2022-11-07 (d=19 to d=1). First EV day is d=19 / d=18 / d=19, so same-point comparisons line up within a day.
- The as-of day on 2026-10-24 was d=11 (2026-10-23): the feed's latest EarlyVoted and ReturnDate were both 2026-10-23
  with a full day's volume (about 26,000 in-person votes), and no partial later day was present. If a later run shows
  a thin latest day, build.py's >500 rule drops it as partial, as in the other kits.
- ABEV `Jurisname` is "<Name> County" (mixed case): the CTE strips " COUNTY" after upper-casing. The 2024 and 2022
  feeds carry one county name in two case spellings (106 distinct raw values, 105 after UPPER). Blank-`DT_Regid`
  rows (132 in 2026, 14,505 in 2024, 1,374 in 2022) still have a Jurisname, so there is no UNKNOWN county.
- `Rejected`: 0 KS rows in all three years (the exclusion rule is still applied; report if that changes).
- Unmatched ABEV rows (no voter in that year's file): 2,495 of 222,775 in 2026 (1.1%), 22,080 in 2024 (3.0%), 3,783 in
  2022; counted as "Unaffiliated / other".
- County spelling: no aliases needed. `voters.CountyName`, the stripped Jurisname and Census NAME.upper() all agree
  (MCPHERSON, POTTAWATOMIE).
- Build checks: `precinct_2026.json` and every `county_daily_*.json` must have exactly 105 counties.
- Same-point figures on 2026-10-23 (d=11): 2026 154,110 early votes, net −6.2; 2024 166,102, net +12.9 (final 711,289,
  +18.1); 2022 92,478, net +2.6 (final 410,720, +10.4). The Democratic lead so far is driven by Johnson County
  (69,592 of 154,110 votes) and the mail return mix; it does not resemble the 2024 or 2022 same-point pattern, so
  re-check it against the spot-check query before reporting if it moves sharply.

## Precinct maps
105 files on the artifact (`precincts/<COUNTY>.json`, spaces as underscores — Kansas has no two-word county names; 1.2 MB total),
built once by `geo/match_precincts.py` from the NYT 2024 precinct map (`KS-precincts-with-results.geojson.gz`, 3,673 shapes,
17 MB gz, downloaded from `https://int.nyt.com/newsgraphics/elections/map-data/2024/national/`) matched to `voters.PrecinctCode`
via each precinct's top-8 Census 2020 blocks (`voter_contact.CensusBlock2020`, Query B in SPEC.md, 2 county chunks; interior
points from TIGER `tl_2020_20_tabblock20`, 163 MB, downloaded from www2.census.gov — both downloads worked from the cloud
session on 2026-10-24). KS NYT precinct IDs are state VTD codes (`20091-KS091000040`), not the county boards' short codes
(`5I`, `046B`, `D128`), so no name match is possible and every code is placed by the block match. Result on 2026-10-24:
4,066 of 4,069 codes placed (3 unmatched: Decatur `CO`, Johnson `D128`, Sheridan `UNE` — tiny codes with no usable blocks);
46 weak (<60% of voters' blocks in the chosen shape); 434 shapes hold more than one code (the voter file splits many rural
precincts finer than the VTD shapes — Osage 15, Butler 14, Miami 14, Reno 13); Sedgwick has 11 and Johnson 14 shapes with
no current code. Rebuild only if KS precinct codes change materially.

## Hand-off to the public site
After republishing the artifact, the standalone page is also published as the artifact FILE `site/index.html` (step 5 above,
same publish call). No GitHub Pages site exists yet for Kansas. If one is set up (e.g. kansas.coldspark.com,
repo `markdavinharris/kansas`), follow `claude/early-vote-sites-publish.md`: the refresh task pushes `index.html` to
the repo through the session's git proxy (ToolSearch-load `mcp__claude-code-remote__add_repo` first, then `add_repo` with
access `push`, shallow clone, copy, commit "Data through <date>", push to main), and the cloud-only safety-net task
compares the artifact's `site/index.html` with the live site. Add the state's row to the table in that runbook when the
repo exists. The repo's first commit also needs `precincts/*.json` (copied from `data/precincts/`), a `CNAME`, `.nojekyll`
and `build/` holding this kit.
