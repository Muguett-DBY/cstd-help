# 6-Stage Orchestrator Log

Repository: `E:\DEV\cstd-help`
Branch: `main`
Started: 2026-06-28

## Long Cycle 4 - Global Preparation

- Prompt: `C:\Users\12031\Desktop\AGENT_ORCHESTRATOR_3_LEVELS_V2\03_LONG_6_STAGE_MAIN_V2.txt`.
- Required sequence: IMPROVE, IMPROVE, UIUX, IMPROVE, CHECK, IMPROVE.
- Start status: clean `main`, synchronized with `origin/main` at `32cc021`; no protected user changes to preserve.
- Project notes: `NEXT_STEPS.md` and `ROADMAP.md` are absent, so continuation is based on `.agent/iteration-log.md` and this orchestrator log.
- Current flagship direction: keep map-position advice tied to real STRATZ/OpenDota evidence until a verified Dota coordinate transform exists.
- Safety constraints: no `AGENTS.md` changes, no Docker file/process changes, no new branch, no force push, no `git add .`.
- Stage plan:
  - Stage 1 IMPROVE: show raw death-coordinate evidence in reports.
  - Stage 2 IMPROVE: add deterministic death-after resource recovery diagnostics.
  - Stage 3 UIUX: make death review faster to scan and act on.
  - Stage 4 IMPROVE: surface report/site coverage for death-position and recovery evidence.
  - Stage 5 CHECK: harden static validation so death evidence cannot silently disappear.
  - Stage 6 IMPROVE: final evidence-backed coaching increment after the previous stages.

## Long Cycle 4 - Stage 1 - IMPROVE

- Prompt: `AGENT_IMPROVE_MAIN.txt`.
- Goal: make reports show real raw death-coordinate evidence instead of leaving position samples buried in text.
- TDD:
  - Added tests for `events.death_map_points` from STRATZ `playerUpdatePositionEvents`.
  - Added generated-report test requiring `死亡坐标图`, `death-coordinate-map`, `data-minute`, raw `x/y`, and the `原始x/y坐标` note.
  - Tests failed before implementation with missing `death_map_points` and missing report section, then passed after implementation.
- Result:
  - Added deterministic `death_map_points` with minute, raw x/y, clamped SVG plot coordinates, and readable labels.
  - Rendered a `死亡坐标图` SVG scatter plot in the report death-event section.
  - Added responsive styling so the map and coordinate chips remain readable on desktop and 390px mobile.
  - Rebuilt the latest 10 public reports from cached real match data generated at `20260630_041720`.
- Real-data verification:
  - 9 of 10 regenerated reports contain death-coordinate maps; Rubick has no map because the real data has no located death point.
  - Latest Legion Commander report shows 12 plotted death points and exact labels such as `11.2分 x=94,y=168`.
- Browser verification:
  - Desktop Chrome at 1280x900: coordinate map visible, 12 points, no horizontal overflow, no console errors.
  - Mobile Chrome at 390x844: coordinate map visible, 12 chips, no horizontal overflow, screenshot reviewed.
