# Task Completion Note

**Task:** Audit worker.py subprocess call for claude CLI flag compatibility

**Result:** PASS - no changes needed

## Findings

The invocation at `scripts/worker.py:203-207` is:

```python
result = subprocess.run(
    ["claude", "--print", "--output-format", "json", prompt],
    capture_output=True, text=True,
    timeout=TASK_TIMEOUT, cwd=REPO_ROOT,
)
```

Both flags are valid per `claude --help`:

- `--print` (alias `-p`): accepted, runs non-interactive and exits
- `--output-format json`: accepted (choices: "text", "json", "stream-json"), requires `--print`

The combination `--print --output-format json` is exactly what the help text describes as the canonical non-interactive JSON output mode. No mismatch found; no edit required.

## Evidence

`claude --help` excerpt:
```
-p, --print    Print response and exit (useful for non-interactive mode)
--output-format <format>    Output format (only works with --print):
    "text" (default), "json" (single result), or "stream-json" (realtime
    streaming) (choices: "text", "json", "stream-json")
```
