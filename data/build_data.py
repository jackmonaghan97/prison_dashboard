"""
Build every CSV the dashboard reads.

Run from anywhere:  python data/build_data.py

Steps
  1. rates.csv                  June 30 prison counts x ACS residents (population & rates)
  2. population_snapshots.csv   IDOC headcount on June 30 each year (expense per inmate)
  3. admissions.csv             monthly admissions, aggregated     (admissions & exits)
  4. exits.csv                  monthly exits, aggregated          (admissions & exits)
  5. recidivism.csv             one row per release event, de-identified
  6. il_counties.geojson        Illinois county boundaries         (map)
  7. expenses.csv               Comptroller spend by object and month (expenses)

data_download.csv (Comptroller expenditures) is downloaded by hand; step 7 reads it.
Every file is written in its final shape, so the dashboard only reads them (dashboard/data.py).
"""
import json
import urllib.request
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent
DB_PATH = r"C:\Users\jackm\OneDrive\Documents\duckdb_cli-windows-amd64\my_database.duckdb"
GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"

AGE_LABELS = ['>18', '18-19', '20-24', '25-29', '30-34', '35-44',
              '45-54', '55-64', '65-74', '75<']
AGE_BINS = [-np.inf, 18, 20, 25, 30, 35, 45, 55, 65, 75, np.inf]

# admissions start 2018-01-01, so a return can only be observed for releases after that
RECID_FIRST_RELEASE = "2018-01-01"
# release reasons that put someone back in the community (at risk of returning)
RECID_RELEASE_REASONS = ("Not Discharged", "Expiration of Sentence")
CRIME_COLS = ['Person', 'Property', 'Public Order', 'Drug']
# ACS "Hispanic" is an ethnicity overlay: those residents are also counted in one of the
# race groups, so a total across races has to leave it out or it double-counts them
HISPANIC = 'Hispanic'
# ACS age bands folded into the IDOC age groups
CENSUS_AGES = {'<5': '>18', '5-9': '>18', '10-14': '>18', '15-17': '>18', '75-84': '75<', '85<': '75<'}
# census cells smaller than this are dropped
MIN_CELL = 10
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# IDOC spellings -> census / map spellings
COUNTY_FIXES = {'DeWitt': 'De Witt', 'Dupage': 'DuPage', 'Lasalle': 'LaSalle'}


# ---------------------------------------------------------------- helpers
def age_group(ref_dt: pd.Series, birth_dt: pd.Series) -> pd.Series:
    age = (ref_dt - birth_dt).dt.days // 365
    return pd.cut(age, bins=AGE_BINS, labels=AGE_LABELS, right=False).astype(str)


def crime_map() -> pd.DataFrame:
    warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')
    m = pd.read_excel(DATA_DIR / "idoc_public_map.xlsx")
    m = m.loc[~m['state_description'].duplicated()]
    m['crime_class'] = m['crime_class'].fillna('Unknown').replace({'Other': 'Unknown'})
    return m


def clean_people(df: pd.DataFrame) -> pd.DataFrame:
    """Shared cleanup for admission / exit / population person-level pulls."""
    df = df.copy()
    df['sex'] = df['sex'].replace({'nan': None, 'Both': None, 'B': None})
    df['race'] = (df['race'].replace({'nan': None, 'Not Assigned': None})
                  .str.replace('_OR_AFRICAN_AMERICAN', '', regex=False)
                  .str.title())
    df['race'] = df['race'].replace({'Unknown': 'Other'})
    df['county'] = df['stnccty'].replace({'nan': None, 'Out of state': 'Out of State'})
    df['county'] = df['county'].replace(COUNTY_FIXES)
    df = df.merge(crime_map(), left_on='hofnscd', right_on='state_description', how='left')
    df['crime_class'] = df['crime_class'].fillna('Unknown')
    return df


def month_floor(s: pd.Series) -> pd.Series:
    return s.dt.to_period('M').dt.to_timestamp()


