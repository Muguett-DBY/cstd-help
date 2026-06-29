# Iteration Log

## 2026-06-29 - Long Cycle Stage 5 CHECK

- Goal: harden generated-site validation around anchors, duplicate IDs, report navigation, and practice-workbench links.
- Completed: added duplicate-id detection, broken-anchor detection for both page-local and cross-page links, and stricter practice-plan workbench requirements in `scripts/check_public_site.py`.
- Real risks fixed: broken section navigation anchors, repeated IDs, or missing practice workbench controls now fail local validation and CI before Cloudflare deployment.
- Verified: new tests failed first, then 57-test suite, compileall, static site validation, gitleaks, diff check, and forbidden-file check all passed.
- Commit: `fix: harden static site validation` (`a1209cd`), pushed to `origin/main`.
- CI: passed, `Deploy Cloudflare Pages` run `28363713371`.
- Remaining risk: static validation checks local generated files only; external CDN hero image availability remains outside the gate.
- Recommended next flagship change: add a compact export/share artifact for the training plan, such as a plain-text next-session checklist generated from the same evidence data.

## 2026-06-28 - Long Cycle Stage 4 IMPROVE

- Carry-over: connect the training plan to pre-filtered evidence and action checkpoints.
- Completed: upgraded `practice-plan.html` into a training task workbench with state filters, local checkbox progress, per-topic next-game checkpoints, and evidence links for failure cases, winning samples, and the primary hero.
- User-visible gain: the player can move from "what to train" directly to filtered proof games and use the same page as a next-game execution checklist.
- Real issues fixed: practice tasks no longer point only to three example matches, and generated Pages files now use LF newlines on Windows so unchanged artifacts do not stay dirty after builds.
- Verified: target tests, 55-test suite, compileall, static site validation, gitleaks, diff check, desktop task/checklist persistence, pre-filtered evidence jump, mobile 390px rendering, and zero browser console errors.
- Commit: `feat: add practice task workbench` (`bc0a56a`), pushed to `origin/main`.
- CI: passed, `Deploy Cloudflare Pages` run `28363394164`.
- Remaining risk: checklist progress is local to one browser because the site is static.
- Recommended next flagship CHECK item: harden generated-site validation around broken anchors, duplicate IDs, report navigation targets, and practice-workbench links so static regressions fail before deploy.

## 2026-06-28 - Long Cycle Stage 3 UIUX

- Carry-over: long report pages had high-quality evidence but were slow to navigate during an actual replay review session.
- Flagship UI/UX change: upgraded each match report into a section-navigable review workspace with sticky anchors for coach summary, next actions, match data, timeline, events, findings, and items.
- Completed: added skip-to-content access, active-section feedback, stable anchor offsets, mobile horizontal navigation, a sticky return-top control, and local timeline-table scrolling.
- User-visible gain: the player can jump directly to the decision surface needed for review instead of scanning a long HTML report linearly.
- Real issues fixed: browser QA caught mobile rail centering and return-top reachability problems; both are now covered by code and style regression checks.
- Verified: 55-test suite, compileall, static site validation, gitleaks, diff check, desktop report navigation, mobile 390px navigation, no horizontal page overflow, and zero browser console errors.
- Commit: `feat: add report section navigation` (`67d2ac4`), pushed to `origin/main`.
- CI: passed, `Deploy Cloudflare Pages` run `28321347459`.
- Remaining risk: newly introduced future report sections must provide stable IDs if they should appear in the navigator.
- Recommended next flagship change: connect the training plan more directly to pre-filtered evidence and per-topic action checkpoints so the player can move from "what to train" to the exact supporting games faster.

## 2026-06-28 - Long Cycle Stage 2 IMPROVE

- Carry-over: result-only topic filters still required scanning every hero in larger recurring-problem archives.
- Completed: added an exact-hero selector, combined hero/result filtering, shareable URL state, unified clear behavior, and mobile-safe topic header/statistics layout.
- User-visible gain: a player can open or share a precise evidence slice such as one hero's losses within the death-cost topic.
- Real issue fixed: browser QA exposed narrow-screen topic content at risk of horizontal clipping; headings now wrap and statistics use a two-column mobile grid.
- Verified: target regression tests, 54-test suite, compileall, static site validation, gitleaks, desktop URL-state interaction, mobile rendering, and zero browser console errors.
- Commit: `feat: add hero filters to topic evidence` (`88b56a0`), pushed to `origin/main`.
- CI: passed, `Deploy Cloudflare Pages` run `28320739812`.
- Remaining risk: hero matching is exact by design; role-aware filtering needs trustworthy role metadata in every generated topic record.
- Recommended next flagship change: add a compact section navigator to long match reports so actions, timeline evidence, deaths, items, and findings are reachable without repeated scrolling.

## 2026-06-28 - Long Cycle Stage 1 IMPROVE

