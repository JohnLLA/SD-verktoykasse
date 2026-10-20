// Tekstene for ett verktøy (fra språkfilen), brukt av de felles skjermene.

import { t } from "../../i18n/nb";
import type { JvToolId } from "./api";

export interface ToolTexts {
  name: string;
  description: string;
  formats: string;
  dropTitle: string;
  dialogTitle: string;
  filterName: string;
}

export function toolTexts(id: JvToolId): ToolTexts {
  return t.jv.tools[id];
}
