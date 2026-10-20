// Klargjør for Datawrapper: argumentene fra skjermvalgene, kolonnefjerning med
// riktig nummerering, visning av rapporten og hele flyten mot en falsk kjerne.

import { beforeEach, describe, expect, it, vi } from "vitest";
import argsRsRaw from "../../../src-tauri/src/tools/jv/args.rs?raw";
import { t } from "../../i18n/nb";
import type { InstalledView, JvReport } from "../jv/api";
import { JvController } from "../jv/controller";
import { FakeJvBackend, fakePlatform } from "../jv/fakes";
import { DatawrapperController, FEEDBACK_MS } from "./controller";
import {
  PREVIEW_ROWS,
  dropColumn,
  keptColumns,
  parseAnalysis,
  parseMade,
  previewOf,
  selectableSheets,
  tsvRows,
  type Analysis,
} from "./report";
import {
  buildAnalyseRequest,
  buildLagRequest,
  choicesFromAnalysis,
  defaultCsvPath,
  ensureCsvExtension,
  initialChoices,
  removeColumn,
  restoreAllColumns,
  restoreColumn,
  withSheet,
  withSums,
  withTable,
  withTranspose,
} from "./request";
import { schema } from "./schema";

const argsRs = argsRsRaw.replace(/\r\n/g, "\n");
const flush = () => new Promise((r) => setTimeout(r, 0));

// ---- rapporter som `jv datawrapper` lager (core.py)

function tableSummary(index: number, range: string, over: Record<string, unknown> = {}) {
  return { index, range, suggested: false, rows: 8, columns: 5, headers: [], title: "", description: "", source: "", notes: [], transpose_suggested: false, ...over };
}

function analysisReport(over: Record<string, unknown> = {}): JvReport {
  return {
    tool: "datawrapper",
    summary: "Fant 3 tabeller i 2 ark.",
    warnings: [],
    outputs: [],
    datawrapper: {
      format: "xlsx",
      hidden_sheets: 1,
      xml_parser: "defusedxml",
      suggested_sheet: "Befolkning",
      sheets: [
        { name: "Skjult", numbers: 0, suggested: false, suggested_table: null, tables: [] },
        { name: "Boliger", numbers: 8, suggested: false, suggested_table: 1, tables: [tableSummary(1, "A3:C7", { suggested: true })] },
        { name: "Befolkning", numbers: 40, suggested: true, suggested_table: 2, tables: [tableSummary(1, "A30:B33", { rows: 3, columns: 2 }), tableSummary(2, "A4:E13", { suggested: true })] },
      ],
      ...over,
    },
  };
}

const COLUMNS = [
  { index: 1, name: "Kommune", numeric: false, sum: false, removed: false },
  { index: 2, name: "Kvinner", numeric: true, sum: false, removed: false },
  { index: 3, name: "Menn", numeric: true, sum: false, removed: false },
  { index: 4, name: "Endring (%)", numeric: true, sum: false, removed: false },
];
const TSV = "Kommune\tKvinner\tMenn\tEndring (%)\nAskvoll\t1260\t1250\t0.4\nBjørnevik\t2100\t2050\t\nDalsfjord\t3300\t3190\t-1.2\n";

function madeReport(over: Record<string, unknown> = {}, extra: Partial<JvReport> = {}): JvReport {
  return {
    tool: "datawrapper",
    summary: "Tabellen har 3 rader og 4 kolonner og er klar for Datawrapper.",
    warnings: ["Fjernet 1 sumrad. Velg «Ta med sumrader» for å beholde dem."],
    outputs: [],
    datawrapper: {
      format: "xlsx",
      hidden_sheets: 1,
      xml_parser: "defusedxml",
      sheet: "Befolkning",
      table: 2,
      tables_in_sheet: 2,
      range: "A4:E13",
      title: "Folkemengde per kommune",
      description: "1. januar 2024",
      source: "Statistisk sentralbyrå",
      notes: ["1) Foreløpige tall."],
      header_rows: 1,
      columns: COLUMNS,
      rows: 3,
      with_sums: false,
      transposed: false,
      transpose_suggested: false,
      removed: {},
      symbols: {},
      filled_labels: 0,
      uncertain_cells: [],
      tsv: TSV,
      ...over,
    },
    ...extra,
  };
}

