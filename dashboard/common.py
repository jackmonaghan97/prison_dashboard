"""Filter controls and helpers shared by the pages."""
import pandas as pd
from shiny import ui

from . import viz


def multi_select(id: str, label: str, choices, placeholder: str = "All"):
    """
    Multi-select dropdown. Nothing selected means "no filter" (every choice), so the
    default state is an empty box reading "All" instead of a wall of tags.
    """
    return ui.input_selectize(
        id, label, choices=choices, multiple=True, remove_button=True,
        options={"placeholder": placeholder, "plugins": ["remove_button"]},
    )


def demo_filters(sexes=viz.SEX_ORDER, races=viz.RACE_ORDER, ages=viz.AGE_ORDER):
    """Sex / race / age dropdowns; empty = all."""
    return [
        multi_select("sex", "Sex", list(sexes)),
        multi_select("race", "Race / ethnicity", list(races)),
        multi_select("age", "Age group", {a: viz.age_label(a) for a in ages}),
    ]


def crime_filter(classes=viz.CRIME_ORDER):
    return multi_select("crime", "Offense class", list(classes))


def reset_button():
    return ui.input_action_button("reset", "Reset filters", class_="btn-outline-secondary btn-sm w-100 mb-2")


def selected(input, id: str, all_choices) -> list:
    """Chosen values for a multi-select, or every choice when nothing is chosen."""
    vals = input[id]() if id in input else None
    return list(vals) if vals else list(all_choices)


def isin_or_all(series: pd.Series, vals) -> pd.Series:
    """Boolean mask for a multi-select: an empty selection matches everything."""
    return series.isin(vals) if vals else pd.Series(True, index=series.index)


def apply_demo(df: pd.DataFrame, input, age_col: str = "age_group") -> pd.DataFrame:
    """Apply the sex/race/age filters (and offense class if the input exists)."""
    mask = (isin_or_all(df["sex"], input.sex()) & isin_or_all(df["race"], input.race())
            & isin_or_all(df[age_col], input.age()))
    if "crime_class" in df.columns and "crime" in input:
        mask &= isin_or_all(df["crime_class"], input.crime())
    return df.loc[mask]


def reset_demo(has_crime: bool = True):
    """Clear the shared sex/race/age(/offense) dropdowns."""
    for id in ["sex", "race", "age"] + (["crime"] if has_crime else []):
        ui.update_selectize(id, selected=[])


def note(text: str):
    return ui.p(text, class_="text-muted small mb-0")
