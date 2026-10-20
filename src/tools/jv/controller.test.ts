// Controller med falsk kjerne: meny, nedlasting, kjøring, resultat og sladding.

import { beforeEach, describe, expect, it } from "vitest";
import { schema as compare } from "../compare/schema";
import { schema as keyframes } from "../keyframes/schema";
import { schema as metadata } from "../metadata/schema";
import { schema as nynorsk } from "../nynorsk/schema";
import { schema as pdfTables } from "../pdf-tables/schema";
import { schema as redact } from "../redact/schema";
import { schema as subtitles } from "../subtitles/schema";
import type { InstalledView, PlanItem } from "./api";
import { JvController } from "./controller";
import { catalogOf, entry, FakeJvBackend, fakePlatform, toolView } from "./fakes";
import { screenMode } from "./view-screen";
import { itemType, itemWhere } from "./view-redact";
import { visibleWarnings } from "./view-result";
import { jvErrorText } from "./errors";
import { t } from "../../i18n/nb";

const flush = () => new Promise((r) => setTimeout(r, 0));

const inst = (id: string, over: Partial<InstalledView> = {}): InstalledView => ({
  id,
  name: id,
  version: "1.0.0",
  bytes: 50_000_000,
  license: "AGPL-3.0-or-later",
  ...over,
});

function setup(opts: { installed?: string[]; platform?: Parameters<typeof fakePlatform>[0] } = {}) {
  const backend = new FakeJvBackend();
  backend.installedList = (opts.installed ?? []).map((id) => inst(id));
  const messages: string[] = [];
  const c = new JvController({ backend, platform: fakePlatform(opts.platform), announce: (m) => messages.push(m) });
  for (const s of [compare, keyframes, metadata, nynorsk, pdfTables, redact, subtitles]) c.registerSchema(s);
  return { backend, c, messages };
}

describe("menyen", () => {
  it("viser lastet ned, ikke lastet ned og «Kommer»", async () => {
    const { c, backend } = setup({ installed: ["compare"] });
    backend.catalogResult = catalogOf({ nynorsk: "not_for_platform", keyframes: "needs_newer_os" });
    await c.init();
    await c.loadCatalog(true);
    expect(c.menuStatus("compare")).toBe("ready");
    expect(c.menuStatus("metadata")).toBe("download");
    expect(c.menuStatus("keyframes")).toBe("download");
    expect(c.menuStatus("nynorsk")).toBe("soon");
  });

  it("uten katalog står alt som ikke er lastet ned, som «ikke lastet ned»", async () => {
    const { c, backend } = setup();
    backend.catalogResult = { code: "catalog_missing" };
    await c.init();
    expect(c.menuStatus("compare")).toBe("download");
    expect(c.menuStatus("nynorsk")).toBe("download");
  });

  it("henter katalogen fra nett bare når brukeren åpner et verktøy som ikke er lastet ned", async () => {
    const { c, backend } = setup({ installed: ["compare"] });
    await c.init();
    expect(backend.callsOf("catalog")).toEqual([[false]]);
    await c.open("compare");
    expect(backend.callsOf("catalog")).toEqual([[false]]);
    await c.open("metadata");
    expect(backend.callsOf("catalog")).toEqual([[false], [true]]);
    // Én gang per økt når det gikk bra.
    await c.open("ocr" as never);
    expect(backend.callsOf("catalog")).toHaveLength(2);
  });

  it("sier «Kommer for Windows» når katalogen er for Windows", async () => {
    const { c, backend } = setup();
    backend.catalogResult = catalogOf({ nynorsk: "not_for_platform" }, { target: "x86_64-pc-windows-msvc" });
    await c.init();
    expect(c.catalogPlatform()).toBe("windows");
    expect(t.jv.install.comingTitle(c.catalogPlatform())).toBe("Kommer for Windows");
    expect(c.installScreen("nynorsk")).toBe("soon");
  });

  it("sier fra om nyere macOS på vanlig norsk", () => {
    const text = jvErrorText({ code: "needs_newer_os", min_os: "26.6.2" });
    expect(text.title).toBe("Verktøyet trenger macOS 26.6.2 eller nyere");
    expect(text.hint).toContain("Programvareoppdatering");
    expect(jvErrorText({ code: "needs_newer_os", min_os: "15.0" }).title).toBe("Verktøyet trenger macOS 15 eller nyere");
    expect(t.jv.install.needsOsTitle("26.6.2")).toBe("Verktøyet trenger macOS 26.6.2 eller nyere");
  });
});

