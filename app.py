"""
Illinois Department of Corrections dashboard.

Run:   shiny run app.py --reload
Data:  python data/build_data.py   (writes the CSVs in data/ from the DuckDB source)
"""
from pathlib import Path

from shiny import App, ui

from dashboard import data, viz
from dashboard.pages import expenses, flows, home, rates, recidivism

data.warm_cache()

app_ui = ui.page_navbar(
    ui.nav_panel("Overview", home.page_ui(), value="home"),
    ui.nav_panel("Population & rates", rates.page_ui("rates"), value="rates"),
    ui.nav_panel("Admissions & exits", flows.page_ui("flows"), value="flows"),
    ui.nav_panel("Recidivism", recidivism.page_ui("recidivism"), value="recidivism"),
    ui.nav_panel("Expenses", expenses.page_ui("expenses"), value="expenses"),
    ui.nav_spacer(),
    ui.nav_control(ui.a("Source: IDOC & IL Comptroller", class_="nav-link text-muted small",
                        href="https://idoc.illinois.gov/reportsandstatistics/prison-population-data-sets.html",
                        target="_blank")),
    title="Illinois Prisons",
    id="nav",
    navbar_options=ui.navbar_options(bg=viz.NAVY, theme="dark", underline=False),
    header=[ui.tags.script(src="/plotly/plotly.min.js"), ui.tags.link(rel="stylesheet", href="/www/styles.css"),
            ui.tags.script(src="/www/plots.js"), ui.tags.script(src="/www/sortable.js")],
    fillable=False,
)


def server(input, output, session):
    home.page_server(input, "nav")
    rates.page_server("rates")
    flows.page_server("flows")
    recidivism.page_server("recidivism")
    expenses.page_server("expenses")


# plotly.min.js is served from the installed plotly package and the map's base-map topojson
# from data/topojson, so no CDN is needed; the page's own CSS / JS live in www/
app = App(app_ui, server, static_assets={"/plotly": viz.PLOTLY_JS_DIR, "/topojson": viz.TOPOJSON_DIR,
                                         "/www": Path(__file__).parent / "www"})
