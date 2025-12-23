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
                    showOutputPanel('Dependency Tree', result.diagram as string || result.output as string || JSON.stringify(result, null, 2));
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
                    const issues = result.issues as Array<Record<string, unknown>> || [];
                    if (issues.length === 0) {
                        vscode.window.showInformationMessage('Module index looks healthy');
                    } else {
                        showOutputPanel('Module Index Audit', formatAuditIssues(issues));
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

function formatAuditIssues(issues: Array<Record<string, unknown>>): string {
    const lines: string[] = [];
    lines.push('Module Index Audit Results:');
    lines.push('');

    for (const issue of issues) {
        lines.push(`[${issue.severity}] ${issue.message}`);
        if (issue.notebook) {
            lines.push(`  Notebook: ${issue.notebook}`);
        }
        if (issue.symbol) {
            lines.push(`  Symbol: ${issue.symbol}`);
        }
        lines.push('');
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
