# Decisions

- The published site is a static Cloudflare Pages site generated from the latest local HTML reports.
- A public report is identified by hero name plus match ID. Generation timestamps are provenance metadata, not part of the canonical URL; previously published timestamped URLs are retained as permanent redirects.
- The deployment target is Cloudflare Pages project `cstd-help`; the requested production domain is `dota.custard.top`.
- The report engine remains data-driven. Deployment work must not add hero-specific analysis branches.
- CI validates tests, Python compilation, and required report sections before deploying.
