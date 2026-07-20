# Refresh lifecycle

## Outcomes

A completed refresh has one of three results:

- `complete`: every scheduled game is current.
- `partial`: at least one attempted game failed, while at least one pending game succeeded.
- `failed`: the schedule request failed, an orchestration error occurred, or every pending boxscore request failed.

The dashboard reports four coverage counts:

- `scheduled`: completed regular-season games returned by the schedule API.
- `current`: successfully cached games with no later failed attempt.
- `stale`: games with retained last-known-good data whose latest attempt failed.
- `missing`: scheduled games without a usable cached copy.

## Sequence

1. Fetch the completed-game schedule once.
2. For an incremental refresh, subtract only current game IDs. Failed IDs remain pending even if stale rows exist.
3. Fetch pending boxscores with bounded concurrency and request-start pacing.
4. Retry 429, 5xx, and transport failures with jittered exponential backoff.
5. On success, replace that game's appearances and mark its fetch state successful in one transaction.
6. On failure, retain any old appearances and mark the game failed.
7. Re-run role classification over stored appearances.
8. Persist the refresh result and coverage counts.

The next incremental refresh automatically retries stale and missing games. A force refresh attempts every scheduled game, but a failed forced attempt cannot make an old cached game appear current.

## UI behavior

The frontend polls `/api/status` while a refresh runs. A transient polling failure remains visible and polling resumes automatically. Refresh-request and team-data errors must not be hidden behind an older successful status.

`GET /api/failures` exposes the retryable game list and whether each failure has retained cached data.