const analysis = (): Analysis => {
  const a = parseAnalysis(analysisReport());
  if (!a) throw new Error("analyse");
  return a;
};

// ---- argumentene

describe("argumentene fra skjermvalgene", () => {
  it("analyser tar bare filen", () => {
    expect(buildAnalyseRequest("/Saker/tall.xlsx")).toEqual({ command: "analyser", inputs: ["/Saker/tall.xlsx"], options: {} });
  });

  it("lag med foreslått ark og tabell sender ingen ark eller tabell", () => {
    const a = analysis();
    const c = choicesFromAnalysis(a);
    expect(c).toEqual({ sheet: "Befolkning", table: 2, withSums: false, transpose: false, removed: [] });
    expect(buildLagRequest("/Saker/tall.xlsx", c, a)).toEqual({ command: "lag", inputs: ["/Saker/tall.xlsx"], options: { table: 2 } });
  });

  it("sender ark bare når det ikke er det foreslåtte, og tabell bare når arket har flere", () => {
    const a = analysis();
    const boliger = withSheet(choicesFromAnalysis(a), a, "Boliger");
    expect(boliger).toMatchObject({ sheet: "Boliger", table: 1 });
    expect(buildLagRequest("/f.xlsx", boliger, a).options).toEqual({ sheet: "Boliger" });
    const first = withTable(choicesFromAnalysis(a), 1);
    expect(buildLagRequest("/f.xlsx", first, a).options).toEqual({ table: 1 });
  });

  it("sender sumrader, bytte, fjernede kolonner og CSV-fil, og bare det som er på", () => {
    const a = analysis();
    let c = choicesFromAnalysis(a);
    c = withSums(c, true);
    c = withTranspose(c, true);
    expect(buildLagRequest("/f.xlsx", c, a).options).toEqual({ table: 2, with_sums: true, transpose: true });
    c = removeColumn(removeColumn(c, 4), 2);
    const req = buildLagRequest("/f.xlsx", c, a, "/Saker/ut.csv");
    expect(req.options).toEqual({ table: 2, with_sums: true, transpose: true, remove_columns: [2, 4], csv_file: "/Saker/ut.csv" });
    expect(req.out_dir).toBeUndefined();
  });

  it("uten analyse sendes bare det brukeren har valgt", () => {
    expect(buildLagRequest("/f.csv", initialChoices(), null).options).toEqual({});
  });

  it("alle valgene finnes i hvitelisten i args.rs", () => {
    const a = analysis();
    let c = withTranspose(withSums(withSheet(choicesFromAnalysis(a), a, "Befolkning"), true), true);
    c = removeColumn(withTable(c, 1), 2);
    const keys = new Set([...Object.keys(buildLagRequest("/f.xlsx", { ...c, sheet: "Boliger" }, a, "/u.csv").options), ...Object.keys(buildLagRequest("/f.xlsx", c, a, "/u.csv").options)]);
    expect([...keys].sort()).toEqual(["csv_file", "remove_columns", "sheet", "table", "transpose", "with_sums"]);
    for (const k of keys) expect(argsRs, k).toContain(`"${k}"`);
    expect(argsRs).toContain('Some("analyser")');
    expect(argsRs).toContain('Some("lag")');
  });

  it("skjemaet har ingen felt i den felles skjermen og tar én fil av riktig type", () => {
    expect(schema.fields).toEqual([]);
    expect(schema.exactFiles).toBe(1);
    expect([...schema.extensions]).toEqual(["xlsx", "xlsm", "xls", "csv", "txt"]);
  });
});

