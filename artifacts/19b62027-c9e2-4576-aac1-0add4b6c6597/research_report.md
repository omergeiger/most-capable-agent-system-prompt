# SQLite WAL Mode Internals - Research Report

**Task:** 19b62027-c9e2-4576-aac1-0add4b6c6597
**Date:** 2026-06-26
**Risk level:** low (summarizing primary public documentation)

---

## Research Question

How does SQLite Write-Ahead Logging (WAL) mode work internally? Specifically:
1. WAL append mechanics
2. How readers and writers coexist without blocking each other
3. Checkpoint trigger conditions (wal_autocheckpoint)
4. WAL size growth risk

---

## Sources

1. **sqlite.org/wal.html** - Primary WAL conceptual documentation (high confidence)
2. **sqlite.org/fileformat2.html** - WAL binary file format specification (high confidence)
3. **sqlite.org/walformat.html** - WAL-index (.shm) format and locking protocol (high confidence)

All three sources are official SQLite documentation. No contradictions found across them.

---

## Findings

### 1. WAL Append Mechanics

In rollback-journal mode, SQLite writes original page content to a journal file before modifying the database. WAL inverts this: the database file is never modified during a transaction. Instead, changed pages are **appended** as frames to the WAL file (`<database>-wal`).

**Write path:**
- Every write transaction appends one or more frames to the WAL.
- Each frame = 24-byte header + one full page of data.
- A transaction is committed by appending a special commit frame (frame header field "size of database" is non-zero) and calling `fsync` on the WAL file.
- The original database file is not touched until a checkpoint runs.

**WAL file binary layout:**

```
[32-byte WAL header]
[24-byte frame header][page data]    <- frame 1
[24-byte frame header][page data]    <- frame 2
...
```

WAL header fields (big-endian 32-bit integers):

| Offset | Field | Notes |
|--------|-------|-------|
| 0 | Magic number | `0x377f0682` (LE) or `0x377f0683` (BE) |
| 4 | Format version | Currently `3007000` |
| 8 | Page size | e.g., 4096 |
| 12 | Checkpoint sequence number | Incremented each checkpoint |
| 16 | Salt-1 | Random; incremented each WAL reset |
| 20 | Salt-2 | Random; re-randomized each WAL reset |
| 24-28 | Checksums | Cover first 24 bytes of header |

Frame header fields:

| Offset | Field | Notes |
|--------|-------|-------|
| 0 | Page number | Which database page this frame carries |
| 4 | Commit size | Non-zero = commit frame; value = total DB pages after commit |
| 8-12 | Salt-1, Salt-2 | Copied from WAL header; used for frame validity |
| 16-20 | Checksum-1/2 | Cumulative Fibonacci-weighted checksum |

**Frame validity:** A frame is valid only if (a) its salt values match the current WAL header and (b) its checksum is correct. This mechanism automatically invalidates leftover frames from a prior WAL cycle after the WAL is reset (salt values change), preventing stale frames from being checkpointed twice.

**WAL reset:** After a complete checkpoint, the next write transaction resets the WAL by incrementing Salt-1 and re-randomizing Salt-2, then writing new frames starting at offset 32 (overwriting the old ones). The WAL file is not truncated by default - it is overwritten in place, which avoids filesystem reallocation overhead.

According to sqlite.org/wal.html: "Beginning with version 3.22.0 (2018-01-22), if the last connection to a database crashed without checkpointing the WAL, then the first new connection to open the WAL will do a checkpoint as part of the process of opening the WAL."

---

### 2. Reader/Writer Non-Blocking

The central insight of WAL is that readers always read from the database file while writers only append to the WAL. This separates read and write I/O paths entirely.

**How readers work:**

At the start of a read transaction, a reader reads `mxFrame` from the WAL-index header. `mxFrame` is the index of the last valid commit frame in the WAL. This value becomes the reader's **end mark** for the duration of the transaction - it sees a consistent snapshot of the database as it existed at that point.

For each page the reader needs:
1. Check the WAL-index hash table for the highest-numbered frame <= `mxFrame` that contains that page.
2. If found, read that frame from the WAL file.
3. If not found (page has no WAL entry at or before end mark), read the page from the original database file.

This means a reader always sees a coherent point-in-time snapshot, regardless of what writers are doing concurrently.

**How writers work:**

Writers simply append new frames after the current `mxFrame`. They hold `WAL_WRITE_LOCK` (exclusive) while doing so - only one writer at a time. After appending all frames and the commit frame, the writer updates `mxFrame` in the WAL-index and releases the lock.

**Why they don't block each other:**

- Writers only append to the end of the WAL; they never modify the database file or existing WAL frames.
- Readers hold a shared lock on one of five `WAL_READ_LOCK(N)` slots in the `.shm` file, recording their end mark in `read-mark[N]`.
- Readers and writers use different byte ranges for locking, so they never contend.
- Multiple concurrent readers can hold `WAL_READ_LOCK(N)` simultaneously (shared lock semantics).

**The five read-mark slots:**

The WAL-index header at bytes 100-119 contains five 32-bit `read-mark` values, each paired with a `WAL_READ_LOCK(N)` byte in the shared memory. Readers acquire a shared lock on one slot and write their end mark (current `mxFrame`) into it. `read-mark[0]` is always zero; holding `WAL_READ_LOCK(0)` is a promise to not use the WAL at all (reads only from the database file).

According to walformat.html: "While holding shared lock on WAL_READ_LOCK(N): Connection promises to use WAL for pages modified by first read-mark[N] entries."

---

### 3. Checkpoint Trigger Conditions

A checkpoint copies frames from the WAL back into the database file, allowing the WAL to be reused from the beginning.

**Automatic checkpoint (wal_autocheckpoint):**

