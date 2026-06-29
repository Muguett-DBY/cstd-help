# Iteration Log

## 2026-06-30 - Long Cycle 4 Stage 6 IMPROVE

- Goal: compare each real death's pre-death and post-death resource pace so the report can coach recovery behavior from observed minute arrays, not inference.
- Completed: added `timeline.death_resource_deltas`, visible `死亡前后资源变化` rows, and `死亡前后资源变化` findings with exact signed LH/min and average GPM deltas.
- Real issue fixed during review: fractional-minute deaths now skip the mixed death minute; `13.6分死亡` compares `10-13分钟` to `14-17分钟`.
- Real issue fixed during final static validation: Chinese custom training topics now hash their practice checklist token, fixing duplicate `practice-custom-*` IDs in `practice-plan.html`.
- User-visible gain: latest `Legion Commander #8870219537` now has a second high-priority finding, `死亡前后资源变化`, with concrete evidence such as `25.3分死亡前后：补刀/分 8.7→3.3（-5.4）` and a next-game action to finish one safe resource action after respawn.
- Verification:
  - New target tests failed before implementation, then passed.
  - `python main.py --skip-fetch --recent 18 --force`: regenerated 18 reports from real STRATZ details.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 81 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 18 report pages.
  - `gitleaks dir . --redact`: no leaks found.
  - `git diff --check`: passed.
  - Browser desktop/mobile QA passed with no horizontal overflow, no duplicate IDs, and no console errors.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Remaining risk: the delta diagnosis intentionally describes adjacent resource changes only; it does not infer the cause of each death or convert raw x/y coordinates into named map regions.
- Pending: commit, push, GitHub Actions, live Cloudflare Pages acceptance, and final Stage 6 closeout log.

## 2026-06-30 - Long Cycle 4 Stage 5 CHECK

- Goal: prevent death-review UI and coverage metadata from silently disappearing while generic static-site checks still pass.
- Completed: added `_find_death_review_coverage_issues()` to require the death workbench, recovery section, mobile phase cards, overview coverage panel, and all four death-review manifest counters.
- Consistency gate: the checker now recomputes coverage counts from every generated report and rejects manifest values that do not match the report set.
- Verification:
  - New CHECK test failed before implementation because the helper did not exist, then passed after the validation was added.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 76 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
  - `git diff --check`: passed.
  - Forbidden-file check: no `AGENTS.md`, Docker, or docker path changes.
- Remaining risk: reports show post-death recovery totals, but do not yet compare each death's pre-death resource pace with the immediate post-death pace.
- Recommended next direction: Stage 6 should add exact before/after death resource deltas from real minute arrays.

## 2026-06-30 - Long Cycle 4 Stage 4 IMPROVE

- Goal: show death-review evidence coverage on the site overview instead of hiding it inside individual match reports.
- Completed: parsed report-level death evidence flags, added site-manifest death coverage counts, and rendered a `死亡复盘覆盖` subsection in the shared coverage panel.
- User-visible gain: the history page now states that the latest 10-match set has 10 death review panels, 10 recovery-window reports, 9 coordinate-map reports, and 9 complete death reviews.
- Verification:
  - New coverage test failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 75 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
  - Browser desktop/mobile coverage-panel QA passed with no horizontal overflow.
- Remaining risk: the static validator validates generic coverage today; it does not yet specifically fail a site missing death-review coverage fields.
- Recommended next direction: Stage 5 CHECK should harden `scripts/check_public_site.py` around death-review UI, recovery windows, and manifest coverage counts.

## 2026-06-30 - Long Cycle 4 Stage 3 UIUX

- Goal: make timeline and death-review evidence easier to scan on mobile while keeping desktop density.
- Completed: added mobile `timeline-phase-cards`, kept desktop phase table, and introduced a `death-review-workbench` summary for located deaths, recovery windows, and coordinate points.
- User-visible gain: latest `Legion Commander #8870219537` now shows mobile timeline phase cards instead of a wide table, and the death section opens with `12` located deaths, `12` recovery windows, and `12` coordinate points.
- Verification:
  - New UIUX tests failed before implementation, then passed.
  - `python main.py --skip-fetch --recent 10 --force`: generated 10 reports from cached real STRATZ detail after live STRATZ fetch was blocked by Cloudflare.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 75 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
  - Browser desktop/mobile report QA passed with no horizontal overflow or console errors; mobile hides the phase table and shows 4 cards.
