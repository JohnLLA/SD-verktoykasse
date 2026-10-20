// Resultatet av en kjøring: overskrift fra `summary`, `warnings` som tydelige
// meldinger, utfilene med «Vis i Finder/Utforsker», og for metadata «vis»
// feltene gruppert. For nynorsk står «Utkast – må leses over» alltid.

import { t } from "../../i18n/nb";
import { fileName } from "../../lib/files";
import type { Platform } from "../../platform/types";
import { h } from "../../ui/dom";
import { icon } from "../../ui/icons";
import type { JvReport } from "./api";
import type { RunState } from "./controller";
import { jvErrorText } from "./errors";
import { outputPath } from "./paths";

const R = t.jv.result;

/** Rapportoppføringer med felter (metadata «vis»): `groups` med lister av felt. */
interface FieldEntry {
  field: string;
  value: string;
  sensitive: boolean;
}
interface MetadataFile {
  path: string;
  format?: string;
  field_count: number;
  sensitive_count: number;
  groups: Record<string, FieldEntry[]>;
}

function asMetadataFile(e: unknown): MetadataFile | null {
  if (!e || typeof e !== "object") return null;
  const o = e as Record<string, unknown>;
  if (typeof o.path !== "string" || typeof o.groups !== "object" || o.groups === null) return null;
  return {
    path: o.path,
    format: typeof o.format === "string" ? o.format : undefined,
    field_count: typeof o.field_count === "number" ? o.field_count : 0,
    sensitive_count: typeof o.sensitive_count === "number" ? o.sensitive_count : 0,
    groups: o.groups as Record<string, FieldEntry[]>,
  };
}

export function revealLabel(os: Platform["os"]): string {
  return R.reveal[os];
}

export interface ResultOptions {
  platform: Platform;
  draft: boolean;
  /** Filer som ikke er utfiler fra verktøyet (planfilen), utelates fra listen. */
  hidePaths?: readonly string[];
}

/** Advarslene som ikke skal vises (de forklares av skjermen selv). */
export function visibleWarnings(report: JvReport | null, hide?: (w: string) => boolean): string[] {
  const all = Array.isArray(report?.warnings) ? (report?.warnings as unknown[]).filter((w): w is string => typeof w === "string") : [];
  return hide ? all.filter((w) => !hide(w)) : all;
}

export function warningsBlock(warnings: readonly string[]): HTMLElement | null {
  if (warnings.length === 0) return null;
  return h(
    "section",
    { class: "result-warnings", "aria-label": R.warnings },
    h("h3", { class: "result-subtitle", text: R.warnings }),
    h(
      "ul",
      { class: "warn-list" },
      ...warnings.map((w) =>
        h("li", { class: "warn-item", role: "note" }, icon("alert", 20), h("span", { class: "offscreen", text: `${R.warningLabel}: ` }), h("span", { text: w })),
      ),
    ),
  );
}

function metadataBlock(file: MetadataFile): HTMLElement {
  const groups = Object.entries(file.groups).filter(([, fields]) => Array.isArray(fields) && fields.length > 0);
  return h(
    "details",
    { class: "meta-details" },
    h("summary", { text: `${fileName(file.path)} · ${R.fieldsCount(file.field_count, file.sensitive_count)}` }),
    ...groups.map(([group, fields]) =>
      h(
        "section",
        { class: "meta-group" },
        h("h4", { class: "meta-group-title", text: R.groups[group] ?? group }),
        h(
          "dl",
          { class: "meta-fields" },
          ...fields.map((f) =>
            h(
              "div",
              { class: f.sensitive ? "meta-field meta-sensitive" : "meta-field" },
              h("dt", { text: f.field }),
              h("dd", {}, h("span", { text: f.value }), f.sensitive && h("span", { class: "badge badge-warn", text: R.sensitive })),
            ),
          ),
        ),
      ),
    ),
  );
}

export function createResult(run: RunState, opts: ResultOptions): HTMLElement {
  const report = run.report;
  const hide = new Set(opts.hidePaths ?? []);
  const entries = Array.isArray(report?.outputs) ? (report?.outputs as unknown[]) : [];
  const metadataFiles = entries.map(asMetadataFile).filter((f): f is MetadataFile => f !== null);
  const paths = entries
    .filter((e) => asMetadataFile(e) === null)
    .map(outputPath)
    .filter((p): p is string => p !== null && !hide.has(p));

  const warnings = warningsBlock(visibleWarnings(report));
  const reveal = revealLabel(opts.platform.os);

  return h(
    "section",
    { class: "result", "aria-labelledby": "jv-result-title" },
    h(
      "div",
      { class: "card card-done", role: "status" },
      icon("check", 24),
      h(
        "div",
        { class: "card-body" },
        h("h2", { id: "jv-result-title", class: "card-title", tabindex: -1, text: report?.summary || R.doneTitle }),
        opts.draft && h("p", { class: "draft-badge", text: R.draft }),
        opts.draft && h("p", { class: "card-sub", text: R.draftHint }),
      ),
    ),
    warnings,
    metadataFiles.length > 0 && h("div", { class: "meta-list" }, ...metadataFiles.map(metadataBlock)),
    metadataFiles.length === 0 &&
      h(
        "section",
        { class: "result-files", "aria-label": R.files },
        h("h3", { class: "result-subtitle", text: R.files }),
        paths.length === 0
          ? h("p", { class: "empty", text: R.noFiles })
          : h(
              "ul",
              { class: "rows" },
              ...paths.map((p) =>
                h(
                  "li",
                  { class: "row row-done" },
                  icon("file", 22),
                  h("div", { class: "row-body" }, h("span", { class: "row-name", text: fileName(p) })),
                  h("div", { class: "row-actions" }, h("button", { type: "button", class: "btn", text: reveal, "aria-label": R.revealFile(fileName(p), reveal), onclick: () => void opts.platform.reveal(p).catch(() => undefined) })),
                ),
              ),
            ),
      ),
  );
}

/** Feilkortet når en kjøring ikke gikk. */
export function createRunError(run: RunState): HTMLElement {
  const e = jvErrorText(run.error ?? { code: "internal" });
  // Verktøyets egen melding (kode 1) er skrevet til brukeren og sier mer enn den generelle.
  const title = run.error?.code === "tool_failed" && run.message ? run.message : e.title;
  const hint = run.error?.code === "tool_failed" && run.message ? "" : e.hint;
  return h(
    "div",
    { class: "card card-error", role: "alert" },
    icon("alert", 24),
    h("div", { class: "card-body" }, h("p", { class: "card-title", text: R.failedTitle }), h("p", { class: "card-strong", text: title }), hint && h("p", { text: hint })),
  );
}
