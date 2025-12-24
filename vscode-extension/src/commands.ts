import * as vscode from 'vscode';
import { NbdevMcpClient } from './mcpClient';
import { NbdevDiagnostics } from './diagnostics';
import * as path from 'path';

export function registerCommands(
    context: vscode.ExtensionContext,
    client: NbdevMcpClient,
    diagnostics: NbdevDiagnostics
): void {
    // Project management commands
    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.setProject', async () => {
            const folders = await vscode.window.showOpenDialog({
                canSelectFolders: true,
                canSelectFiles: false,
                canSelectMany: false,
                title: 'Select nbdev Project Folder'
            });

            if (folders && folders.length > 0) {
                const result = await client.setProject(folders[0].fsPath);
                if (result.ok) {
                    vscode.window.showInformationMessage(
                        `Set active project: ${folders[0].fsPath}`
                    );
                } else {
                    vscode.window.showErrorMessage(
                        `Failed to set project: ${result.error}`
                    );
                }
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.currentProject', async () => {
            const result = await client.getCurrentProject();
            if (result.ok) {
                const message = result.summary || 'No project selected';
                vscode.window.showInformationMessage(message as string);
            } else {
                vscode.window.showWarningMessage(
                    result.error || 'No project selected'
                );
            }
        })
    );

    // nbdev workflow commands
    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.export', async () => {
            await runWithProgress('Exporting notebooks...', async () => {
                const result = await client.callTool('nbdev_export', {});
                showResult(result, 'Export');
            });
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.prepare', async () => {
            await runWithProgress('Running nbdev_prepare...', async () => {
                const result = await client.callTool('nbdev_prepare', {});
                showResult(result, 'Prepare');
            });
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.test', async () => {
            await runWithProgress('Running tests...', async () => {
                const result = await client.callTool('nbdev_test', {});
                showResult(result, 'Test');
            });
        })
    );

    // Lint commands
    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.lint', async () => {
            await runWithProgress('Linting notebooks...', async () => {
                const result = await client.callTool('lint_rules', {});
                if (result.ok) {
                    const issues = result.issues as Array<Record<string, unknown>> || [];
                    diagnostics.updateDiagnosticsFromLint(issues);
                    if (issues.length === 0) {
                        vscode.window.showInformationMessage('No lint issues found');
                    } else {
                        vscode.window.showWarningMessage(
                            `Found ${issues.length} lint issue(s) - see Problems panel`
                        );
                    }
                } else {
                    vscode.window.showErrorMessage(`Lint failed: ${result.error}`);
                }
            });
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.lintImports', async () => {
            await runWithProgress('Checking unused imports...', async () => {
                const result = await client.callTool('lint_imports', {});
                if (result.ok) {
                    const issues = result.issues as Array<Record<string, unknown>> || [];
                    diagnostics.updateDiagnosticsFromImports(issues);
                    if (issues.length === 0) {
                        vscode.window.showInformationMessage('No unused imports found');
                    } else {
                        vscode.window.showWarningMessage(
                            `Found unused imports in ${issues.length} cell(s) - see Problems panel`
                        );
                    }
                } else {
                    vscode.window.showErrorMessage(`Import check failed: ${result.error}`);
                }
            });
        })
    );

    // Analysis commands
    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.findSymbol', async () => {
            const symbol = await vscode.window.showInputBox({
                prompt: 'Enter symbol name to find',
                placeHolder: 'e.g., MyClass, my_function'
            });

            if (symbol) {
                await runWithProgress(`Finding symbol: ${symbol}...`, async () => {
                    const result = await client.callTool('find_symbol', { symbol });
                    if (result.ok) {
                        const locations = result.locations as Array<{
                            module: string;
                            notebook: string;
                        }> || [];
                        if (locations.length === 0) {
                            vscode.window.showInformationMessage(
                                `Symbol '${symbol}' not found`
                            );
                        } else {
                            const items = locations.map(loc => ({
                                label: loc.module,
                                description: loc.notebook
                            }));
                            const selected = await vscode.window.showQuickPick(items, {
                                title: `Found ${locations.length} location(s) for '${symbol}'`
                            });
                            if (selected) {
                                // Open the notebook
                                const uri = vscode.Uri.file(selected.description!);
                                await vscode.window.showTextDocument(uri);
                            }
                        }
                    } else {
                        vscode.window.showErrorMessage(`Find failed: ${result.error}`);
                    }
                });
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.analyzeExports', async () => {
            const editor = vscode.window.activeTextEditor;
            let notebook = '';

            if (editor && editor.document.fileName.endsWith('.ipynb')) {
                notebook = path.basename(editor.document.fileName);
            } else {
                const input = await vscode.window.showInputBox({
                    prompt: 'Enter notebook filename',
                    placeHolder: 'e.g., 01_core.ipynb'
                });
                if (input) {
                    notebook = input;
                }
            }

            if (notebook) {
                await runWithProgress(`Analyzing exports: ${notebook}...`, async () => {
                    const result = await client.callTool('analyze_exports', { notebook });
                    if (result.ok) {
                        showOutputPanel('Notebook Exports', formatExports(result));
                    } else {
                        vscode.window.showErrorMessage(`Analysis failed: ${result.error}`);
                    }
                });
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.dependencyTree', async () => {
            await runWithProgress('Generating dependency graph...', async () => {
                // Use 'both' scope to show all dependencies
                const result = await client.callTool('dependency_tree', { scope: 'both' });
                if (result.error) {
                    vscode.window.showErrorMessage(`Failed: ${result.error}`);
                    return;
                }

                const internalNodes = result.nodes_internal as string[] || [];
                const externalNodes = result.nodes_external as string[] || [];
                const edges = result.edges as Array<[string, string]> || [];

                if (edges.length === 0) {
                    vscode.window.showInformationMessage('No dependencies found');
                    return;
                }

                showInteractiveGraph(
                    context,
                    `Dependencies: ${internalNodes.length} modules → ${externalNodes.length} libraries`,
                    internalNodes,
                    externalNodes,
                    edges
                );
            });
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.modidxAudit', async () => {
            await runWithProgress('Auditing module index...', async () => {
                const result = await client.callTool('modidx_audit', {});
                // Note: ok=false means issues were found, not that the command failed
                if (result.error) {
                    vscode.window.showErrorMessage(`Audit failed: ${result.error}`);
                    return;
                }

                const duplicates = result.duplicates as Array<Record<string, unknown>> || [];
                const privateExports = result.private_exports as Array<Record<string, unknown>> || [];
                const numberingIssues = result.numbering_issues as Array<Record<string, unknown>> || [];
                const totalIssues = duplicates.length + privateExports.length + numberingIssues.length;

                if (totalIssues === 0) {
                    vscode.window.showInformationMessage('Module index looks healthy');
                } else {
                    showOutputPanel('Module Index Audit', formatModidxAudit(result));
                }
            });
        })
    );

    // Error scanning commands
    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.scanErrors', async () => {
            await runWithProgress('Scanning notebook errors...', async () => {
                const result = await client.callTool('scan_notebook_errors', {});
                if (result.ok) {
                    const errors = result.errors as Array<Record<string, unknown>> || [];
                    if (errors.length === 0) {
                        vscode.window.showInformationMessage('No error outputs found');
                    } else {
                        diagnostics.updateDiagnosticsFromErrors(errors);
                        vscode.window.showWarningMessage(
                            `Found ${errors.length} error output(s) - see Problems panel`
                        );
                    }
                } else {
                    vscode.window.showErrorMessage(`Scan failed: ${result.error}`);
                }
            });
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.runTutorials', async () => {
            await runWithProgress('Running tutorials...', async () => {
                const result = await client.callTool('run_tutorials', {});
                if (result.ok) {
                    const failures = result.failures as Array<Record<string, unknown>> || [];
                    if (failures.length === 0) {
                        vscode.window.showInformationMessage('All tutorials passed');
                    } else {
                        showOutputPanel('Tutorial Failures', formatTutorialFailures(failures));
                    }
                } else {
                    vscode.window.showErrorMessage(`Failed: ${result.error}`);
                }
            });
        })
    );

    // Source tracking commands
    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.findSourceNotebook', async () => {
            const editor = vscode.window.activeTextEditor;
            let pyFile = '';

            if (editor && editor.document.fileName.endsWith('.py')) {
                pyFile = editor.document.fileName;
            } else {
                const input = await vscode.window.showInputBox({
                    prompt: 'Enter Python file path',
                    placeHolder: 'e.g., mylib/core.py'
                });
                if (input) {
                    pyFile = input;
                }
            }

            if (pyFile) {
                const result = await client.callTool('find_source_notebook', { py_file: pyFile });
                if (result.ok && result.notebook) {
                    const action = await vscode.window.showInformationMessage(
                        `Source notebook: ${result.notebook}`,
                        'Open Notebook'
                    );
                    if (action === 'Open Notebook') {
                        const uri = vscode.Uri.file(result.notebook as string);
                        await vscode.window.showTextDocument(uri);
                    }
                } else {
                    vscode.window.showWarningMessage(
                        result.error || 'Source notebook not found'
                    );
                }
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.checkIfGenerated', async () => {
            const editor = vscode.window.activeTextEditor;
            let filePath = '';

            if (editor && editor.document.fileName.endsWith('.py')) {
                filePath = editor.document.fileName;
            }

            if (filePath) {
                const result = await client.callTool('check_if_generated', { file_path: filePath });
                if (result.ok) {
                    if (result.generated) {
                        vscode.window.showWarningMessage(
                            `This file is auto-generated by nbdev. Edit the source notebook instead: ${result.source_notebook || 'unknown'}`
                        );
                    } else {
                        vscode.window.showInformationMessage(
                            'This file is NOT auto-generated - safe to edit directly'
                        );
                    }
                } else {
                    vscode.window.showErrorMessage(`Check failed: ${result.error}`);
                }
            }
        })
    );

    // New analysis commands
    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.lintDeadExports', async () => {
            await runWithProgress('Finding dead exports...', async () => {
                const result = await client.callTool('lint_dead_exports', {});
                if (result.error) {
                    vscode.window.showErrorMessage(`Analysis failed: ${result.error}`);
                    return;
                }

                const deadExports = result.dead_exports as Array<Record<string, unknown>> || [];
                if (deadExports.length === 0) {
                    vscode.window.showInformationMessage('No dead exports found');
                } else {
                    showOutputPanel('Dead Exports', formatDeadExports(deadExports));
                }
            });
        })
    );

    // Track running nbdev_preview process
    let previewProcess: import('child_process').ChildProcess | null = null;
    let previewPanel: vscode.WebviewPanel | null = null;

    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.generateApiDocs', async () => {
            // Kill existing preview if running
            if (previewProcess) {
                previewProcess.kill();
                previewProcess = null;
            }

            const projectPath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
            if (!projectPath) {
                vscode.window.showErrorMessage('No workspace folder open');
                return;
            }

            // Create output channel for logging
            const outputChannel = vscode.window.createOutputChannel('nbdev Preview');
            outputChannel.show();
            outputChannel.appendLine('Starting nbdev preview...');
            outputChannel.appendLine(`Working directory: ${projectPath}`);

            const { spawn } = require('child_process');

            // Use nbdev_preview which handles nbdev directives properly
            outputChannel.appendLine('Running nbdev_preview (this handles nbdev directives correctly)');

            previewProcess = spawn('nbdev_preview', ['--no_browser'], {
                cwd: projectPath,
                shell: true,
                env: { ...process.env }
            });

            let serverUrl = '';

            const proc = previewProcess;
            if (!proc) {
                vscode.window.showErrorMessage('Failed to start quarto preview');
                return;
            }

            proc.stdout?.on('data', (data: Buffer) => {
                const output = data.toString();
                outputChannel.appendLine(output);
                // Look for the URL in output (e.g., "Browse at http://localhost:4567/")
                const urlMatch = output.match(/https?:\/\/localhost:\d+\/?/);
                if (urlMatch && !serverUrl) {
                    serverUrl = urlMatch[0];
                    outputChannel.appendLine(`Opening browser at: ${serverUrl}`);
                    vscode.commands.executeCommand('simpleBrowser.show', serverUrl);
                }
            });

            proc.stderr?.on('data', (data: Buffer) => {
                const output = data.toString();
                outputChannel.appendLine(output);
                // Quarto may output URL to stderr
                const urlMatch = output.match(/https?:\/\/localhost:\d+\/?/);
                if (urlMatch && !serverUrl) {
                    serverUrl = urlMatch[0];
                    outputChannel.appendLine(`Opening browser at: ${serverUrl}`);
                    vscode.commands.executeCommand('simpleBrowser.show', serverUrl);
                }
            });

            proc.on('error', (error: Error) => {
                outputChannel.appendLine(`[error] ${error.message}`);
                vscode.window.showErrorMessage(`Failed to start preview: ${error.message}`);
            });

            proc.on('close', (code: number) => {
                outputChannel.appendLine(`nbdev preview exited with code ${code}`);
                previewProcess = null;
                // Clean up _docs folder
                const { rmSync } = require('fs');
                const docsPath = require('path').join(projectPath, '_docs');
                try {
                    rmSync(docsPath, { recursive: true, force: true });
                    outputChannel.appendLine('Cleaned up _docs folder');
                } catch (e) {
                    // Ignore cleanup errors
                }
            });

            // Register cleanup on extension deactivate
            context.subscriptions.push({
                dispose: () => {
                    if (previewProcess) {
                        previewProcess.kill();
                        previewProcess = null;
                    }
                }
            });
        })
    );

    // Stop preview command
    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.stopPreview', () => {
            if (previewProcess) {
                previewProcess.kill();
                previewProcess = null;
                vscode.window.showInformationMessage('Preview server stopped');
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.analyzeRemote', async () => {
            const url = await vscode.window.showInputBox({
                prompt: 'Enter GitHub repository URL',
                placeHolder: 'e.g., https://github.com/fastai/nbdev'
            });

            if (url) {
                await runWithProgress(`Analyzing remote project...`, async () => {
                    const result = await client.callTool('analyze_remote', { url });
                    if (result.ok) {
                        showOutputPanel('Remote Project Analysis', formatRemoteAnalysis(result));
                    } else {
                        vscode.window.showErrorMessage(`Analysis failed: ${result.error}`);
                    }
                });
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.serverMetrics', async () => {
            const result = await client.callTool('server_metrics', {});
            if (result.ok) {
                showOutputPanel('Server Metrics', formatServerMetrics(result));
            } else {
                vscode.window.showErrorMessage(`Failed to get metrics: ${result.error}`);
            }
        })
    );

    // Lint Panel - comprehensive view of all lint/analysis results
    let lintPanel: vscode.WebviewPanel | null = null;

    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.showLintPanel', async () => {
            // Create or reveal the panel
            if (lintPanel) {
                lintPanel.reveal();
            } else {
                lintPanel = vscode.window.createWebviewPanel(
                    'nbdevLint',
                    'nbdev Lint & Analysis',
                    vscode.ViewColumn.One,
                    { enableScripts: true, retainContextWhenHidden: true }
                );

                lintPanel.onDidDispose(() => {
                    lintPanel = null;
                });
            }

            // Run all lint checks and show results
            await runLintAnalysis(client, diagnostics, lintPanel);
        })
    );

    // Also update lint command to show panel
    // Override the existing lint command behavior to use panel
}

