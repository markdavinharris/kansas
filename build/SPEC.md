# Kansas early-vote data extraction spec

Use the MCP tool `mcp__Google_Cloud_BigQuery__execute_sql_readonly` with projectId `coldspark-voterdata`,
timeoutMs 180000. Results are capped at 3,000 rows: if a query returns exactly 3000 rows, split its
county range further and re-run. Every result that matters is saved to a file by the harness (add the `pad`
column so even small results are); convert them with the kit's merge scripts, never retype numbers.
Working folder: `<scratchpad>/kansas/` with `data/`, `bq/` (saved query results) and `geo/`.

## Year parameters

| year | abev table | voter file table | Election Day |
|---|---|---|---|
| 2026 | `coldspark-voterdata.national_file.abev_2026` | `coldspark-voterdata.national_file.voters` | 2026-11-03 |
| 2024 | `coldspark-voterdata.national_file.abev_2024` | `coldspark-voterdata.national_file.voterfile_2024` | 2024-11-05 |
| 2022 | `coldspark-voterdata.national_file.abev_2022` | `coldspark-voterdata.national_file.voterfile_2022` | 2022-11-08 |

## Party note
Kansas has party registration. Party comes from the voter file's `PartyRollUp` for each year, never from
the ABEV flags (they are zero on about 60% of KS rows). Values in KS (2026-10-24): `Republican` 891,658,
`Democrat` 499,877, `Unaffiliated/DTS` 597,516, `Independent/Other` 23,849 (Libertarian and other minor parties);
no modeled values. The CASE below maps Democrat → D, Republican → R and everything else (including rows that
matched no voter) → O. The CASE also accepts the modeled labels so the SQL is identical to the other state kits.

## County note
KS ABEV `Jurisname` is "<Name> County" in mixed case (e.g. "Johnson County", "McPherson County");
`REGEXP_REPLACE(UPPER(..), ' COUNTY$', '')` gives JOHNSON / MCPHERSON, which equals `voters.CountyName` and the
Census NAME.upper() used in `counties.json`. No aliases are needed. `COUNT(DISTINCT Jurisname)` is 106 in the
2024 and 2022 feeds because one county name appears in two spellings of case; UPPER() merges them to 105.
Rows with a blank `DT_Regid` (132 in 2026, 14,505 in 2024, 1,374 in 2022) still carry a Jurisname in Kansas, so
there is no `UNKNOWN` county and county sums equal statewide sums exactly (build.py prints no WARNING).

## Feed-start note (changes how the request line reads)
Kansas's feed begins the day before in-person advance voting opens, and every request made before then is
dated to that first day: 2026-10-14 (82,532 rows, d=20), 2024-10-16 (123,705 rows, d=20), 2022-10-19
(107,327 rows, d=20). The usual 60-day request cap date (2026-09-04 etc.) holds no rows. There are no rows at
all before that first day, so the 2026 statewide daily file has only about 8 days and Query C fits in ONE query
per year (756 / 1,736 / 1,813 rows on 2026-10-24) — the `county >= 'A'` "chunk" below. `Rejected` is 0 on every
KS row in all three years (the rule is still applied).

## Common CTE (substitute ABEV, VF, ED, YEAR) — `bq/cte.py YEAR "<chunk>"` prints a Query C instance

```sql
WITH a AS (
  SELECT IFNULL(REGEXP_REPLACE(UPPER(a.Jurisname), ' COUNTY$', ''), 'UNKNOWN') AS county,
    a.RequestDate, a.ReturnDate, a.EarlyVoted, a.Rejected,
    CASE WHEN v.PartyRollUp IN ('Republican','Modeled Republican') THEN 'R' WHEN v.PartyRollUp IN ('Democrat','Modeled Democrat') THEN 'D' ELSE 'O' END AS party
  FROM `ABEV` a
  LEFT JOIN `VF` v ON v.DT_Regid = a.DT_Regid AND v.State = 'KS'
  WHERE a.State = 'KS'
),
u AS (
  SELECT county, 'req' AS m, DATE_DIFF(DATE 'ED', RequestDate, DAY) AS d, party FROM a
    WHERE Rejected = 0 AND RequestDate BETWEEN DATE 'YEAR-01-01' AND DATE 'YEAR-12-31'
  UNION ALL
  SELECT county, 'ret', DATE_DIFF(DATE 'ED', ReturnDate, DAY), party FROM a
    WHERE Rejected = 0 AND ReturnDate BETWEEN DATE 'YEAR-01-01' AND DATE 'YEAR-12-31'
  UNION ALL
  SELECT county, 'eip', DATE_DIFF(DATE 'ED', EarlyVoted, DAY), party FROM a
    WHERE EarlyVoted BETWEEN DATE 'YEAR-01-01' AND DATE 'YEAR-12-31'
)
```

## Query S — statewide daily (one per year, + pad so it is saved to a file)

