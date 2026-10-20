// Tilstanden og handlingene for journalistverktøyene: katalog, nedlasting,
// filer, valg, kjøring, resultat og de to stegene i sladding. Ingen DOM og
// ingen Tauri (bare `JvBackend` og `Platform`), så alt kan testes med en falsk
// kjerne. Én controller deles av alle ni verktøyene.
//
// Rust tillater én jobb per verktøy (nedlasting, kjøring eller fjerning).
// Hendelsene kobles derfor til verktøyet (`id`), og jobb-ID-en brukes til å
// ignorere hendelser fra en eldre jobb.

import { t } from "../../i18n/nb";
import { fileName } from "../../lib/files";
import type { Platform } from "../../platform/types";
import {
  isJvToolId,
  type CatalogView,
  type InstallDoneEvent,
  type InstallProgressEvent,
  type InstalledView,
  type JvError,
  type JvJobId,
  type JvReport,
  type JvToolId,
  type PlanItem,
  type RunDoneEvent,
  type RunProgressEvent,
  type RunRequest,
  type ToolView,
} from "./api";
import { toJvError, type JvBackend } from "./backend";
import { installScreen, menuStatus, type InstallScreen, type MenuStatus } from "./menu";
import { defaultOutDir, findSummary, outputPath, partitionFiles } from "./paths";
import {
  buildRunRequest,
  defaultValues,
  needsOutDir,
  valuesValid,
  type OptionValue,
  type ToolSchema,
  type Values,
} from "./schema";

export type InstallStatus = "idle" | "starting" | "downloading" | "installing" | "failed" | "cancelled" | "done";

export interface InstallState {
  status: InstallStatus;
  jobId: JvJobId | null;
  /** Siste jobb-ID vi har sett, så hendelser fra en eldre jobb ignoreres. */
  lastJobId: number;
  downloaded: number;
  total: number;
  error: JvError | null;
  cancelRequested: boolean;
}

export type RunStatus = "idle" | "starting" | "running" | "done" | "failed" | "cancelled";

export interface RunState {
  status: RunStatus;
  /** `find` er steg 1 i sladding; alt annet er `run`. */
  kind: "run" | "find";
  jobId: JvJobId | null;
  lastJobId: number;
  /** 0 til 1. */
  progress: number;
  cancelRequested: boolean;
  error: JvError | null;
  /** Verktøyets egen norske feilmelding (kode 1). */
  message: string | null;
  report: JvReport | null;
}

export type FileNotice = { kind: "unsupported"; names: string[] } | { kind: "count"; n: number } | null;

export interface RedactState {
  step: "find" | "review";
  planPath: string | null;
  items: PlanItem[];
  /** Rapporten fra «Finn», for advarslene. */
  findReport: JvReport | null;
  loading: boolean;
  error: JvError | null;
}

export interface Session {
  files: string[];
  values: Values;
  /** Filer valgt i skjemaet (for eksempel listen med egne ord), per felt. */
  fieldFiles: Record<string, string>;
  outDir: string | null;
  outDirChosen: boolean;
  notice: FileNotice;
  run: RunState;
  redact: RedactState;
}

export type JvChange =
  | { type: "catalog" }
  | { type: "installed" }
  | { type: "install"; id: JvToolId }
  | { type: "install-progress"; id: JvToolId }
  | { type: "session"; id: JvToolId }
  | { type: "run-progress"; id: JvToolId };

export interface JvControllerDeps {
  backend: JvBackend;
  platform: Platform;
  announce(message: string): void;
}

function freshInstall(): InstallState {
  return { status: "idle", jobId: null, lastJobId: 0, downloaded: 0, total: 0, error: null, cancelRequested: false };
}

function freshRun(lastJobId = 0): RunState {
  return {
    status: "idle",
    kind: "run",
    jobId: null,
    lastJobId,
    progress: 0,
    cancelRequested: false,
    error: null,
    message: null,
    report: null,
  };
}

function freshRedact(): RedactState {
  return { step: "find", planPath: null, items: [], findReport: null, loading: false, error: null };
}

const activeInstall = (s: InstallStatus) => s === "starting" || s === "downloading" || s === "installing";
const activeRun = (s: RunStatus) => s === "starting" || s === "running";