- Remaining risk: coverage is visible inside each report, but the history/site overview does not yet summarize which matches have complete death review coverage.
- Recommended next direction: Stage 4 should add site-level death evidence coverage for recovery windows and coordinate maps.

## 2026-06-30 - Long Cycle 4 Stage 2 IMPROVE

- Goal: measure whether each death was followed by a real resource recovery or another dead window.
- Completed: added `timeline.death_recovery_windows`, `死亡后恢复` findings, and a visible `死亡后恢复窗口` section in 时间线诊断.
- Real issue fixed during review: the first threshold marked low-LH/high-GPM windows as `恢复不足`; after real-report inspection it now requires both LH and GPM to be low when both metrics exist.
- User-visible gain: latest `Legion Commander #8870219537` now shows exact recovery rows such as `11.2分死亡后11-14分钟：25补，平均GPM 504.3，已恢复资源`.
- Verification:
  - New target tests failed before implementation, then passed.
  - `python main.py --skip-fetch --recent 10 --force`: generated 10 reports from cached real STRATZ detail after live STRATZ fetch was blocked by Cloudflare.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 73 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
  - Browser desktop/mobile report QA passed with no horizontal page overflow or console errors; recovery rows are readable on mobile.
- Remaining risk: mobile 时间线 phase table is still wide and awkward to scan, even though the page itself does not horizontally overflow.
- Recommended next direction: Stage 3 UIUX should convert the mobile timeline/death review area into a more readable stacked workbench.

## 2026-06-30 - Long Cycle 4 Stage 1 IMPROVE

- Goal: expose real death-position evidence as a visual report section without inventing map regions.
- Completed: added deterministic `death_map_points`, a report `死亡坐标图` SVG scatter plot, responsive coordinate chips, and tests covering both analysis output and generated HTML.
- User-visible gain: latest `Legion Commander #8870219537` now shows 12 raw STRATZ death coordinate points, including labels like `11.2分 x=94,y=168`, directly inside `死亡/装备事件`.
- Verification:
  - New target tests failed before implementation, then passed.
  - `python main.py --skip-fetch --recent 10 --force`: generated 10 reports from cached real STRATZ detail after live STRATZ fetch was blocked by Cloudflare.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 71 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
  - Browser desktop/mobile report QA passed with no horizontal overflow or console errors.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28393634468`.
- Live check: latest `Legion Commander #8870219537` report returned 200 and contains `死亡坐标图`, raw coordinate note, and 12 plotted points.
- Remaining risk: raw coordinates are not converted to named map regions until a verified Dota coordinate transform exists.
- Recommended next direction: add death-after resource recovery diagnostics, using real minute-level LH/gold data to show whether each death was followed by a recovery or a dead window.

## 2026-06-30 - Long Cycle 3 Stage 6 IMPROVE

- Goal: connect deaths with low-efficiency windows so reports show where real deaths interrupted resource flow.
- Completed: added `timeline.death_overlap_windows`, high-priority `死亡打断资源` findings, and a visible `死亡打断资源窗口` subsection in report 时间线诊断.
- User-visible gain: latest `Legion Commander #8870219537` now shows exact overlap evidence such as `低效率窗口 25-27分钟含 25.3分死亡` and `低效率窗口 32-36分钟含 32.2分死亡、33.8分死亡`.
- Verification:
  - New target tests failed before implementation, then passed.
  - `python main.py --skip-fetch --recent 10 --force`: generated 10 new reports after live STRATZ detail fetch succeeded.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 69 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
  - Browser desktop/mobile report QA passed with no horizontal overflow or console errors.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28391972379`.
- Live check: latest `Legion Commander #8870219537` report returned 200 with the new overlap section and evidence-source coverage.
- Remaining risk: overlap diagnosis is time-based only; it does not infer death cause or named map region.
- Recommended next direction: improve map-position interpretation only after adding a verified Dota coordinate transform; otherwise keep advice tied to raw samples and event timing.

## 2026-06-30 - Long Cycle 3 Stage 5 CHECK

- Goal: prevent future generated report regressions where evidence-source coverage disappears but CI still passes.
- Completed: added static-site validation for report evidence-source coverage and a regression test that fails on a report missing `证据来源与覆盖`.
- Real issue fixed: `scripts/check_public_site.py` now rejects report pages missing source list hooks or required source rows for stats, timeline, purchases, deaths, and death positions.
- Verification:
  - New CHECK test failed before implementation, then passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 67 tests.
  - `python -m compileall -q .`: passed.
  - `gitleaks dir . --redact`: no leaks found.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28391396819`.
- Live check: latest `Legion Commander #8870219537` report returned 200 with seven evidence-source rows.
- Remaining risk: validator proves coverage is visible; analyzer tests remain responsible for semantic source-row correctness.
- Recommended next flagship change: cross-reference deaths with low-efficiency windows so the report can show where deaths directly interrupted resource flow.

