# Research Report: SQLite Journal Mode Internals

**Task ID:** 4245d4b0-46fe-4c09-9582-a9b98d106043  
**Date:** 2026-06-26  
**Scope:** Default journal mode mechanics, exclusive locking during writes, reader blocking; out of scope: WAL mode, benchmarking

---

## Question

How does SQLite's rollback journal work? Specifically: the write sequence when a transaction commits, the lock escalation protocol (shared -> reserved -> exclusive), how concurrent readers are blocked during a write, and what differs between the DELETE/TRUNCATE/PERSIST/MEMORY journal mode variants.

---

## Sources

1. **SQLite Atomic Commit** - https://www.sqlite.org/atomiccommit.html  
   *Primary SQLite documentation. High confidence.*

2. **SQLite Locking and Concurrency in Version 3** - https://www.sqlite.org/lockingv3.html  
   *Primary SQLite documentation. High confidence.*

3. **SQLite PRAGMA Reference (journal_mode)** - https://www.sqlite.org/pragma.html#pragma_journal_mode  
   *Primary SQLite documentation. High confidence.*

---

## Findings

### 1. Rollback Journal Write Sequence

The rollback journal exists to make transactions atomic: before modifying any database page, SQLite saves the original version of that page to the journal file. If the process crashes mid-transaction, recovery replays the journal to restore the database.

**Step-by-step write sequence (DELETE mode, the default):**

1. Writer acquires a **SHARED lock** on the database file (allows concurrent reads).
2. Writer escalates to a **RESERVED lock** - signals intent to write. At this point, no other writer can start, but existing and new readers are still allowed.
3. SQLite creates the rollback journal file on disk. The journal header is written with a page count of **zero** initially.
4. For each page to be modified, SQLite writes the *original* page content into the journal (saving what was there before the change).
5. All journal page data is flushed to disk (fsync). Only after this flush is confirmed:
6. The journal header is updated with the **actual page count** (making the journal valid for recovery), then flushed again.
7. Pages are modified in the in-memory page cache (user space only at this point - not yet on disk). Other connections still see unchanged data from the OS page cache.
8. Writer escalates to **PENDING lock** - new readers are blocked from connecting.
9. Writer escalates to **EXCLUSIVE lock** - all existing shared locks must clear first.
10. Modified pages are written to the database file and flushed to disk.
11. The journal is deleted (DELETE mode) - this deletion is the **atomic commit point**.
12. Locks are released.

**Why the two-phase journal header write matters:**  
According to https://www.sqlite.org/atomiccommit.html, section 3.7, the page count starts at zero and is only updated after all page content is safely flushed. If power fails during the first flush, the page count stays at zero, which signals an incomplete/invalid journal. Recovery treats a zero page count as "no changes to replay" and safely ignores the orphaned journal file. This is the mechanism that makes crash recovery safe.

**Sector alignment rule:**  
SQLite always journals *all pages within an affected disk sector*, not just the one being modified. If a page shares a sector with pages the transaction doesn't touch, those neighboring pages are journaled too. This guards against the hardware behavior where writing a sector rewrites all its bytes, potentially corrupting adjacent pages if power fails mid-write.

