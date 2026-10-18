import { beforeEach, describe, expect, it } from "vitest";
import type { DoneEvent } from "./api";
import { TranskriberingController } from "./controller";
import { FakeBackend, fakePlatform, modelList, type FakePlatform } from "./fakes";

let backend: FakeBackend;
let platform: FakePlatform;
let c: TranskriberingController;

async function make(setup?: () => void): Promise<TranskriberingController> {
  backend = new FakeBackend();
  platform = fakePlatform();
  setup?.();
  c = new TranskriberingController({
    backend,
    platform,
    announce: (m) => platform.announced.push(m),
    now: () => new Date(2026, 9, 18),
  });
  await c.init();
  return c;
}

const flush = () => new Promise((r) => setTimeout(r, 0));

const done = (job_id: number, over: Partial<DoneEvent> = {}): DoneEvent => ({
  job_id,
  outcome: "completed",
  error: null,
  model_id: "medium-semantic",
  duration_ms: 9000,
  segments: [
    { start_ms: 0, end_ms: 4000, text: "Dette er første linje." },
    { start_ms: 4000, end_ms: 9000, text: "Og dette er neste." },
  ],
  ...over,
});

beforeEach(async () => {
  await make();
});

describe("oppstart", () => {
  it("bruker standardvalgene fra spesifikasjonen første gang", () => {
    expect(c.choices).toEqual({ malform: "bokmål", stil: "tolket", kvalitet: "anbefalt" });
    expect(c.decoding).toBe("beam5");
  });

  it("husker siste valg til neste gang appen startes", async () => {
    await c.setChoice("malform", "nynorsk");
    await c.setChoice("stil", "lydrett");
    await c.setChoice("kvalitet", "rask");
    const next = new TranskriberingController({ backend, platform, announce: () => undefined });
    await next.init();
    expect(next.choices).toEqual({ malform: "nynorsk", stil: "lydrett", kvalitet: "rask" });
  });

  it("husker søkemåten", async () => {
    await c.setDecoding("greedy");
    const next = new TranskriberingController({ backend, platform, announce: () => undefined });
    await next.init();
    expect(next.decoding).toBe("greedy");
  });

  it("starter selv om systemsjekken svikter", async () => {
    await make(() => {
      backend.checkSystem = () => Promise.reject({ code: "internal" });
    });
    expect(c.cpuSupported).toBe(true);
  });

  it("klarer at listen over modeller ikke kan hentes", async () => {
    await make(() => {
      backend.listModels = () => Promise.reject({ code: "internal" });
    });
    expect(c.models).toBeNull();
    expect(c.modelsError?.code).toBe("internal");
    expect(c.modelNeed()).toBeNull();
  });
});