# ---------------------------------------------------------------- 1. rates
def county_key(s: pd.Series) -> pd.Series:
    """Join key for a county name in either source ('De Witt County, Illinois' / 'DeWitt' -> 'dewitt')."""
    return s.str.split(' Cou').str[0].str.replace('e W', 'ew').str.lower()


def load_census(con) -> pd.DataFrame:
    """ACS residents per (year, county, age, sex, race), in the IDOC age groups and race names."""
    c = con.execute("SELECT * FROM illinois_demo").fetchdf().drop_duplicates()
    c = c.loc[c['year'].notna()].copy()
    c['age'] = c['age'].replace(CENSUS_AGES)
    c.loc[c['race'].str.contains('NATIVE'), 'race'] = 'AMERICAN INDIAN'
    c.loc[c['race'].str.contains('TWO'), 'race'] = 'BI-RACIAL'
    # the regrouping above leaves several rows per cell: add them up
    c['value'] = c['value'].astype(int)
    c = c.groupby(['age', 'sex', 'race', 'year', 'county_name'])['value'].sum().reset_index()
    c = c.loc[c['value'] >= MIN_CELL].copy()
    c['race'] = c['race'].str.replace('_OR_AFRICAN_AMERICAN', '').str.replace('_OR_LATINO', '').str.title()
    c['sex'] = c['sex'].str.title()
    c['key'] = county_key(c['county_name'])
    c['county'] = c['county_name'].str.replace(' County, Illinois', '', regex=False)
    return c.rename(columns={'year': 'census_year', 'value': 'gen_population'})


def load_prison_june(con) -> pd.DataFrame:
    """People in custody on June 30 by (year, county key, age, sex, race), one column per offense class."""
    p = con.execute("""
        SELECT * FROM prison_population_data_sets
        WHERE EXTRACT(month FROM record_dt) = 6        -- June 30: end of the state fiscal year
    """).fetchdf()
    invalid = (p['sex'].isin(['nan', 'B']) | p['race'].isin(['nan', 'Unknown', 'Not Assigned'])
               | p['race'].isna() | p['birthdt'].isna())
    p = p.loc[~invalid].copy()
    p['age'] = age_group(p['cstdt'], p['birthdt'])
    p = p.merge(crime_map(), left_on='hofnscd', right_on='state_description', how='left')
    p['year'] = p['record_dt'].dt.year
    p['key'] = p['stnccty'].str.lower()
    return (p.groupby(['year', 'key', 'age', 'sex', 'race', 'crime_class'])['docnbr'].count()
             .unstack('crime_class').reindex(columns=CRIME_COLS).fillna(0).reset_index())


def build_rates(con):
    """
    One row per (prison year, county, age, sex, race): the ACS residents of that cell and the
    people in custody from it on June 30. Every prison year gets every census cell exactly
    once; years after the newest ACS reuse it. People who match no census cell (out of
    state, unknown county, cells under MIN_CELL) are left out. The rates themselves are
    worked out in the app after the filters are applied - rates can't be added up, counts can.

    `gen_population` is the ACS count of the row's own group; `residents` is the same except
    zero on Hispanic rows, so summing it over any set of races counts each person once.
    """
    print("1/7 rates.csv")
    census, prison = load_census(con), load_prison_june(con)
    first, last = int(census['census_year'].min()), int(census['census_year'].max())
    years = pd.DataFrame({'year': range(first, int(prison['year'].max()) + 1)})
    years['census_year'] = years['year'].clip(first, last)
    grid = years.merge(census, on='census_year')
    out = grid.merge(prison, on=['year', 'key', 'age', 'sex', 'race'], how='left')
    out[CRIME_COLS] = out[CRIME_COLS].fillna(0)
    out['total'] = out[CRIME_COLS].sum(axis=1)
    out['residents'] = out['gen_population'].where(out['race'] != HISPANIC, 0)
    out = out[['year', 'census_year', 'county', 'age', 'sex', 'race', 'gen_population', 'residents']
              + CRIME_COLS + ['total']]
    out.to_csv(DATA_DIR / "rates.csv", index=False)
    print(f"    {len(out):,} rows, {first}-{out['year'].max()}, ACS {first}-{last}")