export class JvController {
  readonly backend: JvBackend;
  readonly platform: Platform;
  private readonly announce: (m: string) => void;
  private readonly schemas = new Map<JvToolId, ToolSchema>();
  private readonly installs = new Map<JvToolId, InstallState>();
  private readonly sessions = new Map<JvToolId, Session>();
  private listeners = new Set<(c: JvChange) => void>();
  private unlisten: (() => void) | null = null;

  catalog: CatalogView | null = null;
  catalogLoading = false;
  /** Feilen fra siste forsøk på å hente katalogen. */
  catalogError: JvError | null = null;
  /** Katalogen er hentet fra nett i denne økten. */
  private catalogFetched = false;
  installed: InstalledView[] = [];

  constructor(deps: JvControllerDeps) {
    this.backend = deps.backend;
    this.platform = deps.platform;
    this.announce = deps.announce;
  }

  // ------------------------------------------------------------ oppsett

  registerSchema(schema: ToolSchema): void {
    this.schemas.set(schema.id, schema);
  }

  schema(id: JvToolId): ToolSchema {
    const s = this.schemas.get(id);
    if (!s) throw new Error("ukjent verktøy");
    return s;
  }

  subscribe(fn: (c: JvChange) => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit(c: JvChange): void {
    for (const l of this.listeners) l(c);
  }

  private started = false;

  /** Lytter på hendelser og leser det som allerede er kontrollert (ingen nett). */
  async init(): Promise<void> {
    if (this.started) return;
    this.started = true;
    try {
      this.unlisten = await this.backend.listen({
        installProgress: (ev) => this.onInstallProgress(ev),
        installDone: (ev) => this.onInstallDone(ev),
        runProgress: (ev) => this.onRunProgress(ev),
        runDone: (ev) => void this.onRunDone(ev),
      });
    } catch {
      // Uten hendelser får vi ingen framdrift; resten virker.
    }
    await Promise.all([this.refreshInstalled(), this.loadCatalog(false)]);
  }

  destroy(): void {
    this.unlisten?.();
    this.unlisten = null;
    this.started = false;
  }

  // ------------------------------------------------------------ katalog og installerte

  async loadCatalog(fetch: boolean): Promise<void> {
    if (this.catalogLoading) return;
    this.catalogLoading = fetch;
    if (fetch) this.emit({ type: "catalog" });
    try {
      const view = await this.backend.catalog(fetch);
      this.catalog = view;
      this.catalogError = view.error;
      if (fetch && view.source === "network") this.catalogFetched = true;
    } catch (e) {
      this.catalogError = toJvError(e);
    }
    this.catalogLoading = false;
    this.emit({ type: "catalog" });
  }

  async refreshInstalled(): Promise<void> {
    try {
      this.installed = await this.backend.installed();
    } catch {
      this.installed = [];
    }
    this.emit({ type: "installed" });
  }

  /** Brukeren åpner et verktøy: henter katalogen fra nett hvis verktøyet ikke er lastet ned. */
  async open(id: JvToolId): Promise<void> {
    if (!this.isInstalled(id) && !this.catalogFetched) await this.loadCatalog(true);
  }

  isInstalled(id: string): boolean {
    return this.installed.some((i) => i.id === id);
  }

  installedInfo(id: string): InstalledView | undefined {
    return this.installed.find((i) => i.id === id);
  }

  toolView(id: string): ToolView | undefined {
    return this.catalog?.tools.find((t) => t.id === id);
  }

  menuStatus(id: string): MenuStatus {
    return menuStatus(this.isInstalled(id), this.toolView(id));
  }

  installScreen(id: string): InstallScreen {
    return installScreen(this.toolView(id), this.catalogLoading);
  }

  /** Plattformen katalogen gjelder for, til «Kommer for Windows». */
  catalogPlatform(): "mac" | "windows" | "other" {
    const target = this.catalog?.target ?? "";
    if (target.includes("windows")) return "windows";
    if (target.includes("apple")) return "mac";
    return this.platform.os;
  }

  /** «Se etter oppdateringer»: henter katalogen fra nett. Gir antall verktøy med ny versjon. */
  async checkUpdates(): Promise<{ ok: boolean; updates: number }> {
    await this.loadCatalog(true);
    const ok = this.catalog?.source === "network" && this.catalog.error === null;
    const updates = this.catalog?.tools.filter((t) => t.update_available && this.isInstalled(t.id)).length ?? 0;
    return { ok, updates };
  }

  // ------------------------------------------------------------ nedlasting

  installState(id: JvToolId): InstallState {
    let s = this.installs.get(id);
    if (!s) {
      s = freshInstall();
      this.installs.set(id, s);
    }
    return s;
  }

  installActive(id: JvToolId): boolean {
    return activeInstall(this.installState(id).status);
  }

  async install(id: JvToolId): Promise<void> {
    const prev = this.installState(id);
    if (activeInstall(prev.status)) return;
    const total = this.toolView(id)?.entry?.bytes ?? 0;
    const s: InstallState = { ...freshInstall(), lastJobId: prev.lastJobId, status: "starting", total };
    this.installs.set(id, s);
    this.emit({ type: "install", id });
    try {
      const job = await this.backend.install(id);
      if (s.jobId === null) s.jobId = job;
      if (s.status === "starting") s.status = "downloading";
      if (s.cancelRequested) void this.backend.cancel(job).catch(() => undefined);
    } catch (e) {
      s.status = "failed";
      s.error = toJvError(e);
      if (s.error.code === "cancelled") {
        s.status = "cancelled";
        s.error = null;
      }
      if (s.error?.code === "needs_newer_os" || s.error?.code === "needs_newer_app") {
        // Katalogen var gammel; hent siste kopi, så skjermen forklarer det samme.
        void this.loadCatalog(false);
      }
    }
    this.emit({ type: "install", id });
  }

  cancelInstall(id: JvToolId): void {
    const s = this.installState(id);
    if (!activeInstall(s.status)) return;
    s.cancelRequested = true;
    if (s.jobId !== null) void this.backend.cancel(s.jobId).catch(() => undefined);
    this.emit({ type: "install", id });
  }

  private matches(eventJob: number, state: { jobId: number | null; lastJobId: number }): boolean {
    if (state.jobId !== null) return eventJob === state.jobId;
    return eventJob > state.lastJobId;
  }

  onInstallProgress(ev: InstallProgressEvent): void {
    if (!isJvToolId(ev.id)) return;
    const s = this.installState(ev.id);
    if (!activeInstall(s.status) || !this.matches(ev.job_id, s)) return;
    s.jobId = ev.job_id;
    s.lastJobId = ev.job_id;
    if (s.status === "starting") s.status = "downloading";
    if (ev.phase === "install") s.status = "installing";
    else {
      s.downloaded = ev.downloaded;
      if (ev.total > 0) s.total = ev.total;
    }
    this.emit({ type: "install-progress", id: ev.id });
  }

  onInstallDone(ev: InstallDoneEvent): void {
    if (!isJvToolId(ev.id)) return;
    const s = this.installState(ev.id);
    if (!activeInstall(s.status) || !this.matches(ev.job_id, s)) return;
    s.jobId = null;
    s.lastJobId = ev.job_id;
    if (ev.outcome === "completed") {
      s.status = "done";
      s.error = null;
      this.announce(t.jv.install.downloaded(this.toolName(ev.id)));
      void this.refreshInstalled();
      void this.loadCatalog(false);
    } else if (ev.outcome === "cancelled") {
      s.status = "cancelled";
      s.error = null;
    } else {
      s.status = "failed";
      s.error = ev.error ?? { code: "internal" };
    }
    this.emit({ type: "install", id: ev.id });
  }

  private toolName(id: string): string {
    return this.toolView(id)?.entry?.name ?? this.installedInfo(id)?.name ?? id;
  }

  /** Fjerner et verktøy. Gir feilen hvis det ikke gikk. */
  async remove(id: JvToolId): Promise<JvError | null> {
    if (this.installActive(id) || activeRun(this.session(id).run.status)) return { code: "busy" };
    try {
      await this.backend.remove(id);
    } catch (e) {
      return toJvError(e);
    }
    this.installs.set(id, freshInstall());
    this.sessions.delete(id);
    await Promise.all([this.refreshInstalled(), this.loadCatalog(false)]);
    this.emit({ type: "install", id });
    this.emit({ type: "session", id });
    return null;
  }

  // ------------------------------------------------------------ økt per verktøy

  session(id: JvToolId): Session {
    let s = this.sessions.get(id);
    if (!s) {
      const schema = this.schema(id);
      s = {
        files: [],
        values: defaultValues(schema),
        fieldFiles: {},
        outDir: null,
        outDirChosen: false,
        notice: null,
        run: freshRun(),
        redact: freshRedact(),
      };
      this.sessions.set(id, s);
    }
    return s;
  }

  private changed(id: JvToolId): void {
    this.emit({ type: "session", id });
  }

  /** Legger til filer. Filer som ikke passer, gir en melding (`session.notice`). */
  addFiles(id: JvToolId, paths: readonly string[]): void {
    const schema = this.schema(id);
    const s = this.session(id);
    if (activeRun(s.run.status)) return;
    const { accepted, rejected } = partitionFiles(paths, schema);
    s.notice = null;
    if (rejected.length > 0) s.notice = { kind: "unsupported", names: rejected };
    const unique = accepted.filter((p, i) => accepted.indexOf(p) === i);
    if (unique.length === 0) {
      this.changed(id);
      return;
    }
    const n = schema.exactFiles;
    let next: string[];
    if (n === undefined) {
      next = [...s.files, ...unique.filter((p) => !s.files.includes(p))];
    } else if (unique.length > n) {
      s.notice = { kind: "count", n };
      this.changed(id);
      return;
    } else if (unique.length === n) {
      next = unique;
    } else {
      next = [...s.files, ...unique.filter((p) => !s.files.includes(p))];
      if (next.length > n) next = next.slice(next.length - n);
    }
    this.setFiles(id, next);
  }

  private setFiles(id: JvToolId, files: string[]): void {
    const s = this.session(id);
    s.files = files;
    if (!s.outDirChosen) s.outDir = defaultOutDir(files);
    this.resetResult(id);
    this.changed(id);
  }

  /** Nye filer eller nye valg gjør et gammelt resultat ugyldig. */
  private resetResult(id: JvToolId): void {
    const s = this.session(id);
    if (activeRun(s.run.status)) return;
    s.run = freshRun(s.run.lastJobId);
    s.redact = freshRedact();
  }

  removeFile(id: JvToolId, index: number): void {
    const s = this.session(id);
    if (activeRun(s.run.status)) return;
    s.notice = null;
    this.setFiles(id, s.files.filter((_, i) => i !== index));
  }

  swapFiles(id: JvToolId): void {
    const s = this.session(id);
    if (activeRun(s.run.status) || s.files.length !== 2) return;
    const [a, b] = s.files as [string, string];
    this.setFiles(id, [b, a]);
  }

  setValue(id: JvToolId, fieldId: string, value: OptionValue): void {
    const s = this.session(id);
    if (activeRun(s.run.status)) return;
    s.values = { ...s.values, [fieldId]: value };
    // Et nytt valg gjør ikke et ferdig resultat feil, men «Finn» må gjøres om.
    if (s.redact.step === "review") this.resetResult(id);
    this.changed(id);
  }

  setFieldFile(id: JvToolId, fieldId: string, path: string | null): void {
    const s = this.session(id);
    if (activeRun(s.run.status)) return;
    const next = { ...s.fieldFiles };
    if (path) next[fieldId] = path;
    else delete next[fieldId];
    s.fieldFiles = next;
    if (s.redact.step === "review") this.resetResult(id);
    this.changed(id);
  }

  setOutDir(id: JvToolId, dir: string): void {
    const s = this.session(id);
    s.outDir = dir;
    s.outDirChosen = true;
    this.changed(id);
  }

  // ---- dialoger

  async chooseFiles(id: JvToolId, labels: { title: string; filterName: string }): Promise<void> {
    const schema = this.schema(id);
    const paths = await this.platform.pickFiles({
      title: labels.title,
      filterName: labels.filterName,
      extensions: [...schema.extensions],
    });
    if (paths.length > 0) this.addFiles(id, paths);
  }

  async chooseFolder(id: JvToolId, title: string): Promise<void> {
    const dir = await this.platform.pickFolder(title);
    if (dir) this.addFiles(id, [dir]);
  }

  async chooseOutDir(id: JvToolId, title: string): Promise<void> {
    const dir = await this.platform.pickFolder(title);
    if (dir) this.setOutDir(id, dir);
  }

  async chooseFieldFile(
    id: JvToolId,
    field: { id: string; extensions: string[]; filterName: string; dialogTitle: string },
  ): Promise<void> {
    const [path] = await this.platform.pickFiles({
      title: field.dialogTitle,
      filterName: field.filterName,
      extensions: field.extensions,
    });
    if (path) this.setFieldFile(id, field.id, path);
  }

  // ------------------------------------------------------------ kjøring

  /** Kan «Kjør» trykkes? */
  canRun(id: JvToolId): boolean {
    const schema = this.schema(id);
    const s = this.session(id);
    if (!this.isInstalled(id) || activeRun(s.run.status)) return false;
    if (s.files.length === 0) return false;
    if (schema.exactFiles !== undefined && s.files.length !== schema.exactFiles) return false;
    if (needsOutDir(schema, s.values) && !s.outDir) return false;
    return valuesValid(schema, s.values);
  }

  /** Bygger det som sendes til `jv_run` (steg 1 for sladding: «finn»). */
  buildRequest(id: JvToolId, commandOverride?: string, extra: Record<string, OptionValue> = {}): RunRequest {
    const schema = this.schema(id);
    const s = this.session(id);
    const fieldExtra: Record<string, OptionValue> = {};
    for (const f of schema.fields) {
      if (f.kind === "file" && s.fieldFiles[f.id]) fieldExtra[f.optionKey] = s.fieldFiles[f.id] as string;
    }
    return buildRunRequest(schema, s.values, s.files, s.outDir, { ...fieldExtra, ...extra }, commandOverride);
  }

  /** «Kjør» (og «Finn» i sladding). */
  async run(id: JvToolId): Promise<void> {
    if (!this.canRun(id)) return;
    const schema = this.schema(id);
    if (schema.twoStep) {
      const req = this.buildRequest(id, "finn");
      await this.startRun(id, req, "find");
    } else {
      await this.startRun(id, this.buildRequest(id), "run");
    }
  }

  private async startRun(id: JvToolId, req: RunRequest, kind: "run" | "find"): Promise<void> {
    const s = this.session(id);
    s.run = { ...freshRun(s.run.lastJobId), status: "starting", kind };
    const run = s.run;
    this.changed(id);
    try {
      const job = await this.backend.run(id, req);
      if (run.jobId === null) run.jobId = job;
      if (run.status === "starting") run.status = "running";
      if (run.cancelRequested) void this.backend.cancel(job).catch(() => undefined);
    } catch (e) {
      run.status = "failed";
      run.error = toJvError(e);
    }
    this.changed(id);
  }

  cancelRun(id: JvToolId): void {
    const s = this.session(id);
    if (!activeRun(s.run.status)) return;
    s.run.cancelRequested = true;
    if (s.run.jobId !== null) void this.backend.cancel(s.run.jobId).catch(() => undefined);
    this.changed(id);
  }

  onRunProgress(ev: RunProgressEvent): void {
    if (!isJvToolId(ev.id)) return;
    const run = this.session(ev.id).run;
    if (!activeRun(run.status) || !this.matches(ev.job_id, run)) return;
    run.jobId = ev.job_id;
    run.lastJobId = ev.job_id;
    if (run.status === "starting") run.status = "running";
    run.progress = Math.min(1, Math.max(run.progress, Number.isFinite(ev.progress) ? ev.progress : 0));
    this.emit({ type: "run-progress", id: ev.id });
  }

  async onRunDone(ev: RunDoneEvent): Promise<void> {
    if (!isJvToolId(ev.id)) return;
    const id = ev.id;
    const s = this.session(id);
    const run = s.run;
    if (!activeRun(run.status) || !this.matches(ev.job_id, run)) return;
    run.jobId = null;
    run.lastJobId = ev.job_id;
    if (ev.outcome === "cancelled") {
      run.status = "cancelled";
    } else if (ev.outcome === "failed") {
      run.status = "failed";
      run.error = ev.error ?? { code: "internal" };
      run.message = ev.message;
    } else {
      run.report = ev.report;
      if (run.kind === "find") {
        await this.finishFind(id, ev.report);
        return;
      }
      run.status = "done";
      run.progress = 1;
      this.announce(ev.report?.summary || t.jv.result.doneAnnounce(this.toolName(id)));
    }
    this.changed(id);
  }

  // ------------------------------------------------------------ sladding, steg 1 og 2

  /** «Finn» er ferdig: leser treffene fra planen og viser dem. */
  private async finishFind(id: JvToolId, report: JvReport | null): Promise<void> {
    const s = this.session(id);
    const run = s.run;
    const planPath = outputPath(report?.outputs?.[0]);
    s.redact = { ...freshRedact(), loading: true, findReport: report };
    this.changed(id);
    try {
      if (!planPath) throw { code: "report_invalid" };
      const view = await this.backend.readPlan(planPath);
      // Avkrysningen følger `sladd` i planen: forkastede kandidater har ingen hake.
      const items = view.items.map((i) => ({ ...i }));
      s.redact = { step: "review", planPath, items, findReport: report, loading: false, error: null };
      run.status = "done";
      run.progress = 1;
      this.announce(findSummary(items));
    } catch (e) {
      s.redact = { ...freshRedact(), error: toJvError(e) };
      run.status = "failed";
      run.error = toJvError(e);
    }
    this.changed(id);
  }

  /** Setter eller fjerner avkrysningen på ett treff. Ingenting annet i planen endres. */
  setRedact(id: JvToolId, itemId: string, on: boolean): void {
    const r = this.session(id).redact;
    if (r.step !== "review") return;
    const item = r.items.find((i) => i.id === itemId);
    if (!item || item.redact === on) return;
    item.redact = on;
    this.changed(id);
  }

  setRedactAll(id: JvToolId, on: boolean): void {
    const r = this.session(id).redact;
    if (r.step !== "review") return;
    for (const i of r.items) i.redact = on;
    this.changed(id);
  }

  /** Avkrysningene slik de sendes til `jv_save_plan`: bare id og av/på. */
  planEdits(id: JvToolId): Record<string, boolean> {
    const out: Record<string, boolean> = {};
    for (const i of this.session(id).redact.items) out[i.id] = i.redact;
    return out;
  }

  /** «Sladd»: lagrer avkrysningene i planen og kjører steg 2. */
  async redact(id: JvToolId): Promise<void> {
    const s = this.session(id);
    const r = s.redact;
    if (r.step !== "review" || !r.planPath || activeRun(s.run.status)) return;
    r.loading = true;
    r.error = null;
    this.changed(id);
    try {
      await this.backend.savePlan(r.planPath, this.planEdits(id));
    } catch (e) {
      r.loading = false;
      r.error = toJvError(e);
      this.changed(id);
      return;
    }
    r.loading = false;
    const req = this.buildRequest(id, "sladd", { plan_file: r.planPath });
    // `terms_file` hører bare til «finn».
    delete req.options.terms_file;
    await this.startRun(id, req, "run");
  }

  /** Tilbake til «Finn» (nye valg eller nye filer). */
  backToFind(id: JvToolId): void {
    const s = this.session(id);
    if (activeRun(s.run.status)) return;
    s.run = freshRun(s.run.lastJobId);
    s.redact = freshRedact();
    this.changed(id);
  }

  /** «Kjør på nytt»: behold filer og valg, nullstill resultatet. */
  again(id: JvToolId): void {
    const s = this.session(id);
    if (activeRun(s.run.status)) return;
    // Etter sladding vises gjennomgangen igjen, med de samme avkrysningene.
    s.run = freshRun(s.run.lastJobId);
    this.changed(id);
  }

  /** «Ny jobb»: tøm filene også. */
  newJob(id: JvToolId): void {
    const s = this.session(id);
    if (activeRun(s.run.status)) return;
    s.files = [];
    s.fieldFiles = {};
    s.notice = null;
    s.outDir = s.outDirChosen ? s.outDir : null;
    s.run = freshRun(s.run.lastJobId);
    s.redact = freshRedact();
    this.changed(id);
  }

  // ------------------------------------------------------------ for skallet

  /** Pågår noe som går tapt hvis appen lukkes? */
  busy(): "running" | null {
    for (const [id, s] of this.sessions) {
      if (activeRun(s.run.status) || this.installActive(id)) return "running";
    }
    for (const [id] of this.installs) if (this.installActive(id)) return "running";
    return null;
  }

  displayName(path: string): string {
    return fileName(path);
  }
}