describe("modell som mangler", () => {
  it("finner modellen valgene peker på, med størrelse fra kjernen", () => {
    // Standard er tolket + anbefalt = medium semantic, som er installert.
    expect(c.modelNeed()?.installed).toBe(true);
  });

  it("vet at modellen mangler og hvor mye som allerede er lastet ned", async () => {
    await c.setChoice("kvalitet", "best");
    const need = c.modelNeed();
    expect(need?.installed).toBe(false);
    expect(need?.model.bytes).toBe(1_081_140_203);
    expect(need?.model.id).toBe("large-semantic");
  });

  it("starter ikke uten modell", async () => {
    await c.setChoice("kvalitet", "best");
    c.addFiles(["/a/x.mp3"]);
    c.start();
    await flush();
    expect(backend.transcribeCalls).toHaveLength(0);
    expect(c.queue.ready()).toHaveLength(1);
  });

  it("laster ned modellen, viser framdrift, og starter filene når den er ferdig", async () => {
    await c.setChoice("kvalitet", "best");
    c.addFiles(["/a/x.mp3"]);
    await c.downloadModel();
    expect(backend.downloads).toEqual(["large-semantic"]);
    expect(c.download?.status).toBe("active");
    const h = backend.handlers;
    h?.downloadProgress({ job_id: 1, model_id: "large-semantic", downloaded: 500, total: 1000 });
    expect(c.download?.downloaded).toBe(500);
    backend.install("large-semantic");
    h?.downloadDone({ job_id: 1, model_id: "large-semantic", outcome: "completed", error: null });
    await flush();
    await flush();
    expect(c.download).toBeNull();
    expect(backend.transcribeCalls).toHaveLength(1);
    expect(backend.transcribeCalls[0]?.kvalitet).toBe("best");
  });

  it("viser feilen og lar brukeren prøve igjen når nedlastingen mislykkes", async () => {
    await c.setChoice("kvalitet", "best");
    c.addFiles(["/a/x.mp3"]);
    await c.downloadModel();
    backend.handlers?.downloadDone({
      job_id: 1,
      model_id: "large-semantic",
      outcome: "failed",
      error: { code: "network" },
    });
    await flush();
    expect(c.download?.status).toBe("failed");
    expect(c.download?.error).toEqual({ code: "network" });
    expect(backend.transcribeCalls).toHaveLength(0);
    c.dismissDownload();
    expect(c.download).toBeNull();
  });

  it("starter ikke automatisk etter avbrutt nedlasting", async () => {
    await c.setChoice("kvalitet", "best");
    c.addFiles(["/a/x.mp3"]);
    await c.downloadModel();
    c.cancelDownload();
    expect(backend.cancelled).toEqual([1]);
    backend.handlers?.downloadDone({ job_id: 1, model_id: "large-semantic", outcome: "cancelled", error: null });
    await flush();
    expect(c.download?.status).toBe("cancelled");
    expect(backend.transcribeCalls).toHaveLength(0);
  });

  it("klarer at nedlastingen er ferdig før kjernen har svart med jobb-ID", async () => {
    await c.setChoice("kvalitet", "best");
    c.addFiles(["/a/x.mp3"]);
    backend.downloadModel = async (id) => {
      backend.downloads.push(id);
      backend.install(id);
      backend.handlers?.downloadDone({ job_id: 7, model_id: id, outcome: "completed", error: null });
      return 7;
    };
    await c.downloadModel();
    await flush();
    expect(c.download).toBeNull();
    expect(backend.transcribeCalls).toHaveLength(1);
  });

  it("tar imot feil fra download_model", async () => {
    await c.setChoice("kvalitet", "best");
    c.addFiles(["/a/x.mp3"]);
    backend.downloadModel = () => Promise.reject({ code: "already_downloading" });
    await c.downloadModel();
    expect(c.download?.status).toBe("failed");
  });
});