- Carry-over: topic evidence pages needed shareable URL-persisted filters after history filters were completed.
- Completed: topic evidence pages now initialize from `?result=win|lose`, update the URL with `history.replaceState`, and include a `清除筛选` button.
- User-visible gain: recurring-problem evidence views can be refreshed or shared while keeping the win/loss evidence slice.
- Real issue fixed: topic page filters were previously ephemeral and reset after refresh.
- Verified: target regression test, 54 tests, compileall, static site validation, browser URL-state flow, diff check, and gitleaks.
- Commit: `feat: persist topic evidence filters` (`bef1838`), pushed to `origin/main`.
- CI: passed, `Deploy Cloudflare Pages` run `28319963955`.
- Remaining risk: topic pages still filter by result only; hero/role/topic search would make large evidence archives faster to scan.
- Recommended next flagship change: add hero/role-aware filters to topic evidence pages and propagate those filters through shareable URLs.

## 2026-06-28 - Cycle 2 Stage 6 IMPROVE

- Carry-over: add shareable URL-persisted filters for the history page.
- Completed: history filters now initialize from `?result=...&priority=...&q=...`, update the URL with `history.replaceState`, and include a `清除筛选` button.
- User-visible gain: filtered review queues can be bookmarked, refreshed, or shared without losing context.
- Real issue fixed: previous filters were ephemeral and reset on refresh.
- Verified: browser URL-state flow, 46 tests, compileall, static site validation, diff check, and gitleaks.
- Commit: `feat: persist history filter URLs` (`46ef363`), pushed to `origin/main`.
- CI: passed, `Deploy Cloudflare Pages` run `28311817122`.
- Remaining risk: filter URLs cover match history only; topic evidence filters still reset on refresh.
- Recommended next flagship change: persist topic-page evidence filters and add hero/topic URL filters once more matches accumulate.

## 2026-06-28 - Cycle 2 Stage 5 CHECK

- Goal: audit generated Pages artifacts for stale/orphaned links and static-site consistency risks.
- Completed: added local href/src link auditing to `scripts/check_public_site.py`, made the checker importable in unit tests, and added a regression test for missing local links.
- User-visible risk fixed: broken dashboard/report/topic links now fail CI before Cloudflare deployment.
- Checks: no tracked local database, sensitive-key scan reviewed, 46 tests, compileall, static site validation, HTTP manifest check, diff check, and gitleaks.
- Browser note: the in-app browser extension blocks direct JSON navigation with `ERR_BLOCKED_BY_CLIENT`; HTTP validation confirmed `site-manifest.json` returns 200 with expected counts.
- Commit: `fix: audit generated local links` (`c86a911`), pushed to `origin/main`.
- CI: passed, `Deploy Cloudflare Pages` run `28311681379`.
- Remaining risk: static checker validates local link existence, not external CDN hero image availability.
- Recommended next flagship change: add shareable URL-persisted filters for the history page so filtered review queues can be reopened or shared.

## 2026-06-28 - Cycle 2 Stage 4 IMPROVE

- Carry-over: add a generated freshness/coverage manifest for the coaching plan.
- Target: make the dashboard explain which report set produced the current training plan.
- Completed: generated `site-manifest.json` and rendered `复盘数据覆盖` panels on the history page and practice plan.
- User-visible gain: the player can immediately see the plan is based on 10 reports, 30 findings, 6 training topics, and the latest Dragon Knight match.
- Real issue fixed: static validation caught a broken indentation regression in manifest checks; fixed before commit.
- Verified: 45 tests, compileall, static site validation, desktop/mobile browser coverage-panel flow, diff check, and gitleaks.
- Commit: `feat: add report coverage manifest` (`d56aeae`), pushed to `origin/main`.
- CI: passed, `Deploy Cloudflare Pages` run `28311495305`.
- Remaining risk: manifest currently describes generated report coverage, not STRATZ/OpenDota fetch freshness.
- Recommended next flagship change: add a CHECK-stage link and artifact audit so stale or orphaned generated pages cannot silently ship.

## 2026-06-28 - Cycle 2 Stage 3 UIUX

- Carry-over: improve evidence-page scanning and cross-topic navigation.
- Flagship UI/UX change: upgraded each topic evidence page into a compact evidence workbench.
- Completed: added topic quick-switch navigation, visible evidence count, win/loss evidence filters, empty-state feedback, card data states, and mobile horizontal topic navigation without page overflow.
- User-visible gain: the player can scan a recurring problem by theme, filter winning/losing examples, and jump between coaching topics without returning to the dashboard.
- Real issue fixed: mobile topic navigation initially exposed a rough native horizontal scrollbar; it now keeps the scroll affordance without visual noise.
- Verified: 44 tests, compileall, static site validation, desktop/mobile browser workbench flow, diff check, and gitleaks.
- Commit: `feat: upgrade topic evidence workbench` (`252abae`), pushed to `origin/main`.
- CI: passed, `Deploy Cloudflare Pages` run `28307268987`.
- Remaining risk: topic pages filter only by result today; hero/role filters could further speed review once more matches accumulate.
- Recommended next flagship change: add a generated freshness/coverage manifest so the dashboard explains exactly which report set and latest match produced the coaching plan.

