// Logikken i Transkribering-skjermen, uten DOM. Kobler køen (`lib/queue.ts`)
// til Rust-kommandoene (`backend.ts`) og maskinen rundt (`platform`). Visningene
// (`view.ts`, `settings.ts`) lytter på endringer og tegner. Testes med en falsk
// kjerne i `controller.test.ts`.
//
// Ingen filnavn eller tekst skrives til konsollen (regel 2).

import type {
  CoreError,
  Decoding,
  ModelList,
  ModelStatus,
  SystemInfo,
} from "./api";
import type { Backend } from "./backend";
import { DEFAULT_CHOICES, DEFAULT_DECODING, modelFor, type Choices } from "../../lib/choices";
import { DownloadTracker, type DownloadState } from "../../lib/download";
import { toCoreError } from "../../lib/errors";
import { buildExportRequest, saveOption, type SaveKind } from "../../lib/export-request";
import { JobQueue, type QueueChange, type QueueItem } from "../../lib/queue";
import { DIALOG_EXTENSIONS } from "../../lib/files";
import { normalizeEditedText, plainText } from "../../lib/segments";
import { loadChoices, loadDecoding, saveChoices, KEYS } from "../../lib/settings";
import { t } from "../../i18n/nb";
import type { Platform } from "../../platform/types";

export type Screen = { kind: "new" } | { kind: "file"; id: number };

export type ControllerChange =
  | QueueChange
  | { type: "choices" }
  | { type: "models" }
  | { type: "download" }
  | { type: "screen" }
  | { type: "system" }
  | { type: "decoding" };

export interface ControllerDeps {
  backend: Backend;
  platform: Platform;
  /** Kort beskjed til skjermlesere (aria-live). */
  announce: (message: string) => void;
  now?: () => Date;
}

export type SaveResult =
  | { status: "saved"; path: string }
  /** Filen finnes. Bekreft med brukeren og kall på nytt med `overwrite`. */
  | { status: "exists"; name: string }
  | { status: "cancelled" }
  | { status: "failed"; error: CoreError };

/** Hva den neste filen trenger av modell, når den starter. */
export interface ModelNeed {
  model: ModelStatus;
  installed: boolean;
  partialBytes: number;
}

export class TranskriberingController {
  readonly queue = new JobQueue();
  readonly downloads = new DownloadTracker();

  choices: Choices = { ...DEFAULT_CHOICES };
  decoding: Decoding = DEFAULT_DECODING;
  models: ModelList | null = null;
  modelsError: CoreError | null = null;
  system: SystemInfo | null = null;
  screen: Screen = { kind: "new" };
  /** Hvilken fil som sist ble lagt til, så visningen kan gi beskjed om dobbeltlagte. */
  lastAdd: { added: number; duplicates: number } | null = null;

  private listeners = new Set<(c: ControllerChange) => void>();
  private unlisten: (() => void) | null = null;
  /** Brukeren har trykket «Last ned» for å komme i gang; start når modellen er der. */
  private startAfterDownload = false;
  private readonly now: () => Date;

  constructor(private readonly deps: ControllerDeps) {
    this.now = deps.now ?? (() => new Date());
    this.queue.subscribe((c) => this.emit(c));
  }

  // ---- oppstart

  async init(): Promise<void> {
    const { backend, platform } = this.deps;
    this.unlisten = await backend.listen({
      progress: (ev) => this.queue.handleProgress(ev),
      segment: (ev) => this.queue.handleSegment(ev),
      done: (ev) => {
        this.queue.handleDone(ev);
        void this.pump();
      },
      downloadProgress: (ev) => {
        this.downloads.progress(ev);
        this.emit({ type: "download" });
      },
      downloadDone: (ev) => void this.onDownloadDone(ev),
    });
    const [choices, decoding, system] = await Promise.all([
      loadChoices(platform.settings),
      loadDecoding(platform.settings),
      backend.checkSystem().catch(() => null),
      this.refreshModels(),
    ]);
    this.choices = choices;
    this.decoding = decoding;
    this.system = system;
    this.emit({ type: "choices" });
    this.emit({ type: "decoding" });
    this.emit({ type: "system" });
  }

  dispose(): void {
    this.unlisten?.();
    this.unlisten = null;
  }

