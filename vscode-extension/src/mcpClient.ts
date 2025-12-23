import * as vscode from 'vscode';
import { spawn, ChildProcess } from 'child_process';

export interface McpToolResult {
    ok: boolean;
    error?: string;
    [key: string]: unknown;
}

export class NbdevMcpClient {
    private process: ChildProcess | undefined;
    private currentProject: string | undefined;
    private requestId = 0;
    private pendingRequests: Map<number, {
        resolve: (value: McpToolResult) => void;
        reject: (error: Error) => void;
    }> = new Map();
    private outputBuffer = '';

    constructor() {
        // Client is created but not started until needed
    }

    async setProject(projectPath: string): Promise<McpToolResult> {
        this.currentProject = projectPath;
        return this.callTool('set_project', { selector: projectPath });
    }

    async getCurrentProject(): Promise<McpToolResult> {
        return this.callTool('current_project', {});
    }

    async callTool(toolName: string, args: Record<string, unknown>): Promise<McpToolResult> {
        // For now, use subprocess execution instead of MCP protocol
        // This is simpler and works without setting up full MCP transport
        return this.executeToolViaSubprocess(toolName, args);
    }

    private async executeToolViaSubprocess(
        toolName: string,
        args: Record<string, unknown>
    ): Promise<McpToolResult> {
        const config = vscode.workspace.getConfiguration('nbdev-mcp');
        const serverPath = config.get<string>('mcpServerPath') || 'python';

        return new Promise((resolve, reject) => {
            // Build Python script to call the tool
            const script = this.buildToolScript(toolName, args);

            const proc = spawn(serverPath, ['-c', script], {
                cwd: this.currentProject || vscode.workspace.workspaceFolders?.[0]?.uri.fsPath,
                env: { ...process.env }
            });

            let stdout = '';
            let stderr = '';

            proc.stdout?.on('data', (data) => {
                stdout += data.toString();
            });

            proc.stderr?.on('data', (data) => {
                stderr += data.toString();
            });

            proc.on('close', (code) => {
                if (code === 0) {
                    try {
                        const result = JSON.parse(stdout);
                        resolve(result);
                    } catch {
                        resolve({ ok: true, output: stdout });
                    }
                } else {
                    resolve({
                        ok: false,
                        error: stderr || `Process exited with code ${code}`
                    });
                }
            });

            proc.on('error', (error) => {
                reject(error);
            });
        });
    }

    private buildToolScript(toolName: string, args: Record<string, unknown>): string {
        const argsJson = JSON.stringify(args);
        return `
import json
import sys
try:
    from nbdev_mcp.tools import ${this.getToolModule(toolName)}
    result = ${toolName}(**${argsJson})
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)}))
    sys.exit(1)
`;
    }

    private getToolModule(toolName: string): string {
        // Map tool names to their module imports
        const moduleMap: Record<string, string> = {
            'set_project': 'set_project',
            'current_project': 'current_project',
            'nbdev_export': 'nbdev_export',
            'nbdev_prepare': 'nbdev_prepare',
            'nbdev_test': 'nbdev_test',
            'lint_rules': 'lint_rules',
            'lint_imports': 'lint_imports',
            'lint_main_guards': 'lint_main_guards',
            'find_symbol': 'find_symbol',
            'modidx_audit': 'modidx_audit',
            'dependency_tree': 'dependency_tree',
            'dependency_snapshot': 'dependency_snapshot',
            'analyze_exports': 'analyze_exports',
            'scan_notebook_errors': 'scan_notebook_errors',
            'run_tutorials': 'run_tutorials',
            'find_source_notebook': 'find_source_notebook',
            'check_if_generated': 'check_if_generated',
            'notebook_diff': 'notebook_diff',
            'lint_dead_exports': 'lint_dead_exports',
            'dependency_notebook': 'dependency_notebook',
            'generate_api_docs': 'generate_api_docs',
            'analyze_remote': 'analyze_remote',
            'server_metrics': 'server_metrics',
        };
        return moduleMap[toolName] || toolName;
    }

    dispose(): void {
        if (this.process) {
            this.process.kill();
            this.process = undefined;
        }
        this.pendingRequests.clear();
    }
}