## 2026-06-28 - Cycle 2 Stage 2 IMPROVE

- Carry-over: make every canonical trend auditable beyond the three example links.
- Target: generate complete topic evidence pages and connect them to both the dashboard and practice plan.
- Completed: generated one `trend-*.html` evidence dossier per canonical topic, linked trend cards and practice-plan cards to those pages, and validated topic pages/backlinks in the static gate.
- User-visible gain: every repeated coaching issue now opens into a full evidence archive with each supporting match, original label, evidence text, training action, acceptance metric, and report link.
- Real issue fixed: practice-plan optional topic navigation no longer emits trailing whitespace when no extra topics exist.
- Verified: 44 tests, compileall, static site validation, browser drill-down flow, diff check, and gitleaks.
- Commit: `feat: add trend evidence drilldowns` (`2940d76`), pushed to `origin/main`.
- CI: passed, `Deploy Cloudflare Pages` run `28307051954`.
- Remaining risk: topic taxonomy is still curated v1; unknown future labels intentionally stay separate until mapped.
- Recommended next flagship change: improve the topic evidence pages for faster scanning across heroes and roles.

## 2026-06-28 - Cycle 2 Stage 1 IMPROVE

- Carry-over: normalize equivalent review focus names across reports.
- Root-cause finding: trend aggregation currently reads only the first finding card in each report, excluding most available coaching evidence.
- Target: aggregate all findings through a deterministic, auditable taxonomy while keeping per-match counts accurate.
- Completed: all 30 report findings now feed 6 canonical trend topics; JSON includes topic ids, finding counts, source labels, and per-match deduplication.
- User-visible gain: the training plan now surfaces recurring death-cost and item-conversion problems across all 10 matches instead of hiding non-primary findings.
- Real issue fixed: generated optional fragments no longer leave trailing whitespace.
- Verified: 42 tests, compileall, static site validation, browser desktop flow, console health, diff check, and gitleaks.
- Commit: `feat: aggregate complete coaching evidence` (`94b38cd`), pushed to `origin/main`.
- CI: passed, `Deploy Cloudflare Pages` run `28306075918`.
- Remaining risk: taxonomy aliases are intentionally curated; unknown labels stay separate until reviewed.
- Recommended next flagship change: topic drill-down pages with all supporting evidence and report links.

## 2026-06-28 - Stage 1 IMPROVE

- Goal: turn the existing match history page into a review-entry surface, not just a file list.
- Completed:
  - Added an evidence-backed priority review queue on the history page.
  - Extracted each report's first structured finding into focus, next action, acceptance metric, and priority.
  - Displayed every match's training focus directly in the history table.
- User-visible gain: the player can decide which match to review first and what to train next without opening every report.
- Real issue fixed: the history page previously hid the actionable coaching advice inside individual reports.
- Verification:
  - `python -m unittest tests.test_build_pages_site`
  - `python -m unittest discover -s tests -p "test*.py"`
  - `python -m compileall -q .`
  - `python scripts/check_public_site.py`
- GitHub Actions / CI: passed, run `28299842160`.
- Risks:
  - Priority is still report-driven; future work should add a multi-match trend view.
- Next best directions:
  - Build a recent-trends summary from repeated report findings.
  - Add client-side filters for hero, result, and review priority.
  - Add previous/next navigation inside report pages.
- Recommended flagship next change: generate a cross-match trend board that turns repeated problems into a focused practice plan.

## 2026-06-28 - Stage 2 IMPROVE

- Goal: convert single-match coaching notes into a recent trend board.
- Completed:
  - Aggregated report findings by focus across the current 10 public reports.
  - Added `最近反复问题` to the history page with frequency, involved heroes, example matches, action, and acceptance metric.
  - Exported `public/review-trends.json` for structured reuse.
  - Extended static site validation to require trend content and JSON shape.
- User-visible gain: the player can see recurring weaknesses before opening any single report.
- Real issue fixed: repeated coaching themes were previously hidden across separate HTML reports.
- Verification:
  - `python -m unittest tests.test_build_pages_site`
  - `python -m unittest discover -s tests -p "test*.py"`
  - `python -m compileall -q .`
  - `python scripts/check_public_site.py`
- GitHub Actions / CI: passed, run `28299977468`.
- Risks:
  - Trends group by exact report focus string; future work should normalize equivalent coaching themes.
