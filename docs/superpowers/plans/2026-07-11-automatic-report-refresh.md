# Automatic Report Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically append evidence-ready ranked matches to the public review site and deploy them through the existing GitHub-to-Cloudflare pipeline.

**Architecture:** A focused refresh orchestrator compares OpenDota ranked history with embedded public report metadata, batches parse requests, analyzes only evidence-ready matches, merges new reports with existing canonical reports, and rebuilds `public/`. Report metadata persists source fetch timestamps so ephemeral CI runs preserve provenance.

**Tech Stack:** Python 3.12, requests, Jinja2, BeautifulSoup, unittest, GitHub Actions, Cloudflare Pages.

## Global Constraints

- Work only on `main`; use normal fast-forward pushes and never force push or rebase.
- Stage exact scoped paths; never use `git add .`.
- Do not modify Docker files or `AGENTS.md`.
- Never commit API keys, SQLite files, raw API payloads, or generated local caches.
- Publish no new match without real minute-level evidence.

---

### Task 1: Portable Secrets And Report Provenance

**Files:**
- Modify: `config.py`
- Modify: `report/generator.py`
- Modify: `scripts/build_pages_site.py`
- Test: `tests/test_report_quality.py`
- Test: `tests/test_build_pages_site.py`

**Interfaces:**
- Consumes: `STRATZ_API_KEY`, `DOTA_REVIEW_REPORT_DIR`, and `DOTA_REVIEW_DB_PATH` environment variables.
- Produces: `generate_report(..., output_dir=None, source_fetches=None)` and parsed `report["source_fetches"]` metadata.

- [ ] Write tests proving environment secrets take precedence, a custom report directory is honored, source timestamps enter report metadata, and a Pages rebuild recovers existing provenance.
- [ ] Run the focused tests and confirm they fail for the missing behavior.
- [ ] Implement environment-backed configuration, optional generator arguments, source timestamp parsing, and embedded/SQLite timestamp merging.
- [ ] Run the focused tests and confirm they pass.

### Task 2: Evidence-Gated Incremental Refresh

**Files:**
- Create: `scripts/refresh_public_reports.py`
- Modify: `api/opendota.py`
- Test: `tests/test_refresh_public_reports.py`

**Interfaces:**
- Consumes: `OpenDotaClient`, `StratzClient`, `analyze_match`, `analyze_with_ai`, `generate_report`, and `build_pages_site`.
- Produces: `refresh_public_reports(public_dir, recent_limit, max_new, parse_wait, ...) -> RefreshResult` and a CLI exit status of zero for successful no-change/deferred runs.

- [ ] Write tests for ranked filtering, unseen-match detection, batched parse retry, timeline readiness gating, existing-report preservation, and deterministic no-change behavior.
- [ ] Run the focused tests and confirm they fail because the orchestrator and readiness helpers do not exist.
- [ ] Implement the smallest orchestrator and OpenDota readiness helper that satisfy the tests.
- [ ] Run the focused tests and confirm they pass.
- [ ] Run one local dry run against current OpenDota data without writing `public/` and inspect discovered/deferred counts.

### Task 3: Scheduled Main-Branch Publication

**Files:**
- Create: `.github/workflows/refresh-reports.yml`
- Modify: `README.md`
- Modify: `tests/test_build_pages_site.py`

**Interfaces:**
- Consumes: GitHub secrets `STRATZ_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, and `CLOUDFLARE_API_TOKEN`, plus the refresh CLI.
- Produces: an hourly/manual workflow that stages only `public/`, commits only on change, and directly deploys the exact refresh commit because `GITHUB_TOKEN` pushes do not trigger a second workflow.

- [ ] Write a workflow contract test for schedule/manual triggers, `contents: write`, secret wiring, quality gates, scoped staging, and normal `main` push.
- [ ] Run the contract test and confirm it fails while the workflow is absent.
- [ ] Add the workflow and document refresh behavior, evidence gate, and secret requirements.
- [ ] Run the workflow contract test and confirm it passes.

### Task 4: Full Verification And Production Bootstrap

**Files:**
- Modify generated `public/` files only through the refresh/build scripts.
- Append: `.agent/iteration-log.md`

**Interfaces:**
- Consumes: all tasks above and the repository's existing deployment credentials.
- Produces: current ranked reports live at `https://dota.custard.top`.

- [ ] Run the full unittest suite, compileall, static-site validator, gitleaks, diff check, and forbidden-file check.
- [ ] Commit and push the implementation to `main` with exact-path staging.
- [ ] Configure `STRATZ_API_KEY` as a GitHub repository secret without printing it.
- [ ] Manually dispatch the refresh workflow and watch it through completion.
- [ ] Watch the triggered deploy workflow through completion.
- [ ] Verify the live manifest's latest match, history count, canonical route, required report sections, mobile overflow, and source/data limitations.
- [ ] Record exact commits, run IDs, test counts, and live evidence in the iteration log; commit, push, and verify the documentation deployment.