async function runWithProgress<T>(
    title: string,
    task: () => Promise<T>
): Promise<T | undefined> {
    return vscode.window.withProgress(
        {
            location: vscode.ProgressLocation.Notification,
            title,
            cancellable: false
        },
        async () => {
            try {
                return await task();
            } catch (error) {
                vscode.window.showErrorMessage(`Error: ${error}`);
                return undefined;
            }
        }
    );
}

function showResult(result: Record<string, unknown>, operation: string): void {
    if (result.ok) {
        vscode.window.showInformationMessage(`${operation} completed successfully`);
    } else {
        vscode.window.showErrorMessage(`${operation} failed: ${result.error}`);
    }
}

function showOutputPanel(title: string, content: string): void {
    const panel = vscode.window.createOutputChannel(title);
    panel.clear();
    panel.appendLine(content);
    panel.show();
}

function formatExports(result: Record<string, unknown>): string {
    const lines: string[] = [];
    lines.push(`Notebook: ${result.notebook || 'unknown'}`);
    lines.push(`Default Export: ${result.default_exp || 'none'}`);
    lines.push('');

    const exports = result.exports as Array<Record<string, string>> || [];
    if (exports.length > 0) {
        lines.push('Exported Symbols:');
        for (const exp of exports) {
            lines.push(`  - ${exp.name} (${exp.type})`);
        }
    } else {
        lines.push('No exports found');
    }

    return lines.join('\n');
}

