// Bygger eksportforespørselen til Rust. Rust skriver filen; her bestemmes bare
// hva som sendes: format, tidskoder, tekster til toppen og dato.

import type { ExportFormat, ExportRequest, Malform, Segment, Stil } from "../tools/transkribering/api";
import { t } from "../i18n/nb";
import { formatDate } from "./format";

export type SaveKind = "docx" | "txt-time" | "txt-plain" | "srt" | "vtt";

export interface SaveOption {
  kind: SaveKind;
  format: ExportFormat;
  timestamps: boolean;
}

/** Valgene i «Lagre som», i den rekkefølgen de vises. */
export const SAVE_OPTIONS: readonly SaveOption[] = [
  { kind: "docx", format: "docx", timestamps: true },
  { kind: "txt-time", format: "txt", timestamps: true },
  { kind: "txt-plain", format: "txt", timestamps: false },
  { kind: "srt", format: "srt", timestamps: false },
  { kind: "vtt", format: "vtt", timestamps: false },
];

export function saveOption(kind: SaveKind): SaveOption {
  const o = SAVE_OPTIONS.find((x) => x.kind === kind);
  if (!o) throw new Error("unknown save kind");
  return o;
}

export interface ExportInput {
  audioPath: string;
  option: SaveOption;
  segments: readonly Segment[];
  malform: Malform;
  stil: Stil;
  modelId: string;
  now: Date;
  /** Valgt sted fra «Lagre som»-dialogen. Utelatt: standard ved siden av lydfilen. */
  targetPath?: string | null;
  /** Bare etter at brukeren har bekreftet overskriving (eller valgt stedet selv i dialogen). */
  overwrite?: boolean;
}

export function buildExportRequest(i: ExportInput): ExportRequest {
  return {
    audio_path: i.audioPath,
    target_path: i.targetPath ?? null,
    format: i.option.format,
    timestamps: i.option.timestamps,
    overwrite: i.overwrite ?? false,
    segments: i.segments.map((s) => ({ start_ms: s.start_ms, end_ms: s.end_ms, text: s.text })),
    malform: i.malform,
    stil: i.stil,
    model_id: i.modelId,
    date: formatDate(i.now),
    labels: { ...t.headerLabels },
  };
}