describe("transkribering", () => {
  it("sender valgene og søkemåten til kjernen, og åpner filen", async () => {
    await c.setChoice("malform", "nynorsk");
    await c.setDecoding("greedy");
    c.addFiles(["/a/intervju.mp3"]);
    c.start();
    await flush();
    expect(backend.transcribeCalls).toEqual([
      { audio_path: "/a/intervju.mp3", malform: "nynorsk", stil: "tolket", kvalitet: "anbefalt", decoding: "greedy" },
    ]);
    const item = c.queue.items[0];
    expect(item?.state).toBe("running");
    expect(c.screen).toEqual({ kind: "file", id: item?.id });
  });

  it("viser framdrift, tid og tekst fortløpende, og så resultatet", async () => {
    c.addFiles(["/a/x.mp3"]);
    c.start();
    await flush();
    const h = backend.handlers;
    h?.progress({ job_id: 1, percent: 12.5, eta_ms: 200_000 });
    h?.segment({ job_id: 1, start_ms: 0, end_ms: 4000, text: "Dette er" });
    const item = c.queue.items[0];
    expect(item?.percent).toBe(12);
    expect(item?.etaMs).toBe(200_000);
    expect(item?.segments).toHaveLength(1);
    h?.done(done(1));
    expect(item?.state).toBe("done");
    expect(item?.segments).toHaveLength(2);
    expect(c.busy()).toBe("unsaved");
  });

  it("tåler hendelser som kommer før transcribe har svart", async () => {
    backend.duringTranscribe = (id, h) => {
      h.progress({ job_id: id, percent: 30, eta_ms: null });
      h.done(done(id));
    };
    c.addFiles(["/a/x.mp3"]);
    c.start();
    await flush();
    expect(c.queue.items[0]?.state).toBe("done");
  });

  it("kjører flere filer etter hverandre", async () => {
    c.addFiles(["/a/1.mp3", "/a/2.mp3"]);
    c.start();
    await flush();
    expect(backend.transcribeCalls.map((r) => r.audio_path)).toEqual(["/a/1.mp3"]);
    expect(c.screen.kind).toBe("new"); // flere filer: bli på listen
    backend.handlers?.done(done(1));
    await flush();
    expect(backend.transcribeCalls.map((r) => r.audio_path)).toEqual(["/a/1.mp3", "/a/2.mp3"]);
  });

  it("går videre til neste fil selv om en feiler", async () => {
    c.addFiles(["/a/1.mp3", "/a/2.mp3"]);
    c.start();
    await flush();
    backend.handlers?.done(done(1, { outcome: "failed", error: { code: "decode_failed" }, segments: [] }));
    await flush();
    expect(c.queue.items[0]?.error).toEqual({ code: "decode_failed" });
    expect(c.queue.items[1]?.state).toBe("running");
  });

  it("gjør feil fra transcribe om til feil på filen og går videre", async () => {
    backend.transcribeError = { code: "cpu_unsupported", missing: ["avx2"] };
    c.addFiles(["/a/1.mp3"]);
    c.start();
    await flush();
    expect(c.queue.items[0]?.state).toBe("failed");
    expect(c.queue.items[0]?.error?.code).toBe("cpu_unsupported");
  });

  it("starter ikke på maskin uten AVX2", async () => {
    await make(() => {
      backend.system = { ...backend.system, cpu_supported: false, missing_cpu_features: ["avx2"] };
    });
    expect(c.cpuSupported).toBe(false);
    c.addFiles(["/a/x.mp3"]);
    c.start();
    await flush();
    expect(backend.transcribeCalls).toHaveLength(0);
  });

  it("avbryter: sender cancel med jobb-ID og får tilbake avbrutt", async () => {
    c.addFiles(["/a/x.mp3"]);
    c.start();
    await flush();
    const id = c.queue.items[0]?.id ?? -1;
    c.cancelItem(id);
    expect(backend.cancelled).toEqual([1]);
    backend.handlers?.done(done(1, { outcome: "cancelled", segments: [] }));
    expect(c.queue.items[0]?.state).toBe("cancelled");
    expect(c.busy()).toBeNull();
  });

  it("sender cancel så snart jobb-ID-en er kjent hvis brukeren avbryter for tidlig", async () => {
    let release: (v: number) => void = () => undefined;
    backend.transcribe = () => new Promise<number>((r) => (release = r));
    c.addFiles(["/a/x.mp3"]);
    c.start();
    await flush();
    c.cancelItem(c.queue.items[0]?.id ?? -1);
    expect(backend.cancelled).toEqual([]);
    release(5);
    await flush();
    expect(backend.cancelled).toEqual([5]);
  });

  it("prøver igjen med valgene som gjelder nå", async () => {
    c.addFiles(["/a/x.mp3"]);
    c.start();
    await flush();
    backend.handlers?.done(done(1, { outcome: "failed", error: { code: "network" }, segments: [] }));
    await c.setChoice("malform", "nynorsk");
    c.retry(c.queue.items[0]?.id ?? -1);
    await flush();
    expect(backend.transcribeCalls[1]?.malform).toBe("nynorsk");
  });

  it("sier fra til skjermlesere når filer legges til, og når de allerede ligger der", () => {
    c.addFiles(["/a/1.mp3", "/a/2.mp3"]);
    expect(platform.announced.at(-1)).toBe("2 filer lagt til.");
    c.addFiles(["/a/1.mp3"]);
    expect(platform.announced.at(-1)).toBe("Filen ligger allerede i listen.");
  });

  it("legger filer fra filvelgeren i køen", async () => {
    platform.picked.files = ["/a/1.mp3", "/a/2.wav"];
    await c.chooseFiles();
    expect(c.queue.ready()).toHaveLength(2);
  });

  it("legger filer med format som ikke støttes, rett i listen som feilet", () => {
    c.addFiles(["/a/opptak.webm"]);
    expect(c.queue.items[0]?.error).toEqual({ code: "unsupported_format", format: "webm" });
    expect(c.queue.ready()).toHaveLength(0);
  });
});

