import * as vscode from "vscode";

export class FlashPanel {
  public static currentPanel: FlashPanel | undefined;
  private readonly _panel: vscode.WebviewPanel;

  public static createOrShow(extensionUri: vscode.Uri): void {
    const column = vscode.window.activeTextEditor?.viewColumn;
    if (FlashPanel.currentPanel) {
      FlashPanel.currentPanel._panel.reveal(column);
      return;
    }
    const panel = vscode.window.createWebviewPanel(
      "aiSupportFlash",
      "AI_SUPPORT Flash",
      column ?? vscode.ViewColumn.One,
      { enableScripts: true, retainContextWhenHidden: true },
    );
    FlashPanel.currentPanel = new FlashPanel(panel, extensionUri);
  }

  private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri) {
    this._panel = panel;
    this._panel.webview.html = this._getHtml();
    this._panel.onDidDispose(() => {
      FlashPanel.currentPanel = undefined;
    }, null);
  }

  private _getHtml(): string {
    return `<!DOCTYPE html>
<html><body>
  <h2>Flash Firmware</h2>
  <p>Dry-run / plan UI — connect to AI_SUPPORT server or CLI.</p>
  <label>Target <select id="target"><option>EngineCar</option><option>RemoteControl</option></select></label>
  <button onclick="vscode.postMessage({command:'flash', dryRun:true})">Plan Flash</button>
  <script>const vscode = acquireVsCodeApi();</script>
</body></html>`;
  }
}
