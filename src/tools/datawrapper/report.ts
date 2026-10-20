// Rapporten fra `jv datawrapper analyser` og `jv datawrapper lag`, lest til
// typer skjermen kan bruke. Rene funksjoner, uten Tauri og uten DOM.
// Formatet står i sidecar/jv/verktoy/datawrapper (core.py: `analyse` og `make`).
// Ukjent eller mangelfull rapport gir `null`, ikke et unntak.

import type { JvReport } from "../jv/api";
import { outputPath } from "../jv/paths";

/** Forhåndsvisningen viser så mange rader. */
export const PREVIEW_ROWS = 50;

export interface TableInfo {
  /** Tabellnummer i arket, fra 1. */
  index: number;
  range: string;
  suggested: boolean;
  rows: number;
  columns: number;
  transposeSuggested: boolean;
}

export interface SheetInfo {
  name: string;
  suggested: boolean;
  /** Tabellen verktøyet foreslår i dette arket (fra 1), eller `null`. */
  suggestedTable: number | null;
  tables: TableInfo[];
}

export interface Analysis {
  sheets: SheetInfo[];
  suggestedSheet: string | null;
  format: string;
  /** Hvilken XML-leser verktøyet brukte (bare xlsx). Vises ikke, men beholdes. */
  xmlParser: string | null;
}

export interface ColumnInfo {
  /** Nummer fra 1 i tabellen etter sumfjerning og bytte, før kolonner fjernes. */
  index: number;
  name: string;
  numeric: boolean;
  sum: boolean;
  removed: boolean;
}

export interface MadeTable {
  sheet: string;
  table: number;
  tablesInSheet: number;
  range: string;
  title: string;
  description: string;
  source: string;
  notes: string[];
  /** Alle kolonnene, også de som er fjernet. */
  columns: ColumnInfo[];
  rows: number;
  withSums: boolean;
  transposed: boolean;
  transposeSuggested: boolean;
  /** Teksten som kopieres: tabseparert, med én overskriftsrad og linjeskift etter hver rad. */
  tsv: string;
  /** Stien til CSV-filen, hvis `--csv` var med. Kan hete `navn-2.csv`. */
  csv: string | null;
  xmlParser: string | null;
  summary: string;
  warnings: string[];
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const num = (v: unknown, d = 0): number => (typeof v === "number" && Number.isFinite(v) ? v : d);
const strList = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

function data(report: JvReport | null): Record<string, unknown> | null {
  const d = report?.datawrapper;
  return isObj(d) ? d : null;
}

export function parseAnalysis(report: JvReport | null): Analysis | null {
  const d = data(report);
  if (!d || !Array.isArray(d.sheets)) return null;
  const sheets: SheetInfo[] = [];
  for (const s of d.sheets) {
    if (!isObj(s) || typeof s.name !== "string" || !Array.isArray(s.tables)) return null;
    const tables: TableInfo[] = [];
    for (const t of s.tables) {
      if (!isObj(t) || typeof t.index !== "number") return null;
      tables.push({
        index: t.index,
        range: str(t.range),
        suggested: t.suggested === true,
        rows: num(t.rows),
        columns: num(t.columns),
        transposeSuggested: t.transpose_suggested === true,
      });
    }
    sheets.push({
      name: s.name,
      suggested: s.suggested === true,
      suggestedTable: typeof s.suggested_table === "number" ? s.suggested_table : null,
      tables,
    });
  }
  return {
    sheets,
    suggestedSheet: typeof d.suggested_sheet === "string" ? d.suggested_sheet : null,
    format: str(d.format),
    xmlParser: typeof d.xml_parser === "string" ? d.xml_parser : null,
  };
}

/** Arkene som har minst én tabell. Skjulte ark og tomme ark er ikke et valg. */
export function selectableSheets(a: Analysis): SheetInfo[] {
  return a.sheets.filter((s) => s.tables.length > 0);
}

export function parseMade(report: JvReport | null): MadeTable | null {
  const d = data(report);
  if (!d || typeof d.tsv !== "string" || !Array.isArray(d.columns)) return null;
  const columns: ColumnInfo[] = [];
  for (const c of d.columns) {
    if (!isObj(c) || typeof c.index !== "number") return null;
    columns.push({ index: c.index, name: str(c.name), numeric: c.numeric === true, sum: c.sum === true, removed: c.removed === true });
  }
  const outputs = Array.isArray(report?.outputs) ? (report?.outputs as unknown[]) : [];
  const csvEntry = outputs.find((o) => isObj(o) && o.type === "csv");
  return {
    sheet: str(d.sheet),
    table: num(d.table, 1),
    tablesInSheet: num(d.tables_in_sheet, 1),
    range: str(d.range),
    title: str(d.title),
    description: str(d.description),
    source: str(d.source),
    notes: strList(d.notes),
    columns,
    rows: num(d.rows),
    withSums: d.with_sums === true,
    transposed: d.transposed === true,
    transposeSuggested: d.transpose_suggested === true,
    tsv: d.tsv,
    csv: typeof d.csv === "string" ? d.csv : outputPath(csvEntry),
    xmlParser: typeof d.xml_parser === "string" ? d.xml_parser : null,
    summary: str(report?.summary),
    warnings: strList(report?.warnings),
  };
}

/** TSV-en som rader av celler. Siste linjeskift gir ingen tom rad. */
export function tsvRows(tsv: string): string[][] {
  const lines = tsv.split("\n");
  if (lines[lines.length - 1] === "") lines.pop();
  return lines.map((l) => l.split("\t"));
}

/** Kolonnene som er med i TSV-en, i samme rekkefølge som cellene i hver rad. */
export function keptColumns(m: Pick<MadeTable, "columns">): ColumnInfo[] {
  return m.columns.filter((c) => !c.removed);
}

export interface Preview {
  header: string[];
  rows: string[][];
  /** Rader i tabellen, ikke bare de som vises. */
  totalRows: number;
  /** Kolonnene i forhåndsvisningen: originalt nummer og om de er tall. */
  columns: ColumnInfo[];
}

/** Overskriftsrad, de første `limit` radene og hvilke kolonner som er tall. */
export function previewOf(m: MadeTable, limit = PREVIEW_ROWS): Preview {
  const all = tsvRows(m.tsv);
  const [header = [], ...rows] = all;
  return { header, rows: rows.slice(0, limit), totalRows: rows.length, columns: keptColumns(m) };
}

/**
 * Tabellen uten kolonne `index` (nummer fra 1 før fjerning), slik `lag` ville
 * gitt den. Brukes til å vise endringen med en gang, før `lag` har svart.
 * Samme tabell hvis kolonnen ikke er med, eller hvis den er den siste.
 */
export function dropColumn(m: MadeTable, index: number): MadeTable {
  const kept = keptColumns(m);
  const pos = kept.findIndex((c) => c.index === index);
  if (pos < 0 || kept.length <= 1) return m;
  const rows = tsvRows(m.tsv).map((r) => r.filter((_, i) => i !== pos));
  return {
    ...m,
    columns: m.columns.map((c) => (c.index === index ? { ...c, removed: true } : c)),
    tsv: rows.map((r) => `${r.join("\t")}\n`).join(""),
  };
}
