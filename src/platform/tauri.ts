// Tauri-versjonen av `Platform`. Ingen nettkall her: bare lokale vinduer,
// dialoger og filer. Ingen filnavn eller tekst skrives til konsollen (regel 2).

import { getVersion } from "@tauri-apps/api/app";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { open, save } from "@tauri-apps/plugin-dialog";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import { load, type Store } from "@tauri-apps/plugin-store";
import { SETTINGS_FILE } from "../tools/transkribering/api";
import { detectOs } from "../lib/platform-info";
import type { SettingsStore } from "../lib/settings";
import type { Platform } from "./types";

class TauriSettings implements SettingsStore {
  private store: Promise<Store> | null = null;

  private open(): Promise<Store> {
    // autoSave av: vi lagrer selv etter hver endring.
    this.store ??= load(SETTINGS_FILE, { defaults: {}, autoSave: false });
    return this.store;
  }

  async get(key: string): Promise<unknown> {
    return (await this.open()).get(key);
  }

  async set(key: string, value: unknown): Promise<void> {
    const s = await this.open();
    await s.set(key, value);
    await s.save();
  }
}

/** Tekst til utklippstavlen. Først det moderne kallet, så den gamle veien. */
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.className = "offscreen";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    ta.remove();
    return ok;
  }
}

export function createTauriPlatform(): Platform {
  return {
    os: detectOs(navigator.userAgent),
    settings: new TauriSettings(),

    async pickFiles({ title, filterName, extensions }) {
      const r = await open({
        title,
        multiple: true,
        directory: false,
        filters: [{ name: filterName, extensions }],
      });
      if (!r) return [];
      return Array.isArray(r) ? r : [r];
    },

    async pickFolder(title) {
      const r = await open({ title, multiple: false, directory: true });
      return typeof r === "string" ? r : null;
    },

    async pickSavePath({ title, defaultPath, extension, filterName }) {
      return save({ title, defaultPath, filters: [{ name: filterName, extensions: [extension] }] });
    },

    async onDrop({ onFiles, onHover }) {
      return getCurrentWebview().onDragDropEvent((event) => {
        const p = event.payload;
        if (p.type === "enter" || p.type === "over") onHover(true);
        else if (p.type === "leave") onHover(false);
        else if (p.type === "drop") {
          onHover(false);
          if (p.paths.length > 0) onFiles(p.paths);
        }
      });
    },

    async playbackUrl(path) {
      try {
        // Skallet åpner asset-protokollen for akkurat denne filen (src-tauri/src/shell.rs).
        const ok = await invoke<boolean>("allow_playback", { path });
        return ok ? convertFileSrc(path) : null;
      } catch {
        return null;
      }
    },

    async reveal(path) {
      await revealItemInDir(path);
    },

    copyText,

    async appVersion() {
      try {
        return await getVersion();
      } catch {
        return null;
      }
    },

    async checkForUpdate() {
      try {
        const r = await invoke<{ version: string } | null>("check_for_update", { manual: false });
        return r ? r.version : null;
      } catch {
        // Ingen nett, bryteren av eller annen feil: ingen melding til brukeren.
        return null;
      }
    },

    async checkForUpdateNow() {
      try {
        const r = await invoke<{ version: string } | null>("check_for_update", { manual: true });
        return r ? ({ status: "available", version: r.version } as const) : ({ status: "none" } as const);
      } catch {
        return { status: "failed" } as const;
      }
    },

    async installUpdate() {
      try {
        await invoke("install_update");
        return true;
      } catch {
        return false;
      }
    },

    async onCloseRequested(guard) {
      return getCurrentWindow().onCloseRequested(async (event) => {
        if (!(await guard())) event.preventDefault();
      });
    },
  };
}

/** Kjører vi inne i Tauri (og ikke i en vanlig nettleser under utvikling)? */
export function insideTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}
