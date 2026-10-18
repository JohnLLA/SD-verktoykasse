// Køen av filer: tilstander, framdrift og resultater. Ingen Tauri og ingen
// DOM, så alt kan testes. Controller kobler køen til Rust-kommandoene.
//
// Tilstander:  ready -> queued -> starting -> running -> done | cancelled | failed
//  - ready:     lagt til, ikke startet. Bruker gjeldende valg når Start trykkes.
//  - queued:    startet av brukeren, venter på tur (én jobb om gangen).
//  - starting:  `transcribe` er kalt, jobb-ID kommer straks.
//  - running:   hendelser (framdrift og segmenter) kommer.
// Filer med format vi vet ikke støttes, legges rett inn som failed.

import type {
  CoreError,
  Decoding,
  DoneEvent,
  JobId,
  ProgressEvent,
  Segment,
  SegmentEvent,
} from "../tools/transkribering/api";
import type { Choices } from "./choices";
import { fileExtension, fileName, isSupportedExtension } from "./files";
import { clampPercent } from "./format";
import { PendingEvents } from "./pending";

export type ItemState = "ready" | "queued" | "starting" | "running" | "done" | "cancelled" | "failed";

export interface QueueItem {
  /** Lokal ID, bare for grensesnittet. */
  readonly id: number;
  readonly path: string;
  /** Filnavnet, bare til visning. */
  readonly name: string;
  state: ItemState;
  /** Valgene filen ble startet med. `null` så lenge den er `ready`. */
  choices: Choices | null;
  decoding: Decoding;
  jobId: JobId | null;
  percent: number;
  etaMs: number | null;
  /** Segmentene så langt, og til slutt de ferdige. Teksten kan rettes. */
  segments: Segment[];
  modelId: string | null;
  durationMs: number;
  error: CoreError | null;
  /** Telles opp for hver rettelse. */
  revision: number;
  /** `revision` ved siste vellykkede lagring, eller `null` hvis aldri lagret. */
  savedRevision: number | null;
  savedPath: string | null;
  /** Brukeren har trykket Avbryt mens jobb-ID-en ikke var kjent ennå. */
  cancelRequested: boolean;
  /** Avbryt er sendt; venter på svar. */
  cancelling: boolean;
}

export type QueueChange =
  | { type: "items" }
  | { type: "progress"; id: number }
  | { type: "segment"; id: number; index: number }
  | { type: "edit"; id: number };

type Listener = (change: QueueChange) => void;
type JobEvent =
  | { kind: "progress"; ev: ProgressEvent }
  | { kind: "segment"; ev: SegmentEvent }
  | { kind: "done"; ev: DoneEvent };

export interface AddResult {
  added: QueueItem[];
  /** Antall filer som ble hoppet over fordi de allerede ligger klare. */
  duplicates: number;
}

export class JobQueue {
  private list: QueueItem[] = [];
  private nextId = 1;
  private listeners = new Set<Listener>();
  private pending = new PendingEvents<{ job_id: number; ev: JobEvent }>();

  get items(): readonly QueueItem[] {
    return this.list;
  }

  get(id: number): QueueItem | undefined {
    return this.list.find((i) => i.id === id);
  }

  byJob(jobId: JobId): QueueItem | undefined {
    return this.list.find((i) => i.jobId === jobId);
  }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit(change: QueueChange): void {
    for (const l of this.listeners) l(change);
  }

  // ---- legge til og fjerne

  add(paths: readonly string[], decoding: Decoding): AddResult {
    const added: QueueItem[] = [];
    let duplicates = 0;
    for (const path of paths) {
      if (this.list.some((i) => i.state === "ready" && i.path === path)) {
        duplicates++;
        continue;
      }
      const item: QueueItem = {
        id: this.nextId++,
        path,
        name: fileName(path),
        state: "ready",
        choices: null,
        decoding,
        jobId: null,
        percent: 0,
        etaMs: null,
        segments: [],
        modelId: null,
        durationMs: 0,
        error: null,
        revision: 0,
        savedRevision: null,
        savedPath: null,
        cancelRequested: false,
        cancelling: false,
      };
      if (!isSupportedExtension(path)) {
        item.state = "failed";
        item.error = { code: "unsupported_format", format: fileExtension(path) };
      }
      this.list.push(item);
      added.push(item);
    }
    if (added.length > 0) this.emit({ type: "items" });
    return { added, duplicates };
  }

  remove(id: number): boolean {
    const item = this.get(id);
    if (!item || item.state === "starting" || item.state === "running") return false;
    this.list = this.list.filter((i) => i.id !== id);
    this.emit({ type: "items" });
    return true;
  }

  // ---- start og kjøring

  ready(): QueueItem[] {
    return this.list.filter((i) => i.state === "ready");
  }

  /** Setter alle klare filer i kø med valgene som gjelder nå. */
  startReady(choices: Choices, decoding: Decoding): QueueItem[] {
    const started = this.ready();
    for (const item of started) {
      item.state = "queued";
      item.choices = { ...choices };
      item.decoding = decoding;
    }
    if (started.length > 0) this.emit({ type: "items" });
    return started;
  }

  /** Neste fil som skal kjøre, hvis ingen annen kjører. */
  next(): QueueItem | undefined {
    if (this.list.some((i) => i.state === "starting" || i.state === "running")) return undefined;
    return this.list.find((i) => i.state === "queued");
  }

  markStarting(id: number): void {
    const item = this.get(id);
    if (!item || item.state !== "queued") return;
    item.state = "starting";
    item.percent = 0;
    item.etaMs = null;
    item.segments = [];
    item.error = null;
    this.pending.clear();
    this.emit({ type: "items" });
  }

