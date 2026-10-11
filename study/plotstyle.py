"""Shared style for the figures of the thesis (RQ1 and RQ3).

The figures are static and meant for a printed document, so they follow a few
fixed rules:
  * one sans typeface, text always in ink colours (never in a series colour);
  * a single series is drawn in one blue; versions of the tool that follow
    an order (original -> final) use shades of that same blue, lighter for the
    older one;
  * thin bars with a rounded end and a square base, a recessive hairline grid
    only where values are not written next to the marks;
  * numbers in Spanish format (1.234 and 56,7 %).
"""

from __future__ import annotations

import math
import statistics
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

matplotlib.use("Agg")          # files only, no window

SURFACE = "#ffffff"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"
# Ordered versions of the tool, lighter for older (one hue, validated as an
# ordinal ramp against white).
VERSION_COLOURS = {"original": "#86b6ef", "intermedia": "#3987e5", "final": "#1c5cab"}

WIDTH = 6.0            # inches, close to the text width of the thesis
ROW = 0.30             # inches per bar row in horizontal bar charts
BAR = 0.16             # bar thickness in inches (well under 24 px)
FONT = 9


def setup() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": FONT,
        "text.color": INK,
        "axes.labelcolor": INK_2,
        "axes.edgecolor": BASELINE,
        "axes.linewidth": 0.8,
        "axes.facecolor": SURFACE,
        "figure.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK_2,
        "ytick.labelcolor": INK_2,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "legend.frameon": False,
        "pdf.fonttype": 42,
        "svg.fonttype": "none",
    })


# --------------------------------------------------------------------------
# Number formatting (Spanish conventions, as in the rest of the thesis)
# --------------------------------------------------------------------------

def num(value: float, decimals: int = 0) -> str:
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def pct(value: float, decimals: int = 1) -> str:
    return f"{num(value, decimals)} %"


def compact(value: float) -> str:
    if value >= 1000:
        return f"{num(value / 1000, 0 if value >= 10000 else 1)} mil"
    return num(value)


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------

def _text_width_in(fig, labels, size=FONT) -> float:
    renderer = fig.canvas.get_renderer()
    widest = 0.0
    for label in labels:
        t = fig.text(0, 0, label, fontsize=size)
        widest = max(widest, t.get_window_extent(renderer).width)
        t.remove()
    return widest / fig.dpi


def _clean(ax, keep=("bottom",)) -> None:
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(side in keep)


def _units_per_pixel(ax):
    inv = ax.transData.inverted()
    (x0, y0), (x1, y1) = inv.transform((0, 0)), inv.transform((1, 1))
    return abs(x1 - x0), abs(y1 - y0)


def rounded_bar(ax, base, start, length, thickness, colour, horizontal=True, radius_pt=3.0):
    """Bar with a rounded data end and a square end at the baseline.

    Axis limits and figure margins must be final before calling, because the
    corner radius is converted from points to data units.
    """
    if length <= 0:
        return
    ux, uy = _units_per_pixel(ax)
    r_px = radius_pt * ax.figure.dpi / 72
    rx, ry = r_px * ux, r_px * uy
    along, across = (rx, ry) if horizontal else (ry, rx)
    if horizontal:
        xy, w, h = (start, base), length, thickness
    else:
        xy, w, h = (base, start), thickness, length
    if length < 2 * along or thickness < 2 * across:
        ax.add_patch(Rectangle(xy, w, h, facecolor=colour, linewidth=0))
        return
    ax.add_patch(FancyBboxPatch(xy, w, h, boxstyle=f"round,pad=0,rounding_size={rx}",
                                mutation_aspect=uy / ux, facecolor=colour, linewidth=0))
    if horizontal:
        ax.add_patch(Rectangle(xy, length - along, thickness, facecolor=colour, linewidth=0))
    else:
        ax.add_patch(Rectangle(xy, thickness, length - along, facecolor=colour, linewidth=0))


def save(fig, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix(".pdf"))
    fig.savefig(path.with_suffix(".png"), dpi=200)
    plt.close(fig)


# --------------------------------------------------------------------------
# Chart forms
# --------------------------------------------------------------------------

