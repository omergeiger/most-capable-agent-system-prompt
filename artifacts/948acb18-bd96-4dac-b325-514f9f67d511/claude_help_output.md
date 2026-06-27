# claude --help Output

Captured: 2026-06-26

```
Usage: claude [options] [command] [prompt]

Claude Code - starts an interactive session by default, use -p/--print for
non-interactive output

Arguments:
  prompt                                Your prompt

Options:
  --add-dir <directories...>            Additional directories to allow tool access to
  --agent <agent>                       Agent for the current session.
  --agents <json>                       JSON object defining custom agents
  --allow-dangerously-skip-permissions  Enable bypassing all permission checks
  --allowedTools, --allowed-tools <tools...>   Comma or space-separated list of tool names to allow
  --append-system-prompt <prompt>       Append a system prompt to the default system prompt
  --ax-screen-reader                    Render screen-reader friendly output
  --bg, --background                    Start the session as a background agent and return immediately
  --bare                                Minimal mode: skip hooks, LSP, plugin sync, attribution, auto-memory, background prefetches, keychain reads, and CLAUDE.md auto-discovery
  --betas <betas...>                    Beta headers to include in API requests (API key users only)
  --brief                               Enable SendUserMessage tool for agent-to-user communication
  --chrome                              Enable Claude in Chrome integration
  -c, --continue                        Continue the most recent conversation in the current directory
  --dangerously-skip-permissions        Bypass all permission checks
  -d, --debug [filter]                  Enable debug mode with optional category filtering
  --debug-file <path>                   Write debug logs to a specific file path
  --disable-slash-commands              Disable all skills
  --disallowedTools, --disallowed-tools <tools...>   Comma or space-separated list of tool names to deny
  --effort <level>                      Effort level: low, medium, high, xhigh, max
  --exclude-dynamic-system-prompt-sections   Move per-machine sections from system prompt into first user message
  --fallback-model <model>              Enable automatic fallback to specified model(s) (only works with --print)
  --file <specs...>                     File resources to download at startup
  --fork-session                        When resuming, create a new session ID instead of reusing original
  --from-pr [value]                     Resume a session linked to a PR
  -h, --help                            Display help for command
  --ide                                 Automatically connect to IDE on startup
  --include-hook-events                 Include all hook lifecycle events in the output stream (only with --output-format=stream-json)
  --include-partial-messages            Include partial message chunks as they arrive (only with --print and --output-format=stream-json)
  --input-format <format>               Input format (only with --print): "text" (default) or "stream-json"
  --json-schema <schema>                JSON Schema for structured output validation
  --max-budget-usd <amount>             Maximum dollar amount to spend on API calls (only works with --print)
  --mcp-config <configs...>             Load MCP servers from JSON files or strings
  --model <model>                       Model for the current session
  -n, --name <name>                     Set a display name for this session
  --no-chrome                           Disable Claude in Chrome integration
  --no-session-persistence              Disable session persistence (only works with --print)
  --output-format <format>              Output format (only with --print): "text" (default), "json", or "stream-json"
  --permission-mode <mode>              Permission mode: acceptEdits, auto, bypassPermissions, default, dontAsk, plan
  --plugin-dir <path>                   Load a plugin from a directory or .zip
  --plugin-url <url>                    Fetch a plugin .zip from a URL
  -p, --print                           Print response and exit (non-interactive mode, useful for pipes)
  --prompt-suggestions [value]          Enable prompt suggestions
  --remote-control [name]               Start an interactive session with Remote Control enabled
  --remote-control-session-name-prefix <prefix>  Prefix for auto-generated Remote Control session names
  --replay-user-messages                Re-emit user messages from stdin back on stdout
  -r, --resume [value]                  Resume a conversation by session ID
  --safe-mode                           Start with all customizations disabled
  --session-id <uuid>                   Use a specific session ID for the conversation
  --setting-sources <sources>           Comma-separated list of setting sources to load
  --settings <file-or-json>             Path to a settings JSON file or a JSON string
  --strict-mcp-config                   Only use MCP servers from --mcp-config
  --system-prompt <prompt>              System prompt to use for the session
  --tmux                                Create a tmux session for the worktree
  --tools <tools...>                    Specify the list of available tools
  --verbose                             Override verbose mode setting from config
  -v, --version                         Output the version number
  -w, --worktree [name]                 Create a new git worktree for this session

Commands:
  agents [options]                      Manage background agents
  auth                                  Manage authentication
  auto-mode                             Inspect auto mode classifier configuration
  doctor                                Check the health of your Claude Code auto-updater
  install [options] [target]            Install Claude Code native build
  mcp                                   Configure and manage MCP servers
  plugin|plugins                        Manage Claude Code plugins
  project                               Manage Claude Code project state
  setup-token                           Set up a long-lived authentication token
  ultrareview [options] [target]        Run a cloud-hosted multi-agent code review
  update|upgrade                        Check for updates and install if available
```
