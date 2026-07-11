# On-Demand Personal Dota Review Workbench Design

## Product Goal

Turn `dota.custard.top` into a focused personal review workbench for Steam account `173776719`:

- The site shows exactly the latest 10 ranked matches.
- Loading the site never contacts OpenDota or STRATZ for a fresh match list.
- A fresh match list is fetched only after the user presses the refresh button.
- Opening a match shows factual match and lineup data without running AI.
- Deterministic analysis and AI coaching run only after the user presses the analysis button.
- Every recommendation remains traceable to measured evidence and has a stricter, measurable next-game target.

The public repository must contain no API keys. `AGENTS.md`, Docker files, Docker configuration, and Docker runtime state are outside this work.

## Current-State Audit

The current site is a static archive of 43 pre-generated reports. The first viewport is dominated by CI-oriented coverage information such as report counts, finding counts, evidence classes, and source timestamps. The primary user task, choosing a recent match and starting a review, appears much later. The match page repeats this pattern by leading with evidence completeness before the player's result and next action.

The current hourly GitHub workflow also fetches and publishes matches without a user action. That behavior directly conflicts with the new manual-refresh requirement. Static report generation additionally makes it impossible to defer AI work until a user clicks inside a match.

## Considered Approaches

### Static-only browser application

The browser could call OpenDota directly and call an AI provider with a user-supplied key. This is simple to deploy, but it either exposes a key or forces repeated key setup in the browser. It also duplicates the mature Python evidence engine in JavaScript. Rejected.

### GitHub Actions as an analysis queue

A button could dispatch the existing report workflow. This reuses Python but requires a privileged GitHub token outside GitHub, introduces multi-minute waits, and makes progress polling and failure recovery awkward. Rejected.

### Cloudflare Python Worker with KV and Workers AI

A Python Worker can reuse the current deterministic analyzer, fetch evidence only when requested, cache match/review payloads in KV, and call Workers AI without exposing an API key. Cloudflare Pages remains the static frontend and the Worker owns only `/api/*`. Selected.

## Architecture

### Static frontend

Cloudflare Pages serves two application shells:

- `/index.html`: latest-10 match workbench.
- `/match.html?id=<match_id>`: factual match detail plus an explicit analysis action.

Static JavaScript never embeds a secret. On first load it reads the API's cached match list; if the API cache is empty or unavailable, it falls back to the committed `matches.json` seed. Neither read causes an external Dota data fetch.

Existing canonical report HTML remains available as historical compatibility content during the migration, but it is not linked from the new primary flow.

### API Worker

A separate Python Worker named `cstd-help-api` handles only `dota.custard.top/api/*`.

Bindings:

- `REVIEW_CACHE`: Workers KV namespace for cached lists, match details, review results, and rate-limit timestamps.
- `AI`: Workers AI binding.
- `STRATZ_API_KEY`: encrypted Worker secret, optional at runtime.

Fixed configuration:

- Account ID: `173776719`.
- Match list size: `10`.
- AI model: `@cf/openai/gpt-oss-120b`.
- Review cache key includes an analysis schema version, so analysis code changes invalidate stale coaching without a public force flag.

Mutation endpoints are deliberately idempotent and bounded instead of requiring a login. Refresh always targets the fixed account and is rate-limited. Analysis only accepts a match belonging to that account and returns an existing schema-versioned cache entry when available. A visitor therefore cannot analyze arbitrary players or repeatedly force model usage for the same match.

### Shared deterministic core

`analysis/analyzer.py` stays the source of truth for timeline, event, data-quality, role-profile, and `review_findings` generation. Network adapters are separated from pure normalization so both the existing CLI and Worker can pass the same OpenDota/STRATZ JSON into `analyze_match()`.

AI is downstream of deterministic analysis. The Worker sends only the structured evidence package and accepted findings to Workers AI. If inference fails, returns malformed output, or introduces unsupported claims, the API returns the deterministic coaching fallback. AI failure never removes the factual report.

## API Contract

### `GET /api/matches`

Reads the cached list only. It never calls OpenDota or STRATZ.

Response:

```json
{
  "account_id": 173776719,
  "matches": [],
  "refreshed_at": null,
  "source": "cache",
  "stale": true
}
```

### `POST /api/matches/refresh`

Fetches the latest 10 ranked matches for account `173776719`, normalizes hero/result/end-time/duration/KDA fields, writes the list to KV, and returns it. A second request inside the cooldown returns the current cache with `rate_limited: true`.

### `GET /api/matches/<match_id>`

