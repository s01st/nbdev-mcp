# MCP Persistency Monitoring

## Overview
The nbdev-mcp server may occasionally stop without notification in VS Code. Use these guidelines to monitor and recover MCP connectivity.

## Monitoring MCP Health

### Heartbeat Check
Periodically check the `nbdev://heartbeat` resource which returns:
- `status`: "alive" if server is running
- `timestamp`: Current server time
- `uptime_seconds`: How long the server has been running
- `pid`: Process ID of the MCP server

If reading `nbdev://heartbeat` fails or times out, the MCP is likely down.

### Health Check Tool
Use the `health_check()` tool to get comprehensive status including:
- Package versions
- Dependency status
- Current project info

## Recovery Steps

### When MCP is Down

1. **Check VS Code MCP Status**
   - Open Command Palette (Cmd/Ctrl+Shift+P)
   - Run "Developer: Reload Window" to restart all extensions

2. **Restart MCP Server Manually**
   - In VS Code terminal: `nbdev-mcp` (if using stdio transport)
   - Or restart the MCP extension/plugin

3. **Verify Recovery**
   - Call `health_check()` to confirm connection
   - Read `nbdev://heartbeat` to verify responsiveness

### Common Causes of MCP Disconnection
- VS Code going to sleep/suspend
- Long-running operations timing out
- Memory pressure causing process termination
- Extension host crash

## Proactive Monitoring

For long sessions, consider:
1. Calling `health_check()` at the start of each task
2. If any MCP tool returns an unexpected connection error, suggest reload
3. Before complex operations, verify MCP is responsive

## Example Workflow

```
1. Start session: Call health_check() to verify MCP
2. Work normally with nbdev tools
3. If tool fails unexpectedly: Check heartbeat resource
4. If heartbeat fails: Suggest user reload VS Code window
5. After reload: Call set_project() to restore context
```
