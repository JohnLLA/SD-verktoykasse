// Innstillinger: verktøyenes egne deler, og det som gjelder hele appen.

import { loadVersionCheck, KEYS } from "../lib/settings";
import { t } from "../i18n/nb";
import type { Platform } from "../platform/types";
import { h, nextId } from "../ui/dom";

export interface SettingsView {
  el: HTMLElement;
  heading: HTMLElement;
  refresh(): void;
}

export function createSettingsView(
  platform: Platform,
  toolSections: readonly { refresh(): void }[],
  sectionHosts: readonly HTMLElement[],
): SettingsView {
  const heading = h("h1", { class: "page-title", tabindex: -1, text: t.settings.title });
  const toggleId = nextId("version-check");
  const toggle = h("input", {
    type: "checkbox",
    role: "switch",
    id: toggleId,
    class: "switch",
    checked: true,
    onchange: () => {
      void platform.settings.set(KEYS.versionCheck, toggle.checked);
    },
  });
  const hintId = nextId("version-hint");
  toggle.setAttribute("aria-describedby", hintId);

  const updates = h(
    "section",
    { class: "block", "aria-labelledby": "set-updates" },
    h("h2", { id: "set-updates", class: "block-title", text: t.settings.updates.title }),
    h(
      "div",
      { class: "switch-row" },
      toggle,
      h("label", { for: toggleId, text: t.settings.updates.toggle }),
    ),
    h("p", { class: "help", id: hintId, text: t.settings.updates.hint }),
  );

  const el = h("div", { class: "settings" }, heading, ...sectionHosts, updates);

  return {
    el,
    heading,
    refresh() {
      void loadVersionCheck(platform.settings).then((on) => {
        toggle.checked = on;
      });
      for (const s of toolSections) s.refresh();
    },
  };
}
