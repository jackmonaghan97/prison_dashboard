"""
Build every CSV the dashboard reads.

Run from anywhere:  python data/build_data.py

Steps
  1. runs retrieve_data.py (unchanged) -> inc_data.csv           (rates & disparities)
  2. population_snapshots.csv   quarterly/semiannual headcounts    (expense per inmate)
  3. admissions.csv             monthly admissions, aggregated     (admissions & exits)
  4. exits.csv                  monthly exits, aggregated          (admissions & exits)
  5. recidivism.csv             one row per release event, de-identified
  6. il_counties.geojson        Illinois county boundaries         (map)

data_download.csv (IDOC expenditures) is downloaded separately and is read as-is.
"""
import json
import os
import runpy
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
def build_inc_data():
    print("1/6 inc_data.csv (retrieve_data.py)")
    cwd = os.getcwd()
    os.chdir(DATA_DIR)
    try:
        runpy.run_path(str(DATA_DIR / "retrieve_data.py"), run_name="__main__")
    finally:
        os.chdir(cwd)


# ---------------------------------------------------------------- 2. population
def build_population(con):
    print("2/6 population_snapshots.csv")
    pop = con.execute("""
        SELECT record_dt, COUNT(DISTINCT docnbr) AS population
        FROM prison_population_data_sets
        WHERE record_dt IS NOT NULL
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
    print("3/6 admissions.csv")
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
    print("4/6 exits.csv")
    ex = ex.assign(month=month_floor(ex['release_dt']))
    out = (ex.groupby(['month', 'exit_reason', 'discrsn', 'sex', 'race', 'age_group',
                       'county', 'crime_class', 'relinst'], dropna=False, observed=True)
             .size().reset_index(name='n'))
    out.to_csv(DATA_DIR / "exits.csv", index=False)


# ---------------------------------------------------------------- 5. recidivism
def build_recidivism(adm: pd.DataFrame, ex: pd.DataFrame):
    print("5/6 recidivism.csv")
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
    print("6/6 il_counties.geojson")
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
    build_inc_data()
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        build_population(con)
        adm = load_admissions(con)
        ex = load_exits(con)
    finally:
        con.close()
    build_admissions(adm)
    build_exits(ex)
    build_recidivism(adm, ex)
    build_geojson()
    check_county_names(adm)
    print("done")
