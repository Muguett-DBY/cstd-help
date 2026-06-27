# Iteration Log

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
