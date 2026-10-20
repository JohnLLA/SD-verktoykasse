// Søkbare PDF-er: ett valg.

import { t } from "../../i18n/nb";
import type { ToolSchema } from "../jv/schema";

const F = t.jv.fields.ocr;

export const schema: ToolSchema = {
  id: "ocr",
  icon: "ocr",
  extensions: ["pdf", "jpg", "jpeg", "png", "tif", "tiff"],
  acceptsFolders: true,
  fields: [{ kind: "toggle", id: "text", label: F.text.label, optionKey: "text", default: false, help: F.text.help }],
};
