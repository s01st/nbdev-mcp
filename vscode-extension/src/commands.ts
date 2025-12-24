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
            await runWithProgress('Generating dependency tree...', async () => {
                const result = await client.callTool('dependency_tree', { scope: 'internal' });
                if (result.ok) {
                    // Show Mermaid diagram in WebView
                    const mermaid = result.mermaid as string;
                    if (mermaid) {
                        showMermaidPanel(context, 'Dependency Tree', mermaid);
                    } else {
                        showOutputPanel('Dependency Tree', JSON.stringify(result, null, 2));
                    }
                } else {
                    vscode.window.showErrorMessage(`Failed: ${result.error}`);
                }
            });
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.modidxAudit', async () => {
            await runWithProgress('Auditing module index...', async () => {
                const result = await client.callTool('modidx_audit', {});
                if (result.ok) {
                    const duplicates = result.duplicates as Array<Record<string, unknown>> || [];
                    const privateExports = result.private_exports as Array<Record<string, unknown>> || [];
                    const numberingIssues = result.numbering_issues as Array<Record<string, unknown>> || [];
                    const totalIssues = duplicates.length + privateExports.length + numberingIssues.length;

                    if (totalIssues === 0) {
                        vscode.window.showInformationMessage('Module index looks healthy');
                    } else {
                        showOutputPanel('Module Index Audit', formatModidxAudit(result));
                    }
                } else {
                    vscode.window.showErrorMessage(`Audit failed: ${result.error}`);
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
                if (result.ok) {
                    const deadExports = result.dead_exports as Array<Record<string, unknown>> || [];
                    if (deadExports.length === 0) {
                        vscode.window.showInformationMessage('No dead exports found');
                    } else {
                        showOutputPanel('Dead Exports', formatDeadExports(deadExports));
                    }
                } else {
                    vscode.window.showErrorMessage(`Analysis failed: ${result.error}`);
                }
            });
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.dependencyNotebook', async () => {
            await runWithProgress('Generating dependency notebook...', async () => {
                const result = await client.callTool('dependency_notebook', {});
                if (result.ok) {
                    const notebookPath = result.notebook_path as string;
                    const action = await vscode.window.showInformationMessage(
                        `Dependency notebook created: ${notebookPath}`,
                        'Open Notebook'
                    );
                    if (action === 'Open Notebook') {
                        const uri = vscode.Uri.file(notebookPath);
                        await vscode.window.showTextDocument(uri);
                    }
                } else {
                    vscode.window.showErrorMessage(`Generation failed: ${result.error}`);
                }
            });
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.generateApiDocs', async () => {
            await runWithProgress('Generating API documentation...', async () => {
                const result = await client.callTool('generate_api_docs', {});
                if (result.ok) {
                    const notebookPath = result.notebook_path as string;
                    const action = await vscode.window.showInformationMessage(
                        `API docs notebook created: ${notebookPath}`,
                        'Open Notebook'
                    );
                    if (action === 'Open Notebook') {
                        const uri = vscode.Uri.file(notebookPath);
                        await vscode.window.showTextDocument(uri);
                    }
                } else {
                    vscode.window.showErrorMessage(`Generation failed: ${result.error}`);
                }
            });
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
        { enableScripts: true }
    );

    panel.webview.html = `<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${title}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body {
            background: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
            font-family: var(--vscode-font-family);
            padding: 20px;
        }
        .mermaid {
            display: flex;
            justify-content: center;
        }
        h1 {
            font-size: 1.5em;
            margin-bottom: 20px;
            border-bottom: 1px solid var(--vscode-panel-border);
            padding-bottom: 10px;
        }
        pre {
            background: var(--vscode-textBlockQuote-background);
            padding: 10px;
            border-radius: 4px;
            overflow-x: auto;
            font-size: 12px;
            margin-top: 20px;
        }
        .toggle {
            cursor: pointer;
            color: var(--vscode-textLink-foreground);
            margin-top: 20px;
        }
        .code-block { display: none; }
    </style>
</head>
<body>
    <h1>${title}</h1>
    <div class="mermaid">
${mermaidCode}
    </div>
    <div class="toggle" onclick="document.querySelector('.code-block').style.display = document.querySelector('.code-block').style.display === 'none' ? 'block' : 'none'">
        Show/Hide Mermaid Code
    </div>
    <pre class="code-block">${mermaidCode.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
    <script>
        mermaid.initialize({
            startOnLoad: true,
            theme: document.body.classList.contains('vscode-dark') ? 'dark' : 'default'
        });
    </script>
</body>
</html>`;
}
