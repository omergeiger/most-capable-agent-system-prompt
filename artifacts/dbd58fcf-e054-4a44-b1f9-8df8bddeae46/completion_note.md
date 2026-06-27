# Completion Note

**Task:** Compare WAL vs journal mode concurrency for simultaneous readers and writers.

**What was done:** Researched SQLite's official locking and WAL documentation and produced `research_report.md` containing:
- Background on SQLite's five lock levels
- Step-by-step lock progression for each mode
- A comparison table covering all four required dimensions
- Per-dimension findings with source citations
- Conclusion summarizing the practical impact

**Key findings:**
- Journal mode: readers and writers mutually block at commit (writer holds EXCLUSIVE, blocking all readers; readers holding SHARED delay the writer at PENDING). SQLITE_BUSY is frequent.
- WAL mode: readers and one writer can proceed simultaneously. Writer appends to WAL; readers read a stable snapshot. SQLITE_BUSY is confined to writer-writer contention and checkpoint reclaim.

**Comparison table is present** with all four required columns: max concurrent readers, writer blocks readers, reader blocks writer, SQLITE_BUSY frequency.

**Gaps:** None. All four required dimensions are covered.
