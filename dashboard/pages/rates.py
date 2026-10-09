"""Page 1 - prison population by sentencing county, incarceration rates per 100k and disparities."""
import pandas as pd
from shiny import module, reactive, render, ui

from .. import data, viz
from ..common import demo_filters, download_footer, isin_or_all, note, reset_button, reset_demo

PER = 100_000
OFFENSE_CHOICES = {"total": "All offenses", "Person": "Person", "Property": "Property",
                   "Drug": "Drug", "Public Order": "Public Order"}
# disparity lines: group compared with the White rate -> (line dash, marker shape)
DISPARITY = {"Black": ("solid", "circle"), "Hispanic": ("dash", "square")}
BREAKDOWNS = {"race": "Race / ethnicity", "sex": "Sex", "age": "Age group", "offense": "Offense class"}
METRICS = {"rate": "Rate per 100k", "count": "People in custody"}


def _residents(df: pd.DataFrame) -> float:
    
    """
    Residents in a selection, each counted once. `residents` leaves the Hispanic overlay
    out (those people are already in a race group); only when the selection is Hispanic
    alone does that sum come to zero, and then the Hispanic count itself is the denominator.
    """
    
    alone = df["residents"].sum()
    return alone if alone else df["gen_population"].sum()


def _rate(df: pd.DataFrame, col: str) -> float:
    pop = _residents(df)
    return df[col].sum() / pop * PER if pop else float("nan")


def _rate_by(df: pd.DataFrame, by, col: str) -> pd.DataFrame:
    """Counts, residents (see _residents) and rate per group; `gen_population` is the denominator used."""
    g = df.groupby(by, as_index=False)[[col, "gen_population", "residents"]].sum()
    g["gen_population"] = g["residents"].where(g["residents"] > 0, g["gen_population"])
    g["rate"] = g[col] / g["gen_population"] * PER
    return g.drop(columns="residents").rename(columns={col: "incarcerated"})


@module.ui
def page_ui():
    
    r = data.rates()
    years = sorted(int(y) for y in r["year"].unique())
    counties = ["All counties"] + sorted(r["county"].unique())
    census_last = data.census_years()[1]
    return ui.layout_sidebar(
        
        ui.sidebar(
            
            reset_button(),
            ui.input_slider("year", "Select year (view is for June 30th)", min=years[0], max=years[-1],
                            value=years[-1], step=1, sep=""),
            ui.input_select("county", "Sentencing county", choices=counties, selected="All counties"),
            ui.input_select("offense", "Offense class", choices=OFFENSE_CHOICES, selected="total"),
            *demo_filters(),
            ui.hr(),
            ui.input_radio_buttons("metric", "Bar charts show", choices=METRICS, selected="rate", inline=True),
            ui.input_radio_buttons("breakdown", "Population trend by", choices=BREAKDOWNS, selected="race"),
            
            note(
                '''Population is defined as the people in IDOC custody on June 30, the end of the DOC fiscal year by county of sentencing. 
                
                Rate is defined as that population per 100,000 residents of the same sex, race and age group as measured by the US cesnsus ACS datasets.
                
                Disparities are the Black or Hispanic rate divided by the White rate.'''),
            
            width=300,
        ),
        ui.layout_column_wrap(
            ui.value_box("People in custody", ui.output_text("kpi_pop"), ui.output_text("kpi_pop_sub"),
                         theme="primary"),
            ui.value_box("Incarceration rate", ui.output_text("kpi_rate"), "per 100,000 residents"),
            ui.value_box(ui.output_text("kpi_change_title"), ui.output_text("kpi_change"),
                         ui.output_text("kpi_change_sub")),
            fill=False,
        ),
        ui.layout_columns(
            ui.card(ui.card_header(ui.output_text("map_title")), viz.output_plot("map_chart"),
                    ui.card_footer(note(
                        'Above is a heat map of Illinois showing the rate per 100K residents for each county. White displays '
                        'low incarceration rate and dark blue is high. If a county is selected to the left, the county will '
                        'be outlines in yellow. A table view of the map is shown to the right.'
                    ))),

            ui.card(ui.card_header(ui.output_text("table_title")), ui.output_ui("table"),
                    download_footer("table_csv", "the county table",
                                    note(
                                    'The table above shows the number of poeople in custody'
                                    'by the DOC, number of residents in that county, and the rate  of' 
                                    'incarceration per 100,000 residents.'))),
            col_widths={"sm": 12, "xl": [5, 7]},
        ),
        ui.layout_columns(
            ui.card(ui.card_header(ui.output_text("sex_title")), viz.output_plot("sex_chart"),
                    ui.output_ui("sex_table"), ui.card_footer( 
                        note(
                        'Above displays the numer of people incarcerated by the DOC as their reported sexes by sex.')) 
                    ),
            ui.card(ui.card_header(ui.output_text("race_title")), viz.output_plot("race_chart"),
                    ui.output_ui("race_table"),  ui.card_footer(
                        note(
                        'Above displays the numer of people incarcerated by the DOC as '
                        'their reported race. The DOC does not report race of those identified as '
                        'Hispanic.')) 
                    ),
            ui.card(ui.card_header(ui.output_text("age_title")), viz.output_plot("age_chart"),
                    ui.output_ui("age_table"), ui.card_footer(
                        note('' \
                        'Above displays the numer of people incarcerated by the DOC as their age '
                        'at the time of incarceration.'))
                    ),
            col_widths={"sm": 12, "xl": [3, 4, 5]}
        ),

        ui.layout_columns(
            ui.card(ui.card_header("Black : White and Hispanic : White disparity ratios over time"),
                    viz.output_plot("ratio_chart"), ui.output_ui("ratio_table"),
                    download_footer("ratio_csv", "the disparity ratio chart",
                                    note(
                                        'The line plot above shows the racial disparity for Black '
                                        'and Hispanic people over time.'))
                    ),

            ui.card(ui.card_header(ui.output_text("trend_title")), viz.output_plot("trend_chart"),
                    ui.output_ui("trend_table"),
                    download_footer("trend_csv", "the population trend table",
                                    note(
                                        'The stacked area plot above shows the distribution of people '
                                        'incarcerated over time. There are multiple breakdowns to be seleceted '
                                        'in the sidebar to the left.'))
                    ),
                                    
            col_widths={"sm": 12, "xl": [4, 8]},
        ),
    )