describe("resultat", () => {
  async function finished() {
    c.addFiles(["/a/intervju.mp3"]);
    c.start();
    await flush();
    backend.handlers?.done(done(1));
    return c.queue.items[0]!;
  }

  it("retter tekst direkte og merker den som ulagret", async () => {
    const item = await finished();
    c.edit(item.id, 0, "  Rettet\nlinje. ");
    expect(item.segments[0]?.text).toBe("Rettet linje.");
    expect(item.revision).toBe(1);
  });

  it("lagrer til standard sted og filnavn, og sender den rettede teksten", async () => {
    const item = await finished();
    c.edit(item.id, 1, "Rettet.");
    const r = await c.save(item.id, "docx");
    expect(r).toEqual({ status: "saved", path: "/a/intervju.bokmal.tolket.docx" });
    const req = backend.exportCalls[0];
    expect(req?.target_path).toBeNull();
    expect(req?.overwrite).toBe(false);
    expect(req?.format).toBe("docx");
    expect(req?.segments[1]?.text).toBe("Rettet.");
    expect(req?.date).toBe("18. oktober 2026");
    expect(req?.model_id).toBe("medium-semantic");
    expect(c.busy()).toBeNull(); // lagret
  });

  it("spør før overskriving, og overskriver bare når brukeren har sagt ja", async () => {
    const item = await finished();
    backend.exportError = { code: "file_exists" };
    const r = await c.save(item.id, "txt-time");
    expect(r).toEqual({ status: "exists", name: "intervju.bokmal.tolket.txt" });
    expect(c.busy()).toBe("unsaved");
    backend.exportError = null;
    const r2 = await c.save(item.id, "txt-time", { overwrite: true });
    expect(r2.status).toBe("saved");
    expect(backend.exportCalls.at(-1)?.overwrite).toBe(true);
  });

  it("lar brukeren velge sted selv, og avbryter uten å lagre hvis dialogen lukkes", async () => {
    const item = await finished();
    platform.picked.save = null;
    expect((await c.save(item.id, "srt", { chooseLocation: true })).status).toBe("cancelled");
    expect(backend.exportCalls).toHaveLength(0);
    platform.picked.save = "/Users/kari/Skrivebord/min.srt";
    const r = await c.save(item.id, "srt", { chooseLocation: true });
    expect(r).toEqual({ status: "saved", path: "/Users/kari/Skrivebord/min.srt" });
    expect(platform.savePathRequests[0]).toBe("/a/intervju.bokmal.tolket.srt");
    expect(backend.exportCalls[0]?.overwrite).toBe(true);
  });

  it("gir feilen videre når lagring mislykkes, og lar teksten være ulagret", async () => {
    const item = await finished();
    backend.exportError = { code: "disk_full" };
    const r = await c.save(item.id, "vtt");
    expect(r).toEqual({ status: "failed", error: { code: "disk_full" } });
    expect(c.busy()).toBe("unsaved");
  });

  it("kopierer all tekst uten tidskoder", async () => {
    const item = await finished();
    expect(await c.copyAll(item.id)).toBe(true);
    expect(platform.copied).toEqual(["Dette er første linje. Og dette er neste."]);
  });

  it("viser den lagrede filen i Finder, ellers lydfilen", async () => {
    const item = await finished();
    await c.reveal(item.id);
    expect(platform.revealed.at(-1)).toBe("/a/intervju.mp3");
    await c.save(item.id, "docx");
    await c.reveal(item.id);
    expect(platform.revealed.at(-1)).toBe("/a/intervju.bokmal.tolket.docx");
  });
});

describe("modellinnstillinger", () => {
  it("sletter en modell og henter listen på nytt", async () => {
    expect(await c.deleteModel("small-verbatim")).toBeNull();
    expect(backend.deleted).toEqual(["small-verbatim"]);
  });

  it("gir feilen tilbake når en modell ikke kan slettes", async () => {
    backend.deleteModel = () => Promise.reject({ code: "model_in_shared_folder" });
    expect(await c.deleteModel("small-verbatim")).toEqual({ code: "model_in_shared_folder" });
  });

  it("lagrer valgt modellmappe via kjernen, og kan gå tilbake til standard", async () => {
    platform.picked.folder = "/Volumes/Delt/modeller";
    expect(await c.chooseModelDir()).toBeNull();
    expect(backend.modelDir).toBe("/Volumes/Delt/modeller");
    expect(await c.setModelDir(null)).toBeNull();
    expect(backend.modelDir).toBeNull();
  });

  it("gjør ingenting når mappevalget avbrytes", async () => {
    platform.picked.folder = null;
    expect(await c.chooseModelDir()).toBe("cancelled");
    expect(backend.modelDir).toBeUndefined();
  });

  it("gir feilen tilbake når mappen ikke finnes", async () => {
    backend.setModelDir = () => Promise.reject({ code: "not_a_directory" });
    expect(await c.setModelDir("/finnes/ikke")).toEqual({ code: "not_a_directory" });
  });
});

describe("avslutning", () => {
  it("sier fra om noe pågår, og om noe ikke er lagret", async () => {
    expect(c.busy()).toBeNull();
    c.addFiles(["/a/x.mp3"]);
    expect(c.busy()).toBeNull(); // bare lagt til
    c.start();
    await flush();
    expect(c.busy()).toBe("running");
    backend.handlers?.done(done(1));
    expect(c.busy()).toBe("unsaved");
  });
});

describe("modelllister uten modeller", () => {
  it("viser at ingen modell er installert", async () => {
    await make(() => {
      backend.models = modelList([]);
    });
    expect(c.modelNeed()?.installed).toBe(false);
  });
});