## 2026-06-30 - Long Cycle 3 Stage 4 IMPROVE

- Goal: make every precise report claim auditable by showing source availability and coverage inside the match report.
- Completed: added deterministic evidence-source coverage rows for core stats, timeline, purchases, deaths, death positions, fight events, and vision events; regenerated the latest 10 public reports from cached real STRATZ/OpenDota data.
- User-visible gain: the latest reports now show `证据来源与覆盖`, including factual labels like `STRATZ位置采样` and `覆盖 12/12 次已定位死亡`.
- Verification:
  - New target tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 66 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
  - Browser desktop/mobile report QA passed with no horizontal overflow or console errors.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28391147465`.
- Live check: latest `Legion Commander #8870219537` report returned 200 and contained the evidence-source coverage section.
- Remaining risk: live STRATZ refresh is still blocked by Cloudflare in this environment; regenerated public reports used cached real payloads.
- Recommended next CHECK item: harden static validation so future report pages cannot ship without evidence-source coverage and source/coverage rows.

## 2026-06-29 - Long Cycle Stage 6 IMPROVE

- Carry-over: add a compact export/share artifact for the training plan.
- Completed: generated `practice-plan.txt` from the same evidence topics as the HTML workbench and linked it from `practice-plan.html` as `导出训练清单`.
- User-visible gain: the player can copy or save a plain-text next-game checklist with priority topics, actions, acceptance metrics, failure evidence links, win-sample links, hero-specific links, and execution checkpoints.
- Real issue fixed: the training plan now has a portable artifact instead of requiring the interactive HTML page to be open before queueing.
- Verified: target export test, static validation for the new text file, browser link presence, HTTP 200/content check for `practice-plan.txt`, 57 unit tests, compileall, full public-site validation, gitleaks, diff check, and forbidden-file check.
- Commit: `feat: add portable practice plan export` (`4872655`).
- CI: passed, `Deploy Cloudflare Pages` run `28364459477`.
- Remaining risk: text export is generated at build time and does not include local checkbox completion state.
- Recommended next flagship change: add live-domain smoke checks for `practice-plan.txt`, filtered topic evidence links, and report-section anchors after deploy.

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

## 2026-06-29 - Long Cycle 2 Stage 1 IMPROVE

- Goal: make the training plan usable immediately before queueing the next ranked match.
- Completed: added `match-brief.html`, a 30-second pre-match execution card generated from the same evidence-ranked trends as the practice plan.
- User-visible gain: the dashboard and training plan now link to a compact page with latest match context, three core commitments, failure evidence links, and the post-game review loop.
- Real issue fixed: legacy report item slots are upgraded during Pages build, preventing unresolved `Item #...` labels from reaching public reports.
- Verification:
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 58 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
  - Playwright CLI desktop/mobile screenshots rendered the execution card; HTTP check returned 200 with 3 cards and latest Legion Commander match.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28366750310`.
- Risks:
  - The pre-match card is static at build time and does not include browser-local checklist progress.
- Next best directions:
  - Add role/hero-aware drill-down from the pre-match card into comparable wins and losses.
  - Add a generated recent-match freshness block to the execution card itself.
  - Keep tightening stale public artifact detection in CHECK.
- Recommended flagship next change: add hero-specific comparison lanes so each core commitment shows the closest winning sample beside the failure evidence.

## 2026-06-29 - Long Cycle 2 Stage 2 IMPROVE

- Goal: make the pre-match execution card more actionable by pairing failure evidence with a winning comparison sample.
- Completed: each commitment now shows `失败证据` and `胜利样本` side by side, with filtered topic links for both losing and winning evidence.
- User-visible gain: the player can see what to avoid and what a better sample looked like without leaving the execution-card workflow.
- Real issue fixed: themes without a real winning sample now say `暂无胜利样本` instead of reusing failure text under a misleading label.
- Verification:
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 58 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
  - HTTP/browser fallback QA returned 200 with 3 proof grids and win/loss links; Playwright CLI desktop screenshot rendered correctly.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28367152171`.
- Live check: `https://dota.custard.top/match-brief.html` returned 200 and contained `brief-proof-grid`, `胜利样本`, and latest `Legion Commander #8870219537`.
- Risks:
  - Winning samples are still topic-level rather than hero-specific comparisons.
