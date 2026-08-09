# Agent operating guide

This repository is a refreshable MLB pitch-workload dashboard. Read `README.md`, `docs/data-contract.md`, and `docs/deployment.md` before changing architecture, storage, refresh behavior, or deployment.

## Supported design

- `observable/` is the only supported UI: a static Observable Framework site on GitHub Pages.
- `pipeline/` owns MLB access, classification, persistence, validation, checking, and build-time export.
- `main` contains human-maintained source. The orphan `dashboard-data` branch contains machine-managed validated snapshots and is never merged into `main`.
- Pages output is an ephemeral Actions artifact. Never commit `observable/dist/`.
- The browser makes no MLB data requests. Public CDN logos and portraits are permitted display assets.

Do not add a runtime backend, database, client-side refresh path, deployment target, credentialed integration, or automatic merge path without a concrete product need and explicit approval.

## Engineering philosophy

Favor durable structure over defensive volume. The supported refresh/build/deploy path is the whole system, not one possible caller among many.

- Encode guarantees in types, required data shapes, and the dataflow. Code consuming a validated snapshot should trust those guarantees instead of rechecking them throughout export, build, and UI layers.
- Validate an invariant at the boundary that owns it. Production checks are justified only for uncertainty that still exists at that boundary; repeating an upstream contract check is maintenance cost, not extra correctness.
- There is one live application/data contract. Meaningful changes rebuild `dashboard-data`; do not retain parsers, defaults, migrations, or UI branches for obsolete shapes.
- Handle domain failures that occur in the supported system, such as MLB request failures and partial snapshots. Do not add guards, fallback paths, abstractions, or configuration for hypothetical external callers, alternate pipelines, or legacy deployments.
- Prefer a small design correction that removes an invalid state or obsolete branch. A fix that adds checks, wrappers, flags, or explanatory caveats should demonstrate that its complexity is cheaper than the reachable failure it prevents.
- Review findings are leads, not obligations. Reproduce a claimed failure through the supported lifecycle and assess its likelihood and impact. Reject unreachable scenarios, stylistic churn, speculative flexibility, and technically true but immaterial nitpicks.
- Keep responses proportional. Do not turn a local bug into a framework, broad hardening pass, or new policy unless the same cause is demonstrably systemic.

Documentation should explain architecture, durable semantics, operational choices, and non-obvious constraints. Do not duplicate implementation that an agent can learn by reading the code.

## Domain invariants

1. Team total pitches equal both `official_sp + official_rp` and `adjusted_sp + adjusted_rp`.
2. Official SP/RP is MLB's per-game `gamesStarted` value. Never infer it from order, pitch count, duration, or result.
3. Role adjustment is conservative. A game's classified relief-dominant opener pairs with its 45+-pitch follower, who adjusts to SP as the planned bulk man; other ambiguous long relief remains RP with an auditable review reason. Reviewed exceptions and the `reviewed_through` review marker use `config/role_overrides.json`.
4. Failed refetches preserve last-known-good appearances as stale; first-time failures are missing. Neither may be silently reported current.
5. Reject a completed-game schedule that loses a persisted game.
6. Validate before writing and after reload. Manifest hashes and coverage counts are part of the contract.
7. Production season comes from `config/dashboard.json`, never the current calendar year.

## Workflow boundaries

- `Refresh dashboard data` is the sole automated writer to `dashboard-data` and refreshes incrementally by default.
- A failed refresh must not start deployment; a failed build must not replace the last successful Pages artifact.
- Pull requests build the real-data artifact but never deploy. Do not path-filter that required PR workflow.
- `workflow_run` handoffs and manual production runs remain restricted to `main`.
- CI is read-only. Refresh receives contents-write only. Pages and id-token permissions belong only to the deployment job.
- Changes under `pipeline/**` must continue to trigger the real-data Pages build.

GitHub cron is best-effort. The 07:17 and 09:17 UTC refreshes use the same serialized incremental path because observed morning dispatches can be hours late; runner pickup was not the bottleneck. Do not promise exact freshness or reframe ordinary dispatch delay as a workflow defect. An external scheduler is a new integration requiring approval.

## Observable React boundary

Observable renders TSX with its self-hosted npm React runtime. Hook-using components must import from `npm:react`:

```ts
import {useEffect, useMemo, useState} from "npm:react";
```

A bare `react` import creates a second runtime and can pass typecheck, tests, and build while failing in the browser. The TypeScript path mapping supplies declarations only; the compiled `_node/react` rejection is intentional.

## Change discipline

- Start from current `main`, use a focused `codex/` branch, and preserve unrelated worktree changes.
- Keep domain calculations pure and separate from HTTP, persistence, and UI where practical.
- Keep displayed values, sort keys, and ranks semantically aligned.
- Update documentation when user-facing concepts, architecture, contracts, configuration, or operations change; omit code narration.
- Never commit caches, virtual environments, `node_modules`, disposable snapshots, or build output.
- Treat automated review according to the engineering philosophy above, not as a checklist to apply mechanically.
- Do not ship suppressed errors, duplicated sources of truth, temporary workarounds, or appearance-only migrations. Resolve the underlying assumption or discuss it with the user.
- Surface material concerns found during the task, but weigh their real likelihood and maintenance cost. Do not add generalized guardrails for hypothetical integrations or legacy states.

## Validation

Pipeline, storage, classification, or export changes:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Static dashboard changes:

```bash
cd observable
npm ci
npm run typecheck
npm test
OBSERVABLE_TELEMETRY_DISABLE=true npm run build
```

Loader, exporter, schema, validation, or deployment changes also require a build from `dashboard-data` and `python -m pipeline.verify_build --dist-dir observable/dist` with the expected season and data revision in the environment.

For UI or bundling changes, inspect the production-data build in a browser. At minimum verify:

- Recent strain and Season leaders both render with 30-team production data.
- Team selection, workload framing, role basis, per-game mode, and header sorting respond.
- Team rows open timelines, player rows open history, and Role adjustment closes/disables row panels.
- Recent/next-game, bullpen, starter-rest, team timeline, and player-history content render coherently.
- Static images load and the browser console has no application errors.

Exercise a real degraded state when the change affects one. Do not manufacture broad edge-state infrastructure for unrelated code.

Workflow changes require parsing the YAML and checking triggers, permissions, concurrency, PR non-deployment, refresh-failure handoff, and relevant source coverage.

## Failure triage

- **Refresh failed:** inspect failed games and upstream HTTP behavior; keep the last Pages site.
- **Partial snapshot:** distinguish stale retained data from missing games and keep that status visible.
- **Build failed:** inspect snapshot reload and payload verification; never bypass integrity checks.
- **Blank deployed page:** inspect console/network output, React runtime duplication, and asset paths.
- **Old-looking data:** compare footer generation time and data revision with the latest refresh before forcing a full fetch.

## GitHub and pull-request handoff

In ChatGPT Work mode, use the native GitHub integration for repository state, pull requests, checks, and logs rather than assuming local `gh` authentication.

Codex only: if `gh auth status` appears unauthenticated inside the sandbox, retry it with escalated permissions outside the sandbox before concluding that authentication is missing; the sandbox can mask a valid login.

A PR description should state what and why, user/data/operational impact, checks run, and any post-merge verification. Delivery or rendering changes are not complete solely because Actions is green; verify the public page after merge. When waiting for GitHub Codex review, inspect written feedback and reactions: a 👍 from `chatgpt-codex-connector[bot]` on the current head is its clean terminal response.
