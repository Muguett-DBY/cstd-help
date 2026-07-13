# Pure Data Dota Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every model-dependent review path with a complete, source-backed, deterministic formula engine for player 173776719.

**Architecture:** OpenDota and STRATZ remain the only match evidence providers. `analysis.analyzer` normalizes all available evidence and a dedicated formula module scores and ranks findings; the Worker only orchestrates evidence jobs, cache, and deterministic review generation.

**Tech Stack:** Python 3.13, Cloudflare Python Workers/KV, vanilla HTML/CSS/JavaScript, unittest, GitHub Actions, Cloudflare Pages.

## Global Constraints

- Do not modify Docker files or runtime.
- Do not modify or create `AGENTS.md`.
- Do not call any language model or retain model bindings, prompts, configuration, UI copy, or cache status fields.
- Use only observed OpenDota/STRATZ values; never estimate missing values.
- Keep latest-ten refresh manual and full evidence fetch on demand.
- Work on `main`, never force push, and stage explicit files only.

---

### Task 1: Lock The Pure Data Contract

**Files:**
- Create: `tests/test_formula_engine.py`
- Modify: `tests/test_worker_router.py`
- Modify: `tests/test_report_quality.py`

- [x] Add failing tests for deterministic scorecards, missing inputs, field ledger coverage, and repository runtime files without model bindings.
- [x] Run the focused tests and confirm they fail for the missing formula/data contract.

### Task 2: Normalize Complete Evidence

**Files:**
- Modify: `api/normalization.py`
- Modify: `analysis/analyzer.py`
- Modify: `analysis/evidence_contract.py`
- Modify: `api/stratz.py`

- [x] Expose participant metrics, XP timeline, extended metrics, source-presence flags, and role-aware field ledger.
- [x] Bump the evidence schema and make publishability depend on required ledger gaps.
- [x] Run analyzer and evidence tests until green.

### Task 3: Implement Deterministic Formulas

**Files:**
- Create: `analysis/formula_engine.py`
- Delete: `analysis/ai_analyst.py`
- Modify: `analysis/analyzer.py`
- Modify: `main.py`
- Modify: `report/generator.py`
- Modify: `report/template.html`

- [x] Build transparent scorecards and stable issue ranking from observed fields.
- [x] Reuse the deterministic review for Worker and offline reports.
- [x] Run formula and report tests until green.

### Task 4: Remove Model Runtime And Migrate Cache

**Files:**
- Modify: `worker/service.py`
- Modify: `worker/cloudflare_adapters.py`
- Modify: `worker_entry.py`
- Modify: `wrangler.toml`
- Modify: `config.py`
- Modify: `scripts/build_worker_bundle.py`
- Modify: Worker tests

- [x] Remove model gateway/parser/config/binding/status fields.
- [x] Bump review schema and return deterministic analysis metadata.
- [x] Run Worker tests and bundle checks until green.

### Task 5: Rebuild The Review UI

**Files:**
- Modify: `web/match.html`
- Modify: `web/static/match.js`
- Modify: `web/static/workbench.css`
- Regenerate: `public/**`

- [x] Show expanded facts, formula scorecards, equations, inputs, thresholds, findings, and role-aware field ledger.
- [x] Remove all model-related copy and states.
- [x] Build Pages output and run UI/static tests.

### Task 6: Release Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/ANALYSIS_ENGINE.md`
- Modify or remove superseded architecture documents containing current model guidance.

- [x] Run the complete unit suite, compile check, secret scan, Worker bundle build, Pages build, and real latest-ten evidence audit.
- [x] Inspect desktop and mobile pages in a real browser with console/network checks.
- [ ] Commit explicit files, push `main`, verify GitHub Actions and `https://dota.custard.top`.
