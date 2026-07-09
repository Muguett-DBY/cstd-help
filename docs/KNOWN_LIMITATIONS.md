# Known Limitations

- GitHub Actions deployment requires Cloudflare secrets in the repository.
- The committed static site reflects the reports present when `scripts/build_pages_site.py` is run.
- New match data still depends on the local OpenDota/STRATZ fetch pipeline and available public data fields. The public build rejects any report with a missing evidence class. Source-bounded partial coverage is allowed only when the report-level counts are explicit and the affected coaching text is capped below 100/100.
- The current public build has 7/8 tracked evidence-field classes complete and 1/8 partial: Rubick `8867351572` has 7/7 real death times but only 4/7 source-backed death coordinates. Those three unlocated deaths are not assigned map coordinates or used as location evidence; their report cards still show source-backed time, objective, resource, and item context so the review remains actionable without inventing locations.
- When STRATZ is unavailable, complete lineups and match timing come from OpenDota; exact numbered position is left unspecified unless a source provides it directly.
- OpenDota teamfight death coordinates are attached only when one teamfight window contains exactly one player death coordinate and exactly one matching Valve death. Ambiguous multi-death/multi-coordinate windows remain unassigned rather than inferred.