**Checksums (secondary defense):**  
At `PRAGMA synchronous=NORMAL`, SQLite adds 32-bit checksums to each journal page. During rollback, if a checksum fails, the journal replay is abandoned. This is a probabilistic secondary defense against the "garbage data in an extended file" hazard (where the OS extends the file's size before writing content).

---

### 2. Lock Escalation Protocol

SQLite uses five lock states on the database file. The pager module tracks four of them; the OS-level VFS layer tracks all five.

**The five states:**

| State | Who can coexist | Purpose |
|-------|----------------|---------|
| UNLOCKED | Anyone | Default; no access |
| SHARED | Multiple SHARED holders | Concurrent reads |
| RESERVED | One RESERVED + any SHARED | Signals write intent; readers still admitted |
| PENDING | One PENDING + existing SHARED only | Blocks new readers; waits for existing ones to finish |
| EXCLUSIVE | Nobody else | Sole access for writing |

**Escalation sequence during a write transaction:**

```
UNLOCKED
  -> SHARED       (acquired on first SELECT)
  -> RESERVED     (acquired on first INSERT/UPDATE/DELETE)
  -> PENDING      (acquired when ready to commit or when cache must spill to disk)
  -> EXCLUSIVE    (acquired when all existing SHARED holders have released)
  -> write database pages
  -> delete journal (commit point)
  -> release EXCLUSIVE, PENDING, SHARED
  -> UNLOCKED
```

According to https://www.sqlite.org/lockingv3.html: "Only a single RESERVED lock can be active at a time." This means only one writer can be preparing to write at a time, even though reads continue freely during that preparation phase.

**PENDING lock and writer starvation:**  
SQLite v2 had a writer starvation bug: if a stream of readers continuously acquired SHARED locks, a writer could be blocked indefinitely because it could never find a window where no SHARED locks were held. SQLite v3 introduced the PENDING lock to solve this. Once a writer acquires PENDING, no new SHARED locks are allowed. Existing readers finish naturally and release their locks. Once the last existing SHARED lock clears, the writer escalates to EXCLUSIVE.

The PENDING lock is never surfaced in the pager module's state machine - it's treated as a transient implementation detail of the OS-level lock file operations.

---

### 3. How Concurrent Reads Are Blocked During Writes

**Phase 1 - SHARED lock held by writer:**  
Other readers can still acquire SHARED locks freely. They see pre-transaction data from the OS page cache. The writer's in-memory changes are not visible to them.

**Phase 2 - RESERVED lock held by writer:**  
Reads continue unblocked. The writer is modifying pages in its own memory. No on-disk changes have been made to the database file. New readers can connect and read the pre-transaction state.

**Phase 3 - PENDING lock held by writer:**  
New readers are blocked from acquiring SHARED locks. Readers that already hold SHARED locks are allowed to continue reading (they see pre-transaction state). The writer waits for those existing SHARED locks to clear.

**Phase 4 - EXCLUSIVE lock held by writer:**  
No other connection holds any lock. No new reads or writes are permitted. The writer flushes modified pages to the database file. From other connections' perspectives, the database is inaccessible until the EXCLUSIVE lock is released.

**After commit:**  
The EXCLUSIVE lock is released. New readers see the post-transaction state. No reader ever observes a partial/intermediate database state, because no data reaches the database file until the writer holds an EXCLUSIVE lock, and the lock is not released until the commit is complete and the journal is deleted.

**Key quote** from https://www.sqlite.org/atomiccommit.html, section 3.6:  
> "Changes that are made in user space are only visible to the database connection that is making the changes. Other database connections still see the information in operating system disk cache buffers which have not yet been changed."

---

### 4. Journal Mode Variants (DELETE / TRUNCATE / PERSIST / MEMORY)

All four modes use the same rollback journal write sequence and the same lock escalation protocol. They differ only in what happens to the journal file at commit time.

#### DELETE (default)

- **Commit action:** Delete the journal file from disk.
- **Recovery signal:** Journal file absent = transaction committed. Journal file present = hot journal, must roll back.
- **Cost:** Directory metadata must be updated; disk sectors may be deallocated. On many filesystems this is the most expensive of the four options.
- **Recovery:** If a crash leaves the journal file present and non-empty with a valid header and page count, SQLite treats it as a "hot journal" and replays the rollback on next open.

#### TRUNCATE

- **Commit action:** Truncate the journal file to zero bytes (file remains on disk, but is empty).
- **Recovery signal:** Zero-length journal = transaction committed. Non-zero journal = hot journal.
- **Cost:** Avoids directory metadata updates and sector deallocation. Truncation is atomic and synchronous on most modern filesystems, making this faster than DELETE on those systems.
- **Caveat:** On embedded systems with synchronous filesystems, truncation may be slower than simply zeroing the header (PERSIST is better there).

#### PERSIST

- **Commit action:** Overwrite the first bytes of the journal header with zeros. File stays on disk at its current size.
- **Recovery signal:** A zeroed header = no valid journal = transaction committed. A valid header with non-zero page count = hot journal.
- **Cost:** No directory modification, no deallocation. Just a single sector overwrite. Fastest option for filesystems where deletion or truncation is expensive (common on embedded/mobile platforms).
- **Size management:** Works with `PRAGMA journal_size_limit` to cap how large the journal file can grow across transactions.
- **Subsequent transactions:** New transactions overwrite the existing journal content in-place rather than appending to a freshly created file. This can be faster since the inode already exists.

#### MEMORY

- **Commit action:** Nothing - the journal was never on disk. It lives entirely in RAM.
- **Recovery signal:** None. If the process crashes, the in-memory journal is gone. The database file may be in a partially written state with no journal to roll it back.
- **Safety:** Explicitly unsafe. According to https://www.sqlite.org/pragma.html: "If the application using SQLite crashes in the middle of a transaction when the MEMORY journaling mode is set, then the database file will very likely go corrupt."
- **Appropriate use:** Testing, ephemeral/in-memory databases, or workloads where data loss on crash is acceptable.

**Comparison table:**

| Mode | Journal file after commit | Directory ops | Sector ops | Crash safety |
|------|--------------------------|--------------|-----------|-------------|
| DELETE | Deleted | Yes | Yes (dealloc) | ACID |
| TRUNCATE | Zero-length | No | Truncate only | ACID |
| PERSIST | Header zeroed, file stays | No | One write | ACID |
| MEMORY | N/A (RAM only) | No | None | Unsafe - corruption risk |

---

## Contradictions / Uncertainties

- **TRUNCATE vs PERSIST speed:** The primary SQLite docs note that TRUNCATE is faster than DELETE on most modern filesystems, but on embedded systems with synchronous VFS layers PERSIST is faster than TRUNCATE. The ranking depends on the target OS. No contradiction between sources; this is a documented platform-dependency.

- **"Atomic" journal deletion in DELETE mode:** The docs describe the journal deletion as the commit point, treating it as effectively atomic from the application's perspective. In practice, filesystem directory entry removal is not guaranteed atomic at the hardware level on all systems. SQLite accounts for this via the hot-journal detection logic (if the file still exists after a crash, it is rolled back). This is consistent across all sources.

---

## Conclusion

SQLite's rollback journal provides atomicity through a write-original-then-modify pattern: save original page content to journal first, flush to disk, then modify the database. The two-phase journal header (write content, then set page count) is the key mechanism ensuring a crashed journal is always either fully valid or safely ignorable.

The lock escalation (SHARED -> RESERVED -> PENDING -> EXCLUSIVE) is designed so reads are unblocked for as long as possible. The PENDING lock is the deliberate solution to writer starvation: it closes the door to new readers while existing readers drain naturally.

The four non-WAL journal modes are functionally identical in terms of ACID semantics (except MEMORY); they differ only in what filesystem operation signals "commit complete": DELETE removes the file, TRUNCATE empties it, PERSIST zeros its header, and MEMORY never writes it at all. For the harness's SQLite usage (tasks.db), the default DELETE mode is safe and appropriate unless running on a filesystem where deletion overhead is measurably expensive.
