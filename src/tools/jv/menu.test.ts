import { describe, expect, it } from "vitest";
import { toolView } from "./fakes";
import { installScreen, menuStatus } from "./menu";

describe("menytilstander", () => {
  it("lastet ned: vanlig", () => {
    expect(menuStatus(true, toolView("ocr", "available"))).toBe("ready");
    // Installert vinner, også om katalogen ikke har en linje (eldre versjon, eller katalogen er i endring).
    expect(menuStatus(true, toolView("ocr", "not_for_platform"))).toBe("ready");
    expect(menuStatus(true, undefined)).toBe("ready");
  });

  it("ikke lastet ned: grå tekst og nedlastingsikon, men kan klikkes", () => {
    expect(menuStatus(false, toolView("ocr", "available"))).toBe("download");
    expect(menuStatus(false, undefined)).toBe("download");
    expect(menuStatus(false, toolView("ocr", "unknown"))).toBe("download");
    expect(menuStatus(false, toolView("ocr", "needs_newer_os"))).toBe("download");
    expect(menuStatus(false, toolView("ocr", "needs_newer_app"))).toBe("download");
  });

  it("finnes ikke for plattformen: «Kommer»", () => {
    expect(menuStatus(false, toolView("nynorsk", "not_for_platform"))).toBe("soon");
  });
});

describe("hva skjermen for et verktøy som ikke er lastet ned, viser", () => {
  it("følger statusen fra katalogen", () => {
    expect(installScreen(toolView("ocr", "available"), false)).toBe("ready");
    expect(installScreen(toolView("nynorsk", "not_for_platform"), false)).toBe("soon");
    expect(installScreen(toolView("ocr", "needs_newer_os"), false)).toBe("needs_os");
    expect(installScreen(toolView("ocr", "needs_newer_app"), false)).toBe("needs_app");
  });

  it("uten katalog: venter mens den hentes, ellers «prøv igjen»", () => {
    expect(installScreen(undefined, true)).toBe("checking");
    expect(installScreen(toolView("ocr", "unknown"), true)).toBe("checking");
    expect(installScreen(undefined, false)).toBe("no_catalog");
  });
});
