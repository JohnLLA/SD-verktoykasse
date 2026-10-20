// Verktøyregisteret. Menyen i skallet lages herfra. Et nytt verktøy legges til
// med én linje her (og én i `src-tauri/src/tools/mod.rs`) og i en gruppe under.

import { t } from "../i18n/nb";
import { compare } from "./compare";
import { datawrapper } from "./datawrapper";
import { keyframes } from "./keyframes";
import { loudness } from "./loudness";
import { metadata } from "./metadata";
import { nynorsk } from "./nynorsk";
import { ocr } from "./ocr";
import { pdfTables } from "./pdf-tables";
import { redact } from "./redact";
import { subtitles } from "./subtitles";
import { transkribering } from "./transkribering";
import type { ToolDefinition } from "./types";

export const tools: readonly ToolDefinition[] = [
  transkribering,
  keyframes,
  loudness,
  subtitles,
  compare,
  metadata,
  pdfTables,
  datawrapper,
  ocr,
  redact,
  nynorsk,
];

/** Gruppene i venstremenyen. Transkribering står først. */
export const menuGroups: readonly { label: string; ids: readonly string[] }[] = [
  { label: t.jv.nav.groups.audio, ids: ["transkribering", "keyframes", "loudness", "subtitles"] },
  { label: t.jv.nav.groups.documents, ids: ["compare", "metadata", "pdf-tables", "datawrapper", "ocr", "redact"] },
  { label: t.jv.nav.groups.language, ids: ["nynorsk"] },
];
