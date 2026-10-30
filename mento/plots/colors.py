"""The colours mento draws with.

Kept apart from :mod:`mento.results` so that drawing a section does not load
the report machinery (python-docx, tabulate, the pandas Styler) just to read a
hex code. :mod:`mento.results` re-exports :data:`CUSTOM_COLORS` for whoever
imports it from there.
"""

CUSTOM_COLORS = {
    "blue": "#1f77b4",  # Default Matplotlib blue
    "red": "#d62728",  # Default Matplotlib red
    "dark_gray": "#323232",
    "light_gray": "#e3e3e3",
    "dark_blue": "#073165",
    "mounting": "#ad641b",
}