# ---------------------------------------------------------------- 2. population
def build_population(con):
    print("2/7 population_snapshots.csv")
    pop = con.execute("""
        SELECT record_dt, COUNT(DISTINCT docnbr) AS population
        FROM prison_population_data_sets
        WHERE record_dt IS NOT NULL
          AND EXTRACT(month FROM record_dt) = 6        -- June 30: end of the state fiscal year
        GROUP BY 1 ORDER BY 1
    """).fetchdf()
    pop.to_csv(DATA_DIR / "population_snapshots.csv", index=False)


# ---------------------------------------------------------------- 3. admissions
def load_admissions(con) -> pd.DataFrame:
    adm = con.execute("""
        SELECT DISTINCT docnbr, birthdt, sex, race, hofnscd, admtyp, stnccty, admitdt
        FROM prison_admission_data_sets
        WHERE admitdt IS NOT NULL
    """).fetchdf()
    adm = clean_people(adm)
    # source files overlap and repeat rows with cosmetic differences: one admission per person-day
    adm = adm.drop_duplicates(['docnbr', 'admitdt'])
    adm['admtyp'] = adm['admtyp'].replace({'nan': 'Other'}).fillna('Other')
    adm['age_group'] = age_group(adm['admitdt'], adm['birthdt'])
    return adm


def build_admissions(adm: pd.DataFrame):
    print("3/7 admissions.csv")
    adm = adm.assign(month=month_floor(adm['admitdt']))
    out = (adm.groupby(['month', 'admtyp', 'sex', 'race', 'age_group', 'county', 'crime_class'],
                       dropna=False, observed=True)
              .size().reset_index(name='n'))
    out.to_csv(DATA_DIR / "admissions.csv", index=False)


# ---------------------------------------------------------------- 4. exits
def load_exits(con) -> pd.DataFrame:
    ex = con.execute("""
        SELECT DISTINCT docnbr, birthdt, sex, race, hofnscd, stnccty, discrsn, sperlsrsn,
               relinst, COALESCE(actmsrdt, actdisdt) AS release_dt
        FROM prison_exit_data_sets
        WHERE COALESCE(actmsrdt, actdisdt) IS NOT NULL
    """).fetchdf()
    ex = clean_people(ex)
    ex['discrsn'] = ex['discrsn'].replace({'nan': None}).fillna('Unknown')
    ex['sperlsrsn'] = ex['sperlsrsn'].str.strip().replace({'nan': None, '': None})
    # FY2020's file lists every exit twice (sperlsrsn '' vs 'nan'): one exit per person-day
    ex = ex.drop_duplicates(['docnbr', 'release_dt'])
    # "Not Discharged" = released to mandatory supervised release; the sperlsrsn says how
    msr = ex['discrsn'].eq('Not Discharged')
    ex['exit_reason'] = np.where(
        msr, 'MSR: ' + ex['sperlsrsn'].fillna('Standard release'), ex['discrsn'])
    ex['age_group'] = age_group(ex['release_dt'], ex['birthdt'])
    return ex


def build_exits(ex: pd.DataFrame):
    print("4/7 exits.csv")
    ex = ex.assign(month=month_floor(ex['release_dt']))
    out = (ex.groupby(['month', 'exit_reason', 'discrsn', 'sex', 'race', 'age_group',
                       'county', 'crime_class', 'relinst'], dropna=False, observed=True)
             .size().reset_index(name='n'))
    out.to_csv(DATA_DIR / "exits.csv", index=False)


