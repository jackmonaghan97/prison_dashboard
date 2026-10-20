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
    """Comptroller spend by object and month; `year` is the fiscal year, `dt` the calendar month."""
    return pd.read_csv(DATA_DIR / "expenses.csv", parse_dates=["dt"])


@lru_cache
def population_snapshots() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "population_snapshots.csv", parse_dates=["record_dt"])
    df["year"] = df["record_dt"].dt.year
    df["fiscal_year"] = fiscal_year(df["record_dt"])
    return df

CRIME_COLS = ["Person", "Property", "Public Order", "Drug"]

@lru_cache
def rates() -> pd.DataFrame:
    """
    One row per (prison year, county, age, sex, race) with the ACS residents and the June 30
    prison counts (see build_rates in data/build_data.py). `residents` is `gen_population`
    with the Hispanic overlay zeroed, so a total across races counts each person once.
    """
    return pd.read_csv(DATA_DIR / "rates.csv")


def census_years() -> tuple[int, int]:
    """First and last ACS year behind the rates."""
    y = rates()["census_year"]
    return int(y.min()), int(y.max())


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
def il_outline() -> tuple[list, list]:
    """The state line around the county map (lon / lat lists), for the choropleths."""
    from . import viz
    return viz.outer_boundary(il_counties())


@lru_cache
def il_counties() -> dict:
    return json.loads((DATA_DIR / "il_counties.geojson").read_text())


@lru_cache
def county_population() -> pd.DataFrame:
    """Total census population per county per year (from the rates table), each resident once."""
    r = rates()
    return (r.groupby(["county", "year"], as_index=False)["residents"].sum()
             .rename(columns={"residents": "gen_population"}))


def warm_cache() -> None:
    """Read every file once at startup so the first session doesn't pay for parsing."""
    for loader in (expenses, population_snapshots, rates, admissions, exits,
                   recidivism, il_counties, il_outline, county_population):
        loader()
