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
- GitHub Actions / CI: pending after push.
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
- GitHub Actions / CI: pending after push.
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
- GitHub Actions / CI: pending after push.
- Risks:
  - Filter state is not reflected in the URL yet.
- Next best directions:
  - Add previous/next navigation and adjacent-match context inside reports.
  - Add a compact practice-plan page generated from repeated trends.
  - Normalize equivalent finding names across reports.
- Recommended flagship next change: connect reports together so reviewing one game naturally leads to the adjacent games and trend context.