Accepts only a match present in the latest-10 cache. It returns cached full OpenDota detail or fetches and caches that detail after the user has navigated to the match. This endpoint does not run deterministic analysis or AI.

### `GET /api/reviews/<match_id>/status`

Returns only whether a review exists for the current analysis schema version and its generation timestamp.

### `POST /api/reviews/<match_id>`

Validates ownership, obtains OpenDota detail and optional STRATZ playback evidence, runs the deterministic analyzer, calls Workers AI, validates the response, stores the result, and returns:

```json
{
  "match_id": 8891116798,
  "generated_at": "2026-07-12T00:00:00Z",
  "cached": false,
  "analysis": {},
  "coach": {
    "conclusion": "",
    "review_points": [],
    "next_actions": [],
    "data_limits": []
  }
}
```

## Frontend Experience

### Latest-10 workbench

The first viewport is a compact operational surface, not a marketing page:

- Header: `173776719 的天梯复盘`, last refresh time, and one primary refresh button.
- Summary strip: 10-match wins, losses, win rate, and analyzed count.
- Match list: hero portrait/name, result, end time, duration, KDA, and analysis status.
- Each row has one clear command: `查看对局`.
- Refresh states: idle, fetching, success with new-match count, rate-limited, and actionable failure.
- Empty cache: explain that no external fetch has run and provide the refresh command.

Only the latest 10 rows are rendered. The old 43-row archive, quality-gate dashboard, trend pages, and technical field coverage are removed from the primary workflow.

### Match detail

The page title and first heading begin with the played hero name. Before analysis it shows:

- Result, match ID, end time, duration, rank/lane/role when available.
- KDA, GPM, XPM, last hits, hero/tower damage.
- Both five-hero lineups and final items.
- A prominent `生成 AI 复盘` button.

Pressing the button creates an in-place progress state. On success, the page reveals sections in this order:

1. Most important conclusion.
2. Three to five next-game actions with measurable acceptance criteria.
3. Timeline diagnosis.
4. Death, item, objective, and participation events.
5. Evidence behind each main finding.
6. Collapsed data-source and limitation details.

If a review is cached, the button reads `打开已生成复盘`; clicking it loads the review without new inference. There is no public force-reanalysis control.

### Visual system

Retain the existing dark Dota-oriented foundation but simplify it:

- Near-black page background, neutral graphite surfaces, Dota red for losses/priority, green for wins/complete evidence, and restrained gold for coaching actions.
- Real Steam hero portraits are the main visual signal.
- Dense list rows on desktop and stacked, non-nested cards on mobile.
- Maximum card radius `8px`, stable row dimensions, visible keyboard focus, 44px minimum primary targets, and no horizontal document overflow at 390px.
- Familiar commands use Lucide icons loaded as a pinned browser dependency; text remains present for primary actions.
- Internal implementation terms such as `finding`, CI gate, payload count, and schema audit are not user-facing.

## Error Handling

- OpenDota list failure leaves the previous cache visible and reports that no data was replaced.
- Missing OpenDota detail produces a factual error state and never starts AI.
- STRATZ failure is recorded in `data_quality.limitations`; OpenDota evidence continues when it satisfies the deterministic gate.
- Evidence that fails the publication-quality gate prevents AI and explains which evidence class is unavailable.
- AI failure returns deterministic coaching with an `ai_status: fallback` marker in data details, not in the primary conclusion.
- Every API response includes a stable error code and a Chinese user-facing message.

## Deployment

- Remove the hourly schedule from `refresh-reports.yml`; keep a manual maintenance dispatch only.
- Deploy `cstd-help-api` before the Pages site from GitHub Actions when API files change.
- Continue deploying Pages from `public/` on every `main` push.
- Keep all secrets in GitHub Actions or Cloudflare encrypted bindings. No key value is written to source, generated HTML, logs, screenshots, or test fixtures.

## Verification

Automated checks cover:

- A page load cannot invoke the refresh or review mutation endpoints.
- Refresh returns at most 10 fixed-account ranked matches and uses the cache inside the cooldown.
- Match detail rejects IDs outside the cached personal list.
- Review generation calls deterministic analysis before AI and validates every finding field.
- AI output cannot add a category absent from `review_findings`.
- A one-window issue always targets zero rather than the current value.
- New static pages contain the required controls, states, and hero-first title contract.
- The scheduled refresh trigger is absent.

Browser acceptance covers desktop and 390px mobile layouts, manual refresh, match navigation, no-analysis initial state, analysis click, cached reopen, failure recovery, keyboard focus, console errors, network calls, and horizontal overflow.
