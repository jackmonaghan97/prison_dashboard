"""Page 1 - prison population by sentencing county, incarceration rates per 100k and disparities."""
import pandas as pd
from shiny import module, reactive, render, ui

from .. import data, viz
from ..common import demo_filters, isin_or_all, note, reset_button, reset_demo

PER = 100_000
OFFENSE_CHOICES = {"total": "All offenses", "Person": "Person", "Property": "Property",
                   "Drug": "Drug", "Public Order": "Public Order"}
BREAKDOWNS = {"race": "Race / ethnicity", "sex": "Sex", "age": "Age group", "offense": "Offense class"}
METRICS = {"rate": "Rate per 100k", "count": "People in custody"}


def _rate(df: pd.DataFrame, col: str) -> float:
    pop = df["gen_population"].sum()
    return df[col].sum() / pop * PER if pop else float("nan")


def _rate_by(df: pd.DataFrame, by, col: str) -> pd.DataFrame:
    g = df.groupby(by, as_index=False)[[col, "gen_population"]].sum()
    g["rate"] = g[col] / g["gen_population"] * PER
    return g.rename(columns={col: "incarcerated"})


@module.ui
def page_ui():
    r = data.rates()
    years = sorted(int(y) for y in r["year"].unique())
    counties = ["All counties"] + sorted(r["county"].unique())
    return ui.layout_sidebar(
        ui.sidebar(
            reset_button(),
            ui.input_slider("year", "Year", min=years[0], max=years[-1], value=years[-1], step=1, sep=""),
            ui.input_select("county", "Sentencing county", choices=counties, selected="All counties"),
            ui.input_select("offense", "Offense class", choices=OFFENSE_CHOICES, selected="total"),
            *demo_filters(),
            ui.hr(),
            ui.input_radio_buttons("breakdown", "Population trend by", choices=BREAKDOWNS, selected="race"),
            ui.input_radio_buttons("metric", "Bar charts show", choices=METRICS, selected="rate", inline=True),
            note("Population = people in IDOC custody at year end, by county of sentencing. "
                 "Rate = that population per 100,000 residents of the same sex, race and age group (ACS). "
                 "Disparity = Black rate ÷ White rate. ACS race groups include Hispanic residents; "
                 "2024–25 use the 2023 ACS denominators."),
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
                    ui.card_footer(note("Rate per 100k residents, by county of sentencing. The county "
                                        "filter outlines a county rather than hiding the others."))),
            ui.card(ui.card_header(ui.output_text("trend_title")), viz.output_plot("trend_chart")),
            col_widths={"sm": 12, "xl": [5, 7]},
        ),
        ui.layout_columns(
            ui.card(ui.card_header(ui.output_text("sex_title")), viz.output_plot("sex_chart")),
            ui.card(ui.card_header(ui.output_text("race_title")), viz.output_plot("race_chart")),
            ui.card(ui.card_header(ui.output_text("age_title")), viz.output_plot("age_chart")),
            col_widths={"sm": 12, "xl": [3, 4, 5]},
        ),
        ui.layout_columns(
            ui.card(ui.card_header("Black : White disparity ratio over time"), viz.output_plot("ratio_chart"),
                    ui.card_footer(note("1.0 = parity. Uses the sex, age, county and offense filters."))),
            ui.card(ui.card_header(ui.output_text("table_title")), ui.output_ui("table"),
                    ui.card_footer(note("Click a column header to sort. The statewide row stays on top."))),
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
    def bw_by_year() -> pd.DataFrame:
        g = _rate_by(base(), ["year", "race"], col())
        piv = g.pivot(index="year", columns="race", values="rate")
        piv["ratio"] = piv.get("Black") / piv.get("White")
        return piv

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
        return f"sentenced in {_where()}, year end {input.year()}"

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
        return f"Incarceration rate by sentencing county, {input.year()}"

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
        return f"Table view - by sentencing county, {input.year()}, {OFFENSE_CHOICES[col()].lower()}"

    # ---- charts
    @viz.render_plot
    def map_chart():
        g = _rate_by(year_all(), "county", col())
        g = g.loc[g["gen_population"] > 0].set_index("county")
        if g.empty:
            return viz.empty_figure(height=480)
        highlight = None if input.county() == "All counties" else input.county()
        return viz.choropleth(
            data.il_counties(), g["rate"], height=480,
            customdata=g[["incarcerated", "gen_population"]].values,
            hovertemplate="<b>%{location}</b><br>%{z:,.0f} per 100k<br>"
                          "%{customdata[0]:,.0f} in custody / %{customdata[1]:,.0f} residents<extra></extra>",
            highlight=highlight,
        )

    @viz.render_plot
    def trend_chart():
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
        if piv.empty or not piv.values.sum():
            return viz.empty_figure(height=480)
        fig = viz.figure(480, hovermode="x unified", yaxis=dict(tickformat=",.0f", rangemode="tozero"),
                         xaxis=dict(dtick=2))
        for g in piv.columns:
            fig.add_scatter(name=viz.age_label(g) if b == "age" else g, x=piv.index, y=piv[g],
                            mode="lines", stackgroup="one", line=dict(width=0.5, color=colors[g]),
                            fillcolor=colors[g], hovertemplate="%{y:,.0f}")
        fig.add_vline(x=input.year(), line=dict(color=viz.AXIS, width=1))
        return fig

    def _bar(by, order, colors, labels=None, height=300):
        g = _rate_by(selected(), by, col())
        g = g.set_index(by).reindex([o for o in order if o in g[by].values]).reset_index()
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
        return fig

    @viz.render_plot
    def sex_chart():
        return _bar("sex", viz.SEX_ORDER, viz.SEX_COLOR)

    @viz.render_plot
    def race_chart():
        return _bar("race", viz.RACE_ORDER, viz.RACE_COLOR)

    @viz.render_plot
    def age_chart():
        return _bar("age", viz.AGE_ORDER, viz.AGE_COLOR, labels=viz.age_label)

    @viz.render_plot
    def ratio_chart():
        piv = bw_by_year()
        if "ratio" not in piv or piv["ratio"].isna().all():
            return viz.empty_figure()
        fig = viz.figure(360, yaxis=dict(rangemode="tozero", ticksuffix="×"), xaxis=dict(dtick=2))
        fig.add_scatter(x=piv.index, y=piv["ratio"], mode="lines+markers",
                        line=dict(color=viz.SERIES[0], width=2),
                        marker=dict(size=8, color=viz.SERIES[0], line=dict(color=viz.SURFACE, width=2)),
                        hovertemplate="<b>%{x}</b><br>%{y:.2f}× the White rate<extra></extra>")
        fig.add_hline(y=1, line=dict(color=viz.AXIS, width=1), annotation_text="parity",
                      annotation_position="bottom right", annotation_font=dict(color=viz.MUTED))
        fig.add_vline(x=input.year(), line=dict(color=viz.AXIS, width=1))
        fig.update_layout(showlegend=False)
        return fig

    @render.ui
    def table():
        c = col()
        # Residents / in custody / rate honor every filter; the Black and White rates ignore
        # the race filter so the ratio is always computable.
        d = data.rates()
        bw_src = d.loc[(d["year"] == input.year()) & isin_or_all(d["sex"], input.sex())
                       & isin_or_all(d["age"], input.age()) & d["race"].isin(["Black", "White"])]

        def _rows(df, bw, label=None):
            by = ["county"] if label is None else []
            g = df.groupby(by)[[c, "gen_population"]].sum() if by \
                else pd.DataFrame({c: [df[c].sum()], "gen_population": [df["gen_population"].sum()]}, index=[label])
            g = g.rename(columns={c: "incarcerated"})
            g["rate"] = g["incarcerated"] / g["gen_population"] * PER
            r = bw.groupby(by + ["race"])[[c, "gen_population"]].sum()
            r = (r[c] / r["gen_population"] * PER).unstack("race") if by \
                else (r[c] / r["gen_population"] * PER).rename(label).to_frame().T
            return g.join(r, how="left")

        state = _rows(year_all(), bw_src, label="All Illinois")
        counties = _rows(year_all(), bw_src)
        counties = counties.loc[counties["gen_population"] > 0].sort_values("rate", ascending=False)
        out = pd.concat([state, counties])
        for race in ("Black", "White"):
            if race not in out.columns:
                out[race] = float("nan")
        out["ratio"] = out["Black"] / out["White"]

        cols = {"County": (None, None), "Residents": ("gen_population", "{:,.0f}"),
                "In custody": ("incarcerated", "{:,.0f}"), "Rate per 100k": ("rate", "{:,.0f}"),
                "Black rate": ("Black", "{:,.0f}"), "White rate": ("White", "{:,.0f}"),
                "Black : White": ("ratio", "{:.1f}×")}
        raw = pd.DataFrame({"County": out.index.astype(str)})
        shown = raw.copy()
        for name, (src, fmt) in cols.items():
            if src is None:
                continue
            raw[name] = out[src].values
            shown[name] = out[src].map(lambda v: "–" if pd.isna(v) else fmt.format(v)).values
        return viz.sortable_table(shown, raw, pinned_rows=1, height="400px")
