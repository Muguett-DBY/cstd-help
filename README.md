# Dota 2 Review Reports

Evidence-driven Dota 2 match review reports for player `173776719`.

Live site: [dota.custard.top](https://dota.custard.top)

The history page is generated from report-embedded OpenDota metadata and shows the real match end time, result, duration, KDA, score, and both five-hero lineups. Each row opens the evidence-based review for that match.

Published report URLs are stable per match (`Hero_Name_<match_id>.html`). Report generation time is stored inside the report metadata, and `public/_redirects` preserves the timestamped URLs that were live before the stable-URL migration.

## Static Site

The Cloudflare Pages output is committed under `public/`.

Refresh it locally after regenerating reports:

```powershell
python scripts/build_pages_site.py
python scripts/check_public_site.py
```

To inspect current ranked matches without changing the site or requesting an OpenDota parse:

```powershell
python scripts/refresh_public_reports.py --dry-run --no-stratz --no-d2pt
```

`refresh_public_reports.py` publishes only unseen ranked matches whose deterministic analysis contains a real minute timeline and evidence/action/check fields for every coaching finding. Unparsed matches are requested from OpenDota in one batch and deferred when minute evidence is still unavailable. Existing canonical reports and their source timestamps are preserved during every rebuild.

## Verification

```powershell
python -m unittest discover -s tests -p "test*.py"
python -m compileall -q .
python scripts/check_public_site.py
```

## Deployment

Pushes to `main` run `.github/workflows/deploy-pages.yml`, validate the analyzer and static reports, then deploy `public/` to Cloudflare Pages project `cstd-help`.

`.github/workflows/refresh-reports.yml` also runs hourly and can be dispatched manually. It fetches new ranked matches, validates the rebuilt site, commits only changed files under `public/`, and deploys that exact commit to Cloudflare Pages in the same run. Free-form AI is disabled by default, so scheduled reports use the deterministic evidence-based coach output.

GitHub repository secrets required for CI deployment:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`

Recommended refresh secret:

- `STRATZ_API_KEY` for STRATZ role/playback evidence. If STRATZ is unavailable, OpenDota parsed minute evidence remains the minimum publication gate and the report states the missing fields.
