# On-Demand Personal Dota Review Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a personal Dota 2 workbench for account `173776719` that fetches exactly 10 recent ranked matches only on refresh and runs evidence-driven AI coaching only after an explicit match-level click.

**Architecture:** Cloudflare Pages serves a static two-screen workbench. A Python Worker on `/api/*` reuses the existing deterministic analyzer, stores cached lists/details/reviews in Workers KV, and calls Workers AI only after review requests. Existing static reports remain as compatibility artifacts but are removed from the primary flow.

**Tech Stack:** Python 3.13, Cloudflare Python Workers, Workers KV, Workers AI, vanilla HTML/CSS/JavaScript, Python `unittest`, Playwright CLI, GitHub Actions, Cloudflare Pages.

## Global Constraints

- The analyzed account is always `173776719`; no account selector is exposed.
- Match-list refresh is external-I/O-free on page load and external-I/O-enabled only for `POST /api/matches/refresh`.
- The primary list contains at most 10 ranked matches.
- AI and deterministic review generation run only for `POST /api/reviews/<match_id>`.
- AI may organize supplied evidence but may not invent findings or unsupported categories.
- No API key or token may enter source, generated HTML, test fixtures, logs, or screenshots.
- Do not create or modify `AGENTS.md`.
- Do not modify Docker files, Docker configuration, Docker paths, or Docker runtime state.
- Work directly on `main`; do not create a branch, rebase, force-push, reset, or use `git add .`.

---

### Task 1: Shared OpenDota Normalization

**Files:**
- Create: `api/normalization.py`
- Modify: `api/opendota.py`
- Test: `tests/test_worker_service.py`

**Interfaces:**
- Produces: `normalize_player_match(raw_match: dict, account_id: int) -> dict | None`.
- Produces: `normalize_recent_match(raw_match: dict, account_id: int) -> dict | None`.
- Existing `OpenDotaClient.parse_match_for_player()` delegates to the shared normalizer.

- [ ] **Step 1: Write failing normalization tests**

```python
def test_recent_match_normalizer_returns_personal_summary(self):
    summary = normalize_recent_match(self.recent_match, 173776719)
    self.assertEqual(summary["match_id"], 8891116798)
    self.assertEqual(summary["hero"]["name"], "Luna")
    self.assertEqual(summary["kda"], {"kills": 13, "deaths": 4, "assists": 11})
    self.assertTrue(summary["is_win"])

def test_full_match_normalizer_rejects_missing_personal_player(self):
    self.assertIsNone(normalize_player_match({"players": []}, 173776719))
```

- [ ] **Step 2: Run the focused tests and verify missing-module failures**

Run: `python -m unittest discover -s tests -p "test_worker_service.py" -k "normalizer"`

Expected: failure because `api.normalization` does not exist.

- [ ] **Step 3: Implement pure normalizers**

The implementation must map match ID, fixed-account ownership, hero ID/name/slug, side, result, start/end timestamps, duration, KDA, rank/lane/role fields, and the flat player fields already consumed by `analyze_match()`.

- [ ] **Step 4: Delegate the existing client parser and run focused tests**

Run: `python -m unittest discover -s tests -p "test_worker_service.py" -k "normalizer"`

Expected: all normalization tests pass.

- [ ] **Step 5: Run existing report-quality tests**

Run: `python -m unittest discover -s tests -p "test_report_quality.py"`

Expected: all existing analyzer/report tests pass unchanged.

### Task 2: Cache-Only Read and Manual Match Refresh Service

**Files:**
- Create: `worker/__init__.py`
- Create: `worker/contracts.py`
- Create: `worker/service.py`
- Test: `tests/test_worker_service.py`

**Interfaces:**
- Consumes: an injected async cache with `get_json(key)` and `put_json(key, value, expiration_ttl=None)`.
- Consumes: an injected Dota gateway with `recent_ranked_matches(account_id, limit)` and `match_detail(match_id)`.
- Produces: `ReviewService.get_matches() -> dict` with no Dota gateway call.
- Produces: `ReviewService.refresh_matches(now) -> dict` with exactly one recent-list gateway call outside cooldown.
- Produces: `ReviewService.get_match_detail(match_id) -> dict` restricted to the cached list.