describe("nedlasting", () => {
  let ctx: ReturnType<typeof setup>;
  beforeEach(async () => {
    ctx = setup();
    ctx.backend.catalogResult = catalogOf({ ocr: { ...toolView("ocr", "available"), entry: entry("ocr", { bytes: 200_000_000 }) } });
    await ctx.c.init();
  });

  it("viser fremdrift, installering og ferdig, og leser listen på nytt", async () => {
    const { c, backend } = ctx;
    const done = c.install("ocr" as never);
    expect(c.installState("ocr" as never).status).toBe("starting");
    await done;
    expect(backend.callsOf("install")).toEqual([["ocr"]]);
    backend.installProgress({ job_id: 1, id: "ocr", downloaded: 50_000_000, total: 200_000_000 });
    const s = c.installState("ocr" as never);
    expect(s.status).toBe("downloading");
    expect([s.downloaded, s.total]).toEqual([50_000_000, 200_000_000]);
    backend.installProgress({ job_id: 1, id: "ocr", phase: "install", downloaded: 0, total: 0 });
    expect(c.installState("ocr" as never).status).toBe("installing");
    backend.installedList = [inst("ocr")];
    backend.installDone({ job_id: 1, id: "ocr" });
    expect(c.installState("ocr" as never).status).toBe("done");
    await flush();
    expect(c.isInstalled("ocr")).toBe(true);
    expect(c.menuStatus("ocr")).toBe("ready");
  });

  it("tar imot hendelser som kommer før jobb-ID-en er kjent", async () => {
    const { c, backend } = ctx;
    const p = c.install("ocr" as never);
    backend.installProgress({ job_id: 1, id: "ocr", downloaded: 10, total: 100 });
    backend.installDone({ job_id: 1, id: "ocr", outcome: "failed", error: { code: "download", cause: { code: "network" } }, version: null });
    await p;
    const s = c.installState("ocr" as never);
    expect(s.status).toBe("failed");
  });

  it("ikke nett: forståelig melding og «Prøv igjen»", async () => {
    const { c, backend } = ctx;
    await c.install("ocr" as never);
    backend.installDone({ job_id: 1, id: "ocr", outcome: "failed", error: { code: "download", cause: { code: "network" } }, version: null });
    const s = c.installState("ocr" as never);
    expect(s.status).toBe("failed");
    expect(jvErrorText(s.error!).title).toBe("Ingen nettforbindelse");
    // Prøv igjen: ny jobb.
    await c.install("ocr" as never);
    expect(c.installState("ocr" as never).status).toBe("downloading");
    expect(c.installState("ocr" as never).error).toBeNull();
    expect(backend.callsOf("install")).toHaveLength(2);
  });

  it("feil sjekksum og ikke plass har egne meldinger", () => {
    expect(jvErrorText({ code: "checksum_mismatch" }).title).toBe("Nedlastingen ble skadet");
    expect(jvErrorText({ code: "download", cause: { code: "disk_full" } }).title).toBe("Det er ikke nok plass på disken");
    for (const e of [
      { code: "download", cause: { code: "internal" } },
      { code: "download", cause: { code: "network" } },
    ] as const) {
      const text = jvErrorText(e);
      expect(text.title.length).toBeGreaterThan(0);
      expect(JSON.stringify(text)).not.toMatch(/panic|stack|Error\(|\.rs/);
    }
  });

  it("feil som kommer som svar fra jv_install (for gammel macOS) gir feilen og ingen jobb", async () => {
    const { c, backend } = ctx;
    backend.installError = { code: "needs_newer_os", min_os: "26.6.2" };
    await c.install("ocr" as never);
    const s = c.installState("ocr" as never);
    expect(s.status).toBe("failed");
    expect(s.error).toEqual({ code: "needs_newer_os", min_os: "26.6.2" });
  });

  it("avbryt stopper jobben og beholder det som er lastet ned", async () => {
    const { c, backend } = ctx;
    await c.install("ocr" as never);
    c.cancelInstall("ocr" as never);
    expect(backend.callsOf("cancel")).toEqual([[1]]);
    backend.installDone({ job_id: 1, id: "ocr", outcome: "cancelled", version: null });
    expect(c.installState("ocr" as never).status).toBe("cancelled");
    expect(c.installState("ocr" as never).error).toBeNull();
  });

  it("avbryt før jobb-ID er kjent sendes så snart den kommer", async () => {
    const { c, backend } = ctx;
    const p = c.install("ocr" as never);
    c.cancelInstall("ocr" as never);
    await p;
    expect(backend.callsOf("cancel")).toEqual([[1]]);
  });

  it("ignorerer hendelser fra en eldre jobb", async () => {
    const { c, backend } = ctx;
    await c.install("ocr" as never);
    backend.installDone({ job_id: 1, id: "ocr", outcome: "failed", error: { code: "internal" }, version: null });
    await c.install("ocr" as never);
    backend.installProgress({ job_id: 1, id: "ocr", downloaded: 999, total: 1000 });
    expect(c.installState("ocr" as never).downloaded).toBe(0);
    backend.installProgress({ job_id: 2, id: "ocr", downloaded: 5, total: 1000 });
    expect(c.installState("ocr" as never).downloaded).toBe(5);
  });

  it("«Se etter oppdateringer» henter katalogen og teller nye versjoner, og oppdaterer ikke selv", async () => {
    const { c, backend } = ctx;
    backend.installedList = [inst("ocr")];
    await c.refreshInstalled();
    backend.catalogResult = catalogOf({ ocr: toolView("ocr", "available", { installed_version: "1.0.0", update_available: true }) });
    const r = await c.checkUpdates();
    expect(r).toEqual({ ok: true, updates: 1 });
    expect(backend.callsOf("install")).toEqual([]);
    await c.install("ocr" as never);
    expect(backend.callsOf("install")).toEqual([["ocr"]]);
  });

  it("uten nett viser «Se etter oppdateringer» at sjekken feilet", async () => {
    const { c, backend } = ctx;
    backend.catalogResult = catalogOf({}, { source: "cache", error: { code: "download", cause: { code: "network" } } });
    expect(await c.checkUpdates()).toEqual({ ok: false, updates: 0 });
  });

  it("fjerner et verktøy, men ikke mens det brukes", async () => {
    const { c, backend } = ctx;
    backend.installedList = [inst("compare")];
    await c.refreshInstalled();
    expect(await c.remove("compare" as never)).toBeNull();
    expect(c.isInstalled("compare")).toBe(false);
    backend.installedList = [inst("compare")];
    await c.refreshInstalled();
    c.addFiles("compare" as never, ["/a.txt", "/b.txt"]);
    await c.run("compare" as never);
    expect(await c.remove("compare" as never)).toEqual({ code: "busy" });
  });
});

describe("kjøring", () => {
  it("gir riktige argumenter til jv_run og utmappe fra første fil", async () => {
    const { c, backend } = setup({ installed: ["subtitles"] });
    await c.init();
    c.addFiles("subtitles" as never, ["/Saker/ordfører/tekst.json"]);
    expect(c.session("subtitles" as never).outDir).toBe("/Saker/ordfører");
    c.setValue("subtitles" as never, "length", "long");
    await c.run("subtitles" as never);
    expect(backend.callsOf("run")).toEqual([
      ["subtitles", { inputs: ["/Saker/ordfører/tekst.json"], out_dir: "/Saker/ordfører", options: { max_chars: 60, max_lines: 2 } }],
    ]);
  });

  it("utmappen kan endres og følger ikke lenger første fil", async () => {
    const { c } = setup({ installed: ["subtitles"], platform: { pickFolder: async () => "/Ferdig" } });
    await c.init();
    c.addFiles("subtitles" as never, ["/a/t.json"]);
    await c.chooseOutDir("subtitles" as never, "Velg");
    c.addFiles("subtitles" as never, ["/b/u.json"]);
    expect(c.session("subtitles" as never).outDir).toBe("/Ferdig");
  });

  it("kan ikke kjøres uten filer, uten riktig antall filer eller med ugyldige valg", async () => {
    const { c } = setup({ installed: ["compare", "keyframes"] });
    await c.init();
    expect(c.canRun("compare" as never)).toBe(false);
    c.addFiles("compare" as never, ["/a.txt"]);
    expect(c.canRun("compare" as never)).toBe(false);
    c.addFiles("compare" as never, ["/b.txt"]);
    expect(c.canRun("compare" as never)).toBe(true);
    c.addFiles("keyframes" as never, ["/v.mp4"]);
    c.setValue("keyframes" as never, "every_seconds", 0);
    expect(c.canRun("keyframes" as never)).toBe(false);
    c.setValue("keyframes" as never, "every_seconds", 4);
    expect(c.canRun("keyframes" as never)).toBe(true);
  });

  it("compare: to filer i rekkefølge, tre filer gir melding, bytte rekkefølge", async () => {
    const { c } = setup({ installed: ["compare"] });
    await c.init();
    c.addFiles("compare" as never, ["/gammel.docx", "/ny.docx"]);
    expect(c.session("compare" as never).files).toEqual(["/gammel.docx", "/ny.docx"]);
    c.swapFiles("compare" as never);
    expect(c.session("compare" as never).files).toEqual(["/ny.docx", "/gammel.docx"]);
    c.addFiles("compare" as never, ["/a.txt", "/b.txt", "/c.txt"]);
    expect(c.session("compare" as never).notice).toEqual({ kind: "count", n: 2 });
    expect(c.session("compare" as never).files).toHaveLength(2);
  });

  it("filformat som ikke støttes gir melding med navnene", async () => {
    const { c } = setup({ installed: ["pdf-tables"] });
    await c.init();
    c.addFiles("pdf-tables" as never, ["/a/regnskap.xlsx", "/a/b.pdf"]);
    const s = c.session("pdf-tables" as never);
    expect(s.files).toEqual(["/a/b.pdf"]);
    expect(s.notice).toEqual({ kind: "unsupported", names: ["regnskap.xlsx"] });
    expect(t.jv.screen.unsupportedHint(["regnskap.xlsx"], "pdf med tekst")).toContain("Gjør filen om til et av disse formatene");
  });

  it("framdrift, avbryt og ferdig med rapport og advarsler", async () => {
    const { c, backend, messages } = setup({ installed: ["pdf-tables"] });
    await c.init();
    c.addFiles("pdf-tables" as never, ["/a/b.pdf"]);
    await c.run("pdf-tables" as never);
    const run = () => c.session("pdf-tables" as never).run;
    expect(run().status).toBe("running");
    backend.runProgress({ job_id: 1, id: "pdf-tables", progress: 0.4 });
    backend.runProgress({ job_id: 1, id: "pdf-tables", progress: 0.2 });
    expect(run().progress).toBe(0.4);
    const report = {
      summary: "Fant 2 tabeller.",
      warnings: ["Tabellen på side 3 har ujevnt antall kolonner.", "PDF-en ser ut til å være skannet. Kjør ocr først."],
      outputs: ["/a/b-tabeller.xlsx"],
    };
    backend.runDone({ job_id: 1, id: "pdf-tables", report });
    await flush();
    expect(run().status).toBe("done");
    expect(run().report).toEqual(report);
    expect(visibleWarnings(run().report)).toEqual(report.warnings);
    expect(messages).toContain("Fant 2 tabeller.");
    expect(screenMode(pdfTables, c.session("pdf-tables" as never))).toBe("result");
  });

  it("verktøyets egen feilmelding (kode 1) beholdes, og feilen er på vanlig norsk", async () => {
    const { c, backend } = setup({ installed: ["pdf-tables"] });
    await c.init();
    c.addFiles("pdf-tables" as never, ["/a/b.pdf"]);
    await c.run("pdf-tables" as never);
    backend.runDone({ job_id: 1, id: "pdf-tables", outcome: "failed", error: { code: "tool_failed", exit_code: 1 }, message: "Filen «b.pdf» er skadet." });
    await flush();
    const run = c.session("pdf-tables" as never).run;
    expect(run.status).toBe("failed");
    expect(run.message).toBe("Filen «b.pdf» er skadet.");
    expect(screenMode(pdfTables, c.session("pdf-tables" as never))).toBe("setup");
  });

  it("feil fra jv_run (ikke installert) blir en feil uten å starte", async () => {
    const { c, backend } = setup({ installed: ["pdf-tables"] });
    await c.init();
    backend.runError = { code: "code_signature" };
    c.addFiles("pdf-tables" as never, ["/a/b.pdf"]);
    await c.run("pdf-tables" as never);
    const run = c.session("pdf-tables" as never).run;
    expect(run.status).toBe("failed");
    expect(jvErrorText(run.error!).title).toBe("Verktøyet er ikke godkjent av macOS");
  });

  it("avbryt under kjøring", async () => {
    const { c, backend } = setup({ installed: ["pdf-tables"] });
    await c.init();
    c.addFiles("pdf-tables" as never, ["/a/b.pdf"]);
    await c.run("pdf-tables" as never);
    c.cancelRun("pdf-tables" as never);
    expect(backend.callsOf("cancel")).toEqual([[1]]);
    backend.runDone({ job_id: 1, id: "pdf-tables", outcome: "cancelled" });
    await flush();
    expect(c.session("pdf-tables" as never).run.status).toBe("cancelled");
    expect(c.busy()).toBeNull();
  });

  it("nynorsk: resultatet merkes alltid som utkast, og retningen sendes", async () => {
    const { c, backend } = setup({ installed: ["nynorsk"] });
    await c.init();
    c.addFiles("nynorsk" as never, ["/t/tekst.docx"]);
    c.setValue("nynorsk" as never, "to", "nb");
    await c.run("nynorsk" as never);
    expect(backend.callsOf("run")[0]?.[1]).toMatchObject({ options: { to: "nb" } });
    expect(nynorsk.draftNotice).toBe(true);
    expect(t.jv.result.draft).toBe("Utkast – må leses over");
  });

  it("ny jobb tømmer filene, og nye filer nullstiller et gammelt resultat", async () => {
    const { c, backend } = setup({ installed: ["pdf-tables"] });
    await c.init();
    c.addFiles("pdf-tables" as never, ["/a/b.pdf"]);
    await c.run("pdf-tables" as never);
    backend.runDone({ job_id: 1, id: "pdf-tables", report: { summary: "ok", outputs: [] } });
    await flush();
    c.addFiles("pdf-tables" as never, ["/a/c.pdf"]);
    expect(c.session("pdf-tables" as never).run.status).toBe("idle");
    c.newJob("pdf-tables" as never);
    expect(c.session("pdf-tables" as never).files).toEqual([]);
  });

  it("drop og dialog legger til filer via plattformen", async () => {
    const { c } = setup({ installed: ["metadata"], platform: { pickFiles: async () => ["/f/bilde.jpg"], pickFolder: async () => "/f/bilder" } });
    await c.init();
    await c.chooseFiles("metadata" as never, { title: "x", filterName: "y" });
    await c.chooseFolder("metadata" as never, "x");
    expect(c.session("metadata" as never).files).toEqual(["/f/bilde.jpg", "/f/bilder"]);
  });
});

const item = (id: string, over: Partial<PlanItem> = {}): PlanItem => ({
  id,
  type: "fodselsnummer",
  page: 1,
  excerpt: "…fødselsnummer 010101 12345…",
  placement: "side",
  redact: true,
  rejected: false,
  reason: null,
  ...over,
});

describe("sladding i to steg", () => {
  async function toReview() {
    const ctx = setup({ installed: ["redact"] });
    ctx.backend.plan = {
      items: [item("t1"), item("t2", { type: "epost", page: 2, redact: true }), item("t3", { type: "telefon", page: 3, redact: false, rejected: true, reason: "tabell" })],
    };
    await ctx.c.init();
    ctx.c.addFiles("redact" as never, ["/s/sak.pdf"]);
    ctx.c.setFieldFile("redact" as never, "terms", "/s/ord.txt");
    await ctx.c.run("redact" as never);
    ctx.backend.runDone({
      job_id: 1,
      id: "redact",
      report: {
        summary: "Fant 2 treff. 1 mulige numre ble forkastet.",
        warnings: ["1 mulige fødselsnumre/telefonnumre ble IKKE merket for sladding (stor avstand mellom sifrene) – gå gjennom planen.", "1 treff ligger ikke som synlig tekst på siden."],
        outputs: [{ path: "/s/sak-treff.json", treff: 2, forkastet: 1 }],
      },
    });
    await flush();
    return ctx;
  }

  it("«Finn» kjører finn med listen over egne ord, og viser treffene til gjennomgang", async () => {
    const { c, backend } = await toReview();
    expect(backend.callsOf("run")[0]).toEqual(["redact", { command: "finn", inputs: ["/s/sak.pdf"], out_dir: "/s", options: { terms_file: "/s/ord.txt" } }]);
    expect(backend.callsOf("readPlan")).toEqual([["/s/sak-treff.json"]]);
    const s = c.session("redact" as never);
    expect(screenMode(redact, s)).toBe("review");
    expect(s.redact.items.map((i) => i.id)).toEqual(["t1", "t2", "t3"]);
  });

  it("forkastede kandidater står uten hake som standard, merket og i egen gruppe", async () => {
    const { c } = await toReview();
    const items = c.session("redact" as never).redact.items;
    const rejected = items.filter((i) => i.rejected);
    expect(rejected.map((i) => i.id)).toEqual(["t3"]);
    expect(rejected.every((i) => !i.redact)).toBe(true);
    expect(t.jv.redact.rejectedHint).toContain("kan være ekte numre");
    // Alle advarslene vises, også at forkastede treff ikke er merket.
    const report = c.session("redact" as never).redact.findReport;
    expect(visibleWarnings(report)).toEqual(report!.warnings);
  });

  it("brukeren kan bare krysse av og på: «Sladd» lagrer bare id og av/på, og kjører sladd med planen", async () => {
    const { c, backend } = await toReview();
    c.setRedact("redact" as never, "t2", false);
    c.setRedact("redact" as never, "t3", false);
    await c.redact("redact" as never);
    expect(backend.savedPlans).toEqual([{ path: "/s/sak-treff.json", redact: { t1: true, t2: false, t3: false } }]);
    // Bare sladd-feltene er sendt: ingen tekst, utdrag, side eller rektangler.
    expect(JSON.stringify(backend.savedPlans)).not.toMatch(/fødselsnummer|utdrag|excerpt|rektangler|side/);
    expect(backend.callsOf("run")[1]).toEqual(["redact", { command: "sladd", inputs: ["/s/sak.pdf"], out_dir: "/s", options: { plan_file: "/s/sak-treff.json" } }]);
    expect(c.session("redact" as never).run.status).toBe("running");
  });

  it("lagringen endrer bare sladd: forkastede er false til brukeren krysser dem av", async () => {
    const { c, backend } = await toReview();
    expect(c.planEdits("redact" as never)).toEqual({ t1: true, t2: true, t3: false });
    c.setRedact("redact" as never, "t3", true);
    await c.redact("redact" as never);
    expect(backend.savedPlans).toEqual([{ path: "/s/sak-treff.json", redact: { t1: true, t2: true, t3: true } }]);
  });

  it("endrer ingenting annet enn avkrysningen i treffene", async () => {
    const { c, backend } = await toReview();
    const before = (await backend.readPlan("/x")).items.map(({ redact: _r, ...rest }) => rest);
    c.setRedactAll("redact" as never, false);
    c.setRedact("redact" as never, "t1", true);
    c.setRedact("redact" as never, "finnes-ikke", true);
    const after = c.session("redact" as never).redact.items.map(({ redact: _r, ...rest }) => rest);
    expect(after).toEqual(before);
    expect(c.planEdits("redact" as never)).toEqual({ t1: true, t2: false, t3: false });
  });

  it("feil ved lagring av planen stopper før sladdingen starter", async () => {
    const { c, backend } = await toReview();
    backend.savePlanError = { code: "io", kind: "PermissionDenied" };
    await c.redact("redact" as never);
    expect(backend.callsOf("run")).toHaveLength(1);
    expect(c.session("redact" as never).redact.error).toEqual({ code: "io", kind: "PermissionDenied" });
  });

  it("etter sladding vises resultatet uten planfilen, og «tilbake» gir gjennomgangen med samme avkrysninger", async () => {
    const { c, backend } = await toReview();
    c.setRedact("redact" as never, "t2", false);
    await c.redact("redact" as never);
    backend.runDone({ job_id: 2, id: "redact", report: { summary: "Sladdet 1 treff.", outputs: [{ path: "/s/sak-sladdet.pdf", sladdet: 1 }] } });
    await flush();
    const s = c.session("redact" as never);
    expect(screenMode(redact, s)).toBe("result");
    c.again("redact" as never);
    expect(screenMode(redact, s)).toBe("review");
    expect(c.planEdits("redact" as never).t2).toBe(false);
  });

  it("uten treff vises beskjed, og «Sladd» lager en vasket kopi", async () => {
    const ctx = setup({ installed: ["redact"] });
    ctx.backend.plan = { items: [] };
    await ctx.c.init();
    ctx.c.addFiles("redact" as never, ["/s/sak.pdf"]);
    await ctx.c.run("redact" as never);
    ctx.backend.runDone({ job_id: 1, id: "redact", report: { summary: "Fant ingen treff.", outputs: ["/s/sak-treff.json"] } });
    await flush();
    expect(ctx.c.session("redact" as never).redact.items).toEqual([]);
    expect(screenMode(redact, ctx.c.session("redact" as never))).toBe("review");
  });

  it("finner ikke planen i rapporten: feilmelding, tilbake til Finn", async () => {
    const ctx = setup({ installed: ["redact"] });
    await ctx.c.init();
    ctx.c.addFiles("redact" as never, ["/s/sak.pdf"]);
    await ctx.c.run("redact" as never);
    ctx.backend.runDone({ job_id: 1, id: "redact", report: { summary: "?", outputs: [] } });
    await flush();
    const s = ctx.c.session("redact" as never);
    expect(s.run.status).toBe("failed");
    expect(screenMode(redact, s)).toBe("setup");
  });

  it("viser type og sted på norsk", () => {
    expect(itemType(item("a"))).toBe("Fødselsnummer");
    expect(itemWhere(item("a", { page: 4 }))).toBe("Side 4");
    expect(itemWhere(item("a", { page: 2, placement: "skjult lag" }))).toBe("Skjult lag, side 2");
    expect(itemWhere(item("a", { page: null, placement: "metadata" }))).toBe("Metadata");
  });
});

describe("hendelser og lukking", () => {
  it("meldes som opptatt mens noe pågår", async () => {
    const { c, backend } = setup({ installed: ["compare"] });
    backend.catalogResult = catalogOf({});
    await c.init();
    expect(c.busy()).toBeNull();
    await c.install("metadata" as never);
    expect(c.busy()).toBe("running");
    c.cancelInstall("metadata" as never);
    backend.installDone({ job_id: 1, id: "metadata", outcome: "cancelled", version: null });
    expect(c.busy()).toBeNull();
  });

  it("ignorerer hendelser for ukjente verktøy", () => {
    const { c, backend } = setup();
    void c.init();
    expect(() => backend.runDone({ job_id: 9, id: "finnes-ikke" })).not.toThrow();
  });
});