- Triggered after any `COMMIT` that causes the WAL to contain >= 1000 frames (default).
- Default threshold is 1000 pages (~4 MB at 4096 bytes/page).
- This is a **passive** checkpoint: it does as much work as possible without blocking readers or writers. If a reader holds an end mark at frame 200 and the WAL has 1000 frames, the checkpoint can only copy frames 1-200 into the database safely.
- Configuration: `PRAGMA wal_autocheckpoint=N` or `sqlite3_wal_autocheckpoint()`.
- A final checkpoint also runs when the **last database connection closes**.

**Manual checkpoints:**

Three modes via `sqlite3_wal_checkpoint_v2()`:

| Mode | Behavior |
|------|----------|
| PASSIVE | Never blocks; returns after copying all it can without waiting |
| FULL | Waits for all current readers to finish, then checkpoints to current `mxFrame` |
| RESTART | Like FULL but also waits for all readers to finish past the checkpoint point, enabling WAL reset |
| TRUNCATE | Like RESTART but also truncates the WAL file to zero bytes |

Also available: `PRAGMA wal_checkpoint`, `sqlite3_wal_checkpoint()` (PASSIVE only), `sqlite3_wal_hook()` to register a callback on each WAL commit.

**How the checkpoint determines the safe boundary:**

The checkpoint process acquires `WAL_CKPT_LOCK` (exclusive), then scans all held `WAL_READ_LOCK(N)` slots (N=1..4). For each active reader, it reads that reader's `read-mark[N]`. The checkpoint boundary is the minimum of all active `read-mark[N]` values. Frames beyond that boundary cannot be moved into the database because a live reader depends on reading them from the WAL.

The `nBackfill` field (WAL-index header offset 96) tracks how many frames have been successfully written back to the database. It only increases during checkpointing. The WAL can be reset (and reused from frame 1) only when `nBackfill == mxFrame` and no readers hold `WAL_READ_LOCK(N > 0)`.

---

### 4. WAL Size Growth Risk

Because WAL resets require all readers to have read past the checkpoint point, the WAL file can grow unboundedly under certain conditions.

**Risk scenario 1 - Checkpoint starvation:**

If there is always at least one reader with an open transaction, the checkpoint can never complete fully. Each new reader grabs the current `mxFrame` as its end mark, and new writers keep appending beyond it. The WAL keeps growing.

- Manifestation: WAL file grows continuously; database file is never updated.
- Solution: Ensure there are periods when no readers are active ("reader gaps"), and run checkpoints during those gaps. The FULL or RESTART checkpoint modes can block until such a gap occurs.

**Risk scenario 2 - Disabled autocheckpoint:**

Setting `PRAGMA wal_autocheckpoint=0` (or `-1`) disables automatic checkpoints entirely. Without them, nothing reclaims WAL space except manual checkpoint calls.

**Risk scenario 3 - Large transactions:**

A single write transaction that touches many pages produces a proportionally large WAL file. The checkpoint cannot run until the transaction commits. In SQLite >= 3.11.0, each page appears in the WAL only once per transaction. In older versions, the same page could be written multiple times, making large transactions even worse.

**Risk scenario 4 - Write-heavy concurrent workloads:**

If writes are continuous and the autocheckpoint threshold is hit repeatedly but the checkpoint always finds an active reader, the WAL grows in steps of ~1000 frames each time.

**Monitoring and mitigation:**

- Monitor WAL file size via filesystem (`<database>-wal`).
- Set `PRAGMA journal_size_limit=N` to force truncation after checkpoints (WAL is truncated to N bytes if possible).
- Run FULL or RESTART checkpoints during known low-activity windows.
- Consider a dedicated checkpoint thread that calls `sqlite3_wal_checkpoint_v2(SQLITE_CHECKPOINT_RESTART)` periodically.
- Keep read transactions short to minimize the window during which the WAL cannot be reset.

**Relationship between WAL size and the `.shm` file:**

The `.shm` file (WAL-index) grows in 32 KiB hash-table blocks as the WAL grows, but it rarely exceeds 32 KiB under normal workloads. It is rebuilt from scratch after a crash and is safe to delete when no connections are open (SQLite rebuilds it on next open).

---

## The `.shm` Shared-Memory File

The WAL-index file (`<database>-shm`) is an ordinary file that all processes memory-map simultaneously. It serves as the shared coordination structure.

Key properties:
- **Never synced to disk.** Its contents are reconstructed from the WAL on recovery.
- **Rarely exceeds 32 KiB** in normal use.
- **Must reside on a local filesystem.** WAL mode cannot be used on NFS or other network filesystems because all processes sharing the database must be able to memory-map the same file.
- **Created** when the first connection opens in WAL mode; **deleted** when the last connection closes.
- Layout: a 136-byte header (with `mxFrame`, `nBackfill`, salt, checksums, and the five `read-mark` values), followed by 32 KiB hash-table segments as needed.

---

## Contradictions Across Sources

None found. All three sources are consistent and complementary - wal.html provides the conceptual model, fileformat2.html provides the binary layout, and walformat.html provides the locking and index protocol detail.

---

## Conclusion

SQLite WAL mode achieves non-blocking reader/writer concurrency through three mechanisms working together:

1. **Append-only writes to the WAL** keep the database file stable for readers.
2. **Per-reader end marks** (recorded in `read-mark[N]` slots of the `.shm` WAL-index) give each reader a consistent snapshot without coordination overhead.
3. **Checkpoint boundary logic** that respects all active `read-mark[N]` values ensures data is only transferred back to the database when it is safe.

The primary operational risk is **WAL growth under checkpoint starvation**: if readers hold transactions open continuously, the WAL accumulates frames without bound. This is mitigated by short read transactions, FULL/RESTART checkpoint modes, and `journal_size_limit`.
