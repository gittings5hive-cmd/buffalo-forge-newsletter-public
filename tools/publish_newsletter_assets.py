#!/usr/bin/env python
"""Publish an issue's photos and chart PNGs to the public GitHub repo so
render_newsletter.py's raw.githubusercontent.com URLs actually resolve.

Copies ISSUE_DIR/images/* and ISSUE_DIR/charts/* into
<repo_asset_root>/<slug>-<issue_date>/{images,charts}/ (per tools/brand.json's
github_hosting.repo_asset_root), scoped-`git add`s just that new folder,
commits, and pushes. The destination folder is derived entirely from
content.json's own meta.slug/meta.issue_date, so this is identical for every
topic -- nothing here is specific to any one issue.

Run this once per issue, any time after images/charts exist in ISSUE_DIR and
before the rendered HTML is shared anywhere (Vercel, Gmail draft, etc.) --
the <img> tags point straight at these raw URLs with no other hosting step.

Usage:
    python tools/publish_newsletter_assets.py --content ISSUE_DIR/content.json

    # commit locally without pushing (e.g. to inspect the diff first):
    python tools/publish_newsletter_assets.py --content ISSUE_DIR/content.json --no-push
"""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def load_issue(content_path):
    raw = json.loads(Path(content_path).read_text(encoding="utf-8"))
    meta = raw["meta"]
    return meta["slug"], meta["issue_date"], raw.get("images", []), raw.get("charts", [])


def load_github_cfg(brand_path):
    brand = json.loads(Path(brand_path).read_text(encoding="utf-8"))
    cfg = brand.get("github_hosting")
    if not cfg:
        raise SystemExit(f"{brand_path} is missing a 'github_hosting' block.")
    return cfg


def copy_assets(issue_dir, dest_root, images, charts):
    copied = []

    if images:
        images_src = issue_dir / "images"
        dest = dest_root / "images"
        dest.mkdir(parents=True, exist_ok=True)
        for image in images:
            found = None
            for ext in (".jpg", ".jpeg", ".png"):
                candidate = images_src / f"{image['id']}{ext}"
                if candidate.exists():
                    found = candidate
                    break
            if found is None:
                raise SystemExit(f"Image file not found for id {image['id']!r} in {images_src}")
            shutil.copyfile(found, dest / found.name)
            copied.append(dest / found.name)

    if charts:
        charts_src = issue_dir / "charts"
        dest = dest_root / "charts"
        dest.mkdir(parents=True, exist_ok=True)
        for chart in charts:
            found = charts_src / f"{chart['id']}.png"
            if not found.exists():
                raise SystemExit(f"Chart PNG not found: {found}")
            shutil.copyfile(found, dest / found.name)
            copied.append(dest / found.name)

    return copied


def run(cmd):
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"Command failed: {' '.join(cmd)}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--content", required=True, help="Path to the issue's content.json")
    parser.add_argument("--brand", default="tools/brand.json", help="Path to a brand config JSON")
    parser.add_argument("--no-push", action="store_true", help="Commit locally but skip pushing to origin")
    args = parser.parse_args()

    content_path = Path(args.content)
    issue_dir = content_path.parent
    slug, issue_date, images, charts = load_issue(content_path)
    github_cfg = load_github_cfg(args.brand)

    if not images and not charts:
        print("No images or charts in content.json -- nothing to publish.")
        return

    asset_root = PROJECT_ROOT / github_cfg.get("repo_asset_root", "newsletter-assets") / f"{slug}-{issue_date}"
    copied = copy_assets(issue_dir, asset_root, images, charts)

    rel_root = asset_root.relative_to(PROJECT_ROOT).as_posix()
    run(["git", "add", rel_root])

    staged = run(["git", "diff", "--cached", "--name-only"])
    if not staged:
        print("Nothing new to commit (assets already published).")
        return

    run(["git", "commit", "-m", f"Add media for {slug} issue ({issue_date})"])
    print(f"Committed {len(copied)} file(s) under {rel_root}/")

    if args.no_push:
        print(
            "--no-push set: commit created locally but not pushed. "
            "raw.githubusercontent.com URLs will 404 until you push."
        )
    else:
        run(["git", "push"])
        print("Pushed to origin.")

    owner = github_cfg["owner"]
    repo = github_cfg["repo"]
    branch = github_cfg.get("branch", "main")
    print("\nPublished asset URLs:")
    for path in copied:
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        print(f"  https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{rel}")


if __name__ == "__main__":
    main()