  /**
   * `transcribe` har svart med jobb-ID. Spiller av hendelser som kom før svaret.
   * Returnerer `true` hvis brukeren allerede har bedt om avbrudd, og
   * controller må sende `cancel`.
   */
  attachJob(id: number, jobId: JobId): boolean {
    const item = this.get(id);
    if (!item || item.state !== "starting") return false;
    item.jobId = jobId;
    item.state = "running";
    this.emit({ type: "items" });
    for (const { ev } of this.pending.take(jobId)) this.apply(item, ev);
    return item.cancelRequested && item.state === "running";
  }

  /** `transcribe` ga feil før noen jobb kom i gang. */
  failStart(id: number, error: CoreError): void {
    const item = this.get(id);
    if (!item) return;
    this.pending.clear();
    this.finish(item, error.code === "cancelled" ? "cancelled" : "failed", error.code === "cancelled" ? null : error);
  }

  // ---- hendelser fra Rust

  handleProgress(ev: ProgressEvent): void {
    this.dispatch(ev.job_id, { kind: "progress", ev });
  }

  handleSegment(ev: SegmentEvent): void {
    this.dispatch(ev.job_id, { kind: "segment", ev });
  }

  handleDone(ev: DoneEvent): void {
    this.dispatch(ev.job_id, { kind: "done", ev });
  }

  private dispatch(jobId: JobId, ev: JobEvent): void {
    const item = this.byJob(jobId);
    if (item) {
      this.apply(item, ev);
      return;
    }
    // Jobb-ID-en er ikke kjent ennå: vent på `attachJob`.
    if (this.list.some((i) => i.state === "starting")) this.pending.push({ job_id: jobId, ev });
  }

  private apply(item: QueueItem, e: JobEvent): void {
    if (item.state !== "running") return; // sene hendelser etter avslutning
    switch (e.kind) {
      case "progress":
        item.percent = Math.max(item.percent, clampPercent(e.ev.percent));
        item.etaMs = e.ev.eta_ms;
        this.emit({ type: "progress", id: item.id });
        break;
      case "segment":
        item.segments.push({ start_ms: e.ev.start_ms, end_ms: e.ev.end_ms, text: e.ev.text });
        this.emit({ type: "segment", id: item.id, index: item.segments.length - 1 });
        break;
      case "done": {
        item.modelId = e.ev.model_id;
        item.durationMs = e.ev.duration_ms;
        if (e.ev.outcome === "completed") {
          item.segments = e.ev.segments.map((s) => ({ ...s }));
          item.percent = 100;
          this.finish(item, "done", null);
        } else if (e.ev.outcome === "cancelled") {
          this.finish(item, "cancelled", null);
        } else {
          this.finish(item, "failed", e.ev.error ?? { code: "internal" });
        }
        break;
      }
    }
  }

  private finish(item: QueueItem, state: "done" | "cancelled" | "failed", error: CoreError | null): void {
    item.state = state;
    item.error = error;
    item.cancelling = false;
    item.cancelRequested = false;
    item.etaMs = null;
    if (state !== "done") item.segments = [];
    this.emit({ type: "items" });
  }

  // ---- avbryt og prøv igjen

  /**
   * Brukeren trykker Avbryt. Gir jobb-ID-en som skal sendes til `cancel`, eller
   * `null` hvis det ikke trengs (fila ventet bare i køen, eller ID-en er ikke
   * kjent ennå og avbruddet sendes når den er det).
   */
  requestCancel(id: number): JobId | null {
    const item = this.get(id);
    if (!item) return null;
    if (item.state === "queued" || item.state === "ready") {
      if (item.state === "queued") this.finish(item, "cancelled", null);
      return null;
    }
    if (item.state === "starting") {
      item.cancelRequested = true;
      item.cancelling = true;
      this.emit({ type: "items" });
      return null;
    }
    if (item.state === "running" && item.jobId !== null) {
      item.cancelRequested = true;
      item.cancelling = true;
      this.emit({ type: "items" });
      return item.jobId;
    }
    return null;
  }

  /** Feilet eller avbrutt fil blir klar igjen. */
  retry(id: number): boolean {
    const item = this.get(id);
    if (!item || (item.state !== "failed" && item.state !== "cancelled")) return false;
    item.state = "ready";
    item.jobId = null;
    item.error = null;
    item.percent = 0;
    item.etaMs = null;
    item.segments = [];
    item.cancelRequested = false;
    item.cancelling = false;
    this.emit({ type: "items" });
    return true;
  }

  // ---- rettelser og lagring

  edit(id: number, index: number, text: string): void {
    const item = this.get(id);
    const seg = item?.segments[index];
    if (!item || item.state !== "done" || !seg || seg.text === text) return;
    seg.text = text;
    item.revision++;
    this.emit({ type: "edit", id });
  }

  markSaved(id: number, path: string, revision: number): void {
    const item = this.get(id);
    if (!item) return;
    item.savedRevision = revision;
    item.savedPath = path;
    this.emit({ type: "edit", id });
  }

  // ---- oppsummering

  static isDirty(item: QueueItem): boolean {
    return item.state === "done" && item.segments.length > 0 && item.savedRevision !== item.revision;
  }

  hasRunning(): boolean {
    return this.list.some((i) => i.state === "starting" || i.state === "running" || i.state === "queued");
  }

  hasUnsaved(): boolean {
    return this.list.some((i) => JobQueue.isDirty(i));
  }
}
