# SQLite Concurrency Models: WAL vs Journal Mode

## Research Question

How do SQLite's WAL (Write-Ahead Log) and default rollback-journal modes differ in their handling of simultaneous readers and writers?

---

## Sources

1. **SQLite WAL documentation** - https://www.sqlite.org/wal.html (primary source; high confidence)
2. **SQLite locking and concurrency documentation** - https://www.sqlite.org/lockingv3.html (primary source; high confidence)
3. **SQLite PRAGMA journal_mode** - https://www.sqlite.org/pragma.html#pragma_journal_mode (primary source; high confidence)
4. **SQLite transaction semantics** - https://www.sqlite.org/lang_transaction.html (primary source; high confidence)

All claims below are drawn from SQLite's own official documentation.

---

## Background: Lock Levels

SQLite uses five lock levels on the database file:

| Lock | Meaning |
|------|---------|
| UNLOCKED | No lock held |
| SHARED | Reading; multiple SHARED locks can coexist |
| RESERVED | Writer intends to write; readers can still enter |
| PENDING | Writer waiting for readers to clear |
| EXCLUSIVE | Writer is committing; no other access permitted |

---

## Journal Mode (Rollback Journal / DELETE mode)

This is the SQLite default. The journal file records page images *before* modification so changes can be rolled back.

### Lock Progression for a Write Transaction

1. Writer acquires **RESERVED** lock - new readers are still allowed in.
2. Writer modifies pages in memory and writes the journal file.
3. Writer promotes to **PENDING** lock - no new SHARED locks are granted.
4. Writer waits for all existing SHARED locks to clear.
5. Writer acquires **EXCLUSIVE** lock - all reads are now blocked.
6. Writer flushes pages to the database file and commits.
7. Journal file is deleted (in DELETE mode). EXCLUSIVE lock released.

### Concurrency Properties

- **Readers block the writer:** Yes. While any SHARED lock is held, the writer cannot acquire EXCLUSIVE and is blocked at the PENDING stage.
- **Writer blocks readers:** Yes. Once the writer reaches PENDING, no new readers can begin. Once EXCLUSIVE is held, all readers are blocked.
- **Max concurrent readers:** Unlimited - while no EXCLUSIVE lock is held, any number of SHARED locks can coexist. However, as soon as a writer reaches PENDING, zero new readers can enter, and it waits for current readers to finish before proceeding.
- **Concurrent readers AND writer:** Not possible simultaneously once commit begins.

### SQLITE_BUSY in Journal Mode

`SQLITE_BUSY` is returned when a connection tries to acquire a lock that another connection holds:

- Reader returns `SQLITE_BUSY` when trying to acquire SHARED while writer holds EXCLUSIVE.
- Writer returns `SQLITE_BUSY` when trying to promote from PENDING to EXCLUSIVE while readers hold SHARED.
- **Frequency: HIGH** - any overlap between a write commit phase and active reads produces SQLITE_BUSY.

---

## WAL Mode (Write-Ahead Log)

Introduced in SQLite 3.7.0 (2010-07-22). Writers append changed pages to a separate WAL file instead of writing directly to the database file. Readers consult the WAL to find the latest version of any page.

### Lock Progression for a Write Transaction (WAL)

1. Writer acquires a **write lock** on the WAL index (a shared-memory structure).
2. Writer appends modified pages to the WAL file.
3. Writer commits by writing a commit frame to the WAL. No lock on the main database file is ever needed for normal writes.
4. Readers already in progress are unaffected - they see only the WAL frames that existed when they started.

**Checkpoint:** Periodically (default: every 1000 WAL pages), SQLite copies WAL pages back into the main database file. A checkpoint must wait for all readers that could be reading those WAL frames to finish, then acquires an EXCLUSIVE lock on the database file briefly. This is the only moment WAL-mode resembles journal-mode locking.

### Concurrency Properties