- Local verification:
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 71 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check for `AGENTS.md`, Docker files, and docker-compose paths: passed.
- Commit: `feat: add raw death coordinate map` (`28ebbd8`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28393634468`.
- Live check: `https://dota.custard.top/Legion_Commander_8870219537_20260630_041720.html` returned 200 and contains `死亡坐标图`, `death-coordinate-map`, `原始x/y坐标`, and 12 plotted points.
- Remaining risk: the plot uses raw STRATZ coordinates only; it still avoids named map-region advice until a verified Dota coordinate transform is implemented.
- Next direction: add deterministic death-after resource recovery diagnostics so the report shows what happened in the minutes immediately after each death.

## Long Cycle 4 - Stage 2 - IMPROVE

- Prompt: `AGENT_IMPROVE_MAIN.txt`.
- Goal: quantify what happens in the 3 minutes after each located death using real minute-level LH/GPM data.
- TDD:
  - Added tests for `timeline.death_recovery_windows` from death events plus STRATZ minute arrays.
  - Added generated-report test requiring `死亡后恢复窗口`, the exact death-after minute range, LH gain, average GPM, and recovery status.
  - Tests failed before implementation with missing `death_recovery_windows` and missing report section, then passed after implementation.
- Result:
  - Added deterministic death-after recovery windows with death minute, observed range, LH gain, average GPM, and status label.
  - Added `死亡后恢复` findings when recovery is genuinely low, with concrete next-game action and acceptance metric.
  - Rendered `死亡后恢复窗口` in the report 时间线诊断 section.
  - Corrected the first implementation after real-report review: low LH alone no longer marks a window as `恢复不足` when GPM is already strong; both LH and GPM must be low when both are available.
  - Rebuilt the latest 10 public reports from cached real match data generated at `20260630_042955/042956`.
- Real-data verification:
  - Every regenerated report now shows death-after recovery windows.
  - Latest Legion Commander report shows 8 recovery windows; examples include `11.2分死亡后11-14分钟：25补，平均GPM 504.3，已恢复资源` and later partial/strong recovery rows.
  - After threshold correction, the previous false positives on high-GPM core windows disappeared from core findings.
- Browser verification:
  - Desktop Chrome at 1280x900: recovery section present, 8 rows, death coordinate map still present, no horizontal page overflow, no console errors.
  - Mobile Chrome at 390x844: recovery rows readable and no horizontal page overflow; existing timeline table is still too wide for comfortable mobile scanning.
- Local verification:
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 73 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check for `AGENTS.md`, Docker files, and docker-compose paths: passed.
- Commit: `feat: add death recovery diagnostics` (`8391fa8`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28405999617`.
- Live check: `https://dota.custard.top/Legion_Commander_8870219537_20260630_042955.html` returned 200 and contains `死亡后恢复窗口`, `已恢复资源`, `death-coordinate-map`, and 8 death-after recovery rows.
- Next direction: Stage 3 UIUX should fix mobile timeline scanning, especially the wide phase table, and make death review sections faster to consume.

## Long Cycle 4 - Stage 3 - UIUX

- Prompt: `AGENT_UIUX_MAIN.txt`.
- Goal: make the new timeline/death evidence readable and fast to scan on mobile, without removing the dense desktop table.
- UI/UX audit findings:
  - P1: mobile 时间线诊断 used the desktop phase table, making the right-side metrics awkward to inspect.
  - P2: death events had detailed evidence but no immediate count summary, so the player had to scan the full death list before understanding coverage.
- TDD:
  - Added generated-report test requiring `timeline-phase-cards`, `death-review-workbench`, `death-review-summary`, and summary labels for located deaths, recovery windows, and coordinate points.
  - Added stylesheet test requiring mobile timeline/death-review classes and mobile phase-table rules.
  - Tests failed before implementation, then passed after the template/CSS changes.
- Result:
  - Kept the desktop `timeline-phase-table` for dense scanning.
  - Added mobile-first `timeline-phase-cards` with stage, LH/min,正补,平均GPM,英雄伤害,推塔伤害.
  - Added a `death-review-workbench` summary row showing `已定位死亡`, `恢复窗口`, and `坐标点` before the detailed death list.
  - Rebuilt the latest 10 public reports from cached real match data generated at `20260630_081552/081553`.
- Browser verification:
  - Desktop Chrome at 1280x900: phase table visible, phase cards hidden, no horizontal overflow, no console errors.
  - Mobile Chrome at 390x844: phase table hidden, 4 phase cards visible, no horizontal overflow, no console errors.
  - Mobile death section: death workbench visible with values `12 / 12 / 12` for latest Legion Commander, readable width 336px.
- Local verification:
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 75 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check for `AGENTS.md`, Docker files, and docker-compose paths: passed.
- Commit: `feat: improve mobile death review UI` (`e238bca`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28406427112`.
- Live check: `https://dota.custard.top/Legion_Commander_8870219537_20260630_081552.html` returned 200 and contains `timeline-phase-cards`, `death-review-workbench`, `death-review-summary`, `death-coordinate-map`, and `死亡后恢复窗口`.
- Next direction: Stage 4 should surface report/site evidence coverage for the new death recovery and death UI evidence so history pages show which reports have complete death-review data.

## Long Cycle 4 - Stage 4 - IMPROVE

- Prompt: `AGENT_IMPROVE_MAIN.txt`.
- Goal: surface death-review evidence coverage at the site level, not only inside individual reports.
- TDD:
  - Extended the site-manifest/coverage-panel test to require death review workbench count, death recovery window count, death coordinate map count, and complete death review count.
  - Added stylesheet coverage for the new coverage subtitle.
  - Coverage test failed before implementation with missing manifest keys, then passed after implementation.
- Result:
  - `_parse_report` now records `death_evidence` flags for `death-review-workbench`, `死亡后恢复窗口`, and `death-coordinate-map`.
  - `site-manifest.json` now includes `death_review_workbench_report_count`, `death_recovery_window_report_count`, `death_coordinate_map_report_count`, and `complete_death_review_report_count`.
  - The shared coverage panel now includes a `死亡复盘覆盖` subsection.
  - Rebuilt the latest 10 public reports from cached real match data generated at `20260630_081552/081553`.
- Real-data verification:
  - Latest rebuilt site manifest: 10 reports, 10 death-review panels, 10 recovery-window reports, 9 coordinate-map reports, 9 complete death-review reports.
  - The single non-complete case is a real data limitation: Rubick has no death coordinate map in the cached source.
- Browser verification:
  - Desktop Chrome at 1280x900: coverage panel shows 8 coverage stats including death coverage; no horizontal overflow.
  - Mobile Chrome at 390x844: coverage panel remains readable in two columns; no horizontal overflow.
- Local verification:
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 75 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check for `AGENTS.md`, Docker files, and docker-compose paths: passed.
- Commit: `feat: surface death review coverage` (`eeb8502`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28406928707`.
- Live check: after cache-busting poll, `https://dota.custard.top/index.html` contains `死亡复盘覆盖`; `site-manifest.json` contains death coverage fields with values 10/10/9/9.
- Next direction: Stage 5 CHECK should make the static validator reject reports/sites where death-review UI, recovery windows, or coverage manifest fields silently disappear.

## Cycle 2 - Global Preparation

- Status: clean `main`, fast-forward synced with `origin/main` at `a211d36`.
- Previous flagship direction: normalize semantically equivalent finding names so recurring trends and the practice plan do not fragment.
- Additional root-cause finding: the site parser only consumed the first finding card from each report, so most evidence-backed findings were excluded from cross-match trends.
- Prompt files re-read from `C:\Users\12031\Desktop\AGENT_PROMPTS_MAIN_PACK`.
- CI workflow and latest successful run checked: `Deploy Cloudflare Pages`, run `28305478428`.

## Cycle 2 - Stage 1 - IMPROVE

- Prompt: `AGENT_IMPROVE_MAIN.txt`
- Goal: rebuild recurring-trend aggregation around all report findings and a deterministic semantic taxonomy.
- Start status: clean, synchronized `main`; no user changes to protect.
- Plan:
  - Add failing tests for multi-finding extraction, semantic grouping, per-match deduplication, and trend provenance.
  - Preserve the first finding for match-row prioritization while using every finding for trends.
  - Expose canonical topic ids and original labels in JSON/UI so grouping remains auditable.
  - Rebuild the public site, run CI-equivalent checks, review diff/security, push, and watch Actions.
- Result:
  - Parsed all structured finding cards from every report while preserving the first finding for per-match priority display.
  - Added taxonomy v1 with explicit aliases, canonical topic ids, per-match deduplication, finding counts, and original-label provenance.
  - Upgraded `review-trends.json` to schema v2 and tightened static validation around aggregation consistency.
  - Rebuilt the current dataset from 10 first findings to all 30 findings across 6 topics.
  - Fixed generated HTML trailing whitespace found by `git diff --check` and added a regression test.
- Browser verification:
  - History page at 1280px: 10 reports, four top trend cards, no horizontal overflow, no console warnings/errors.
  - Practice plan: five cards; `死亡成本` and `装备后转化` each correctly show 10 matches / 10 evidence items.
- Local verification: 42 tests passed; compile, static validation, diff check, and gitleaks passed.
- Commit: `feat: aggregate complete coaching evidence` (`94b38cd`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28306075918`.
- Next direction: add topic drill-down pages so every aggregated trend exposes all supporting matches, evidence, actions, and acceptance metrics instead of only three examples.

## Cycle 2 - Stage 2 - IMPROVE

- Prompt: `AGENT_IMPROVE_MAIN.txt`
- Goal: turn canonical trend summaries into complete evidence drill-down pages.
- Start status: clean `main`; Stage 1 deployment passed (`203a97f`, CI `28306103066`).
- Previous-stage direction: expose every supporting match and finding behind each aggregated topic.
- Plan:
  - Add failing tests for complete per-topic evidence payloads and generated topic pages.
  - Generate one stable topic page per taxonomy id with match/result, source label, evidence, action, metric, and report link.
  - Link trend cards and practice-plan cards to the topic dossier.
  - Validate topic page count and backlinks in the static production gate.
  - Run browser, local, security, diff, push, and CI verification as an independent stage.
- Result:
  - Added `trend-*.html` topic evidence pages for all 6 canonical topics.
  - Embedded every source finding behind each trend in `review-trends.json` with `page`, `findings`, source label, evidence, action, metric, match id, hero, and report link.
  - Linked dashboard trend cards and practice-plan cards to the evidence dossiers.
  - Added a practice-plan overflow topic nav so low-frequency topics remain reachable without weakening the top-5 training queue.
  - Fixed optional practice-plan HTML generation so empty optional blocks do not produce trailing whitespace.
- Browser verification:
  - History page: 6 topic links, no horizontal overflow, no console warnings/errors.
  - Clicked `死亡成本` from the trend grid and verified `trend-death-cost.html`.
  - Topic page: 10 evidence cards, 10 report links, evidence/action/metric text present, no framework overlay, no horizontal overflow, no console warnings/errors.
- Local verification:
  - `python -m unittest tests.test_build_pages_site.BuildPagesSiteTests.test_generated_coaching_pages_have_no_trailing_whitespace`: failed before the optional-block fix, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 44 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages plus topic page validation.
  - `git diff --check`: passed with only existing generated-report CRLF warnings.
  - `gitleaks dir . --redact`: passed, no leaks found.
- Commit: `feat: add trend evidence drilldowns` (`2940d76`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28307051954`.
- Next direction: improve evidence-page scanning and cross-topic navigation for faster coach-style review.

## Cycle 2 - Stage 3 - UIUX

- Prompt: `AGENT_UIUX_MAIN.txt`
- Goal: upgrade topic evidence pages from static evidence lists into a faster scan-and-filter coaching workbench.
- Start status: clean `main`, fast-forward synced with `origin/main`; Stage 2 deployment passed after log closeout (`f6e9de8`, CI `28307077843`).
- UI/UX audit findings:
  - P1: topic pages exposed complete evidence but forced linear scanning through long card lists.
  - P1: switching between recurring problems required returning to dashboard/practice-plan.
  - P2: there was no interaction feedback for narrowing evidence by match outcome.
  - P2: mobile topic exploration needed a denser, touch-friendly navigation pattern.
- Plan:
  - Add failing tests for topic workbench structure, filters, counters, empty state, and stylesheet hooks.
  - Generate per-topic quick-switch navigation across all canonical topics.
  - Add result filters with `aria-pressed`, live count updates, card hiding, and empty-state feedback.
  - Keep the page static and dependency-free while improving desktop and mobile layouts.
  - Rebuild `public`, verify browser desktop/mobile behavior, run local CI-equivalent gates, push, and watch Actions.
- Result:
  - Added a `topic-workbench` layout to every `trend-*.html` page.
  - Added topic switcher links, evidence counters, win/loss filter buttons, hidden-card states, and `没有符合当前筛选的证据` empty state.
  - Added responsive CSS so desktop uses a side topic rail and mobile uses a horizontal touch-friendly topic switcher.
  - Hid the mobile switcher scrollbar after visual verification showed it was noisy.
  - Tightened static validation so generated topic pages must keep the workbench controls.
- Browser verification:
  - Desktop `trend-death-cost.html`: 6 topic links, 10 evidence cards, win filter shows 5 cards, lose filter shows 5 cards, no overflow, no console warnings/errors.
  - Mobile 390px: 6 topic links, filter controls present, 10 visible cards by default, switcher scrollable without page overflow, no console warnings/errors.
- Local verification:
  - `python -m unittest tests.test_build_pages_site.BuildPagesSiteTests.test_build_pages_site_writes_topic_evidence_pages_and_links tests.test_build_pages_site.BuildPagesSiteTests.test_semantic_trend_provenance_has_visible_styles`: failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 44 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages plus topic workbench validation.
  - `git diff --check`: passed with only generated-report CRLF warnings.
  - `gitleaks dir . --redact`: passed, no leaks found.
- Commit: `feat: upgrade topic evidence workbench` (`252abae`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28307268987`.
- Next direction: add a generated freshness/coverage manifest so the dashboard explains which reports and latest match produced the current coaching plan.

## Cycle 2 - Stage 4 - IMPROVE

- Prompt: `AGENT_IMPROVE_MAIN.txt`
- Goal: add a generated coverage/freshness manifest and make the dashboard explain the report set behind the coaching plan.
- Start status: clean `main`; Stage 3 deployment passed after log closeout (`3ac32cd`, CI `28307298755`).
- Previous-stage direction: add a generated freshness/coverage manifest so the dashboard explains which reports and latest match produced the current coaching plan.
- Plan:
  - Add failing tests for `site-manifest.json` and visible `复盘数据覆盖` panels.
  - Build a deterministic manifest from parsed reports and canonical trends.
  - Render the same coverage summary on both history and practice-plan pages.
  - Tighten static validation so manifest and coverage panels cannot disappear.
  - Rebuild public output, verify browser desktop/mobile behavior, run local gates, push, and watch Actions.
- Result:
  - Added `public/site-manifest.json` with schema version, player id, report count, finding count, topic count, high-priority report count, win/loss counts, latest match, and topic coverage.
  - Added `复盘数据覆盖` panels to `index.html` and `practice-plan.html`.
  - Added a JSON link from the panel for auditing the generated source set.
  - Added responsive coverage-panel styles.
  - Extended static validation for manifest structure and page coverage.
- Browser verification:
  - History page: one coverage panel, manifest link, 10 reports, 30 findings, 6 topics, latest `Dragon Knight #8867124876`, no overflow, no console warnings/errors.
  - Practice plan: same coverage panel present, no overflow, no console warnings/errors.
  - Mobile 390px: coverage panel renders 4 stats, no horizontal overflow, no console warnings/errors.
- Local verification:
  - `python -m unittest tests.test_build_pages_site.BuildPagesSiteTests.test_build_pages_site_writes_site_manifest_and_coverage_panel tests.test_build_pages_site.BuildPagesSiteTests.test_semantic_trend_provenance_has_visible_styles`: failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 45 tests.
  - `python -m compileall -q .`: failed once on a static-check indentation regression, then passed after fixing.
  - `python scripts/check_public_site.py`: passed, 10 report pages plus manifest and coverage validation.
  - `git diff --check`: passed with only generated HTML CRLF warnings.
  - `gitleaks dir . --redact`: passed, no leaks found.
- Commit: `feat: add report coverage manifest` (`d56aeae`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28311495305`.
- Next direction: CHECK-stage audit for stale/orphaned generated pages and broken local links.

## Cycle 2 - Stage 5 - CHECK

- Prompt: `AGENT_CHECK_MAIN.txt`
- Goal: audit generated Pages artifacts for stale/orphaned links, manifest/report consistency, sensitive data, and CI coverage gaps.
- Start status: clean `main`, fast-forward synced with `origin/main`; Stage 4 deployment passed after log closeout (`288c5dc`, CI `28311525127`).
- Checks performed:
  - Confirmed current branch is `main` and working tree was clean before edits.
  - Re-read CI workflow commands.
  - Confirmed no local `data/` files are tracked.
  - Scanned for TODO/debugger/console/sensitive-token strings; hits were variable names, secret names in docs, and error text, not actual secrets.
  - Ran gitleaks.
  - Checked generated public site.
- Issue found:
  - `scripts/check_public_site.py` validated required sections but did not validate local links/assets, so a generated dashboard/topic/report link could point to a missing local file and still pass CI.
  - While adding the test, the checker also proved hard to import because it used script-only imports.
- Result:
  - Made `check_public_site.py` importable from tests while still runnable as a script.
  - Added `LocalLinkParser` and `_find_local_link_issues()` to detect broken local `href`/`src` references in generated HTML.
  - Wired local-link auditing into the CI static-site checker.
  - Added a regression test that fails on `index.html -> missing-report.html`.
- Browser / HTTP verification:
  - HTML dashboard remained healthy with one manifest link and no overflow/console warnings before JSON navigation.
  - In-app browser blocked direct JSON navigation with `ERR_BLOCKED_BY_CLIENT`; HTTP request to `http://127.0.0.1:8010/site-manifest.json` returned 200 with 10 reports, 30 findings, 6 topics, and latest match `8867124876`.
- Local verification:
  - `python -m unittest tests.test_build_pages_site.BuildPagesSiteTests.test_static_site_checker_detects_missing_local_links`: failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 46 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages plus manifest/local-link checks.
  - `git diff --check`: passed.
  - `gitleaks dir . --redact`: passed, no leaks found.
- Commit: `fix: audit generated local links` (`c86a911`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28311681379`.
- Next direction: add shareable URL-persisted filters for the history page so filtered review queues can be reopened or shared.

## Cycle 2 - Stage 6 - IMPROVE

- Prompt: `AGENT_IMPROVE_MAIN.txt`
- Goal: make match-history filters shareable and refresh-safe with URL-persisted state.
- Start status: clean `main`; Stage 5 deployment passed after log closeout (`c5184c1`, CI `28311703604`).
- Previous-stage direction: add shareable URL-persisted filters for the history page so filtered review queues can be reopened or shared.
- Plan:
  - Add failing tests for clear-filter controls and URL-state script hooks.
  - Initialize history filters from `result`, `priority`, and `q` query params.
  - Sync filter changes back into the URL with `history.replaceState`.
  - Add a clear-filter button that resets state, visible rows, and URL.
  - Rebuild public output, browser-test the URL flow, run local gates, push, and watch Actions.
- Result:
  - Added `清除筛选` to the match-history filter header.
  - Added URL parsing with `URLSearchParams` for `result`, `priority`, and search query `q`.
  - Added URL synchronization with `history.replaceState` after result/priority/search changes.
  - Added reset behavior that restores all rows and removes query params.
  - Added responsive styles for the clear button.
  - Extended static validation to require the URL filter hooks.
- Browser verification:
  - Loaded `/?result=lose&priority=high&q=Dragon`: active filters restored, search input set to `Dragon`, 1 / 10 visible row, no overflow, no console warnings/errors.
  - Clicked `清除筛选`: URL returned to `/`, filters reset to all, 10 / 10 rows visible.
  - Clicked `只看胜利`: URL changed to `/?result=win`, 5 / 10 rows visible.
- Local verification:
  - `python -m unittest tests.test_build_pages_site.BuildPagesSiteTests.test_render_index_contains_clickable_match_table_with_real_fields`: failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 46 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `git diff --check`: passed with generated HTML CRLF warnings only.
  - `gitleaks dir . --redact`: passed, no leaks found.
- Commit: `feat: persist history filter URLs` (`46ef363`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28311817122`.
- Next direction: persist topic evidence filters and add hero/topic URL filters once the match sample grows.

## Cycle 2 - Final Status

- Completed stages: 6 / 6.
- Final feature commit before log closeout: `46ef363`.
- Final verified workflow at feature commit: `Deploy Cloudflare Pages` run `28311817122`, passed.
- Local final gates:
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 46 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
- Remaining risks:
  - Topic evidence filters do not persist in URL yet.
  - External CDN hero images are not checked by the local-link validator.
  - Manifest describes generated report coverage, not external STRATZ/OpenDota fetch freshness.
- Recommended next flagship change: persist topic evidence filters and add hero/topic filter URLs when the report set grows.

## Global Preparation

- Status: clean on `main`, synced with `origin/main`.
- Recent commits checked: latest 5 requested; repository currently has 4 commits.
- Prompt files read from `C:\Users\12031\Desktop\AGENT_PROMPTS_MAIN_PACK`.
- CI workflow: `.github/workflows/deploy-pages.yml`.
- CI commands: install `requirements.txt`, run unit tests, compile Python, validate static site, deploy to Cloudflare Pages.
- Baseline verification:
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 35 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.

## Stage 1 - IMPROVE

- Prompt: `AGENT_IMPROVE_MAIN.txt`
- Goal: improve the historical review site with a product-visible capability that makes match review navigation more actionable.
- Start status: clean `main`, baseline CI commands passed.
- Plan:
  - Identify the next high-value continuation from the current report-history baseline.
  - Add an evidence-backed match overview surface that helps the player decide which replay to review first.
  - Add focused validation so the generated public site cannot regress silently.
- Result:
  - Added a coach priority queue to the history page.
  - Parsed each report's first structured finding into review focus, next action, success metric, and priority.
  - Rendered each match row with the real training focus and acceptance metric from that report.
  - Rebuilt `public` from the real report source.
- Local verification:
  - `python -m unittest tests.test_build_pages_site`: failed before implementation for missing fields, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 35 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
- Commit: `feat: add coach review priority queue` (`f24c0f6`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, run `28299842160`.
- Risks:
  - Priority is derived from the report's existing finding priority plus real match outcome/death count, not from new external data.
- Next stage: Stage 2 IMPROVE.

## Stage 2 - IMPROVE

- Prompt: `AGENT_IMPROVE_MAIN.txt`
- Goal: add a cross-match trend board so repeated issues become a concrete training plan.
- Start status: clean `main`, stage 1 CI passed, local unit tests and static site validation passed.
- Previous-stage direction:
  - Stage 1 recommended generating a recent-trends summary from repeated report findings.
- Plan:
  - Aggregate report findings by focus/category across the current public report set.
  - Render a trend board on the history page with frequency, examples, next action, and acceptance metric.
  - Export the same trend data as JSON for later UI and automation work.
  - Add tests that fail before the aggregate trend generator exists.
- Result:
  - Added cross-match focus trend aggregation from real report findings.
  - Added a `最近反复问题` trend board to the history page.
  - Generated `public/review-trends.json` with schema version, priorities, examples, actions, and success metrics.
  - Extended static site validation to require the trend board and JSON payload.
- Local verification:
  - `python -m unittest tests.test_build_pages_site`: failed before implementation for missing trend generation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 37 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
- Data check:
  - `public/review-trends.json`: 3 trend groups; top group appears in 5 matches.
- Commit: `feat: add recurring review trends` (`f192360`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, run `28299977468`.
- Risks:
  - Trend grouping uses the exact report focus text; future work may normalize semantically similar focus names if they diverge.
- Next stage: Stage 3 UIUX.

## Stage 3 - UIUX

- Prompt: `AGENT_UIUX_MAIN.txt`
- Goal: make the history page feel like a usable coaching dashboard with responsive filtering and no layout overflow.
- Start status: clean `main`, stage 2 CI passed.
- Baseline browser finding:
  - Desktop 1280px had horizontal overflow: `scrollWidth 1308 > clientWidth 1265`.
- Result:
  - Added a visible `筛选比赛` tool with search, result filters, priority filters, active states, and live visible-count feedback.
  - Added row data attributes for hero, result, priority, focus, and search text.
  - Fixed the default desktop overflow by widening the responsive table breakpoint to 1360px.
  - Extended static site validation to require filter controls.
- Browser verification:
  - Desktop 1280px: no overflow, filters visible, losing-match filter changed count to 5/10, Mirana search changed count to 1/10.
  - Mobile 390px: no overflow, filters visible, priority filter active state works.
  - Navigation flow: history page -> latest report -> back to history, no overflow and no console warnings/errors.
  - Screenshot attempt failed due browser CDP screenshot timeout; DOM/layout/interaction checks completed successfully.
- Local verification:
  - `python -m unittest tests.test_build_pages_site.BuildPagesSiteTests.test_render_index_contains_clickable_match_table_with_real_fields`: failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 37 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
- Commit: `feat: upgrade review history filtering UX` (`a761acc`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, run `28300185847`.
- Risks:
  - The filter is intentionally static-client-side; no persistence or URL query sharing yet.
- Next stage: Stage 4 IMPROVE.

## Stage 4 - IMPROVE

- Prompt: `AGENT_IMPROVE_MAIN.txt`
- Goal: connect individual reports into the match-history context so review can continue without returning to the list manually.
- Start status: clean `main`, stage 3 CI passed, local tests and static validation passed.
- Previous-stage direction:
  - Stage 3 recommended previous/next report navigation and adjacent-match context inside reports.
- Plan:
  - Add deterministic adjacent-match navigation to copied public reports.
  - Show current report position, nearby hero, result, and focus text using real report metadata.
  - Add tests that fail before the injection exists.
  - Extend static validation so every report must include the adjacent-match navigation.
- Result:
  - Injected `相邻比赛` navigation into every copied public report.
  - Each report now shows position in the current history set and links to the newer/older adjacent match when available.
  - Neighbor cards include real hero, match id, result, and review focus.
  - Extended static validation to require adjacent report navigation.
- Browser verification:
  - Opened Dragon Knight report, saw `第 1 / 10 场` and the next older Mirana report.
  - Clicked the Mirana neighbor link; Mirana report loaded with action list and adjacent navigation.
  - No horizontal overflow or console warnings/errors.
- Local verification:
  - `python -m unittest tests.test_build_pages_site.BuildPagesSiteTests.test_build_pages_site_injects_adjacent_report_navigation`: failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 38 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
- Commit: `feat: add adjacent report navigation` (`2058dfd`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, run `28305140645`.
- Risks:
  - Navigation is generated from the current public report set; if source reports are missing, the chain reflects only available reports.
- Next stage: Stage 5 CHECK.

## Stage 5 - CHECK

- Prompt: `AGENT_CHECK_MAIN.txt`
- Goal: run a focused project health check and fix a real stability/UX issue without adding unrelated features.
- Start status: clean `main`, stage 4 CI passed, local tests and static validation passed.
- Checks performed:
  - Verified `data/dota2.db` is ignored and not tracked.
  - Scanned for TODO/debugger/console/sensitive-token strings.
  - Ran `gitleaks dir . --redact`.
  - Rebuilt `public` from the real report source and confirmed generated output stays consistent.
  - Ran unit tests and static validation.
- Issue found:
  - The history filters could produce an empty table with only `显示 0 / 10 场`; there was no explicit empty state, making the UI look broken.
- Result:
  - Added a `没有匹配的比赛` empty state to the history page.
  - Updated filter JavaScript to toggle the empty state when visible rows reach zero.
  - Added styling and static validation for the empty state.
- Browser verification:
  - Searched `zzzz-no-match`; page showed `显示 0 / 10 场` plus the empty-state guidance, no overflow, no console warnings/errors.
- Local verification:
  - `python -m unittest tests.test_build_pages_site.BuildPagesSiteTests.test_render_index_contains_clickable_match_table_with_real_fields`: failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 38 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
- Commit: `fix: add empty state for match filters` (`9adaf42`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, run `28305267306`.
- Risks:
  - Exact trend focus normalization remains future work.
- Next stage: Stage 6 IMPROVE.

## Stage 6 - IMPROVE

- Prompt: `AGENT_IMPROVE_MAIN.txt`
- Goal: turn recurring review trends into a next-session practice plan.
- Start status: clean `main`, stage 5 CI passed.
- Previous-stage direction:
  - Stage 5 recommended generating a practice-plan page from recurring trends.
- Result:
  - Added `practice-plan.html`.
  - Added a history-page entry point labeled `下一次训练计划`.
  - Practice cards use real trend data: frequency, involved heroes, next action, acceptance metric, and example match links.
  - Fixed the static checker so non-report pages are not validated as match reports.
  - Extended static validation to require the practice-plan page and core content.
- Browser verification:
  - Opened history page, clicked `practice-plan.html`, verified 3 practice cards.
  - Desktop: no overflow, first card shows `前10分钟资源`, 5 matches, next action, and acceptance metric.
  - Mobile 390px: no overflow, back link visible, cards render.
  - No console warnings/errors.
- Local verification:
  - `python -m unittest tests.test_build_pages_site.BuildPagesSiteTests.test_build_pages_site_writes_practice_plan_page`: failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 39 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
- Commit: `feat: add next-session practice plan` (`b879a1a`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, run `28305412170`.
- Risks:
  - The practice plan is generated from exact trend focus names; semantic normalization remains future work.
- Next stage: complete 6-stage run.

## Final Status

- Completed stages: 6 / 6.
- Final deployed commit before log closeout: `b879a1a`.
- Final GitHub Actions / CI status: passed, run `28305412170`.
- Live checks:
  - `https://dota.custard.top/`: history filters, empty state, and practice-plan link present.
  - `https://dota.custard.top/practice-plan.html`: 3 practice cards and next-action content present.
  - Dragon Knight report: adjacent-match navigation and action list present.
  - `review-trends.json`: schema version 1 with 3 trends.
- Remaining risk:
  - Trend grouping still uses exact focus strings; semantic normalization is the next highest-value improvement.

## 2026-06-28 - Long Cycle Stage 1 IMPROVE - Start

- Stage: 1 / 6
- Type: IMPROVE
- Prompt: AGENT_IMPROVE_MAIN.txt
- Goal: Persist topic evidence win/loss filters in the URL so recurring-problem views can be refreshed and shared.
- Carry-over: Previous iteration recommended persisting topic-page evidence filters and adding richer shareable filters.
- Start state: main branch, clean worktree, origin/main up to date; CI workflow is Deploy Cloudflare Pages.
- Constraints: do not touch Docker; do not edit AGENTS.md; no force push or branch changes.

## 2026-06-28 - Long Cycle Stage 1 IMPROVE - Complete

- Completed: topic evidence pages now persist win/loss filters through `?result=win|lose`, update URLs on button clicks, and expose a clear-filter control.
- User-visible increment: shareable recurring-problem evidence links preserve the selected result slice after refresh.
- Real issue fixed: topic filters no longer reset silently on refresh.
- Local verification:
  - `python -m unittest tests.test_build_pages_site.BuildPagesSiteTests.test_build_pages_site_writes_topic_evidence_pages_and_links`: failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 54 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
  - Browser: `trend-death-cost.html?result=lose` initialized correctly, win filter updated URL, clear filter removed query, no console errors.
- Commit: `feat: persist topic evidence filters` (`bef1838`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28319963955`.
- Risk: topic filters are result-only; hero/role evidence filtering remains the next useful extension.
- Next stage: Stage 2 IMPROVE.

## 2026-06-28 - Long Cycle Stage 2 IMPROVE - Start

- Stage: 2 / 6
- Type: IMPROVE
- Prompt: AGENT_IMPROVE_MAIN.txt
- Goal: Add hero-aware topic evidence filtering with URL persistence so larger evidence archives can be narrowed by hero and result.
- Carry-over: Stage 1 left result-only topic filters; the next useful extension is hero/role evidence filtering.
- Start state: main branch after `chore: record stage 1 filter deployment` (`8533945`), clean worktree expected after CI success.
- Constraints: do not touch Docker; do not edit AGENTS.md; no force push or branch changes.

## 2026-06-28 - Long Cycle Stage 2 IMPROVE - Complete

- Completed: topic evidence pages now support combined hero and win/loss filtering, persist both selections in shareable `?result=...&hero=...` URLs, and reset both dimensions through one clear action.
- User-visible increment: recurring-problem archives can be narrowed to the exact hero/result slice needed for comparison instead of scanning every evidence card.
- Real issue fixed during browser QA: narrow topic pages needed stronger overflow protection; headings now wrap safely and mobile topic statistics use a stable two-column grid.
- Local verification:
  - Target topic-page tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 54 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
  - Browser: `?result=lose&hero=Legion+Commander` restored one matching card; switching to Dragon Knight preserved the loss filter and showed two cards; clear restored 10/10 cards and removed the query; mobile layout and console were clean after the responsive fix.
- Commit: `feat: add hero filters to topic evidence` (`88b56a0`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28320739812`.
- Risk: topic filters are exact-hero filters; role grouping is intentionally deferred because the generated report evidence does not currently expose a verified role on every topic card.
- Next stage: Stage 3 UIUX.

## 2026-06-28 - Long Cycle Stage 3 UIUX - Start

- Stage: 3 / 6
- Type: UIUX
- Prompt: AGENT_UIUX_MAIN.txt
- Flagship goal: turn long match reports into a navigable evidence workspace with direct access to coaching, actions, timeline, events, findings, and item analysis.
- Supporting improvements: skip-to-content accessibility, active-section feedback, a top-return control, mobile horizontal navigation, stable anchor offsets, and visible keyboard focus.
- Design choice: use one sticky horizontal section navigator instead of a desktop-only sidebar or collapsed report sections; this preserves data-table width and keeps the same interaction model on desktop and mobile.
- Start state: main at `chore: record stage 2 hero filter deployment` (`0dbaaf0`), Stage 2 closeout CI passed in run `28320763849`, clean worktree.
- Constraints: do not touch Docker; do not edit AGENTS.md; no force push or branch changes; no new frontend dependency.

## 2026-06-28 - Long Cycle Stage 3 UIUX - Complete

- Completed: long match reports now include a skip link, sticky section navigation, anchored coaching/action/data/timeline/event/finding/item sections, active-section state, a visible return-top control, and local horizontal scrolling for timeline tables.
- User-visible increment: a player can jump directly to `下一局`, `时间线`, `事件`, `问题证据`, or `出装` inside a long report instead of repeatedly scrolling through the full document.
- Real issues fixed during browser QA:
  - Mobile active-link centering now scrolls only the navigation rail, not the whole page.
  - The return-top control is sticky on the right side of the horizontal report navigator, so it remains clickable on 390px mobile width.
- Browser verification:
  - Desktop report: `#next-actions` click updated the hash, activated `下一局`, kept horizontal scroll at 0, exposed 7 section links, and produced zero console errors.
  - Mobile 390px report: `#timeline-diagnosis` click activated `时间线`, kept document width equal to viewport width, preserved a local timeline-table scroller, kept the sticky top link visible, and produced zero console errors.
- Local verification:
  - Target regression tests failed before implementation where applicable, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 55 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Commit: `feat: add report section navigation` (`67d2ac4`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28321347459`.
- Risk: section navigation is static HTML/JS, so future generated report sections need matching IDs to appear in the rail.
- Next stage: Stage 4 IMPROVE.

## 2026-06-28 - Long Cycle Stage 4 IMPROVE - Start

- Stage: 4 / 6
- Type: IMPROVE
- Prompt: AGENT_IMPROVE_MAIN.txt
- Goal: connect the generated training plan to pre-filtered evidence and per-topic action checkpoints so the player can move from "what to train" to "which games prove it" and "what to execute next game".
- Carry-over: Stage 3 recommended connecting the training plan more directly to pre-filtered evidence and action checkpoints.
- Start state: main at `chore: record stage 3 navigation deployment` (`2935277`), Stage 3 closeout CI passed in run `28321377046`, clean worktree.
- Constraints: do not touch Docker; do not edit AGENTS.md; no force push or branch changes; no new frontend dependency.

## 2026-06-28 - Long Cycle Stage 4 IMPROVE - Complete

- Completed: `practice-plan.html` is now a training task workbench with URL-filtered task states, local checkbox progress, per-topic next-game checkpoints, and evidence links that open topic pages pre-filtered by result or hero.
- User-visible increment: the player can jump from a training task directly into `?result=lose` failure evidence, compare `?result=win` samples, and track whether the next-game checklist is done without leaving the static site.
- Real issues fixed:
  - The previous plan linked only example matches, so it did not connect the training task to the complete evidence archive or filtered failure cases.
  - Generated Pages files now write UTF-8 with LF newlines, avoiding Windows CRLF churn that made unchanged public artifacts appear dirty after each build.
  - A source/output mix-up during generation was recovered by restoring generated public files and rebuilding from a separate 10-report staging source; no Docker or protected files were touched.
- Browser verification:
  - Desktop: 4 task cards, 12 checks, 4 loss-evidence links, `done` filter persisted as `?practice=done`, 3/3 progress survived reload, and console errors were zero.
  - Evidence jump: `trend-death-cost.html?result=lose` opened with `只看失败` active and 6 / 10 evidence cards visible.
  - Mobile 390px: `?practice=todo` rendered 3 visible unfinished cards after one completed card, document width matched viewport width, and console errors were zero.
- Local verification:
  - Target practice-plan tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 55 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Commit: `feat: add practice task workbench` (`bc0a56a`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28363394164`.
- Risk: checklist progress uses browser localStorage, so it is intentionally per-browser and not synced across devices.
- Next stage: Stage 5 CHECK.

## 2026-06-29 - Long Cycle Stage 5 CHECK - Start

- Stage: 5 / 6
- Type: CHECK
- Prompt: AGENT_CHECK_MAIN.txt
- Goal: harden generated-site validation around broken anchors, duplicate IDs, report navigation targets, and practice-workbench links so static regressions fail before deploy.
- Carry-over: Stage 4 recommended strengthening static validation for the new evidence-linked training workflow.
- Start state: main at `chore: record stage 4 workbench deployment` (`82ab3a4`), Stage 4 closeout CI passed in run `28363460323`, clean worktree.
- Constraints: do not touch Docker; do not edit AGENTS.md; no force push or branch changes; keep the CHECK diff focused on real validation gaps.

## 2026-06-29 - Long Cycle Stage 5 CHECK - Complete

- Completed: static Pages validation now detects duplicate element IDs, broken local anchors including `href="#..."`, and missing practice-workbench structures.
- Real risks fixed:
  - Report section navigation, return-top links, topic anchors, and generated in-page links could previously point to missing IDs without failing CI.
  - Duplicate IDs in generated pages could silently break navigation or active-section behavior.
  - The Stage 4 training workbench could regress out of `practice-plan.html` while older broad content checks still passed.
- Local verification:
  - New checker tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 57 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Commit: `fix: harden static site validation` (`a1209cd`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28363713371`.
- Risk: static validation still does not verify external CDN image availability.
- Next stage: Stage 6 IMPROVE.

## 2026-06-29 - Long Cycle Stage 6 IMPROVE - Start

- Stage: 6 / 6
- Type: IMPROVE
- Prompt: AGENT_IMPROVE_MAIN.txt
- Goal: add a compact export/share artifact for the training plan, generated from the same evidence data as `practice-plan.html`.
- Carry-over: Stage 5 recommended a plain-text next-session checklist generated from current training topics.
- Start state: main at `chore: record stage 5 validation deployment` (`f0432dd`), Stage 5 closeout CI passed in run `28363786094`, clean worktree.
- Constraints: do not touch Docker; do not edit AGENTS.md; no force push or branch changes; keep the export static and evidence-derived.

## 2026-06-29 - Long Cycle Stage 6 IMPROVE - Complete

- Completed: generated `practice-plan.txt` from the same trend evidence as the HTML training workbench and linked it from `practice-plan.html` as `导出训练清单`.
- User-visible increment: the player can copy or save a compact next-game checklist with priority topics, actions, acceptance metrics, failure-evidence links, win-sample links, hero-specific links, and the 3-step execution checkpoint.
- Stability improvement: static validation now requires `practice-plan.txt` and verifies its core training/export content.
- Browser / HTTP verification:
  - `practice-plan.html` rendered one `practice-plan.txt` export link, 4 task cards, no horizontal overflow, and no console errors.
  - Direct browser navigation to `.txt` was blocked by the in-app browser extension, matching earlier JSON blocking behavior.
  - HTTP request to `http://127.0.0.1:8026/practice-plan.txt` returned 200 and contained title, player id, failure evidence, and checkpoint content.
- Local verification:
  - Export test failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 57 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Commit: `feat: add portable practice plan export` (`4872655`).
- Push: pushed to `origin/main`.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28364459477`.
- Risk: the text export is static at build time; it does not include per-browser checkbox completion state.
- Next stage: final online acceptance.

## 2026-06-29 - Long Cycle Final Online Acceptance - Complete

- Campaign status: all 6 / 6 stages completed in the required `IMPROVE -> IMPROVE -> UIUX -> IMPROVE -> CHECK -> IMPROVE` order.
- Final deployed stage commit: `chore: record stage 6 export deployment` (`2311b6f`).
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28364548302`; deployment URL `https://8205033a.cstd-help.pages.dev`.
- Repository status: `Muguett-DBY/cstd-help` is public and uses `main` as its default branch.
- Live custom-domain verification:
  - `https://dota.custard.top/`: 200; rendered 10-match history, latest Legion Commander report, evidence coverage, filters, priority queue, and trend links.
  - `https://dota.custard.top/practice-plan.html`: 200; rendered 4 evidence-driven tasks, 12 checkpoints, state filters, and the `practice-plan.txt` export link.
  - `https://dota.custard.top/practice-plan.txt`: 200; contained the player id, priorities, actions, acceptance metrics, failure/win evidence links, hero links, and execution checkpoints.
  - `https://dota.custard.top/trend-death-cost.html?result=lose`: 200; browser state applied `只看失败` and showed 6 / 10 evidence cards.
  - Latest Legion Commander report: 200; hero-first title, 8 report navigation links, next-action checklist, 10/20-minute data, low-efficiency windows, 12 located deaths, and 27.7-minute Black King Bar event were present.
  - Mobile 390px practice-plan check: 4 task cards and 4 filters rendered, export remained visible, document width equaled viewport width, and console errors were zero.
  - Direct Pages smoke: `https://8205033a.cstd-help.pages.dev/practice-plan.txt` returned 200 with the expected title and player id.
- Final local release gates: 57 tests passed; compileall, public-site validation for 10 reports, gitleaks, diff check, and forbidden-file check passed.
- Protected scope: no Docker or `AGENTS.md` changes were made.
- Residual risks: practice checkbox state remains browser-local by design; the text export reflects build-time evidence and does not include local checkbox state; external CDN image availability is outside static validation.

## 2026-06-29 - Long Cycle 2 Stage 1 IMPROVE - Start

- Stage: 1 / 6
- Type: IMPROVE
- Prompt: AGENT_IMPROVE_MAIN.txt
- Goal: turn the existing next-session training plan into an even faster pre-match execution surface that can be read immediately before queueing.
- Carry-over: the prior cycle left a build-time practice export and browser-local checklist; the next high-value step is making the plan usable at match start, not only as a post-review page.
- Start state: main at `chore: record six-stage completion` (`cc86b37`), clean worktree, origin/main up to date, latest tracked public report set preserved.
- Constraints: do not touch Docker; do not edit `AGENTS.md`; no branch changes; no force push; keep generated public reports on the latest tracked 10-match set.

## 2026-06-29 - Long Cycle 2 Stage 1 IMPROVE - Local Complete

- Completed: generated `match-brief.html`, linked it from the dashboard and practice plan, and styled it as a 30-second pre-match execution card with three evidence-ranked commitments.
- User-visible increment: before queueing, the player can open one page showing the latest reviewed match, the three highest-priority habits to execute, direct failure-evidence links, and a post-game review loop.
- Real issues fixed:
  - Legacy source reports with old final-item slots are upgraded during Pages build so published reports no longer show unresolved `Item #...` labels.
  - Static validation now treats `match-brief.html` as a first-class non-report page and requires its core execution-card content.
  - A temporary default-source rebuild mixed in an older 886 report set; public was restored to the latest tracked 10-report source before the final build.
- Local verification:
  - New `match-brief.html` test failed before implementation, then passed.
  - New legacy item-slot upgrade test failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 58 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
  - Browser fallback QA: Playwright CLI screenshots for desktop 1280px and mobile 390px rendered the execution card; HTTP check returned 200 with 3 cards and latest Legion Commander match.
- Commit: `feat: add pre-match execution brief` (`71bc201`).
- Push / CI: pushed to `origin/main`; GitHub Actions passed, `Deploy Cloudflare Pages` run `28366750310`.
- Live check: `https://dota.custard.top/match-brief.html`, `/`, and `/practice-plan.html` returned 200 and contained `赛前执行卡` plus latest `Legion Commander #8870219537` context.
- Risk: `match-brief.html` is build-time static; it intentionally does not include browser-local checklist completion state.
- Next stage after CI closeout: Stage 2 IMPROVE.

## 2026-06-29 - Long Cycle 2 Stage 1 IMPROVE - Complete

- Completed stage: 1 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Stage commit: `feat: add pre-match execution brief` (`71bc201`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28366750310`.
- Production acceptance: custom domain served the new pre-match execution card and linked it from the dashboard and practice plan.
- Remaining risk: the pre-match card is static at build time and does not sync browser-local checklist progress.
- Next stage: Stage 2 IMPROVE.

## 2026-06-29 - Long Cycle 2 Stage 2 IMPROVE - Start

- Stage: 2 / 6
- Type: IMPROVE
- Prompt: AGENT_IMPROVE_MAIN.txt
- Goal: add comparable winning evidence beside each pre-match commitment so the card shows both what failed and what a better sample looks like.
- Carry-over: Stage 1 recommended hero/topic comparison lanes from the pre-match card into wins and losses.
- Start state: main at `chore: record stage 1 brief deployment` (`840b03b`), clean worktree, CI passed in run `28366861561`.
- Constraints: do not touch Docker; do not edit `AGENTS.md`; keep the latest 10-report public set.

## 2026-06-29 - Long Cycle 2 Stage 2 IMPROVE - Local Complete

- Completed: each pre-match commitment now renders a two-column proof lane with `失败证据` and `胜利样本` plus filtered topic links for `result=lose` and `result=win`.
- User-visible increment: the player can compare the mistake pattern against a winning sample directly from the 30-second execution card.
- Real issue fixed: topics without a real winning sample no longer duplicate failure text under `胜利样本`; they explicitly say that no win sample exists yet.
- Local verification:
  - Target `match-brief.html` test failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 58 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - HTTP/browser fallback QA: local `match-brief.html` returned 200 with 3 proof grids and both win/loss links; Playwright CLI screenshot confirmed desktop layout.
- Commit: `feat: add win loss proof lanes` (`2294d9b`).
- Push / CI: pushed to `origin/main`; GitHub Actions passed, `Deploy Cloudflare Pages` run `28367152171`.
- Live check: `https://dota.custard.top/match-brief.html` returned 200 and contained `brief-proof-grid`, `胜利样本`, and latest `Legion Commander #8870219537` context.
- Risk: winning samples are topic-level, not hero-specific yet.
- Next stage after CI closeout: Stage 3 UIUX.

## 2026-06-29 - Long Cycle 2 Stage 2 IMPROVE - Complete

- Completed stage: 2 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Stage commit: `feat: add win loss proof lanes` (`2294d9b`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28367152171`.
- Production acceptance: custom domain served the proof-lane execution card with both failure and winning-sample evidence links.
- Remaining risk: winning samples are still topic-level rather than hero-specific comparisons.
- Next stage: Stage 3 UIUX.

## 2026-06-29 - Long Cycle 2 Stage 3 UIUX - Start

- Stage: 3 / 6
- Type: UIUX
- Prompt: AGENT_UIUX_MAIN.txt
- Goal: make the pre-match execution card faster to scan on mobile and desktop by adding a compact commitment navigation strip.
- Carry-over: Stage 2 made the card more useful but the three commitments were only visible after scanning the card grid.
- Start state: main at `chore: record stage 2 proof deployment` (`1b2fe00`), clean worktree, CI passed in run `28369055368`.
- Constraints: do not touch Docker; do not edit `AGENTS.md`; keep the latest 10-report public set.

## 2026-06-29 - Long Cycle 2 Stage 3 UIUX - Local Complete

- Completed: added a sticky `赛前只盯` command bar to `match-brief.html`, with one compact link per generated commitment and matching card anchors.
- User-visible increment: on desktop the player sees all three commitments in the first viewport; on mobile the commitments become a horizontal chip strip before the detailed cards.
- Static validation: `match-brief.html` now must include `brief-command-bar` so future builds cannot silently drop the scan navigation.
- Local verification:
  - Target UI tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 58 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
  - Browser fallback QA: local `match-brief.html` returned 200 with 3 command links, 3 card anchors, and 3 cards; Playwright CLI desktop/mobile screenshots rendered the command bar without obvious overlap.
- Commit: `feat: improve brief scan navigation` (`bfa8cca`).
- Push / CI: pushed to `origin/main`; GitHub Actions passed, `Deploy Cloudflare Pages` run `28369377149`.
- Live check: `https://dota.custard.top/match-brief.html` returned 200 and contained `brief-command-bar`, `赛前承诺导航`, `brief-commitment-3`, and latest `Legion Commander #8870219537` context.
- Risk: command bar is static and does not highlight active scroll position yet.
- Next stage after CI closeout: Stage 4 IMPROVE.

## 2026-06-29 - Long Cycle 2 Stage 3 UIUX - Complete

- Completed stage: 3 / 6.
- Type: UIUX.
- Prompt: AGENT_UIUX_MAIN.txt.
- Stage commit: `feat: improve brief scan navigation` (`bfa8cca`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28369377149`.
- Production acceptance: custom domain served the sticky scan navigation with three commitment anchors.
- Remaining risk: the command bar does not track the currently visible commitment while scrolling.
- Next stage: Stage 4 IMPROVE.

## 2026-06-29 - Long Cycle 2 Stage 4 IMPROVE - Start

- Stage: 4 / 6
- Type: IMPROVE
- Prompt: AGENT_IMPROVE_MAIN.txt
- Goal: add a portable plain-text export for the pre-match execution card.
- Carry-over: Stage 3 made the HTML card faster to scan; the next improvement is making the same three commitments usable outside the page.
- Start state: main at `chore: record stage 3 navigation deployment` (`68e48ab`), clean worktree, CI passed in run `28369457147`.
- Constraints: do not touch Docker; do not edit `AGENTS.md`; keep the latest 10-report public set.

## 2026-06-29 - Long Cycle 2 Stage 4 IMPROVE - Local Complete

- Completed: generated `match-brief.txt` from the same top-three trend evidence used by `match-brief.html`, and linked it from the execution-card header as `导出执行卡`.
- User-visible increment: the player can open a lightweight text version with latest match context, the three commitments, exact action/metric text, and win/loss evidence links plus excerpts.
- Static validation: `scripts/check_public_site.py` now requires `match-brief.txt` and validates its core headings, commitments, actions, and evidence links.
- Local verification:
  - Target export test failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 58 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
  - Manual output review: `public/match-brief.txt` contains `Legion Commander #8870219537`, three commitments, failure evidence, and winning-sample evidence.
- Commit: `feat: add brief text export` (`12d001a`).
- Push / CI: pushed to `origin/main`; GitHub Actions passed, `Deploy Cloudflare Pages` run `28369747011`.
- Live check: `https://dota.custard.top/match-brief.html` linked `match-brief.txt`; `https://dota.custard.top/match-brief.txt` returned 200 and contained latest `Legion Commander #8870219537`, `承诺 1：死亡成本`, and failure evidence links.
- Risk: text export is build-time static and does not include browser-local checklist state.
- Next stage after CI closeout: Stage 5 CHECK.

## 2026-06-29 - Long Cycle 2 Stage 4 IMPROVE - Complete

- Completed stage: 4 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Stage commit: `feat: add brief text export` (`12d001a`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28369747011`.
- Production acceptance: custom domain served both the HTML execution card and the text export.
- Remaining risk: the text export is static at build time and does not include browser-local checklist state.
- Next stage: Stage 5 CHECK.

## 2026-06-29 - Long Cycle 2 Stage 5 CHECK - Start

- Stage: 5 / 6
- Type: CHECK
- Prompt: AGENT_CHECK_MAIN.txt
- Goal: harden generated-site validation around support-page classification and text exports.
- Root cause: support HTML pages and text exports were listed inline inside `main()`, while report-page classification was a separate ad hoc comprehension. That made future support pages easy to misclassify as match reports or forget from required-file checks.
- Start state: main at `chore: record stage 4 export deployment` (`b0926ce`), clean worktree, CI passed in run `28369832337`.
- Constraints: do not touch Docker; do not edit `AGENTS.md`; keep the latest 10-report public set.

## 2026-06-29 - Long Cycle 2 Stage 5 CHECK - Local Complete

- Completed: centralized support-file definitions in `scripts/check_public_site.py` and added `_is_report_page()` / `_report_pages()` so report classification is tested and reused.
- Bug/risk fixed: `index.html`, `practice-plan.html`, `match-brief.html`, and `trend-*.html` are explicitly non-report pages; `practice-plan.txt` and `match-brief.txt` are explicitly required support exports.
- Regression coverage: added a CHECK test that failed before implementation because `_is_report_page()` did not exist, then passed after the validation fix.
- Local verification:
  - New CHECK regression test failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 59 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Commit: `fix: harden support page validation` (`3e0e2a2`).
- Push / CI: pushed to `origin/main`; GitHub Actions passed, `Deploy Cloudflare Pages` run `28370064631`.
- Live check: `https://dota.custard.top/` returned 200 with history, practice-plan, and match-brief links; `https://dota.custard.top/match-brief.txt` returned 200 with latest `Legion Commander #8870219537`.
- Risk: support-page classification still uses filename conventions for `trend-*.html`, which is acceptable for the current static site generator.
- Next stage after CI closeout: Stage 6 IMPROVE.

## 2026-06-29 - Long Cycle 2 Stage 5 CHECK - Complete

- Completed stage: 5 / 6.
- Type: CHECK.
- Prompt: AGENT_CHECK_MAIN.txt.
- Stage commit: `fix: harden support page validation` (`3e0e2a2`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28370064631`.
- Production acceptance: custom domain still served the dashboard and text export after validator hardening.
- Remaining risk: support-page classification still uses the `trend-*.html` filename convention.
- Next stage: Stage 6 IMPROVE.

## 2026-06-29 - Long Cycle 2 Stage 6 IMPROVE - Start

- Stage: 6 / 6
- Type: IMPROVE
- Prompt: AGENT_IMPROVE_MAIN.txt
- Goal: add visible evidence freshness/context to the pre-match execution card.
- Carry-over: Stage 5 recommended making the card show exactly how much evidence it is based on before queueing.
- Start state: main at `chore: record stage 5 validation deployment` (`869eeaa`), clean worktree, CI passed in run `28370162029`.
- Constraints: do not touch Docker; do not edit `AGENTS.md`; keep the latest 10-report public set.

## 2026-06-29 - Long Cycle 2 Stage 6 IMPROVE - Local Complete

- Completed: added a `证据覆盖` strip to `match-brief.html`, showing report count, coach-evidence count, and topic count directly under the summary cards.
- User-visible increment: before queueing, the player can see that the current execution card is based on `10 场复盘`, `16 条教练证据`, and `4 个训练主题`, rather than trusting an opaque summary.
- Static validation: `scripts/check_public_site.py` now requires the execution card to include the freshness strip and report-count marker.
- Local verification:
  - Target UI tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 59 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
  - Browser fallback QA: local `match-brief.html` returned 200 with freshness content; Playwright CLI desktop/mobile screenshots showed the freshness strip without overlap.
- Commit: `feat: show brief evidence coverage` (`57919bf`).
- Push / CI: pushed to `origin/main`; GitHub Actions passed, `Deploy Cloudflare Pages` run `28370478876`.
- Live check: `https://dota.custard.top/match-brief.html` returned 200 and contained `证据覆盖`, `10 场复盘`, `16 条教练证据`, `4 个训练主题`, and latest `Legion Commander #8870219537`; `site-manifest.json` matched report_count=10, finding_count=16, topic_count=4.
- Risk: freshness values are build-time static and update on the next site build.
- Next stage after CI closeout: final six-stage summary.

## 2026-06-30 - Long Cycle 2 Stage 6 IMPROVE - Complete

- Completed stage: 6 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Stage commit: `feat: show brief evidence coverage` (`57919bf`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28370478876`.
- Production acceptance: custom domain served the evidence-coverage strip and manifest counts matched the visible values.
- Remaining risk: freshness values are static until the next Pages build.
- Final state: all six requested stages are complete locally and deployed after CI.

## 2026-06-30 - Long Cycle 3 - Global Preparation

- Requested control file: `C:\Users\12031\Desktop\AGENT_ORCHESTRATOR_3_LEVELS_V2\03_LONG_6_STAGE_MAIN_V2.txt`.
- Stage order: `IMPROVE -> IMPROVE -> UIUX -> IMPROVE -> CHECK -> IMPROVE`.
- Prompt pack: `C:\Users\12031\Desktop\AGENT_PROMPTS_MAIN_PACK`; `AGENT_IMPROVE_MAIN.txt`, `AGENT_UIUX_MAIN.txt`, and `AGENT_CHECK_MAIN.txt` were readable.
- Start state: `main`, clean worktree, `origin/main` up to date after `git fetch --prune` and `git pull --ff-only`.
- CI workflow: `.github/workflows/deploy-pages.yml` runs Python dependency install, unit tests, compileall, static Pages validation, then Wrangler Pages deploy.
- Project shape: Python static Dota review generator; no `package.json`; validation commands are Python/unit/static-site based.
- Carry-over direction from the last iteration: no urgent summary-UI gap remained; future work should focus on deeper match data ingestion rather than more summary UI.
- Constraints: do not touch Docker; do not edit `AGENTS.md`; stay on `main`; no force push; no branch creation.

## 2026-06-30 - Long Cycle 3 Stage 1 IMPROVE - Start

- Stage: 1 / 6
- Type: IMPROVE
- Prompt: AGENT_IMPROVE_MAIN.txt
- Goal: convert STRATZ playback `csEvents` into a deterministic minute-level lane timeline when regular minute arrays are missing.
- Carry-over: this directly advances the deeper real-data ingestion direction from the prior cycle.
- User-visible increment: reports can still show 10-minute last hits, phase LH/min, and low-efficiency windows from real playback CS events instead of falling back to missing-data caveats.
- Start state: main at `chore: record stage 6 evidence deployment` (`f3e80e5`), clean worktree, origin/main up to date.

## 2026-06-30 - Long Cycle 3 Stage 1 IMPROVE - Local Complete

- Completed: added STRATZ playback `csEvents` lane-timeline derivation when OpenDota logs and STRATZ minute arrays do not include LH/min arrays.
- User-visible increment: affected reports now show 10-minute LH, phase LH/min, low-efficiency windows, and a visible `时间线来源：STRATZ补刀事件` label from real playback events.
- Data-quality increment: `data_quality.available` now records `stratz_playback_cs` when that evidence source powers the timeline.
- Local verification:
  - New target tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 61 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Pending: commit, push, GitHub Actions, and custom-domain acceptance for Stage 1.

## 2026-06-30 - Long Cycle 3 Stage 1 IMPROVE - Complete

- Completed stage: 1 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Stage commit: `feat: derive lane timeline from playback cs` (`81f79ef`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28388235464`.
- Production acceptance: `https://dota.custard.top/` returned 200; `site-manifest.json` returned 200 with report_count=10 and latest `Legion Commander #8870219537`.
- Remaining risk: STRATZ playback CS evidence only supplies real last-hit timing unless other minute arrays are also available.
- Next stage: Stage 2 IMPROVE.

## 2026-06-30 - Long Cycle 3 Stage 2 IMPROVE - Start

- Stage: 2 / 6
- Type: IMPROVE
- Prompt: AGENT_IMPROVE_MAIN.txt
- Goal: enrich death events with real STRATZ `playerUpdatePositionEvents` samples.
- Carry-over: Stage 1 improved lane timing from playback data; the next coaching gap is knowing where deaths occurred, not just the minute.
- User-visible increment: death findings can cite exact sampled x/y positions near each death when STRATZ playback provides them.
- Start state: main at `chore: record stage 1 playback timeline deployment` (`98a96da`), clean worktree, CI passed in run `28388328621`.
- Constraints: do not touch Docker; do not edit `AGENTS.md`; use only real position samples, no inferred map location labels.

## 2026-06-30 - Long Cycle 3 Stage 2 IMPROVE - Local Complete

- Completed: normalized STRATZ `playerUpdatePositionEvents`, attached the nearest death-before position sample to each death event when the sample is within 45 seconds, and exposed those labels in death findings and AI prompt event text.
- User-visible increment: reports can now include death evidence such as `7.0分 x=122,y=140（死亡前30秒）`, making the replay target concrete without inventing map names.
- Data-quality increment: `data_quality.available` records `stratz_position_samples` when deaths have attached position evidence.
- Local verification:
  - New target test failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 62 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Pending: commit, push, GitHub Actions, and custom-domain acceptance for Stage 2.

## 2026-06-30 - Long Cycle 3 Stage 2 IMPROVE - Complete

- Completed stage: 2 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Stage commit: `feat: attach position evidence to deaths` (`14a05d7`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28388612290`.
- Production acceptance: `https://dota.custard.top/` returned 200 and included the latest report context; `site-manifest.json` returned 200 with report_count=10 and latest `Legion Commander #8870219537`.
- Remaining risk: death positions are raw sampled x/y coordinates only; the system does not infer named map regions without a verified coordinate transform.
- Next stage: Stage 3 UIUX.

## 2026-06-30 - Long Cycle 3 Stage 3 UIUX - Start

- Stage: 3 / 6
- Type: UIUX
- Prompt: AGENT_UIUX_MAIN.txt
- Goal: expose real death-position samples directly beside each death time in the HTML event section.
- Carry-over: Stage 2 attached position evidence to structured findings; this stage makes that evidence scannable without searching the coaching text.
- User-visible increment: each located death shows its minute, sampled x/y coordinate, and sample age in a compact evidence card.
- Start state: main at `chore: record stage 2 death position deployment` (`55e8c28`), clean worktree, CI passed in run `28388695806`.
- Constraints: do not touch Docker; do not edit `AGENTS.md`; do not infer named map regions.

## 2026-06-30 - Long Cycle 3 Stage 3 UIUX - Local Complete

- Completed: replaced the death-time pill row with responsive evidence cards that keep the death minute and real position sample together; deaths without a sample explicitly show `无位置采样`.
- User-visible increment: the event section now displays evidence such as `7.0分` plus `死亡位置：x=122,y=140（死亡前30秒）` in the same visual unit.
- Local verification:
  - New report-rendering test failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 63 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
  - In-app browser QA: report title matched `Anti-Mage`; event navigation reached `#match-events`; two death cards rendered at desktop and 390x844 mobile widths; no horizontal page overflow or console errors.
- Pending: commit, push, GitHub Actions, and custom-domain acceptance for Stage 3.

## 2026-06-30 - Long Cycle 3 Stage 3 UIUX - Complete

- Completed stage: 3 / 6.
- Type: UIUX.
- Prompt: AGENT_UIUX_MAIN.txt.
- Stage commit: `feat: show death position evidence in reports` (`2b87436`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28389527343`.
- Real-report refresh: regenerated the most recent 10 matches from cached STRATZ/OpenDota evidence after live STRATZ requests were blocked by Cloudflare; rebuilt `public/` from only those 10 new reports.
- Real-report acceptance: latest `Legion Commander #8870219537` contains 12 located deaths, ten visible death evidence cards, purchase timing, 10-minute last hits, and a visible timeline-source label; report title is hero-first.
- Browser acceptance: latest real report loaded with the correct title, event anchor, 10 position labels, no page-level horizontal overflow, and no console errors.
- Public corpus: `site-manifest.json` remains report_count=10 with latest `Legion Commander #8870219537`.
- Remaining risk: live STRATZ refresh is Cloudflare-blocked in this environment, so the rebuild used the already cached real playback payloads; map-region names remain intentionally uninferred.
- Next stage: Stage 4 IMPROVE.

## 2026-06-30 - Long Cycle 3 Stage 4 IMPROVE - Start

- Stage: 4 / 6
- Type: IMPROVE
- Prompt: AGENT_IMPROVE_MAIN.txt
- Goal: add visible evidence-source coverage to each generated match report.
- Carry-over: Stage 3 exposed death-position evidence; this stage makes the report say which evidence sources are available, partial, missing, or not applicable.
- User-visible increment: the player can tell whether time-line, deaths, death positions, items, fights, and vision came from OpenDota, STRATZ minute arrays, STRATZ playback, or are unavailable.
- Start state: main at `chore: publish refreshed position evidence reports` (`04e0e04`), worktree already contains the Stage 4 implementation and regenerated public reports from cached real data.
- Constraints: do not touch Docker; do not edit `AGENTS.md`; keep source labels factual and do not infer map-region names.

## 2026-06-30 - Long Cycle 3 Stage 4 IMPROVE - Local Complete

- Completed: added deterministic `data_quality.evidence_sources` rows for core stats, timeline, purchases, deaths, death positions, fight events, and vision events.
- Report UI: added `证据来源与覆盖` inside the data-quality section, with source, status, and coverage details for each major evidence type.
- User-visible increment: latest real reports now show labels such as `STRATZ位置采样` and `覆盖 12/12 次已定位死亡`, so precise coaching advice is auditable.
- Public refresh: regenerated the latest 10 cached real reports and rebuilt `public/` from exactly that report set.
- Browser verification:
  - Desktop report `Legion Commander #8870219537`: evidence-source section visible, seven rows rendered, no horizontal overflow, no clipped rows, and no console warnings/errors.
  - Mobile 390x844: evidence-source rows remained visible without horizontal overflow.
- Local verification:
  - New target tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 66 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Pending: commit, push, GitHub Actions, custom-domain acceptance, and Stage 4 closeout log.

## 2026-06-30 - Long Cycle 3 Stage 4 IMPROVE - Complete

- Completed stage: 4 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Stage commit: `feat: show report evidence source coverage` (`0353345`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28391147465`.
- Production acceptance: `https://dota.custard.top/Legion_Commander_8870219537_20260630_032336.html` returned 200 and contained hero-first title, `证据来源与覆盖`, `STRATZ位置采样`, `覆盖 12/12 次已定位死亡`, and timeline-source text.
- Remaining risk: evidence source coverage reports factual source availability; STRATZ live refresh is still Cloudflare-blocked in this environment, so public refresh used cached real payloads.
- Next stage: Stage 5 CHECK.

## 2026-06-30 - Long Cycle 3 Stage 5 CHECK - Start

- Stage: 5 / 6
- Type: CHECK
- Prompt: AGENT_CHECK_MAIN.txt
- Goal: harden static Pages validation so report pages cannot ship without visible evidence-source coverage.
- Risk found: Stage 4 added `证据来源与覆盖` to reports, but the generated-site checker still only required older report sections; a future template regression could drop source coverage while CI stayed green.
- Start state: main at `chore: record stage 4 evidence coverage deployment` (`e108a04`), clean worktree, CI passed in run `28391242756`.
- Constraints: do not touch Docker; do not edit `AGENTS.md`; keep CHECK diff focused on validation and regression tests.

## 2026-06-30 - Long Cycle 3 Stage 5 CHECK - Local Complete

- Completed: added `_find_report_evidence_source_issues()` and wired it into `scripts/check_public_site.py`.
- Real risk fixed: report pages now fail static validation if they are missing `证据来源与覆盖`, evidence-source list/row hooks, or core source rows for stats, timeline, purchases, deaths, and death positions.
- Regression coverage: new CHECK test failed before implementation because the checker had no evidence-source validation helper, then passed after the fix.
- Local verification:
  - Target CHECK test failed before implementation, then passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 67 tests.
  - `python -m compileall -q .`: passed.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Pending: commit, push, GitHub Actions, custom-domain acceptance, and Stage 5 closeout log.

## 2026-06-30 - Long Cycle 3 Stage 5 CHECK - Complete

- Completed stage: 5 / 6.
- Type: CHECK.
- Prompt: AGENT_CHECK_MAIN.txt.
- Stage commit: `fix: require report evidence coverage in static checks` (`c864f15`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28391396819`.
- Production acceptance: latest `Legion Commander #8870219537` report returned 200 with `证据来源与覆盖`, seven evidence-source rows, and `覆盖 12/12 次已定位死亡`.
- Remaining risk: the static validator checks visible evidence-source labels, not semantic correctness of every source row; semantic correctness is covered by analyzer tests.
- Next stage: Stage 6 IMPROVE.

## 2026-06-30 - Long Cycle 3 Stage 6 IMPROVE - Start

- Stage: 6 / 6
- Type: IMPROVE
- Prompt: AGENT_IMPROVE_MAIN.txt
- Goal: cross-reference deaths with low-efficiency windows so reports show where real deaths interrupted resource flow.
- Carry-over: Stage 5 recommended adding deterministic timing links between death events and low-resource windows.
- User-visible increment: reports can show `死亡打断资源窗口` with exact low-efficiency windows and death minutes.
- Start state: main at `chore: record stage 5 evidence validation deployment` (`5cd06b9`), clean worktree, CI passed by public Actions API for run `28391486168`.
- Constraints: do not touch Docker; do not edit `AGENTS.md`; use only death times and minute timeline windows, no inferred map regions or blame.

## 2026-06-30 - Long Cycle 3 Stage 6 IMPROVE - Local Complete

- Completed: added deterministic `timeline.death_overlap_windows` by matching death minutes against low-efficiency windows.
- Report UI: added `死亡打断资源窗口` under 时间线诊断 when overlap evidence exists.
- Coaching findings: added high-priority `死亡打断资源` findings when deaths and low-efficiency windows overlap, with an exact action to recover one safe wave/resource pocket before rejoining risky map movement.
- Public refresh: live STRATZ detail fetch succeeded for the latest 10 matches, then `public/` was rebuilt from exactly those 10 newly generated reports.
- Real-report acceptance: latest `Legion Commander #8870219537` now shows three overlap windows, including `低效率窗口 25-27分钟含 25.3分死亡` and `低效率窗口 32-36分钟含 32.2分死亡、33.8分死亡`.
- Browser verification:
  - Desktop latest report: title correct, nonblank, `死亡打断资源窗口` visible, three overlap rows, no horizontal overflow, no console warnings/errors.
  - Mobile 390x844: same three overlap rows visible, no horizontal overflow, no console warnings/errors.
- Local verification:
  - New target tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 69 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Pending: commit, push, GitHub Actions, custom-domain acceptance, and final closeout logs.

## 2026-06-30 - Long Cycle 3 Stage 6 IMPROVE - Complete

- Completed stage: 6 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Stage commit: `feat: cross reference deaths with low efficiency windows` (`30bc9c8`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28391972379`.
- Production acceptance: `https://dota.custard.top/Legion_Commander_8870219537_20260630_034916.html` returned 200 and contained hero-first title, `死亡打断资源窗口`, `低效率窗口 25-27分钟含 25.3分死亡`, `低效率窗口 32-36分钟含 32.2分死亡、33.8分死亡`, and `证据来源与覆盖`.
- Remaining risk: overlap diagnosis is strictly time-based; it does not infer the cause of the death or named map region.
- Final state: all six requested Long Cycle 3 stages are complete, pushed to `main`, CI-passed, and custom-domain checked.

## 2026-06-30 - Long Cycle 3 - Final Status

- Completed stages: 6 / 6.
- Stage commits:
  - Stage 1: `feat: derive lane timeline from playback cs` (`81f79ef`).
  - Stage 2: `feat: attach position evidence to deaths` (`14a05d7`).
  - Stage 3: `feat: show death position evidence in reports` (`2b87436`) plus public refresh `04e0e04`.
  - Stage 4: `feat: show report evidence source coverage` (`0353345`).
  - Stage 5: `fix: require report evidence coverage in static checks` (`c864f15`).
  - Stage 6: `feat: cross reference deaths with low efficiency windows` (`30bc9c8`).
- Final local gates: 69 tests, compileall, static Pages validation, gitleaks, diff check, forbidden-file check, and desktop/mobile report browser QA passed.
- Final CI state: last feature deployment run `28391972379` passed; final log closeout pending at the time of this entry.
- Final production state: custom domain serves latest hero-first reports with event-level death positions, evidence-source coverage, and death/resource overlap windows.
- Remaining risks:
  - Death positions remain raw x/y samples until a verified Dota map transform exists.
  - Death/resource overlap is time-based only and intentionally does not infer death cause.
  - Public reports are static until the next fetch/build/deploy cycle.
- Recommended next flagship change: add a verified Dota map coordinate transform before converting raw x/y samples into named map-region guidance.

## 2026-06-30 - Long Cycle 4 Stage 5 CHECK - Start

- Stage: 5 / 6
- Type: CHECK
- Prompt: AGENT_CHECK_MAIN.txt
- Goal: harden static Pages validation around the complete death-review experience and its site-level coverage counters.
- Risk found: Stage 4 exposed death-review coverage on the history page, but CI did not specifically require the report workbench, recovery section, mobile phase cards, overview panel, or internally consistent manifest counters.
- Start state: main at `chore: record stage 4 coverage deployment` (`578898c`), clean worktree, CI passed in run `28407017928`.
- Constraints: do not touch Docker; do not edit `AGENTS.md`; keep CHECK changes limited to validation, tests, and execution logs.

## 2026-06-30 - Long Cycle 4 Stage 5 CHECK - Local Complete

- Completed: added `_find_death_review_coverage_issues()` and wired it into `scripts/check_public_site.py`.
- Report gates: every report must retain `death-review-workbench`, `death-review-summary`, `死亡后恢复窗口`, and mobile `timeline-phase-cards`.
- Site gates: the history page must retain `死亡复盘覆盖`; the manifest must expose all four death-review counters and each count must equal evidence parsed from the current report set.
- Regression coverage: the new CHECK test failed before implementation because the helper did not exist, then passed after the validation was added.
- Local verification:
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 76 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Pending: commit, push, GitHub Actions, custom-domain acceptance, and Stage 5 closeout log.

## 2026-06-30 - Long Cycle 4 Stage 5 CHECK - Complete

- Completed stage: 5 / 6.
- Type: CHECK.
- Prompt: AGENT_CHECK_MAIN.txt.
- Stage commit: `fix: validate death review coverage` (`47920b9`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28407553060`; unit tests, compile, static Pages validation, and Cloudflare deployment all succeeded.
- Production acceptance: `https://dota.custard.top/` and `site-manifest.json` returned 200; the history page contained `死亡复盘覆盖`, and live counters matched the 10-report set at 10 workbenches, 10 recovery reports, 9 coordinate maps, and 9 complete death reviews.
- Remaining risk: post-death rows show exact recovery totals but do not compare the same player's resource pace immediately before and after each death.
- Next stage: Stage 6 IMPROVE will add deterministic death-adjacent resource deltas from real minute arrays.

## 2026-06-30 - Long Cycle 4 Stage 6 IMPROVE - Start

- Stage: 6 / 6
- Type: IMPROVE
- Prompt: AGENT_IMPROVE_MAIN.txt
- Goal: compare each real death's preceding resource pace with the immediate post-death pace using only observed minute arrays.
- Carry-over: Stage 5 confirmed every report exposes recovery windows, but those absolute post-death totals do not show how sharply the same player's pace changed around the death.
- User-visible increment: add `死亡前后资源变化` with exact before/after LH per minute, average GPM, and signed deltas for each supported death event.
- Start state: main at `chore: record stage 5 death coverage validation` (`740a024`), clean worktree, CI passed in run `28407613769`.
- Constraints: do not touch Docker; do not edit `AGENTS.md`; do not infer causality, benchmark quality, or map regions from the deltas.

## 2026-06-30 - Long Cycle 4 Stage 6 IMPROVE - Local Complete

- Completed: added deterministic `timeline.death_resource_deltas` by comparing each death's preceding resource pace with the immediate post-death pace using real `lastHitsPerMinute` and `goldPerMinute` arrays.
- Boundary fix found by reading the real report: fractional-minute deaths now skip the mixed event minute, so `13.6分死亡` compares `10-13分钟` to `14-17分钟` instead of contaminating the post window with minute 13.
- Coaching findings: added `死亡前后资源变化` findings when a real death-adjacent window has a meaningful LH/min or GPM drop; evidence includes exact signed before/after deltas and explicitly says the system does not judge death cause.
- Report UI: added `死亡前后资源变化` under 时间线诊断 with exact before/after windows, signed deltas, and a no-causality caveat.
- Static-site fix found during final validation: custom Chinese training topics now use hashed practice checklist IDs, fixing duplicate `practice-custom-*` IDs in `practice-plan.html`.
- Public refresh: regenerated the full 18-report history from real STRATZ details and rebuilt `public/`; the manifest now reports 18 reports, 48 findings, 18 death workbenches, 18 recovery reports, 17 coordinate maps, and 17 complete death reviews.
- Real-report acceptance: latest `Legion Commander #8870219537` report `Legion_Commander_8870219537_20260630_091309.html` has hero-first title, `死亡前后资源变化`, high-priority `死亡前后资源变化` finding, and exact evidence such as `25.3分死亡前后：补刀/分 8.7→3.3（-5.4）` and `30.4分死亡（27-30分钟 → 31-34分钟）`.
- Browser verification:
  - Desktop history page: 18-report manifest, `死亡复盘覆盖`, no duplicate IDs, no horizontal overflow.
  - Desktop latest report: hero-first title, exact delta evidence, `不判断死亡原因` caveat, no duplicate IDs, no horizontal overflow.
  - Desktop practice plan: `死亡前后资源变化` topic present and custom checklist IDs unique.
  - Mobile 390x844 report/practice plan: no horizontal overflow; report shows mobile phase cards and hides the desktop phase table.
- Local verification:
  - New target tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 81 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 18 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Pending: commit, push, GitHub Actions, custom-domain acceptance, and Stage 6 closeout log.

## 2026-06-30 - Long Cycle 4 Stage 6 IMPROVE - Complete

- Completed stage: 6 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Stage commit: `feat: add death resource delta diagnostics` (`ee2fef0`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28409150631`; unit tests, compile, static Pages validation, and Cloudflare deployment all succeeded.
- Production acceptance:
  - `https://dota.custard.top/` returned 200 and contained `死亡复盘覆盖` plus `死亡前后资源变化`.
  - `site-manifest.json` returned 18 reports, 48 findings, 18 death workbenches, 18 recovery reports, 17 coordinate maps, and 17 complete death reviews.
  - `https://dota.custard.top/Legion_Commander_8870219537_20260630_091309.html` returned 200 with hero-first title, `死亡前后资源下降窗口`, `25.3分死亡前后：补刀/分 8.7→3.3（-5.4）`, `30.4分死亡（27-30分钟 → 31-34分钟）`, and `不判断死亡原因`.
  - `practice-plan` returned 200 with `死亡前后资源变化` and hashed custom checklist IDs such as `practice-custom-0568eadc6b-1`.
- Remaining risk: the delta diagnosis intentionally describes adjacent resource changes only; it does not infer why each death happened, and raw death x/y coordinates remain untranslated until a verified Dota map transform exists.
- Final state: all six requested Long Cycle 4 stages are complete, pushed to `main`, CI-passed, and custom-domain checked.

## 2026-06-30 - Long Cycle 4 - Final Status

- Completed stages: 6 / 6.
- Stage commits:
  - Stage 1: `feat: add raw death coordinate map` (`28ebbd8`) plus log deploy `d98f64e`.
  - Stage 2: `feat: add death recovery diagnostics` (`8391fa8`) plus log deploy `ebc02cb`.
  - Stage 3: `feat: improve mobile death review UI` (`e238bca`) plus log deploy `6eaed03`.
  - Stage 4: `feat: surface death review coverage` (`eeb8502`) plus log deploy `578898c`.
  - Stage 5: `fix: validate death review coverage` (`47920b9`) plus log deploy `740a024`.
  - Stage 6: `feat: add death resource delta diagnostics` (`ee2fef0`).
- Final local gates: 81 tests, compileall, static Pages validation, gitleaks, diff check, forbidden-file check, and desktop/mobile browser QA passed.
- Final CI state: feature deployment run `28409150631` passed; final log closeout deployment pending at the time of this entry.
- Final production state: custom domain serves latest hero-first 18-report history with raw death coordinate maps where available, recovery windows, death-adjacent resource deltas, death-review coverage counters, trend pages, and a practice plan.
- Remaining risks:
  - Death positions remain raw x/y samples until a verified Dota map transform exists.
  - Death-adjacent deltas are exact adjacent resource comparisons, not causal labels.
  - Public reports are static until the next fetch/build/deploy cycle.
- Recommended next flagship change: add a verified Dota map coordinate transform and objective-event overlays before giving named-map-region death advice.

## 2026-06-30 - Short Cycle Stage 1 IMPROVE - Start

- Stage: 1 / 2.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Goal: advance the map-position evidence direction without inventing named map regions by detecting repeated death coordinate clusters from real STRATZ x/y samples and turning them into visible report evidence plus coach findings.
- Carry-over: previous recommended flagship change was a verified Dota map coordinate transform and objective overlays; this stage takes the safe first step by making repeated raw-coordinate danger patterns auditable before any region naming.
- User-visible increment: reports should show repeated death coordinate clusters on top of the existing death coordinate map, with exact minutes and raw centers.
- Start state: main at `chore: record stage 6 delta deployment` (`d3e4a32`), clean worktree, `git pull --ff-only` already up to date.
- Constraints: do not touch Docker; do not edit `AGENTS.md`; do not infer death causes or named map regions from raw x/y coordinates.

## 2026-06-30 - Short Cycle Stage 1 IMPROVE - Local Complete

- Completed: added deterministic repeated death coordinate clustering from real STRATZ raw x/y death-position samples.
- Report UI: the death coordinate map now draws cluster rings, adds a `重复死亡坐标簇` evidence block, and exposes a fourth workbench count for repeated clusters.
- Coaching findings: added `重复死亡坐标` findings with exact minutes, raw cluster centers, sample count, and an explicit caveat that the system does not convert raw coordinates into map-region names.
- Public refresh: regenerated 18 reports from real STRATZ details and rebuilt `public/`.
- Real-report acceptance: latest `Legion Commander #8870219537` report `Legion_Commander_8870219537_20260630_094728.html` shows two repeated coordinate clusters: `22.7、33.8分` centered at `x=137.0,y=129.0`, and `25.3、43.5分` centered at `x=125.0,y=72.0`.
- Site-level acceptance: `review-trends.json` now has a `重复死亡坐标` topic with 14 reports/findings, and the training plan includes the new topic.
- Browser verification:
  - Desktop history/report/topic/practice pages: no duplicate IDs, no horizontal overflow, no console warnings/errors.
  - Mobile 390x844 latest report/practice plan: repeated cluster rows are readable, no horizontal overflow, no console warnings/errors.
- Local verification:
  - New target tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 83 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 18 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Pending: commit, push, GitHub Actions, custom-domain acceptance, and Stage 1 closeout log.

## 2026-06-30 - Long Cycle 5 Stage 1 IMPROVE - Complete

- Completed stage: 1 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Stage commit: `feat: add verified objective event timeline` (`fa0fe6a`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28419477448`; unit tests, compile, static Pages validation, credential validation, and deployment all succeeded.
- Production acceptance: `https://dota.custard.top/` and the 18-report manifest returned 200; latest Legion Commander report returned 200 with a hero-first title, 19 objective rows, exact 44.1-minute Roshan loss, and `OpenDota目标事件` source coverage.
- Remaining risk: the timeline proves event order and ownership but does not yet connect deaths or item timings to nearby objectives.
- Next stage: Stage 2 IMPROVE will add exact death-to-objective temporal windows without claiming causality.

## 2026-06-30 - Long Cycle 5 Stage 2 IMPROVE - Start

- Stage: 2 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Goal: cross-reference each observed death with verified objective losses in the following 90 seconds and turn those exact windows into measurable coaching evidence.
- Carry-over: Stage 1 now proves objective event order and ownership, but the player still has to manually compare the objective timeline with twelve death timestamps.
- User-visible increment: reports will show `死亡后目标窗口` rows with death minute, objective minute, exact elapsed seconds, and the objective lost.
- Start state: `main` at `8e0525a`, clean worktree; Stage 1 feature CI `28419477448` and log-closeout CI `28419524740` passed.
- Constraints: use observed death/objective timestamps only; do not claim the death caused the objective loss; do not touch Docker or `AGENTS.md`.

## 2026-06-30 - Long Cycle 5 Stage 2 IMPROVE - Local Complete

- Completed: added deterministic `events.death_objective_windows` and summary counters by joining observed deaths to verified objective losses in the following 90 seconds.
- Coaching: added `死亡后目标损失` findings with exact death minute, objective minute, elapsed seconds, a zero-window training target, and a strict non-causality statement.
- Report UI: added `死亡后目标窗口` rows beneath the objective timeline and retained every exact event while limiting the coach finding to the first five examples.
- Real-report acceptance: latest Legion Commander report has 9 windows, including `33.8分死亡 -> 34.6分失去中路二塔（45秒）`, `38.0分死亡 -> 38.2分失去中路高地塔（15秒）`, and `43.5分死亡 -> 44.1分失去肉山（36秒）`.
- Browser verification: desktop 1440x1000 and mobile 390x844 rendered all 9 windows without horizontal overflow; the non-causality caveat was visible and console had 0 errors/warnings.
- Local verification:
  - New death/objective analyzer and report tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 88 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 18 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Pending: commit, push, GitHub Actions, custom-domain acceptance, and Stage 2 closeout log.

## 2026-06-30 - Long Cycle 6 Stage 2 IMPROVE - Complete

- Completed stage: 2 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Stage commit: `feat: add OpenDota performance context` (`79ec340`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28437943940`; tests, compile, static validation, credential validation, and Cloudflare deployment all succeeded.
- Production acceptance:
  - `site-manifest.json` and latest report returned 200 with 18 reports and latest file `Legion_Commander_8870219537_20260630_202728.html`.
  - Live report contains `分路与参战画像`, `performance-context-grid`, 66% lane efficiency, 68% participation, 12m52s dead time / 27.7%, `OpenDota对局汇总字段`, and a hero-first title.
  - Live action ordering places `高优先级 · 死亡后目标损失` before `中优先级 · 英雄样本短板`.
- Remaining risk: the report still contains several replay-oriented raw-coordinate checks; Stage 3 should improve first-screen decision flow, while a later evidence stage should reduce remaining manual interpretation.
- Next stage: Stage 3 UIUX will make the highest-cost evidence and one executable next-match rule immediately scannable on desktop and mobile.

## 2026-06-30 - Long Cycle 5 Stage 2 IMPROVE - Complete

- Completed stage: 2 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Stage commit: `feat: connect deaths to objective losses` (`be4a85c`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28419797426`.
- Production acceptance: latest Legion Commander report returned 200 with 9 death/objective windows, the exact 15-second high-ground loss window, the non-causality caveat, and a `死亡后目标损失` finding; generated trend page `trend-custom-bac9d883f8.html` also returned 200.
- Remaining risk: long reports now contain up to dozens of objective and death rows without in-section filtering.
- Next stage: Stage 3 UIUX will turn the objective/death area into a responsive evidence workbench with meaningful filters and direct navigation.

## 2026-06-30 - Long Cycle 5 Stage 3 UIUX - Start

- Stage: 3 / 6.
- Type: UIUX.
- Prompt: AGENT_UIUX_MAIN.txt.
- Flagship goal: redesign the long objective/death evidence area as a filterable, responsive objective review workbench.
- P1 issue: latest report stacks 19 objective rows, 9 death/objective windows, and 12 death cards, so the player cannot quickly isolate gained, lost, or direct-participation events.
- Planned companion improvements: unified in-section jump navigation, live filter counts/status, stronger gained/lost row hierarchy, visible keyboard focus, and a touch-friendly 390px layout.
- Start state: `main` at `bfe8cc4`, clean worktree; Stage 2 feature CI `28419797426` and log-closeout CI `28419847100` passed.
- Constraints: UI/UX scope only except test support; preserve all evidence and non-causality text; do not touch Docker or `AGENTS.md`.

## 2026-06-30 - Long Cycle 5 Stage 3 UIUX - Local Complete

- Completed: converted the objective/death event area into an `objective-review-workbench` with in-section anchors, objective filters for all/gained/lost/direct, live status text, and gained/lost row hierarchy.
- Real-report acceptance: latest `Legion Commander #8870219537` report is `Legion_Commander_8870219537_20260630_142543.html`; it renders 19 objective events, 9 death/objective windows, exact 15-second high-ground evidence, and an OpenDota source caveat.
- Browser verification:
  - Desktop latest report: hero-first title, objective workbench visible, filter clicked from all to lost, status changed to `我方失去：15/19 条目标事件`, gained rows hidden, no console errors.
  - Mobile 390x844: `scrollWidth=390`, objective rows fit within 314px, toolbar/filter controls wrap into stable two-column touch targets, no console errors; screenshot saved under ignored `output/playwright/`.
- Local verification:
  - New UIUX target test failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 88 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 18 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Pending: commit, push, GitHub Actions, custom-domain acceptance, and Stage 3 closeout log.

## 2026-06-30 - Long Cycle 5 Stage 3 UIUX - Complete

- Completed stage: 3 / 6.
- Type: UIUX.
- Prompt: AGENT_UIUX_MAIN.txt.
- Stage commit: `feat: add objective event workbench` (`ebfeb95`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28420439204`; unit tests, compile, static Pages validation, credential validation, and Cloudflare deployment all succeeded.
- Production acceptance:
  - `site-manifest.json` returned 18 reports, 70 findings, 10 topics, and latest report `Legion_Commander_8870219537_20260630_142543.html`.
  - Latest Legion Commander report returned 200 with hero-first title, `objective-review-workbench`, lost-event filter, `data-objective-filtering`, exact `相隔15秒` death/objective window, and `来源：OpenDota 目标事件`.
  - `trend-custom-bac9d883f8.html`, `index.html`, and `practice-plan.html` returned 200 with `死亡后目标损失`.
- Remaining risk: the workbench improves scanning and filtering only; death/objective windows remain temporal evidence and intentionally do not assign causality.
- Next stage: Stage 4 IMPROVE should add a deterministic post-objective coaching target that converts the new objective/death evidence into one explicit next-match drill.

## 2026-06-30 - Long Cycle 5 Stage 4 IMPROVE - Start

- Stage: 4 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Goal: convert verified death/objective windows into one deterministic next-match drill, so the report does more than list evidence.
- Planned user-visible increment: add a `目标前90秒生存规则` card and wire the same drill into the `death_objective_window` finding action, training goal, and success metric.
- Start state: `main` at `034427c`, clean worktree; Stage 3 feature CI `28420439204` and log-closeout CI `28420564258` passed.
- Constraints: use only real OpenDota objective/death event windows; keep non-causality caveat; do not touch Docker or `AGENTS.md`.

## 2026-06-30 - Long Cycle 5 Stage 4 IMPROVE - Local Complete

- Completed: added deterministic `death_objective_drill` generation from verified death/objective windows and wired the same drill into `death_objective_window` finding action, training goal, success metric, and replay check.
- Report UI: added `目标前90秒生存规则` drill card under `死亡后目标窗口`, with trigger, execution rule, success metric, and priority replay evidence.
- Real-report acceptance: latest `Legion Commander #8870219537` report is `Legion_Commander_8870219537_20260630_144813.html`; it shows the drill, `处理基地防守`, `优先回看: 45.5分死亡 → 46.5分失去遗迹（54秒）`, and `死亡后90秒内失去目标窗口=0`, with no `接失去` wording.
- Browser verification:
  - Desktop latest report: hero-first title, drill card visible, drill width 1032px, no console errors.
  - Mobile 390x844: `scrollWidth=390`, drill card width 314px, no console errors; screenshot saved under ignored `output/playwright/`.
- Local verification:
  - New drill tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 88 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 18 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Pending: commit, push, GitHub Actions, custom-domain acceptance, and Stage 4 closeout log.

## 2026-06-30 - Long Cycle 5 Stage 4 IMPROVE - Complete

- Completed stage: 4 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Stage commit: `feat: add objective survival drill` (`345b089`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28421148889`; unit tests, compile, static Pages validation, credential validation, and Cloudflare deployment all succeeded.
- Production acceptance:
  - `site-manifest.json` returned 18 reports, 70 findings, 10 topics, and latest report `Legion_Commander_8870219537_20260630_144813.html`.
  - Latest Legion Commander report returned 200 with `目标前90秒生存规则`, `处理基地防守`, `死亡后90秒内失去目标窗口=0`, and exact replay evidence `45.5分死亡 → 46.5分失去遗迹（54秒）`.
  - Live report no longer contains the awkward `接失去` wording.
- Remaining risk: the drill is still a prevention rule from temporal evidence; it does not claim the death caused the objective loss.
- Next stage: Stage 5 CHECK should audit generated report text and static validation for remaining awkward or unverifiable coaching wording.

## 2026-06-30 - Long Cycle 5 Stage 5 CHECK - Start

- Stage: 5 / 6.
- Type: CHECK.
- Prompt: AGENT_CHECK_MAIN.txt.
- Goal: audit generated report text quality and CI validation for remaining awkward or unverifiable coaching wording.
- Start state: `main` at `5633cc0`, clean worktree; Stage 4 feature CI `28421148889` and log-closeout CI `28421331825` passed.
- Constraints: do not touch Docker or `AGENTS.md`; use automated checks plus real-report/browser acceptance; fix issues found before declaring the stage complete.

## 2026-06-30 - Long Cycle 5 Stage 5 CHECK - Local Complete

- Completed: audited generated reports for awkward objective drill wording, missing hero-first Chinese report titles, missing objective drills when death/objective windows exist, and accidental forbidden tokens.
- Fix: added `_find_report_text_quality_issues` to `scripts/check_public_site.py` and wired it into the public-site CI gate.
- Regression test: added a failing fixture for `接失去`, missing `复盘报告` in title, and missing `目标前90秒生存规则`; test failed before implementation and passed after the checker was added.
- Browser verification: latest Legion Commander report opened locally with hero-first title, `目标前90秒生存规则`, `处理基地防守`, no `接失去`, no console errors.
- Local verification:
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 89 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 18 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
- Pending: commit, push, GitHub Actions, custom-domain acceptance, and Stage 5 closeout log.

## 2026-06-30 - Long Cycle 5 Stage 5 CHECK - Complete

- Completed stage: 5 / 6.
- Type: CHECK.
- Prompt: AGENT_CHECK_MAIN.txt.
- Stage commit: `test: enforce report text quality` (`6ea8025`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28421523540`; unit tests, compile, enhanced static Pages validation, credential validation, and Cloudflare deployment all succeeded.
- Production acceptance:
  - `site-manifest.json` returned 18 reports and latest report `Legion_Commander_8870219537_20260630_144813.html`.
  - Latest Legion Commander report returned 200 with `目标前90秒生存规则`, `处理基地防守`, `复盘报告`, and without `接失去`.
- Remaining risk: the new static text checker catches known bad patterns and required drill coverage, not every possible awkward sentence.
- Next stage: Stage 6 IMPROVE should make one final evidence-backed product improvement and complete the full 6-stage cycle.

## 2026-06-30 - Long Cycle 5 Stage 6 IMPROVE - Start

- Stage: 6 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Goal: make the objective survival drill more actionable by turning the replay prompt into concrete replay checkpoints.
- Planned user-visible increment: show three deterministic `目标前90秒` replay checklist items: teammate support, enemy control visibility, and retreat route.
- Start state: `main` at `6a9255d`, clean worktree; Stage 5 feature CI `28421523540` and log-closeout CI `28421571374` passed.
- Constraints: do not touch Docker or `AGENTS.md`; keep all checkpoint text tied to the existing death/objective evidence and avoid cause claims.

## 2026-06-30 - Short Cycle Stage 1 IMPROVE - Complete

- Completed stage: 1 / 2.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Stage commit: `feat: surface repeated death coordinate clusters` (`130228e`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28410448019`; unit tests, compile, static Pages validation, and Cloudflare deployment all succeeded.
- Production acceptance:
  - `site-manifest.json` returned 18 reports, 60 findings, 9 topics, and latest report `Legion_Commander_8870219537_20260630_094728.html`.
  - Latest Legion Commander report returned 200 with hero-first title, `重复死亡坐标簇`, `中心x=137.0,y=129.0`, `中心x=125.0,y=72.0`, and `不转换成地图区域名`.
  - `trend-custom-97ad93fe24.html` returned 200 with `重复死亡坐标` evidence; `practice-plan.html` includes the new topic.
- Remaining risk: repeated coordinate clusters still require replay confirmation and do not name map regions or infer death causes.
- Next stage: Stage 2 UIUX should make the long match report evidence area faster to scan, especially the death/event evidence workbench on mobile.

## 2026-06-30 - Short Cycle Stage 2 UIUX - Start

- Stage: 2 / 2.
- Type: UIUX.
- Prompt: AGENT_UIUX_MAIN.txt.
- Goal: upgrade the long report death/event evidence area into a faster-scanning death review workspace, with repeated-coordinate deaths visibly highlighted and mobile-friendly in-section navigation.
- Carry-over: Stage 1 surfaced repeated coordinate evidence, but the death list still makes users manually connect individual death cards with cluster evidence.
- User-visible increment: death cards that belong to repeated coordinate clusters should be visibly marked, and the death section should provide direct jump controls to the list, coordinate map, and cluster evidence.
- Start state: main at `chore: record stage 1 coordinate cluster deployment` (`5c1de61`), clean worktree, Stage 1 CI passed in run `28410536047`.
- Constraints: UI/UX only; do not touch Docker; do not edit `AGENTS.md`; do not invent map-region names or causal labels.

## 2026-06-30 - Short Cycle Stage 2 UIUX - Local Complete

- Completed: added stable repeated-coordinate cluster labels to death events and rendered those labels directly on matching death cards.
- Report UI: added a `death-evidence-toolbar` with direct links to `death-event-list`, `death-coordinate-map`, `death-coordinate-clusters`, and recovery windows when present.
- Mobile UX: repeated-coordinate death cards wrap cleanly, show the `重复坐标` badge, and the toolbar becomes static/touch-friendly on 390px mobile.
- Public refresh: regenerated 18 reports from cached real STRATZ details and rebuilt `public/`; the latest report is `Legion_Commander_8870219537_20260630_132753.html`.
- Real-report acceptance: latest `Legion Commander #8870219537` report shows 3 repeated-coordinate death cards, including `重复簇 #1 中心x=137.0,y=129.0` and `重复簇 #2 中心x=125.0,y=72.0`.
- Browser verification:
  - Desktop latest report: toolbar anchors present, 3 repeated-position cards, repeated-coordinate cluster section present, no horizontal overflow, no console errors.
  - Mobile 390x900: repeated death cards and labels readable, toolbar is static, no horizontal overflow, no console errors.
- Local verification:
  - New target UIUX tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 85 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 18 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Pending: commit, push, GitHub Actions, custom-domain acceptance, and final 2-stage closeout log.

## 2026-06-30 - Short Cycle Stage 2 UIUX - Complete

- Completed stage: 2 / 2.
- Type: UIUX.
- Prompt: AGENT_UIUX_MAIN.txt.
- Stage commit: `feat: improve death evidence scanning` (`ab35526`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28418442790`; unit tests, compile, static Pages validation, and Cloudflare deployment all succeeded.
- Production acceptance:
  - `site-manifest.json` returned 18 reports, 60 findings, 9 topics, and latest report `Legion_Commander_8870219537_20260630_132753.html`.
  - Latest Legion Commander report returned 200 with hero-first title, `death-evidence-toolbar`, `death-event-card repeat-position`, `重复坐标`, and exact cluster labels for centers `x=137.0,y=129.0` and `x=125.0,y=72.0`.
  - `trend-custom-97ad93fe24.html` returned 200 with `重复死亡坐标`.
- Remaining risk: repeated coordinate cards still use raw STRATZ x/y clusters only; they intentionally do not infer map-region names or death causes.
- Final state: both requested short-cycle stages are complete, pushed to `main`, CI-passed, and custom-domain checked.

## 2026-06-30 - Short Cycle - Final Status

- Completed stages: 2 / 2.
- Stage commits:
  - Stage 1: `feat: surface repeated death coordinate clusters` (`130228e`) plus log deploy `5c1de61`.
  - Stage 2: `feat: improve death evidence scanning` (`ab35526`).
- Final local gates: 85 tests, compileall, static Pages validation, gitleaks, diff check, forbidden-file check, and desktop/mobile browser QA passed.
- Final CI state: Stage 2 deployment run `28418442790` passed; final log closeout deployment pending at the time of this entry.
- Final production state: custom domain serves the 18-report history with repeated death-coordinate clusters, repeated-coordinate death-card highlighting, death-section jump controls, trend pages, and practice-plan topic coverage.
- Remaining risks:
  - Death coordinates remain raw STRATZ x/y samples until a verified Dota map transform exists.
  - Live STRATZ refresh was blocked by Cloudflare in this environment; reports regenerated from cached real STRATZ details.
  - Public reports are static until the next fetch/build/deploy cycle.
- Recommended next flagship change: add verified objective-event overlays or a verified Dota coordinate transform before producing named-map-region death advice.

## 2026-06-30 - Long Cycle 5 Stage 1 IMPROVE - Start

- Stage: 1 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Goal: turn the real OpenDota `objectives` feed into an auditable objective timeline that distinguishes objectives gained, objectives lost, and direct player last hits.
- Carry-over: the previous cycle recommended verified objective-event overlays or a verified coordinate transform; the cache contains complete OpenDota objective feeds for all 18 current reports, so objective evidence is the higher-confidence path.
- User-visible increment: reports will show exact tower, barracks, Roshan, and Aegis times with team outcome and direct-participation labels.
- Start state: `main` at `da328bc`, clean and synchronized with `origin/main`; latest `Deploy Cloudflare Pages` run `28418555643` passed.
- Constraints: do not touch Docker or `AGENTS.md`; use only observed OpenDota event fields; do not infer objective causes or named map regions.

## 2026-06-30 - Long Cycle 5 Stage 1 IMPROVE - Local Complete

- Completed: normalized real OpenDota tower, barracks, Ancient, Roshan, Aegis, and Tormentor events into `events.objectives`, with exact minutes, team outcome, and direct player event markers.
- Report UI: added `目标事件时间线`, a four-metric objective summary, exact gained/lost rows, and an explicit source/attribution caveat.
- Data quality: reports now expose `地图目标事件` as a separately auditable OpenDota evidence source and name the gap when objective data is absent.
- Real-report acceptance: latest `Legion Commander #8870219537` contains 19 objective events: 4 gained, 15 lost, and 0 direct player event markers; exact evidence includes 10.7-minute bottom tier-one loss, 19.4/44.1-minute Roshan and Aegis losses, and 38.5-minute middle melee barracks loss.
- Browser verification: desktop 1440x1000 and mobile 390x844 rendered all 19 rows without horizontal overflow; console had 0 errors and 0 warnings.
- Local verification:
  - New objective analyzer and report tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 87 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 18 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Pending: commit, push, GitHub Actions, custom-domain acceptance, and Stage 1 closeout log.

## 2026-06-30 - Long Cycle 5 Stage 6 IMPROVE - Local Complete

- Completed: added a deterministic `目标前90秒` replay checklist to `death_objective_drill` so the report now gives three concrete checks before a major objective window: teammate support, enemy control visibility, and retreat route.
- Report UI: rendered the checklist inside the objective drill card with responsive desktop/mobile layout.
- Public refresh: regenerated 18 real reports and rebuilt `public/`; latest report is `Legion_Commander_8870219537_20260630_151304.html`.
- Real-report acceptance: latest Legion Commander report contains `目标前90秒生存规则`, `队友接应`, `敌方控制`, `撤退路线`, and no `接失去`.
- Browser verification: Chromium desktop 1440x1000 and mobile 390x844 loaded the latest report with the three checklist labels, no horizontal overflow, and 0 console messages.
- Local verification:
  - New target tests failed first with missing `checklist`, then passed after implementation.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 89 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 18 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Pending: commit, push, GitHub Actions, custom-domain acceptance, and full 6-stage closeout log.

## 2026-06-30 - Long Cycle 5 Stage 6 IMPROVE - Complete

- Completed stage: 6 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Stage commit: `feat: add objective replay checklist` (`6903742`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28422200529`; unit tests, compile, static Pages validation, credential validation, and Cloudflare deployment all succeeded.
- Production acceptance:
  - `site-manifest.json` returned 18 reports and latest report `Legion_Commander_8870219537_20260630_151304.html`.
  - Latest Legion Commander report returned 200 with `目标前90秒生存规则`, `队友接应`, `敌方控制`, `撤退路线`, `复盘报告`, and without `接失去`.
- Remaining risk: the checklist is a replay rubric tied to temporal objective evidence; it does not claim the death caused the objective loss.

## 2026-06-30 - Long Cycle 5 - Final Status

- Completed stages: 6 / 6.
- Stage commits:
  - Stage 1: `feat: add verified objective event timeline` (`fa0fe6a`) plus log deploy `8e0525`.
  - Stage 2: `feat: connect deaths to objective losses` (`be4a85c`) plus log deploy `bfe8cc4`.
  - Stage 3: `feat: add objective event workbench` (`ebfeb95`) plus log deploy `034427c`.
  - Stage 4: `feat: add objective survival drill` (`345b089`) plus log deploy `5633cc0`.
  - Stage 5: `test: enforce report text quality` (`6ea8025`) plus log deploy `6a9255d`.
  - Stage 6: `feat: add objective replay checklist` (`6903742`).
- Final local gates: 89 tests, compileall, static Pages validation, gitleaks, diff check, forbidden-file check, and desktop/mobile browser QA passed.
- Final CI state: Stage 6 deployment run `28422200529` passed; final log closeout deployment pending at the time of this entry.
- Final production state: custom domain serves the 18-report history with verified objective timelines, death/objective windows, filterable objective workbench, objective survival drill, three-point replay checklist, trend pages, and static text quality gates.
- Remaining risks:
  - Death/objective relationships remain temporal evidence unless replay/video confirms causality.
  - Report coordinate evidence remains raw STRATZ x/y samples until a verified Dota map transform exists.
  - Future richer combat/vision advice depends on STRATZ/OpenDota exposing reliable event fields for those dimensions.
- Recommended next flagship change: add richer verified combat or vision event ingestion if playback fields become consistently available, then wire those fields into the same deterministic finding pipeline.

## 2026-06-30 - Long Cycle 6 Stage 1 IMPROVE - Start

- Stage: 1 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Goal: continue the previous recommendation for richer verified source data by ingesting OpenDota hero benchmark percentiles into the deterministic report pipeline.
- Planned user-visible increment: reports will show `英雄样本百分位` from OpenDota, including low/high percentile indicators and a structured finding when a metric is below the same-hero 30th percentile.
- Start state: `main` at `d87e335`, clean and synchronized with `origin/main`; latest closeout CI `28422302494` passed.
- Constraints: do not touch Docker or `AGENTS.md`; percentile data is OpenDota same-hero sample evidence, not a professional target or causal claim.

## 2026-06-30 - Long Cycle 6 Stage 1 IMPROVE - Local Complete

- Completed: normalized OpenDota `benchmarks` into `opendota_benchmarks`, sorted same-hero percentile metrics, counted strong/weak metrics, and generated `hero_benchmark_gap` findings for metrics below the 30th percentile.
- Report UI: added `英雄样本百分位` section, report navigation entry, responsive percentile cards, and explicit caveat that this is OpenDota same-hero public sample evidence rather than a professional target.
- Static validation: `scripts/check_public_site.py` now fails if a report advertises hero benchmark evidence but does not render the percentile section.
- Public refresh: regenerated 18 real reports and rebuilt `public/`; latest report is `Legion_Commander_8870219537_20260630_195426.html`.
- Real-report acceptance: latest Legion Commander report contains `英雄样本百分位`, `OpenDota英雄样本百分位`, percentiles including `第76百分位` and `第17百分位`, and no `接失去`.
- Browser verification: Chromium desktop 1440x1000 and mobile 390x844 loaded the latest report with the benchmark section, no horizontal overflow, and 0 console messages.
- Local verification:
  - New target tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 92 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 18 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Pending: commit, push, GitHub Actions, custom-domain acceptance, and Stage 1 closeout log.

## 2026-06-30 - Long Cycle 6 Stage 1 IMPROVE - Complete

- Completed stage: 1 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Stage commit: `feat: add OpenDota benchmark percentiles` (`223f76d`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28436322975`; unit tests, compile, static Pages validation, credential validation, and Cloudflare deployment all succeeded.
- Production acceptance:
  - `site-manifest.json` returned 18 reports and latest report `Legion_Commander_8870219537_20260630_195426.html`.
  - Latest Legion Commander report returned 200 with `英雄样本百分位`, `OpenDota英雄样本百分位`, `benchmark-grid`, `复盘报告`, and without `接失去`.
- Remaining risk: OpenDota percentiles are public same-hero sample comparisons only; they indicate review priority but do not replace event/replay evidence.
- Next stage: Stage 2 IMPROVE should continue by exposing another reliable OpenDota context field, with lane efficiency and teamfight participation as the best candidates.

## 2026-06-30 - Long Cycle 6 Stage 2 IMPROVE - Start

- Stage: 2 / 6.
- Type: IMPROVE.
- Prompt: AGENT_IMPROVE_MAIN.txt.
- Goal: turn OpenDota lane efficiency, teamfight participation, total dead time, and buyback count into source-backed coaching evidence instead of leaving them hidden in cached JSON.
- Start state: `main` at `9882f26`, clean and synchronized with `origin/main`; Stage 1 closeout CI `28436830771` passed.
- Constraints: do not touch Docker or `AGENTS.md`; aggregate fields may establish measured values and transparent training thresholds, but must not invent causal explanations.

## 2026-06-30 - Long Cycle 6 Stage 2 IMPROVE - Local Complete

- Completed: added `performance_context` from real OpenDota `lane_efficiency_pct`, `teamfight_participation`, `life_state_dead`, and `buyback_count` fields, including total dead-time share and average dead time per death.
- Deterministic coaching: enriched lane, map-impact, and death findings with those measured values; removed an unsupported participation-cause claim; demoted same-hero percentile gaps behind event-backed death/objective findings.
- Report UI: added responsive `分路与参战画像` cards, report navigation, source/caveat copy, and evidence-source coverage.
- Static validation: reports advertising `opendota_performance_context` must render the profile section.
- Public refresh: regenerated and rebuilt all 18 reports; latest report is `Legion_Commander_8870219537_20260630_202728.html`.
- Real-report acceptance: latest report shows 66% lane efficiency, 68% participation, 12m52s dead time (27.7%), one buyback, and now ranks death/objective evidence ahead of the 17th-percentile tower-damage hint.
- Browser verification: in-app Chromium passed 1280x720 and 390x844; navigation interaction worked, four cards rendered, no overlap or horizontal overflow, and no console warnings/errors.
- Local verification:
  - New profile, report, static-checker, no-inference wording, and priority-order tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 95 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 18 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Pending: commit, push, GitHub Actions, custom-domain acceptance, and Stage 2 closeout log.

## 2026-06-30 - Long Cycle 6 Stage 3 UIUX - Complete

- Completed: added a first-screen `上分决策卡` driven only by the highest-priority `review_findings` item, with action, evidence, validation, data coverage, and supporting-section jump links.
- Interaction/UI: added tabbed action/evidence/validation panels, `aria-live` status, visible selected/focus states, desktop evidence rail, and mobile single-column layout with 44px controls.
- Static validation: `scripts/check_public_site.py` now rejects reports with findings that do not render the decision snapshot.
- Public refresh: regenerated 18 reports and rebuilt `public/`; latest report is `Legion_Commander_8870219537_20260630_204657.html`.
- Browser verification: in-app Browser passed 1280x720 and 390x844 flows; tab switching worked, console logs were clean, and document width stayed within the viewport.
- Local verification:
  - New UI/report/checker tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 97 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 18 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Stage commit: `feat: add first-screen decision card` (`51f3dfa`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28439123263`; unit tests, compile, static Pages validation, credential validation, and Cloudflare deployment all succeeded.
- Production acceptance:
  - `site-manifest.json` returned 18 reports and latest report `Legion_Commander_8870219537_20260630_204657.html`.
  - Latest Legion Commander report returned 200 with `上分决策卡`, `decision-snapshot`, decision tabs, `分路与参战画像`, and hero-first title.
- Remaining risk: first-screen prioritization is now stronger, but richer coaching specificity still depends on reliable public event data rather than unsupported inference.
- Next stage: Stage 4 IMPROVE should add cross-match trend context so the latest decision card can be compared against repeated recent weaknesses.

## 2026-06-30 - Long Cycle 6 Stage 4 IMPROVE - Complete

- Completed: added per-report `近期同类问题` context below the decision card, generated from existing focus-trend aggregation rather than new inference.
- User-visible gain: latest Legion Commander now says the current top topic `死亡后目标损失` appears in 13 of the latest 18 reports and links to the full trend evidence page.
- Build pipeline: added `_inject_report_trend_context` after trend aggregation in `scripts/build_pages_site.py`, preserving generated report source while enhancing the public Pages output.
- Static validation: `scripts/check_public_site.py` rejects any finding-bearing report missing the trend context.
- Browser verification: in-app Browser confirmed desktop trend-link navigation to the topic workbench and mobile 390x844 single-column layout with no console warnings/errors.
- Local verification:
  - New trend-context tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 99 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 18 report pages.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Stage commit: `feat: add report trend context` (`0b58de0`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28439780094`; unit tests, compile, static Pages validation, credential validation, and Cloudflare deployment all succeeded.
- Production acceptance:
  - `site-manifest.json` returned 18 reports and latest report `Legion_Commander_8870219537_20260630_204657.html`.
  - Latest Legion Commander report returned 200 with `近期同类问题`, `最近 18 场中 13 场出现`, sample report links, and a working `trend-custom-bac9d883f8.html` full-evidence page.
- Remaining risk: trend grouping is based on report focus labels and proves repetition, not causal explanation.
- Next stage: Stage 5 CHECK should remove or gate remaining public-facing replay/manual-confirmation language where the system already has source-backed evidence.

## 2026-06-30 - Long Cycle 6 Stage 5 CHECK - Complete

- Completed: removed public-facing manual replay/confirmation wording from deterministic findings, objective drill labels, repeated-coordinate notes, support pages, trend pages, and regenerated public reports.
- Quality gate: added `_find_manual_review_language_issues` to `scripts/check_public_site.py`, scanning reports, topic pages, support pages, text exports, and `review-trends.json` for banned phrases before deploy.
- Latest public artifact: `Legion_Commander_8870219537_20260630_212154.html`.
- Local verification:
  - New manual-language tests failed before implementation and pass now.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 100 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 18 reports.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
  - Browser QA passed desktop and 390x844 mobile with clean console, no banned phrases, and no horizontal overflow.
- Stage commit: `fix: gate manual replay language in reports` (`b49b647`).
- Pushed to main: yes.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28440951874`; unit tests, compile, static Pages validation, credential validation, and Cloudflare deployment all succeeded.
- Production acceptance:
  - `site-manifest.json` returned 18 reports and latest report `Legion_Commander_8870219537_20260630_212154.html`.
  - Latest Legion Commander report returned 200 with `上分决策卡`, `近期同类问题`, `证据窗口`/`系统证据窗口`, `目标前90秒证据检查点`, and zero banned manual-review phrase hits.
- Remaining risk: `STRATZ回放事件` and `Valve回放事件` remain as source labels; this is intentional source attribution, not an instruction to manually review.
- Next stage: Stage 6 should add a final production-quality/coverage summary so report readers can immediately see current evidence coverage and quality gate status.

## 2026-07-01 - Long Cycle 6 Stage 6 IMPROVE - Local Complete

- Previous direction carried forward: expose production quality/coverage status to report readers, not just CI.
- Completed: added `quality_gate` to `site-manifest.json` and rendered `复盘质量门禁` in the shared coverage panel on the history page and practice plan.
- Quality-gate values in current public build: status `pass`, decision snapshot coverage `18/18`, trend context coverage `18/18`, evidence-source coverage `18/18`, manual-review-language hits `0`, complete-quality reports `18`.
- Static validation: `scripts/check_public_site.py` now rejects missing quality panels, missing quality-gate manifest summaries, and inconsistent quality counts.
- Browser verification: desktop and 390x844 mobile homepage QA passed with the quality panel visible, clean console, and no horizontal overflow.
- Local verification:
  - New quality-gate tests failed before implementation and pass now.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 101 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 18 reports.
  - `gitleaks dir . --redact`: passed, no leaks found.
  - `git diff --check`: passed.
- Pending: commit, push, GitHub Actions, live custom-domain acceptance, final closeout log.
