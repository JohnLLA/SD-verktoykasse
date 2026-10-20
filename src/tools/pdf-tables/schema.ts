// Tabeller fra PDF: sider, sammenslåing og csv.

import { t } from "../../i18n/nb";
import type { ToolSchema } from "../jv/schema";

const F = t.jv.fields["pdf-tables"];

/** `3-7` eller `1,4-5` (samme mønster som Rust godtar). */
export const PAGES_PATTERN = /^\d{1,5}(-\d{1,5})?(,\d{1,5}(-\d{1,5})?)*$/;

export const schema: ToolSchema = {
  id: "pdf-tables",
  icon: "table",
  extensions: ["pdf"],
  fields: [
    { kind: "text", id: "pages", legend: F.pages.legend, optionKey: "pages", placeholder: F.pages.placeholder, pattern: PAGES_PATTERN, invalidHelp: F.pages.invalid, help: F.pages.help },
    { kind: "toggle", id: "merge", label: F.merge.label, optionKey: "merge", default: false, help: F.merge.help },
    { kind: "toggle", id: "csv", label: F.csv.label, optionKey: "csv", default: false },
  ],
};