function formatModidxAudit(result: Record<string, unknown>): string {
    const lines: string[] = [];
    lines.push('Module Index Audit Results:');
    lines.push('');

    const duplicates = result.duplicates as Array<Record<string, unknown>> || [];
    if (duplicates.length > 0) {
        lines.push('=== Duplicate Exports ===');
        for (const dup of duplicates) {
            lines.push(`  Symbol: ${dup.symbol}`);
            lines.push(`  Locations: ${JSON.stringify(dup.locations)}`);
            lines.push('');
        }
    }

    const privateExports = result.private_exports as Array<Record<string, unknown>> || [];
    if (privateExports.length > 0) {
        lines.push('=== Private Exports (should not be exported) ===');
        for (const priv of privateExports) {
            lines.push(`  Symbol: ${priv.symbol}`);
            lines.push(`  Module: ${priv.module}`);
            lines.push('');
        }
    }

    const numberingIssues = result.numbering_issues as Array<Record<string, unknown>> || [];
    if (numberingIssues.length > 0) {
        lines.push('=== Numbering Issues ===');
        for (const issue of numberingIssues) {
            lines.push(`  Notebook: ${issue.notebook}`);
            lines.push(`  Issue: ${issue.message}`);
            lines.push('');
        }
    }

    return lines.join('\n');
}

function formatTutorialFailures(failures: Array<Record<string, unknown>>): string {
    const lines: string[] = [];
    lines.push('Tutorial Execution Failures:');
    lines.push('');

    for (const failure of failures) {
        lines.push(`Notebook: ${failure.notebook}`);
        lines.push(`Error: ${failure.error}`);
        lines.push('');
    }

    return lines.join('\n');
}

function formatDeadExports(deadExports: Array<Record<string, unknown>>): string {
    const lines: string[] = [];
    lines.push('Dead Exports (never imported):');
    lines.push('');

    for (const exp of deadExports) {
        lines.push(`Symbol: ${exp.symbol}`);
        lines.push(`  Notebook: ${exp.notebook}`);
        lines.push(`  Module: ${exp.module}`);
        lines.push('');
    }

    return lines.join('\n');
}

function formatRemoteAnalysis(result: Record<string, unknown>): string {
    const lines: string[] = [];
    lines.push(`Remote Project Analysis: ${result.url}`);
    lines.push('');
    lines.push(`Project Name: ${result.lib_name || 'unknown'}`);
    lines.push(`Notebooks: ${result.notebook_count || 0}`);
    lines.push(`Modules: ${result.module_count || 0}`);
    lines.push('');

    const notebooks = result.notebooks as string[] || [];
    if (notebooks.length > 0) {
        lines.push('Notebooks:');
        for (const nb of notebooks) {
            lines.push(`  - ${nb}`);
        }
    }

    return lines.join('\n');
}