describe("kolonner som fjernes", () => {
  it("telles fra 1, sorteres og har ingen dubletter", () => {
    let c = initialChoices();
    c = removeColumn(c, 3);
    c = removeColumn(c, 1);
    c = removeColumn(c, 3);
    expect(c.removed).toEqual([1, 3]);
    expect(removeColumn(c, 0).removed).toEqual([1, 3]);
    expect(removeColumn(c, 1.5).removed).toEqual([1, 3]);
  });

  it("kan angres én og én eller alle", () => {
    const c = removeColumn(removeColumn(removeColumn(initialChoices(), 2), 4), 5);
    expect(restoreColumn(c, 4).removed).toEqual([2, 5]);
    expect(restoreColumn(c, 9)).toBe(c);
    expect(restoreAllColumns(c).removed).toEqual([]);
  });

  it("nullstilles når tallene ville betydd noe annet: bytte, sumrader, ark og tabell", () => {
    const a = analysis();
    const c = removeColumn(choicesFromAnalysis(a), 3);
    expect(withTranspose(c, true).removed).toEqual([]);
    expect(withSums(c, true).removed).toEqual([]);
    expect(withTable(c, 1).removed).toEqual([]);
    expect(withSheet(c, a, "Boliger").removed).toEqual([]);
    // Samme avkrysning som før, ingen endring.
    expect(withSheet(c, a, "Finnes ikke")).toBe(c);
  });

  it("bytte og sumrader beholdes når arket byttes", () => {
    const a = analysis();
    const c = withSheet(withTranspose(withSums(choicesFromAnalysis(a), true), true), a, "Boliger");
    expect(c).toMatchObject({ withSums: true, transpose: true, sheet: "Boliger", table: 1 });
  });
});

describe("filnavn for CSV", () => {
  it("foreslår samme mappe og navn med .csv, på Mac og Windows", () => {
    expect(defaultCsvPath("/Users/kari/Saker/Tall 2024.xlsx")).toBe("/Users/kari/Saker/Tall 2024.csv");
    expect(defaultCsvPath("C:\\Users\\kari\\Saker\\Tall.xls")).toBe("C:\\Users\\kari\\Saker\\Tall.csv");
    expect(defaultCsvPath("/tall.xlsx")).toBe("/tall.csv");
  });

  it("legger på .csv bare når det mangler", () => {
    expect(ensureCsvExtension("/a/b")).toBe("/a/b.csv");
    expect(ensureCsvExtension("/a/b.CSV")).toBe("/a/b.CSV");
  });
});

// ---- rapporten

