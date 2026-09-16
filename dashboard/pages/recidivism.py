"""Page 3 - recidivism: share of release cohorts readmitted within a chosen window."""
import numpy as np
import pandas as pd
from shiny import module, reactive, render, ui

from .. import data, viz
from ..common import apply_demo, crime_filter, demo_filters, multi_select, note, reset_button, reset_demo, selected

RETURN_TYPES = {"court": "Court admission (new sentence)",
                "newsent": "New sentence violator",
                "tech": "Technical violator",
                "other": "Other"}
RETURN_COLOR = {"court": viz.ADMTYP_COLOR["Court admission"],
                "newsent": viz.ADMTYP_COLOR["New sentence violator"],
                "tech": viz.ADMTYP_COLOR["Technical violator"],
                "other": viz.ADMTYP_COLOR["Other"]}
DAYS_PER_YEAR = 365


def _last_observed_year() -> int:
    return int(data.admissions()["month"].max().year)


def _with_return(df: pd.DataFrame, types: list[str], window_years: int) -> pd.DataFrame:
    """
    Add days_to_return (first return of any selected type), return_type (which type that
    first return was) and returned (within the window).
    """
    cols = [f"days_{t}" for t in types]
    days = df[cols].min(axis=1)
    # idxmin refuses all-NaN rows (people who never returned), so fill them for the argmin only
    first = df[cols].fillna(np.inf).idxmin(axis=1).str.removeprefix("days_").where(days.notna())
    out = df.assign(days_to_return=days, return_type=first)
    out["returned"] = out["days_to_return"] <= window_years * DAYS_PER_YEAR
    return out


def _rate_by(df: pd.DataFrame, by) -> pd.DataFrame:
    g = df.groupby(by, as_index=False).agg(released=("returned", "size"), returned=("returned", "sum"))
    g["rate"] = g["returned"] / g["released"]
    return g


@module.ui
def page_ui():
    r = data.recidivism()
    counties = ["All counties"] + sorted(r["county"].dropna().unique())
    return ui.layout_sidebar(
        ui.sidebar(
            reset_button(),
            ui.input_radio_buttons("window", "Return within", choices={"1": "1 year", "2": "2 years", "3": "3 years"},
                                   selected="3", inline=True),
            multi_select("types", "Count as a return", RETURN_TYPES, placeholder="All return types"),
            ui.input_select("county", "Sentencing county", choices=counties, selected="All counties"),
            crime_filter(),
            *demo_filters(),
            note("A release is anyone leaving IDOC custody to mandatory supervised release or at "
                 "sentence expiration (2018 onward). A return is a later IDOC admission of a selected "
                 "type. Only cohorts old enough to be fully observed for the chosen window are shown."),
            width=310,
        ),
        ui.layout_column_wrap(
            ui.value_box("Recidivism rate", ui.output_text("kpi_rate"), ui.output_text("kpi_rate_sub"),
                         theme="primary"),
            ui.value_box("Releases in cohorts", ui.output_text("kpi_released"), ui.output_text("kpi_cohorts")),
            ui.value_box("Median time to return", ui.output_text("kpi_median"), "among those who returned"),
            fill=False,
        ),
        ui.layout_columns(
            ui.card(ui.card_header("Recidivism rate by release year"), viz.output_plot("year_chart"),
                    ui.card_footer(note("Colored by the type of the first return."))),
            ui.card(ui.card_header("Cumulative share returned, by months since release"),
                    viz.output_plot("curve_chart"),
                    ui.card_footer(note("By race. Each line stops at the selected window."))),
            col_widths={"sm": 12, "xl": [5, 7]},
        ),
        ui.layout_columns(
            ui.card(ui.card_header("By race"), viz.output_plot("race_chart")),
            ui.card(ui.card_header("By age at release"), viz.output_plot("age_chart")),
            ui.card(ui.card_header("By offense class"), viz.output_plot("crime_chart")),
            col_widths={"sm": 12, "xl": [4, 4, 4]},
        ),
        ui.card(ui.card_header("Table view - release cohorts"), ui.output_data_frame("table")),
    )


