import * as vscode from 'vscode';
import * as path from 'path';
import { NbdevMcpClient } from './mcpClient';

// Tree item for various views
export class NbdevTreeItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState,
        public readonly command?: vscode.Command,
        public readonly contextValue?: string,
        public readonly iconPath?: vscode.ThemeIcon,
        public readonly description?: string
    ) {
        super(label, collapsibleState);
        this.command = command;
        this.contextValue = contextValue;
        this.iconPath = iconPath;
        this.description = description;
    }
}

// Project view provider - shows current project info
export class ProjectViewProvider implements vscode.TreeDataProvider<NbdevTreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<NbdevTreeItem | undefined | null | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private projectInfo: Record<string, unknown> | null = null;

    constructor(private mcpClient: NbdevMcpClient) {}

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    setProjectInfo(info: Record<string, unknown> | null): void {
        this.projectInfo = info;
        this.refresh();
    }

    getTreeItem(element: NbdevTreeItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: NbdevTreeItem): Thenable<NbdevTreeItem[]> {
        if (!this.projectInfo) {
            return Promise.resolve([]);
        }

        if (!element) {
            // Root level - show project details
            const items: NbdevTreeItem[] = [];

            if (this.projectInfo.project) {
                const projectPath = this.projectInfo.project as string;
                items.push(new NbdevTreeItem(
                    path.basename(projectPath),
                    vscode.TreeItemCollapsibleState.None,
                    undefined,
                    'project-root',
                    new vscode.ThemeIcon('folder'),
                    projectPath
                ));
            }

            if (this.projectInfo.lib_name) {
                items.push(new NbdevTreeItem(
                    'Library',
                    vscode.TreeItemCollapsibleState.None,
                    undefined,
                    'lib-name',
                    new vscode.ThemeIcon('package'),
                    this.projectInfo.lib_name as string
                ));
            }

            if (this.projectInfo.nbs_dir) {
                items.push(new NbdevTreeItem(
                    'Notebooks',
                    vscode.TreeItemCollapsibleState.None,
                    {
                        command: 'revealInExplorer',
                        title: 'Open Notebooks Folder',
                        arguments: [vscode.Uri.file(this.projectInfo.nbs_dir as string)]
                    },
                    'nbs-dir',
                    new vscode.ThemeIcon('notebook'),
                    path.basename(this.projectInfo.nbs_dir as string)
                ));
            }

            return Promise.resolve(items);
        }

        return Promise.resolve([]);
    }
}

// Commands view provider - shows available commands grouped by category
export class CommandsViewProvider implements vscode.TreeDataProvider<NbdevTreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<NbdevTreeItem | undefined | null | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private commands: CommandGroup[] = [
        {
            name: 'Build',
            icon: 'tools',
            commands: [
                { id: 'nbdev-mcp.export', label: 'Export Notebooks', icon: 'export' },
                { id: 'nbdev-mcp.prepare', label: 'Prepare (Export, Test, Clean)', icon: 'package' },
                { id: 'nbdev-mcp.test', label: 'Run Tests', icon: 'beaker' },
            ]
        },
        {
            name: 'Lint & Analysis',
            icon: 'search',
            commands: [
                { id: 'nbdev-mcp.showLintPanel', label: 'Run All Checks', icon: 'checklist' },
                { id: 'nbdev-mcp.lint', label: 'Lint Notebooks', icon: 'list-unordered' },
                { id: 'nbdev-mcp.lintImports', label: 'Check Unused Imports', icon: 'warning' },
                { id: 'nbdev-mcp.lintDeadExports', label: 'Find Dead Exports', icon: 'trash' },
                { id: 'nbdev-mcp.scanErrors', label: 'Scan Notebook Errors', icon: 'error' },
            ]
        },
        {
            name: 'Dependencies',
            icon: 'git-merge',
            commands: [
                { id: 'nbdev-mcp.dependencyTree', label: 'Show Dependency Graph', icon: 'type-hierarchy' },
                { id: 'nbdev-mcp.modidxAudit', label: 'Audit Module Index', icon: 'list-tree' },
            ]
        },
        {
            name: 'Documentation',
            icon: 'book',
            commands: [
                { id: 'nbdev-mcp.generateApiDocs', label: 'Preview Docs (Quarto)', icon: 'preview' },
                { id: 'nbdev-mcp.stopPreview', label: 'Stop Preview Server', icon: 'debug-stop' },
                { id: 'nbdev-mcp.runTutorials', label: 'Run Tutorials', icon: 'play' },
            ]
        },
        {
            name: 'Symbols',
            icon: 'symbol-method',
            commands: [
                { id: 'nbdev-mcp.findSymbol', label: 'Find Symbol', icon: 'search' },
                { id: 'nbdev-mcp.analyzeExports', label: 'Analyze Exports', icon: 'symbol-class' },
            ]
        }
    ];

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: NbdevTreeItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: NbdevTreeItem): Thenable<NbdevTreeItem[]> {
        if (!element) {
            // Root level - show command groups
            return Promise.resolve(
                this.commands.map(group => new NbdevTreeItem(
                    group.name,
                    vscode.TreeItemCollapsibleState.Collapsed,
                    undefined,
                    'command-group',
                    new vscode.ThemeIcon(group.icon)
                ))
            );
        }

        // Find the group and return its commands
        const group = this.commands.find(g => g.name === element.label);
        if (group) {
            return Promise.resolve(
                group.commands.map(cmd => new NbdevTreeItem(
                    cmd.label,
                    vscode.TreeItemCollapsibleState.None,
                    {
                        command: cmd.id,
                        title: cmd.label
                    },
                    'command',
                    new vscode.ThemeIcon(cmd.icon)
                ))
            );
        }

        return Promise.resolve([]);
    }
}