- Next best directions:
  - UI/UX pass on the execution card for mobile readability and scan speed.
  - Add source freshness/context directly into the execution card.
  - Add hero-specific comparison where enough reports exist.
- Recommended flagship next change: make the pre-match execution card visually faster to scan on mobile and desktop.

## 2026-06-29 - Long Cycle 2 Stage 3 UIUX

- Goal: make the pre-match execution card faster to scan before queueing.
- Completed: added a sticky `赛前只盯` command bar to `match-brief.html`, with compact links to each generated commitment card.
- User-visible gain: desktop users can see the three priorities immediately; mobile users get a horizontal strip of commitment chips before the detailed cards.
- Verification:
  - Target UI tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 58 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
  - Playwright CLI desktop/mobile screenshots rendered the command bar; local HTTP/static checks found 3 command links, 3 cards, and 3 anchors.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28369377149`.
- Live check: `https://dota.custard.top/match-brief.html` returned 200 and contained the command bar, commitment anchors, and latest `Legion Commander #8870219537`.
- Risks:
  - The command bar does not yet track the currently visible commitment while scrolling.
- Next best directions:
  - Add a portable export for the pre-match execution card.
  - Add freshness/context directly into the execution card.
  - Add active-section highlighting if the card grows beyond three commitments.
- Recommended flagship next change: add a compact text export for the pre-match execution card so the same three commitments can be opened outside the HTML page.

## 2026-06-29 - Long Cycle 2 Stage 4 IMPROVE

- Goal: add a portable plain-text export for the pre-match execution card.
- Completed: generated `match-brief.txt` and linked it from `match-brief.html` as `导出执行卡`.
- User-visible gain: the same three pre-match commitments can be opened as lightweight text, including latest match context, action metrics, failure evidence, and winning-sample evidence.
- Verification:
  - Target export test failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 58 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
  - Manual output review confirmed `public/match-brief.txt` contains latest `Legion Commander #8870219537`, three commitments, and win/loss evidence.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28369747011`.
- Live check: `https://dota.custard.top/match-brief.html` linked the export, and `https://dota.custard.top/match-brief.txt` returned 200 with latest match context and failure evidence.
- Risks:
  - The text export is static at build time and does not reflect browser-local checklist state.
- Next best directions:
  - CHECK should harden generated-site validation around support-page classification and text exports.
  - Add freshness/context directly into the execution card.
  - Add active-section highlighting only if commitments expand beyond three.
- Recommended flagship next change: harden the Pages validator so future generated support pages and text exports cannot be misclassified or left stale.

## 2026-06-29 - Long Cycle 2 Stage 5 CHECK

- Goal: fix a real validation risk instead of returning a status-only CHECK.
- Completed: centralized support-file definitions and report-page classification in `scripts/check_public_site.py`.
- User-visible protection: future generated support pages and text exports are less likely to break the public site by being counted as match reports or omitted from required-file validation.
- Verification:
  - New CHECK regression test failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 59 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28370064631`.
- Live check: `https://dota.custard.top/` and `https://dota.custard.top/match-brief.txt` returned 200 with expected content.
- Risks:
  - Topic pages are still identified by the `trend-*.html` filename convention.
- Next best directions:
  - Add freshness/context directly into the execution card.
  - Add source/report count to the text export if needed.
  - Keep Cloudflare Pages acceptance checks on every push.
- Recommended flagship next change: add a freshness strip to the execution card so the player can see exactly how much evidence the card is based on before queueing.

## 2026-06-29 - Long Cycle 2 Stage 6 IMPROVE

- Goal: make evidence coverage visible on the pre-match execution card.
- Completed: added a `证据覆盖` strip to `match-brief.html` showing `10 场复盘`, `16 条教练证据`, and `4 个训练主题`.
- User-visible gain: the player can judge the evidence base of the three commitments before using them in the next match.
- Verification:
  - Target UI tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 59 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
  - Playwright CLI desktop/mobile screenshots showed the freshness strip without overlap.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28370478876`.
- Live check: `https://dota.custard.top/match-brief.html` returned 200 with `证据覆盖`, `10 场复盘`, `16 条教练证据`, `4 个训练主题`, and latest `Legion Commander #8870219537`.
- Risks:
  - Freshness values are static until the next Pages build.