  subscribe(fn: (c: ControllerChange) => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit(c: ControllerChange): void {
    for (const l of this.listeners) l(c);
  }

  // ---- avledet tilstand

  get cpuSupported(): boolean {
    return this.system?.cpu_supported ?? true;
  }

  get totalMemoryBytes(): number | null {
    return this.system?.total_memory_bytes ?? null;
  }

  /** Modellen valgene peker på, når det finnes filer som venter på å starte. */
  modelNeed(choices: Choices = this.choices): ModelNeed | null {
    if (!this.models) return null;
    const model = modelFor(this.models, choices.stil, choices.kvalitet);
    if (!model) return null;
    return { model, installed: model.installed, partialBytes: model.partial_bytes };
  }

  get download(): DownloadState | null {
    return this.downloads.state;
  }

  /** `running` hvis noe pågår, `unsaved` hvis det er tekst som ikke er lagret, ellers `null`. */
  busy(): "running" | "unsaved" | null {
    if (this.queue.hasRunning()) return "running";
    if (this.queue.hasUnsaved()) return "unsaved";
    return null;
  }

  // ---- valg

  async setChoice<K extends keyof Choices>(key: K, value: Choices[K]): Promise<void> {
    if (this.choices[key] === value) return;
    this.choices = { ...this.choices, [key]: value };
    this.emit({ type: "choices" });
    await saveChoices(this.deps.platform.settings, this.choices).catch(() => undefined);
  }

  async setDecoding(d: Decoding): Promise<void> {
    this.decoding = d;
    this.emit({ type: "decoding" });
    await this.deps.platform.settings.set(KEYS.decoding, d);
  }

  // ---- filer

  addFiles(paths: readonly string[]): void {
    if (paths.length === 0) return;
    const r = this.queue.add(paths, this.decoding);
    this.lastAdd = { added: r.added.length, duplicates: r.duplicates };
    this.screen = { kind: "new" };
    this.emit({ type: "screen" });
    const ok = r.added.filter((i) => i.state === "ready").length;
    if (ok > 0) this.deps.announce(t.transkribering.drop.added(ok));
    else if (r.duplicates > 0) this.deps.announce(t.transkribering.drop.duplicates);
  }

  async chooseFiles(): Promise<void> {
    const paths = await this.deps.platform.pickFiles({
      title: t.transkribering.drop.dialogTitle,
      filterName: t.transkribering.drop.filterName,
      extensions: DIALOG_EXTENSIONS,
    });
    this.addFiles(paths);
  }

  removeItem(id: number): void {
    if (this.queue.remove(id) && this.screen.kind === "file" && this.screen.id === id) {
      this.showNew();
    }
  }

  // ---- visning

  openFile(id: number): void {
    if (!this.queue.get(id)) return;
    this.screen = { kind: "file", id };
    this.emit({ type: "screen" });
  }

  showNew(): void {
    this.screen = { kind: "new" };
    this.emit({ type: "screen" });
  }

  // ---- start og kjøring

  /** Starter alle klare filer med valgene som gjelder nå. */
  start(): void {
    if (!this.cpuSupported) return;
    if (this.queue.ready().length === 0) return;
    const need = this.modelNeed();
    if (!need || !need.installed) return; // visningen viser «Last ned» i stedet for Start
    this.startAfterDownload = false;
    const started = this.queue.startReady(this.choices, this.decoding);
    const first = started[0];
    if (started.length === 1 && first) this.openFile(first.id);
    void this.pump();
  }

  private pumping = false;

  /** Starter neste fil i køen hvis ingen kjører. */
  async pump(): Promise<void> {
    if (this.pumping) return;
    this.pumping = true;
    try {
      for (let item = this.queue.next(); item; item = this.queue.next()) {
        await this.run(item);
      }
    } finally {
      this.pumping = false;
    }
  }

  private async run(item: QueueItem): Promise<void> {
    const c = item.choices ?? this.choices;
    this.queue.markStarting(item.id);
    try {
      const jobId = await this.deps.backend.transcribe({
        audio_path: item.path,
        malform: c.malform,
        stil: c.stil,
        kvalitet: c.kvalitet,
        decoding: item.decoding,
      });
      if (this.queue.attachJob(item.id, jobId)) {
        await this.deps.backend.cancel(jobId).catch(() => undefined);
      }
    } catch (e) {
      this.queue.failStart(item.id, toCoreError(e));
    }
  }

  cancelItem(id: number): void {
    const jobId = this.queue.requestCancel(id);
    if (jobId !== null) void this.deps.backend.cancel(jobId).catch(() => undefined);
  }

  /** Feilet eller avbrutt fil gjøres klar igjen og startes med valgene som gjelder nå. */
  retry(id: number): void {
    if (!this.queue.retry(id)) return;
    this.showNew();
    this.start();
  }

  // ---- modeller

  async refreshModels(): Promise<void> {
    try {
      this.models = await this.deps.backend.listModels();
      this.modelsError = null;
    } catch (e) {
      this.modelsError = toCoreError(e);
    }
    this.emit({ type: "models" });
  }

  async downloadModel(): Promise<void> {
    const need = this.modelNeed();
    if (!need || need.installed || this.downloads.active) return;
    this.startAfterDownload = this.queue.ready().length > 0;
    this.downloads.begin(need.model.id, need.partialBytes);
    this.emit({ type: "download" });
    try {
      const jobId = await this.deps.backend.downloadModel(need.model.id);
      if (this.downloads.attach(jobId)) {
        await this.deps.backend.cancel(jobId).catch(() => undefined);
      }
    } catch (e) {
      this.downloads.fail(toCoreError(e));
    }
    this.emit({ type: "download" });
    // Hendelsene kan ha kommet før jobb-ID-en: nedlastingen kan allerede være ferdig.
    await this.finishDownloadIfDone();
  }

  cancelDownload(): void {
    const jobId = this.downloads.requestCancel();
    this.startAfterDownload = false;
    if (jobId !== null) void this.deps.backend.cancel(jobId).catch(() => undefined);
    this.emit({ type: "download" });
  }

  dismissDownload(): void {
    if (this.downloads.active) return;
    this.downloads.clear();
    this.emit({ type: "download" });
  }

  private async onDownloadDone(ev: Parameters<DownloadTracker["done"]>[0]): Promise<void> {
    this.downloads.done(ev);
    this.emit({ type: "download" });
    await this.finishDownloadIfDone();
  }

  private finishing = false;

  private async finishDownloadIfDone(): Promise<void> {
    if (this.finishing || this.downloads.state?.status !== "done") return;
    this.finishing = true;
    try {
      const finished = this.downloads.state.modelId;
      await this.refreshModels();
      this.downloads.clear();
      this.emit({ type: "download" });
      const start = this.startAfterDownload && this.modelNeed()?.model.id === finished;
      this.startAfterDownload = false;
      if (start) this.start();
    } finally {
      this.finishing = false;
    }
  }

  async deleteModel(modelId: string): Promise<CoreError | null> {
    try {
      await this.deps.backend.deleteModel(modelId);
      await this.refreshModels();
      return null;
    } catch (e) {
      await this.refreshModels();
      return toCoreError(e);
    }
  }

  async setModelDir(path: string | null): Promise<CoreError | null> {
    try {
      await this.deps.backend.setModelDir(path);
      await this.refreshModels();
      return null;
    } catch (e) {
      return toCoreError(e);
    }
  }

  async chooseModelDir(): Promise<CoreError | null | "cancelled"> {
    const path = await this.deps.platform.pickFolder(t.settings.folder.dialogTitle);
    if (!path) return "cancelled";
    return this.setModelDir(path);
  }

  // ---- resultat

  edit(id: number, index: number, raw: string): void {
    this.queue.edit(id, index, normalizeEditedText(raw));
  }

  async copyAll(id: number): Promise<boolean> {
    const item = this.queue.get(id);
    if (!item || item.state !== "done") return false;
    return this.deps.platform.copyText(plainText(item.segments));
  }

  async reveal(id: number): Promise<void> {
    const item = this.queue.get(id);
    if (!item) return;
    try {
      await this.deps.platform.reveal(item.savedPath ?? item.path);
    } catch {
      // Finder/Utforsker kunne ikke åpnes. Ingenting å gjøre for brukeren.
    }
  }

  async save(
    id: number,
    kind: SaveKind,
    opts: { chooseLocation?: boolean; overwrite?: boolean } = {},
  ): Promise<SaveResult> {
    const item = this.queue.get(id);
    if (!item || item.state !== "done" || !item.choices || !item.modelId) {
      return { status: "failed", error: { code: "internal" } };
    }
    const option = saveOption(kind);
    const { backend, platform } = this.deps;
    const revision = item.revision;
    let target: string | null = null;
    let overwrite = opts.overwrite ?? false;
    try {
      const suggested = await backend.suggestExportPath(
        item.path,
        item.choices.malform,
        item.choices.stil,
        option.format,
      );
      if (opts.chooseLocation) {
        target = await platform.pickSavePath({
          title: t.transkribering.save.dialogTitle,
          defaultPath: suggested,
          extension: option.format,
          filterName: t.transkribering.save.formats[kind].label,
        });
        if (!target) return { status: "cancelled" };
        overwrite = true; // operativsystemet har allerede spurt om overskriving
      }
      const path = await backend.exportFile(
        buildExportRequest({
          audioPath: item.path,
          option,
          segments: item.segments,
          malform: item.choices.malform,
          stil: item.choices.stil,
          modelId: item.modelId,
          now: this.now(),
          targetPath: target,
          overwrite,
        }),
      );
      this.queue.markSaved(item.id, path, revision);
      return { status: "saved", path };
    } catch (e) {
      const error = toCoreError(e);
      if (error.code === "file_exists") {
        const name = (await backend
          .suggestExportPath(item.path, item.choices.malform, item.choices.stil, option.format)
          .catch(() => "")) as string;
        return { status: "exists", name: name.split(/[\\/]/).pop() ?? name };
      }
      return { status: "failed", error };
    }
  }
}
