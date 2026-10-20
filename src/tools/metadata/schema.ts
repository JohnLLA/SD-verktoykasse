// Metadata: «Vis» (ingen utfiler) og «Fjern» (vasket kopi).

import { t } from "../../i18n/nb";
import type { ToolSchema } from "../jv/schema";

const F = t.jv.fields.metadata;

export const schema: ToolSchema = {
  id: "metadata",
  icon: "metadata",
  extensions: ["jpg", "jpeg", "png", "heic", "pdf", "docx", "xlsx", "pptx"],
  acceptsFolders: true,
  fields: [
    {
      kind: "choice",
      id: "mode",
      legend: F.legend,
      default: "show",
      options: [
        { id: "show", label: F.show.label, help: F.show.help, command: "vis", noOutDir: true },
        { id: "clean", label: F.clean.label, help: F.clean.help, command: "vask" },
      ],
    },
  ],
};
