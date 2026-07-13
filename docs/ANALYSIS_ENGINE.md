# Analysis Engine

The review runtime is fully deterministic. OpenDota and STRATZ provide observed match fields; `analysis.analyzer` normalizes them and `analysis.formula_engine` produces scorecards, issue priority, conclusions, and next-match actions. No runtime module calls a language model or free-form text service.

## Evidence Contract

Every analysis includes a role-aware `data_quality.field_ledger`. The ledger covers core stats, ten participants, role and lane, ability build, final items, minute LH/gold/XP/damage, purchases, deaths and death positions, fight events, objectives, vision, hero percentiles, performance context, and extended activity data.

Required ledger entries must be `available` before a review can be cached or returned. Missing inputs are never estimated. The Worker keeps evidence acquisition in `processing` state and retries the fixed OpenDota/STRATZ workflow instead of publishing a partial recommendation.

Scoreboard K/D/A totals and timed combat events are separate facts. The scoreboard remains authoritative for totals. Timed logs are used only for event windows, expose their own coverage and source, and are never padded with invented timestamps when a provider's event count differs from the scoreboard.

## Formula Output

`analysis.formula_engine` publishes a versioned formula contract:

- Five scorecards: laning, economy, survival cost, map conversion, and role execution.
- Every scorecard exposes its equation, observed inputs, input sources, threshold, weight, and status.
- Findings are ranked by rule priority, measured impact, and field-ledger confidence.
- Actions are dimension-deduplicated. Data-acquisition gaps, death-overlapped farm windows, and raw-coordinate drills are not promoted into next-match actions.
- Unavailable scorecard dimensions are listed as unscored; they receive no inferred value.

Hero names are used for report titles, filenames, and metadata. Position-specific rules select the relevant metric family, but deployment files do not contain hero-specific tactical claims.