- **Readers block the writer:** No. Readers hold no lock that prevents a writer from appending to the WAL.
- **Writer blocks readers:** No. Readers continue reading the snapshot they began on, unaffected by new WAL frames the writer appends.
- **Concurrent readers AND writer:** Yes - this is the key WAL advantage. Multiple readers and one writer can all proceed simultaneously.
- **Max concurrent readers:** Unlimited. Multiple readers can read concurrently with each other and with an active writer.
- **Multiple concurrent writers:** No. WAL still serializes writers - only one write transaction can be active at a time. A second writer returns `SQLITE_BUSY` and must retry.

### SQLITE_BUSY in WAL Mode

- `SQLITE_BUSY` is returned when a second writer tries to start while a writer is already active.
- `SQLITE_BUSY` can occur during checkpoint if readers hold positions in the WAL that the checkpoint needs to reclaim.
- **Frequency: LOW** under typical mixed read/write workloads. SQLITE_BUSY only surfaces under write-write contention or during checkpoint operations.

---

## Comparison Table

| Property | Journal Mode (DELETE) | WAL Mode |
|---|---|---|
| **Max concurrent readers** | Unlimited (while no EXCLUSIVE held) | Unlimited |
| **Writer blocks readers** | Yes (during EXCLUSIVE commit phase) | No |
| **Reader blocks writer** | Yes (writer waits at PENDING for readers to clear) | No |
| **Concurrent readers + writer** | No (mutually exclusive at commit) | Yes |
| **Concurrent writers** | No (serialized) | No (serialized) |
| **SQLITE_BUSY frequency** | High (reader/writer overlap) | Low (writer/writer only, plus checkpoint) |
| **SQLITE_BUSY triggers** | Any read/write overlap at commit | Concurrent writers; checkpoint reclaim |
| **Write serialization** | One writer, readers excluded at commit | One writer, readers proceed unblocked |
| **Checkpoint needed** | No (journal deleted on commit) | Yes (WAL must be periodically flushed back to DB) |

---

## Findings

### Max Concurrent Readers

Both modes support unlimited concurrent readers. In journal mode this is contingent on no writer holding EXCLUSIVE; in WAL mode it is unconditional.

According to the SQLite WAL documentation: "WAL mode allows concurrent readers and one writer to proceed at the same time. A writer does not prevent readers from accessing the database file."

### Writer Blocks Readers

- **Journal mode: Yes.** At commit, the writer must hold EXCLUSIVE, which prevents all readers. Any reader that arrives during EXCLUSIVE will receive SQLITE_BUSY.
- **WAL mode: No.** Readers always read against a snapshot; new WAL frames written by the writer are invisible to in-progress readers and do not block them.

### Reader Blocks Writer

- **Journal mode: Yes.** The writer must wait for all SHARED locks to clear before it can upgrade to EXCLUSIVE. Long-running read transactions directly delay write commits.
- **WAL mode: No.** The writer appends to the WAL without acquiring a lock on the main database file. Existing readers do not block it.

### SQLITE_BUSY Frequency

- **Journal mode:** SQLITE_BUSY is common whenever a reader is active during a write commit or vice versa. Under any mixed workload it will appear regularly.
- **WAL mode:** SQLITE_BUSY appears only when two writers attempt to write simultaneously, or when a checkpoint attempts to reclaim WAL frames that active readers still reference. Under read-heavy or balanced workloads, it is rare.

---

## Contradictions / Notes

No contradictions found across sources - WAL's behavior is well-specified and consistent across all SQLite documentation.

One nuance: WAL mode introduces a new failure mode that journal mode does not have - if readers hold very old WAL frames open for a long time, the WAL file cannot be checkpointed and will grow without bound. This is a resource concern, not a correctness concern, and is out of scope for this task.

---

## Conclusion

WAL mode provides substantially better reader-writer concurrency than journal mode. The core difference is architectural: journal mode requires an EXCLUSIVE lock on the database file during commit (blocking all readers), while WAL mode allows readers to continue against a stable snapshot while the writer appends to a separate file. The practical result is that SQLITE_BUSY under WAL is confined to writer-writer contention, which is typically infrequent, whereas journal mode generates SQLITE_BUSY whenever any read and write commit overlap.

For workloads with concurrent reads and writes, WAL mode is the correct choice. Journal mode is appropriate only for single-writer, batch, or write-only workloads where the locking overhead is acceptable.
