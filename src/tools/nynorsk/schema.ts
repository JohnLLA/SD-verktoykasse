// Bokmål ↔ nynorsk: retning. Resultatet er alltid et utkast.

import { t } from "../../i18n/nb";
import type { ToolSchema } from "../jv/schema";

const F = t.jv.fields.nynorsk;

export const schema: ToolSchema = {
  id: "nynorsk",
  icon: "language",
  extensions: ["txt", "md", "docx"],
  draftNotice: true,
  fields: [
    {
      kind: "choice",
      id: "to",
      legend: F.legend,
      default: "nn",
      options: [
        { id: "nn", label: F.toNynorsk.label, help: F.toNynorsk.help, options: { to: "nn" } },
        { id: "nb", label: F.toBokmal.label, help: F.toBokmal.help, options: { to: "nb" } },
      ],
    },
  ],
};
