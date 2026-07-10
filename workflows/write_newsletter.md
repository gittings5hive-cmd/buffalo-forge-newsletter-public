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
- `tools/publish_newsletter_assets.py` (commits+pushes this issue's photos/charts to the public GitHub repo, so `render_newsletter.py`'s raw.githubusercontent.com URLs resolve).
- `tools/render_newsletter.py` (renders `content.json` -> web/email HTML).
- `mcp__claude_ai_Vercel__deploy_to_vercel` (hosts the web page itself -- just `index.html`, no images).
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

5. **Publish photos/charts to GitHub** (skip if this issue has neither):
   ```
   python tools/publish_newsletter_assets.py --content ISSUE_DIR/content.json
   ```
   This copies them into `newsletter-assets/<slug>-<issue_date>/{images,charts}/` in this same repo, commits, and pushes. Both `render_newsletter.py` variants resolve `<img>` URLs straight to `raw.githubusercontent.com` at that same path -- computed automatically from `content.json`'s own slug/date, so this step and the URLs it produces are identical for every topic. Do this before deploying/drafting so the images are actually live by the time anyone opens the page or the email.

6. **Render the web variant:**
   ```
   python tools/render_newsletter.py --content ISSUE_DIR/content.json --brand tools/brand.json \
     --variant web --base-url . --out ISSUE_DIR/web.html
   ```
   `--base-url .` here just means "no CTA link yet" -- photos/charts/logo already resolve to their GitHub raw URLs regardless.

7. **Deploy to Vercel.** One call, one reused project (name comes from `brand.json`'s `vercel_project_name` -- don't invent a new project per issue):
   `mcp__claude_ai_Vercel__deploy_to_vercel` with `target: "preview"`, files = `ISSUE_DIR/web.html` renamed to `index.html` **only** -- no images to upload, since those are already hosted on GitHub. Capture the returned URL.

8. **Render the email variant**, now that a real deploy URL exists (must be absolute -- the script refuses a relative one). This only affects the "Read the Full Issue" CTA link; photos/charts/logo were already resolved in step 6 and don't change:
   ```
   python tools/render_newsletter.py --content ISSUE_DIR/content.json --brand tools/brand.json \
     --variant email --base-url "<deploy-url>" --out ISSUE_DIR/email.html
   ```

9. **Resolve the recipient.** Read `NEWSLETTER_DRAFT_TO` from `.env`. If unset, ask the user.

10. **Create the Gmail draft** (never send): `mcp__claude_ai_Gmail__create_draft` with `subject = content.meta.title`, `body` = plain text built from `hero.summary` + the deploy URL, `htmlBody` = the contents of `ISSUE_DIR/email.html`.

11. **Report back**: the Vercel URL and confirmation the Gmail draft was created (with its ID), explicitly noting it was **not sent**.

## Notes / things learned
- Charts always render in light mode only (a PNG can't retheme itself) and sit in a fixed light card frame -- this stays legible even when the web page itself is in dark mode.
- The email template is intentionally single-theme (light) -- email client dark-mode support is too inconsistent to build against.
- `render_newsletter.py` must be run **twice**, web before deploy and email after. Photos/charts/logo don't care about this sequencing anymore (GitHub raw URLs, always resolvable regardless of variant) -- the only thing that still needs the two-pass is the "Read the Full Issue" CTA link, which requires a real Vercel URL that doesn't exist until after deploy.
- **Photos/charts/logo are hosted on GitHub, not Vercel.** `deploy_to_vercel` only accepts inline file bytes in the tool call itself (no presigned-upload option), and transcribing a real photo's base64 into a tool call turned out to be unreliable -- on the first newsletter issue with real photos, repeated "not valid base64" failures forced shrinking images down to ~110px/heavily-compressed just to get a deploy to succeed, which produced visibly bad image quality. The fix: images/charts/logo are committed to the public `buffalo-forge-newsletter-public` GitHub repo (this same repo) and referenced by `raw.githubusercontent.com` URL instead -- full resolution, no size constraint, no transcription risk, since the bytes never pass through a tool call at all. `tools/publish_newsletter_assets.py` handles the copy+commit+push; `render_newsletter.py` computes the URL automatically from `content.json`'s own `meta.slug`/`meta.issue_date` plus `brand.json`'s `github_hosting` block, so this is identical for every topic with nothing hardcoded per issue. Consequently Vercel now only ever receives `index.html` -- no images, no base64, ever.
- Vercel: reuse one project across issues; don't try to build a cumulative multi-issue archive tree (would mean re-uploading every prior issue's `index.html` each run, though that's cheap now that it's text-only). Vercel's own deployment history and the Gmail drafts folder already double as a browsable archive. A real cross-issue index page is an explicit non-goal for now.
- `tools/brand.json` holds Buffalo Forge & Foundry's real colors/fonts/logo/buttons (derived from the reference sheets in `branding/`). The categorical chart palette is capped at 3 hues (Forge Orange/Molten Copper/Fire Gold) -- the brand's warm hue range doesn't support more without failing the dataviz skill's CVD validator; `generate_chart.py` cycles them with direct value labels as the prescribed relief for >3 categories.
- The "Read the Full Issue" CTA button only renders when a real `web_url` is known (i.e. whenever `--base-url` isn't `.`) -- in practice that's the email variant, since the web variant is always rendered *before* the Vercel URL exists. This is automatic; no special-casing needed per variant.
- `.tmp/newsletter/<slug>-<date>/` itself is disposable (source images/charts, intermediate HTML) -- but once `publish_newsletter_assets.py` has run, the *copies* it made under `newsletter-assets/<slug>-<date>/` are durable and tracked in git, alongside the Vercel deployment and the Gmail draft. Re-running the publish step is safe (it only stages/commits when the copied bytes actually differ) but don't manually delete `newsletter-assets/` entries for past issues -- their raw URLs are baked into already-sent/already-drafted HTML.
- The first newsletter issue (`rebar-to-knife-2026-07-09`) predates this GitHub-hosting convention and was hand-committed to `linkedin-stills/rebar-to-knife-2026-07-09/` instead of `newsletter-assets/rebar-to-knife-2026-07-09/`, with its rendered HTML's `<img src>` values hand-edited to match. That issue's files are a historical exception -- leave them where they are (its live page and Gmail draft already point at those exact URLs); every issue from here on uses `newsletter-assets/` automatically via `publish_newsletter_assets.py`.
