# Illinois Prisons dashboard

A Python Shiny dashboard over IDOC prison population, admission and exit data sets,
the ACS census, and Illinois Comptroller expenditure data.

```
app.py                    Shiny entry point (navbar: overview + the four pages)
dashboard/
  data.py                 loads the CSVs once at startup (lru_cache)
  viz.py                  palette, fixed entity colors, plotly base layout, HTML renderer
  common.py               shared multi-select filters, reset button, filter helpers
  pages/
    home.py               overview page - one tile per dashboard
    rates.py              (1) population by sentencing county, rates per 100k, disparity
    flows.py              (2) admissions, exits, net change, admission types, exit reasons
    recidivism.py         (3) return-to-prison rates for release cohorts
    expenses.py           (4) expenditures and expense per inmate, by fiscal year
data/
  build_data.py           rebuilds every CSV below from the DuckDB source
  retrieve_data.py        original census x prison join (called by build_data.py)
  data_download.csv       Comptroller expenditures by object code (downloaded manually)
  inc_data.csv            census cells x prison year-end counts
  population_snapshots.csv  IDOC headcount per snapshot date
  admissions.csv          monthly admissions by type / sex / race / age / county / offense
  exits.csv               monthly exits by reason / sex / race / age / county / offense
  recidivism.csv          one de-identified row per release event with days to first return
  il_counties.geojson     Illinois county boundaries for the map
  idoc_public_map.xlsx    offense description -> offense class
```

## Run locally

```
pip install -r requirements.txt
shiny run app.py --reload
```

## Rebuild the data

`python data/build_data.py` reads the DuckDB file named at the top of the script
(`DB_PATH`) plus `idoc_public_map.xlsx`, and overwrites the CSVs. Needs `duckdb` and
`openpyxl` in addition to `requirements.txt`. The container only needs the CSVs.

## Definitions

- **Filters** - the sex / race / age / offense dropdowns are multi-select; leaving one
  empty ("All") applies no filter. "Reset filters" restores every control on the page.
- **Expense per inmate** - total expenditures in the fiscal year ÷ mean of the IDOC
  headcount snapshots falling in that fiscal year. The Comptroller's "Year" is the state
  fiscal year (July-June, named for the year it ends in), so FY2026 = July 2025 - June
  2026; a year with fewer than 12 reported months is marked partial.
- **Incarceration rate** - people in custody at year end (December snapshot, by sentencing
  county) per 100,000 ACS residents of the same sex, race and age group. ACS race groups
  include Hispanic residents; Hispanic is also its own group. Prison years 2024-25 use
  the 2023 ACS denominators.
- **Disparity** - Black rate ÷ White rate.
- **Recidivism** - a release is any exit to mandatory supervised release or at sentence
  expiration from 2018 on (deaths, reversals, court orders excluded). A return is a later
  admission of a selected type (court admission, new-sentence violator, technical
  violator, other) within the chosen window (1, 2 or 3 years). Only release years that can
  be fully observed for the window are shown; admissions data end Dec 2025.
- **Admissions / exits** - deduplicated to one event per person per day (the FY2020
  exit file lists every exit twice). Exits before 2018 exist in the data but are not shown
  because admissions start in 2018. Every "MSR: ..." exit reason is combined into one
  mandatory supervised release category.

## Deploy

The app reads only the files in `data/` and `plotly.min.js` from the installed plotly
package, so a container just needs `requirements.txt`, `app.py`, `dashboard/` and
`data/`. Start it with `shiny run app.py --host 0.0.0.0 --port $PORT`.
