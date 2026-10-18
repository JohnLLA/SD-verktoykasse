import { describe, expect, it } from "vitest";
import type { ModelList, ModelStatus } from "../tools/transkribering/api";
import {
  DEFAULT_CHOICES,
  lowMemoryForBest,
  modelDisplayName,
  modelFor,
  normalizeChoices,
  normalizeDecoding,
} from "./choices";

function model(id: string, repo: string): ModelStatus {
  return {
    id,
    variant: "semantic",
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
  models: [model("a", "NbAiLabBeta/nb-whisper-medium-semantic"), model("b", "NbAiLab/nb-whisper-small-verbatim")],
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
});

describe("modellvalg", () => {
  it("finner modellen kjernen har valgt for stil og kvalitet", () => {
    expect(modelFor(list, "tolket", "anbefalt")?.id).toBe("a");
    expect(modelFor(list, "lydrett", "rask")?.id).toBe("b");
    expect(modelFor(list, "lydrett", "best")).toBeUndefined();
  });
  it("viser modellnavnet uten organisasjon", () => {
    expect(modelDisplayName({ repo: "NbAiLabBeta/nb-whisper-medium-semantic" })).toBe(
      "nb-whisper-medium-semantic",
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
