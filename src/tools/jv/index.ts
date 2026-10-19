// Delt oppsett for journalistverktøyene: én controller for alle ni, og en
// funksjon som lager registeroppføringen fra et skjema. Hvert verktøy har sin
// egen mappe (`src/tools/<id>/`) med skjema og én linje i registeret.

import type { Platform } from "../../platform/types";
import { announce } from "../../ui/announce";
import type { ToolDefinition } from "../types";
import { getJvBackend } from "./backend";
import { JvController } from "./controller";
import type { ToolSchema } from "./schema";
import { toolTexts } from "./texts";
import { mountJvTool, type JvScreen } from "./view";

let shared: JvController | null = null;

/** Controlleren alle jv-verktøyene deler. Lages første gang den trengs. */
export function sharedJv(platform: Platform): JvController {
  shared ??= new JvController({ backend: getJvBackend(), platform, announce: (m) => announce(m) });
  return shared;
}

/** For tester og prøvevisning: start på nytt med en ny kjerne. */
export function resetSharedJv(): void {
  shared?.destroy();
  shared = null;
}

export function defineJvTool(schema: ToolSchema): ToolDefinition {
  const texts = toolTexts(schema.id);
  return {
    id: schema.id,
    name: texts.name,
    description: texts.description,
    icon: schema.icon,
    create(ctx) {
      const c = sharedJv(ctx.platform);
      c.registerSchema(schema);
      let screen: JvScreen | null = null;
      return {
        menu: {
          status: () => c.menuStatus(schema.id),
          subscribe: (listener) => {
            c.subscribe((change) => {
              if (change.type === "catalog" || change.type === "installed") listener();
            });
          },
        },
        init: () => c.init(),
        mountScreen(root) {
          screen = mountJvTool(root, c, schema.id, schema, texts, ctx);
          // Filer sluppet i vinduet går til verktøyet som vises (skallet sorterer).
          void ctx.platform.onDrop({
            onFiles: (paths) => screen?.drop(paths),
            onHover: (over) => screen?.hover(over),
          });
        },
        onShow() {
          screen?.onShow();
        },
        busy: () => c.busy(),
      };
    },
  };
}
