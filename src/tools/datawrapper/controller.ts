// Tilstanden og handlingene på skjermen «Klargjør for Datawrapper». Ingen DOM
// og ingen Tauri (bare `JvController` og `Platform`), så alt kan testes med en
// falsk kjerne.
//
// Flyt: filen kommer inn i økten til det delte `JvController` (slipp eller
// filvelger). Da kjøres `analyser`, og så `lag` med det verktøyet foreslår.
// Hver endring av valgene kjører `lag` på nytt. «Lagre som CSV» er en egen
// `lag`-kjøring med `csv_file`. Rust tillater én kjøring om gangen, så
// endringer mens noe pågår, samles og kjøres rett etterpå.

import { t } from "../../i18n/nb";
import { fileName } from "../../lib/files";
import type { Platform } from "../../platform/types";
import type { JvToolId } from "../jv/api";
import type { JvController, RunState } from "../jv/controller";
import {
  buildAnalyseRequest,
  buildLagRequest,
  choicesFromAnalysis,
  defaultCsvPath,
  ensureCsvExtension,
  initialChoices,
  removeColumn as chooseRemove,
  restoreAllColumns,
  restoreColumn as chooseRestore,
  withSheet,
  withSums,
  withTable,
  withTranspose,
  type Choices,
} from "./request";
import { dropColumn, keptColumns, parseAnalysis, parseMade, selectableSheets, type Analysis, type MadeTable } from "./report";

const ID: JvToolId = "datawrapper";
const D = t.jv.datawrapper;

/** Hvor lenge «Kopiert» står. */
export const FEEDBACK_MS = 3000;

export type Phase = "empty" | "analysing" | "ready" | "failed";

/** Hva som ble kopiert (eller forsøkt), så riktig knapp kan si «Kopiert». */
export type CopyKey = "tsv" | "title" | "description" | "source" | "notes";

export interface Feedback {
  key: CopyKey;
  ok: boolean;
}

type JobKind = "analyse" | "make" | "save";
interface Job {
  kind: JobKind;
  run: RunState;
}

export class DatawrapperController {
  phase: Phase = "empty";
  file: string | null = null;
  analysis: Analysis | null = null;
  choices: Choices = initialChoices();
  made: MadeTable | null = null;
  /** `lag` kjører (forhåndsvisningen er fra forrige gang eller vist uten kolonnen som ble klikket bort). */
  making = false;
  saving = false;
  /** Siste feil: `analyse` gjelder hele filen, `make` og `save` bare den handlingen. */
  error: { kind: JobKind; run: RunState } | null = null;
  /** Stien CSV-filen ble lagret på, med det navnet den faktisk fikk. */
  savedPath: string | null = null;
  feedback: Feedback | null = null;
  /** Telles opp for hver endring, så skjermen vet når den må tegne på nytt. */
  version = 0;