```sql
<CTE>
SELECT d,
  COUNTIF(m='req' AND party='R') reqR, COUNTIF(m='req' AND party='D') reqD, COUNTIF(m='req' AND party='O') reqO,
  COUNTIF(m='ret' AND party='R') retR, COUNTIF(m='ret' AND party='D') retD, COUNTIF(m='ret' AND party='O') retO,
  COUNTIF(m='eip' AND party='R') eipR, COUNTIF(m='eip' AND party='D') eipD, COUNTIF(m='eip' AND party='O') eipO,
  REPEAT('x',10000) pad
FROM u WHERE d BETWEEN -14 AND 60 GROUP BY d ORDER BY d
```
Totals (one query, all three years; small enough to come back inline — paste the numbers into `make_daily.py`'s TOT dict):
```sql
SELECT '2026' y, COUNT(*) rows_total, COUNTIF(a.Rejected=1) rejected_rows, COUNTIF(v.DT_Regid IS NULL) unmatched_rows
FROM `..abev_2026` a LEFT JOIN `..voters` v ON v.DT_Regid=a.DT_Regid AND v.State='KS' WHERE a.State='KS'
UNION ALL ... 2024 with voterfile_2024 ... UNION ALL ... 2022 with voterfile_2022 ...
```
(On 2026-10-24: 2026 222,775 / 0 / 2,495; 2024 725,112 / 0 / 22,080; 2022 429,840 / 0 / 3,783.)
Then `python3 make_daily.py data/daily.json bq/S_2026.json bq/S_2024.json bq/S_2022.json`.

Output `daily.json`:
```json
{"2026":{"rows":[[d,reqR,reqD,reqO,retR,retD,retO,eipR,eipD,eipO],...],"rows_total":N,"rejected_rows":N,"unmatched_rows":N},
 "2024":{...},"2022":{...}}
```

## Query C — county daily (one per year; one query covers all 105 counties)

```sql
<CTE>
SELECT county, d, <same 9 COUNTIF columns as Query S>, REPEAT('x',300) pad
FROM u WHERE d BETWEEN -14 AND 60 AND county >= 'A'   -- chunk; split (< 'M' / >= 'M') only if a year nears 3,000 rows
GROUP BY county, d ORDER BY county, d
```
`bq/cte.py 2026 "county >= 'A'"` prints it. `merge_county.py out.json c1 [c2 ...]` converts the saved results.
Output `county_daily_YEAR.json`: `{"COUNTY":[[d,reqR,...,eipO],...], ...}` (105 counties; no UNKNOWN in Kansas).

## Query P — precinct level, 2026 only (two chunks: `UPPER(CountyName) < 'M'` and `>= 'M'`; 4,069 county/precinct codes, 1,983 + 2,086 rows)

```sql
SELECT UPPER(v.CountyName) county, v.PrecinctCode precinct,
  COUNTIF(party='R') regR, COUNTIF(party='D') regD, COUNTIF(party='O') regO,
  COUNTIF(a.Rejected=0 AND a.RequestDate IS NOT NULL AND party='R') reqR,
  COUNTIF(a.Rejected=0 AND a.RequestDate IS NOT NULL AND party='D') reqD,
  COUNTIF(a.Rejected=0 AND a.RequestDate IS NOT NULL AND party='O') reqO,
  COUNTIF(a.Rejected=0 AND a.ReturnDate IS NOT NULL AND party='R') retR,
  COUNTIF(a.Rejected=0 AND a.ReturnDate IS NOT NULL AND party='D') retD,
  COUNTIF(a.Rejected=0 AND a.ReturnDate IS NOT NULL AND party='O') retO,
  COUNTIF(a.EarlyVoted IS NOT NULL AND party='R') eipR,
  COUNTIF(a.EarlyVoted IS NOT NULL AND party='D') eipD,
  COUNTIF(a.EarlyVoted IS NOT NULL AND party='O') eipO,
  REPEAT('x',300) pad
FROM (
  SELECT DT_Regid, CountyName, PrecinctCode,
    CASE WHEN PartyRollUp IN ('Republican','Modeled Republican') THEN 'R' WHEN PartyRollUp IN ('Democrat','Modeled Democrat') THEN 'D' ELSE 'O' END AS party
  FROM `coldspark-voterdata.national_file.voters`
  WHERE State='KS' AND UPPER(CountyName) < 'M'   -- chunk
) v
LEFT JOIN `coldspark-voterdata.national_file.abev_2026` a ON a.DT_Regid = v.DT_Regid AND a.State='KS'
GROUP BY 1,2 ORDER BY 1,2
```
`merge_precinct.py out.json c1 c2`. Output `precinct_2026.json`: `{"COUNTY":[["precinctCode",regR,regD,regO,reqR,reqD,reqO,retR,retD,retO,eipR,eipD,eipO],...],...}`.
KS precinct codes are the county's own short codes (e.g. Allen "5I", Douglas "046B", Johnson "D128"); never NULL or blank.

## Query H — party × vote history cells (2026 and 2022; one query per year, 105 × 3 × 5 ≈ 1,575 rows; `heat_merge.py out.json result`)

Run AFTER daily.json exists: replace `ASOF` below with the as-of day `build.py` reports (smallest d with
returns + in-person > 500; 11 on 2026-10-24). Both years use that same ASOF so the cells compare the same point.

2026 (current file; history = generals 2018–2024):
```sql
SELECT UPPER(v.CountyName) county,
  CASE WHEN v.PartyRollUp IN ('Republican','Modeled Republican') THEN 'R' WHEN v.PartyRollUp IN ('Democrat','Modeled Democrat') THEN 'D' ELSE 'O' END party,
  (IF(v.VH18G IS NOT NULL,1,0)+IF(v.VH20G IS NOT NULL,1,0)+IF(v.VH22G IS NOT NULL,1,0)+IF(v.VH24G IS NOT NULL,1,0)) hist,
  COUNT(*) reg,
  COUNTIF((a.Rejected=0 AND a.ReturnDate BETWEEN DATE '2026-01-01' AND DATE_SUB(DATE '2026-11-03', INTERVAL ASOF DAY)) OR a.EarlyVoted BETWEEN DATE '2026-01-01' AND DATE_SUB(DATE '2026-11-03', INTERVAL ASOF DAY)) ev_now,
  COUNTIF(a.Rejected=0 AND a.ReturnDate BETWEEN DATE '2026-01-01' AND DATE_SUB(DATE '2026-11-03', INTERVAL ASOF DAY)) mail_now,
  COUNTIF(a.EarlyVoted BETWEEN DATE '2026-01-01' AND DATE_SUB(DATE '2026-11-03', INTERVAL ASOF DAY)) eip_now,
  COUNTIF(a.Rejected=0 AND a.RequestDate BETWEEN DATE '2026-01-01' AND DATE_SUB(DATE '2026-11-03', INTERVAL ASOF DAY)) req_now,
  REPEAT('x',300) pad
FROM `coldspark-voterdata.national_file.voters` v
LEFT JOIN `coldspark-voterdata.national_file.abev_2026` a ON a.DT_Regid = v.DT_Regid AND a.State='KS'
WHERE v.State='KS' GROUP BY 1,2,3 ORDER BY 1,2,3
```
2022 (voterfile_2022 + abev_2022; history = generals 2014–2020; Election Day 2022-11-08): same query with the
tables and dates swapped, `VH14G/VH16G/VH18G/VH20G` for `hist`, and two extra columns before `pad`:
`COUNTIF((a.Rejected=0 AND a.ReturnDate BETWEEN DATE '2022-01-01' AND DATE '2022-12-31') OR a.EarlyVoted BETWEEN DATE '2022-01-01' AND DATE '2022-12-31') ev_final, COUNTIF(v.VH22G IS NOT NULL) voted22`.

Output `heat_2026.json` / `heat_2022.json`:
`{"cols":["hist","reg","ev_now","mail_now","eip_now","req_now"(,"ev_final","voted22")],"data":{"COUNTY":{"R":[[hist,reg,ev_now,...],...],"D":[...],"O":[...]},...}}`

## Query B — precinct census blocks (geometry only; re-run only when rebuilding the precinct maps)

Two chunks (`UPPER(v.CountyName) < 'M'` / `>= 'M'`), counts only, no personal fields:
```sql
WITH b AS (
  SELECT UPPER(v.CountyName) county, v.PrecinctCode precinct, c.CensusBlock2020 blk, COUNT(*) n
  FROM `coldspark-voterdata.national_file.voters` v
  JOIN `coldspark-voterdata.national_contact.voter_contact` c ON c.DT_Regid = v.DT_Regid
  WHERE v.State='KS' AND UPPER(v.CountyName) < 'M' AND c.CensusBlock2020 IS NOT NULL AND c.CensusBlock2020 != ''
  GROUP BY 1,2,3
), r AS (
  SELECT county, precinct, blk, n, ROW_NUMBER() OVER (PARTITION BY county, precinct ORDER BY n DESC) rk, SUM(n) OVER (PARTITION BY county, precinct) tot FROM b
)
SELECT county, precinct, ANY_VALUE(tot) voters_with_block, STRING_AGG(CONCAT(blk, ':', CAST(n AS STRING)), ',' ORDER BY n DESC) blocks, REPEAT('x',200) pad
FROM r WHERE rk <= 8 GROUP BY 1,2 ORDER BY 1,2
```
Then `geo/make_blocks.py bq/B_1.json bq/B_2.json` (needs TIGER `tl_2020_20_tabblock20` unzipped in `geo/dl/tl/`) and
`geo/match_precincts.py` (needs `geo/nyt/KS.geojson` and `geo/dl/cb/cb_2023_us_county_20m`).
