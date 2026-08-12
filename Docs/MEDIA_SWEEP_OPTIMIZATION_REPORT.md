# media.sweep_pending Crash-Recovery Polling — Optimization Report

**Date:** 2026-08-13
**Scope:** `app/workers/media_generation.py::run()`, `app/celery_app.py`'s Beat schedule, and their tests. No unrelated files touched.
**Files changed:** `Backend/app/celery_app.py`, `Backend/app/workers/media_generation.py`, `Backend/tests/unit/test_celery_app.py`, `Backend/tests/unit/test_media_generation_worker.py`, `Backend/tests/unit/test_media_repository.py`
**Not done, per instructions:** nothing committed or pushed; no unrelated changes; `STALE_AFTER_SECONDS` (120s) left untouched; no new queue/scheduler introduced; task not moved back into FastAPI.

---

## 1. Current Architecture

`media.sweep_pending` is a Celery Beat–triggered task (`app/tasks/media.py`) that calls `app.workers.media_generation.run()`. It exists purely as a **crash-recovery / multi-process safety net** for image variant generation — the primary path is `generate_variants.delay(str(image.id))`, dispatched synchronously from the HTTP request the moment a crop/upload/replace/regenerate commits (`universal_service._enqueue_generation`). `run()` matters only when that primary dispatch didn't finish: a worker process died mid-generation (row stuck `'processing'`), or the dispatch itself was lost before ever being claimed (row still `'pending'`).

Per-image claiming is atomic and untouched by this work: `ImageRepository.try_claim_pending()` does `UPDATE images SET status='processing' ... WHERE status='pending' ... RETURNING id` — whichever of the fast path or the sweep reaches a given image first wins the claim; the other gets zero rows back and no-ops. This is the actual concurrency-safety mechanism for "never process the same image twice," and it lives entirely downstream of everything changed in this report.

State machine (confirmed by reading every write site, not assumed):
```
pending --[try_claim_pending, atomic UPDATE...WHERE status='pending']--> processing
processing --[generation succeeds]--> ready
processing --[generation fails, attempts < MAX_ATTEMPTS=3]--> pending (retry)
processing --[generation fails, attempts >= MAX_ATTEMPTS]--> failed
processing --[stuck > STALE_AFTER_SECONDS=120s, reclaim_stale_processing]--> pending (crash recovery)
```
`reclaim_stale_processing`'s `UPDATE ... WHERE status='processing' AND updated_at < cutoff` does not itself check or bump the attempts counter — but every subsequent `try_claim_pending` does, on every claim, reclaimed or fresh — so `MAX_ATTEMPTS` is enforced cumulatively across both plain-retry and crash-reclaim cycles, unchanged by this work.

## 2. Why the 5-Second Polling Was Expensive

Every tick of `run()`, whether or not there was anything to do, opened **two separate `AsyncSessionLocal()` sessions**:

```python
async with AsyncSessionLocal() as db:           # session 1
    reclaimed = await _repo.reclaim_stale_processing(db, stale_after_seconds=STALE_AFTER_SECONDS)
    await db.commit()
...
async with AsyncSessionLocal() as db:           # session 2
    pending = await _repo.list_pending_images(db, limit=POLL_BATCH_LIMIT)
```

Each session is its own transaction lifecycle against the remote Supabase Postgres instance. Counting actual network round trips (not connection-pool checkouts, which the DB connection pool fix from the previous session already confirmed cost ~0ms — see `Docs/IMAGE_CROP_ROOT_CAUSE_INVESTIGATION.md`/pool metrics):

| Step | Round trips |
|---|---|
| Session 1: `UPDATE ... RETURNING` (reclaim) | 1 |
| Session 1: `COMMIT` | 1 |
| Session 2: `SELECT` (list) | 1 |
| Session 2: implicit `ROLLBACK` on session close (read-only, nothing to commit) | 1 |
| **Total per tick** | **4** |

At the original 5s interval: `4 round trips × (86400 / 5) ticks/day = 69,120 round trips/day`, continuously, whether or not there was ever anything pending — this matches the production observation of a steady ~419-550ms `sweep_pending` task duration even when finding nothing to reclaim or process.

## 3. Old Query/Session Behavior

`reclaim_stale_processing(db, ...)` and `list_pending_images(db, ...)` both already accept an `AsyncSession` parameter — they were written session-agnostic from the start (introduced together in commit `4836a9e`). The two-session split was purely how `run()` orchestrated them, not a constraint of the repository layer. Confirmed via `git log`/`git show` that no test or docstring asserted the two operations *needed* isolation from each other — the split was incidental structure, not a documented safety requirement.

