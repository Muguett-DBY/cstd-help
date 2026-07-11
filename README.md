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

## Verification

```powershell
python -m unittest discover -s tests -p "test*.py"
python -m compileall -q .
python scripts/check_public_site.py
```

## Deployment

Pushes to `main` run `.github/workflows/deploy-pages.yml`, validate the analyzer and static reports, then deploy `public/` to Cloudflare Pages project `cstd-help`.

GitHub repository secrets required for CI deployment:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