- [ ] **Step 1: Write failing cache/manual-refresh tests**

```python
async def test_get_matches_reads_cache_without_external_fetch(self):
    result = await self.service.get_matches()
    self.assertEqual(self.dota.recent_calls, 0)
    self.assertEqual(result["source"], "cache")

async def test_refresh_keeps_only_ten_ranked_personal_matches(self):
    result = await self.service.refresh_matches(self.now)
    self.assertEqual(len(result["matches"]), 10)
    self.assertEqual(self.dota.recent_calls, 1)

async def test_refresh_inside_cooldown_returns_cache(self):
    await self.service.refresh_matches(self.now)
    result = await self.service.refresh_matches(self.now + timedelta(seconds=30))
    self.assertTrue(result["rate_limited"])
    self.assertEqual(self.dota.recent_calls, 1)
```

- [ ] **Step 2: Verify the service tests fail for missing service**

Run: `python -m unittest discover -s tests -p "test_worker_service.py" -k "matches"`

- [ ] **Step 3: Implement cache keys, cooldown, filtering, and ownership validation**

Use `matches:v1:173776719` for the current list and `match:v1:<match_id>` for details. Return stable error codes `MATCH_NOT_IN_RECENT_LIST`, `MATCH_NOT_FOUND`, and `UPSTREAM_UNAVAILABLE` through typed `ServiceError` exceptions.

- [ ] **Step 4: Verify focused tests pass**

Run: `python -m unittest discover -s tests -p "test_worker_service.py" -k "matches"`

### Task 3: Click-Only Evidence and AI Review Service

**Files:**
- Create: `analysis/coach_contract.py`
- Modify: `analysis/ai_analyst.py`
- Modify: `worker/service.py`
- Test: `tests/test_worker_service.py`
- Test: `tests/test_report_quality.py`

**Interfaces:**
- Produces: `build_coach_payload(analysis: dict, hero_name: str, is_win: bool) -> dict`.
- Produces: `validate_coach_payload(payload: dict, findings: list[dict]) -> dict`.
- Consumes: an injected AI gateway with `generate(evidence_package) -> dict`.
- Produces: `ReviewService.review_status(match_id) -> dict` without deterministic analysis or AI.
- Produces: `ReviewService.generate_review(match_id, now) -> dict` with deterministic analysis before one AI call on cache miss.

- [ ] **Step 1: Write failing review orchestration tests**

```python
async def test_status_does_not_run_analysis_or_ai(self):
    await self.service.review_status(8891116798)
    self.assertEqual(self.ai.calls, 0)
    self.assertEqual(self.analyzer.calls, 0)

async def test_review_runs_only_after_explicit_generation(self):
    result = await self.service.generate_review(8891116798, self.now)
    self.assertEqual(self.analyzer.calls, 1)
    self.assertEqual(self.ai.calls, 1)
    self.assertFalse(result["cached"])

async def test_cached_review_does_not_repeat_ai(self):
    await self.service.generate_review(8891116798, self.now)
    result = await self.service.generate_review(8891116798, self.now)
    self.assertTrue(result["cached"])
    self.assertEqual(self.ai.calls, 1)
```

- [ ] **Step 2: Write failing AI evidence-boundary tests**

```python
def test_coach_payload_rejects_categories_absent_from_findings(self):
    with self.assertRaises(CoachValidationError):
        validate_coach_payload(
            {"review_points": [{"category": "invented_positioning"}]},
            [{"category": "resource_continuity", "evidence": "32-34分钟"}],
        )
```

- [ ] **Step 3: Verify review tests fail**

Run: `python -m unittest discover -s tests -p "test_worker_service.py" -k "review"`

Run: `python -m unittest discover -s tests -p "test_report_quality.py" -k "coach_payload"`

