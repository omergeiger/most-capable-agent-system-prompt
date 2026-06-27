# Task Completion Note

**Task ID:** 948acb18-bd96-4dac-b325-514f9f67d511
**Completed:** 2026-06-26

## What was done

Ran `claude --help` and captured the full flag list. Output saved to `claude_help_output.md`.

## Key findings for non-interactive invocation

The primary non-interactive flag is:

- **`-p` / `--print`** - Print response and exit (non-interactive mode, useful for pipes). This is the canonical flag for scripted/harness invocation.

Additional flags that only work in `--print` mode (relevant for harness use):

| Flag | Purpose |
|------|---------|
| `--output-format <format>` | "text" (default), "json", or "stream-json" - controls structured output |
| `--input-format <format>` | "text" or "stream-json" - for streaming input |
| `--max-budget-usd <amount>` | Budget cap per invocation |
| `--fallback-model <model>` | Fallback if primary model is unavailable |
| `--no-session-persistence` | Stateless run, no session saved to disk |
| `--include-partial-messages` | Stream partial chunks as they arrive |

Other flags useful for harness orchestration:

| Flag | Purpose |
|------|---------|
| `--bare` | Minimal mode - skips hooks, CLAUDE.md, MCP, plugins; good for clean subagent spawns |
| `--permission-mode <mode>` | acceptEdits, auto, bypassPermissions, dontAsk, plan |
| `--dangerously-skip-permissions` | Bypass all permission checks (sandbox use only) |
| `--system-prompt <prompt>` | Inject a custom system prompt |
| `--append-system-prompt <prompt>` | Append to the default system prompt |
| `--model <model>` | Override the model per invocation |
| `--mcp-config <configs...>` | Load MCP servers for the session |
| `--allowed-tools <tools...>` | Allowlist specific tools |
| `--disallowed-tools <tools...>` | Denylist specific tools |
| `--tools <tools...>` | Full tool override (use "" to disable all) |
| `--session-id <uuid>` | Pin to a specific session UUID |
| `--bg` / `--background` | Fire-and-forget background agent |
| `--effort <level>` | low/medium/high/xhigh/max |
| `--json-schema <schema>` | Enforce structured output schema |

## Gaps / Uncertainties

None - help output is comprehensive and well-documented.

## Recommended pattern for harness invocation

```bash
claude -p \
  --bare \
  --permission-mode bypassPermissions \
  --output-format json \
  --model sonnet \
  --max-budget-usd 0.50 \
  "Your task prompt here"
```

Use `--bare` to skip all customizations for a clean subagent context, `--permission-mode bypassPermissions` for autonomous tool use, and `--output-format json` for structured output.
