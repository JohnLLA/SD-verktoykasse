// Registeroppføringen for Transkribering.

import { t } from "../../i18n/nb";
import type { ToolDefinition } from "../types";
import { getBackend } from "./backend";
import { TranskriberingController } from "./controller";
import { mountSettingsSection } from "./settings-section";
import { mountTranskribering } from "./view";

export const transkribering: ToolDefinition = {
  id: "transkribering",
  name: t.tools.transkribering.name,
  description: t.tools.transkribering.description,
  icon: "waveform",
  create(ctx) {
    const controller = new TranskriberingController({
      backend: getBackend(),
      platform: ctx.platform,
      announce: ctx.announce,
    });
    return {
      init: () => controller.init(),
      mountScreen(root) {
        mountTranskribering(root, controller, ctx);
      },
      mountSettings(root) {
        return mountSettingsSection(root, controller, ctx);
      },
      busy: () => controller.busy(),
    };
  },
};