- [ ] **Step 4: Implement schema-versioned review caching and deterministic fallback**

Use cache key `review:<ANALYSIS_SCHEMA_VERSION>:<match_id>`. The returned `coach` object must always contain `conclusion`, `review_points`, `next_actions`, and `data_limits`. AI validation rejects unknown categories, missing evidence/action fields, forbidden inference language, and action metrics that do not improve on current evidence.

- [ ] **Step 5: Verify focused tests pass**

Run both focused commands from Step 3 and expect zero failures.

### Task 4: Cloudflare Python Worker Adapter

**Files:**
- Create: `worker_entry.py`
- Create: `worker/cloudflare_adapters.py`
- Create: `wrangler.api.toml`
- Create: `pyproject.toml`
- Test: `tests/test_worker_router.py`

**Interfaces:**
- Produces HTTP routes:
  - `GET /api/health`
  - `GET /api/matches`
  - `POST /api/matches/refresh`
  - `GET /api/matches/<match_id>`
  - `GET /api/reviews/<match_id>/status`
  - `POST /api/reviews/<match_id>`
- Cloudflare adapters expose the cache, OpenDota/STRATZ fetch, and Workers AI interfaces required by `ReviewService`.

- [ ] **Step 1: Write failing router tests**

```python
async def test_get_matches_routes_to_cache_only_service(self):
    response = await route_request(FakeRequest("GET", "/api/matches"), self.service)
    self.assertEqual(response.status, 200)
    self.assertEqual(self.service.called, "get_matches")

async def test_review_requires_post(self):
    response = await route_request(FakeRequest("GET", "/api/reviews/8891116798"), self.service)
    self.assertEqual(response.status, 405)
```

- [ ] **Step 2: Implement a runtime-neutral router and Cloudflare entrypoint**

`worker_entry.py` imports `WorkerEntrypoint`, builds adapters from `self.env`, and converts router responses with `Response.json`. `worker/contracts.py` remains importable under normal CPython tests without the Workers SDK.

- [ ] **Step 3: Add deployment bindings**

`wrangler.api.toml` declares:

```toml
name = "cstd-help-api"
main = "worker_entry.py"
compatibility_date = "2026-07-12"
compatibility_flags = ["python_workers"]

[vars]
ACCOUNT_ID = "173776719"
AI_MODEL = "@cf/openai/gpt-oss-120b"

[ai]
binding = "AI"

[[kv_namespaces]]
binding = "REVIEW_CACHE"

[[routes]]
pattern = "dota.custard.top/api/*"
zone_name = "custard.top"
```

- [ ] **Step 4: Verify router and pure service tests**

Run: `python -m unittest discover -s tests -p "test_worker*.py"`

- [ ] **Step 5: Run Python Worker local validation**

Run: `uvx --from workers-py pywrangler dev --config wrangler.api.toml`

Probe: `Invoke-WebRequest http://127.0.0.1:8787/api/health`

Expected: HTTP 200 with fixed account ID and binding availability, without exposing secret values.

### Task 5: Workbench Static Build and Seed Data

**Files:**
- Create: `web/index.html`
- Create: `web/match.html`
- Create: `web/static/workbench.css`
- Create: `web/static/shared.js`
- Create: `web/static/history.js`
- Create: `web/static/match.js`
- Create: `scripts/build_workbench_site.py`
- Modify: `scripts/refresh_public_reports.py`
- Test: `tests/test_workbench_site.py`

**Interfaces:**
- Produces `public/index.html`, `public/match.html`, `public/static/workbench.css`, JavaScript modules, and `public/matches.json`.
- `public/matches.json` contains the latest 10 report-derived summaries as a no-network seed.

- [ ] **Step 1: Write failing static build tests**

