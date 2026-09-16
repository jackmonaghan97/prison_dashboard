"""
Shared plotly styling: one palette, fixed entity -> color assignments, a base layout.

Colors follow the entity (a race, a category) and never its rank, so filtering
never repaints the survivors. Categorical hues are assigned in a fixed order.
"""
import functools
import uuid
from pathlib import Path

import pandas as pd
import plotly
import plotly.graph_objects as go
from shiny import render, ui

PLOTLY_JS_DIR = Path(plotly.__file__).parent / "package_data"   # holds plotly.min.js

# ---------------------------------------------------------------- palette (light surface)
SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

# ICJIA brand: navy for chrome (nav, primary tiles, buttons), blue as the first chart hue
NAVY = "#0a3a60"
NAVY_2 = "#0e4471"
BLUE = "#1565c0"
STEEL = "#466c8c"
BLUE_TINT = "#ebf6ff"

SERIES = [BLUE, "#e36209", "#22863a", "#e8a600",
          "#6f42c1", "#d73a49", STEEL, "#8a6d3b"]
SEQ_BLUE = [BLUE_TINT, "#bcd8f5", "#8fbbea", "#5f9bdc", BLUE, NAVY_2, NAVY]
DIVERGING = [[0.0, BLUE], [0.5, "#f0efec"], [1.0, "#d73a49"]]

# ---------------------------------------------------------------- fixed entity colors
RACE_ORDER = ["Black", "White", "Hispanic", "Asian", "American Indian", "Bi-Racial", "Other"]
RACE_COLOR = dict(zip(RACE_ORDER, SERIES))

SEX_ORDER = ["Male", "Female"]
SEX_COLOR = dict(zip(SEX_ORDER, SERIES))

AGE_ORDER = ['>18', '18-19', '20-24', '25-29', '30-34', '35-44',
             '45-54', '55-64', '65-74', '75<']
AGE_LABEL = {'>18': 'Under 18', '75<': '75+'}


