import { describe, expect, it } from "vitest";
import type { DoneEvent, ProgressEvent, SegmentEvent } from "../tools/transkribering/api";
import { DEFAULT_CHOICES } from "./choices";
import { JobQueue, type QueueChange } from "./queue";

const progress = (job_id: number, percent: number, eta_ms: number | null = null): ProgressEvent => ({
  job_id,
  percent,
  eta_ms,
});
const segment = (job_id: number, start_ms: number, text: string): SegmentEvent => ({
  job_id,
  start_ms,
  end_ms: start_ms + 1000,
  text,
});
const done = (job_id: number, over: Partial<DoneEvent> = {}): DoneEvent => ({
  job_id,
  outcome: "completed",
  error: null,
  model_id: "nb-whisper-small-verbatim-q5_0",
  duration_ms: 5000,
  segments: [{ start_ms: 0, end_ms: 1000, text: "ferdig" }],
  ...over,
});

function started(paths = ["/a/intervju.mp3"]) {
  const q = new JobQueue();
  q.add(paths, "beam5");
  q.startReady(DEFAULT_CHOICES, "beam5");
  return q;
}

/** Kjører første fil i køen til den er i gang med jobb-ID. */
function run(q: JobQueue, jobId: number) {
  const item = q.next();
  if (!item) throw new Error("ingen fil i kø");
  q.markStarting(item.id);
  q.attachJob(item.id, jobId);
  return item;
}

describe("legge til filer", () => {
  it("legger filene klare, med filnavn og uten valg", () => {
    const q = new JobQueue();
    const r = q.add(["/mappe/Intervju æøå.mp3", "C:\\Opptak\\møte.wav"], "beam5");
    expect(r.added.map((i) => i.name)).toEqual(["Intervju æøå.mp3", "møte.wav"]);
    expect(q.items.every((i) => i.state === "ready" && i.choices === null)).toBe(true);
  });

  it("hopper over samme fil to ganger mens den ligger klar", () => {
    const q = new JobQueue();
    q.add(["/a/x.mp3"], "beam5");
    const r = q.add(["/a/x.mp3", "/a/y.mp3"], "beam5");
    expect(r.duplicates).toBe(1);
    expect(r.added.map((i) => i.name)).toEqual(["y.mp3"]);
    expect(q.items).toHaveLength(2);
  });

  it("legger filer med format som ikke støttes, rett inn som feilet med formatet", () => {
    const q = new JobQueue();
    const { added } = q.add(["/a/opptak.webm", "/a/ok.mp3"], "beam5");
    expect(added[0]?.state).toBe("failed");
    expect(added[0]?.error).toEqual({ code: "unsupported_format", format: "webm" });
    expect(added[1]?.state).toBe("ready");
    expect(q.ready()).toHaveLength(1);
  });

  it("kan fjerne en klar fil, men ikke en som kjører", () => {
    const q = started(["/a/x.mp3", "/a/y.mp3"]);
    const first = run(q, 1);
    expect(q.remove(first.id)).toBe(false);
    const second = q.items[1];
    expect(second && q.remove(second.id)).toBe(true);
    expect(q.items).toHaveLength(1);
  });
});

describe("start og kø", () => {
  it("gir klare filer valgene som gjelder når Start trykkes", () => {
    const q = new JobQueue();
    q.add(["/a/x.mp3"], "beam5");
    q.startReady({ malform: "nynorsk", stil: "lydrett", kvalitet: "rask" }, "greedy");
    const item = q.items[0];
    expect(item?.state).toBe("queued");
    expect(item?.choices).toEqual({ malform: "nynorsk", stil: "lydrett", kvalitet: "rask" });
    expect(item?.decoding).toBe("greedy");
  });

  it("kjører én fil om gangen, i den rekkefølgen de ble lagt til", () => {
    const q = started(["/a/1.mp3", "/a/2.mp3", "/a/3.mp3"]);
    const a = run(q, 10);
    expect(q.next()).toBeUndefined(); // en kjører
    q.handleDone(done(10));
    expect(a.state).toBe("done");
    const b = q.next();
    expect(b?.name).toBe("2.mp3");
    expect(b && q.get(b.id)?.state).toBe("queued");
  });

  it("gir ikke ny jobb før forrige er ferdig, også mens den starter", () => {
    const q = started(["/a/1.mp3", "/a/2.mp3"]);
    const a = q.next();
    expect(a).toBeDefined();
    if (a) q.markStarting(a.id);
    expect(q.next()).toBeUndefined();
  });

  it("filer lagt til mens noe kjører, venter som klare", () => {
    const q = started();
    run(q, 1);
    q.add(["/a/ny.mp3"], "beam5");
    expect(q.ready()).toHaveLength(1);
    expect(q.next()).toBeUndefined();
  });
});

