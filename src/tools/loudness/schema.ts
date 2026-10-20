// Lydnivå: podcast eller kringkasting.

import { t } from "../../i18n/nb";
import type { ToolSchema } from "../jv/schema";

const F = t.jv.fields.loudness;

export const schema: ToolSchema = {
  id: "loudness",
  icon: "loudness",
  extensions: ["wav", "mp3", "m4a", "flac", "mp4", "mov", "m4v", "mkv"],
  fields: [
    {
      kind: "choice",
      id: "target",
      legend: F.legend,
      default: "podcast",
      options: [
        { id: "podcast", label: F.podcast.label, help: F.podcast.help, options: { target: "podcast" } },
        { id: "broadcast", label: F.broadcast.label, help: F.broadcast.help, options: { target: "broadcast" } },
      ],
    },
  ],
};