function formatServerMetrics(result: Record<string, unknown>): string {
    const lines: string[] = [];
    lines.push('Server Metrics');
    lines.push('');
    lines.push(`Uptime: ${result.uptime_seconds || 0}s`);
    lines.push(`Memory Usage: ${result.memory_mb || 0} MB`);
    lines.push(`CPU Percent: ${result.cpu_percent || 0}%`);
    lines.push(`Total Requests: ${result.total_requests || 0}`);
    lines.push('');

    const toolCounts = result.tool_counts as Record<string, number> || {};
    if (Object.keys(toolCounts).length > 0) {
        lines.push('Tool Usage:');
        for (const [tool, count] of Object.entries(toolCounts)) {
            lines.push(`  ${tool}: ${count}`);
        }
    }

    return lines.join('\n');
}

function showMermaidPanel(context: vscode.ExtensionContext, title: string, mermaidCode: string): void {
    const panel = vscode.window.createWebviewPanel(
        'nbdevMermaid',
        title,
        vscode.ViewColumn.One,
        {
            enableScripts: true
        }
    );

    // Escape mermaid code for embedding in JS
    const escapedMermaid = mermaidCode
        .replace(/\\/g, '\\\\')
        .replace(/`/g, '\\`')
        .replace(/\$/g, '\\$')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    panel.webview.html = `<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src https://cdn.jsdelivr.net 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; img-src data:;">
    <title>${title}</title>
    <style>
        body {
            background: #1e1e1e;
            color: #d4d4d4;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            padding: 20px;
            margin: 0;
        }
        #diagram {
            background: #2d2d2d;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            overflow: auto;
        }
        #diagram svg {
            max-width: none;
        }
        h1 {
            font-size: 1.5em;
            margin-bottom: 10px;
            border-bottom: 1px solid #444;
            padding-bottom: 10px;
        }
        .controls {
            margin-bottom: 15px;
            display: flex;
            gap: 10px;
        }
        .controls button {
            background: #0e639c;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
        }
        .controls button:hover {
            background: #1177bb;
        }
        pre {
            background: #2d2d2d;
            padding: 15px;
            border-radius: 4px;
            overflow-x: auto;
            font-size: 11px;
            font-family: 'SF Mono', Monaco, 'Courier New', monospace;
            white-space: pre-wrap;
            max-height: 300px;
        }
        .hidden { display: none; }
        .loading {
            text-align: center;
            padding: 40px;
            color: #888;
        }
        .error {
            color: #f48771;
            padding: 20px;
            background: #3a2424;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <h1>${title}</h1>
    <div class="controls">
        <button onclick="toggleCode()">Toggle Code</button>
        <button onclick="zoomIn()">Zoom In</button>
        <button onclick="zoomOut()">Zoom Out</button>
        <button onclick="resetZoom()">Reset</button>
    </div>
    <div id="diagram" class="loading">Loading diagram...</div>
    <pre id="code-block" class="hidden">${escapedMermaid}</pre>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <script>
        let currentZoom = 1;
        const diagramDiv = document.getElementById('diagram');

        function toggleCode() {
            document.getElementById('code-block').classList.toggle('hidden');
        }
        function zoomIn() {
            currentZoom *= 1.2;
            applyZoom();
        }
        function zoomOut() {
            currentZoom /= 1.2;
            applyZoom();
        }
        function resetZoom() {
            currentZoom = 1;
            applyZoom();
        }
        function applyZoom() {
            const svg = diagramDiv.querySelector('svg');
            if (svg) {
                svg.style.transform = 'scale(' + currentZoom + ')';
                svg.style.transformOrigin = 'top left';
            }
        }

        async function renderDiagram() {
            try {
                mermaid.initialize({
                    startOnLoad: false,
                    theme: 'dark',
                    securityLevel: 'loose',
                    flowchart: {
                        useMaxWidth: false,
                        htmlLabels: true,
                        curve: 'basis',
                        rankSpacing: 50,
                        nodeSpacing: 30
                    }
                });

                const code = \`${mermaidCode.replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`;
                const { svg } = await mermaid.render('mermaid-svg', code);
                diagramDiv.innerHTML = svg;
                diagramDiv.classList.remove('loading');
            } catch (e) {
                diagramDiv.innerHTML = '<div class="error">Failed to render: ' + e.message + '<br><br>Try viewing the code instead.</div>';
                diagramDiv.classList.remove('loading');
                document.getElementById('code-block').classList.remove('hidden');
            }
        }

        renderDiagram();
    </script>
</body>
</html>`;
}

function getNonce(): string {
    let text = '';
    const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    for (let i = 0; i < 32; i++) {
        text += possible.charAt(Math.floor(Math.random() * possible.length));
    }
    return text;
}

async function runLintAnalysis(
    client: NbdevMcpClient,
    diagnostics: NbdevDiagnostics,
    panel: vscode.WebviewPanel
): Promise<void> {
    // Show loading state
    panel.webview.html = getLintPanelHtml({ loading: true });

    // Run all lint checks in parallel
    const [lintResult, importsResult, deadExportsResult, errorsResult] = await Promise.all([
        client.callTool('lint_rules', {}),
        client.callTool('lint_imports', {}),
        client.callTool('lint_dead_exports', {}),
        client.callTool('scan_notebook_errors', {})
    ]);

    // Extract issues
    const lintIssues = lintResult.ok ? (lintResult.issues as Array<Record<string, unknown>> || []) : [];
    const importIssues = importsResult.ok ? (importsResult.issues as Array<Record<string, unknown>> || []) : [];
    const deadExports = deadExportsResult.error ? [] : (deadExportsResult.dead_exports as Array<Record<string, unknown>> || []);
    const errorOutputs = errorsResult.ok ? (errorsResult.errors as Array<Record<string, unknown>> || []) : [];

    // Update diagnostics panel
    if (lintIssues.length > 0) {
        diagnostics.updateDiagnosticsFromLint(lintIssues);
    }
    if (importIssues.length > 0) {
        diagnostics.updateDiagnosticsFromImports(importIssues);
    }
    if (errorOutputs.length > 0) {
        diagnostics.updateDiagnosticsFromErrors(errorOutputs);
    }

    // Update webview with results
    panel.webview.html = getLintPanelHtml({
        loading: false,
        lintIssues,
        importIssues,
        deadExports,
        errorOutputs
    });
}

function getLintPanelHtml(data: {
    loading?: boolean;
    lintIssues?: Array<Record<string, unknown>>;
    importIssues?: Array<Record<string, unknown>>;
    deadExports?: Array<Record<string, unknown>>;
    errorOutputs?: Array<Record<string, unknown>>;
}): string {
    if (data.loading) {
        return `<!DOCTYPE html>
