// Om-vinduet: versjon, personvern og lisenser.

import { t } from "../i18n/nb";
import type { Platform } from "../platform/types";
import { h } from "../ui/dom";

export interface AboutView {
  el: HTMLElement;
  heading: HTMLElement;
  refresh(): void;
}

export function createAboutView(platform: Platform): AboutView {
  const A = t.about;
  const heading = h("h1", { class: "page-title", tabindex: -1, text: A.title });
  const version = h("p", { class: "about-version", text: A.versionUnknown });

  const licenses = h(
    "ul",
    { class: "licenses" },
    ...A.licenses.map((l) =>
      h(
        "li",
        { class: "license" },
        h("p", { class: "license-name", text: l.name }),
        h("p", { class: "license-line", text: A.licenseLine(l.by, l.license) }),
        h("p", { class: "help", text: l.note }),
      ),
    ),
  );

  // Hele lisensteksten (ca. 750 kB) ligger i en egen fil som bare hentes når
  // brukeren åpner den. Den ligger i appen; ingen nettkall.
  const fullText = h("pre", { class: "license-full", tabindex: 0, role: "region", "aria-label": A.fullLicenses.regionLabel, hidden: true });
  const full = h(
    "details",
    { class: "license-details" },
    h("summary", { text: A.fullLicenses.summary }),
    h("p", { class: "help", text: A.fullLicenses.intro }),
    fullText,
  );
  let fullLoaded = false;
  full.addEventListener("toggle", () => {
    if (!full.open || fullLoaded) return;
    fullLoaded = true;
    fullText.hidden = false;
    fullText.textContent = A.fullLicenses.loading;
    import("../assets/tredjepart.txt?raw").then(
      (m) => {
        fullText.textContent = m.default;
      },
      () => {
        fullLoaded = false;
        fullText.textContent = A.fullLicenses.failed;
      },
    );
  });

  const el = h(
    "div",
    { class: "about" },
    heading,
    h("p", { class: "about-name", text: t.app.name }),
    version,
    h("p", { text: A.by }),
    h(
      "section",
      { class: "block", "aria-labelledby": "about-privacy" },
      h("h2", { id: "about-privacy", class: "block-title", text: A.privacyTitle }),
      h("p", { class: "about-privacy", text: A.privacy }),
      h("p", { class: "help", text: A.privacyDetail }),
    ),
    h(
      "section",
      { class: "block", "aria-labelledby": "about-licenses" },
      h("h2", { id: "about-licenses", class: "block-title", text: A.licensesTitle }),
      h("p", { class: "help", text: A.licensesIntro }),
      licenses,
      full,
    ),
  );

  return {
    el,
    heading,
    refresh() {
      void platform.appVersion().then((v) => {
        if (v) version.textContent = A.version(v);
      });
    },
  };
}