interface CommandGroup {
    name: string;
    icon: string;
    commands: { id: string; label: string; icon: string }[];
}

// Notebooks view provider - shows notebooks in the project
export class NotebooksViewProvider implements vscode.TreeDataProvider<NbdevTreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<NbdevTreeItem | undefined | null | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private nbsDir: string | null = null;

    constructor(private mcpClient: NbdevMcpClient) {}

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    setNbsDir(dir: string | null): void {
        this.nbsDir = dir;
        this.refresh();
    }

    getTreeItem(element: NbdevTreeItem): vscode.TreeItem {
        return element;
    }

    async getChildren(element?: NbdevTreeItem): Promise<NbdevTreeItem[]> {
        if (!this.nbsDir) {
            return [];
        }

        const targetDir = element?.resourceUri?.fsPath || this.nbsDir;

        try {
            const uri = vscode.Uri.file(targetDir);
            const entries = await vscode.workspace.fs.readDirectory(uri);

            const items: NbdevTreeItem[] = [];

            // Sort: directories first, then files
            const sorted = entries.sort((a, b) => {
                if (a[1] === vscode.FileType.Directory && b[1] !== vscode.FileType.Directory) return -1;
                if (a[1] !== vscode.FileType.Directory && b[1] === vscode.FileType.Directory) return 1;
                return a[0].localeCompare(b[0]);
            });

            for (const [name, type] of sorted) {
                // Skip hidden files and __pycache__
                if (name.startsWith('.') || name === '__pycache__') continue;

                const fullPath = path.join(targetDir, name);

                if (type === vscode.FileType.Directory) {
                    const item = new NbdevTreeItem(
                        name,
                        vscode.TreeItemCollapsibleState.Collapsed,
                        undefined,
                        'folder',
                        new vscode.ThemeIcon('folder')
                    );
                    item.resourceUri = vscode.Uri.file(fullPath);
                    items.push(item);
                } else if (name.endsWith('.ipynb')) {
                    const item = new NbdevTreeItem(
                        name.replace('.ipynb', ''),
                        vscode.TreeItemCollapsibleState.None,
                        {
                            command: 'vscode.open',
                            title: 'Open Notebook',
                            arguments: [vscode.Uri.file(fullPath)]
                        },
                        'notebook',
                        new vscode.ThemeIcon('notebook')
                    );
                    item.resourceUri = vscode.Uri.file(fullPath);
                    items.push(item);
                }
            }

            return items;
        } catch (error) {
            console.error('Failed to read notebooks directory:', error);
            return [];
        }
    }
}
