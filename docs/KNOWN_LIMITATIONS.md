# Known Limitations

- GitHub Actions deployment requires Cloudflare secrets in the repository.
- The committed static site reflects the reports present when `scripts/build_pages_site.py` is run.
- New match data still depends on the local OpenDota/STRATZ fetch pipeline and available public data fields. The public site now publishes `evidence_field_audit` in `site-manifest.json` and shows the same field coverage in the history/practice pages, so missing cached fields are visible and are not used for coaching attribution.
- When STRATZ is unavailable, complete lineups and match timing come from OpenDota; exact numbered position is left unspecified unless a source provides it directly.
