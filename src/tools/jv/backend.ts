// Kallene til Rust-modulen `jv`. Dette er det eneste stedet som kaller
// `invoke("plugin:jv|…")`. Grensesnittet `JvBackend` gjør at controller kan
// testes med en falsk kjerne. Rå feil, stier og filnavn når aldri brukeren.

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import {
  JV_ERROR_CODES,
  JV_EVENTS,
  type CatalogView,
  type InstallDoneEvent,
  type InstallProgressEvent,
  type InstalledView,
  type JvError,
  type JvJobId,
  type PlanView,
  type RunDoneEvent,
  type RunProgressEvent,
  type RunRequest,
} from "./api";

export interface JvBackendEvents {
  installProgress(ev: InstallProgressEvent): void;
  installDone(ev: InstallDoneEvent): void;
  runProgress(ev: RunProgressEvent): void;
  runDone(ev: RunDoneEvent): void;
}

export interface JvBackend {
  /** `fetch = false`: bare siste kontrollerte kopi, uten nett. */
  catalog(fetch: boolean): Promise<CatalogView>;
  installed(): Promise<InstalledView[]>;
  install(id: string): Promise<JvJobId>;
  remove(id: string): Promise<void>;
  run(id: string, request: RunRequest): Promise<JvJobId>;
  cancel(jobId: JvJobId): Promise<void>;
  readPlan(path: string): Promise<PlanView>;
  savePlan(path: string, redact: Record<string, boolean>): Promise<void>;
  listen(handlers: JvBackendEvents): Promise<() => void>;
}

const KNOWN = new Set<string>(JV_ERROR_CODES);

/** Gjør alt som kan komme fra `invoke` om til en `JvError`. */
export function toJvError(e: unknown): JvError {
  if (e && typeof e === "object" && "code" in e) {
    const code = (e as { code: unknown }).code;
    if (typeof code === "string" && KNOWN.has(code)) return e as JvError;
  }
  return { code: "internal" };
}

const call = async <T>(command: string, args?: Record<string, unknown>): Promise<T> => {
  try {
    return await invoke<T>(`plugin:jv|${command}`, args);
  } catch (e) {
    throw toJvError(e);
  }
};

export const tauriJvBackend: JvBackend = {
  catalog: (fetch) => call("jv_catalog", { fetch }),
  installed: () => call("jv_installed"),
  install: (id) => call("jv_install", { id }),
  remove: (id) => call("jv_remove", { id }),
  run: (id, request) => call("jv_run", { id, request }),
  cancel: (jobId) => call("jv_cancel", { jobId }),
  readPlan: (path) => call("jv_read_plan", { path }),
  savePlan: (path, redact) => call("jv_save_plan", { path, redact }),

  async listen(h) {
    const offs: UnlistenFn[] = await Promise.all([
      listen<InstallProgressEvent>(JV_EVENTS.installProgress, (e) => h.installProgress(e.payload)),
      listen<InstallDoneEvent>(JV_EVENTS.installDone, (e) => h.installDone(e.payload)),
      listen<RunProgressEvent>(JV_EVENTS.runProgress, (e) => h.runProgress(e.payload)),
      listen<RunDoneEvent>(JV_EVENTS.runDone, (e) => h.runDone(e.payload)),
    ]);
    return () => offs.forEach((off) => off());
  },
};

let override: JvBackend | null = null;

/** Brukes av prøvevisningen i `src/dev` til å bytte ut kjernen. */
export function setJvBackend(b: JvBackend | null): void {
  override = b;
}

export function getJvBackend(): JvBackend {
  return override ?? tauriJvBackend;
}
