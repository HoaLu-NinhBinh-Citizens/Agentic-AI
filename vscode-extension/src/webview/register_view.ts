import * as vscode from "vscode";

export class RegisterViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "aiSupportTargets";

  constructor(private readonly _extensionUri: vscode.Uri) {}

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken,
  ): void {
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = `<!DOCTYPE html>
<html><body>
  <h3>Registers</h3>
  <p>PC, SP, LR — live values via AI_SUPPORT trace API.</p>
</body></html>`;
  }
}
