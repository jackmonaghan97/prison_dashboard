"""Page 4 - IDOC expenditures and expense per inmate, by state fiscal year (July-June)."""
import pandas as pd
from shiny import module, reactive, render, ui

from .. import viz
from .. import data
from ..common import download_footer, multi_select, note, reset_button, selected

MONTHS = data.FISCAL_MONTHS   # Jul ... Jun


def _fy(y: int) -> str:
    return f"FY{y}"


def _annual() -> pd.DataFrame:
    """Total spend, months reported, June 30 headcount and expense per inmate, per fiscal year."""
    e = data.expenses()
    spend = e.groupby("year").agg(amount=("amount", "sum"))
    months = e.loc[e["amount"] != 0].groupby("year")["month"].nunique().rename("months")
    pop = data.population_snapshots().set_index("fiscal_year")["population"]
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
                 "fiscal year ÷ IDOC's headcount on June 30, the last day of that fiscal year."),
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
                    download_footer("per_inmate_csv", "the expense per inmate chart",
                                    ui.output_text("per_inmate_note"))),
            ui.card(ui.card_header(ui.output_text("annual_title")), viz.output_plot("annual_chart"),
                    ui.output_ui("annual_table"),
                    download_footer("annual_csv", "the spending by category table")),
            col_widths={"sm": 12, "xl": [6, 6]},
        ),
        ui.layout_columns(
            ui.card(ui.card_header(ui.output_text("monthly_title")), viz.output_plot("monthly_chart"),
                    ui.output_ui("monthly_table"),
                    download_footer("monthly_csv", "the average monthly spending table",
                                    ui.output_text("monthly_note"))),
            ui.card(ui.card_header(ui.output_text("objects_title")), viz.output_plot("objects_chart"),
                    download_footer("objects_csv", "the top line items chart")),
            col_widths={"sm": 12, "xl": [7, 5]},
        ),
        ui.card(ui.card_header(ui.output_text("table_title")),
                ui.output_data_frame("table"),
                download_footer("table_csv", "the spend by category and month table")),
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

    @reactive.calc
    def season_years() -> list[int]:
        """Complete fiscal years (12 months reported), averaged in the seasonal chart."""
        a = annual()
        return [int(y) for y in a.loc[~a["partial"], "year"]]

    def _season_span() -> str:
        ys = season_years()
        return f"{_fy(ys[0])}–{_fy(ys[-1])}" if len(ys) > 1 else _fy(ys[0])

    @render.text
    def annual_title():
        return f"Spending by category, {_fy(year())}"

    @render.text
    def monthly_title():
        return f"Average monthly spend by category, {_season_span()}"

    @render.text
    def monthly_note():
        return (f"Average of the {len(season_years())} complete fiscal years ({_season_span()}) for each month; "
                "partial years are left out. Uses the category filter, not the year.")

    @render.text
    def table_title():
        return f"Table view - spend by category and month, {_fy(year())}"

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
                                  "Population June 30: %{customdata[1]:,.0f}<extra></extra>")
        fig.update_layout(showlegend=False, yaxis_range=[0, a["per_inmate"].max() * 1.18])
        return viz.describe(fig, "Bar chart of IDOC expenditure per inmate by fiscal year (* = partial year): "
                                 f"{viz.alt_values(zip(labels, a['per_inmate']), '${:,.0f}')}.")

    @viz.download_csv("expense_per_inmate_by_fiscal_year.csv")
    def per_inmate_csv():
        a = annual()
        return pd.DataFrame({"Fiscal year": [_fy(y) for y in a["year"]], "Months reported": a["months"],
                             "Partial year": a["partial"], "Total expenditures": a["amount"],
                             "Population June 30": a["population"], "Expense per inmate": a["per_inmate"]})

    @reactive.calc
    def year_categories() -> pd.Series:
        """Spend per category (selected categories, EXPENSE_ORDER) in the selected fiscal year."""
        g = filtered().groupby("category")["amount"].sum()
        return g.reindex([c for c in viz.EXPENSE_ORDER if c in g.index])

    @render.ui
    def annual_table():
        g = year_categories()
        if g.empty:
            return None
        total = g.sum()
        head = ui.tags.tr(*[ui.tags.th(h, scope="col") for h in ("Category", "Spend", "Share")])
        rows = [ui.tags.tr(ui.tags.th(cat, scope="row"), ui.tags.td(f"${v:,.0f}"),
                           ui.tags.td(f"{v / total:.1%}" if total else "–"))
                for cat, v in g.items()]
        rows.append(ui.tags.tr(ui.tags.th("Total", scope="row"), ui.tags.td(f"${total:,.0f}"),
                               ui.tags.td("100.0%" if total else "–")))
        return ui.tags.details(
            ui.tags.summary("Show the chart's values as a table"),
            ui.div(ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="layer-table"),
                   class_="layer-wrap"),
            class_="layer-details")

    @viz.download_csv(lambda: f"spending_by_category_{_fy(year())}.csv")
    def annual_csv():
        g = year_categories()
        return pd.DataFrame({"Fiscal year": _fy(year()), "Category": g.index, "Spend": g.values,
                             "Share": g.values / g.sum() if g.sum() else float("nan")})

    @viz.render_plot
    def annual_chart():
        g = year_categories()
        g = g.loc[g > 0]
        if g.empty:
            return viz.empty_figure(height=320)
        partial = " (partial year)" if this_year()["partial"] else ""
        # a donut of the selected year: every slice is labelled with its name and share, so it
        # reads without matching colors to a legend; slices are parted by a surface-colored seam
        fig = viz.figure(320, margin=dict(l=8, r=8, t=24, b=24), showlegend=False)
        fig.add_pie(labels=list(g.index), values=g.values, hole=0.45, sort=False, direction="clockwise",
                    marker=dict(colors=[viz.EXPENSE_COLOR[c] for c in g.index],
                                line=dict(color=viz.SURFACE, width=2)),
                    texttemplate="%{label}<br>%{percent:.1%}", textposition="outside",
                    textfont=dict(color=viz.INK_2, size=12),
                    hovertemplate="<b>%{label}</b><br>$%{value:,.0f} (%{percent:.1%})<extra></extra>")
        fig.add_annotation(text=f"{_fy(year())}{'*' if partial else ''}<br>{viz.fmt_money(g.sum())}",
                           x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
                           font=dict(color=viz.INK, size=14))
        shares = ((c, v / g.sum()) for c, v in g.items())
        return viz.describe(fig, f"Donut chart of IDOC expenditures by category, {_fy(year())}{partial}, total "
                                 f"{viz.fmt_money(g.sum())}: {viz.alt_values(zip(g.index, g.values), '${:,.0f}')}. "
                                 f"Shares: {viz.alt_values(shares, '{:.1%}')}.")

    @reactive.calc
    def monthly_piv() -> pd.DataFrame:
        """Month of the fiscal year (Jul ... Jun) x category: average spend over the complete fiscal years."""
        df = data.expenses()
        df = df.loc[df["year"].isin(season_years()) & df["category"].isin(categories())]
        if df.empty:
            return pd.DataFrame()
        piv = (df.pivot_table(index="month", columns="category", values="amount", aggfunc="sum")
                 .reindex(MONTHS).fillna(0) / len(season_years()))
        return piv[[c for c in viz.EXPENSE_ORDER if c in piv.columns]]

    @render.ui
    def monthly_table():
        piv = monthly_piv()
        return None if piv.empty else viz.layer_table(piv, fmt="${:,.0f}", index_name=f"Month (average, {_season_span()})")

    @viz.download_csv(lambda: f"average_monthly_spending_{_season_span()}.csv".replace("–", "-"))
    def monthly_csv():
        out = monthly_piv().copy()
        out["Total"] = out.sum(axis=1)
        out.insert(0, "Fiscal years averaged", _season_span())
        return out.rename_axis("Month").reset_index()

    @viz.render_plot
    def monthly_chart():
        piv = monthly_piv()
        if piv.empty:
            return viz.empty_figure()
        labels = list(piv.index)
        fig = viz.figure(340, barmode="stack", yaxis=dict(tickprefix="$", exponentformat="B"))
        for cat in viz.EXPENSE_ORDER:
            if cat in piv.columns:
                fig.add_bar(name=cat, x=labels, y=piv[cat],
                            marker=viz.bar_marker(viz.EXPENSE_COLOR[cat]),
                            hovertemplate=f"<b>{cat}</b><br>%{{x}} average: $%{{y:,.0f}}<extra></extra>")
        fig.update_layout(xaxis=dict(type="category"))
        tot = piv.sum(axis=1)
        return viz.describe(fig, f"Stacked bar chart of average IDOC spend per month of the fiscal year (July to June) "
                                 f"by category, averaged over {_season_span()}. Average monthly totals: "
                                 f"{viz.alt_values(zip(labels, tot), '${:,.0f}')}.")

    @reactive.calc
    def top_objects() -> pd.DataFrame:
        """The 12 largest line items (object codes) in the selected year, largest first."""
        df = filtered()
        return (df.groupby(["object", "category"], as_index=False)["amount"].sum()
                  .sort_values("amount", ascending=False).head(12))

    @viz.download_csv(lambda: f"top_line_items_{_fy(year())}.csv")
    def objects_csv():
        top = top_objects()
        return pd.DataFrame({"Fiscal year": _fy(year()), "Line item": top["object"].str.title(),
                             "Category": top["category"], "Spend": top["amount"]})

    @viz.render_plot
    def objects_chart():
        df = filtered()
        if df.empty:
            return viz.empty_figure()
        top = top_objects().iloc[::-1]
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
        return viz.describe(fig, f"Horizontal bar chart of the 12 largest IDOC line items, {_fy(year())}, colored by "
                                 f"category: {viz.alt_values(zip(top['object'].str.title()[::-1], top['amount'][::-1]), '${:,.0f}')}.")

    @reactive.calc
    def category_month() -> pd.DataFrame:
        """Category x month (Jul ... Jun) for the selected fiscal year, with total row and column."""
        df = filtered()
        piv = (df.pivot_table(index="category", columns="month", values="amount", aggfunc="sum")
                 .reindex(columns=MONTHS).fillna(0))
        piv["Total"] = piv.sum(axis=1)
        piv = piv.reindex([c for c in viz.EXPENSE_ORDER if c in piv.index])
        piv.loc["Total"] = piv.sum()
        return piv.rename_axis(index="Category", columns=None).reset_index()

    @viz.download_csv(lambda: f"spending_by_category_and_month_{_fy(year())}.csv")
    def table_csv():
        out = category_month()
        out.insert(0, "Fiscal year", _fy(year()))
        return out

    @render.data_frame
    def table():
        out = category_month()
        for c in out.columns[1:]:
            out[c] = out[c].map(lambda v: f"${v:,.0f}")
        return render.DataGrid(out, width="100%")
