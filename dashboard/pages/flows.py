"""Page 2 - admissions and exits: flows over time, by type and reason."""
import pandas as pd
from shiny import module, reactive, render, ui

from .. import data, viz
from ..common import apply_demo, crime_filter, demo_filters, note, reset_button, reset_demo

GRAIN = {"M": "Month", "Q": "Quarter", "Y": "Year"}
MSR = "Mandatory supervised release (MSR)"
EXPIRATION = "Expiration of Sentence"


def _period(s: pd.Series, grain: str) -> pd.Series:
    return s.dt.to_period(grain).dt.to_timestamp()


def _labels(index: pd.DatetimeIndex, grain: str) -> list[str]:
    if grain == "Q":
        return [f"Q{d.quarter} {d.year}" for d in index]
    return list(index.strftime({"M": "%b %Y", "Y": "%Y"}[grain]))


def _reason_group(reason: pd.Series) -> pd.Series:
    """Every 'MSR: ...' sub-reason is one category."""
    return reason.where(~reason.str.startswith("MSR"), MSR)


@module.ui
def page_ui():
    adm, ex = data.admissions(), data.exits()
    y0 = int(adm["month"].min().year)
    y1 = int(min(adm["month"].max(), ex["month"].max()).year)
    counties = ["All counties"] + sorted(set(adm["county"].dropna()) | set(ex["county"].dropna()))
    return ui.layout_sidebar(
        ui.sidebar(
            reset_button(),
            ui.input_slider("years", "Years", min=y0, max=y1, value=(y0, y1), step=1, sep=""),
            ui.input_radio_buttons("grain", "Show by", choices=GRAIN, selected="Q", inline=True),
            ui.input_select("county", "Sentencing county", choices=counties, selected="All counties"),
            crime_filter(),
            *demo_filters(),
            note(f"Admissions data begin in {y0}; exits are shown for the same period. "
                 "County = county of sentencing."),
            width=310,
        ),
        ui.layout_column_wrap(
            ui.value_box("Admissions", ui.output_text("kpi_adm"), ui.output_text("kpi_range"), theme="primary"),
            ui.value_box("Exits", ui.output_text("kpi_ex"), ui.output_text("kpi_range2")),
            ui.value_box("Net change", ui.output_text("kpi_net"), "admissions − exits"),
            fill=False,
        ),
        ui.card(ui.card_header("Admissions, exits and net change"), viz.output_plot("flow_chart"),
                ui.card_footer(note("Exits are drawn below zero; the line is net change "
                                    "(admissions − exits)."))),
        ui.layout_columns(
            ui.card(ui.card_header("Admissions by type"), viz.output_plot("type_chart")),
            ui.card(ui.card_header("Exits by reason"), viz.output_plot("reason_chart"),
                    ui.card_footer(note("MSR = mandatory supervised release (parole)."))),
            col_widths={"sm": 12, "xl": [7, 5]},
        ),
        ui.card(ui.card_header("Table view - by year"), ui.output_data_frame("table"),
                ui.card_footer(note("Admission shares are % of that year's admissions; exit shares are "
                                    "% of that year's exits. Other exits = anything that is not MSR or "
                                    "expiration of sentence (deaths, reversals, court orders, ...)."))),
    )


