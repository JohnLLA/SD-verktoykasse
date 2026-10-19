// Skjemaet som styrer det felles skjermbildet for et jv-verktøy: hvilke filer
// det tar imot og hvilke valg brukeren har. Hvert verktøy har sitt eget skjema
// i `src/tools/<id>/`. Rene data og funksjoner, uten Tauri og uten DOM.
//
// Valgene blir til `RunRequest.options` (Rust: `args.rs` har hvitelisten, så
// alt som ikke står der, avvises uansett).

import type { JvToolId, RunRequest } from "./api";

export type OptionValue = string | number | boolean;
export type Values = Record<string, OptionValue>;

export type MenuGroupId = "audio" | "documents" | "language";

/** Ett valg i en gruppe med segmentknapper. */
export interface ChoiceOption {
  id: string;
  label: string;
  /** Forklaring som vises under gruppen når valget er på. */
  help?: string;
  /** Underkommando (`vis`/`vask`, `finn`/`sladd`). */
  command?: string;
  /** Valg som sendes til verktøyet når dette er på. */
  options?: Record<string, OptionValue>;
  /** Verktøyet lager ingen utfiler og trenger ingen utmappe (metadata «vis»). */
  noOutDir?: boolean;
}

export interface ChoiceField {
  kind: "choice";
  id: string;
  legend: string;
  options: readonly ChoiceOption[];
  default: string;
  showIf?: (v: Values) => boolean;
}

export interface NumberField {
  kind: "number";
  id: string;
  legend: string;
  /** Navnet på valget i `RunRequest.options`. */
  optionKey: string;
  min: number;
  max: number;
  step: number;
  default: number;
  unit?: string;
  help?: string;
  showIf?: (v: Values) => boolean;
}

export interface ToggleField {
  kind: "toggle";
  id: string;
  label: string;
  optionKey: string;
  default: boolean;
  help?: string;
  showIf?: (v: Values) => boolean;
}

export interface TextField {
  kind: "text";
  id: string;
  legend: string;
  optionKey: string;
  placeholder: string;
  /** Tomt felt sender ingenting. */
  pattern: RegExp;
  invalidHelp: string;
  help?: string;
  showIf?: (v: Values) => boolean;
}

/** En valgfri fil (for eksempel en liste med egne ord). */
export interface FileField {
  kind: "file";
  id: string;
  legend: string;
  optionKey: string;
  extensions: string[];
  filterName: string;
  dialogTitle: string;
  help?: string;
  showIf?: (v: Values) => boolean;
}

export type Field = ChoiceField | NumberField | ToggleField | TextField | FileField;

export interface ToolSchema {
  id: JvToolId;
  icon: string;
  /** Filendelser uten punktum, små bokstaver. */
  extensions: readonly string[];
  /** Verktøyet tar også mapper (metadata, ocr). */
  acceptsFolders?: boolean;
  /** Nøyaktig så mange filer (sammenligning: 2, sladding: 1). */
  exactFiles?: number;
  fields: readonly Field[];
  /** «Utkast – må leses over» står alltid i resultatet (nynorsk). */
  draftNotice?: boolean;
  /** To steg: «Finn» og «Sladd». */
  twoStep?: boolean;
}

export function fieldVisible(f: Field, v: Values): boolean {
  return !f.showIf || f.showIf(v);
}

export function defaultValues(schema: ToolSchema): Values {
  const v: Values = {};
  for (const f of schema.fields) {
    if (f.kind === "file") continue;
    if (f.kind === "text") v[f.id] = "";
    else v[f.id] = f.default;
  }
  return v;
}

/** Valget som er på i en gruppe. */
export function selectedOption(f: ChoiceField, v: Values): ChoiceOption {
  const id = v[f.id];
  return f.options.find((o) => o.id === id) ?? (f.options[0] as ChoiceOption);
}

/** Underkommandoen valgene gir, eller `undefined`. */
export function commandFor(schema: ToolSchema, v: Values): string | undefined {
  for (const f of schema.fields) {
    if (f.kind === "choice" && fieldVisible(f, v)) {
      const c = selectedOption(f, v).command;
      if (c) return c;
    }
  }
  return undefined;
}

/** Trenger kjøringen en utmappe? */
export function needsOutDir(schema: ToolSchema, v: Values): boolean {
  for (const f of schema.fields) {
    if (f.kind === "choice" && fieldVisible(f, v) && selectedOption(f, v).noOutDir) return false;
  }
  return true;
}

export function textValid(f: TextField, value: string): boolean {
  return value.trim() === "" || f.pattern.test(value.trim());
}

/** Er alle valgene gyldige (tallene innenfor grensene, tekstfeltene i riktig form)? */
export function valuesValid(schema: ToolSchema, v: Values): boolean {
  for (const f of schema.fields) {
    if (!fieldVisible(f, v)) continue;
    if (f.kind === "number") {
      const n = v[f.id];
      if (typeof n !== "number" || !Number.isFinite(n) || n < f.min || n > f.max) return false;
    } else if (f.kind === "text") {
      if (!textValid(f, String(v[f.id] ?? ""))) return false;
    }
  }
  return true;
}

/**
 * Gjør valgene om til en `RunRequest`. `extra` er valg som ikke kommer fra
 * skjemaet (filen med egne ord, planfilen i redact).
 */
export function buildRunRequest(
  schema: ToolSchema,
  values: Values,
  inputs: string[],
  outDir: string | null,
  extra: Record<string, OptionValue> = {},
  commandOverride?: string,
): RunRequest {
  const options: Record<string, OptionValue> = {};
  for (const f of schema.fields) {
    if (!fieldVisible(f, values)) continue;
    const v = values[f.id];
    switch (f.kind) {
      case "choice":
        Object.assign(options, selectedOption(f, values).options ?? {});
        break;
      case "number":
        if (typeof v === "number") options[f.optionKey] = v;
        break;
      case "toggle":
        options[f.optionKey] = v === true;
        break;
      case "text":
        if (typeof v === "string" && v.trim() !== "") options[f.optionKey] = v.trim();
        break;
      case "file":
        break;
    }
  }
  Object.assign(options, extra);
  const command = commandOverride ?? commandFor(schema, values);
  const req: RunRequest = { inputs, options };
  if (command) req.command = command;
  if (outDir && needsOutDir(schema, values)) req.out_dir = outDir;
  return req;
}
