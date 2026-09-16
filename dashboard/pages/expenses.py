"""Page 4 - IDOC expenditures and expense per inmate, by state fiscal year (July-June)."""
import pandas as pd
from shiny import module, reactive, render, ui

from .. import data, viz
from ..common import multi_select, note, reset_button, selected

MONTHS = data.FISCAL_MONTHS   # Jul ... Jun


def _fy(y: int) -> str:
    return f"FY{y}"


def _annual() -> pd.DataFrame:
    """Total spend, months reported, average headcount and expense per inmate, per fiscal year."""
    e = data.expenses()
    spend = e.groupby("year").agg(amount=("amount", "sum"))
    months = e.loc[e["amount"] != 0].groupby("year")["month"].nunique().rename("months")
    pop = data.population_snapshots().groupby("fiscal_year")["population"].mean().rename("population")
    out = spend.join(months).join(pop).reset_index()
    out["months"] = out["months"].fillna(0).astype(int)
    out["per_inmate"] = out["amount"] / out["population"]
    out["per_month"] = out["amount"] / out["months"].replace(0, float("nan"))
    out["partial"] = out["months"] < 12
    return out


@module.ui
def page_ui():
    years = sorted(data.expenses()["year"].unique())
    complete = [y for y in years if not _annual().set_index("year").loc[y, "partial"]]
    default = complete[-1] if complete else years[-1]
    return ui.layout_sidebar(
        ui.sidebar(
            reset_button(),
            ui.input_select("year", "Fiscal year", choices={str(y): _fy(y) for y in years}, selected=str(default)),
            multi_select("category", "Spending category", viz.EXPENSE_ORDER),
            note("Illinois fiscal years run July–June and are named for the year they end in "
                 "(FY2026 = July 2025 – June 2026). Expense per inmate = total expenditures for the "
                 "fiscal year ÷ the average of IDOC's quarterly headcounts in that fiscal year."),
            width=300,
        ),
        ui.layout_column_wrap(
            ui.value_box("Expense per inmate", ui.output_text("kpi_per_inmate"),
                         ui.output_text("kpi_per_inmate_sub"), theme="primary"),
            ui.value_box("Total expenditures", ui.output_text("kpi_total"),
                         ui.output_text("kpi_total_sub")),
            ui.value_box("Average monthly expense", ui.output_text("kpi_month"),
                         ui.output_text("kpi_month_sub")),
            fill=False,
        ),
        ui.layout_columns(
            ui.card(ui.card_header("Expense per inmate by fiscal year"), viz.output_plot("per_inmate_chart"),
                    ui.card_footer(ui.output_text("per_inmate_note"))),
            ui.card(ui.card_header("Annual spend by category"), viz.output_plot("annual_chart")),
            col_widths={"sm": 12, "xl": [6, 6]},
        ),
        ui.layout_columns(
            ui.card(ui.card_header(ui.output_text("monthly_title")), viz.output_plot("monthly_chart")),
            ui.card(ui.card_header(ui.output_text("objects_title")), viz.output_plot("objects_chart")),
            col_widths={"sm": 12, "xl": [7, 5]},
        ),
        ui.card(ui.card_header("Table view - spend by category and month"),
                ui.output_data_frame("table")),
    )