@module.server
def page_server(input, output, session):
    @reactive.effect
    @reactive.event(input.reset)
    def _reset():
        ui.update_radio_buttons("window", selected="3")
        ui.update_selectize("types", selected=[])
        ui.update_select("county", selected="All counties")
        reset_demo(has_crime=True)

    @reactive.calc
    def window() -> int:
        return int(input.window())

    @reactive.calc
    def types() -> list[str]:
        return selected(input, "types", RETURN_TYPES)

    @reactive.calc
    def cohort() -> pd.DataFrame:
        df = data.recidivism()
        df = df.loc[df["release_year"] <= _last_observed_year() - window()]
        df = apply_demo(df, input)
        if input.county() != "All counties":
            df = df.loc[df["county"] == input.county()]
        return _with_return(df, types(), window())

    @reactive.calc
    def returners() -> pd.DataFrame:
        c = cohort()
        return c.loc[c["returned"]]

    # ---- KPIs
    @render.text
    def kpi_rate():
        c = cohort()
        return f"{c['returned'].mean():.1%}" if len(c) else "–"

    @render.text
    def kpi_rate_sub():
        return f"returned to IDOC within {window()} year{'s' if window() > 1 else ''} of release"

    @render.text
    def kpi_released():
        return viz.fmt_int(len(cohort()))

    @render.text
    def kpi_cohorts():
        c = cohort()
        if c.empty:
            return ""
        return f"released {c['release_year'].min()}–{c['release_year'].max()}"

    @render.text
    def kpi_median():
        r = returners()
        if r.empty:
            return "–"
        return f"{r['days_to_return'].median() / 30.44:.0f} months"

    # ---- charts
    def _bar(g, x, colors, height=300, order=None, labels=None):
        if g.empty:
            return viz.empty_figure(height=height)
        if order is not None:
            g = g.set_index(x).reindex([o for o in order if o in g[x].values]).reset_index()
        fig = viz.figure(height, yaxis=dict(tickformat=".0%", rangemode="tozero"))
        fig.add_bar(x=[labels(v) for v in g[x]] if labels else g[x], y=g["rate"],
                    marker=dict(color=colors if isinstance(colors, str) else [colors[v] for v in g[x]]),
                    text=[f"{v:.0%}" for v in g["rate"]], textposition="outside",
                    textfont=dict(color=viz.INK_2),
                    customdata=g[["returned", "released"]].values,
                    hovertemplate="<b>%{x}</b><br>%{y:.1%} returned<br>"
                                  "%{customdata[0]:,.0f} of %{customdata[1]:,.0f} released<extra></extra>")
        fig.update_layout(showlegend=False, yaxis_range=[0, min(1, g["rate"].max() * 1.2)])
        return fig

    @viz.render_plot
    def year_chart():
        c = cohort()
        if c.empty:
            return viz.empty_figure(height=320)
        released = c.groupby("release_year").size()
        by_type = (c.loc[c["returned"]].groupby(["release_year", "return_type"]).size()
                    .unstack("return_type").reindex(released.index).fillna(0))
        years = [str(y) for y in released.index]
        total = by_type.sum(axis=1) / released
        fig = viz.figure(320, barmode="stack", yaxis=dict(tickformat=".0%", rangemode="tozero"))
        for t in RETURN_TYPES:
            if t not in by_type.columns:
                continue
            share = by_type[t] / released
            fig.add_bar(name=RETURN_TYPES[t], x=years, y=share, marker=viz.bar_marker(RETURN_COLOR[t]),
                        customdata=list(zip(by_type[t], released)),
                        hovertemplate=f"<b>{RETURN_TYPES[t]}</b><br>%{{y:.1%}} of releases "
                                      "(%{customdata[0]:,.0f} of %{customdata[1]:,.0f})<extra></extra>")
        fig.add_scatter(x=years, y=total, mode="text", text=[f"{v:.0%}" for v in total],
                        textposition="top center", textfont=dict(color=viz.INK_2),
                        showlegend=False, hoverinfo="skip")
        fig.update_layout(yaxis_range=[0, min(1, total.max() * 1.2)])
        return fig

    @viz.render_plot
    def race_chart():
        return _bar(_rate_by(cohort(), "race"), "race", viz.RACE_COLOR, order=viz.RACE_ORDER)

    @viz.render_plot
    def age_chart():
        g = _rate_by(cohort(), "age_group")
        return _bar(g, "age_group", viz.SERIES[0], order=viz.AGE_ORDER, labels=viz.age_label)

    @viz.render_plot
    def crime_chart():
        return _bar(_rate_by(cohort(), "crime_class"), "crime_class", viz.CRIME_COLOR, order=viz.CRIME_ORDER)

    @viz.render_plot
    def curve_chart():
        c = cohort()
        if c.empty:
            return viz.empty_figure(height=320)
        months = np.arange(0, window() * 12 + 1)
        fig = viz.figure(320, hovermode="x unified",
                         xaxis=dict(title="Months since release", dtick=6),
                         yaxis=dict(tickformat=".0%", rangemode="tozero"))
        for race in viz.RACE_ORDER:
            s = c.loc[c["race"] == race, "days_to_return"]
            if len(s) < 50:
                continue
            days = s.dropna().to_numpy()
            cum = [(days <= m * 30.44).sum() / len(s) for m in months]
            fig.add_scatter(name=race, x=months, y=cum, mode="lines",
                            line=dict(color=viz.RACE_COLOR[race], width=2),
                            hovertemplate="%{y:.1%}")
        return fig

    @render.data_frame
    def table():
        g = _rate_by(cohort(), "release_year")
        out = pd.DataFrame({
            "Release year": g["release_year"],
            "Released": g["released"].map("{:,.0f}".format),
            f"Returned within {window()}y": g["returned"].map("{:,.0f}".format),
            "Rate": g["rate"].map("{:.1%}".format),
        })
        return render.DataGrid(out, width="100%")
