// Typer for Rust-modulen `jv` (journalistverktøyene).
// Kilde: src-tauri/src/tools/jv/{commands,service,catalog,error,args,plan}.rs.
// `api.test.ts` sammenligner med Rust-filene, så de ikke kan komme ut av takt.
//
// Kommandoene kalles som `invoke("plugin:jv|<navn>", args)`. Argumentnavn på
// toppnivå er camelCase fra JS (`jobId`); feltene inne i objektene er snake_case.

import type { CoreError } from "../transkribering/api";

export type JvJobId = number;

/** De ni verktøyene, i menyrekkefølge (Rust: `catalog::KNOWN_TOOLS`). */
export const JV_TOOL_IDS = [
  "compare",
  "metadata",
  "keyframes",
  "loudness",
  "subtitles",
  "pdf-tables",
  "ocr",
  "redact",
  "nynorsk",
] as const;
export type JvToolId = (typeof JV_TOOL_IDS)[number];

export function isJvToolId(id: string): id is JvToolId {
  return (JV_TOOL_IDS as readonly string[]).includes(id);
}

/** Feil fra Rust (`JvError`). Ingen har filnavn eller stier. */
export type JvError =
  | { code: "catalog_signature" }
  | { code: "catalog_invalid"; reason: string }
  | { code: "catalog_outdated" }
  | { code: "catalog_missing" }
  | { code: "catalog_key_missing" }
  | { code: "unknown_tool" }
  | { code: "not_for_platform" }
  | { code: "needs_newer_app"; min_app_version: string }
  | { code: "needs_newer_os"; min_os: string }
  | { code: "not_installed" }
  | { code: "busy" }
  | { code: "checksum_mismatch" }
  | { code: "unsafe_archive"; reason: string }
  | { code: "archive_read" }
  | { code: "manifest_invalid"; reason: string }
  | { code: "code_signature" }
  | { code: "trial_run_failed" }
  | { code: "tool_failed"; exit_code: number | null }
  | { code: "report_invalid" }
  | { code: "invalid_args"; reason: string }
  | { code: "download"; cause: CoreError }
  | { code: "cancelled" }
  | { code: "io"; kind: string }
  | { code: "internal" };

/** Alle feilkoder, i samme rekkefølge som `JvError` i `error.rs`. */
export const JV_ERROR_CODES = [
  "catalog_signature",
  "catalog_invalid",
  "catalog_outdated",
  "catalog_missing",
  "catalog_key_missing",
  "unknown_tool",
  "not_for_platform",
  "needs_newer_app",
  "needs_newer_os",
  "not_installed",
  "busy",
  "checksum_mismatch",
  "unsafe_archive",
  "archive_read",
  "manifest_invalid",
  "code_signature",
  "trial_run_failed",
  "tool_failed",
  "report_invalid",
  "invalid_args",
  "download",
  "cancelled",
  "io",
  "internal",
] as const satisfies readonly JvError["code"][];

// ---- jv_catalog({ fetch }) -> CatalogView
export type ToolStatus = "available" | "needs_newer_app" | "needs_newer_os" | "not_for_platform" | "unknown";
export type CatalogSource = "network" | "cache" | "none";

export interface CatalogEntry {
  id: string;
  name: string;
  version: string;
  target: string;
  url: string;
  bytes: number;
  sha256: string;
  min_app_version: string;
  min_os: string | null;
  notes: string;
}

export interface ToolView {
  id: string;
  status: ToolStatus;
  entry: CatalogEntry | null;
  installed_version: string | null;
  update_available: boolean;
}

export interface CatalogView {
  /** `aarch64-apple-darwin` eller `x86_64-pc-windows-msvc`. */
  target: string;
  source: CatalogSource;
  error: JvError | null;
  tools: ToolView[];
}

// ---- jv_installed() -> InstalledView[]
export interface InstalledView {
  id: string;
  name: string;
  version: string;
  bytes: number;
  license: string;
}

// ---- jv_install({ id }) -> JvJobId      hendelser install-progress / install-done
// ---- jv_remove({ id }) -> void
// ---- jv_cancel({ jobId }) -> void
// ---- jv_run({ id, request }) -> JvJobId  hendelser run-progress / run-done
export interface RunRequest {
  /** `vis`/`vask` (metadata) og `finn`/`sladd` (redact). */
  command?: string;
  inputs: string[];
  out_dir?: string;
  options: Record<string, string | number | boolean>;
}

// ---- jv_read_plan({ path }) -> PlanView       (redact: treffene fra «finn»)
// ---- jv_save_plan({ path, redact }) -> void   (id -> true/false; endrer bare `sladd`)
export interface PlanItem {
  id: string;
  type: string;
  page: number | null;
  excerpt: string;
  placement: string;
  /** Skal sladdes (avkrysset). */
  redact: boolean;
  /** Mulig nummer der sifrene står langt fra hverandre (trolig tabellceller). */
  rejected: boolean;
  reason: string | null;
}

export interface PlanView {
  items: PlanItem[];
}

export type JvOutcome = "completed" | "cancelled" | "failed";
export type InstallPhase = "download" | "install";

export interface InstallProgressEvent {
  job_id: JvJobId;
  id: string;
  phase: InstallPhase;
  downloaded: number;
  total: number;
}

export interface InstallDoneEvent {
  job_id: JvJobId;
  id: string;
  outcome: JvOutcome;
  error: JvError | null;
  version: string | null;
}

export interface RunProgressEvent {
  job_id: JvJobId;
  id: string;
  /** 0 til 1. */
  progress: number;
}

/** Rapporten fra verktøyet (bare ved kode 0). */
export interface JvReport {
  tool?: string;
  version?: string;
  summary?: string;
  warnings?: string[];
  /** Filsti som tekst, eller et objekt med `path`. */
  outputs?: unknown[];
  [key: string]: unknown;
}

export interface RunDoneEvent {
  job_id: JvJobId;
  id: string;
  outcome: JvOutcome;
  error: JvError | null;
  /** Verktøyets egen norske feilmelding ved kode 1. */
  message: string | null;
  report: JvReport | null;
}

export const JV_EVENTS = {
  installProgress: "jv:install-progress",
  installDone: "jv:install-done",
  runProgress: "jv:run-progress",
  runDone: "jv:run-done",
} as const;

/** Kommandonavn (Rust: `command_names.rs`). Kalles som `plugin:jv|<navn>`. */
export const JV_COMMANDS = [
  "jv_catalog",
  "jv_installed",
  "jv_install",
  "jv_remove",
  "jv_run",
  "jv_cancel",
  "jv_read_plan",
  "jv_save_plan",
] as const;
