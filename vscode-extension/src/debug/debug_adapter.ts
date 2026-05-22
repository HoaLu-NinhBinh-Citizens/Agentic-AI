import * as vscode from "vscode";

/** Scaffold Debug Adapter Factory — integrate GDB/DAP later. */
export function registerDebugProvider(context: vscode.ExtensionContext): void {
  const provider = new AiSupportDebugConfigurationProvider();
  context.subscriptions.push(
    vscode.debug.registerDebugConfigurationProvider("ai-support", provider),
  );
}

class AiSupportDebugConfigurationProvider
  implements vscode.DebugConfigurationProvider
{
  resolveDebugConfiguration(
    _folder: vscode.WorkspaceFolder | undefined,
    config: vscode.DebugConfiguration,
  ): vscode.DebugConfiguration {
    if (!config.type) {
      config.type = "ai-support";
    }
    if (!config.name) {
      config.name = "AI_SUPPORT Attach";
    }
    config.request = config.request ?? "attach";
    config.target = config.target ?? "EngineCar";
    return config;
  }
}