## 4. New Query/Session Behavior

`run()` now opens **one** `AsyncSessionLocal()`, runs both repository calls against it, and issues **one** `db.commit()` at the end:

```python
async def run() -> None:
    pending_ids: list[uuid.UUID] = []
    async with AsyncSessionLocal() as db:
        try:
            reclaimed = await _repo.reclaim_stale_processing(db, stale_after_seconds=STALE_AFTER_SECONDS)
            pending = await _repo.list_pending_images(db, limit=POLL_BATCH_LIMIT)
            pending_ids = [image.id for image in pending]
            await db.commit()
            if reclaimed:
                log.warning("media_generation_reclaimed_stale", count=reclaimed)
        except _TRANSIENT_DB_ERRORS as exc:
            await db.rollback()
            log.warning("media_generation_db_unavailable", error=str(exc))
            return
        except Exception:
            await db.rollback()
            log.exception("media_generation_reclaim_failed")
            return

    for image_id in pending_ids:
        await process_one(image_id)
```

No repository method signatures changed — `reclaim_stale_processing`/`list_pending_images` are called exactly as before, just against a shared session. This matches the explicit guidance to prefer passing a session into existing repository functions over creating hidden nested sessions.

**Safety, verified (not assumed):**
- **Visibility:** within one transaction, `list_pending_images`'s `SELECT` runs *after* `reclaim_stale_processing`'s `UPDATE` in the same uncommitted transaction — Postgres's read-your-own-writes guarantees the SELECT sees the just-reclaimed rows. (Previously this worked too, because session 1 fully committed before session 2 opened — same outcome, different mechanism.)
- **No double-reclaim under concurrent sweeps:** unchanged, guaranteed by Postgres row-locking on the `UPDATE ... WHERE status='processing'` — a second concurrent sweep's UPDATE re-evaluates its WHERE clause against the post-commit state and simply won't match a row the first sweep already flipped to `'pending'`. This guarantee lives in the UPDATE itself, not in session boundaries, so merging sessions doesn't touch it.
- **No double-processing downstream:** unchanged, guaranteed by `try_claim_pending`'s own atomic claim in `process_one()`, entirely independent of how `run()` discovers candidate image IDs.
- **One accepted, bounded, self-healing trade-off:** if the transaction fails *after* the UPDATE succeeds but *before* COMMIT (e.g. the subsequent SELECT hits a transient error), the reclaim rolls back too. This is not a correctness loss — the row is still `'processing'` with a stale `updated_at`, which is exactly what the next tick's `reclaim_stale_processing` WHERE clause is built to catch. Worst case: one extra tick (now 15s, previously 5s) of delay before that specific image is reclaimed. Verified directly: `test_list_failure_after_reclaim_rolls_back_and_skips_processing`.

New round-trip count per tick:

| Step | Round trips |
|---|---|
| `UPDATE ... RETURNING` (reclaim) | 1 |
| `SELECT` (list, same transaction) | 1 |
| `COMMIT` | 1 |
| **Total per tick** | **3** |

## 5. Schedule Change

`app/celery_app.py`'s `beat_schedule["media-sweep-pending"]["schedule"]`: `timedelta(seconds=5)` → `timedelta(seconds=15)`.

**Traced the 5s figure to its actual origin, not assumed it was tuned for this purpose.** It predates the Celery migration entirely — from the deleted `app/workers/queue.py` (APScheduler era), git history (`git show 4836a9e`):

> "Every 5s — the crash-recovery/retry net for image variant generation... **Short interval since an admin waiting on "Generating…" in the editor is the worst case this recovers.**"

This is an important nuance the task brief's framing (evaluate against the 120s stale threshold) doesn't fully capture on its own: the sweep is *also* the fallback for an image that never got claimed at all (fast-path dispatch lost entirely, e.g. a Redis blip at the exact wrong moment) — that case has **no 120s floor**, it's bounded only by the poll interval itself, and it's the scenario the original 5s was explicitly tuned for, not the stale-`'processing'` case.

**Worst-case added delay, both scenarios, stated precisely:**

| Scenario | Before (5s) | After (15s) | Delta |
|---|---|---|---|
| Stale `'processing'` row (worker crashed after claiming) | up to 120 + 5 = 125s | up to 120 + 15 = 135s | +10s |
| Never claimed at all (fast-path dispatch lost) | up to 5s + generation time | up to 15s + generation time | +~10s |

