// Innstillinger som huskes (Tauri store-plugin, `settings.json`). Grensesnittet
// snakker med `SettingsStore`, så logikken kan testes uten Tauri.

import type { Decoding } from "../tools/transkribering/api";
import {
  DEFAULT_CHOICES,
  DEFAULT_DECODING,
  normalizeChoices,
  normalizeDecoding,
  type Choices,
} from "./choices";

export interface SettingsStore {
  get(key: string): Promise<unknown>;
  set(key: string, value: unknown): Promise<void>;
}

export const KEYS = {
  malform: "transkribering.malform",
  stil: "transkribering.stil",
  kvalitet: "transkribering.kvalitet",
  decoding: "transkribering.decoding",
  versionCheck: "shell.versionCheck",
} as const;

export async function loadChoices(store: SettingsStore): Promise<Choices> {
  try {
    return normalizeChoices({
      malform: await store.get(KEYS.malform),
      stil: await store.get(KEYS.stil),
      kvalitet: await store.get(KEYS.kvalitet),
    });
  } catch {
    return { ...DEFAULT_CHOICES };
  }
}

export async function saveChoices(store: SettingsStore, c: Choices): Promise<void> {
  await store.set(KEYS.malform, c.malform);
  await store.set(KEYS.stil, c.stil);
  await store.set(KEYS.kvalitet, c.kvalitet);
}

export async function loadDecoding(store: SettingsStore): Promise<Decoding> {
  try {
    return normalizeDecoding(await store.get(KEYS.decoding));
  } catch {
    return DEFAULT_DECODING;
  }
}

/** Versjonssjekk er på som standard (spesifikasjonen: kan slås av). */
export async function loadVersionCheck(store: SettingsStore): Promise<boolean> {
  try {
    const v = await store.get(KEYS.versionCheck);
    return typeof v === "boolean" ? v : true;
  } catch {
    return true;
  }
}

/** Minneslager til tester og prøvevisning. */
export class MemorySettings implements SettingsStore {
  readonly data = new Map<string, unknown>();
  async get(key: string): Promise<unknown> {
    return this.data.get(key);
  }
  async set(key: string, value: unknown): Promise<void> {
    this.data.set(key, value);
  }
}
