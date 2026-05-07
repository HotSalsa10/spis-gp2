# Phase 9 -- "Make It Smart" (Professor Feedback Round)

> **Goal:** address the prof's "isn't actually smart" critique by making the existing
> ML core visible and adding the operational loop (receive -> alert -> order -> recall).
>
> **Background:** SPIS already has XGBoost forecasting (MAE 1.06, beats naive 4.23),
> risk tiers, expiry-tiered discounts, ABC analysis, 94 tests. The prof's reaction is
> mostly a *framing* problem plus three real gaps (operational loop, financial impact,
> drug-name labels). Most "new" items below are extensions of what already exists.

---

## Instructions for whoever is executing this file

1. Work top-to-bottom. Items are ordered by **defense impact per hour**.
2. **As soon as an item is fully done (code + tests + docs/project_summary.txt updated), DELETE that whole section from this file.** Do not just check it off -- remove it. The file shrinks as Phase 9 progresses, so what's left is always "what's still pending."
3. After every deletion, update the "Status snapshot" line at the bottom.
4. If an item turns out to be wrong or out-of-scope mid-implementation, replace its section with a one-line "SKIPPED: <reason>" entry instead of deleting silently.
5. Do NOT add Co-Authored-By attribution to commits. Do NOT mention AI tooling anywhere in the codebase, commits, or docs. The team does not use Claude Code.
6. Each item below already states the files to touch, the approach, and the test bar. Stay surgical -- no adjacent refactors unless the section explicitly calls for one.
7. Windows terminal is cp1252 -- keep all written code/docs ASCII-only (no Unicode box-drawing or emoji).

---

## After every item

- Update `docs/project_summary.txt` (team reads this to stay in sync).
- Run `pytest` -- all tests must pass before deletion from this file.
- Commit with `feat:` or `fix:` prefix, no AI attribution.
- Delete the completed section from this file. Update status snapshot below.

---

## Status snapshot

- Total items pending: 0 (items 1-10 done; refill reminders deferred to ch7 Future Work)
- Last updated: 2026-05-07
