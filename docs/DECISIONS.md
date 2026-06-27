# Decisions

- The published site is a static Cloudflare Pages site generated from the latest local HTML reports.
- The deployment target is Cloudflare Pages project `cstd-help`; the requested production domain is `dota.custard.top`.
- The report engine remains data-driven. Deployment work must not add hero-specific analysis branches.
- CI validates tests, Python compilation, and required report sections before deploying.