@module.server
def page_server(input, output, session):
    years = sorted(data.expenses()["year"].unique())
    complete = [y for y in years if not _annual().set_index("year").loc[y, "partial"]]
    default = complete[-1] if complete else years[-1]

    @reactive.effect
    @reactive.event(input.reset)
    def _reset():
        ui.update_select("year", selected=str(default))
        ui.update_selectize("category", selected=[])

    @reactive.calc
    def year() -> int:
        return int(input.year())

    @reactive.calc
    def categories() -> list[str]:
        return selected(input, "category", viz.EXPENSE_ORDER)

    @reactive.calc
    def filtered() -> pd.DataFrame:
        df = data.expenses()
        return df.loc[(df["year"] == year()) & df["category"].isin(categories())]

    @reactive.calc
    def annual() -> pd.DataFrame:
        return _annual()

    @reactive.calc
    def this_year() -> pd.Series:
        a = annual()
        return a.loc[a["year"] == year()].iloc[0]

    @reactive.calc
    def prev_year():
        a = annual()
        prev = a.loc[a["year"] == year() - 1]
        return None if prev.empty else prev.iloc[0]

    def _delta(col, fmt):
        prev = prev_year()
        if prev is None or pd.isna(prev[col]):
            return "No prior year"
        cur = this_year()[col]
        pct = (cur - prev[col]) / prev[col]
        arrow = "▲" if pct >= 0 else "▼"
        return f"{arrow} {abs(pct):.1%} vs {_fy(year() - 1)} ({fmt(prev[col])})"

    def _partial_note():
        t = this_year()
        return f" ({_fy(year())} has {t['months']} of 12 months reported)" if t["partial"] else ""

    # ---- KPIs
    @render.text
    def kpi_per_inmate():
        return viz.fmt_money(this_year()["per_inmate"])

    @render.text
    def kpi_per_inmate_sub():
        return _delta("per_inmate", viz.fmt_money) + _partial_note()

    @render.text
    def kpi_total():
        return viz.fmt_money(this_year()["amount"])

    @render.text
    def kpi_total_sub():
        return _delta("amount", viz.fmt_money) + _partial_note()

    @render.text
    def kpi_month():
        return viz.fmt_money(this_year()["per_month"])

    @render.text
    def kpi_month_sub():
        t = this_year()
        return _delta("per_month", viz.fmt_money) + f" · over {t['months']} months"

    @render.text
    def monthly_title():
        return f"Monthly spend by category, {_fy(year())}"

    @render.text
    def objects_title():
        return f"Top 12 line items, {_fy(year())}"

    @render.text
    def per_inmate_note():
        partial = [f"{_fy(y)} ({m} of 12 months)" for y, m, p in
                   annual()[["year", "months", "partial"]].itertuples(index=False) if p]
        base = "All spending categories. Selected year highlighted."
        return base + (" * partial year: " + ", ".join(partial) if partial else "")

    # ---- charts
    @viz.render_plot
    def per_inmate_chart():
        a = annual()
        colors = [viz.SERIES[0] if y == year() else viz.SEQ_BLUE[1] for y in a["year"]]
        labels = [_fy(y) + ("*" if p else "") for y, p in zip(a["year"], a["partial"])]
        fig = viz.figure(320, yaxis=dict(tickprefix="$", tickformat=",.0f"))
        fig.add_bar(x=labels, y=a["per_inmate"], marker=dict(color=colors),
                    text=[viz.fmt_money(v) for v in a["per_inmate"]], textposition="outside",
                    textfont=dict(color=viz.INK_2),
                    customdata=a[["amount", "population", "months"]].values,
                    hovertemplate="<b>%{x}</b><br>Per inmate: $%{y:,.0f}<br>"
                                  "Spend: $%{customdata[0]:,.0f} (%{customdata[2]} months)<br>"
                                  "Avg population: %{customdata[1]:,.0f}<extra></extra>")
        fig.update_layout(showlegend=False, yaxis_range=[0, a["per_inmate"].max() * 1.18])
        return fig

    @viz.render_plot
    def annual_chart():
        df = data.expenses()
        df = df.loc[df["category"].isin(categories())]
        piv = df.pivot_table(index="year", columns="category", values="amount", aggfunc="sum").fillna(0)
        fig = viz.figure(320, barmode="stack", yaxis=dict(tickprefix="$", exponentformat="B"))
        for cat in viz.EXPENSE_ORDER:
            if cat in piv.columns:
                fig.add_bar(name=cat, x=[_fy(y) for y in piv.index], y=piv[cat],
                            marker=viz.bar_marker(viz.EXPENSE_COLOR[cat]),
                            hovertemplate=f"<b>{cat}</b><br>%{{x}}: $%{{y:,.0f}}<extra></extra>")
        return fig

    @viz.render_plot
    def monthly_chart():
        df = filtered()
        if df.empty:
            return viz.empty_figure()
        piv = (df.pivot_table(index="month", columns="category", values="amount", aggfunc="sum")
                 .reindex(MONTHS).fillna(0))
        labels = [f"{m} {y}" for m, y in zip(MONTHS, [year() - 1] * 6 + [year()] * 6)]
        fig = viz.figure(340, barmode="stack", yaxis=dict(tickprefix="$", exponentformat="B"))
        for cat in viz.EXPENSE_ORDER:
            if cat in piv.columns:
                fig.add_bar(name=cat, x=labels, y=piv[cat],
                            marker=viz.bar_marker(viz.EXPENSE_COLOR[cat]),
                            hovertemplate=f"<b>{cat}</b><br>%{{x}}: $%{{y:,.0f}}<extra></extra>")
        fig.update_layout(xaxis=dict(type="category"))
        return fig

    @viz.render_plot
    def objects_chart():
        df = filtered()
        if df.empty:
            return viz.empty_figure()
        top = (df.groupby(["object", "category"], as_index=False)["amount"].sum()
                 .sort_values("amount", ascending=False).head(12).iloc[::-1])
        fig = viz.figure(
            340, bargap=0.3,
            margin=dict(l=8, r=60, t=8, b=8),
            xaxis=dict(tickprefix="$", exponentformat="B", showgrid=True, gridcolor=viz.GRID),
            yaxis=dict(showgrid=False, tickfont=dict(size=11)),
        )
        fig.add_bar(x=top["amount"], y=top["object"].str.title(), orientation="h",
                    marker=dict(color=[viz.EXPENSE_COLOR[c] for c in top["category"]]),
                    text=[viz.fmt_money(v) for v in top["amount"]], textposition="outside",
                    textfont=dict(color=viz.INK_2, size=11),
                    customdata=top["category"],
                    hovertemplate="<b>%{y}</b><br>%{customdata}<br>$%{x:,.0f}<extra></extra>")
        fig.update_layout(showlegend=False, xaxis_range=[0, top["amount"].max() * 1.25])
        return fig

    @render.data_frame
    def table():
        df = filtered()
        piv = (df.pivot_table(index="category", columns="month", values="amount", aggfunc="sum")
                 .reindex(columns=MONTHS).fillna(0))
        piv["Total"] = piv.sum(axis=1)
        piv = piv.reindex([c for c in viz.EXPENSE_ORDER if c in piv.index])
        piv.loc["Total"] = piv.sum()
        out = piv.reset_index().rename(columns={"category": "Category"})
        for c in out.columns[1:]:
            out[c] = out[c].map(lambda v: f"${v:,.0f}")
        return render.DataGrid(out, width="100%")
