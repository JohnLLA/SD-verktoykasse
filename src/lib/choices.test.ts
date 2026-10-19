import { describe, expect, it } from "vitest";
import type { ModelList, ModelStatus } from "../tools/transkribering/api";
import {
  DEFAULT_CHOICES,
  lowMemoryForBest,
  modelDisplayName,
  modelFor,
  normalizeChoices,
  normalizeDecoding,
  showLydrettNynorskNote,
} from "./choices";
import { t } from "../i18n/nb";

function model(id: string, repo: string): ModelStatus {
  return {
    id,
    variant: "main",
    size: "medium",
    quant: "q5_0",
    repo,
    bytes: 539_212_484,
    installed: false,
    location: null,
    partial_bytes: 0,
  };
}

const list: ModelList = {
  models: [model("a", "NbAiLab/nb-whisper-medium"), model("b", "NbAiLab/nb-whisper-small-verbatim")],
  choices: [
    { stil: "tolket", kvalitet: "anbefalt", model_id: "a" },
    { stil: "lydrett", kvalitet: "rask", model_id: "b" },
  ],
  app_model_dir: "/x",
  custom_model_dir: null,
  license: "Apache-2.0",
  license_holder: "NB",
};

describe("standardvalg (spesifikasjonen)", () => {
  it("er bokmål, tolket og anbefalt", () => {
    expect(DEFAULT_CHOICES).toEqual({ malform: "bokmål", stil: "tolket", kvalitet: "anbefalt" });
    expect(normalizeChoices({})).toEqual(DEFAULT_CHOICES);
  });
  it("husker gyldige lagrede valg", () => {
    expect(normalizeChoices({ malform: "nynorsk", stil: "lydrett", kvalitet: "best" })).toEqual({
      malform: "nynorsk",
      stil: "lydrett",
      kvalitet: "best",
    });
  });
  it("faller tilbake til standard for ugyldige verdier, ett felt om gangen", () => {
    expect(normalizeChoices({ malform: "svensk", stil: "lydrett", kvalitet: 3 })).toEqual({
      malform: "bokmål",
      stil: "lydrett",
      kvalitet: "anbefalt",
    });
  });
  it("beam er standard søkemåte", () => {
    expect(normalizeDecoding(undefined)).toBe("beam5");
    expect(normalizeDecoding("greedy")).toBe("greedy");
    expect(normalizeDecoding("beam9")).toBe("beam5");
  });
  it("hjelpeteksten for Raskere sier at den bare gjelder tolket", () => {
    expect(t.settings.decoding.greedyHint).toBe(
      "Raskere for tolket, men litt mindre nøyaktig. Lydrett bruker alltid grundig.",
    );
  });
});

describe("modellvalg", () => {
  it("finner modellen kjernen har valgt for stil og kvalitet", () => {
    expect(modelFor(list, "tolket", "anbefalt")?.id).toBe("a");
    expect(modelFor(list, "lydrett", "rask")?.id).toBe("b");
    expect(modelFor(list, "lydrett", "best")).toBeUndefined();
  });
  it("viser modellnavnet uten organisasjon", () => {
    expect(modelDisplayName({ repo: "NbAiLab/nb-whisper-medium" })).toBe("nb-whisper-medium");
    expect(modelDisplayName({ repo: "NbAiLab/nb-whisper-small-verbatim" })).toBe("nb-whisper-small-verbatim");
  });
});

describe("forklaring for lydrett + nynorsk", () => {
  it("vises bare når både lydrett og nynorsk er valgt", () => {
    expect(showLydrettNynorskNote({ malform: "nynorsk", stil: "lydrett" })).toBe(true);
    expect(showLydrettNynorskNote({ malform: "nynorsk", stil: "tolket" })).toBe(false);
    expect(showLydrettNynorskNote({ malform: "bokmål", stil: "lydrett" })).toBe(false);
    expect(showLydrettNynorskNote({ malform: "bokmål", stil: "tolket" })).toBe(false);
    expect(showLydrettNynorskNote(DEFAULT_CHOICES)).toBe(false);
  });
  it("har teksten i språkfilen", () => {
    expect(t.transkribering.choices.stil.explainLydrettNynorsk).toBe(
      "Lydrett gir det som blir sagt. Snakker personen bokmål, blir noe stående på bokmål.",
    );
  });
});

describe("advarsel om minne for Best", () => {
  const GiB = 2 ** 30;
  it("advarer bare for Best, og bare under 16 GB", () => {
    expect(lowMemoryForBest(8 * GiB, "best")).toBe(8);
    expect(lowMemoryForBest(8 * GiB, "anbefalt")).toBeNull();
    expect(lowMemoryForBest(8 * GiB, "rask")).toBeNull();
    expect(lowMemoryForBest(16 * GiB, "best")).toBeNull();
    expect(lowMemoryForBest(36 * GiB, "best")).toBeNull();
  });
  it("regner en 16 GB-maskin som melder 15,7 GiB som 16 GB", () => {
    expect(lowMemoryForBest(Math.floor(15.7 * GiB), "best")).toBeNull();
  });
  it("sier ikke noe når minnet er ukjent", () => {
    expect(lowMemoryForBest(null, "best")).toBeNull();
  });
});
