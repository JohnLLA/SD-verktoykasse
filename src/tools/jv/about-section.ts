// Om-vinduet: installerte verktøy med versjon og lisens.

import { t } from "../../i18n/nb";
import { h, replace } from "../../ui/dom";
import type { JvController } from "./controller";

const A = t.jv.about;

export function mountJvAbout(root: HTMLElement, c: JvController): { refresh(): void } {
  const list = h("ul", { class: "licenses" });
  root.append(
    h(
      "section",
      { class: "block", "aria-labelledby": "about-jv" },
      h("h2", { id: "about-jv", class: "block-title", text: A.title }),
      h("p", { class: "help", text: A.note }),
      list,
    ),
  );

  function render(): void {
    if (c.installed.length === 0) {
      replace(list, h("li", { class: "empty", text: A.none }));
      return;
    }
    replace(
      list,
      ...c.installed.map((i) =>
        h("li", { class: "license" }, h("p", { class: "license-name", text: i.name }), h("p", { class: "license-line", text: A.line(i.version, i.license) })),
      ),
    );
  }

  c.subscribe((ch) => {
    if (ch.type === "installed") render();
  });
  render();
  return { refresh: () => void c.refreshInstalled() };
}
