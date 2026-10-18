// Typer for Rust-kommandoene og -hendelsene i Transkribering (steg 1).
// Kilde: src-tauri/src/tools/transkribering/commands.rs. Bare typer og
// konstanter her; selve kallene ligger i backend.ts.
// `api.test.ts` sammenligner med Rust-filene, så de ikke kan komme ut av takt.
//
// Kommandoene kalles som `invoke("plugin:transkribering|<navn>", args)`.
// Merk: argumentnavn på toppnivå skrives i camelCase fra JS (Tauri gjør dem
// om), f.eks. `{ modelId }`, `{ jobId }`, `{ audioPath, malform, stil, format }`.
// Feltene inne i objektene (request, hendelser) er snake_case som her.

export type Malform = "bokmål" | "nynorsk";
export type Stil = "lydrett" | "tolket";
export type Kvalitet = "rask" | "anbefalt" | "best";
export type Decoding = "beam5" | "greedy";
export type ExportFormat = "txt" | "srt" | "vtt" | "docx";
export type JobId = number;

export interface Segment {
  start_ms: number;
  end_ms: number;
  text: string;
}

/** Feil fra Rust. `code` slås opp i språkfilen; ingen feil har filnavn eller tekst. */
export type CoreError =
  | { code: "file_not_found" }
  | { code: "unsupported_format"; format: string }
  | { code: "no_audio_track" }
  | { code: "empty_audio" }
  | { code: "decode_failed" }
  | { code: "unknown_model" }
  | { code: "model_missing"; model_id: string }
  | { code: "model_load_failed" }
  | { code: "model_in_shared_folder" }
  | { code: "invalid_catalog"; reason: string }
  | { code: "host_not_allowed"; host: string }
  | { code: "http_status"; status: number }
  | { code: "network" }
  | { code: "checksum_mismatch" }
  | { code: "size_mismatch" }
  | { code: "disk_full" }
  | { code: "cpu_unsupported"; missing: string[] }
  | { code: "busy" }
  | { code: "already_downloading" }
  | { code: "cancelled" }
  | { code: "whisper"; whisper_code: number }
  | { code: "file_exists" }
  | { code: "not_a_directory" }
  | { code: "invalid_path" }
  | { code: "permission_denied" }
  | { code: "io"; kind: string }
  | { code: "internal" };

/** Alle feilkoder, i samme rekkefølge som i `error.rs`. Språkfilen må ha en tekst for hver. */
export const ERROR_CODES = [
  "file_not_found",
  "unsupported_format",
  "no_audio_track",
  "empty_audio",
  "decode_failed",
  "unknown_model",
  "model_missing",
  "model_load_failed",
  "model_in_shared_folder",
  "invalid_catalog",
  "host_not_allowed",
  "http_status",
  "network",
  "checksum_mismatch",
  "size_mismatch",
  "disk_full",
  "cpu_unsupported",
  "busy",
  "already_downloading",
  "cancelled",
  "whisper",
  "file_exists",
  "not_a_directory",
  "invalid_path",
  "permission_denied",
  "io",
  "internal",
] as const satisfies readonly CoreError["code"][];

export type ErrorCode = CoreError["code"];

// ---- check_system() -> SystemInfo
export interface SystemInfo {
  cpu_supported: boolean;
  missing_cpu_features: string[];
  physical_cores: number;
  whisper_threads: number;
  total_memory_bytes: number | null;
  accelerator: "metal" | "cpu";
}

// ---- list_models() -> ModelList
export interface ModelStatus {
  id: string;
  variant: "verbatim" | "semantic" | "main";
  size: "small" | "medium" | "large";
  quant: string;
  repo: string;
  bytes: number;
  installed: boolean;
  location: "app" | "custom" | null;
  partial_bytes: number;
}

export interface Choice {
  stil: Stil;
  kvalitet: Kvalitet;
  model_id: string;
}

export interface ModelList {
  models: ModelStatus[];
  choices: Choice[];
  app_model_dir: string;
  custom_model_dir: string | null;
  license: string;
  license_holder: string;
}

// ---- download_model({ modelId }) -> JobId
// ---- delete_model({ modelId }) -> void
// ---- set_model_dir({ path: string | null }) -> void
// ---- cancel({ jobId }) -> void   Transkribering: `done` (cancelled) kommer med en gang,
//      og en ny jobb kan startes; whisper kan regne noen sekunder til i bakgrunnen.
//      Nedlasting: `download-done` kommer når nedlastingen har stoppet.

// ---- transcribe({ request }) -> JobId
export interface TranscribeRequest {
  audio_path: string;
  malform: Malform;
  stil: Stil;
  kvalitet: Kvalitet;
  decoding?: Decoding; // standard "beam5"
}

// ---- suggest_export_path({ audioPath, malform, stil, format }) -> string
// ---- export({ request }) -> string (stien som ble skrevet)
export interface HeaderLabels {
  file: string;
  date: string;
  malform: string;
  stil: string;
  model: string;
  bokmal: string;
  nynorsk: string;
  lydrett: string;
  tolket: string;
  notice: string;
}

export interface ExportRequest {
  audio_path: string;
  /** Utelatt: `<lydfil>.<målform>.<stil>.<ending>` ved siden av lydfilen. */
  target_path?: string | null;
  format: ExportFormat;
  /** Tidskoder i txt og docx. */
  timestamps?: boolean;
  /** Bare true etter at brukeren har bekreftet. Ellers gir finnes-fra-før `file_exists`. */
  overwrite?: boolean;
  segments: Segment[];
  malform: Malform;
  stil: Stil;
  model_id: string;
  /** Lokal dato slik den skal stå i toppteksten. */
  date: string;
  labels: HeaderLabels;
}

// ---- Hendelser (listen("transkribering:<navn>", ...))
export const EVENTS = {
  progress: "transkribering:progress",
  segment: "transkribering:segment",
  done: "transkribering:done",
  downloadProgress: "transkribering:download-progress",
  downloadDone: "transkribering:download-done",
} as const;

export type Outcome = "completed" | "cancelled" | "failed";

export interface ProgressEvent {
  job_id: JobId;
  /** 0–100, aldri bakover. */
  percent: number;
  /** Anslått gjenværende tid; null de første sekundene. */
  eta_ms: number | null;
}

export interface SegmentEvent extends Segment {
  job_id: JobId;
}

export interface DoneEvent {
  job_id: JobId;
  outcome: Outcome;
  error: CoreError | null;
  model_id: string;
  duration_ms: number;
  segments: Segment[];
}

export interface DownloadProgressEvent {
  job_id: JobId;
  model_id: string;
  downloaded: number;
  total: number;
}

export interface DownloadDoneEvent {
  job_id: JobId;
  model_id: string;
  outcome: Outcome;
  error: CoreError | null;
}

/** Innstillingsfil og nøkkel (store-plugin) som Rust leser egen modellmappe fra. */
export const SETTINGS_FILE = "settings.json";
export const MODEL_DIR_KEY = "transkribering.modelDir";

/** Kommandonavn (Rust: `command_names.rs`). Kalles som `plugin:transkribering|<navn>`. */
export const COMMANDS = [
  "check_system",
  "list_models",
  "download_model",
  "delete_model",
  "set_model_dir",
  "transcribe",
  "cancel",
  "suggest_export_path",
  "export",
] as const;