describe("rapporten", () => {
  it("leser analysen, og bare arkene med tabeller er et valg", () => {
    const a = analysis();
    expect(a.suggestedSheet).toBe("Befolkning");
    expect(a.xmlParser).toBe("defusedxml");
    expect(a.sheets).toHaveLength(3);
    expect(selectableSheets(a).map((s) => s.name)).toEqual(["Boliger", "Befolkning"]);
    expect(a.sheets[2]?.suggestedTable).toBe(2);
    expect(a.sheets[2]?.tables[1]).toMatchObject({ index: 2, range: "A4:E13", suggested: true });
  });

  it("gir null for en rapport som ikke er fra verktøyet", () => {
    expect(parseAnalysis(null)).toBeNull();
    expect(parseAnalysis({ summary: "x" })).toBeNull();
    expect(parseAnalysis({ datawrapper: { sheets: [{ name: 1, tables: [] }] } })).toBeNull();
    expect(parseAnalysis({ datawrapper: { sheets: [{ name: "A", tables: [{ range: "A1" }] }] } })).toBeNull();
    expect(parseMade(null)).toBeNull();
    expect(parseMade({ datawrapper: { tsv: 1, columns: [] } })).toBeNull();
    expect(parseMade({ datawrapper: { tsv: "", columns: [{ name: "a" }] } })).toBeNull();
  });

  it("leser tabellen: tittel, kilde, noter, kolonner, advarsler og TSV", () => {
    const m = parseMade(madeReport());
    expect(m).toMatchObject({
      sheet: "Befolkning",
      table: 2,
      tablesInSheet: 2,
      title: "Folkemengde per kommune",
      description: "1. januar 2024",
      source: "Statistisk sentralbyrå",
      notes: ["1) Foreløpige tall."],
      rows: 3,
      tsv: TSV,
      csv: null,
      xmlParser: "defusedxml",
      summary: "Tabellen har 3 rader og 4 kolonner og er klar for Datawrapper.",
    });
    expect(m?.warnings).toEqual(["Fjernet 1 sumrad. Velg «Ta med sumrader» for å beholde dem."]);
    expect(m?.columns.map((c) => c.name)).toEqual(["Kommune", "Kvinner", "Menn", "Endring (%)"]);
  });

  it("finner navnet CSV-filen faktisk fikk, også når den heter navn-2.csv", () => {
    const m = parseMade(madeReport({ csv: "/Saker/Tall-2.csv" }, { outputs: [{ path: "/Saker/Tall-2.csv", type: "csv" }] }));
    expect(m?.csv).toBe("/Saker/Tall-2.csv");
    const fromOutputs = parseMade(madeReport({}, { outputs: [{ path: "/Saker/Tall-3.csv", type: "csv" }] }));
    expect(fromOutputs?.csv).toBe("/Saker/Tall-3.csv");
  });

  it("deler TSV-en i rader, med tomme celler og uten tom siste rad", () => {
    expect(tsvRows(TSV)).toEqual([
      ["Kommune", "Kvinner", "Menn", "Endring (%)"],
      ["Askvoll", "1260", "1250", "0.4"],
      ["Bjørnevik", "2100", "2050", ""],
      ["Dalsfjord", "3300", "3190", "-1.2"],
    ]);
    expect(tsvRows("")).toEqual([]);
  });

  it("forhåndsvisningen viser overskrift og de første 50 radene, med antall totalt", () => {
    const rows = Array.from({ length: 120 }, (_, i) => `Sted ${i + 1}\t${i}\n`).join("");
    const m = parseMade(madeReport({ tsv: `Navn\tTall\n${rows}`, columns: COLUMNS.slice(0, 2), rows: 120 }));
    const p = previewOf(m as NonNullable<typeof m>);
    expect(PREVIEW_ROWS).toBe(50);
    expect(p.header).toEqual(["Navn", "Tall"]);
    expect(p.rows).toHaveLength(50);
    expect(p.rows[49]).toEqual(["Sted 50", "49"]);
    expect(p.totalRows).toBe(120);
    expect(p.columns.map((c) => c.numeric)).toEqual([false, true]);
  });

  it("tall høyrejusteres: forhåndsvisningen vet hvilke kolonner som er tall, også etter fjerning", () => {
    const m = parseMade(madeReport({ columns: COLUMNS.map((c) => (c.index === 2 ? { ...c, removed: true } : c)), tsv: "Kommune\tMenn\tEndring (%)\nA\t1\t0.4\n" }));
    const p = previewOf(m as NonNullable<typeof m>);
    expect(p.header).toEqual(["Kommune", "Menn", "Endring (%)"]);
    expect(p.columns.map((c) => [c.index, c.numeric])).toEqual([[1, false], [3, true], [4, true]]);
  });

  it("dropColumn viser tabellen uten kolonnen med en gang, med original nummerering", () => {
    const m = parseMade(madeReport()) as NonNullable<ReturnType<typeof parseMade>>;
    const d = dropColumn(m, 3);
    expect(d.tsv).toBe("Kommune\tKvinner\tEndring (%)\nAskvoll\t1260\t0.4\nBjørnevik\t2100\t\nDalsfjord\t3300\t-1.2\n");
    expect(keptColumns(d).map((c) => c.index)).toEqual([1, 2, 4]);
    expect(d.columns.find((c) => c.index === 3)?.removed).toBe(true);
    // Neste kolonne fjernes med riktig plass, ikke plassen i originalen.
    expect(dropColumn(d, 4).tsv).toBe("Kommune\tKvinner\nAskvoll\t1260\nBjørnevik\t2100\nDalsfjord\t3300\n");
    // Ukjent eller allerede fjernet kolonne endrer ingenting.
    expect(dropColumn(d, 3)).toBe(d);
    expect(dropColumn(d, 9)).toBe(d);
  });

  it("dropColumn lar siste kolonne stå", () => {
    const one = parseMade(madeReport({ columns: [COLUMNS[0]], tsv: "Kommune\nA\n" })) as NonNullable<ReturnType<typeof parseMade>>;
    expect(dropColumn(one, 1)).toBe(one);
  });
});