- Next best directions:
  - Consider active-section highlighting only if the execution card expands beyond three commitments.
  - Keep strict public-site validation for every support file and text export.
  - Continue using real STRATZ/OpenDota evidence in the report generator.
- Recommended flagship next change: no urgent product gap remains in this 6-stage cycle; future work should focus on deeper match data ingestion rather than more summary UI.

## 2026-06-30 - Long Cycle 3 Stage 1 IMPROVE

- Goal: make minute-level lane diagnostics survive when regular minute arrays are missing but STRATZ playback CS events are available.
- Completed: derived LH/min arrays from `playbackData.csEvents`, surfaced `STRATZ补刀事件` as the visible timeline source, and recorded the source in `data_quality.available`.
- User-visible gain: reports can produce real 10-minute LH, phase LH/min, and low-efficiency windows from event evidence instead of showing a missing-data caveat.
- Verification:
  - New target tests failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 61 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28388235464`.
- Live check: `https://dota.custard.top/` and `https://dota.custard.top/site-manifest.json` returned 200; manifest still reported 10 reports and latest `Legion Commander #8870219537`.
- Risks:
  - CS playback still only provides lane last-hit counts; it does not add gold/XP/damage arrays unless STRATZ also exposes those minute arrays.
- Next best directions:
  - Attach STRATZ position samples to death events so death findings can point to real map-location evidence.
  - Expose death-event evidence more clearly in the report UI.
  - Keep generated-site validation aware of newly exposed evidence-source labels.
- Recommended flagship next change: enrich death events with nearest STRATZ position samples so coaching advice can target where deaths happened, not just when.

## 2026-06-30 - Long Cycle 3 Stage 2 IMPROVE

- Goal: add real map-position evidence to death events when STRATZ playback position samples are available.
- Completed: normalized `playerUpdatePositionEvents`, attached the latest pre-death sample within 45 seconds to each death event, and carried those labels into death findings plus AI prompt event formatting.
- User-visible gain: death review can point to specific sampled coordinates, for example `x=122,y=140（死亡前30秒）`, so replay checks target the real death location instead of vague “站位问题”.
- Verification:
  - New target test failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 62 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
- GitHub Actions / CI: passed, `Deploy Cloudflare Pages` run `28388612290`.
- Live check: `https://dota.custard.top/` and `https://dota.custard.top/site-manifest.json` returned 200; manifest still reported 10 reports and latest `Legion Commander #8870219537`.
- Risks:
  - The system intentionally labels raw x/y samples only; it does not infer lane, jungle, Roshan, high-ground, or tower-area names without a verified map transform.
- Next best directions:
  - Improve the HTML event section so death position labels are visible next to each death pill.
  - Add static validation that generated reports expose death position evidence when present.
  - Keep all death-location advice tied to real samples rather than inferred map zones.
- Recommended flagship next change: make death position samples visible in the report UI, not just inside the structured finding and AI prompt.

## 2026-06-30 - Long Cycle 3 Stage 3 UIUX

- Goal: make real death-position evidence immediately visible in the event section.
- Completed: rendered each located death as a responsive evidence card with death minute, x/y sample, and sample age; missing samples remain explicit rather than inferred.
- User-visible gain: the player can scan the exact death review targets without finding the same evidence inside a longer coaching paragraph.
- Verification:
  - New target rendering test failed before implementation, then passed.
  - `python -m unittest discover -s tests -p "test*.py"`: passed, 63 tests.
  - `python -m compileall -q .`: passed.
  - `python scripts/check_public_site.py`: passed, 10 report pages.
  - `gitleaks dir . --redact`: no leaks found.
  - Browser QA passed at the default desktop viewport and 390x844 mobile viewport; event cards had no horizontal overflow and console logs were clean.
- Deployment: feature commit `2b87436` pushed; GitHub Actions run `28389527343` passed. The latest 10 real reports were then regenerated from cached playback evidence and staged for the public-site refresh.
- Real-report review: latest `Legion Commander #8870219537` shows purchase timing, 10-minute LH, timeline provenance, and 12/12 located deaths; the visible event grid contains ten position-evidence cards without horizontal page overflow.
- Risks:
  - Coordinates intentionally remain raw x/y samples until a verified Dota map transform is available.
- Next best directions:
  - Show evidence-source coverage explicitly in every generated report.
  - Add validation that unsupported map-region claims cannot appear without real evidence.
  - Cross-reference deaths with low-efficiency windows using deterministic timing.
- Recommended flagship next change: add a visible source-provenance summary so every precise claim can be traced to OpenDota or STRATZ evidence.
