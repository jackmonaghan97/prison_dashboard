"""Overview - one large tile per dashboard; clicking a tile opens it."""
from shiny import reactive, ui

# (nav value, title, what it answers, what is inside, data source)
TILES = [
    ("rates", "Population & rates",
     "How many people are in IDOC custody, where they were sentenced, and how incarceration "
     "rates differ by race, sex, age and county.",
     ["People in custody & rate per 100k", "County map", "Population trend by race / sex / age / offense",
      "Rates by sex, race and age", "Black : White disparity over time", "County table"],
     "IDOC year-end population data sets · U.S. Census ACS (denominators)"),
    ("flows", "Admissions & exits",
     "How many people enter and leave prison each period, why they are admitted, and how "
     "they are released.",
     ["Admissions vs. exits & net change", "Admissions by type", "Exits by reason", "Yearly table"],
     "IDOC admissions and exits data sets, 2018 onward"),
    ("recidivism", "Recidivism",
     "What share of people released from IDOC return within 1, 2 or 3 years, and how that "
     "differs by return type, race, age and offense.",
     ["Recidivism rate by release year and return type", "Cumulative return curves",
      "Rates by race, age and offense class", "Cohort table"],
     "IDOC exits linked to later admissions (releases from 2018)"),
    ("expenses", "Expenses",
     "What IDOC spends each fiscal year, where the money goes, and the cost per inmate.",
     ["Expense per inmate by fiscal year", "Spend by category", "Monthly spend & top line items",
      "Category × month table"],
     "Illinois Comptroller expenditures by object code · IDOC headcounts"),
]


def page_ui():
    tiles = [
        ui.input_action_button(
            f"go_{value}",
            ui.div(
                ui.h2(title, class_="tile-title"),
                ui.p(blurb, class_="tile-blurb"),
                ui.div(*[ui.span(item, class_="tile-chip") for item in items], class_="tile-chips"),
                ui.p(ui.span("Data: ", class_="fw-semibold"), source, class_="tile-source"),
                ui.span("Open dashboard →", class_="tile-cta"),
                class_="tile-body",
            ),
            class_="home-tile",
        )
        for value, title, blurb, items, source in TILES
    ]
    return ui.div(
        ui.div(
            ui.h1("Illinois Prisons", class_="home-heading"),
            ui.p("Population, admissions and releases, recidivism and spending in the Illinois "
                 "Department of Corrections. Pick a dashboard to start; every page has filters in "
                 "the sidebar and a table view at the bottom.", class_="home-lead"),
            class_="home-intro",
        ),
        ui.layout_column_wrap(*tiles, width=1 / 2, fill=False, heights_equal="all", class_="home-grid"),
        class_="home",
    )


def page_server(input, nav_id: str = "nav"):
    """Wire each tile to its nav panel."""
    for value, *_ in TILES:
        def _make(v):
            @reactive.effect
            @reactive.event(input[f"go_{v}"])
            def _go():
                ui.update_navset(nav_id, selected=v)
        _make(value)