<html>
<head>
    <style>
        body { background: #1e1e1e; color: #d4d4d4; font-family: -apple-system, sans-serif; padding: 20px; }
        .loading { text-align: center; padding: 60px; }
        .spinner { border: 3px solid #333; border-top: 3px solid #4fc3f7; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 20px auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="loading">
        <div class="spinner"></div>
        <p>Running lint checks...</p>
    </div>
</body>
</html>`;
    }

    const { lintIssues = [], importIssues = [], deadExports = [], errorOutputs = [] } = data;
    const totalIssues = lintIssues.length + importIssues.length + deadExports.length + errorOutputs.length;

    // Build sections HTML
    const sectionsHtml: string[] = [];

    // Lint Issues section
    if (lintIssues.length > 0) {
        const items = lintIssues.map(issue => `
            <div class="issue">
                <div class="issue-header">
                    <span class="badge warning">${issue.type || 'lint'}</span>
                    <span class="file">${issue.notebook || issue.file || 'unknown'}</span>
                </div>
                <div class="issue-message">${issue.message || JSON.stringify(issue)}</div>
                ${issue.cell_index !== undefined ? `<div class="issue-detail">Cell ${issue.cell_index}</div>` : ''}
            </div>
        `).join('');
        sectionsHtml.push(`
            <div class="section">
                <div class="section-header" onclick="toggleSection('lint')">
                    <span class="arrow" id="arrow-lint">▼</span>
                    <span class="section-title">Lint Issues</span>
                    <span class="badge count">${lintIssues.length}</span>
                </div>
                <div class="section-content" id="content-lint">${items}</div>
            </div>
        `);
    }

    // Unused Imports section
    if (importIssues.length > 0) {
        const items = importIssues.map(issue => `
            <div class="issue">
                <div class="issue-header">
                    <span class="badge info">import</span>
                    <span class="file">${issue.notebook || 'unknown'}</span>
                </div>
                <div class="issue-message">Unused: ${(issue.unused as string[] || []).join(', ')}</div>
                ${issue.cell_index !== undefined ? `<div class="issue-detail">Cell ${issue.cell_index}</div>` : ''}
            </div>
        `).join('');
        sectionsHtml.push(`
            <div class="section">
                <div class="section-header" onclick="toggleSection('imports')">
                    <span class="arrow" id="arrow-imports">▼</span>
                    <span class="section-title">Unused Imports</span>
                    <span class="badge count">${importIssues.length}</span>
                </div>
                <div class="section-content" id="content-imports">${items}</div>
            </div>
        `);
    }

    // Dead Exports section
    if (deadExports.length > 0) {
        const items = deadExports.map(exp => `
            <div class="issue">
                <div class="issue-header">
                    <span class="badge dead">dead</span>
                    <span class="symbol">${exp.symbol}</span>
                </div>
                <div class="issue-message">Never imported by other modules</div>
                <div class="issue-detail">${exp.notebook || exp.module || ''}</div>
            </div>
        `).join('');
        sectionsHtml.push(`
            <div class="section">
                <div class="section-header" onclick="toggleSection('dead')">
                    <span class="arrow" id="arrow-dead">▼</span>
                    <span class="section-title">Dead Exports</span>
                    <span class="badge count">${deadExports.length}</span>
                </div>
                <div class="section-content" id="content-dead">${items}</div>
            </div>
        `);
    }

    // Error Outputs section
    if (errorOutputs.length > 0) {
        const items = errorOutputs.map(err => `
            <div class="issue error">
                <div class="issue-header">
                    <span class="badge error">error</span>
                    <span class="file">${err.notebook || 'unknown'}</span>
                </div>
                <div class="issue-message">${err.ename || 'Error'}: ${err.evalue || ''}</div>
                ${err.cell_index !== undefined ? `<div class="issue-detail">Cell ${err.cell_index}</div>` : ''}
            </div>
        `).join('');
        sectionsHtml.push(`
            <div class="section">
                <div class="section-header" onclick="toggleSection('errors')">
                    <span class="arrow" id="arrow-errors">▼</span>
                    <span class="section-title">Notebook Errors</span>
                    <span class="badge count error">${errorOutputs.length}</span>
                </div>
                <div class="section-content" id="content-errors">${items}</div>
            </div>
        `);
    }

    const contentHtml = sectionsHtml.length > 0
        ? sectionsHtml.join('')
        : '<div class="success"><span class="checkmark">✓</span> All checks passed! No issues found.</div>';

    return `<!DOCTYPE html>
<html>
<head>
    <style>
        body { background: #1e1e1e; color: #d4d4d4; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 0; margin: 0; }
        .header { background: #252526; padding: 16px 20px; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 100; }
        .header h1 { font-size: 16px; margin: 0; font-weight: 500; }
        .summary { font-size: 13px; color: #888; }
        .summary.clean { color: #4ec9b0; }
        .summary.issues { color: #f48771; }
        .content { padding: 16px 20px; }
        .section { margin-bottom: 12px; background: #252526; border-radius: 6px; overflow: hidden; }
        .section-header { padding: 12px 16px; cursor: pointer; display: flex; align-items: center; gap: 10px; background: #2d2d2d; }
        .section-header:hover { background: #333; }
        .arrow { font-size: 10px; color: #888; transition: transform 0.2s; }
        .arrow.collapsed { transform: rotate(-90deg); }
        .section-title { font-weight: 500; flex: 1; }
        .section-content { padding: 0; max-height: 500px; overflow-y: auto; transition: max-height 0.3s; }
        .section-content.collapsed { max-height: 0; padding: 0; overflow: hidden; }
        .badge { font-size: 10px; padding: 2px 8px; border-radius: 10px; text-transform: uppercase; font-weight: 600; }
        .badge.warning { background: #664d00; color: #ffc107; }
        .badge.info { background: #1a3a52; color: #4fc3f7; }
        .badge.dead { background: #3d2f2f; color: #f48771; }
        .badge.error { background: #4a1f1f; color: #f48771; }
        .badge.count { background: #444; color: #fff; min-width: 20px; text-align: center; }
        .issue { padding: 12px 16px; border-bottom: 1px solid #333; }
        .issue:last-child { border-bottom: none; }
        .issue:hover { background: #2a2a2a; }
        .issue.error { border-left: 3px solid #f48771; }
        .issue-header { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
        .file { color: #4fc3f7; font-size: 12px; }
        .symbol { color: #dcdcaa; font-family: 'SF Mono', Monaco, monospace; font-size: 13px; }
        .issue-message { color: #d4d4d4; font-size: 13px; }
        .issue-detail { color: #888; font-size: 11px; margin-top: 4px; }
        .success { text-align: center; padding: 60px 20px; }
        .checkmark { font-size: 48px; display: block; margin-bottom: 16px; color: #4ec9b0; }
        .success p { color: #888; font-size: 14px; }
        button { background: #0e639c; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 12px; }
        button:hover { background: #1177bb; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Lint & Analysis Results</h1>
        <div class="summary ${totalIssues === 0 ? 'clean' : 'issues'}">
            ${totalIssues === 0 ? '✓ All clean' : `${totalIssues} issue${totalIssues !== 1 ? 's' : ''} found`}
        </div>
    </div>
    <div class="content">
        ${contentHtml}
    </div>
    <script>
        function toggleSection(id) {
            const content = document.getElementById('content-' + id);
            const arrow = document.getElementById('arrow-' + id);
            content.classList.toggle('collapsed');
            arrow.classList.toggle('collapsed');
        }
    </script>
</body>
</html>`;
}

function showInteractiveGraph(
    context: vscode.ExtensionContext,
    title: string,
    internalNodes: string[],
    externalNodes: string[],
    edges: Array<[string, string]>
): void {
    const panel = vscode.window.createWebviewPanel(
        'nbdevGraph',
        title,
        vscode.ViewColumn.One,
        { enableScripts: true }
    );

    // Build hierarchical data: modules -> notebooks -> symbols
    interface HierarchyNode {
        name: string;
        fullId?: string;
        type?: string;
        isExternal?: boolean;
        children?: HierarchyNode[];
    }

    // Normalize package name (handle hyphen vs underscore)
    const normalizePkg = (name: string) => name.replace(/-/g, '_').toLowerCase();

    // Combine all nodes - treat any node from internalNodes OR matching package as internal
    const allInternalIds = new Set(internalNodes);
    const internalPackages = new Set<string>();
    for (const n of internalNodes) {
        const pkg = n.split('.')[0];
        internalPackages.add(pkg);
        internalPackages.add(normalizePkg(pkg));  // Also add normalized version
    }

    // Add "external" nodes that belong to internal packages back to internal
    for (const n of externalNodes) {
        const pkg = n.split('.')[0];
        if (internalPackages.has(pkg) || internalPackages.has(normalizePkg(pkg))) {
            allInternalIds.add(n);
        }
    }

    const hierarchy: HierarchyNode = { name: "root", children: [] };
    const moduleMap = new Map<string, HierarchyNode>();
    const notebookMap = new Map<string, HierarchyNode>();

    // Process all internal nodes: package.module.notebook.symbol
    for (const n of allInternalIds) {
        const parts = n.split('.');
        const moduleName = parts.length > 1 ? parts[1] : 'root';
        const notebookName = parts.length > 2 ? parts[2] : moduleName;
        const symbolName = parts[parts.length - 1];

        // Get or create module
        if (!moduleMap.has(moduleName)) {
            const moduleNode: HierarchyNode = { name: moduleName, children: [] };
            moduleMap.set(moduleName, moduleNode);
            hierarchy.children!.push(moduleNode);
        }
        const moduleNode = moduleMap.get(moduleName)!;

        // Get or create notebook within module
        const nbKey = `${moduleName}:${notebookName}`;
        if (!notebookMap.has(nbKey)) {
            const nbNode: HierarchyNode = { name: notebookName, children: [] };
            notebookMap.set(nbKey, nbNode);
            moduleNode.children!.push(nbNode);
        }
        const nbNode = notebookMap.get(nbKey)!;

        // Add symbol (avoid duplicates)
        if (!nbNode.children!.some(c => c.fullId === n)) {
            nbNode.children!.push({
                name: symbolName,
                fullId: n,
                type: 'internal'
            });
        }
    }

    // Process truly external nodes: package -> symbols (flat)
    const trueExternalNodes = externalNodes.filter(n => {
        const pkg = n.split('.')[0];
        return !internalPackages.has(pkg) && !internalPackages.has(normalizePkg(pkg));
    });

    if (trueExternalNodes.length > 0) {
        const extPackages = new Map<string, HierarchyNode>();

        for (const n of trueExternalNodes) {
            const parts = n.split('.');
            const pkgName = parts[0];
            const symbolName = parts[parts.length - 1];

            if (!extPackages.has(pkgName)) {
                const pkgNode: HierarchyNode = {
                    name: pkgName,
                    isExternal: true,
                    children: []
                };
                extPackages.set(pkgName, pkgNode);
                hierarchy.children!.push(pkgNode);
            }

            if (!extPackages.get(pkgName)!.children!.some(c => c.fullId === n)) {
                extPackages.get(pkgName)!.children!.push({
                    name: symbolName,
                    fullId: n,
                    type: 'external'
                });
            }
        }
    }

    // Build edge lookup for highlighting
    const edgeData = edges.map(([s, t]) => ({ source: s, target: t }));

    // Debug: log what we're seeing
    console.log('Internal packages detected:', [...internalPackages]);
    console.log('True external nodes count:', trueExternalNodes.length);
    console.log('Hierarchy modules:', hierarchy.children?.map(c => c.name + (c.isExternal ? ' (ext)' : '')));

    const graphData = JSON.stringify({ hierarchy, edges: edgeData });

    panel.webview.html = `<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src https://d3js.org 'unsafe-inline'; style-src 'unsafe-inline';">
    <style>
        body {
            margin: 0;
            background: #1e1e1e;
            overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }
        #controls {
            position: fixed;
            top: 10px;
            left: 10px;
            z-index: 100;
            display: flex;
            gap: 8px;
        }
        button {
            background: #0e639c;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        button:hover { background: #1177bb; }
        button.active { background: #16825d; }
        #info {
            position: fixed;
            top: 10px;
            right: 10px;
            color: #888;
            font-size: 12px;
            background: #252526;
            padding: 8px 12px;
            border-radius: 6px;
        }
        #legend {
            position: fixed;
            bottom: 10px;
            left: 10px;
            background: #252526;
            padding: 12px;
            border-radius: 6px;
            font-size: 11px;
            color: #aaa;
        }
        .legend-item { display: flex; align-items: center; gap: 8px; margin: 4px 0; }
        #tooltip {
            position: absolute;
            background: #333;
            color: #d4d4d4;
            padding: 10px 14px;
            border-radius: 6px;
            font-size: 12px;
            pointer-events: none;
            display: none;
            max-width: 350px;
            border: 1px solid #555;
            z-index: 1000;
        }
        circle { cursor: grab; }
        circle:active { cursor: grabbing; }
        circle.module { fill: rgba(79,195,247,0.1); stroke: #4fc3f7; stroke-width: 2; }
        circle.module-external { fill: rgba(244,135,113,0.1); stroke: #f48771; stroke-width: 2; }
        circle.notebook { fill: rgba(129,199,132,0.05); stroke: #81c784; stroke-width: 1.5; }
        circle.symbol-internal { fill: #4fc3f7; stroke: #4fc3f7; stroke-width: 3; stroke-opacity: 0; }
        circle.symbol-external { fill: #f48771; stroke: #f48771; stroke-width: 3; stroke-opacity: 0; }
        circle.symbol-internal:hover, circle.symbol-external:hover { stroke-opacity: 0.5; }
        text.label { pointer-events: none; text-anchor: middle; }
        text.module-label { font-size: 14px; font-weight: bold; fill: #4fc3f7; }
        text.module-external-label { font-size: 14px; font-weight: bold; fill: #f48771; }
        text.notebook-label { font-size: 11px; font-weight: 500; fill: #81c784; }
        text.symbol-label { font-size: 10px; fill: #e0e0e0; }
        .link { fill: none; stroke: #888; stroke-opacity: 0.4; stroke-width: 1; }
        .link.highlight { stroke: #ff0; stroke-opacity: 1; stroke-width: 2; }
    </style>
</head>
<body>
    <div id="controls">
        <button onclick="zoomIn()">Zoom +</button>
        <button onclick="zoomOut()">Zoom -</button>
        <button onclick="resetView()">Reset</button>
        <button onclick="toggleLabels()" id="labelBtn" class="active">Labels</button>
        <button onclick="toggleLinks()" id="linkBtn" class="active">Links</button>
    </div>
    <div id="info">
        ${internalNodes.length} internal • ${trueExternalNodes.length} external • ${edges.length} imports<br>
        <small>Drag circles to move • Scroll to zoom • Click to highlight</small>
    </div>
    <div id="legend">
        <div class="legend-item"><svg width="20" height="20"><circle cx="10" cy="10" r="8" fill="rgba(79,195,247,0.1)" stroke="#4fc3f7" stroke-width="2"/></svg> Module</div>
        <div class="legend-item"><svg width="20" height="20"><circle cx="10" cy="10" r="6" fill="rgba(129,199,132,0.05)" stroke="#81c784" stroke-width="1.5"/></svg> Notebook</div>
        <div class="legend-item"><svg width="20" height="20"><circle cx="10" cy="10" r="4" fill="#4fc3f7"/></svg> Internal Symbol</div>
        <div class="legend-item"><svg width="20" height="20"><circle cx="10" cy="10" r="8" fill="rgba(244,135,113,0.1)" stroke="#f48771" stroke-width="2"/></svg> External Package</div>
        <div class="legend-item"><svg width="20" height="20"><circle cx="10" cy="10" r="4" fill="#f48771"/></svg> External Symbol</div>
    </div>
    <div id="tooltip"></div>
    <svg id="graph"></svg>

    <script src="https://d3js.org/d3.v7.min.js"></script>
    <script>
        const data = ${graphData};
        const width = window.innerWidth;
        const height = window.innerHeight;
        let showLabels = true;
        let showLinks = true;

        const svg = d3.select("#graph")
            .attr("width", width)
            .attr("height", height);

        const g = svg.append("g");

        // Zoom
        const zoom = d3.zoom()
            .scaleExtent([0.1, 6])
            .on("zoom", e => g.attr("transform", e.transform));
        svg.call(zoom);

        // Create hierarchy and pack layout
        const root = d3.hierarchy(data.hierarchy)
            .sum(d => d.children ? 0 : 1)
            .sort((a, b) => b.value - a.value);

        const pack = d3.pack()
            .size([Math.max(width * 2, 1600), Math.max(height * 2, 1200)])
            .padding(d => d.depth === 0 ? 50 : d.depth === 1 ? 30 : 15);

        pack(root);

        // Store original packed radius for containment
        root.descendants().forEach(d => {
            d.packedR = d.r;
            d.originalX = d.x;
            d.originalY = d.y;
        });

        // Build node lookup by fullId for edges
        const nodeById = new Map();
        root.descendants().forEach(d => {
            if (d.data.fullId) {
                nodeById.set(d.data.fullId, d);
            }
        });

        // Draw links layer
        const linksG = g.append("g").attr("class", "links-layer");
        const linkData = data.edges
            .filter(e => nodeById.has(e.source) && nodeById.has(e.target))
            .map(e => ({
                source: nodeById.get(e.source),
                target: nodeById.get(e.target)
            }));

        const links = linksG.selectAll("line")
            .data(linkData)
            .join("line")
            .attr("class", "link");

        // Draw circles layer - sorted by depth for proper layering
        const circlesG = g.append("g").attr("class", "circles-layer");
        const allNodes = root.descendants().filter(d => d.depth > 0);
        allNodes.sort((a, b) => a.depth - b.depth);

        const circles = circlesG.selectAll("circle")
            .data(allNodes)
            .join("circle")
            .attr("r", d => d.r)
            .attr("class", d => {
                if (d.depth === 1) return d.data.isExternal ? "module-external" : "module";
                if (d.children) return "notebook";
                return d.data.type === "external" ? "symbol-external" : "symbol-internal";
            })
            .on("click", (event, d) => {
                event.stopPropagation();
                if (!d.children && d.data.fullId) highlightConnections(d.data.fullId);
            })
            .on("mouseover", (event, d) => {
                const tooltip = document.getElementById("tooltip");
                tooltip.style.display = "block";
                tooltip.style.left = (event.pageX + 15) + "px";
                tooltip.style.top = (event.pageY + 15) + "px";
                tooltip.innerHTML = d.children
                    ? "<strong>" + d.data.name + "</strong><br>" + d.leaves().length + " symbols"
                    : "<strong>" + d.data.name + "</strong><br>" + (d.data.fullId || "");
            })
            .on("mouseout", () => document.getElementById("tooltip").style.display = "none");

        // Draw labels layer
        const labelsG = g.append("g").attr("class", "labels-layer");
        const labels = labelsG.selectAll("text")
            .data(allNodes)
            .join("text")
            .attr("class", d => {
                if (d.depth === 1) return d.data.isExternal ? "label module-external-label" : "label module-label";
                if (d.children) return "label notebook-label";
                return "label symbol-label";
            })
            .text(d => d.data.name);

        // Manual physics - no D3 force simulation
        // Clamp node inside its parent, OR push parent if node is being dragged
        function clampToParent(node, pushParent = false) {
            if (!node.parent || node.parent.depth === 0) return;
            const p = node.parent;
            const dx = node.x - p.x;
            const dy = node.y - p.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            const maxDist = p.r - node.r - 2;
            if (maxDist > 0 && dist > maxDist) {
                if (pushParent) {
                    // Push parent to keep child at its position
                    const excess = dist - maxDist;
                    const nx = dx / dist;
                    const ny = dy / dist;
                    p.x += nx * excess;
                    p.y += ny * excess;
                    // Recursively push grandparent if needed
                    clampToParent(p, true);
                } else {
                    // Clamp child inside parent
                    node.x = p.x + (dx / dist) * maxDist;
                    node.y = p.y + (dy / dist) * maxDist;
                }
            }
        }

        // Resolve collision between two sibling nodes (moves both nodes and their descendants)
        function resolveCollision(a, b) {
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            const minDist = a.r + b.r + 4;
            if (dist < minDist && dist > 0.1) {
                const overlap = (minDist - dist) / 2;
                const nx = dx / dist;
                const ny = dy / dist;

                // Move node a and all its descendants
                const moveA = (node) => {
                    node.x -= nx * overlap;
                    node.y -= ny * overlap;
                };
                moveA(a);
                if (a.children) a.descendants().slice(1).forEach(moveA);

                // Move node b and all its descendants
                const moveB = (node) => {
                    node.x += nx * overlap;
                    node.y += ny * overlap;
                };
                moveB(b);
                if (b.children) b.descendants().slice(1).forEach(moveB);
            }
        }

        // Run physics step
        function physicsStep() {
            // Collision between siblings at each depth level (top-down)
            for (let depth = 1; depth <= 3; depth++) {
                const nodesAtDepth = allNodes.filter(d => d.depth === depth);
                // Group by parent
                const byParent = new Map();
                nodesAtDepth.forEach(n => {
                    const key = n.parent ? n.parent.data.name : 'root';
                    if (!byParent.has(key)) byParent.set(key, []);
                    byParent.get(key).push(n);
                });
                // Resolve collisions within each group
                byParent.forEach(siblings => {
                    for (let i = 0; i < siblings.length; i++) {
                        for (let j = i + 1; j < siblings.length; j++) {
                            resolveCollision(siblings[i], siblings[j]);
                        }
                    }
                });
            }
            // Containment - process from deepest to shallowest
            const maxDepth = d3.max(allNodes, d => d.depth) || 1;
            for (let depth = maxDepth; depth >= 1; depth--) {
                allNodes.filter(d => d.depth === depth).forEach(d => clampToParent(d, false));
            }
        }

        // Animation loop for physics
        let animating = false;
        function animate() {
            if (!animating) return;
            for (let i = 0; i < 3; i++) physicsStep();
            updatePositions();
            requestAnimationFrame(animate);
        }

        // Track which node is being dragged
        let draggedNode = null;

        // Drag behavior
        circles.call(d3.drag()
            .on("start", (event, d) => {
                draggedNode = d;
                animating = true;
                animate();
            })
            .on("drag", (event, d) => {
                // Store old positions of ancestors to move their children
                const ancestors = [];
                let p = d.parent;
                while (p && p.depth > 0) {
                    ancestors.push({ node: p, oldX: p.x, oldY: p.y });
                    p = p.parent;
                }

                // Move this node
                const oldX = d.x, oldY = d.y;
                d.x = event.x;
                d.y = event.y;

                // Push parent containers if hitting boundary
                clampToParent(d, true);

                // If container, move all descendants with it
                if (d.children) {
                    const dx = d.x - oldX;
                    const dy = d.y - oldY;
                    d.descendants().slice(1).forEach(c => {
                        c.x += dx;
                        c.y += dy;
                    });
                }

                // Move siblings of pushed ancestors
                ancestors.forEach(({ node, oldX, oldY }) => {
                    const dx = node.x - oldX;
                    const dy = node.y - oldY;
                    if (dx !== 0 || dy !== 0) {
                        // Move all descendants of this ancestor (except the dragged subtree)
                        node.descendants().slice(1).forEach(c => {
                            if (c !== d && !isDescendant(c, d) && !isDescendant(d, c)) {
                                c.x += dx;
                                c.y += dy;
                            }
                        });
                    }
                });
            })
            .on("end", (event, d) => {
                draggedNode = null;
                setTimeout(() => { animating = false; }, 500);
            }));

        function isDescendant(node, potentialAncestor) {
            let p = node.parent;
            while (p) {
                if (p === potentialAncestor) return true;
                p = p.parent;
            }
            return false;
        }

        // Initial physics settling
        animating = true;
        setTimeout(() => { animating = false; }, 1000);
        animate();

        function updatePositions() {
            circles.attr("cx", d => d.x).attr("cy", d => d.y);
            labels.attr("x", d => d.x).attr("y", d => d.children ? d.y - d.r + 16 : d.y + 3);
            links.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
                 .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
        }

        function highlightConnections(id) {
            const connected = new Set([id]);
            linkData.forEach(l => {
                if (l.source.data.fullId === id) connected.add(l.target.data.fullId);
                if (l.target.data.fullId === id) connected.add(l.source.data.fullId);
            });
            links.classed("highlight", d => d.source.data.fullId === id || d.target.data.fullId === id);
            circles.style("opacity", d => d.children ? 1 : (connected.has(d.data.fullId) ? 1 : 0.15));
            labels.style("opacity", d => d.children ? 1 : (connected.has(d.data.fullId) ? 1 : 0.15));
        }

        svg.on("click", () => {
            links.classed("highlight", false);
            circles.style("opacity", 1);
            labels.style("opacity", 1);
        });

        function zoomIn() { svg.transition().call(zoom.scaleBy, 1.5); }
        function zoomOut() { svg.transition().call(zoom.scaleBy, 0.67); }
        function resetView() {
            const s = Math.min((width - 40) / (root.r * 2), (height - 40) / (root.r * 2), 1) * 0.9;
            svg.transition().call(zoom.transform, d3.zoomIdentity.translate(width/2 - root.x*s, height/2 - root.y*s).scale(s));
            links.classed("highlight", false);
            circles.style("opacity", 1);
            labels.style("opacity", 1);
        }

        function toggleLabels() {
            showLabels = !showLabels;
            labels.style("display", showLabels ? "block" : "none");
            document.getElementById("labelBtn").classList.toggle("active", showLabels);
        }

        function toggleLinks() {
            showLinks = !showLinks;
            links.style("display", showLinks ? "block" : "none");
            document.getElementById("linkBtn").classList.toggle("active", showLinks);
        }

        // Initial centered view
        const initScale = Math.min((width - 40) / (root.r * 2), (height - 40) / (root.r * 2), 1) * 0.9;
        svg.call(zoom.transform, d3.zoomIdentity.translate(width/2 - root.x*initScale, height/2 - root.y*initScale).scale(initScale));
    </script>
</body>
</html>`;
}
