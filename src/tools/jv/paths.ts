// Stier og filtyper for jv-verktøyene. Rene funksjoner. Filnavn brukes bare i
// grensesnittet og sendes aldri til logg (regel 2).

import { t } from "../../i18n/nb";
import { fileExtension, fileName } from "../../lib/files";
import type { ToolSchema } from "./schema";

/** Mappen en sti ligger i. Tåler både `/` og `\`. Tom streng hvis det ikke finnes noen. */
export function dirName(path: string): string {
  const trimmed = path.replace(/[\\/]+$/, "");
  const i = Math.max(trimmed.lastIndexOf("/"), trimmed.lastIndexOf("\\"));
  if (i < 0) return "";
  if (i === 0) return trimmed.slice(0, 1);
  // «C:\» beholder skråstreken.
  if (i === 2 && /^[A-Za-z]:/.test(trimmed)) return trimmed.slice(0, 3);
  return trimmed.slice(0, i);
}

/** Standard utmappe: samme mappe som første fil. */
export function defaultOutDir(files: readonly string[]): string | null {
  const first = files[0];
  if (!first) return null;
  const d = dirName(first);
  return d === "" ? null : d;
}

/** Filendelsene som «hørtes riktige ut» for verktøyet. Mapper har ingen endelse. */
export function isAccepted(path: string, schema: ToolSchema): boolean {
  const ext = fileExtension(path);
  if (ext === "") return schema.acceptsFolders === true;
  return schema.extensions.includes(ext);
}

export interface Partitioned {
  accepted: string[];
  /** Filene som ikke passer, bare navnene, til meldingen. */
  rejected: string[];
}

export function partitionFiles(paths: readonly string[], schema: ToolSchema): Partitioned {
  const accepted: string[] = [];
  const rejected: string[] = [];
  for (const p of paths) (isAccepted(p, schema) ? accepted : rejected).push(p);
  return { accepted, rejected: rejected.map(fileName) };
}

/** Navn på filen en rapport peker på, eller `null` hvis oppføringen ikke har sti. */
export function outputPath(entry: unknown): string | null {
  if (typeof entry === "string") return entry;
  if (entry && typeof entry === "object" && "path" in entry) {
    const p = (entry as { path: unknown }).path;
    return typeof p === "string" ? p : null;
  }
  return null;
}

/** «Fant 6 treff. 2 mulige numre ble forkastet.» Verktøyets egen setning peker på kommandolinjen og brukes ikke. */
export function findSummary(items: readonly { rejected: boolean }[]): string {
  const rejected = items.filter((i) => i.rejected).length;
  return t.jv.redact.found(items.length - rejected, rejected);
}
