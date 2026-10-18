// Hendelser fra Rust kan komme før `invoke` har svart med jobb-ID-en (jobben
// starter i en egen tråd). Mens vi venter på ID-en, samler vi hendelsene og
// spiller dem av i rekkefølge når ID-en er kjent.

export class PendingEvents<E extends { job_id: number }> {
  private buffer: E[] = [];

  push(ev: E): void {
    this.buffer.push(ev);
  }

  /** Tar ut hendelsene som hører til jobben, og forkaster resten. */
  take(jobId: number): E[] {
    const mine = this.buffer.filter((e) => e.job_id === jobId);
    this.buffer = [];
    return mine;
  }

  clear(): void {
    this.buffer = [];
  }
}
