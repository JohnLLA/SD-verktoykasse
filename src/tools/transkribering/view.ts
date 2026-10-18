// Transkribering-skjermen: bytter mellom «Ny transkribering» og én fil.

import { t } from "../../i18n/nb";
import { h } from "../../ui/dom";
import type { ToolContext } from "../types";
import type { ControllerChange, TranskriberingController } from "./controller";
import { createFileView, type FileView } from "./view-file";
import { createNewView } from "./view-new";

export function mountTranskribering(root: HTMLElement, c: TranskriberingController, ctx: ToolContext): void {
  const heading = h("h1", { class: "page-title", tabindex: -1, text: t.transkribering.title });
  const stage = h("div", { class: "stage" });
  root.append(heading, stage);

  const newView = createNewView(c);
  let fileView: FileView | null = null;
  stage.append(newView.el);

  function showScreen(): void {
    if (c.screen.kind === "file") {
      const id = c.screen.id;
      fileView?.destroy();
      fileView = createFileView(c, ctx.platform, id);
      newView.el.hidden = true;
      stage.append(fileView.el);
      fileView.focusHeading();
    } else {
      if (fileView) {
        fileView.destroy();
        fileView.el.remove();
        fileView = null;
        heading.focus();
      }
      newView.el.hidden = false;
    }
  }

  c.subscribe((change: ControllerChange) => {
    if (change.type === "screen") showScreen();
    newView.onChange(change);
    fileView?.onChange(change);
  });

  // Filer sluppet i vinduet legges i køen, uansett hvilken side som vises.
  void ctx.platform.onDrop({
    onFiles: (paths) => {
      ctx.activate();
      c.addFiles(paths);
    },
    onHover: (over) => newView.setDragging(over),
  });
}