describe("framdrift og tekst", () => {
  it("viser framdrift og tid, og går aldri bakover", () => {
    const q = started();
    const item = run(q, 7);
    q.handleProgress(progress(7, 10, 120_000));
    q.handleProgress(progress(7, 8, 130_000));
    expect(item.percent).toBe(10);
    expect(item.etaMs).toBe(130_000);
    q.handleProgress(progress(7, 55.9, null));
    expect(item.percent).toBe(55);
    expect(item.etaMs).toBeNull();
  });

  it("fyller teksten fortløpende", () => {
    const q = started();
    const item = run(q, 7);
    q.handleSegment(segment(7, 0, "første"));
    q.handleSegment(segment(7, 1000, "andre"));
    expect(item.segments.map((s) => s.text)).toEqual(["første", "andre"]);
  });

  it("bytter ut den løpende teksten med den ferdige når jobben er ferdig", () => {
    const q = started();
    const item = run(q, 7);
    q.handleSegment(segment(7, 0, "foreløpig"));
    q.handleDone(done(7));
    expect(item.state).toBe("done");
    expect(item.percent).toBe(100);
    expect(item.segments.map((s) => s.text)).toEqual(["ferdig"]);
    expect(item.modelId).toBe("nb-whisper-small-verbatim-q5_0");
    expect(item.durationMs).toBe(5000);
  });

  it("ignorerer hendelser fra andre jobber og fra jobber som er over", () => {
    const q = started();
    const item = run(q, 7);
    q.handleProgress(progress(99, 50));
    q.handleSegment(segment(99, 0, "feil jobb"));
    expect(item.percent).toBe(0);
    expect(item.segments).toHaveLength(0);
    q.handleDone(done(7));
    q.handleProgress(progress(7, 30));
    q.handleSegment(segment(7, 5000, "for sent"));
    expect(item.segments.map((s) => s.text)).toEqual(["ferdig"]);
  });

  it("samler hendelser som kommer før jobb-ID-en er kjent, og spiller dem av i rekkefølge", () => {
    const q = started();
    const next = q.next();
    expect(next).toBeDefined();
    if (!next) return;
    q.markStarting(next.id);
    q.handleProgress(progress(5, 20, 60_000));
    q.handleSegment(segment(5, 0, "tidlig"));
    q.handleProgress(progress(6, 90)); // fra en annen jobb: forkastes
    q.attachJob(next.id, 5);
    expect(next.percent).toBe(20);
    expect(next.segments.map((s) => s.text)).toEqual(["tidlig"]);
  });

  it("klarer at hele jobben er over før jobb-ID-en er kjent", () => {
    const q = started();
    const next = q.next();
    if (!next) throw new Error("ingen fil");
    q.markStarting(next.id);
    q.handleDone(done(5));
    q.attachJob(next.id, 5);
    expect(next.state).toBe("done");
    expect(next.segments).toHaveLength(1);
  });
});

describe("feil og avbrudd", () => {
  it("setter feilen fra kjernen på filen", () => {
    const q = started();
    const item = run(q, 3);
    q.handleDone(done(3, { outcome: "failed", error: { code: "decode_failed" }, segments: [] }));
    expect(item.state).toBe("failed");
    expect(item.error).toEqual({ code: "decode_failed" });
    expect(item.segments).toEqual([]);
  });

  it("gir intern feil hvis kjernen melder feil uten kode", () => {
    const q = started();
    const item = run(q, 3);
    q.handleDone(done(3, { outcome: "failed", error: null, segments: [] }));
    expect(item.error).toEqual({ code: "internal" });
  });

  it("feil når jobben ikke kommer i gang", () => {
    const q = started();
    const item = q.next();
    if (!item) throw new Error("ingen fil");
    q.markStarting(item.id);
    q.failStart(item.id, { code: "model_missing", model_id: "x" });
    expect(item.state).toBe("failed");
    expect(item.error?.code).toBe("model_missing");
    expect(q.next()).toBeUndefined(); // ingen flere i kø
  });

  it("avbryter kjørende jobb: gir jobb-ID, venter på svar, og blir avbrutt uten tekst", () => {
    const q = started();
    const item = run(q, 4);
    q.handleSegment(segment(4, 0, "halvveis"));
    expect(q.requestCancel(item.id)).toBe(4);
    expect(item.cancelling).toBe(true);
    q.handleDone(done(4, { outcome: "cancelled", segments: [] }));
    expect(item.state).toBe("cancelled");
    expect(item.cancelling).toBe(false);
    expect(item.segments).toEqual([]);
  });

  it("avbryter en fil som venter i køen uten å kalle kjernen", () => {
    const q = started(["/a/1.mp3", "/a/2.mp3"]);
    run(q, 1);
    const second = q.items[1];
    expect(second && q.requestCancel(second.id)).toBeNull();
    expect(second?.state).toBe("cancelled");
  });

  it("husker Avbryt hvis det trykkes før jobb-ID-en er kjent", () => {
    const q = started();
    const item = q.next();
    if (!item) throw new Error("ingen fil");
    q.markStarting(item.id);
    expect(q.requestCancel(item.id)).toBeNull();
    expect(q.attachJob(item.id, 8)).toBe(true); // controller må sende cancel(8)
  });

  it("lar en feilet eller avbrutt fil prøves på nytt, uten gammel tekst eller feil", () => {
    const q = started();
    const item = run(q, 4);
    q.handleDone(done(4, { outcome: "failed", error: { code: "network" }, segments: [] }));
    expect(q.retry(item.id)).toBe(true);
    expect(item.state).toBe("ready");
    expect(item.error).toBeNull();
    expect(item.jobId).toBeNull();
    expect(q.retry(item.id)).toBe(false); // allerede klar
  });
});

