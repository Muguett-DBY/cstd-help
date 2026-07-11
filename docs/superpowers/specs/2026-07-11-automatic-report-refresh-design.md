# Automatic Report Refresh Design

## Problem

The public site currently ends at match `8870219537` from 2026-06-28, while OpenDota lists ranked match `8891116798` from 2026-07-11. The deploy workflow only publishes the committed `public/` directory and never fetches matches, so GitHub-to-Cloudflare deployment works but report data silently becomes stale.

## Goals

- Discover ranked matches for player `173776719` that are absent from the public site.
- Request OpenDota parsing automatically and publish only when real minute-level evidence is available.
- Use STRATZ core/playback evidence when a repository secret is configured, with OpenDota as the required public fallback.
- Append new canonical reports without regenerating or deleting historical reports.
- Preserve report generation time, source fetch time, evidence limitations, and all historical redirects.
- Run hourly and allow manual dispatch; commit only real `public/` changes to `main`.

## Non-goals

- Do not infer missing deaths, positions, objectives, roles, or item timings.
- Do not publish a core-stat-only report without minute-level evidence.
- Do not commit SQLite data, raw API payloads, API keys, or local report directories.
- Do not modify Docker files or `AGENTS.md`.

## Architecture

`scripts/refresh_public_reports.py` inventories canonical report metadata already present in `public/`, fetches recent ranked matches from OpenDota, and processes only unseen match IDs. It requests parsing for every unseen match that lacks minute arrays, waits once for the batch, then refetches those details. Each match is analyzed with available STRATZ and OpenDota evidence; publication is deferred when the analyzer still marks the timeline evidence missing.

The script copies existing canonical reports into a temporary source directory, generates new reports into the same directory, and calls the existing Pages builder. This preserves unlimited history while letting the builder recalculate navigation, trends, manifests, and stable redirects across the complete set.

Source fetch timestamps are embedded in report metadata and can also be recovered from an already-published report's provenance attributes. The Pages builder merges embedded timestamps with SQLite timestamps, so an ephemeral GitHub runner cannot erase historical provenance.

## Publication Readiness

A new report may be published only when:

- the OpenDota full match contains the target player and valid core match data;
- the deterministic analyzer returns a usable `timeline` evidence source (`available` or `partial`);
- every generated finding still carries evidence, action, and replay/system check fields under the existing quality gate.

Missing event-level data remains visible as partial evidence. A match with no minute timeline is deferred and retried by the next scheduled run.

## Workflow And Security

`.github/workflows/refresh-reports.yml` runs hourly and on manual dispatch with `contents: write`. It reads `STRATZ_API_KEY` only from GitHub Secrets, runs the refresh, executes tests/compile/static validation, stages only `public/`, and pushes a normal fast-forward commit to `main` when content changed. GitHub suppresses new workflow events caused by the repository `GITHUB_TOKEN`, so the refresh workflow deploys that exact committed `public/` tree to Cloudflare Pages in the same run instead of assuming the push will trigger the separate deployment workflow.

The key remains outside Git and logs. A missing or blocked STRATZ source is a supported state because OpenDota parsing supplies the minimum evidence gate.

## Acceptance

- A missing parsed match is requested, not published immediately, and becomes publishable after minute arrays arrive.
- Existing report HTML and source timestamps survive an incremental build.
- No-new-match runs produce no public diff and no commit.
- New ranked matches appear in the history list with canonical hero-first URLs and evidence-backed reports.
- Unit tests, compile, static-site validation, secret scan, GitHub Actions, and live browser checks all pass.
