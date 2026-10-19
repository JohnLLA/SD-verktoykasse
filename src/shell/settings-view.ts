// Innstillinger: verktøyenes egne deler, og det som gjelder hele appen.

import { loadVersionCheck, KEYS } from "../lib/settings";
import { t } from "../i18n/nb";
import type { Platform, UpdateCheckResult } from "../platform/types";
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
  /** Knappen «Se etter ny versjon nå». Nettkallet gjøres først når den trykkes. */
  checkNow: () => Promise<UpdateCheckResult>,
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

  const status = h("p", { class: "help check-now-status", role: "status", "aria-live": "polite" });
  const checkButton = h("button", {
    type: "button",
    class: "btn",
    text: t.settings.updates.checkNow,
    onclick: () => {
      checkButton.disabled = true;
      status.textContent = t.settings.updates.checking;
      void checkNow()
        .catch((): UpdateCheckResult => ({ status: "failed" }))
        .then((r) => {
          status.textContent =
            r.status === "available" ? t.settings.updates.foundNew(r.version) : r.status === "none" ? t.settings.updates.upToDate : t.settings.updates.checkFailed;
          checkButton.disabled = false;
        });
    },
  });

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
    h("div", { class: "check-now" }, checkButton, status),
    h("p", { class: "help", text: t.settings.updates.checkNowHint }),
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
