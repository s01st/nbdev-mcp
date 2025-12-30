# Auto-Approve nbdev-mcp Tools in Claude Code

To configure Claude Code to automatically accept all tools from the nbdev-mcp server without prompting, add the tool patterns to your allowed tools list.

## Option 1: Project-level settings (recommended)

Create or edit `.claude/settings.json` in your project root:

```json
{
  "permissions": {
    "allow": [
      "mcp__nbdev",
      "mcp__nbdev-mcp"
    ]
  }
}
```

## Option 2: User-level settings

Edit `~/.claude/settings.json` to apply globally:

```json
{
  "permissions": {
    "allow": [
      "mcp__nbdev",
      "mcp__nbdev-mcp"
    ]
  }
}
```

## Option 3: Via Claude Code CLI

Run these commands to add permissions:

```bash
claude config add allowedTools "mcp__nbdev"
claude config add allowedTools "mcp__nbdev-mcp"
```

## Tool Pattern Reference

| Pattern | Description |
|---------|-------------|
| `mcp__nbdev` | All tools from server named `nbdev` |
| `mcp__nbdev__*` | Same as above (wildcard variant) |
| `mcp__nbdev__set_project` | Single specific tool |
| `Bash(command:*)` | Bash command with any arguments (`:*` is for Bash only) |

**Note:** The `:*` suffix is for Bash command argument matching, not for MCP tools. For MCP, use either `mcp__server` or `mcp__server__*` to allow all tools.

## Verifying Configuration

Check your current allowed tools:

```bash
claude config list
```

Or in a Claude Code session, run `/permissions` to see active permissions.
