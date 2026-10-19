// Skallet: venstremeny fra registeret, Innstillinger, Om, oppdateringsplass,
// og vakt når appen lukkes mens noe pågår.

import { t } from "../i18n/nb";
import type { Platform } from "../platform/types";
import type { ToolContext, ToolDefinition, ToolInstance } from "../tools/types";
import { announce, mountAnnouncer } from "../ui/announce";
import { h } from "../ui/dom";
import { icon } from "../ui/icons";
import { confirmDialog } from "../ui/modal";
import { createAboutView } from "./about-view";
import { createSettingsView } from "./settings-view";
import { runManualUpdateCheck, runStartupUpdateCheck, type UpdateCheckDeps } from "./update-check";
import { createUpdateNotice, type UpdateNotice } from "./update-notice";

type Page = { kind: "tool"; id: string } | { kind: "settings" } | { kind: "about" };

export interface App {
  updateNotice: UpdateNotice;
  navigate(page: Page): void;
}

export async function startApp(
  root: HTMLElement,
  platform: Platform,
  tools: readonly ToolDefinition[],
): Promise<App> {
  const pages = new Map<string, HTMLElement>();
  const navButtons = new Map<string, HTMLButtonElement>();
  const key = (p: Page) => (p.kind === "tool" ? `tool:${p.id}` : p.kind);
  let current: Page | null = null;

  const updateNotice = createUpdateNotice();
  const main = h("main", { class: "main", id: "main" });
  const nav = h("nav", { class: "nav", "aria-label": t.app.menuLabel });
  const toolList = h("ul", { class: "nav-list" });
  const bottomList = h("ul", { class: "nav-list nav-bottom" });

  function navItem(page: Page, label: string, iconName: string): HTMLElement {
    const button = h(
      "button",
      { type: "button", class: "nav-item", onclick: () => navigate(page) },
      icon(iconName, 22),
      h("span", { text: label }),
    );
    navButtons.set(key(page), button);
    return h("li", {}, button);
  }

  // ---- verktøyene
  const instances: { def: ToolDefinition; tool: ToolInstance; page: HTMLElement }[] = [];
  const settingsHosts: HTMLElement[] = [];
  const settingsSections: { refresh(): void }[] = [];

  for (const def of tools) {
    const ctx: ToolContext = {
      platform,
      announce: (m) => announce(m),
      activate: () => navigate({ kind: "tool", id: def.id }),
    };
    const tool = def.create(ctx);
    const page = h("section", { class: "page", id: `page-${def.id}`, hidden: true });
    tool.mountScreen(page);
    main.append(page);
    pages.set(key({ kind: "tool", id: def.id }), page);
    toolList.append(navItem({ kind: "tool", id: def.id }, def.name, def.icon));
    instances.push({ def, tool, page });
    if (tool.mountSettings) {
      const host = h("div", { class: "settings-tool" });
      settingsSections.push(tool.mountSettings(host));
      settingsHosts.push(host);
    }
  }

  const updateDeps: UpdateCheckDeps = {
    platform,
    notice: updateNotice,
    confirmInstall: async () => {
      if (!instances.some((i) => i.tool.busy?.())) return true;
      return confirmDialog({
        title: t.update.busyTitle,
        body: t.update.busyBody,
        confirmLabel: t.update.busyConfirm,
        cancelLabel: t.update.busyCancel,
        danger: true,
      });
    },
  };
  const settings = createSettingsView(platform, settingsSections, settingsHosts, () => runManualUpdateCheck(updateDeps));
  const about = createAboutView(platform);
  const settingsPage = h("section", { class: "page", id: "page-settings", hidden: true }, settings.el);
  const aboutPage = h("section", { class: "page", id: "page-about", hidden: true }, about.el);
  main.append(settingsPage, aboutPage);
  pages.set("settings", settingsPage);
  pages.set("about", aboutPage);
  bottomList.append(navItem({ kind: "settings" }, t.nav.settings, "settings"), navItem({ kind: "about" }, t.nav.about, "info"));

  nav.append(
    h("div", { class: "brand" }, h("span", { class: "brand-mark", "aria-hidden": "true", text: "LLA" }), h("span", { class: "brand-name", text: t.app.shortName })),
    toolList,
    bottomList,
  );

  const skip = h("a", { class: "skip", href: "#main", text: t.app.skipToContent, onclick: (e: Event) => { e.preventDefault(); main.focus(); } });
  main.tabIndex = -1;
  root.append(skip, h("div", { class: "shell" }, nav, h("div", { class: "content" }, updateNotice.el, main)));
  mountAnnouncer(root);

  function navigate(page: Page): void {
    const k = key(page);
    if (!pages.has(k)) return;
    if (current && key(current) === k) return;
    current = page;
    for (const [pk, el] of pages) el.hidden = pk !== k;
    for (const [bk, b] of navButtons) {
      if (bk === k) b.setAttribute("aria-current", "page");
      else b.removeAttribute("aria-current");
    }
    main.scrollTop = 0;
    if (page.kind === "settings") {
      settings.refresh();
      settings.heading.focus();
    } else if (page.kind === "about") {
      about.refresh();
      about.heading.focus();
    } else {
      instances.find((i) => i.def.id === page.id)?.tool.onShow?.();
    }
  }

  // Verktøyene starter opp (lytter, leser innstillinger) før første side vises.
  await Promise.all(instances.map((i) => i.tool.init?.().catch(() => undefined)));
  const first = tools[0];
  navigate(first ? { kind: "tool", id: first.id } : { kind: "settings" });

  // ---- versjonssjekk (hopper over alt nettarbeid hvis bryteren er av). Feil vises ikke.
  void runStartupUpdateCheck(updateDeps).catch(() => undefined);

  // ---- vakt ved lukking
  await platform.onCloseRequested(async () => {
    const states = instances.map((i) => i.tool.busy?.() ?? null);
    const kind = states.includes("running") ? "running" : states.includes("unsaved") ? "unsaved" : null;
    if (!kind) return true;
    return confirmDialog({
      title: t.app.closeTitle,
      body: kind === "running" ? t.app.closeWithRunning : t.app.closeWithUnsaved,
      confirmLabel: t.app.closeConfirm,
      cancelLabel: t.app.closeCancel,
      danger: true,
    });
  });

  return { updateNotice, navigate };
}
