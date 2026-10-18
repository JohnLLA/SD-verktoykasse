// Inngang. Alt her kjører lokalt i appen; ingen nettkall, ingen eksterne
// skript eller fonter.

import { createTauriPlatform, insideTauri } from "./platform/tauri";
import type { Platform } from "./platform/types";
import { startApp } from "./shell/app";
import { tools } from "./tools/registry";

async function boot(): Promise<void> {
  const root = document.getElementById("app");
  if (!root) return;
  let platform: Platform;
  if (insideTauri()) {
    platform = createTauriPlatform();
  } else if (import.meta.env.DEV) {
    // Under utvikling i en vanlig nettleser: prøvevisning uten Tauri (src/dev).
    const { installMock } = await import("./dev/mock");
    platform = await installMock();
  } else {
    return;
  }
  await startApp(root, platform, tools);
}

void boot();
