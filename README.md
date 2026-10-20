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
www/                      served at /www
  styles.css              page styles (colors match the palette in viz.py)
  plots.js                re-fits charts when their card resizes or their tab opens
  sortable.js             click-to-sort for viz.sortable_table
data/
  build_data.py           rebuilds every file below in its final shape (dashboard/data.py only reads them)
  data_download.csv       Comptroller expenditures by object code (downloaded manually; input to expenses.csv)
  expenses.csv            Comptroller spend by object and month (fiscal year + calendar month)
  rates.csv               June 30 prison counts x ACS residents per year / county / age / sex / race
  population_snapshots.csv  IDOC headcount on June 30 of each year
  admissions.csv          monthly admissions by type / sex / race / age / county / offense
  exits.csv               monthly exits by reason / sex / race / age / county / offense
  recidivism.csv          one de-identified row per release event with days to first return
  il_counties.geojson     Illinois county boundaries for the map
  topojson/world_110m.json  plotly's base-map file for the map, served by the app (copied from cdn.plot.ly)
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

## Accessibility

- Every chart carries alternative text describing its contents (not an analysis): the
  chart div has `role="img"` and an `aria-label`, followed by a visually hidden paragraph
  with the same text. Set it with `viz.describe(fig, text)`; `viz.alt_values()` formats
  the value lists.
- The county map draws the state line in black and shades counties on `viz.MAP_SCALE`,
  a single blue hue from white (low) to dark navy (high), on a grey background
  (`viz.MAP_BG`) so the white end never meets the white page. County borders follow the
  fill (`viz.map_border`): dark grey on light fills, white on dark ones, whichever is at
  least 3:1 against the county. A selected county is outlined in yellow
  (`viz.MAP_HIGHLIGHT`) over a wider black line: black carries the contrast on the five
  lightest fills (19.7, 13.9, 8.9, 5.3, 3.1:1), yellow on the darker ones (4.5, 8.5,
  11.7:1), and yellow on black is 14:1.
- Every chart and table has a "Download CSV" button with the numbers behind it
  (`common.download_button` / `common.download_footer` in the UI, `viz.download_csv` on
  the server). A chart that already has a table on the page (the county map, the
  admissions / exits / net change chart) has no button of its own; its table has one.
  The sex / race / age bar charts on Population & rates have a table view instead.
  Each button's accessible name starts with the visible "Download CSV" and names the
  chart or table ("Download CSV of the county table").
- The disparity chart has a table view (rates and ratios per year) as well as its CSV, and
  separates the Black : White and Hispanic : White lines by dash
  and marker shape as well as color, and names each line at its right-hand end.
- The annual spending donut labels every slice with its category and share.
- Every stacked chart (admissions by type, the two expense stacks, the population trend
  area) has a "Show the chart's values as a table" disclosure under it (`viz.layer_table`)
  listing every layer per period, so thin layers can be read without hovering. The same
  disclosure (`total=False`) gives the bar charts and disparity chart a table view.
- Stacked area charts (`viz.stacked_area`) separate bands with a surface-colored seam and
  name each band at its right-hand end, so the stack reads without color.
- Multi-line charts give every line a different marker shape (`viz.SYMBOLS`).

## Definitions

- **Filters** - the sex / race / age / offense dropdowns are multi-select; leaving one
  empty ("All") applies no filter. "Reset filters" restores every control on the page.
- **Expense per inmate** - total expenditures in the fiscal year ÷ IDOC's
  headcount on June 30, the last day of that fiscal year. The Comptroller's "Year" is the state
  fiscal year (July-June, named for the year it ends in), so FY2026 = July 2025 - June
  2026; a year with fewer than 12 reported months is marked partial.
- **Incarceration rate** - people in custody on June 30 (the end of the state fiscal year
  and IDOC's reporting date, by sentencing county) per 100,000 ACS residents of the same
  sex, race and age group. ACS race groups include Hispanic residents; Hispanic is also its
  own group (an ethnicity overlay), so any total across races uses the race groups only
  and leaves Hispanic out - otherwise Illinois would count 15M residents instead of 12.7M.
  Prison years after the newest ACS release reuse that release's denominators.
- **Net change, COVID share** - the net-change tile also says what share of the net change
  in the selected years happened in April-June 2020, when the population fell by about a
  quarter.
- **Disparity** - Black rate ÷ White rate, and Hispanic rate ÷ White rate. The Hispanic
  rate uses Hispanic residents as its denominator; the White rate uses all White residents
  (ACS race groups include Hispanic residents).
- **Average monthly spend** - each month of the fiscal year (July-June) averaged over the
  complete fiscal years (12 months reported); partial years are left out.
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

The app reads only the files in `data/` (including the map's base-map topojson, so
the map does not depend on cdn.plot.ly) and `plotly.min.js` from the installed plotly
package, so a container just needs `requirements.txt`, `app.py`, `dashboard/` and
`data/`. Start it with `shiny run app.py --host 0.0.0.0 --port $PORT`.