// ---- flyten

const inst = (id: string): InstalledView => ({ id, name: id, version: "1.0.0", bytes: 40_000_000, license: "AGPL-3.0-or-later" });

async function setup(platform: Parameters<typeof fakePlatform>[0] = {}) {
  const backend = new FakeJvBackend();
  backend.installedList = [inst("datawrapper")];
  const copied: string[] = [];
  const c = new JvController({
    backend,
    platform: fakePlatform({
      copyText: async (text) => {
        copied.push(text);
        return true;
      },
      ...platform,
    }),
    announce: () => undefined,
  });
  c.registerSchema(schema);
  await c.init();
  const dw = new DatawrapperController(c, c.platform);
  const runs = () => backend.callsOf("run").map((a) => a[1] as { command: string; inputs: string[]; options: Record<string, unknown> });
  /** Rust svarer på den siste jobben. */
  const answer = async (report: JvReport | null, over: Record<string, unknown> = {}) => {
    backend.runDone({ job_id: backend.nextJob - 1, id: "datawrapper", report, ...over });
    await flush();
  };
  return { backend, c, dw, copied, runs, answer };
}

describe("flyten på skjermen", () => {
  let env: Awaited<ReturnType<typeof setup>>;
  beforeEach(async () => {
    env = await setup();
  });

  async function ready() {
    env.c.addFiles("datawrapper", ["/Saker/Tall.xlsx"]);
    await flush();
    await env.answer(analysisReport());
    await env.answer(madeReport());
  }

  it("analyserer med en gang når filen kommer, og lager tabellen med det som foreslås", async () => {
    expect(env.dw.phase).toBe("empty");
    env.c.addFiles("datawrapper", ["/Saker/Tall.xlsx"]);
    await flush();
    expect(env.dw.phase).toBe("analysing");
    expect(env.runs()).toEqual([{ command: "analyser", inputs: ["/Saker/Tall.xlsx"], options: {} }]);
    await env.answer(analysisReport());
    expect(env.dw.phase).toBe("ready");
    expect(env.dw.making).toBe(true);
    expect(env.runs()[1]).toEqual({ command: "lag", inputs: ["/Saker/Tall.xlsx"], options: { table: 2 } });
    await env.answer(madeReport());
    expect(env.dw.making).toBe(false);
    expect(env.dw.made?.title).toBe("Folkemengde per kommune");
    expect(env.dw.ready).toBe(true);
  });

  it("ark og tabell er bare et valg når det er flere", async () => {
    await ready();
    expect(env.dw.sheets().map((s) => s.name)).toEqual(["Boliger", "Befolkning"]);
    expect(env.dw.tables()).toHaveLength(2);
    env.dw.setSheet("Boliger");
    expect(env.dw.tables()).toHaveLength(1);
    expect(env.dw.choices).toMatchObject({ sheet: "Boliger", table: 1 });
  });

  it("ett ark med én tabell gir ingen lister", async () => {
    env.c.addFiles("datawrapper", ["/Saker/Tall.csv"]);
    await flush();
    await env.answer(
      analysisReport({ suggested_sheet: "Tall", sheets: [{ name: "Tall", numbers: 9, suggested: true, suggested_table: 1, tables: [tableSummary(1, "A1:C9", { suggested: true })] }] }),
    );
    expect(env.dw.sheets()).toHaveLength(1);
    expect(env.dw.tables()).toHaveLength(1);
    expect(env.runs()[1]?.options).toEqual({});
  });

  it("hver endring kjører lag på nytt", async () => {
    await ready();
    env.dw.setWithSums(true);
    expect(env.runs()[2]?.options).toEqual({ table: 2, with_sums: true });
    await env.answer(madeReport({ with_sums: true }));
    env.dw.setTranspose(true);
    expect(env.runs()[3]?.options).toEqual({ table: 2, with_sums: true, transpose: true });
    await env.answer(madeReport({ transposed: true }));
    env.dw.setSheet("Boliger");
    expect(env.runs()[4]?.options).toEqual({ sheet: "Boliger", with_sums: true, transpose: true });
  });

  it("kolonnen forsvinner med en gang, lag får riktig nummer, og den kan angres", async () => {
    await ready();
    env.dw.removeColumn(3);
    expect(env.dw.made?.tsv.split("\n")[0]).toBe("Kommune\tKvinner\tEndring (%)");
    expect(env.runs()[2]?.options).toEqual({ table: 2, remove_columns: [3] });
    await env.answer(madeReport({ columns: COLUMNS.map((c) => (c.index === 3 ? { ...c, removed: true } : c)), tsv: "Kommune\tKvinner\tEndring (%)\nA\t1\t0.4\n" }));
    env.dw.removeColumn(1);
    expect(env.runs()[3]?.options).toEqual({ table: 2, remove_columns: [1, 3] });
    await env.answer(madeReport({ columns: COLUMNS.map((c) => (c.index !== 2 && c.index !== 4 ? { ...c, removed: true } : c)), tsv: "Kvinner\tEndring (%)\n1\t0.4\n" }));
    env.dw.restoreColumn(3);
    expect(env.dw.choices.removed).toEqual([1]);
    expect(env.runs()[4]?.options).toEqual({ table: 2, remove_columns: [1] });
  });

  it("den siste kolonnen kan ikke fjernes", async () => {
    await ready();
    await env.answer(null);
    env.c.newJob("datawrapper");
    env.c.addFiles("datawrapper", ["/Saker/En.csv"]);
    await flush();
    await env.answer(analysisReport());
    await env.answer(madeReport({ columns: [COLUMNS[0]], tsv: "Kommune\nA\n" }));
    expect(env.dw.canRemoveColumn()).toBe(false);
    const before = env.runs().length;
    env.dw.removeColumn(1);
    expect(env.runs()).toHaveLength(before);
  });

  it("endringer mens lag kjører, samles og kjøres rett etterpå, uten å miste valgene", async () => {
    await ready();
    env.dw.setWithSums(true);
    const n = env.runs().length;
    env.dw.setTranspose(true);
    env.dw.setWithSums(false);
    expect(env.runs()).toHaveLength(n);
    expect(env.dw.ready).toBe(false);
    await env.answer(madeReport());
    expect(env.runs()).toHaveLength(n + 1);
    expect(env.runs()[n]?.options).toEqual({ table: 2, transpose: true });
  });

  it("endring av bytte og sumrader nullstiller fjernede kolonner", async () => {
    await ready();
    env.dw.removeColumn(2);
    await env.answer(madeReport());
    env.dw.setTranspose(true);
    expect(env.dw.choices.removed).toEqual([]);
    expect(env.runs().at(-1)?.options).toEqual({ table: 2, transpose: true });
  });

  it("en ny fil starter på nytt, og gamle svar gjelder ikke lenger", async () => {
    await ready();
    env.c.addFiles("datawrapper", ["/Saker/Annen.xls"]);
    await flush();
    expect(env.dw.phase).toBe("analysing");
    expect(env.dw.made).toBeNull();
    expect(env.runs().at(-1)).toEqual({ command: "analyser", inputs: ["/Saker/Annen.xls"], options: {} });
  });

  it("filer som ikke støttes, gir en melding og ingen kjøring", async () => {
    env.c.addFiles("datawrapper", ["/Saker/Brev.docx"]);
    await flush();
    expect(env.dw.phase).toBe("empty");
    expect(env.runs()).toHaveLength(0);
    expect(env.c.session("datawrapper").notice).toEqual({ kind: "unsupported", names: ["Brev.docx"] });
  });

  it("feil fra verktøyet vises på vanlig norsk, og feil i analysen gir «Velg annen fil»", async () => {
    env.c.addFiles("datawrapper", ["/Saker/Passord.xlsx"]);
    await flush();
    await env.answer(null, { outcome: "failed", error: { code: "tool_failed", exit_code: 1 }, message: "Filen er passordbeskyttet. Fjern passordet i Excel og prøv igjen." });
    expect(env.dw.phase).toBe("failed");
    expect(env.dw.error?.kind).toBe("analyse");
    expect(env.dw.error?.run.message).toBe("Filen er passordbeskyttet. Fjern passordet i Excel og prøv igjen.");
  });

  it("en rapport uten tabell gir feil, ikke en tom skjerm", async () => {
    env.c.addFiles("datawrapper", ["/Saker/Tom.xlsx"]);
    await flush();
    await env.answer({ summary: "", datawrapper: {} });
    expect(env.dw.phase).toBe("failed");
    expect(env.dw.error?.run.error).toEqual({ code: "report_invalid" });
  });

  it("feil i lag beholder valgene og viser feilen ved siden av forhåndsvisningen", async () => {
    await ready();
    env.dw.setWithSums(true);
    await env.answer(null, { outcome: "failed", error: { code: "tool_failed", exit_code: 1 }, message: "Tabellen er for stor til å kopieres til Datawrapper (mer enn 24 MB)." });
    expect(env.dw.phase).toBe("ready");
    expect(env.dw.error?.kind).toBe("make");
    expect(env.dw.made?.title).toBe("Folkemengde per kommune");
    env.dw.setWithSums(false);
    expect(env.dw.error).toBeNull();
  });

  it("avvist forespørsel fra Rust (ugyldig valg) gir en norsk feil, ikke et unntak", async () => {
    await ready();
    env.backend.runError = { code: "invalid_args", reason: "option_value" };
    env.dw.setWithSums(true);
    await flush();
    expect(env.dw.error?.kind).toBe("make");
    expect(env.dw.error?.run.error).toEqual({ code: "invalid_args", reason: "option_value" });
    expect(t.jvErrors.invalid_args({ code: "invalid_args", reason: "option_value" }).title).not.toBe("");
  });
});

