import * as vscode from 'vscode';
import * as path from 'path';

export class NbdevDiagnostics implements vscode.Disposable {
    private collection: vscode.DiagnosticCollection;

    constructor() {
        this.collection = vscode.languages.createDiagnosticCollection('nbdev-mcp');
    }

    updateDiagnostics(issues: Array<Record<string, unknown>>): void {
        this.collection.clear();
        const diagnosticMap = new Map<string, vscode.Diagnostic[]>();

        for (const issue of issues) {
            const filePath = issue.notebook as string || issue.file as string;
            if (!filePath) continue;

            const uri = vscode.Uri.file(filePath);
            const uriString = uri.toString();

            if (!diagnosticMap.has(uriString)) {
                diagnosticMap.set(uriString, []);
            }

            const line = (issue.line as number) || (issue.cell_index as number) || 0;
            const message = issue.message as string || issue.error as string || 'Unknown issue';
            const severity = this.getSeverity(issue.severity as string);

            const range = new vscode.Range(
                new vscode.Position(line, 0),
                new vscode.Position(line, Number.MAX_VALUE)
            );

            const diagnostic = new vscode.Diagnostic(range, message, severity);
            diagnostic.source = 'nbdev-mcp';
            diagnostic.code = issue.code as string || issue.type as string;

            diagnosticMap.get(uriString)!.push(diagnostic);
        }

        for (const [uriString, diagnostics] of diagnosticMap) {
            this.collection.set(vscode.Uri.parse(uriString), diagnostics);
        }
    }

    updateDiagnosticsFromLint(issues: Array<Record<string, unknown>>): void {
        this.collection.clear();
        const diagnosticMap = new Map<string, vscode.Diagnostic[]>();

        for (const issue of issues) {
            const notebook = issue.notebook as string;
            if (!notebook) continue;

            const uri = vscode.Uri.file(notebook);
            const uriString = uri.toString();

            if (!diagnosticMap.has(uriString)) {
                diagnosticMap.set(uriString, []);
            }

            const cellIndex = issue.cell_index as number || 0;
            const message = this.formatLintMessage(issue);
            const severity = this.getLintSeverity(issue.type as string);

            const range = new vscode.Range(
                new vscode.Position(cellIndex, 0),
                new vscode.Position(cellIndex, Number.MAX_VALUE)
            );

            const diagnostic = new vscode.Diagnostic(range, message, severity);
            diagnostic.source = 'nbdev-mcp';
            diagnostic.code = issue.type as string;

            diagnosticMap.get(uriString)!.push(diagnostic);
        }

        for (const [uriString, diagnostics] of diagnosticMap) {
            this.collection.set(vscode.Uri.parse(uriString), diagnostics);
        }
    }

    updateDiagnosticsFromImports(issues: Array<Record<string, unknown>>): void {
        this.collection.clear();
        const diagnosticMap = new Map<string, vscode.Diagnostic[]>();

        for (const issue of issues) {
            const notebook = issue.notebook as string;
            if (!notebook) continue;

            const uri = vscode.Uri.file(notebook);
            const uriString = uri.toString();

            if (!diagnosticMap.has(uriString)) {
                diagnosticMap.set(uriString, []);
            }

            const cellIndex = issue.cell_index as number || 0;
            const unusedImports = issue.unused_imports as string[] || [];
            const message = `Unused imports: ${unusedImports.join(', ')}`;

            const range = new vscode.Range(
                new vscode.Position(cellIndex, 0),
                new vscode.Position(cellIndex, Number.MAX_VALUE)
            );

            const diagnostic = new vscode.Diagnostic(
                range,
                message,
                vscode.DiagnosticSeverity.Warning
            );
            diagnostic.source = 'nbdev-mcp';
            diagnostic.code = 'unused-import';

            diagnosticMap.get(uriString)!.push(diagnostic);
        }

        for (const [uriString, diagnostics] of diagnosticMap) {
            this.collection.set(vscode.Uri.parse(uriString), diagnostics);
        }
    }

    updateDiagnosticsFromErrors(errors: Array<Record<string, unknown>>): void {
        this.collection.clear();
        const diagnosticMap = new Map<string, vscode.Diagnostic[]>();

        for (const error of errors) {
            const notebook = error.notebook as string;
            if (!notebook) continue;

            const uri = vscode.Uri.file(notebook);
            const uriString = uri.toString();

            if (!diagnosticMap.has(uriString)) {
                diagnosticMap.set(uriString, []);
            }

            const cellIndex = error.cell_index as number || 0;
            const errorType = error.error_type as string || 'Error';
            const traceback = error.traceback as string || '';
            const message = `${errorType}: ${traceback.substring(0, 200)}${traceback.length > 200 ? '...' : ''}`;

            const range = new vscode.Range(
                new vscode.Position(cellIndex, 0),
                new vscode.Position(cellIndex, Number.MAX_VALUE)
            );

            const diagnostic = new vscode.Diagnostic(
                range,
                message,
                vscode.DiagnosticSeverity.Error
            );
            diagnostic.source = 'nbdev-mcp';
            diagnostic.code = 'notebook-error-output';

            diagnosticMap.get(uriString)!.push(diagnostic);
        }

        for (const [uriString, diagnostics] of diagnosticMap) {
            this.collection.set(vscode.Uri.parse(uriString), diagnostics);
        }
    }

    private getSeverity(severity: string | undefined): vscode.DiagnosticSeverity {
        switch (severity?.toLowerCase()) {
            case 'error':
                return vscode.DiagnosticSeverity.Error;
            case 'warning':
                return vscode.DiagnosticSeverity.Warning;
            case 'info':
            case 'information':
                return vscode.DiagnosticSeverity.Information;
            case 'hint':
                return vscode.DiagnosticSeverity.Hint;
            default:
                return vscode.DiagnosticSeverity.Warning;
        }
    }

    private getLintSeverity(type: string | undefined): vscode.DiagnosticSeverity {
        switch (type) {
            case 'relative_import':
            case 'duplicate_export':
                return vscode.DiagnosticSeverity.Warning;
            case '__all__':
                return vscode.DiagnosticSeverity.Information;
            default:
                return vscode.DiagnosticSeverity.Warning;
        }
    }

    private formatLintMessage(issue: Record<string, unknown>): string {
        const type = issue.type as string;
        switch (type) {
            case 'relative_import':
                return `Relative import found: ${issue.import_statement || ''}. Use absolute imports.`;
            case '__all__':
                return 'Manual __all__ definition found. Let nbdev manage exports.';
            case 'duplicate_export':
                return `Duplicate export: '${issue.symbol}' also exported in ${issue.other_notebooks}`;
            default:
                return issue.message as string || `Lint issue: ${type}`;
        }
    }

    clear(): void {
        this.collection.clear();
    }

    dispose(): void {
        this.collection.dispose();
    }
}
