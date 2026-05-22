import * as vscode from "vscode";
import { registerDebugProvider } from "./debug/debug_adapter";
import { FlashPanel } from "./flash/flash_panel";
import { RegisterViewProvider } from "./webview/register_view";

export function activate(context: vscode.ExtensionContext): void {
  const registerProvider = new RegisterViewProvider(context.extensionUri);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      RegisterViewProvider.viewType,
      registerProvider,
    ),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("aiSupport.openFlashPanel", () => {
      FlashPanel.createOrShow(context.extensionUri);
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("aiSupport.openRegisterView", async () => {
      await vscode.commands.executeCommand(
        "workbench.view.extension.aiSupportTargets",
      );
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("aiSupport.connectTarget", async () => {
      const target = await vscode.window.showQuickPick(
        ["EngineCar", "RemoteControl", "Generic_STM32F407"],
        { placeHolder: "Select target" },
      );
      if (target) {
        vscode.window.showInformationMessage(
          `AI_SUPPORT: connect ${target} (wire to CLI/server)`,
        );
      }
    }),
  );

  registerDebugProvider(context);
}

export function deactivate(): void {}