@module.server
def page_server(input, output, session):
    years = sorted(int(y) for y in data.rates()["year"].unique())

    @reactive.effect
    @reactive.event(input.reset)
    def _reset():
        
        ui.update_slider("year", value=years[-1])
        ui.update_select("county", selected="All counties")
        ui.update_select("offense", selected="total")
        reset_demo(has_crime=False)
        ui.update_radio_buttons("breakdown", selected="race")
        ui.update_radio_buttons("metric", selected="rate")

    @reactive.calc
    def col() -> str:
        return input.offense()

    def _county(df: pd.DataFrame) -> pd.DataFrame:
        if input.county() == "All counties":
            return df
        return df.loc[df["county"] == input.county()]

    @reactive.calc
    def demo_all() -> pd.DataFrame:
        """Sex / race / age filters only - every county, every year (map, table, trend)."""
        df = data.rates()
        mask = (isin_or_all(df["sex"], input.sex()) & isin_or_all(df["age"], input.age())
                & isin_or_all(df["race"], input.race()))
        return df.loc[mask]

    @reactive.calc
    def base() -> pd.DataFrame:
        """Everything except the year and race filters (for B:W comparisons)."""
        df = data.rates()
        return _county(df.loc[isin_or_all(df["sex"], input.sex()) & isin_or_all(df["age"], input.age())])

    @reactive.calc
    def year_df() -> pd.DataFrame:
        b = base()
        return b.loc[b["year"] == input.year()]

    @reactive.calc
    def year_all() -> pd.DataFrame:
        d = demo_all()
        return d.loc[d["year"] == input.year()]

    @reactive.calc
    def selected() -> pd.DataFrame:
        """All filters, selected year."""
        return _county(year_all())

    @reactive.calc
    def trend() -> pd.DataFrame:
        """All filters, every year."""
        return _county(demo_all())

    @reactive.calc
    def disparity_by_year() -> pd.DataFrame:
        """Rate per year for each DISPARITY group and White, and each group's ratio to White."""
        g = _rate_by(base(), ["year", "race"], col())
        piv = g.pivot(index="year", columns="race", values="rate").reindex(columns=[*DISPARITY, "White"])
        out = pd.DataFrame(index=piv.index)
        for grp in piv.columns:
            out[f"{grp} rate per 100k"] = piv[grp]
        for grp in DISPARITY:
            out[f"{grp} : White"] = piv[grp] / piv["White"]
        return out

    @reactive.calc
    def pop_by_year() -> pd.Series:
        return trend().groupby("year")[col()].sum().reindex(years).fillna(0)

    def _where() -> str:
        return "Illinois" if input.county() == "All counties" else f"{input.county()} County"

    # ---- KPIs
    @render.text
    def kpi_pop():
        return viz.fmt_int(selected()[col()].sum())

    @render.text
    def kpi_pop_sub():
        return f"sentenced in {_where()}, June 30, {input.year()}"

    @render.text
    def kpi_rate():
        return f"{_rate(selected(), col()):,.0f}"

    @render.text
    def kpi_change_title():
        return f"Change vs {input.year() - 1}"

    @render.text
    def kpi_change():
        s = pop_by_year()
        prev = s.get(input.year() - 1)
        if prev is None or input.year() - 1 not in s.index:
            return "–"
        delta = s[input.year()] - prev
        return f"{'▲' if delta >= 0 else '▼'} {abs(delta):,.0f}"

    @render.text
    def kpi_change_sub():
        s = pop_by_year()
        prev = s.get(input.year() - 1)
        if not prev:
            return "no prior year"
        pct = (s[input.year()] - prev) / prev
        return f"{pct:+.1%} from {prev:,.0f} people in custody"

    @render.text
    def map_title():
        return f"Incarceration rate by sentencing county, June 30, {input.year()}"

    @render.text
    def trend_title():
        return f"People in custody by {BREAKDOWNS[input.breakdown()].lower()}, {_where()}"

    def _bar_title(what):
        return f"{METRICS[input.metric()]} by {what}, {input.year()}"

    @render.text
    def sex_title():
        return _bar_title("sex")

    @render.text
    def race_title():
        return _bar_title("race")

    @render.text
    def age_title():
        return _bar_title("age")

    @render.text
    def table_title():
        return f"Table view - by sentencing county, June 30, {input.year()}, {OFFENSE_CHOICES[col()].lower()}"

    # ---- charts
    @viz.render_plot
    def map_chart():
        g = _rate_by(year_all(), "county", col())
        g = g.loc[g["gen_population"] > 0].set_index("county")
        if g.empty:
            return viz.empty_figure(height=480)
        highlight = None if input.county() == "All counties" else input.county()
        fig = viz.choropleth(
            data.il_counties(), g["rate"], height=480,
            customdata=g[["incarcerated", "gen_population"]].values,
            hovertemplate="<b>%{location}</b><br>%{z:,.0f} per 100k<br>"
                          "%{customdata[0]:,.0f} in custody / %{customdata[1]:,.0f} residents<extra></extra>",
            highlight=highlight, outline=data.il_outline(),
        )
        top = g["rate"].sort_values(ascending=False).head(5)
        return viz.describe(fig, f"Map of Illinois counties shaded by incarceration rate per 100,000 residents, "
                                 f"{input.year()}, {OFFENSE_CHOICES[col()].lower()}: {len(g)} counties from "
                                 f"{g['rate'].min():,.0f} to {g['rate'].max():,.0f}; highest {viz.alt_values(top.items())}."
                                 " Colors run from white (lowest) to dark blue (highest) on a grey background."
                                 + (f" {highlight} County is outlined in yellow." if highlight else ""))

    @reactive.calc
    def trend_piv() -> tuple[pd.DataFrame, dict, object]:
        """Year x group table behind the trend chart, with its colors and label function."""
        df = trend()
        b = input.breakdown()
        if b == "offense":
            long = df.melt(id_vars="year", value_vars=data.CRIME_COLS, var_name="group", value_name="n")
            order, colors = [c for c in viz.CRIME_ORDER if c in data.CRIME_COLS], viz.CRIME_COLOR
            if col() != "total":
                long = long.loc[long["group"] == col()]
        else:
            long = df[["year", b, col()]].rename(columns={b: "group", col(): "n"})
            order, colors = {"race": (viz.RACE_ORDER, viz.RACE_COLOR), "sex": (viz.SEX_ORDER, viz.SEX_COLOR),
                             "age": (viz.AGE_ORDER, viz.AGE_COLOR)}[b]
        piv = long.pivot_table(index="year", columns="group", values="n", aggfunc="sum").reindex(years).fillna(0)
        piv = piv[[g for g in order if g in piv.columns]]
        label = viz.age_label if b == "age" else (lambda c: c)
        return piv, colors, label

    @viz.render_plot
    def trend_chart():
        piv, colors, label = trend_piv()
        b = input.breakdown()
        if piv.empty or not piv.values.sum():
            return viz.empty_figure(height=480)
        fig = viz.figure(480, hovermode="x unified", yaxis=dict(tickformat=",.0f", rangemode="tozero"),
                         xaxis=dict(dtick=2))
        viz.stacked_area(fig, piv, colors, label)
        fig.add_vline(x=input.year(), line=dict(color=viz.AXIS, width=1))
        last = piv.index[-1]
        return viz.describe(fig, f"Stacked area chart of people in custody sentenced in {_where()} by "
                                 f"{BREAKDOWNS[b].lower()}, yearly {piv.index[0]} to {last}. "
                                 f"Total {piv.sum(axis=1).iloc[0]:,.0f} in {piv.index[0]} and "
                                 f"{piv.sum(axis=1).iloc[-1]:,.0f} in {last}; in {last}: "
                                 f"{viz.alt_values((label(c), piv.loc[last, c]) for c in piv.columns)}.")

    @render.ui
    def trend_table():
        piv, _, label = trend_piv()
        if piv.empty or not piv.values.sum():
            return None
        return viz.layer_table(piv.sort_index(ascending=False), index_name="Fiscal year", labels=label)

    @viz.download_csv(lambda: f"people_in_custody_by_{input.breakdown()}_{_where()}.csv".replace(" ", "_"))
    def trend_csv():
        piv, _, label = trend_piv()
        out = piv.rename(columns=label)
        out["Total"] = out.sum(axis=1)
        return out.rename_axis("Fiscal year").reset_index()

    def _bar_data(by, order) -> pd.DataFrame:
        g = _rate_by(selected(), by, col())
        return g.set_index(by).reindex([o for o in order if o in g[by].values]).reset_index()

    def _bar_table(by, order, labels=None, name="Group"):
        g = _bar_data(by, order)
        if g.empty or not g["incarcerated"].sum():
            return None
        t = pd.DataFrame({"In custody": g["incarcerated"].values, "Residents": g["gen_population"].values,
                          "Rate per 100k": g["rate"].values},
                         index=[labels(v) for v in g[by]] if labels else g[by].values)
        return viz.layer_table(t, index_name=name, total=False)

    def _bar(by, order, colors, labels=None, height=300, what_by="group"):
        g = _bar_data(by, order)
        if g.empty or not g["incarcerated"].sum():
            return viz.empty_figure(height=height)
        rate = input.metric() == "rate"
        y = g["rate"] if rate else g["incarcerated"]
        fig = viz.figure(height, yaxis=dict(tickformat=",.0f"))
        fig.add_bar(x=[labels(v) for v in g[by]] if labels else g[by], y=y,
                    marker=dict(color=[colors[v] for v in g[by]]),
                    text=[f"{v:,.0f}" for v in y], textposition="outside", textfont=dict(color=viz.INK_2),
                    customdata=g[["incarcerated", "gen_population", "rate"]].values,
                    hovertemplate="<b>%{x}</b><br>%{customdata[2]:,.0f} per 100k<br>"
                                  "%{customdata[0]:,.0f} in custody / %{customdata[1]:,.0f} residents"
                                  "<extra></extra>")
        fig.update_layout(showlegend=False, yaxis_range=[0, y.max() * 1.18])
        names = [labels(v) for v in g[by]] if labels else list(g[by])
        what = "incarceration rate per 100,000 residents" if rate else "people in custody"
        return viz.describe(fig, f"Bar chart of {what} by {what_by}, {_where()}, {input.year()}: "
                                 f"{viz.alt_values(zip(names, y))}.")

    @viz.render_plot
    def sex_chart():
        return _bar("sex", viz.SEX_ORDER, viz.SEX_COLOR, what_by="sex")

    @viz.render_plot
    def race_chart():
        return _bar("race", viz.RACE_ORDER, viz.RACE_COLOR, what_by="race / ethnicity")

    @viz.render_plot
    def age_chart():
        return _bar("age", viz.AGE_ORDER, viz.AGE_COLOR, labels=viz.age_label, what_by="age group")

    @render.ui
    def sex_table():
        return _bar_table("sex", viz.SEX_ORDER, name="Sex")

    @render.ui
    def race_table():
        return _bar_table("race", viz.RACE_ORDER, name="Race / ethnicity")

    @render.ui
    def age_table():
        return _bar_table("age", viz.AGE_ORDER, labels=viz.age_label, name="Age group")

    @viz.render_plot
    def ratio_chart():
        d = disparity_by_year()
        lines = {grp: d[f"{grp} : White"].dropna() for grp in DISPARITY}
        lines = {grp: r for grp, r in lines.items() if not r.empty}
        if not lines:
            return viz.empty_figure()
        fig = viz.figure(480, yaxis=dict(rangemode="tozero", ticksuffix="×"), xaxis=dict(dtick=2),
                         margin=dict(r=96))
        # each line has its own color, dash and marker shape, and is named at its right-hand end,
        # so the two read apart without color or a legend
        for grp, r in lines.items():
            color = viz.RACE_COLOR[grp]
            dash, symbol = DISPARITY[grp]
            fig.add_scatter(name=f"{grp} : White", x=r.index, y=r.values, mode="lines+markers",
                            line=dict(color=color, width=2, dash=dash),
                            marker=dict(size=7, symbol=symbol, color=color, line=dict(color=viz.SURFACE, width=1)),
                            hovertemplate=f"<b>{grp}</b> %{{x}}<br>%{{y:.2f}}× the White rate<extra></extra>")
            fig.add_annotation(x=r.index[-1], y=r.iloc[-1], text=f"{grp} : White", showarrow=False,
                               xanchor="left", xshift=8, font=dict(size=11, color=viz.INK_2),
                               bgcolor=viz.rgba(viz.SURFACE, 0.85))
        fig.add_hline(y=1, line=dict(color=viz.AXIS, width=1), annotation_text="parity",
                      annotation_position="bottom left", annotation_font=dict(color=viz.MUTED))
        fig.add_vline(x=input.year(), line=dict(color=viz.AXIS, width=1))
        first = min(r.index[0] for r in lines.values())
        last = max(r.index[-1] for r in lines.values())
        # fixed x range: the end labels sit in the right margin and must not stretch the axis
        fig.update_layout(showlegend=False, xaxis_range=[first - 0.5, last + 0.5])
        parts = [f"{grp} to White ({'solid line, circles' if DISPARITY[grp][0] == 'solid' else 'dashed line, squares'}): "
                 f"{viz.alt_values(r.items(), '{:.1f}x')}" for grp, r in lines.items()]
        return viz.describe(fig, f"Line chart of incarceration-rate ratios to the White rate in {_where()}, "
                                 f"yearly {first} to {last}, one line per group. " + ". ".join(parts) +
                                 ". A horizontal line marks parity at 1.0.")

    @render.ui
    def ratio_table():
        d = disparity_by_year().dropna(how="all")
        if d.empty:
            return None
        fmt = {c: "{:.2f}" if c.endswith(": White") else "{:,.0f}" for c in d.columns}
        return viz.layer_table(d.sort_index(ascending=False), fmt=fmt, index_name="Fiscal year", total=False)

    @viz.download_csv(lambda: f"disparity_ratios_{_where()}_{OFFENSE_CHOICES[col()]}.csv".replace(" ", "_"))
    def ratio_csv():
        return disparity_by_year().rename_axis("Fiscal year").reset_index()

    @reactive.calc
    def county_table() -> pd.DataFrame:
        """Statewide row, then every county by rate (selected year, demographic filters)."""
        c = col()
        d = year_all()
        state = pd.DataFrame({"incarcerated": [d[c].sum()], "gen_population": [_residents(d)]}, index=["All Illinois"])
        state["rate"] = state["incarcerated"] / state["gen_population"] * PER
        counties = _rate_by(d, "county", c).set_index("county")
        counties = counties.loc[counties["gen_population"] > 0].sort_values("rate", ascending=False)
        return pd.concat([state, counties])

    @viz.download_csv(lambda: f"incarceration_by_county_{input.year()}_{OFFENSE_CHOICES[col()]}.csv".replace(" ", "_"))
    def table_csv():
        out = county_table()
        return pd.DataFrame({"County": out.index.astype(str), "Fiscal year": input.year(),
                             "Offense class": OFFENSE_CHOICES[col()], "Residents": out["gen_population"].values,
                             "In custody": out["incarcerated"].values, "Rate per 100k": out["rate"].values})

    @render.ui
    def table():
        out = county_table()

        cols = {"County": (None, None), "Residents": ("gen_population", "{:,.0f}"),
                "In custody": ("incarcerated", "{:,.0f}"), "Rate per 100k": ("rate", "{:,.0f}")}
        raw = pd.DataFrame({"County": out.index.astype(str)})
        shown = raw.copy()
        for name, (src, fmt) in cols.items():
            if src is None:
                continue
            raw[name] = out[src].values
            shown[name] = out[src].map(lambda v: "–" if pd.isna(v) else fmt.format(v)).values
        return viz.sortable_table(shown, raw, pinned_rows=1, height="400px")
