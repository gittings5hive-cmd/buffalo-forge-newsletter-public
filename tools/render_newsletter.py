#!/usr/bin/env python
"""Render a newsletter issue's content.json into web or email HTML.

Photos, chart PNGs, and the brand logo always resolve to permanent
raw.githubusercontent.com URLs (per tools/brand.json's github_hosting block),
regardless of variant -- run tools/publish_newsletter_assets.py first so
those URLs actually resolve (see that script's docstring). This is topic-
agnostic: the per-issue path is derived from content.json's own
meta.slug/meta.issue_date, nothing is hardcoded per topic.

--base-url has a narrower job now: it only controls the page's own "Read the
Full Issue" link target (web_url), since that's the one thing that
genuinely doesn't exist until the page is deployed somewhere.

  --variant web    --base-url "." before a deploy exists (no CTA link yet),
                    or the real deploy URL once one exists. Full light/dark
                    theming.
  --variant email   requires an absolute --base-url (the deploy URL, for the
                    CTA link -- email HTML has no "relative to this file"
                    concept), single-theme (light) styling, and gets piped
                    through premailer to inline all CSS -- Outlook and other
                    clients need every style on the tag itself, not in a
                    <style> block.

Run once per variant, in this order: publish assets, web (relative CTA is
fine pre-deploy), deploy, then email (now that a real deploy URL exists for
the CTA link).

Usage:
    python tools/publish_newsletter_assets.py --content ISSUE_DIR/content.json

    python tools/render_newsletter.py --content ISSUE_DIR/content.json \\
        --brand tools/brand.json --variant web \\
        --base-url . --out ISSUE_DIR/web.html

    python tools/render_newsletter.py --content ISSUE_DIR/content.json \\
        --brand tools/brand.json --variant email \\
        --base-url https://your-deploy.vercel.app \\
        --out ISSUE_DIR/email.html
"""
import argparse
import json
import logging
from pathlib import Path
from typing import Annotated, List, Literal, Optional, Union

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from PIL import Image
from pydantic import BaseModel, Field, ValidationError

TEMPLATES_DIR = Path(__file__).parent / "templates"
PROJECT_ROOT = Path(__file__).parent.parent
CHART_DISPLAY_WIDTH = 600
LOGO_DISPLAY_HEIGHT = 56


# ---------------------------------------------------------------------------
# content.json schema -- validated up front so a malformed research/synthesis
# step fails with one specific field error instead of a confusing template
# KeyError three steps later.
# ---------------------------------------------------------------------------

class Meta(BaseModel):
    topic: str
    slug: str
    issue_date: str
    title: str
    subtitle: Optional[str] = None


class Hero(BaseModel):
    eyebrow: Optional[str] = None
    summary: str


class ParagraphBlock(BaseModel):
    type: Literal["paragraph"]
    text: str


class ChartBlock(BaseModel):
    type: Literal["chart"]
    chart_id: str


class StatCalloutBlock(BaseModel):
    type: Literal["stat_callout"]
    value: str
    label: str
    tone: Literal["positive", "negative", "neutral"] = "neutral"


class QuoteBlock(BaseModel):
    type: Literal["quote"]
    text: str
    attribution: Optional[str] = None


class ImageBlock(BaseModel):
    type: Literal["image"]
    image_id: str


Block = Annotated[
    Union[ParagraphBlock, ChartBlock, StatCalloutBlock, QuoteBlock, ImageBlock],
    Field(discriminator="type"),
]


class Section(BaseModel):
    id: str
    heading: str
    blocks: List[Block]


class Chart(BaseModel):
    id: str
    type: Literal["bar", "line"]
    title: Optional[str] = None
    subtitle: Optional[str] = None
    unit: str = ""
    data: List[dict]
    source_id: Optional[str] = None


class Source(BaseModel):
    id: str
    title: str
    url: str
    publisher: Optional[str] = None
    accessed_date: Optional[str] = None


