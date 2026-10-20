// Stillbilder fra video: fast intervall eller ved klipp.

import { t } from "../../i18n/nb";
import type { ToolSchema } from "../jv/schema";

const F = t.jv.fields.keyframes;

export const schema: ToolSchema = {
  id: "keyframes",
  icon: "keyframes",
  extensions: ["mp4", "mov", "mkv", "m4v", "avi", "webm"],
  fields: [
    {
      kind: "choice",
      id: "mode",
      legend: F.modeLegend,
      default: "every",
      options: [
        { id: "every", label: F.every.label, help: F.every.help },
        { id: "scenes", label: F.scenes.label, help: F.scenes.help },
      ],
    },
    {
      kind: "number",
      id: "every_seconds",
      legend: F.seconds.legend,
      optionKey: "every_seconds",
      min: 0.1,
      max: 86400,
      step: 0.5,
      default: 2,
      unit: F.seconds.unit,
      help: F.seconds.help,
      showIf: (v) => v.mode === "every",
    },
    {
      kind: "choice",
      id: "sensitivity",
      legend: F.sensitivityLegend,
      default: "normal",
      showIf: (v) => v.mode === "scenes",
      options: [
        { id: "sensitive", label: F.sensitive.label, help: F.sensitive.help, options: { scene_threshold: 0.2 } },
        { id: "normal", label: F.normal.label, help: F.normal.help, options: { scene_threshold: 0.3 } },
        { id: "strict", label: F.strict.label, help: F.strict.help, options: { scene_threshold: 0.5 } },
      ],
    },
  ],
};