The second scenario is the more material one, since it's admin-visible. The frontend's `pollImageUntilReady` (`Frontend_whole/packages/shared-media/src/mediaApi.ts`) gives the admin a 30s client-side timeout before showing an error. Worst case at the new interval: 15s (poll delay) + typically 1-3s (observed generation time in prior session's `crop_service_phases` logs) ≈ 16-18s — still comfortably inside the 30s budget, with ~12-14s of margin remaining. **Conclusion: 15s is safe**, though it is a more meaningful trade-off than "just" the stale-reclaim math suggests, and is documented as such rather than glossed over.

`STALE_AFTER_SECONDS` (120s) was left unchanged, per instructions — no separate proven reason to touch it.

## 6. Crash-Recovery Semantics

Unaffected. `reclaim_stale_processing`'s WHERE clause, `try_claim_pending`'s atomic claim, `MAX_ATTEMPTS` bookkeeping, and `_handle_failure`'s pending-vs-failed decision are all untouched code. Verified via the full existing `TestProcessOneClaim`/`TestProcessOneSuccess`/`TestProcessOneFailure` suite in `test_media_generation_worker.py` — all pass unmodified, confirming no regression in the parts of the pipeline this change doesn't touch.

## 7. Concurrency Behavior

**What's verified directly:** the per-tick sequencing (reclaim → list → commit, in that order, within one transaction) via `test_stale_and_pending_images_together_processes_all_pending_ids` (asserts call order), and that a mid-transaction failure rolls back everything rather than partially committing, via `test_list_failure_after_reclaim_rolls_back_and_skips_processing`.

**What's verified analytically, not empirically:** true concurrent-transaction race behavior (two `run()` calls' UPDATEs racing at the Postgres row-lock level) requires a live Postgres instance — this repo has no integration-test harness against a real database (`tests/conftest.py` explicitly: "No external service is contacted... integration tests drive the ASGI app in-process without running the lifespan (no DB/Redis needed)"), and no live Docker/DB was available in this environment (see §10). The safety argument is architectural: Postgres's own MVCC/row-locking on `UPDATE ... WHERE status='processing'` is what prevents double-reclaim, not anything in this codebase's session management, and that guarantee is unchanged by merging sessions. This is stated as an analytical conclusion, not claimed as empirically measured — consistent with not fabricating verification that wasn't actually performed.

## 8. Query-Count: Before/After

**Per tick:** 4 round trips → 3 round trips (**25% fewer per tick**).

**Per day**, combining both changes (no live Supabase available in this environment — this is pure arithmetic from the code change and schedule change, not a latency measurement; no millisecond figures are invented here per instructions):

| | Round trips/tick | Ticks/day | Round trips/day |
|---|---|---|---|
| Before | 4 | 17,280 (every 5s) | 69,120 |
| After | 3 | 5,760 (every 15s) | 17,280 |

**Net: 75% fewer daily round trips** attributable to this sweep (69,120 → 17,280).

## 9. Test Results

All new/updated tests target the 13 scenarios requested. Honest mapping — some are true behavioral tests against mocked repository calls, some are SQL-statement-shape checks (since this repo has no live-DB integration harness), one is a repository-invariant check:

| # | Scenario | Test | Method |
|---|---|---|---|
| 1 | Pending image discovered | `TestListPendingImages::test_returns_pending_images` | behavioral (mocked) |
| 2 | Stale processing image reclaimed | `TestReclaimStaleProcessing::test_returns_count_of_reclaimed_images` | behavioral (mocked) |
| 3 | Fresh processing image untouched | `TestReclaimStaleProcessing::test_query_shape_only_matches_stale_processing_rows` | statement-shape |
| 4 | Completed image untouched | same test (status binds to `'processing'` only) + `test_query_shape_excludes_non_pending_and_deleted_rows` (status binds to `'pending'` only) | statement-shape |
| 5 | Deleted image untouched | `TestListPendingImages::test_query_shape_excludes_non_pending_and_deleted_rows` (`deleted_at IS NULL`) + `TestSoftDeleteNeverLeavesAProcessingStatus` (soft_delete always flips status away from `'processing'`, which is what actually protects reclaim, not a `deleted_at` filter there) | statement-shape + invariant |
| 6 | No pending images | `TestRun::test_no_pending_or_stale_images_processes_nothing` | behavioral (mocked) |
| 7 | Stale + pending together | `TestRun::test_stale_and_pending_images_together_processes_all_pending_ids` | behavioral (mocked) |
| 8 | Multiple pending images | `TestRun::test_reclaims_stale_then_processes_each_pending_id` | behavioral (mocked) |
| 9 | Concurrent sweep executions | analytical (§7) + `test_repeated_execution_is_idempotent` as a sequential proxy | analytical + behavioral |
| 10 | Task failure/rollback | `TestRun::test_list_failure_after_reclaim_rolls_back_and_skips_processing`, `test_non_transient_reclaim_error_is_logged_and_swallowed` | behavioral (mocked) |
| 11 | DB session cleanup | `TestRun::test_reclaims_stale_then_processes_each_pending_id` (`session_ctor.assert_called_once()`) | behavioral (mocked) |
| 12 | Worker retry behavior | pre-existing `TestProcessOneFailure` suite (unmodified, unaffected by this change) — re-run to confirm no regression | behavioral (mocked) |
| 13 | Idempotent repeated execution | `TestRun::test_repeated_execution_is_idempotent` | behavioral (mocked) |

