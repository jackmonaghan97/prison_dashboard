"""Load the CSVs produced by data/build_data.py once at startup."""
import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


FISCAL_MONTHS = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun"]


def fiscal_year(dt: pd.Series) -> pd.Series:
    """Illinois fiscal year: July-June, named for the calendar year in which it ends."""
    return dt.dt.year + (dt.dt.month >= 7).astype(int)


@lru_cache
def expenses() -> pd.DataFrame:
    """
    Comptroller spend by object and month. The Comptroller's "Year" is the state fiscal
    year (July-June), so Jul-Dec rows belong to the previous calendar year; `year` keeps
    the fiscal year and `dt` is the real calendar month.
    """
    df = pd.read_csv(DATA_DIR / "data_download.csv")
    df = df.rename(columns={"Object": "object", "Object_cat": "category", "Year": "year"})
    month_num = df["month"].map({m: i for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)})
    cal_year = df["year"] - (month_num >= 7).astype(int)
    df["dt"] = pd.to_datetime(dict(year=cal_year, month=month_num, day=1))
    return df[["year", "month", "dt", "object", "category", "amount"]]


@lru_cache
def population_snapshots() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "population_snapshots.csv", parse_dates=["record_dt"])
    df["year"] = df["record_dt"].dt.year
    df["fiscal_year"] = fiscal_year(df["record_dt"])
    return df


CRIME_COLS = ["Person", "Property", "Public Order", "Drug"]
CENSUS_YEARS = (2009, 2023)  # ACS years available; prison years outside use the nearest


@lru_cache
def rates() -> pd.DataFrame:
    """
    One row per (prison year, county, age, sex, race) with the census denominator and
    year-end prison counts. inc_data.csv is census-cell x prison-year, so a census year
    with several prison years (2023 -> 2023/24/25) repeats its population; rebuild the
    grid here so every prison year has every census cell exactly once.
    """
    df = pd.read_csv(DATA_DIR / "inc_data.csv")
    df["county"] = df["county_name"].str.replace(" County, Illinois", "", regex=False)
    df["sex"] = df["sex"].str.title()
    df["race"] = df["race"].str.title()
    key = ["county", "age", "sex", "race"]

    census = df.drop_duplicates(["year_cen"] + key)[["year_cen"] + key + ["gen_population"]]
    prison = df.loc[df["total"] > 0, ["year_pri"] + key + CRIME_COLS]
    prison["year_pri"] = prison["year_pri"].astype(int)

    years = pd.DataFrame({"year": range(CENSUS_YEARS[0], int(prison["year_pri"].max()) + 1)})
    years["year_cen"] = years["year"].clip(*CENSUS_YEARS)
    grid = years.merge(census, on="year_cen")
    out = grid.merge(prison, left_on=["year"] + key, right_on=["year_pri"] + key, how="left")
    out[CRIME_COLS] = out[CRIME_COLS].fillna(0)
    out["total"] = out[CRIME_COLS].sum(axis=1)
    return out[["year", "county", "age", "sex", "race", "gen_population"] + CRIME_COLS + ["total"]]


@lru_cache
def admissions() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "admissions.csv", parse_dates=["month"])


@lru_cache
def exits() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "exits.csv", parse_dates=["month"])


@lru_cache
def recidivism() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "recidivism.csv", parse_dates=["release_month"])


@lru_cache
def il_counties() -> dict:
    return json.loads((DATA_DIR / "il_counties.geojson").read_text())


@lru_cache
def county_population() -> pd.DataFrame:
    """Total census population per county per year (from the rates table)."""
    r = rates()
    return r.groupby(["county", "year"], as_index=False)["gen_population"].sum()


def warm_cache() -> None:
    """Read every file once at startup so the first session doesn't pay for parsing."""
    for loader in (expenses, population_snapshots, rates, admissions, exits,
                   recidivism, il_counties, county_population):
        loader()