def hbars(labels, values, path, value_text=None, colour=BLUE, xmax=None, note=None):
    """Ranked horizontal bars, one series; every bar carries its value."""
    value_text = value_text or num
    n = len(labels)
    height = n * ROW + 0.25 + (0.25 if note else 0)
    fig = plt.figure(figsize=(WIDTH, height))
    left = _text_width_in(fig, labels) + 0.12
    right_pad = 0.75                       # room for the value at the bar tip
    ax = fig.add_axes([left / WIDTH, (0.12 + (0.25 if note else 0)) / height,
                       (WIDTH - left - right_pad) / WIDTH, (n * ROW) / height])
    top = xmax or max(values) or 1
    ax.set_xlim(0, top)
    ax.set_ylim(n - 0.5, -0.5)
    _clean(ax, keep=("left",))
    ax.spines["left"].set_color(BASELINE)
    ax.xaxis.set_major_locator(NullLocator())
    ax.set_yticks(range(n), labels)
    thickness = BAR / ROW
    for i, value in enumerate(values):
        rounded_bar(ax, i - thickness / 2, 0, value, thickness, colour)
        ax.annotate(value_text(value), (value, i), xytext=(4, 0), textcoords="offset points",
                    va="center", ha="left", color=INK_2, fontsize=FONT - 0.5)
    if note:
        # Aligned with the bars when it fits, otherwise with the figure edge.
        x = left / WIDTH
        if left + _text_width_in(fig, [note], FONT - 1) > WIDTH - 0.05:
            x = 0.01
        fig.text(x, 0.06 / height, note, color=MUTED, fontsize=FONT - 1, va="bottom")
    save(fig, path)