**Combining that combining the merge and the schedule change does not change what a resulting state looks like:** `test_reclaims_stale_then_processes_each_pending_id` and `test_stale_and_pending_images_together_processes_all_pending_ids` both assert the exact same `process_one` call set the pre-merge single-session test asserted — the merge changes *how many round trips* it takes to reach that state, not the state itself.

**Full results:**
```
Backend/tests/unit/test_celery_app.py ............ 14 passed
Backend/tests/unit/test_media_repository.py ....... 15 passed  (+5 new)
Backend/tests/unit/test_media_generation_worker.py . 10 passed  (+6 new)

Full backend suite: 1481 passed, 2 skipped, 0 failed  (135.22s)
Black --check:      436 files unchanged
Ruff:                All checks passed
Mypy (app/):          Success: no issues found in 255 source files
```
The 2 skipped and pre-existing `RuntimeWarning: coroutine ... was never awaited` warnings are in unrelated files (`test_service_mocks.py`, `test_service_notifications.py`, `test_service_reviews.py`, `test_service_reviews_support_wishlist.py`) untouched by this work — pre-existing, not introduced here.

## 10. Docker Verification

**Not performed — reported honestly rather than fabricated.** `docker ps` in this environment returned:
```
error during connect: Get "http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/...": open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```
Docker Desktop's daemon is not running in this sandbox. Per instructions ("If live Docker + DB is available, measure actual behavior... otherwise report query-count reduction only"), §8 above is the query-count report; no live-Beat-dispatch or live-worker-execution claim is made.

**What *is* verified without a live daemon:** `test_celery_app.py::TestBeatSchedule` directly inspects the real `celery_app.conf.beat_schedule` dict that a live Beat process would load — `test_interval_schedules_match_former_apscheduler_cadences` confirms the `media-sweep-pending` entry is `timedelta(seconds=15)` and routes to `media.sweep_pending`, and `test_every_former_apscheduler_job_has_exactly_one_beat_entry` confirms there are still exactly 6 entries (no duplicate/missing schedule introduced). `TestApiNoLongerStartsAScheduler` (pre-existing, re-run, passing) confirms no APScheduler reference remains in `app/main.py`. This proves the *configuration* is correct; it does not prove a live Beat process dispatches on schedule, which needs the Docker stack this environment doesn't have running.

## 11. Remaining Risks

- **Concurrent-transaction locking is unverified empirically** (§7) — architecturally sound per Postgres semantics and the existing atomic-claim design, but not exercised against a real database in this pass. Recommend a real staging-environment smoke test (create a stale `'processing'` row, confirm it's reclaimed within ~15-30s) before/shortly after deploy, since that's cheap and closes the one gap this environment couldn't close.
- **Docker/Beat live-dispatch unverified** (§10) — same recommendation: confirm in staging/production logs after deploy that `media-sweep-pending` fires every 15s, not 5s (the task notification logs already show the format to look for: `Scheduler: Sending due task media-sweep-pending`).
- **The "never-claimed fallback" scenario's admin-visible worst-case grew from ~8s to ~18s** (§5) — still within the 30s client timeout with real margin, but if `pollImageUntilReady`'s timeout is ever tightened independently in the future, this trade-off should be re-examined together with it rather than treated as permanently settled.

---

## Final Conclusion

**PASS — optimization safe and verified**, with two items (concurrent-transaction locking, live Beat dispatch) verified analytically/by configuration rather than empirically against a live Postgres/Docker stack, because neither was available in this environment. Both are flagged explicitly in §11 as cheap, specific follow-up checks for staging rather than open questions about correctness.