class Photo(BaseModel):
    """A real photo (e.g. a video still), as opposed to a generated chart."""

    id: str
    caption: Optional[str] = None
    alt: Optional[str] = None
    source_id: Optional[str] = None


class Content(BaseModel):
    meta: Meta
    hero: Hero
    sections: List[Section]
    charts: List[Chart] = []
    images: List[Photo] = []
    sources: List[Source] = []


def load_content(content_path):
    raw = json.loads(Path(content_path).read_text(encoding="utf-8"))
    try:
        return Content.model_validate(raw)
    except ValidationError as exc:
        raise SystemExit(f"content.json failed validation:\n{exc}")


def load_brand(brand_path):
    return json.loads(Path(brand_path).read_text(encoding="utf-8"))


def get_github_hosting(brand):
    github_cfg = brand.get("github_hosting")
    if not github_cfg:
        raise SystemExit(
            "brand.json is missing a 'github_hosting' block -- required to "
            "resolve photo/chart/logo URLs. See tools/brand.json's "
            "github_hosting field for the expected shape "
            "(owner/repo/branch/repo_asset_root)."
        )
    return github_cfg


def resolve_github_raw_url(github_cfg, repo_relative_path):
    owner = github_cfg["owner"]
    repo = github_cfg["repo"]
    branch = github_cfg.get("branch", "main")
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{repo_relative_path}"


def issue_asset_root(github_cfg, meta):
    """Repo-relative folder this issue's images/charts get published under
    by publish_newsletter_assets.py -- derived from the issue's own slug and
    date, so it's identical per topic with no hardcoding."""
    prefix = github_cfg.get("repo_asset_root", "newsletter-assets")
    return f"{prefix}/{meta.slug}-{meta.issue_date}"


def build_charts_by_id(content, charts_dir, github_cfg):
    """Resolve each chart to a display-ready {src, width, height, title, source}."""
    sources_by_id = {s.id: s for s in content.sources}
    asset_root = issue_asset_root(github_cfg, content.meta)
    charts_by_id = {}
    for chart in content.charts:
        png_path = charts_dir / f"{chart.id}.png"
        if not png_path.exists():
            raise SystemExit(
                f"Chart PNG not found: {png_path}. Run generate_chart.py for "
                f"chart id {chart.id!r} before rendering."
            )
        with Image.open(png_path) as img:
            native_width, native_height = img.size
        display_width = min(CHART_DISPLAY_WIDTH, native_width)
        display_height = round(display_width * native_height / native_width)

        charts_by_id[chart.id] = {
            "src": resolve_github_raw_url(github_cfg, f"{asset_root}/charts/{chart.id}.png"),
            "width": display_width,
            "height": display_height,
            "title": chart.title,
            "subtitle": chart.subtitle,
            "source": sources_by_id.get(chart.source_id) if chart.source_id else None,
        }
    return charts_by_id


def build_images_by_id(content, images_dir, github_cfg):
    """Resolve each real photo to a display-ready {src, width, height, caption, source}.

    Unlike charts (always PNG, generated by generate_chart.py), photos arrive
    pre-made (e.g. video stills) so either .jpg or .png is accepted.
    """
    sources_by_id = {s.id: s for s in content.sources}
    asset_root = issue_asset_root(github_cfg, content.meta)
    images_by_id = {}
    for photo in content.images:
        image_path = None
        for ext in (".jpg", ".jpeg", ".png"):
            candidate = images_dir / f"{photo.id}{ext}"
            if candidate.exists():
                image_path = candidate
                break
        if image_path is None:
            raise SystemExit(
                f"Image file not found for id {photo.id!r} in {images_dir} "
                "(expected a .jpg or .png)."
            )
        with Image.open(image_path) as img:
            native_width, native_height = img.size
        display_width = min(CHART_DISPLAY_WIDTH, native_width)
        display_height = round(display_width * native_height / native_width)

        images_by_id[photo.id] = {
            "src": resolve_github_raw_url(github_cfg, f"{asset_root}/images/{image_path.name}"),
            "width": display_width,
            "height": display_height,
            "caption": photo.caption,
            "alt": photo.alt or photo.caption or "Photo",
            "source": sources_by_id.get(photo.source_id) if photo.source_id else None,
        }
    return images_by_id


