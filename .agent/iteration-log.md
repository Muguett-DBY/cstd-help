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
