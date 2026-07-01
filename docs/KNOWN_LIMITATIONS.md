# Known Limitations

- GitHub Actions deployment requires Cloudflare secrets in the repository.
- The committed static site reflects the reports present when `scripts/build_pages_site.py` is run.
- New match data still depends on the local OpenDota/STRATZ fetch pipeline and available public data fields. The public build now requires all 8 tracked evidence-field classes to cover every cached report and rejects any report with a missing evidence class.
- When STRATZ is unavailable, complete lineups and match timing come from OpenDota; exact numbered position is left unspecified unless a source provides it directly.
- OpenDota teamfight death coordinates are attached only when one teamfight window contains exactly one player death coordinate and exactly one matching Valve death. Ambiguous multi-death/multi-coordinate windows remain unassigned rather than inferred.
