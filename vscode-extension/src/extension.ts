import * as vscode from 'vscode';
import { NbdevMcpClient } from './mcpClient';
import { registerCommands } from './commands';
import { NbdevDiagnostics } from './diagnostics';
import { ProjectViewProvider, CommandsViewProvider, NotebooksViewProvider } from './views';

let mcpClient: NbdevMcpClient | undefined;
let diagnostics: NbdevDiagnostics | undefined;
let projectView: ProjectViewProvider | undefined;
let notebooksView: NotebooksViewProvider | undefined;

export async function activate(context: vscode.ExtensionContext) {
    console.log('nbdev-mcp extension is activating...');

    // Initialize MCP client
    mcpClient = new NbdevMcpClient();

    // Initialize diagnostics provider
    diagnostics = new NbdevDiagnostics();
    context.subscriptions.push(diagnostics);

    // Initialize and register tree views
    projectView = new ProjectViewProvider(mcpClient);
    const commandsView = new CommandsViewProvider();
    notebooksView = new NotebooksViewProvider(mcpClient);

    vscode.window.registerTreeDataProvider('nbdev-project', projectView);
    vscode.window.registerTreeDataProvider('nbdev-commands', commandsView);
    vscode.window.registerTreeDataProvider('nbdev-notebooks', notebooksView);

    // Register refresh command
    context.subscriptions.push(
        vscode.commands.registerCommand('nbdev-mcp.refresh', () => {
            projectView?.refresh();
            notebooksView?.refresh();
        })
    );

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
            // Found an nbdev project - parse settings.ini for lib_name
            const projectPath = folder.uri.fsPath;
            let libName = folder.name;
            let nbsDir = `${projectPath}/nbs`;

            // Try to read settings.ini for lib_name and nbs_path
            try {
                const settingsContent = await vscode.workspace.fs.readFile(settingsIni);
                const settingsText = Buffer.from(settingsContent).toString('utf8');

                // Parse lib_name from settings.ini
                const libMatch = settingsText.match(/^lib_name\s*=\s*(.+)$/m);
                if (libMatch) {
                    libName = libMatch[1].trim();
                }

                // Parse nbs_path from settings.ini
                const nbsMatch = settingsText.match(/^nbs_path\s*=\s*(.+)$/m);
                if (nbsMatch) {
                    nbsDir = `${projectPath}/${nbsMatch[1].trim()}`;
                }
            } catch {
                // Use defaults if can't parse
            }

            // Update client's current project
            client.setProject(projectPath);

            // Update views with project info
            const projectInfo = {
                project: projectPath,
                lib_name: libName,
                nbs_dir: nbsDir
            };
            projectView?.setProjectInfo(projectInfo);
            notebooksView?.setNbsDir(nbsDir);

            vscode.window.showInformationMessage(
                `nbdev project detected: ${libName}`
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