describe("kopiering og lagring", () => {
  it("«Kopier til Datawrapper» kopierer TSV-en uendret og bekrefter", async () => {
    const env = await setup();
    env.c.addFiles("datawrapper", ["/Saker/Tall.xlsx"]);
    await flush();
    await env.answer(analysisReport());
    await env.answer(madeReport());
    vi.useFakeTimers();
    try {
      const ok = await env.dw.copyTable();
      expect(ok).toBe(true);
      expect(env.copied).toEqual([TSV]);
      expect(env.dw.feedback).toEqual({ key: "tsv", ok: true });
      await vi.advanceTimersByTimeAsync(FEEDBACK_MS + 1);
      expect(env.dw.feedback).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("tittel, kilde, beskrivelse og noter kopieres hver for seg", async () => {
    const env = await setup();
    env.c.addFiles("datawrapper", ["/Saker/Tall.xlsx"]);
    await flush();
    await env.answer(analysisReport());
    await env.answer(madeReport({ notes: ["1) A.", "2) B."] }));
    await env.dw.copy("title", env.dw.made?.title ?? "");
    await env.dw.copy("source", env.dw.made?.source ?? "");
    await env.dw.copy("notes", (env.dw.made?.notes ?? []).join("\n"));
    expect(env.copied).toEqual(["Folkemengde per kommune", "Statistisk sentralbyrå", "1) A.\n2) B."]);
  });

  it("melder at kopieringen mislyktes i stedet for å late som", async () => {
    const env = await setup({ copyText: async () => false });
    expect(await env.dw.copy("tsv", "x")).toBe(false);
    expect(env.dw.feedback).toEqual({ key: "tsv", ok: false });
    const thrown = await setup({
      copyText: async () => {
        throw new Error("nei");
      },
    });
    expect(await thrown.dw.copy("tsv", "x")).toBe(false);
  });

  it("kopierer ikke mens forhåndsvisningen oppdateres", async () => {
    const env = await setup();
    env.c.addFiles("datawrapper", ["/Saker/Tall.xlsx"]);
    await flush();
    await env.answer(analysisReport());
    expect(env.dw.ready).toBe(false);
    await env.answer(madeReport());
    expect(env.dw.ready).toBe(true);
    env.dw.setWithSums(true);
    expect(env.dw.ready).toBe(false);
  });

  it("«Lagre som CSV» åpner lagre-dialogen og kjører lag med csv_file, og viser navnet filen fikk", async () => {
    const dialogs: unknown[] = [];
    const env = await setup({
      pickSavePath: async (o) => {
        dialogs.push(o);
        return "/Saker/Tall";
      },
    });
    env.c.addFiles("datawrapper", ["/Saker/Tall.xlsx"]);
    await flush();
    await env.answer(analysisReport());
    await env.answer(madeReport());
    await env.dw.saveCsv();
    expect(dialogs).toEqual([{ title: t.jv.datawrapper.saveDialogTitle, defaultPath: "/Saker/Tall.csv", extension: "csv", filterName: "CSV" }]);
    expect(env.runs().at(-1)?.options).toEqual({ table: 2, csv_file: "/Saker/Tall.csv" });
    expect(env.dw.saving).toBe(true);
    await env.answer(madeReport({ csv: "/Saker/Tall-2.csv" }, { outputs: [{ path: "/Saker/Tall-2.csv", type: "csv" }] }));
    expect(env.dw.saving).toBe(false);
    expect(env.dw.savedPath).toBe("/Saker/Tall-2.csv");
    expect(env.dw.savedName()).toBe("Tall-2.csv");
    // Å endre valg fjerner meldingen, siden den ikke gjelder lenger.
    env.dw.setWithSums(true);
    expect(env.dw.savedName()).toBeNull();
  });

  it("avbrutt lagre-dialog gjør ingenting", async () => {
    const env = await setup({ pickSavePath: async () => null });
    env.c.addFiles("datawrapper", ["/Saker/Tall.xlsx"]);
    await flush();
    await env.answer(analysisReport());
    await env.answer(madeReport());
    const n = env.runs().length;
    await env.dw.saveCsv();
    expect(env.runs()).toHaveLength(n);
  });

  it("feil ved lagring vises, og forhåndsvisningen blir stående", async () => {
    const env = await setup({ pickSavePath: async () => "/Saker/Tall.csv" });
    env.c.addFiles("datawrapper", ["/Saker/Tall.xlsx"]);
    await flush();
    await env.answer(analysisReport());
    await env.answer(madeReport());
    await env.dw.saveCsv();
    await env.answer(null, { outcome: "failed", error: { code: "tool_failed", exit_code: 1 }, message: "Mangler skrivetilgang til mappen for CSV-filen. Velg en annen mappe." });
    expect(env.dw.error?.kind).toBe("save");
    expect(env.dw.saving).toBe(false);
    expect(env.dw.savedPath).toBeNull();
    expect(env.dw.made).not.toBeNull();
  });
});
