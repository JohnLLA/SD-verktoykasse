// Valgene (målform, stil, kvalitet), standardene fra spesifikasjonen og
// kobling til modellene fra `list_models`.

import type {
  Decoding,
  Kvalitet,
  Malform,
  ModelList,
  ModelStatus,
  Stil,
} from "../tools/transkribering/api";
import { roundedGb } from "./format";

export interface Choices {
  malform: Malform;
  stil: Stil;
  kvalitet: Kvalitet;
}

/** Spesifikasjonen: Bokmål, Tolket, Anbefalt. */
export const DEFAULT_CHOICES: Choices = {
  malform: "bokmål",
  stil: "tolket",
  kvalitet: "anbefalt",
};

export const DEFAULT_DECODING: Decoding = "beam5";

export const MALFORMS: readonly Malform[] = ["bokmål", "nynorsk"];
export const STILER: readonly Stil[] = ["lydrett", "tolket"];
export const KVALITETER: readonly Kvalitet[] = ["rask", "anbefalt", "best"];

function pick<T extends string>(allowed: readonly T[], value: unknown, fallback: T): T {
  return typeof value === "string" && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : fallback;
}

/** Gjør lagrede verdier om til gyldige valg. Ukjent eller manglende gir standard. */
export function normalizeChoices(raw: Partial<Record<keyof Choices, unknown>>): Choices {
  return {
    malform: pick(MALFORMS, raw.malform, DEFAULT_CHOICES.malform),
    stil: pick(STILER, raw.stil, DEFAULT_CHOICES.stil),
    kvalitet: pick(KVALITETER, raw.kvalitet, DEFAULT_CHOICES.kvalitet),
  };
}

export function normalizeDecoding(raw: unknown): Decoding {
  return pick(["beam5", "greedy"] as const, raw, DEFAULT_DECODING);
}

/**
 * Lydrett nynorsk gir det som blir sagt, så bokmålstale gir noe bokmål
 * (docs/kvalitet.md). Forklaringen vises når begge er valgt. Teksten
 * etterbehandles ikke (regel 4).
 */
export function showLydrettNynorskNote(c: Pick<Choices, "malform" | "stil">): boolean {
  return c.stil === "lydrett" && c.malform === "nynorsk";
}

/** Modellen kjernen bruker for en kombinasjon av stil og kvalitet. */
export function modelFor(list: ModelList, stil: Stil, kvalitet: Kvalitet): ModelStatus | undefined {
  const choice = list.choices.find((c) => c.stil === stil && c.kvalitet === kvalitet);
  return choice ? list.models.find((m) => m.id === choice.model_id) : undefined;
}

/** `NbAiLab/nb-whisper-medium-verbatim` blir `nb-whisper-medium-verbatim`. */
export function modelDisplayName(m: Pick<ModelStatus, "repo">): string {
  const parts = m.repo.split("/");
  return parts[parts.length - 1] ?? m.repo;
}

/** «Best» anbefales bare med 16 GB eller mer (spesifikasjonen). Gir GB ved for lite, ellers `null`. */
export const BEST_MIN_MEMORY_BYTES = 15 * 2 ** 30; // 16 GB-maskiner melder litt under 16 GiB

export function lowMemoryForBest(totalMemoryBytes: number | null, kvalitet: Kvalitet): number | null {
  if (kvalitet !== "best" || totalMemoryBytes === null) return null;
  return totalMemoryBytes < BEST_MIN_MEMORY_BYTES ? roundedGb(totalMemoryBytes) : null;
}
