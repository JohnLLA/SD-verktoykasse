// Tilstanden til en modellnedlasting. Rene funksjoner uten Tauri.

import type {
  CoreError,
  DownloadDoneEvent,
  DownloadProgressEvent,
  JobId,
} from "../tools/transkribering/api";
import { PendingEvents } from "./pending";

export type DownloadStatus = "starting" | "active" | "failed" | "cancelled" | "done";

export interface DownloadState {
  modelId: string;
  jobId: JobId | null;
  status: DownloadStatus;
  downloaded: number;
  total: number;
  error: CoreError | null;
  cancelRequested: boolean;
}

type Ev = { job_id: number; kind: "progress"; ev: DownloadProgressEvent } | { job_id: number; kind: "done"; ev: DownloadDoneEvent };

export class DownloadTracker {
  state: DownloadState | null = null;
  private pending = new PendingEvents<Ev>();

  /** `download_model` er kalt; jobb-ID kommer straks. */
  begin(modelId: string, alreadyDownloaded = 0): void {
    this.pending.clear();
    this.state = {
      modelId,
      jobId: null,
      status: "starting",
      downloaded: alreadyDownloaded,
      total: 0,
      error: null,
      cancelRequested: false,
    };
  }

  /** Returnerer `true` hvis brukeren har avbrutt mens vi ventet på jobb-ID. */
  attach(jobId: JobId): boolean {
    const s = this.state;
    if (!s || s.status !== "starting") return false;
    s.jobId = jobId;
    s.status = "active";
    for (const e of this.pending.take(jobId)) this.apply(e);
    return s.cancelRequested && this.state?.status === "active";
  }

  fail(error: CoreError): void {
    const s = this.state;
    if (!s) return;
    this.pending.clear();
    s.status = error.code === "cancelled" ? "cancelled" : "failed";
    s.error = error.code === "cancelled" ? null : error;
  }

  progress(ev: DownloadProgressEvent): void {
    this.dispatch({ job_id: ev.job_id, kind: "progress", ev });
  }

  done(ev: DownloadDoneEvent): void {
    this.dispatch({ job_id: ev.job_id, kind: "done", ev });
  }

  private dispatch(e: Ev): void {
    const s = this.state;
    if (!s) return;
    if (s.jobId === e.job_id) this.apply(e);
    else if (s.status === "starting") this.pending.push(e);
  }

  private apply(e: Ev): void {
    const s = this.state;
    if (!s || s.status !== "active") return;
    if (e.kind === "progress") {
      s.downloaded = e.ev.downloaded;
      s.total = e.ev.total;
      return;
    }
    if (e.ev.outcome === "completed") s.status = "done";
    else if (e.ev.outcome === "cancelled") s.status = "cancelled";
    else {
      s.status = "failed";
      s.error = e.ev.error ?? { code: "internal" };
    }
  }

  /** Brukeren trykker Avbryt. Gir jobb-ID-en som skal avbrytes, hvis den er kjent. */
  requestCancel(): JobId | null {
    const s = this.state;
    if (!s) return null;
    s.cancelRequested = true;
    return s.status === "active" ? s.jobId : null;
  }

  get active(): boolean {
    return this.state?.status === "starting" || this.state?.status === "active";
  }

  clear(): void {
    this.state = null;
    this.pending.clear();
  }
}
