import * as vscode from 'vscode';
import { NbdevMcpClient } from './mcpClient';
import { registerCommands } from './commands';
import { NbdevDiagnostics } from './diagnostics';

let mcpClient: NbdevMcpClient | undefined;
let diagnostics: NbdevDiagnostics | undefined;

export async function activate(context: vscode.ExtensionContext) {
    console.log('nbdev-mcp extension is activating...');

    // Initialize MCP client
    mcpClient = new NbdevMcpClient();

    // Initialize diagnostics provider
    diagnostics = new NbdevDiagnostics();
    context.subscriptions.push(diagnostics);

    // Register all commands
    registerCommands(context, mcpClient, diagnostics);

    // Auto-detect project if enabled
    const config = vscode.workspace.getConfiguration('nbdev-mcp');
    if (config.get('autoDetectProject')) {
        await autoDetectProject(mcpClient);
    }

    // Set up file watchers for lint-on-save
    if (config.get('lintOnSave')) {
        const watcher = vscode.workspace.onDidSaveTextDocument(async (doc) => {
            if (doc.fileName.endsWith('.ipynb')) {
                await runLintOnFile(doc.fileName);
            }
        });
        context.subscriptions.push(watcher);
    }

    // Show status bar item
    const statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Left,
        100
    );
    statusBarItem.text = '$(notebook) nbdev';
    statusBarItem.tooltip = 'nbdev MCP - Click for commands';
    statusBarItem.command = 'nbdev-mcp.currentProject';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    console.log('nbdev-mcp extension activated');
}

async function autoDetectProject(client: NbdevMcpClient): Promise<void> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
        return;
    }

    for (const folder of workspaceFolders) {
        const settingsIni = vscode.Uri.joinPath(folder.uri, 'settings.ini');
        try {
            await vscode.workspace.fs.stat(settingsIni);
            // Found an nbdev project
            await client.setProject(folder.uri.fsPath);
            vscode.window.showInformationMessage(
                `nbdev project detected: ${folder.name}`
            );
            return;
        } catch {
            // No settings.ini in this folder
        }
    }
}

async function runLintOnFile(filePath: string): Promise<void> {
    if (!mcpClient || !diagnostics) {
        return;
    }

    try {
        const result = await mcpClient.callTool('lint_rules', {});
        if (result.ok && result.issues) {
            const issues = result.issues as Array<Record<string, unknown>>;
            diagnostics.updateDiagnostics(issues);
        }
    } catch (error) {
        console.error('Lint on save failed:', error);
    }
}

export function deactivate() {
    if (mcpClient) {
        mcpClient.dispose();
        mcpClient = undefined;
    }
}
