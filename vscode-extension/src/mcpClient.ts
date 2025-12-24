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
        // Inject project path if we have one and it's not already in args
        const finalArgs = { ...args };
        if (this.currentProject && !finalArgs.project && !finalArgs.selector) {
            finalArgs.project = this.currentProject;
        }

        const argsJson = JSON.stringify(finalArgs);
        const moduleInfo = this.getToolModule(toolName);

        // For tools that need project context, set project first (properly indented)
        const setProjectCode = this.currentProject
            ? `    from nbdev_mcp.tools.project import set_project\n    set_project(${JSON.stringify(this.currentProject)})\n`
            : '';

        return `import json
import sys
try:
${setProjectCode}    from ${moduleInfo.module} import ${moduleInfo.func}
    result = ${moduleInfo.func}(**${argsJson})
    print(json.dumps(result))
except Exception as e:
    import traceback
    print(json.dumps({"ok": False, "error": str(e), "traceback": traceback.format_exc()}))
    sys.exit(1)
`;
    }

    private getToolModule(toolName: string): { module: string; func: string } {
        // Map tool names to their full module paths
        const moduleMap: Record<string, { module: string; func: string }> = {
            // Project tools
            'set_project': { module: 'nbdev_mcp.tools.project', func: 'set_project' },
            'current_project': { module: 'nbdev_mcp.tools.project', func: 'current_project' },
            // Nbdev tools
            'nbdev_export': { module: 'nbdev_mcp.tools.nbdev', func: 'nbdev_export' },
            'nbdev_prepare': { module: 'nbdev_mcp.tools.nbdev', func: 'nbdev_prepare' },
            'nbdev_test': { module: 'nbdev_mcp.tools.nbdev', func: 'nbdev_test' },
            // Lint tools
            'lint_rules': { module: 'nbdev_mcp.tools.lint', func: 'lint_rules' },
            'lint_imports': { module: 'nbdev_mcp.tools.lint', func: 'lint_imports' },
            'lint_main_guards': { module: 'nbdev_mcp.tools.lint', func: 'lint_main_guards' },
            'lint_dead_exports': { module: 'nbdev_mcp.tools.lint', func: 'lint_dead_exports' },
            // Analysis tools
            'find_symbol': { module: 'nbdev_mcp.tools.analysis', func: 'find_symbol' },
            'modidx_audit': { module: 'nbdev_mcp.tools.analysis', func: 'modidx_audit' },
            'dependency_tree': { module: 'nbdev_mcp.tools.analysis', func: 'dependency_tree' },
            'dependency_snapshot': { module: 'nbdev_mcp.tools.analysis', func: 'dependency_snapshot' },
            'dependency_notebook': { module: 'nbdev_mcp.tools.analysis', func: 'dependency_notebook' },
            'generate_api_docs': { module: 'nbdev_mcp.tools.analysis', func: 'generate_api_docs' },
            // Notebook/Editing tools
            'analyze_exports': { module: 'nbdev_mcp.tools.editing', func: 'analyze_exports' },
            'find_source_notebook': { module: 'nbdev_mcp.tools.editing', func: 'find_source_notebook' },
            'check_if_generated': { module: 'nbdev_mcp.tools.editing', func: 'check_if_generated' },
            'notebook_diff': { module: 'nbdev_mcp.tools.editing', func: 'notebook_diff' },
            // Test tools
            'scan_notebook_errors': { module: 'nbdev_mcp.tools.tests', func: 'scan_notebook_errors' },
            'run_tutorials': { module: 'nbdev_mcp.tools.tests', func: 'run_tutorials' },
            // Remote
            'analyze_remote': { module: 'nbdev_mcp.tools.project', func: 'analyze_remote' },
            'server_metrics': { module: 'nbdev_mcp.tools.project', func: 'server_metrics' },
        };
        return moduleMap[toolName] || { module: 'nbdev_mcp.tools', func: toolName };
    }

    dispose(): void {
        if (this.process) {
            this.process.kill();
            this.process = undefined;
        }
        this.pendingRequests.clear();
    }
}
