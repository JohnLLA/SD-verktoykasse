// Falsk kjerne og maskin til tester av controller. Ingen Tauri.

import type { Backend, BackendEvents } from "./backend";
import type {
  CoreError,
  ExportRequest,
  JobId,
  ModelList,
  ModelStatus,
  SystemInfo,
  TranscribeRequest,
} from "./api";
import { MemorySettings } from "../../lib/settings";
import type { Platform } from "../../platform/types";

export function model(
  id: string,
  size: ModelStatus["size"],
  variant: ModelStatus["variant"],
  over: Partial<ModelStatus> = {},
): ModelStatus {
  return {
    id,
    variant,
    size,
    quant: "q5_0",
    repo: variant === "main" ? `NbAiLab/nb-whisper-${size}` : `NbAiLab/nb-whisper-${size}-${variant}`,
    bytes: size === "small" ? 175_209_680 : size === "medium" ? 539_212_484 : 1_081_140_203,
    installed: false,
    location: null,
    partial_bytes: 0,
    ...over,
  };
}

export function modelList(installedIds: string[] = [], over: Partial<ModelList> = {}): ModelList {
  const models = [
    model("small-verbatim", "small", "verbatim"),
    model("medium-verbatim", "medium", "verbatim"),
    model("large-verbatim", "large", "verbatim"),
    model("small-main", "small", "main"),
    model("medium-main", "medium", "main"),
    model("large-main", "large", "main"),
  ].map((m) => (installedIds.includes(m.id) ? { ...m, installed: true, location: "app" as const } : m));
  const choices = (["rask", "anbefalt", "best"] as const).flatMap((kvalitet, i) =>
    (["lydrett", "tolket"] as const).map((stil) => ({
      stil,
      kvalitet,
      model_id: `${(["small", "medium", "large"] as const)[i]}-${stil === "lydrett" ? "verbatim" : "main"}`,
    })),
  );
  return {
    models,
    choices,
    app_model_dir: "/data/modeller",
    custom_model_dir: null,
    license: "Apache-2.0",
    license_holder: "Nasjonalbiblioteket",
    ...over,
  };
}

export const OK_SYSTEM: SystemInfo = {
  cpu_supported: true,
  missing_cpu_features: [],
  physical_cores: 8,
  whisper_threads: 6,
  total_memory_bytes: 16 * 2 ** 30,
  accelerator: "metal",
};

export class FakeBackend implements Backend {
  models: ModelList = modelList(["medium-main", "small-verbatim"]);
  system: SystemInfo = OK_SYSTEM;
  handlers: BackendEvents | null = null;
  nextJob = 1;
  transcribeCalls: TranscribeRequest[] = [];
  exportCalls: ExportRequest[] = [];
  cancelled: JobId[] = [];
  downloads: string[] = [];
  deleted: string[] = [];
  modelDir: string | null | undefined = undefined;
  transcribeError: CoreError | null = null;
  exportError: CoreError | null = null;
  /** Sti som `suggest_export_path` svarer med. */
  suggested = (audio: string, malform: string, stil: string, format: string) =>
    `${audio.replace(/\.[^.]+$/, "")}.${malform === "bokmål" ? "bokmal" : malform}.${stil}.${format}`;
  /** Hendelser som sendes mens `transcribe` ennå ikke har svart (kappløp). */
  duringTranscribe: ((jobId: JobId, h: BackendEvents) => void) | null = null;

  async checkSystem() {
    return this.system;
  }
  async listModels() {
    return structuredClone(this.models);
  }
  async downloadModel(modelId: string) {
    this.downloads.push(modelId);
    return this.nextJob++;
  }
  async deleteModel(modelId: string) {
    this.deleted.push(modelId);
  }
  async setModelDir(path: string | null) {
    this.modelDir = path;
  }
  async transcribe(request: TranscribeRequest) {
    this.transcribeCalls.push(request);
    if (this.transcribeError) throw this.transcribeError;
    const id = this.nextJob++;
    if (this.duringTranscribe && this.handlers) this.duringTranscribe(id, this.handlers);
    return id;
  }
  async cancel(jobId: JobId) {
    this.cancelled.push(jobId);
  }
  async suggestExportPath(audio: string, malform: string, stil: string, format: string) {
    return this.suggested(audio, malform, stil, format);
  }
  async exportFile(request: ExportRequest) {
    this.exportCalls.push(request);
    if (this.exportError) throw this.exportError;
    return request.target_path ?? this.suggested(request.audio_path, request.malform, request.stil, request.format);
  }
  async listen(handlers: BackendEvents) {
    this.handlers = handlers;
    return () => {
      this.handlers = null;
    };
  }

  /** Markerer en modell som nedlastet, som om nedlastingen var ferdig. */
  install(id: string) {
    this.models = {
      ...this.models,
      models: this.models.models.map((m) => (m.id === id ? { ...m, installed: true, location: "app" } : m)),
    };
  }
}

export interface FakePlatform extends Platform {
  announced: string[];
  copied: string[];
  revealed: string[];
  /** `save`: undefined = brukeren godtar forslaget, null = lukker dialogen, tekst = valgt sti. */
  picked: { files: string[]; folder: string | null; save: string | null | undefined };
  savePathRequests: string[];
}

export function fakePlatform(): FakePlatform {
  const p: FakePlatform = {
    os: "mac",
    settings: new MemorySettings(),
    announced: [],
    copied: [],
    revealed: [],
    savePathRequests: [],
    picked: { files: [], folder: null, save: undefined },
    async pickFiles() {
      return p.picked.files;
    },
    async pickFolder() {
      return p.picked.folder;
    },
    async pickSavePath(opts) {
      p.savePathRequests.push(opts.defaultPath);
      return p.picked.save === undefined ? opts.defaultPath : p.picked.save;
    },
    async onDrop() {
      return () => undefined;
    },
    async playbackUrl() {
      return null;
    },
    async reveal(path) {
      p.revealed.push(path);
    },
    async copyText(text) {
      p.copied.push(text);
      return true;
    },
    async appVersion() {
      return "0.1.0";
    },
    async checkForUpdate() {
      return null;
    },
    async checkForUpdateNow() {
      return { status: "none" } as const;
    },
    async installUpdate() {
      return false;
    },
    async onCloseRequested() {
      return () => undefined;
    },
  };
  return p;
}