def rgba(hex_color: str, alpha: float) -> str:
    """'#rrggbb' -> 'rgba(r,g,b,a)' so a tint also shows in the legend swatch."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def _ramp(colors: list[str], n: int) -> list[str]:
    """n evenly spaced hex colors interpolated along a list of hex stops."""
    rgb = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in colors]
    out = []
    for k in range(n):
        t = k / (n - 1) * (len(rgb) - 1)
        i = min(int(t), len(rgb) - 2)
        f = t - i
        out.append("#" + "".join(f"{round(a + (b - a) * f):02x}" for a, b in zip(rgb[i], rgb[i + 1])))
    return out


# ordered groups get a sequential ramp so the stacking order reads as a gradient
AGE_COLOR = dict(zip(AGE_ORDER, _ramp(["#bcd8f5", BLUE, NAVY], len(AGE_ORDER))))

CRIME_ORDER = ["Person", "Property", "Drug", "Public Order", "Unknown"]
CRIME_COLOR = dict(zip(CRIME_ORDER, SERIES[:4] + [MUTED]))

ADMTYP_ORDER = ["Court admission", "New sentence violator", "Technical violator", "Other"]
ADMTYP_COLOR = dict(zip(ADMTYP_ORDER, SERIES[:4]))

EXPENSE_ORDER = ["Personnel", "Medical & Health", "Contractual & Services",
                 "Supplies & Materials", "Utilities & Fuel", "Other"]
EXPENSE_COLOR = dict(zip(EXPENSE_ORDER, SERIES[:6]))

FLOW_COLOR = {"Admissions": SERIES[0], "Exits": SERIES[1], "Net change": SERIES[2]}

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


# ---------------------------------------------------------------- base layout
def base_layout(height: int = 360, **overrides) -> dict:
    layout = dict(
        height=height,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=FONT, size=13, color=INK_2),
        margin=dict(l=8, r=16, t=16, b=8),
        hovermode="closest",
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=GRID,
                        font=dict(family=FONT, size=12, color=INK)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    traceorder="normal",
                    font=dict(size=12, color=INK_2), bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(showgrid=False, linecolor=AXIS, linewidth=1, ticks="",
                   tickfont=dict(color=MUTED), title=dict(font=dict(color=MUTED)),
                   zeroline=False),
        yaxis=dict(showgrid=True, gridcolor=GRID, gridwidth=1, linecolor="rgba(0,0,0,0)",
                   ticks="", tickfont=dict(color=MUTED), title=dict(font=dict(color=MUTED)),
                   zeroline=True, zerolinecolor=AXIS, zerolinewidth=1),
        bargap=0.35,
        bargroupgap=0.08,
    )
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(layout.get(k), dict):
            layout[k] = {**layout[k], **v}
        else:
            layout[k] = v
    return layout


def figure(height: int = 360, **overrides) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(**base_layout(height, **overrides))
    return fig


def bar_marker(color: str, gap: bool = True) -> dict:
    """Thin fill with a 2px surface gap so adjacent/stacked segments never touch."""
    m = dict(color=color)
    if gap:
        m.update(line=dict(color=SURFACE, width=2))
    return m


def choropleth(geojson: dict, values, *, height: int = 480, tickformat: str = ",.0f",
               hovertemplate: str, customdata=None, highlight: str | None = None) -> go.Figure:
    """Illinois county map on the sequential blue ramp. `values` is a Series keyed by county."""
    fig = go.Figure(go.Choropleth(
        geojson=geojson, featureidkey="properties.name",
        locations=values.index, z=values.values,
        colorscale=[[i / 6, c] for i, c in enumerate(SEQ_BLUE)],
        marker=dict(line=dict(color=SURFACE, width=0.8)),
        colorbar=dict(thickness=10, len=0.6, outlinewidth=0, tickfont=dict(color=MUTED),
                      tickformat=tickformat),
        customdata=customdata, hovertemplate=hovertemplate,
    ))
    if highlight and highlight in values.index:
        fig.add_choropleth(geojson=geojson, featureidkey="properties.name", locations=[highlight],
                           z=[0], showscale=False, colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
                           marker=dict(line=dict(color=INK, width=2)), hoverinfo="skip")
    fig.update_layout(**base_layout(height, margin=dict(l=0, r=0, t=0, b=0)))
    fig.update_geos(fitbounds="locations", visible=False, bgcolor=SURFACE, projection_type="mercator")
    return fig


def empty_figure(message: str = "No data for this selection", height: int = 360) -> go.Figure:
    fig = figure(height)
    fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False))
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(color=MUTED, size=14))
    return fig


# ---------------------------------------------------------------- rendering
PLOT_CONFIG = '{"responsive": true, "displayModeBar": false, "scrollZoom": false}'


def plot_html(fig: go.Figure) -> ui.HTML:
    """A figure as a div + Plotly.newPlot call; plotly.min.js is loaded once by the page."""
    div_id = f"plot-{uuid.uuid4().hex}"
    height = fig.layout.height or 360
    return ui.HTML(
        f'<div id="{div_id}" class="plotly-chart" style="width:100%;height:{height}px"></div>'
        f'<script>(function(){{var f={fig.to_json()};'
        f'Plotly.newPlot("{div_id}", f.data, f.layout, {PLOT_CONFIG});}})();</script>'
    )


def output_plot(id: str):
    return ui.output_ui(id)


def render_plot(fn):
    """Decorator: the function returns a go.Figure; it is rendered as HTML."""
    @render.ui
    @functools.wraps(fn)
    def _wrapped():
        return plot_html(fn())
    return _wrapped


def sortable_table(display: pd.DataFrame, sort_values: pd.DataFrame | None = None,
                   pinned_rows: int = 0, height: str = "400px") -> ui.Tag:
    """
    HTML table whose headers sort on click. `display` holds the formatted strings shown;
    `sort_values` (same shape) holds the raw numbers used for ordering, so "1,234" sorts
    numerically. The first `pinned_rows` rows stay on top (e.g. a statewide total).
    """
    sv = display if sort_values is None else sort_values
    head = ui.tags.tr(*[ui.tags.th(c, tabindex="0", title="Click to sort") for c in display.columns])
    rows = []
    for i, (_, row) in enumerate(display.iterrows()):
        cells = []
        for c in display.columns:
            v = sv.iloc[i][c] if c in sv.columns else row[c]
            attrs = {} if isinstance(v, str) else {"data_v": "" if v != v else f"{float(v):.6f}"}
            cells.append(ui.tags.td(str(row[c]), **attrs))
        rows.append(ui.tags.tr(*cells, class_="pinned" if i < pinned_rows else None))
    return ui.div(ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="sortable-table"),
                  class_="sortable-wrap", style=f"max-height:{height}")


SORTABLE_JS = """
document.addEventListener("click", function (e) {
  const th = e.target.closest(".sortable-table th");
  if (!th) return;
  const table = th.closest("table"), tbody = table.querySelector("tbody");
  const idx = Array.from(th.parentNode.children).indexOf(th);
  const asc = th.dataset.dir !== "asc";
  table.querySelectorAll("th").forEach(h => { h.dataset.dir = ""; h.classList.remove("asc", "desc"); });
  th.dataset.dir = asc ? "asc" : "desc"; th.classList.add(asc ? "asc" : "desc");
  const rows = Array.from(tbody.rows), pinned = rows.filter(r => r.classList.contains("pinned"));
  const key = r => { const c = r.cells[idx]; return "v" in c.dataset ? (c.dataset.v === "" ? null : +c.dataset.v) : c.textContent; };
  const sorted = rows.filter(r => !pinned.includes(r)).sort((a, b) => {
    const x = key(a), y = key(b);
    if (x === null) return 1; if (y === null) return -1;
    const d = typeof x === "number" ? x - y : String(x).localeCompare(String(y));
    return asc ? d : -d;
  });
  pinned.concat(sorted).forEach(r => tbody.appendChild(r));
});
"""


# ---------------------------------------------------------------- formatting
def fmt_money(x: float) -> str:
    if x >= 1e9:
        return f"${x / 1e9:,.2f}B"
    if x >= 1e6:
        return f"${x / 1e6:,.1f}M"
    if x >= 1e3:
        return f"${x / 1e3:,.0f}K"
    return f"${x:,.0f}"


def fmt_int(x: float) -> str:
    return f"{x:,.0f}"


def age_label(a: str) -> str:
    return AGE_LABEL.get(a, a)
