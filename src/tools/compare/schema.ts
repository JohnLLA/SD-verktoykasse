// Sammenlign versjoner: to filer, to valg.

import { t } from "../../i18n/nb";
import type { ToolSchema } from "../jv/schema";

const F = t.jv.fields.compare;

export const schema: ToolSchema = {
  id: "compare",
  icon: "compare",
  extensions: ["txt", "md", "docx", "pdf"],
  exactFiles: 2,
  fields: [
    { kind: "toggle", id: "ignore_whitespace", label: F.ignoreWhitespace.label, optionKey: "ignore_whitespace", default: true, help: F.ignoreWhitespace.help },
    { kind: "toggle", id: "ignore_case", label: F.ignoreCase.label, optionKey: "ignore_case", default: false, help: F.ignoreCase.help },
  ],
};