def columns(labels, values, path, xlabel="", value_text=None, colour=BLUE, height=2.6):
    """Columns over ordered categories (for example, bins of a distribution)."""
    value_text = value_text or num
    fig = plt.figure(figsize=(WIDTH, height))
    ax = fig.add_axes([0.04, 0.22, 0.92, 0.70])
    n = len(labels)
    ax.set_xlim(-0.6, n - 0.4)
    ax.set_ylim(0, max(values) * 1.12 or 1)
    _clean(ax)
    ax.yaxis.set_major_locator(NullLocator())
    ax.set_xticks(range(n), labels)
    ax.tick_params(axis="x", pad=4)
    if xlabel:
        ax.set_xlabel(xlabel, labelpad=6)
    width_in = ax.get_position().width * WIDTH
    thickness = min(0.6, (BAR * 1.4) / (width_in / n))
    for i, value in enumerate(values):
        rounded_bar(ax, i - thickness / 2, 0, value, thickness, colour, horizontal=False)
        ax.annotate(value_text(value), (i, value), xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", color=INK_2, fontsize=FONT - 0.5)
    save(fig, path)


def _log_ticks(ax, axis: str, top: float) -> None:
    ticks = [0, 1] + [10 ** k for k in range(1, int(math.log10(max(top, 10))) + 2)]
    locator = FixedLocator([t for t in ticks if t <= top * 1.5])
    formatter = FuncFormatter(lambda v, _: compact(v))
    target = ax.xaxis if axis == "x" else ax.yaxis
    target.set_major_locator(locator)
    target.set_major_formatter(formatter)
    target.set_minor_locator(NullLocator())


def dumbbell(labels, before, after, path, names=("PromptSet original", "promptset-extended"),
             log=True, xlabel=""):
    """Before -> after per item: two shades of one hue joined by a line."""
    n = len(labels)
    height = n * ROW + 0.85
    fig = plt.figure(figsize=(WIDTH, height))
    left = _text_width_in(fig, labels) + 0.15
    ax = fig.add_axes([left / WIDTH, 0.45 / height, (WIDTH - left - 0.35) / WIDTH,
                       (n * ROW) / height])
    top = max(max(before), max(after), 1)
    if log:
        ax.set_xscale("symlog", linthresh=1, linscale=0.4)
        ax.set_xlim(0, top * 2.2)
        _log_ticks(ax, "x", top)
    else:
        ax.set_xlim(0, top * 1.12)
    ax.set_ylim(n - 0.5, -0.5)
    _clean(ax, keep=())
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.set_yticks(range(n), labels)
    old, new = VERSION_COLOURS["original"], VERSION_COLOURS["final"]
    for i, (b, a) in enumerate(zip(before, after)):
        ax.plot([b, a], [i, i], color=BASELINE, linewidth=1.6, zorder=2, solid_capstyle="round")
        ax.scatter([b], [i], s=42, color=old, edgecolors=SURFACE, linewidths=1.4, zorder=3)
        ax.scatter([a], [i], s=42, color=new, edgecolors=SURFACE, linewidths=1.4, zorder=4)
        # Values sit outside the pair: the smaller on the left, the larger on the right.
        lo, hi = (a, b) if a <= b else (b, a)
        ax.annotate(num(lo), (lo, i), xytext=(-7, 0), textcoords="offset points",
                    ha="right", va="center", color=INK_2, fontsize=FONT - 1)
        if hi != lo:
            ax.annotate(num(hi), (hi, i), xytext=(7, 0), textcoords="offset points",
                        ha="left", va="center", color=INK_2, fontsize=FONT - 1)
    if xlabel:
        ax.set_xlabel(xlabel, labelpad=5)
    handles = [plt.Line2D([], [], marker="o", linestyle="", markersize=6.5, color=c,
                          markeredgecolor=SURFACE) for c in (old, new)]
    fig.legend(handles, names, loc="upper left", ncol=2, bbox_to_anchor=(left / WIDTH - 0.01, 1.0),
               handletextpad=0.3, columnspacing=1.4, fontsize=FONT - 0.5, labelcolor=INK_2)
    save(fig, path)


def scatter_compare(x, y, path, xlabel, ylabel, note_below="", height=3.6):
    """One dot per item, with the y = x diagonal as reference."""
    fig = plt.figure(figsize=(WIDTH * 0.72, height))
    ax = fig.add_axes([0.16, 0.15, 0.78, 0.78])
    top = max(max(x, default=1), max(y, default=1), 1)
    for axis in ("x", "y"):
        getattr(ax, f"set_{axis}scale")("symlog", linthresh=1, linscale=0.4)
        getattr(ax, f"set_{axis}lim")(0, top * 2.2)
        _log_ticks(ax, axis, top)
    _clean(ax, keep=())
    ax.grid(color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.plot([0, top * 2.2], [0, top * 2.2], color=BASELINE, linewidth=1, zorder=1)
    ax.scatter(x, y, s=30, color=BLUE, alpha=0.8, edgecolors=SURFACE, linewidths=1.1, zorder=3)
    ax.set_xlabel(xlabel, labelpad=5)
    ax.set_ylabel(ylabel, labelpad=5)
    if note_below:
        ax.text(0.98, 0.04, note_below, transform=ax.transAxes, ha="right", va="bottom",
                color=MUTED, fontsize=FONT - 1)
    save(fig, path)


def strip_by_group(groups, series, path, ylabel, xlabel="", seed=7):
    """Distribution per ordered group: jittered dots plus the median.

    The median of each group is drawn as a short ink line and written under
    the group name, so no label sits on top of the dots.
    """
    import random
    rng = random.Random(seed)
    fig = plt.figure(figsize=(WIDTH, 3.1))
    ax = fig.add_axes([0.11, 0.24, 0.86, 0.72])
    top = max((max(v) for v in series if v), default=1)
    ax.set_yscale("symlog", linthresh=1, linscale=0.4)
    ax.set_ylim(-0.3, top * 2.2)
    _log_ticks(ax, "y", top)
    ax.set_xlim(-0.6, len(groups) - 0.4)
    _clean(ax, keep=())
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ticks = []
    for i, values in enumerate(series):
        xs = [i + rng.uniform(-0.22, 0.22) for _ in values]
        ax.scatter(xs, values, s=16, color=BLUE, alpha=0.45, edgecolors=SURFACE,
                   linewidths=0.6, zorder=3)
        if values:
            med = statistics.median(values)
            ax.plot([i - 0.3, i + 0.3], [med, med], color=INK, linewidth=2,
                    solid_capstyle="round", zorder=4)
            ticks.append(f"{groups[i]}\nmediana {num(med, 1 if med % 1 else 0)}")
        else:
            ticks.append(groups[i])
    ax.set_xticks(range(len(groups)), ticks)
    ax.set_ylabel(ylabel, labelpad=5)
    if xlabel:
        ax.set_xlabel(xlabel, labelpad=6)
    save(fig, path)
