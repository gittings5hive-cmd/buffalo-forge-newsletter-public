#!/usr/bin/env python
"""Generate a single bar or line chart PNG for one newsletter issue.

A lone number ("42% increase") is not a chart -- it belongs in a
`stat_callout` content block instead, so only "bar" and "line" are supported
here. Colors and typography come from the brand config so swapping in real
brand assets later never requires touching this script.

Usage:
    python tools/generate_chart.py \\
        --content .tmp/newsletter/<slug>-<date>/content.json \\
        --chart-id chart-1 \\
        --brand tools/brand.json \\
        --out .tmp/newsletter/<slug>-<date>/charts/chart-1.png
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager
import matplotlib.pyplot as plt

SUPPORTED_TYPES = {"bar", "line"}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_chart(content, chart_id):
    for chart in content.get("charts", []):
        if chart["id"] == chart_id:
            return chart
    raise SystemExit(f"No chart with id {chart_id!r} in content.json")


def register_brand_font(brand):
    """Use the brand's bundled body-font file if present, else fall back cleanly.

    Charts use the body font role (most legible for tick/data labels at small
    sizes) rather than trying to mix in the heading face for just the title --
    not worth the complexity when no font binaries are bundled either way.
    """
    fonts = brand.get("fonts", {}).get("body", {})
    family = fonts.get("family_name", "DejaVu Sans")
    for key in ("regular_path", "bold_path"):
        path = fonts.get(key)
        if path and Path(path).exists():
            font_manager.fontManager.addfont(path)
    available = {f.name for f in font_manager.fontManager.ttflist}
    return family if family in available else "DejaVu Sans"


def style_axes(ax, colors):
    ax.set_facecolor(colors["surface"])
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(colors["baseline"])
        ax.spines[spine].set_linewidth(1)
    ax.tick_params(colors=colors["muted_ink"], labelsize=10, length=0)
    ax.yaxis.grid(True, color=colors["gridline"], linewidth=1)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)


def render_bar(ax, chart, colors):
    palette = colors["categorical"]
    labels = [d["label"] for d in chart["data"]]
    values = [d["value"] for d in chart["data"]]
    bar_colors = [palette[i % len(palette)] for i in range(len(values))]
    bars = ax.bar(labels, values, color=bar_colors, width=0.55)
    unit = chart.get("unit", "")
    for bar, value in zip(bars, values):
        ax.annotate(
            f"{value:g}{unit}",
            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=10,
            color=colors["primary_ink"],
        )


def render_line(ax, chart, colors):
    accent = colors["categorical"][0]
    xs = [d["x"] for d in chart["data"]]
    ys = [d["y"] for d in chart["data"]]
    ax.plot(
        xs,
        ys,
        color=accent,
        linewidth=2,
        marker="o",
        markersize=6,
        markerfacecolor=accent,
        markeredgecolor=colors["surface"],
        markeredgewidth=1.5,
    )
    unit = chart.get("unit", "")
    ax.annotate(
        f"{ys[-1]:g}{unit}",
        xy=(xs[-1], ys[-1]),
        xytext=(6, 0),
        textcoords="offset points",
        ha="left",
        va="center",
        fontsize=10,
        fontweight="bold",
        color=colors["primary_ink"],
    )


def generate_chart(content_path, chart_id, brand_path, out_path):
    content = load_json(content_path)
    brand = load_json(brand_path)
    colors = brand["colors"]["light"]
    chart = find_chart(content, chart_id)

    if chart["type"] not in SUPPORTED_TYPES:
        raise SystemExit(
            f"Unsupported chart type {chart['type']!r} for chart {chart_id!r}. "
            f"generate_chart.py only supports {sorted(SUPPORTED_TYPES)} -- "
            "a single number belongs in a stat_callout block, not a chart."
        )

    family = register_brand_font(brand)
    plt.rcParams["font.family"] = family

    fig, ax = plt.subplots(figsize=(6, 3.4), dpi=200)
    fig.patch.set_facecolor(colors["surface"])
    style_axes(ax, colors)

    if chart["type"] == "bar":
        render_bar(ax, chart, colors)
    else:
        render_line(ax, chart, colors)

    title = chart.get("title")
    if title:
        ax.set_title(
            title,
            loc="left",
            fontsize=13,
            color=colors["primary_ink"],
            fontweight="bold",
            pad=14,
        )
    subtitle = chart.get("subtitle")
    if subtitle:
        ax.text(
            0,
            1.03,
            subtitle,
            transform=ax.transAxes,
            fontsize=10,
            color=colors["secondary_ink"],
        )

    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight", facecolor=colors["surface"])
    plt.close(fig)
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--content", required=True, help="Path to the issue's content.json")
    parser.add_argument("--chart-id", required=True, help="id of the chart entry in content.json to render")
    parser.add_argument("--brand", default="tools/brand.json", help="Path to a brand config JSON")
    parser.add_argument("--out", required=True, help="Output PNG path")
    args = parser.parse_args()

    out_path = generate_chart(args.content, args.chart_id, args.brand, args.out)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