# ---------------------------------------------------------------- 5. recidivism
def build_recidivism(adm: pd.DataFrame, ex: pd.DataFrame):
    print("5/7 recidivism.csv")
    rel = ex.loc[ex['discrsn'].isin(RECID_RELEASE_REASONS)
                 & (ex['release_dt'] >= RECID_FIRST_RELEASE),
                 ['docnbr', 'release_dt', 'sex', 'race', 'age_group', 'county',
                  'crime_class', 'relinst']]
    returns = adm[['docnbr', 'admitdt', 'admtyp']]

    # days from release to the first admission *of each type* strictly after it, so the app
    # can count a return under any combination of admission types
    joined = duckdb.query("""
        SELECT r.*,
               MIN(CASE WHEN a.admtyp = 'Court admission'       THEN a.admitdt END) AS dt_court,
               MIN(CASE WHEN a.admtyp = 'New sentence violator' THEN a.admitdt END) AS dt_newsent,
               MIN(CASE WHEN a.admtyp = 'Technical violator'    THEN a.admitdt END) AS dt_tech,
               MIN(CASE WHEN a.admtyp = 'Other'                 THEN a.admitdt END) AS dt_other
        FROM rel r LEFT JOIN returns a
          ON a.docnbr = r.docnbr AND a.admitdt > r.release_dt
        GROUP BY ALL
    """).to_df()

    for c in ['court', 'newsent', 'tech', 'other']:
        joined[f'days_{c}'] = (joined[f'dt_{c}'] - joined['release_dt']).dt.days
    joined['release_year'] = joined['release_dt'].dt.year
    joined['release_month'] = month_floor(joined['release_dt'])
    out = joined.drop(columns=['docnbr', 'release_dt', 'dt_court', 'dt_newsent', 'dt_tech', 'dt_other'])
    out.to_csv(DATA_DIR / "recidivism.csv", index=False)
    any_return = out[['days_court', 'days_newsent', 'days_tech', 'days_other']].notna().any(axis=1)
    print(f"    {len(out):,} release events, {any_return.mean():.1%} returned (any window)")


# ---------------------------------------------------------------- 6. geojson
def build_geojson():
    print("6/7 il_counties.geojson")
    target = DATA_DIR / "il_counties.geojson"
    if target.exists():
        print("    already present, skipping download")
        return
    with urllib.request.urlopen(GEOJSON_URL) as r:
        us = json.load(r)
    il = {"type": "FeatureCollection",
          "features": [f for f in us['features'] if f['id'].startswith('17')]}
    for f in il['features']:
        f['properties'] = {'name': f['properties']['NAME'], 'fips': f['id']}
    target.write_text(json.dumps(il))


# ---------------------------------------------------------------- 7. expenses
def build_expenses():
    """
    Comptroller spend by object and month. The Comptroller's "Year" is the state fiscal
    year (July-June), so Jul-Dec rows belong to the previous calendar year; `year` keeps
    the fiscal year and `dt` is the real calendar month.
    """
    print("7/7 expenses.csv")
    df = pd.read_csv(DATA_DIR / "data_download.csv")
    df = df.rename(columns={"Object": "object", "Object_cat": "category", "Year": "year"})
    month_num = df["month"].map({m: i for i, m in enumerate(MONTHS, 1)})
    cal_year = df["year"] - (month_num >= 7).astype(int)
    df["dt"] = pd.to_datetime(dict(year=cal_year, month=month_num, day=1))
    df[["year", "month", "dt", "object", "category", "amount"]].to_csv(DATA_DIR / "expenses.csv", index=False)


# ---------------------------------------------------------------- checks
def check_county_names(adm: pd.DataFrame):
    """Warn if sentencing-county names in IDOC data don't match the map / census names."""
    geo = json.loads((DATA_DIR / "il_counties.geojson").read_text())
    geo_names = {f['properties']['name'] for f in geo['features']}
    idoc_names = set(adm['county'].dropna().unique()) - {'Out of State'}
    missing = sorted(idoc_names - geo_names)
    if missing:
        print(f"    WARNING: IDOC counties not found on map: {missing}")


if __name__ == "__main__":
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        build_rates(con)
        build_population(con)
        adm = load_admissions(con)
        ex = load_exits(con)
    finally:
        con.close()
    build_admissions(adm)
    build_exits(ex)
    build_recidivism(adm, ex)
    build_geojson()
    build_expenses()
    check_county_names(adm)
    print("done")
