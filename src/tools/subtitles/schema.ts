// Teksting: linjelengde og antall linjer.

import { t } from "../../i18n/nb";
import type { ToolSchema } from "../jv/schema";

const F = t.jv.fields.subtitles;

export const schema: ToolSchema = {
  id: "subtitles",
  icon: "subtitles",
  extensions: ["json"],
  fields: [
    {
      kind: "choice",
      id: "length",
      legend: F.lengthLegend,
      default: "normal",
      options: [
        { id: "short", label: F.short.label, help: F.short.help, options: { max_chars: 32 } },
        { id: "normal", label: F.normal.label, help: F.normal.help, options: { max_chars: 42 } },
        { id: "long", label: F.long.label, help: F.long.help, options: { max_chars: 60 } },
      ],
    },
    {
      kind: "choice",
      id: "lines",
      legend: F.linesLegend,
      default: "two",
      options: [
        { id: "one", label: F.one.label, options: { max_lines: 1 } },
        { id: "two", label: F.two.label, options: { max_lines: 2 } },
      ],
    },
  ],
};