  private job: Job | null = null;
  private dirty = false;
  private queuedSave: string | null = null;
  private listeners = new Set<() => void>();
  private unsubscribe: (() => void) | null = null;
  private feedbackTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly c: JvController,
    private readonly platform: Platform,
  ) {
    this.unsubscribe = c.subscribe((change) => {
      if (change.type === "session" && change.id === ID) this.sync();
    });
    this.sync();
  }

  dispose(): void {
    this.unsubscribe?.();
    this.unsubscribe = null;
    if (this.feedbackTimer) clearTimeout(this.feedbackTimer);
    this.listeners.clear();
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit(): void {
    this.version += 1;
    for (const l of [...this.listeners]) l();
  }

  // ------------------------------------------------------------ avledet

  /** Arkene brukeren kan velge mellom. Listen vises bare når det er flere enn ett. */
  sheets(): Analysis["sheets"] {
    return this.analysis ? selectableSheets(this.analysis) : [];
  }

  /** Tabellene i arket som er valgt. Listen vises bare når det er flere enn én. */
  tables(): Analysis["sheets"][number]["tables"] {
    return this.sheets().find((s) => s.name === this.choices.sheet)?.tables ?? [];
  }

  /** Kan flere kolonner fjernes? Minst én må bli igjen. */
  canRemoveColumn(): boolean {
    return this.made !== null && keptColumns(this.made).length > 1;
  }

  /** Kopiering og lagring venter på at forhåndsvisningen er oppdatert. */
  get ready(): boolean {
    return this.phase === "ready" && this.made !== null && !this.making && !this.saving && !this.dirty;
  }

  // ------------------------------------------------------------ fil og økt

  private sync(): void {
    const file = this.c.session(ID).files[0] ?? null;
    if (file !== this.file) {
      this.reset(file);
      if (file) this.start("analyse", buildAnalyseRequest(file));
      this.emit();
      return;
    }
    this.settle();
  }

  private reset(file: string | null): void {
    this.file = file;
    this.phase = file ? "analysing" : "empty";
    this.analysis = null;
    this.choices = initialChoices();
    this.made = null;
    this.making = false;
    this.saving = false;
    this.error = null;
    this.savedPath = null;
    this.feedback = null;
    this.job = null;
    this.dirty = false;
    this.queuedSave = null;
  }

  /** Starter en kjøring. Gir `false` hvis Rust-siden er opptatt. */
  private start(kind: JobKind, req: Parameters<JvController["runRequest"]>[1]): boolean {
    const before = this.c.session(ID).run;
    void this.c.runRequest(ID, req);
    const run = this.c.session(ID).run;
    if (run === before) return false;
    this.job = { kind, run };
    return true;
  }

  private active(): boolean {
    const s = this.c.session(ID).run.status;
    return s === "starting" || s === "running";
  }

  /** Leser resultatet når en kjøring er ferdig, og setter i gang det som ventet. */
  private settle(): void {
    const job = this.job;
    if (job && (job.run.status === "done" || job.run.status === "failed" || job.run.status === "cancelled")) {
      this.job = null;
      this.finish(job);
    }
    this.kick();
    this.emit();
  }

  private finish(job: Job): void {
    const { kind, run } = job;
    const failed = run.status !== "done";
    if (kind === "analyse") {
      const a = failed ? null : parseAnalysis(run.report);
      if (!a || selectableSheets(a).length === 0) {
        this.phase = "failed";
        this.error = { kind, run: failed ? run : { ...run, status: "failed", error: { code: "report_invalid" } } };
        return;
      }
      this.analysis = a;
      this.choices = choicesFromAnalysis(a);
      this.phase = "ready";
      this.dirty = true;
      return;
    }
    if (kind === "make") {
      this.making = false;
      if (failed) {
        this.error = { kind, run: run.status === "cancelled" ? { ...run, status: "failed", error: { code: "cancelled" } } : run };
        return;
      }
      const m = parseMade(run.report);
      if (!m) {
        this.error = { kind, run: { ...run, status: "failed", error: { code: "report_invalid" } } };
        return;
      }
      this.error = null;
      this.made = m;
      return;
    }
    this.saving = false;
    if (failed) {
      this.error = { kind, run: run.status === "cancelled" ? { ...run, status: "failed", error: { code: "cancelled" } } : run };
      return;
    }
    const m = parseMade(run.report);
    if (!m?.csv) {
      this.error = { kind, run: { ...run, status: "failed", error: { code: "report_invalid" } } };
      return;
    }
    this.error = null;
    this.savedPath = m.csv;
  }

  /** Neste ting å gjøre når ingenting kjører: lagre, eller lag på nytt etter en endring. */
  private kick(): void {
    if (this.phase !== "ready" || !this.file || this.job || this.active()) return;
    if (this.dirty) {
      this.dirty = false;
      this.making = this.start("make", buildLagRequest(this.file, this.choices, this.analysis));
      if (!this.making) this.dirty = true;
      return;
    }
    if (this.queuedSave) {
      const path = this.queuedSave;
      this.queuedSave = null;
      this.saving = this.start("save", buildLagRequest(this.file, this.choices, this.analysis, path));
    }
  }

  private changeChoices(next: Choices): void {
    if (next === this.choices) return;
    this.choices = next;
    this.dirty = true;
    this.error = this.error?.kind === "analyse" ? this.error : null;
    this.savedPath = null;
    this.kick();
    this.emit();
  }

  // ------------------------------------------------------------ valg

  setSheet(name: string): void {
    if (this.analysis) this.changeChoices(withSheet(this.choices, this.analysis, name));
  }

  setTable(table: number): void {
    if (this.tables().some((x) => x.index === table)) this.changeChoices(withTable(this.choices, table));
  }

  setWithSums(on: boolean): void {
    if (on !== this.choices.withSums) this.changeChoices(withSums(this.choices, on));
  }

  setTranspose(on: boolean): void {
    if (on !== this.choices.transpose) this.changeChoices(withTranspose(this.choices, on));
  }

  /**
   * Klikk på en kolonneoverskrift. Kolonnen forsvinner med en gang fra
   * forhåndsvisningen; `lag` bekrefter rett etterpå.
   */
  removeColumn(index: number): void {
    if (!this.made || !this.canRemoveColumn()) return;
    if (!keptColumns(this.made).some((c) => c.index === index)) return;
    this.made = dropColumn(this.made, index);
    this.changeChoices(chooseRemove(this.choices, index));
  }

  restoreColumn(index: number): void {
    this.changeChoices(chooseRestore(this.choices, index));
  }

  restoreAllColumns(): void {
    this.changeChoices(restoreAllColumns(this.choices));
  }

  // ------------------------------------------------------------ handlinger

  /** Starter filvelgeren. Selve filen kommer inn gjennom økten. */
  async chooseFile(): Promise<void> {
    const texts = t.jv.tools.datawrapper;
    await this.c.chooseFiles(ID, { title: texts.dialogTitle, filterName: texts.filterName });
  }

  /** Tilbake til start, så brukeren kan velge en annen fil. */
  clearFile(): void {
    this.c.newJob(ID);
  }

  /**
   * Må kalles rett fra knappetrykket: `navigator.clipboard.writeText` krever
   * en brukerhandling, og `copyText` kaller den før første `await`.
   */
  copy(key: CopyKey, text: string): Promise<boolean> {
    const done = this.platform.copyText(text).catch(() => false);
    return done.then((ok) => {
      this.feedback = { key, ok };
      if (this.feedbackTimer) clearTimeout(this.feedbackTimer);
      this.feedbackTimer = setTimeout(() => {
        this.feedback = null;
        this.emit();
      }, FEEDBACK_MS);
      this.emit();
      return ok;
    });
  }

  copyTable(): Promise<boolean> {
    return this.copy("tsv", this.made?.tsv ?? "");
  }

  /** «Lagre som CSV»: lagre-dialogen først, og så `lag` med `csv_file`. */
  async saveCsv(): Promise<void> {
    if (!this.file || !this.ready) return;
    const path = await this.platform.pickSavePath({
      title: D.saveDialogTitle,
      defaultPath: defaultCsvPath(this.file),
      extension: "csv",
      filterName: D.saveFilterName,
    });
    if (!path || this.phase !== "ready") return;
    this.queuedSave = ensureCsvExtension(path);
    this.savedPath = null;
    this.error = this.error?.kind === "save" ? null : this.error;
    this.kick();
    this.emit();
  }

  /** Navnet på filen som ble lagret, slik det faktisk ble (kan være `navn-2.csv`). */
  savedName(): string | null {
    return this.savedPath ? fileName(this.savedPath) : null;
  }
}
