# Completion Note

## Task
Audit claude CLI flags in scripts/worker.py against `claude --help` output.

## Findings

All flags used in worker.py are valid. No mismatches found.

### Flags used in worker.py

Both `execute_task` (line 203) and `verify_task` (line 252) use identical subprocess calls:

```python
["claude", "--print", "--output-format", "json", prompt]
```

### Cross-check against `claude --help`

| Flag | Accepted? | Notes |
|------|-----------|-------|
| `--print` | YES | `-p, --print` — "Print response and exit" |
| `--output-format json` | YES | Accepted choices: `"text"`, `"json"`, `"stream-json"` |
| `prompt` (positional) | YES | Documented as `Arguments: prompt` |

## Files changed

None. worker.py required no changes.

## How to verify

Run `claude --help` and confirm:
- `-p, --print` appears in Options
- `--output-format <format>` lists `"json"` as an accepted choice
- Both match exactly what worker.py passes in its subprocess calls (lines 203-207 and 252-255)
