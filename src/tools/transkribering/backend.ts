// Kallene til Rust-kjernen (`transkriberingsbygger`, steg 1). Dette er det
// eneste stedet som kaller `invoke("plugin:transkribering|…")`. Grensesnittet
// `Backend` gjør at controller kan testes med en falsk kjerne.
//
// Feil fra Rust kommer som `CoreError`-objekter. Alt annet blir `internal`
// (så ingen rå feilmelding, sti eller filnavn når brukeren).

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import {
  EVENTS,
  type DoneEvent,
  type DownloadDoneEvent,
  type DownloadProgressEvent,
  type ExportFormat,
  type ExportRequest,
  type JobId,
  type Malform,
  type ModelList,
  type ProgressEvent,
  type SegmentEvent,
  type Stil,
  type SystemInfo,
  type TranscribeRequest,
} from "./api";
import { toCoreError } from "../../lib/errors";

export interface BackendEvents {
  progress(ev: ProgressEvent): void;
  segment(ev: SegmentEvent): void;
  done(ev: DoneEvent): void;
  downloadProgress(ev: DownloadProgressEvent): void;
  downloadDone(ev: DownloadDoneEvent): void;
}

export interface Backend {
  checkSystem(): Promise<SystemInfo>;
  listModels(): Promise<ModelList>;
  downloadModel(modelId: string): Promise<JobId>;
  deleteModel(modelId: string): Promise<void>;
  setModelDir(path: string | null): Promise<void>;
  transcribe(request: TranscribeRequest): Promise<JobId>;
  cancel(jobId: JobId): Promise<void>;
  suggestExportPath(audioPath: string, malform: Malform, stil: Stil, format: ExportFormat): Promise<string>;
  exportFile(request: ExportRequest): Promise<string>;
  /** Begynner å lytte. Returnerer en funksjon som slutter. */
  listen(handlers: BackendEvents): Promise<() => void>;
}

const call = async <T>(command: string, args?: Record<string, unknown>): Promise<T> => {
  try {
    return await invoke<T>(`plugin:transkribering|${command}`, args);
  } catch (e) {
    throw toCoreError(e);
  }
};

export const tauriBackend: Backend = {
  checkSystem: () => call("check_system"),
  listModels: () => call("list_models"),
  downloadModel: (modelId) => call("download_model", { modelId }),
  deleteModel: (modelId) => call("delete_model", { modelId }),
  setModelDir: (path) => call("set_model_dir", { path }),
  transcribe: (request) => call("transcribe", { request }),
  cancel: (jobId) => call("cancel", { jobId }),
  suggestExportPath: (audioPath, malform, stil, format) =>
    call("suggest_export_path", { audioPath, malform, stil, format }),
  exportFile: (request) => call("export", { request }),

  async listen(h) {
    const offs: UnlistenFn[] = await Promise.all([
      listen<ProgressEvent>(EVENTS.progress, (e) => h.progress(e.payload)),
      listen<SegmentEvent>(EVENTS.segment, (e) => h.segment(e.payload)),
      listen<DoneEvent>(EVENTS.done, (e) => h.done(e.payload)),
      listen<DownloadProgressEvent>(EVENTS.downloadProgress, (e) => h.downloadProgress(e.payload)),
      listen<DownloadDoneEvent>(EVENTS.downloadDone, (e) => h.downloadDone(e.payload)),
    ]);
    return () => offs.forEach((off) => off());
  },
};

let override: Backend | null = null;

/** Brukes av prøvevisningen i `src/dev` til å bytte ut kjernen. */
export function setBackend(b: Backend | null): void {
  override = b;
}

export function getBackend(): Backend {
  return override ?? tauriBackend;
}