- Next best directions:
  - Improve the history page UI density and responsive behavior now that it has two coaching sections.
  - Add client-side filters for result, hero, and priority.
  - Add previous/next report navigation.
- Recommended flagship next change: run a UI/UX pass that turns the history page into a polished coaching dashboard.

## 2026-06-28 - Stage 3 UIUX

- Goal: improve the history page's daily-use UX after adding priority queue and trends.
- Completed:
  - Added match search by hero, match id, action text, and focus text.
  - Added result and priority filter buttons with active state and live count feedback.
  - Fixed the default 1280px horizontal overflow.
  - Verified history -> latest report -> back navigation in browser.
- User-visible gain: the player can quickly find loss reviews, high-priority reviews, or a specific hero/problem without scanning all rows.
- Real issue fixed: the history dashboard overflowed horizontally at the default desktop viewport.
- Verification:
  - Browser desktop 1280px, mobile 390px, filter interactions, navigation flow, console health.
  - `python -m unittest discover -s tests -p "test*.py"`
  - `python -m compileall -q .`
  - `python scripts/check_public_site.py`
- GitHub Actions / CI: passed, run `28300185847`.
- Risks:
  - Filter state is not reflected in the URL yet.
- Next best directions:
  - Add previous/next navigation and adjacent-match context inside reports.
  - Add a compact practice-plan page generated from repeated trends.
  - Normalize equivalent finding names across reports.
- Recommended flagship next change: connect reports together so reviewing one game naturally leads to the adjacent games and trend context.

## 2026-06-28 - Stage 4 IMPROVE

- Goal: connect individual reports into the current match-history context.
- Completed:
  - Added `相邻比赛` navigation to each generated public report.
  - Showed report position plus newer/older match cards with hero, match id, result, and review focus.
  - Extended static validation so adjacent report navigation cannot disappear silently.
- User-visible gain: the player can continue reviewing nearby games without returning to the history list after every report.
- Real issue fixed: reports were isolated pages with no adjacent-match context.
- Verification:
  - Browser navigation: Dragon Knight report -> Mirana adjacent report.
  - `python -m unittest discover -s tests -p "test*.py"`
  - `python -m compileall -q .`
  - `python scripts/check_public_site.py`
- GitHub Actions / CI: passed, run `28305140645`.
- Risks:
  - The chain only includes reports available in the current public build.
- Next best directions:
  - Run a full project health check and tighten validation around generated HTML consistency.
  - Add a compact practice-plan page generated from recurring trends.
  - Normalize semantically equivalent review focus names.
- Recommended flagship next change: make the static validation stricter around stale report artifacts and generated asset consistency.

## 2026-06-28 - Stage 5 CHECK

- Goal: run a focused project health check and fix a real issue from the new dashboard flow.
- Completed:
  - Confirmed local SQLite data is ignored and not tracked.
  - Scanned for obvious sensitive strings, debugger, and console logging.
  - Added an empty state for zero-result match filtering.
  - Extended static validation so the empty state is required.
- User-visible issue fixed: searching or filtering to zero matches no longer leaves a blank table.
- Verification:
  - Browser check for `zzzz-no-match`: empty state visible, no overflow, no console warnings/errors.
  - `python -m unittest discover -s tests -p "test*.py"`
  - `python -m compileall -q .`
  - `python scripts/check_public_site.py`
  - `gitleaks dir . --redact`
- GitHub Actions / CI: passed, run `28305267306`.
- Risks:
  - Exact trend focus normalization remains future work.
- Next best directions:
  - Add a compact practice-plan page from recurring trends.
  - Add semantic grouping for equivalent focus names.
  - Add a small generated manifest for report freshness and counts.
- Recommended flagship next change: generate a practice-plan page that converts repeated trends into a next-session training queue.

## 2026-06-28 - Stage 6 IMPROVE

- Goal: turn repeated review trends into a next-session practice plan.
- Completed:
  - Added `practice-plan.html` generated from recurring trend data.
  - Added a `下一次训练计划` link on the history page.
  - Practice cards show priority, trend frequency, involved heroes, next action, acceptance metric, and example report links.
  - Fixed static validation so non-report pages are not checked as match reports.
- User-visible gain: before queueing the next ranked match, the player has a compact checklist of what to train first.
- Verification:
  - Browser desktop and mobile practice-plan checks with no overflow or console warnings/errors.
  - `python -m unittest discover -s tests -p "test*.py"`
  - `python -m compileall -q .`
  - `python scripts/check_public_site.py`
- GitHub Actions / CI: passed, run `28305412170`.
- Risks:
  - Trend focus names are still exact-string grouped.
- Next best directions:
  - Normalize equivalent focus names across reports.
  - Add URL-persisted filters for shareable history views.
  - Add a freshness manifest showing source report count and latest match id.
- Recommended flagship next change: normalize trend taxonomy so the practice plan groups equivalent issues across heroes and roles more intelligently.
