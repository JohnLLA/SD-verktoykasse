// Hvordan et verktøy står i venstremenyen. Rene funksjoner uten Tauri.

import type { ToolView } from "./api";

/**
 * - `ready`: lastet ned, vanlig tekst.
 * - `download`: ikke lastet ned (grå tekst og nedlastingsikon), men kan klikkes.
 * - `soon`: finnes ikke for denne plattformen («Kommer»), kan ikke lastes ned.
 */
export type MenuStatus = "ready" | "download" | "soon";

export function menuStatus(installed: boolean, view: ToolView | undefined): MenuStatus {
  if (installed) return "ready";
  if (view?.status === "not_for_platform") return "soon";
  return "download";
}

/** Hva skjermen for et verktøy som ikke er lastet ned, skal vise. */
export type InstallScreen =
  | "checking" // katalogen hentes
  | "ready" // kan lastes ned
  | "soon" // «Kommer for Windows»
  | "needs_os"
  | "needs_app"
  | "no_catalog"; // ingen katalog, og den lot seg ikke hente

export function installScreen(view: ToolView | undefined, catalogLoading: boolean): InstallScreen {
  if (!view || view.status === "unknown") return catalogLoading ? "checking" : "no_catalog";
  switch (view.status) {
    case "available":
      return "ready";
    case "not_for_platform":
      return "soon";
    case "needs_newer_os":
      return "needs_os";
    case "needs_newer_app":
      return "needs_app";
  }
}
