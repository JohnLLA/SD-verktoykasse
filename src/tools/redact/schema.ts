// Sladding: én PDF, valgfri liste med egne ord, to steg (Finn og Sladd).

import { t } from "../../i18n/nb";
import type { ToolSchema } from "../jv/schema";

const F = t.jv.fields.redact;

export const schema: ToolSchema = {
  id: "redact",
  icon: "redact",
  extensions: ["pdf"],
  exactFiles: 1,
  twoStep: true,
  fields: [
    { kind: "file", id: "terms", legend: F.terms.legend, optionKey: "terms_file", extensions: ["txt"], filterName: F.terms.filterName, dialogTitle: F.terms.dialogTitle, help: F.terms.help },
  ],
};