def build_logo(brand, github_cfg):
    """Resolve the brand logo to its raw.githubusercontent.com URL --
    logo_path is already a repo-relative path, so no per-issue folder."""
    logo_path = brand.get("logo_path")
    if not logo_path:
        return None
    full_path = PROJECT_ROOT / logo_path
    if not full_path.exists():
        raise SystemExit(f"brand logo_path not found: {full_path}")
    with Image.open(full_path) as img:
        native_width, native_height = img.size
    display_height = LOGO_DISPLAY_HEIGHT
    display_width = round(display_height * native_width / native_height)
    return {
        "src": resolve_github_raw_url(github_cfg, logo_path),
        "width": display_width,
        "height": display_height,
        "on_dark_band": brand.get("logo_on_dark_band", False),
    }


def render(content_path, brand_path, variant, base_url, out_path):
    content = load_content(content_path)
    brand = load_brand(brand_path)

    if variant == "email" and (base_url in (".", "") or not base_url.startswith("http")):
        raise SystemExit(
            "--variant email requires an absolute --base-url "
            "(e.g. https://your-deploy.vercel.app) -- it's used for the "
            "'Read the Full Issue' link; email HTML has no concept of a "
            "path relative to the message itself."
        )

    github_cfg = get_github_hosting(brand)
    charts_dir = Path(content_path).parent / "charts"
    images_dir = Path(content_path).parent / "images"
    charts_by_id = build_charts_by_id(content, charts_dir, github_cfg)
    images_by_id = build_images_by_id(content, images_dir, github_cfg)
    logo = build_logo(brand, github_cfg)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=True,
    )

    status = {k: v for k, v in brand["colors"]["status"].items() if not k.startswith("_")}
    context = {
        "meta": content.meta,
        "hero": content.hero,
        "sections": content.sections,
        "sources": content.sources,
        "charts_by_id": charts_by_id,
        "images_by_id": images_by_id,
        "logo": logo,
        "web_url": base_url if base_url != "." else None,
        "colors_light": brand["colors"]["light"],
        "colors_dark": brand["colors"]["dark"],
        "status_light": {name: tones["light"] for name, tones in status.items()},
        "status_dark": {name: tones["dark"] for name, tones in status.items()},
        "fonts": brand["fonts"],
        "layout": brand["layout"],
        "buttons": brand.get("buttons"),
    }

    template_name = "web.html.j2" if variant == "web" else "email.html.j2"
    html = env.get_template(template_name).render(**context)

    if variant == "email":
        from premailer import Premailer
        import cssutils

        cssutils.log.setLevel(logging.CRITICAL)
        # premailer unconditionally copies inline width/height CSS onto the
        # HTML attributes (force=True internally) -- without this, our
        # deliberate pixel width/height attributes (Outlook's fallback when it
        # ignores CSS max-width) get clobbered with the literal "100%"/"auto"
        # strings from the responsive img style.
        html = Premailer(
            html,
            keep_style_tags=False,
            disable_validation=True,
            disable_basic_attributes=["width", "height"],
        ).transform()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--content", required=True, help="Path to the issue's content.json")
    parser.add_argument("--brand", default="tools/brand.json", help="Path to a brand config JSON")
    parser.add_argument("--variant", required=True, choices=["web", "email"])
    parser.add_argument(
        "--base-url",
        required=True,
        help='Only controls the "Read the Full Issue" CTA link target -- '
        "images/charts/logo always resolve to raw.githubusercontent.com "
        "regardless of this value (see github_hosting in brand.json). "
        'Use "." before a deploy exists (no CTA link), or the deployed '
        "root URL once one exists (required, and must be absolute, for "
        "--variant email).",
    )
    parser.add_argument("--out", required=True, help="Output HTML path")
    args = parser.parse_args()

    out_path = render(args.content, args.brand, args.variant, args.base_url, args.out)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