```python
def test_build_outputs_exactly_ten_seed_matches(self):
    build_workbench_site(self.public_dir, self.web_dir)
    payload = json.loads((self.public_dir / "matches.json").read_text("utf-8"))
    self.assertEqual(len(payload["matches"]), 10)

def test_home_contains_manual_refresh_and_no_autorefresh(self):
    html = (self.public_dir / "index.html").read_text("utf-8")
    self.assertIn('data-refresh-matches', html)
    self.assertNotIn('setInterval(', html)

def test_match_shell_contains_click_only_analysis_control(self):
    html = (self.public_dir / "match.html").read_text("utf-8")
    self.assertIn('data-generate-review', html)
    self.assertIn('data-review-output', html)
```

- [ ] **Step 2: Verify build tests fail**

Run: `python -m unittest discover -s tests -p "test_workbench_site.py"`

- [ ] **Step 3: Implement seed builder and templates**

The builder parses canonical report metadata, sorts by actual `ended_at`, limits to 10, writes normalized JSON, and copies source-controlled workbench assets. It never fetches an external URL.

- [ ] **Step 4: Integrate maintenance refresh**

After legacy reports rebuild, `refresh_public_reports.py` runs `build_workbench_site()` so a manual maintenance workflow cannot restore the old archive homepage.

- [ ] **Step 5: Verify static build tests pass**

Run: `python -m unittest discover -s tests -p "test_workbench_site.py"`

### Task 6: Latest-10 Frontend Interaction

**Files:**
- Modify: `web/index.html`
- Modify: `web/static/workbench.css`
- Modify: `web/static/shared.js`
- Modify: `web/static/history.js`
- Test: `tests/test_workbench_site.py`

**Interfaces:**
- `loadCachedMatches()` performs `GET /api/matches` and falls back to `matches.json`.
- `refreshMatches()` performs `POST /api/matches/refresh` only from the refresh button handler.
- `renderMatchList(matches)` renders no more than 10 rows.

- [ ] **Step 1: Add failing source-contract tests**

Verify the refresh endpoint string exists only inside the refresh handler, the initial loader uses GET cache/seed paths, the list slices to 10, and every row links to `/match.html?id=<id>`.

- [ ] **Step 2: Implement the workbench states**

Build idle, empty, loading, success, rate-limited, stale-cache, and error states. Use real hero portraits, compact summary metrics, stable row tracks, text plus Lucide icons for commands, and local-time formatting.

- [ ] **Step 3: Implement responsive and accessible behavior**

Desktop uses a dense list. Mobile uses one un-nested card per match. Preserve semantic headings, visible focus, `aria-live` refresh status, disabled loading controls, 44px primary targets, and zero page-level overflow at 390px.

- [ ] **Step 4: Build and run static tests**

Run: `python scripts/build_workbench_site.py`

Run: `python -m unittest discover -s tests -p "test_workbench_site.py"`

### Task 7: Match Detail and Click-Only Review Interaction

**Files:**
- Modify: `web/match.html`
- Modify: `web/static/workbench.css`
- Modify: `web/static/shared.js`
- Modify: `web/static/match.js`
- Test: `tests/test_workbench_site.py`

**Interfaces:**
- Page load invokes only match detail and review status GET endpoints.
- `generateReview()` invokes `POST /api/reviews/<id>` only from the analysis button.
- Document title and H1 begin with the played hero name after detail loads.

- [ ] **Step 1: Add failing click-only source-contract tests**

Assert no review POST occurs in top-level module initialization, the button owns the generation handler, cached status changes the button label, and hero-first title/H1 setters exist.

- [ ] **Step 2: Implement factual pre-analysis view**

Render result, match ID, end time, duration, lane/role/rank, KDA, GPM, XPM, last hits, damage, two five-hero lineups, and final items before any AI response.

- [ ] **Step 3: Implement analysis progress and report sections**

Render conclusion, 3-5 next actions, timeline, events, evidence findings, and collapsed data limitations. Errors retain factual match detail and offer a retry button; AI fallback remains usable.

- [ ] **Step 4: Rebuild and verify static contracts**

Run: `python scripts/build_workbench_site.py`

Run: `python -m unittest discover -s tests -p "test_workbench_site.py"`

