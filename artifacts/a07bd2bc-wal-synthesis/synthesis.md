# SQLite WAL vs Journal Mode - Synthesis and Recommendation

**Goal:** 101934b2 | **Synthesis task:** a07bd2bc  
**Date:** 2026-06-27

---

## Summary

This document synthesizes three research tasks on SQLite's two durability mechanisms. The recommendation applies to the agent harness (tasks.db) which runs with concurrent reads (worker scanning task queue) and single-writer patterns (claim_task, mark done).

---

## WAL Mode Internals

- Each write transaction appends 24-byte header + full page frames to a `-wal` file; the main database file is untouched until checkpoint.
- Readers capture `mxFrame` at transaction start and consult the WAL-index hash table. Writers append beyond `mxFrame` and hold `WAL_WRITE_LOCK` exclusively - but readers and writers lock different byte ranges, so they never contend.
- Autocheckpoint defaults to 1000 frames (~4 MB). Passive checkpoint runs after every `COMMIT` crossing the threshold. Three stronger modes (FULL, RESTART, TRUNCATE) block until all readers clear.
- WAL growth risk: checkpoint starvation from long-running readers, disabled autocheckpoint, large single transactions. Mitigations: short read transactions, FULL/RESTART checkpoints in low-activity windows, `journal_size_limit`.
- Requires local filesystem. NFS incompatible (`.shm` file is memory-mapped and never synced to disk).

---

## Journal Mode Internals

- Original page content is saved to a rollback journal before modifying the database. Journal header page count is written as 0 until all page data flushes - making crash recovery safe at any point.
- Lock escalation: SHARED (read) -> RESERVED (write intent) -> PENDING (blocks new readers, drains existing) -> EXCLUSIVE (sole access, writes database).
- PENDING lock is the key mechanism preventing writer starvation from a continuous stream of readers.
- Mode variants: DELETE/TRUNCATE/PERSIST are all ACID-safe (differ only in the on-disk signal for "committed"). MEMORY is unsafe - journal lives in RAM, crashes cause corruption.

---

## Concurrency Comparison

| Property | Journal Mode | WAL Mode |
|---|---|---|
| Max concurrent readers | Unlimited (while no EXCLUSIVE held) | Unlimited |
| Writer blocks readers | Yes (EXCLUSIVE during commit) | No |
| Reader blocks writer | Yes (waits for SHARED to clear) | No |
| Concurrent readers + writer | No | Yes |
| SQLITE_BUSY frequency | High under any contention | Low (writer-writer only) |
| NFS compatible | Yes | No |
| Crash recovery | Rollback journal | WAL replay |

---

## Recommendation: WAL Mode for tasks.db

**Use WAL mode.** The harness access pattern is read-heavy with infrequent single-writer commits:

- `worker.py` scans for pending tasks frequently
- `claim_task.py` locks one task at a time
- `scan.py` reads the whole queue periodically

Under journal mode, every `claim_task` commit holds an EXCLUSIVE lock, blocking all concurrent reads. Under WAL, the worker can keep scanning while a claim commits. This eliminates the main source of `SQLITE_BUSY` errors in the harness.

**Implementation:** Add this to `scripts/init_db.py` after `connect()`:

```python
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA wal_autocheckpoint=500")  # checkpoint at ~2MB, not default 4MB
```

**Caveats:**
- Only applies to local filesystem (already satisfied - tasks.db is local only)
- Monitor WAL file size if long-running reader sessions are added later
- FULL checkpoint should be run during shutdown if WAL file grows unexpectedly

---

## Status

This synthesis completes goal 101934b2. The WAL pragma change is a low-risk improvement to queue in the Milestone 3 task list.
