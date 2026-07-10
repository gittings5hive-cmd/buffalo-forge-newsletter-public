# Workflow: Write Newsletter

## Objective
Given a topic, research it, structure the findings, generate a couple of data-driven infographics, and deliver a polished newsletter two ways: a hosted web page and a Gmail draft (draft only -- never sent automatically).

## Required inputs
- **Topic** (required): what the newsletter is about.
- **Angle/audience** (optional): if the user gives one, use it to shape the research and tone. Otherwise pick a sensible general-audience angle.
- **Recipient** (optional): who the Gmail draft should be addressed to. Default to `NEWSLETTER_DRAFT_TO` in `.env`. If that's unset, ask the user -- never guess an email address.

## Brand voice

This is the **Buffalo Forge & Foundry** newsletter (`tools/brand.json`). Write copy that is Authentic, Skilled, Educational, Community Focused, Industrial, Inspirational -- not Corporate, Trendy, Overly Technical, or Abstract. Prefer concrete, hands-on language over marketing-speak.

## Tools this workflow uses
- Your own WebSearch / WebFetch (research -- no dedicated search-API tool exists for this).
- `tools/generate_chart.py` (bar/line chart PNGs).
- `tools/render_newsletter.py` (renders `content.json` -> web/email HTML).
- `mcp__claude_ai_Vercel__deploy_to_vercel` (hosts the web page + chart/photo images).
- `mcp__claude_ai_Gmail__create_draft` (creates the review draft).
- The **dataviz** skill (which findings become a chart vs. a stat_callout vs. a quote).
- The **artifact-design** skill (if you're touching `tools/templates/web.html.j2` itself).

## Steps

1. **Set up the issue directory.** Slugify the topic and use today's date:
   `ISSUE_DIR = .tmp/newsletter/<slug>-<issue_date>/`

2. **Research.** Use WebSearch/WebFetch to gather ~5-10 credible sources. Take real notes -- exact numbers, direct quotes with attribution, publisher names, URLs. You'll need all of this for `content.json`.

3. **Write `ISSUE_DIR/content.json`.** Schema (see `tools/render_newsletter.py`'s pydantic models for the authoritative version):

   ```json
   {
     "meta": {"topic": "...", "slug": "...", "issue_date": "YYYY-MM-DD", "title": "...", "subtitle": "optional"},
     "hero": {"eyebrow": "optional", "summary": "1-2 sentences, also doubles as the email plaintext fallback"},
     "sections": [
       {
         "id": "section-1",
         "heading": "...",
         "blocks": [
           {"type": "paragraph", "text": "..."},
           {"type": "chart", "chart_id": "chart-1"},
           {"type": "stat_callout", "value": "42%", "label": "...", "tone": "positive|negative|neutral"},
           {"type": "quote", "text": "...", "attribution": "Name, Title"},
           {"type": "image", "image_id": "img-1"}
         ]
       }
     ],
     "charts": [
       {"id": "chart-1", "type": "bar|line", "title": "...", "subtitle": "optional", "unit": "%",
        "data": [{"label": "A", "value": 42.0}], "source_id": "src-1"}
     ],
     "images": [
       {"id": "img-1", "caption": "optional caption shown under the photo", "alt": "optional alt text (falls back to caption)", "source_id": "src-1"}
     ],
     "sources": [
       {"id": "src-1", "title": "...", "url": "https://...", "publisher": "...", "accessed_date": "YYYY-MM-DD"}
     ]
   }
   ```

   Blocks are an **ordered list per section** -- a quote can sit between two paragraphs. `bar`/`data` entries are `{label, value}`; `line`/`data` entries are `{x, y}`.

   Consult the **dataviz** skill while deciding: real numbers with a shape (a trend, a breakdown) become a `chart` block; a single number becomes a `stat_callout`, never a chart; qualitative findings become `quote` or `paragraph`; a real photo (e.g. a video still) is an `image` block. A section, or the whole issue, can have **zero charts and/or zero images** -- both templates handle empty arrays correctly.

4. **Generate chart images.** For each entry in `content.json["charts"]`:
   ```
   python tools/generate_chart.py --content ISSUE_DIR/content.json --chart-id <id> \
     --brand tools/brand.json --out ISSUE_DIR/charts/<id>.png
   ```
   Only `bar` and `line` are supported -- this is enforced with a clear error, by design.

   For each entry in `content.json["images"]`, place the actual photo file at `ISSUE_DIR/images/<id>.jpg` (or `.png`) -- `render_newsletter.py` looks it up by id, there's no generator script for these since they're real photos, not generated charts.

5. **Render the web variant** (relative asset paths, safe before anything is deployed):
   ```
   python tools/render_newsletter.py --content ISSUE_DIR/content.json --brand tools/brand.json \
     --variant web --base-url . --out ISSUE_DIR/web.html
   ```

6. **Deploy to Vercel.** One call, one reused project (name comes from `brand.json`'s `vercel_project_name` -- don't invent a new project per issue):
   `mcp__claude_ai_Vercel__deploy_to_vercel` with `target: "preview"`, files = `ISSUE_DIR/web.html` renamed to `index.html`, every PNG under `ISSUE_DIR/charts/` at the same relative path, every photo under `ISSUE_DIR/images/` at the same relative path, plus `tools/assets/logo/buffalo-forge-script-bison.png` uploaded as `assets/logo.png`. Capture the returned URL -- this is the deploy **root**, not a path to any one asset folder.

7. **Render the email variant**, now that a real deploy URL exists (must be absolute -- the script refuses a relative one). Charts resolve to `<deploy-url>/charts/<id>.png`, photos to `<deploy-url>/images/<id>.jpg`, and the logo to `<deploy-url>/assets/logo.png` automatically:
   ```
   python tools/render_newsletter.py --content ISSUE_DIR/content.json --brand tools/brand.json \
     --variant email --base-url "<deploy-url>" --out ISSUE_DIR/email.html
   ```

8. **Resolve the recipient.** Read `NEWSLETTER_DRAFT_TO` from `.env`. If unset, ask the user.

9. **Create the Gmail draft** (never send): `mcp__claude_ai_Gmail__create_draft` with `subject = content.meta.title`, `body` = plain text built from `hero.summary` + the deploy URL, `htmlBody` = the contents of `ISSUE_DIR/email.html`.

10. **Report back**: the Vercel URL and confirmation the Gmail draft was created (with its ID), explicitly noting it was **not sent**.

## Notes / things learned
- Charts always render in light mode only (a PNG can't retheme itself) and sit in a fixed light card frame -- this stays legible even when the web page itself is in dark mode.
- The email template is intentionally single-theme (light) -- email client dark-mode support is too inconsistent to build against.
- `render_newsletter.py` must be run **twice**, web before deploy and email after -- there's no way around the two-pass sequencing since email HTML has no relative-path concept.
- Vercel: reuse one project across issues; don't try to build a cumulative multi-issue archive tree (would mean re-uploading every prior issue's bytes each run). Vercel's own deployment history and the Gmail drafts folder already double as a browsable archive. A real cross-issue index page is an explicit non-goal for now.
- `tools/brand.json` holds Buffalo Forge & Foundry's real colors/fonts/logo/buttons (derived from the reference sheets in `branding/`). The categorical chart palette is capped at 3 hues (Forge Orange/Molten Copper/Fire Gold) -- the brand's warm hue range doesn't support more without failing the dataviz skill's CVD validator; `generate_chart.py` cycles them with direct value labels as the prescribed relief for >3 categories.
- The "Read the Full Issue" CTA button only renders when a real `web_url` is known (i.e. whenever `--base-url` isn't `.`) -- in practice that's the email variant, since the web variant is always rendered *before* the Vercel URL exists. This is automatic; no special-casing needed per variant.
- Everything under `.tmp/newsletter/<slug>-<date>/` is disposable -- the Vercel deployment and the Gmail draft are the durable deliverables.