### Task 8: CI, Deployment, and Schedule Removal

**Files:**
- Modify: `.github/workflows/deploy-pages.yml`
- Modify: `.github/workflows/refresh-reports.yml`
- Modify: `README.md`
- Modify: `scripts/check_public_site.py`
- Modify: `tests/test_build_pages_site.py`
- Test: `tests/test_workbench_site.py`

**Interfaces:**
- Main deploy validates Python, builds the workbench, deploys `cstd-help-api`, then deploys Pages.
- Refresh workflow has `workflow_dispatch` only and no `schedule` trigger.

- [ ] **Step 1: Write failing workflow tests**

```python
def test_refresh_workflow_is_manual_only(self):
    workflow = REFRESH_WORKFLOW.read_text("utf-8")
    self.assertIn("workflow_dispatch:", workflow)
    self.assertNotIn("schedule:", workflow)

def test_deploy_workflow_deploys_api_before_pages(self):
    workflow = DEPLOY_WORKFLOW.read_text("utf-8")
    self.assertLess(workflow.index("pywrangler deploy"), workflow.index("pages deploy public"))
```

- [ ] **Step 2: Update static checker for workbench invariants**

Require the latest-10 seed, manual refresh control, match shell, click-only analysis control, static assets, canonical legacy links, and absence of old primary-page coverage dashboard markers.

- [ ] **Step 3: Provision Cloudflare resources and encrypted secret**

Deploy once with the ID-less `REVIEW_CACHE` binding so Wrangler creates the namespace and writes the returned non-secret ID into `wrangler.api.toml`; rename/confirm it as `cstd-help-review-cache`. Set `STRATZ_API_KEY` through `pywrangler secret put` using the existing local key without printing it.

- [ ] **Step 4: Update workflows and documentation**

Use Python 3.13 for Worker compatibility, install `uv`, run all tests/build/checks, deploy the API with the existing Cloudflare account credentials, then deploy Pages. Document manual refresh, click-only analysis, cache semantics, and secret names.

- [ ] **Step 5: Run workflow/static tests**

Run: `python -m unittest discover -s tests -p "test*.py"`

### Task 9: Full Verification and Live Acceptance

**Files:**
- Modify only files required by failures found in this task.
- Artifacts: ignored `output/playwright/` screenshots and traces.

- [ ] **Step 1: Run complete local gates**

Run:

```powershell
python -m unittest discover -s tests -p "test*.py"
python -m compileall -q .
python scripts/build_workbench_site.py
python scripts/check_public_site.py
gitleaks dir . --redact --no-banner
git diff --check
```

- [ ] **Step 2: Start local Worker and Pages preview without Docker**

Run the Python Worker through `pywrangler dev` and Pages through `wrangler pages dev public`. Use hidden background processes and non-conflicting ports.

- [ ] **Step 3: Browser-test the full desktop flow**

Verify initial load makes no refresh/review POST, refresh returns no more than 10 rows, a match opens factual detail with hero-first title, review status performs no AI call, analysis starts only after the button, and cached reopen performs no second model run.

- [ ] **Step 4: Browser-test mobile and failures**

At 390x844 verify no document overflow or overlap, readable hero/result/KDA rows, 44px actions, keyboard focus, stale-cache recovery, upstream failure messaging, and zero console errors.

- [ ] **Step 5: Inspect screenshots and iterate**

Compare current-state screenshots with the new desktop/mobile screenshots at matching viewports. Fix hierarchy, spacing, truncation, contrast, loading-state, and interaction problems, then repeat screenshots until no high-impact issue remains.

- [ ] **Step 6: Commit and push exact files to `main`**

Stage only files owned by each completed task, run `git diff --cached --check`, commit with scoped messages, and push `main` without force.

- [ ] **Step 7: Verify GitHub Actions and production**

Watch the API/Pages deployment run to completion. On `https://dota.custard.top`, repeat the latest-10, manual-refresh, factual-detail, click-only-analysis, cached-reopen, mobile-overflow, network, and console checks against production.