describe("rettelser og lagring", () => {
  function finished() {
    const q = started();
    const item = run(q, 1);
    q.handleDone(
      done(1, {
        segments: [
          { start_ms: 0, end_ms: 1000, text: "en" },
          { start_ms: 1000, end_ms: 2000, text: "to" },
        ],
      }),
    );
    return { q, item };
  }

  it("er usikret til første lagring", () => {
    const { q, item } = finished();
    expect(JobQueue.isDirty(item)).toBe(true);
    expect(q.hasUnsaved()).toBe(true);
    q.markSaved(item.id, "/a/x.docx", item.revision);
    expect(JobQueue.isDirty(item)).toBe(false);
    expect(q.hasUnsaved()).toBe(false);
  });

  it("blir usikret igjen av en rettelse etter lagring", () => {
    const { q, item } = finished();
    q.markSaved(item.id, "/a/x.docx", item.revision);
    q.edit(item.id, 1, "to rettet");
    expect(item.segments[1]?.text).toBe("to rettet");
    expect(JobQueue.isDirty(item)).toBe(true);
  });

  it("teller ikke en uendret tekst som rettelse", () => {
    const { q, item } = finished();
    q.edit(item.id, 0, "en");
    expect(item.revision).toBe(0);
  });

  it("husker revisjonen som ble lagret, selv om brukeren retter mens lagringen pågår", () => {
    const { q, item } = finished();
    const rev = item.revision;
    q.edit(item.id, 0, "endret under lagring");
    q.markSaved(item.id, "/a/x.txt", rev);
    expect(JobQueue.isDirty(item)).toBe(true);
  });

  it("regner en ferdig fil uten tekst som ingenting å lagre", () => {
    const q = started();
    const item = run(q, 1);
    q.handleDone(done(1, { segments: [] }));
    expect(item.state).toBe("done");
    expect(JobQueue.isDirty(item)).toBe(false);
  });

  it("kan ikke rette tekst som ikke er ferdig", () => {
    const q = started();
    const item = run(q, 1);
    q.handleSegment(segment(1, 0, "løpende"));
    q.edit(item.id, 0, "rettet");
    expect(item.segments[0]?.text).toBe("løpende");
  });
});

describe("oppsummering og varsler", () => {
  it("vet om noe pågår", () => {
    const q = new JobQueue();
    expect(q.hasRunning()).toBe(false);
    q.add(["/a/x.mp3"], "beam5");
    expect(q.hasRunning()).toBe(false); // klar er ikke startet
    q.startReady(DEFAULT_CHOICES, "beam5");
    expect(q.hasRunning()).toBe(true);
    const item = run(q, 1);
    q.handleDone(done(1));
    expect(q.hasRunning()).toBe(false);
    expect(item.state).toBe("done");
  });

  it("varsler om endringer, og kan avmeldes", () => {
    const q = new JobQueue();
    const seen: QueueChange["type"][] = [];
    const off = q.subscribe((c) => seen.push(c.type));
    q.add(["/a/x.mp3"], "beam5");
    q.startReady(DEFAULT_CHOICES, "beam5");
    const item = run(q, 1);
    q.handleProgress(progress(1, 5));
    q.handleSegment(segment(1, 0, "x"));
    expect(seen).toContain("progress");
    expect(seen).toContain("segment");
    off();
    const n = seen.length;
    q.handleDone(done(1));
    expect(seen.length).toBe(n);
    expect(item.state).toBe("done");
  });
});
