"""Module-level rendering-mode flag.

Lives here (not in canvas.py) so element items can check it without taking
a circular import on the canvas module.
"""

# True while LaceCanvas._render_for_output is producing print / PDF / SVG
# output.  Element paint() methods consult this to suppress on-screen-only
# adornments (direction markers, etc.) that shouldn't end up on the pricking.
output_rendering = False