@module.server
def page_server(input, output, session):
    adm_src, ex_src = data.admissions(), data.exits()
    y0 = int(adm_src["month"].min().year)
    y1 = int(min(adm_src["month"].max(), ex_src["month"].max()).year)

    @reactive.effect
    @reactive.event(input.reset)
    def _reset():
        ui.update_slider("years", value=(y0, y1))
        ui.update_radio_buttons("grain", selected="Q")
        ui.update_select("county", selected="All counties")
        reset_demo(has_crime=True)

    def _in_range(df: pd.DataFrame) -> pd.DataFrame:
        a, b = input.years()
        return df.loc[(df["month"].dt.year >= a) & (df["month"].dt.year <= b)]

    def _county(df: pd.DataFrame) -> pd.DataFrame:
        if input.county() == "All counties":
            return df
        return df.loc[df["county"] == input.county()]

    @reactive.calc
    def adm() -> pd.DataFrame:
        return _county(apply_demo(_in_range(adm_src), input))

    @reactive.calc
    def ex() -> pd.DataFrame:
        return _county(apply_demo(_in_range(ex_src), input))

    @reactive.calc
    def flows() -> pd.DataFrame:
        g = input.grain()
        a = adm().assign(period=lambda d: _period(d["month"], g)).groupby("period")["n"].sum()
        e = ex().assign(period=lambda d: _period(d["month"], g)).groupby("period")["n"].sum()
        out = pd.DataFrame({"Admissions": a, "Exits": e}).fillna(0).sort_index()
        out["Net change"] = out["Admissions"] - out["Exits"]
        return out

    # ---- KPIs
    @render.text
    def kpi_adm():
        return viz.fmt_int(adm()["n"].sum())

    @render.text
    def kpi_ex():
        return viz.fmt_int(ex()["n"].sum())

    @render.text
    def kpi_net():
        net = adm()["n"].sum() - ex()["n"].sum()
        return f"{'+' if net > 0 else ''}{net:,.0f}"

    @reactive.calc
    def year_label() -> str:
        a, b = input.years()
        return f"{a}–{b}" if a != b else str(a)

    @render.text
    def kpi_range():
        return year_label()

    @render.text
    def kpi_range2():
        return year_label()

    # ---- charts
    @viz.render_plot
    def flow_chart():
        f = flows()
        if f.empty:
            return viz.empty_figure()
        labels = _labels(f.index, input.grain())
        fig = viz.figure(380, barmode="relative", bargap=0.25, hovermode="x unified",
                         yaxis=dict(tickformat=",.0f"))
        # admissions above the axis, exits below, net change as a line across both
        fig.add_bar(name="Admissions", x=labels, y=f["Admissions"],
                    marker=dict(color=viz.FLOW_COLOR["Admissions"]),
                    hovertemplate="%{y:,.0f}")
        fig.add_bar(name="Exits", x=labels, y=-f["Exits"], customdata=f["Exits"],
                    marker=dict(color=viz.FLOW_COLOR["Exits"]),
                    hovertemplate="%{customdata:,.0f}")
        fig.add_scatter(name="Net change", x=labels, y=f["Net change"], mode="lines+markers",
                        line=dict(color=viz.FLOW_COLOR["Net change"], width=2),
                        marker=dict(size=6, color=viz.FLOW_COLOR["Net change"],
                                    line=dict(color=viz.SURFACE, width=1.5)),
                        hovertemplate="%{y:+,.0f}")
        fig.update_layout(xaxis=dict(type="category", tickangle=-45 if len(f) > 12 else 0))
        return fig

    @viz.render_plot
    def type_chart():
        g = input.grain()
        a = adm().assign(period=lambda d: _period(d["month"], g))
        piv = a.pivot_table(index="period", columns="admtyp", values="n", aggfunc="sum").fillna(0)
        if piv.empty:
            return viz.empty_figure(height=400)
        labels = _labels(piv.index, g)
        fig = viz.figure(400, barmode="stack", yaxis=dict(tickformat=",.0f"))
        for t in viz.ADMTYP_ORDER:
            if t in piv.columns:
                fig.add_bar(name=t, x=labels, y=piv[t], marker=viz.bar_marker(viz.ADMTYP_COLOR[t]),
                            hovertemplate=f"<b>{t}</b><br>%{{x}}: %{{y:,.0f}}<extra></extra>")
        fig.update_layout(xaxis=dict(type="category", tickangle=-45 if len(piv) > 12 else 0))
        return fig

    @viz.render_plot
    def reason_chart():
        g = ex().groupby("exit_reason")["n"].sum().sort_values(ascending=False)
        if g.empty:
            return viz.empty_figure(height=400)
        if len(g) > 8:
            g = pd.concat([g.iloc[:8], pd.Series({"Other": g.iloc[8:].sum()})])
        g = g.iloc[::-1]
        fig = viz.figure(400, margin=dict(l=8, r=70, t=8, b=8),
                         xaxis=dict(tickformat=",.0f", showgrid=True, gridcolor=viz.GRID),
                         yaxis=dict(showgrid=False, tickfont=dict(size=11)))
        fig.add_bar(x=g.values, y=g.index, orientation="h", marker=dict(color=viz.FLOW_COLOR["Exits"]),
                    text=[f"{v:,.0f}" for v in g.values], textposition="outside",
                    textfont=dict(color=viz.INK_2, size=11),
                    hovertemplate="<b>%{y}</b><br>%{x:,.0f} exits<extra></extra>")
        fig.update_layout(showlegend=False, xaxis_range=[0, g.max() * 1.25])
        return fig

    @render.data_frame
    def table():
        a = adm().assign(year=lambda d: d["month"].dt.year)
        e = ex().assign(year=lambda d: d["month"].dt.year)
        adm_tot = a.groupby("year")["n"].sum()
        adm_typ = a.pivot_table(index="year", columns="admtyp", values="n", aggfunc="sum").fillna(0)
        ex_tot = e.groupby("year")["n"].sum()
        e["group"] = _reason_group(e["exit_reason"])
        e["group"] = e["group"].where(e["group"].isin([MSR, EXPIRATION]), "Other")
        ex_typ = e.pivot_table(index="year", columns="group", values="n", aggfunc="sum").fillna(0)

        years = sorted(set(adm_tot.index) | set(ex_tot.index))
        adm_tot, ex_tot = adm_tot.reindex(years).fillna(0), ex_tot.reindex(years).fillna(0)

        def share(piv, colname, total):
            s = piv[colname].reindex(years).fillna(0) / total if colname in piv.columns \
                else pd.Series(0.0, index=years)
            return s.map(lambda v: "–" if pd.isna(v) else f"{v:.1%}").values

        out = pd.DataFrame({
            "Year": [str(y) for y in years],
            "Admissions": adm_tot.map("{:,.0f}".format).values,
            "Adm – Technical %": share(adm_typ, "Technical violator", adm_tot),
            "Adm – New sentence %": share(adm_typ, "New sentence violator", adm_tot),
            "Adm – Court %": share(adm_typ, "Court admission", adm_tot),
            "Exits": ex_tot.map("{:,.0f}".format).values,
            "Exit – MSR %": share(ex_typ, MSR, ex_tot),
            "Exit – Exp. sentence %": share(ex_typ, EXPIRATION, ex_tot),
            "Exit – Other %": share(ex_typ, "Other", ex_tot),
        })
        return render.DataGrid(out, width="100%")
