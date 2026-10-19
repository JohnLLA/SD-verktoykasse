// «Valg»: feltene fra skjemaet. Hvert felt bygges én gang og oppdateres på
// stedet, så fokus ikke hopper mens brukeren skriver.

import { t } from "../../i18n/nb";
import { fileName } from "../../lib/files";
import { h, nextId } from "../../ui/dom";
import { segmented, type Segmented } from "../../ui/segmented";
import type { JvController } from "./controller";
import {
  fieldVisible,
  selectedOption,
  textValid,
  type ChoiceField,
  type Field,
  type FileField,
  type NumberField,
  type TextField,
  type ToggleField,
  type ToolSchema,
} from "./schema";
import type { JvToolId } from "./api";

export interface FieldsView {
  el: HTMLElement;
  update(): void;
}

interface Part {
  el: HTMLElement;
  field: Field;
  update(): void;
}

export function createFields(c: JvController, id: JvToolId, schema: ToolSchema): FieldsView {
  const J = t.jv.screen;
  const parts: Part[] = schema.fields.map((f) => buildPart(c, id, f));

  const grid = h("div", { class: "choice-grid" }, ...parts.map((p) => p.el));
  const el = h(
    "section",
    { class: "block choices", "aria-labelledby": `jv-choices-${id}` },
    h("h2", { id: `jv-choices-${id}`, class: "block-title", text: J.choicesTitle }),
    grid,
  );

  function update(): void {
    const values = c.session(id).values;
    let any = false;
    for (const p of parts) {
      const visible = fieldVisible(p.field, values);
      p.el.hidden = !visible;
      if (visible) any = true;
      p.update();
    }
    el.hidden = !any;
  }
  update();
  return { el, update };
}

function buildPart(c: JvController, id: JvToolId, f: Field): Part {
  switch (f.kind) {
    case "choice":
      return choicePart(c, id, f);
    case "number":
      return numberPart(c, id, f);
    case "toggle":
      return togglePart(c, id, f);
    case "text":
      return textPart(c, id, f);
    case "file":
      return filePart(c, id, f);
  }
}

function choicePart(c: JvController, id: JvToolId, f: ChoiceField): Part {
  const helpId = nextId("jv-help");
  const help = h("p", { class: "help", id: helpId });
  const seg: Segmented<string> = segmented({
    legend: f.legend,
    options: f.options.map((o) => ({ value: o.id, label: o.label })),
    value: c.session(id).values[f.id] as string,
    onChange: (v) => c.setValue(id, f.id, v),
    describedBy: helpId,
  });
  return {
    field: f,
    el: h("div", { class: "choice" }, seg.el, help),
    update() {
      const s = c.session(id);
      seg.set(selectedOption(f, s.values).id);
      help.textContent = selectedOption(f, s.values).help ?? "";
      help.hidden = help.textContent === "";
    },
  };
}

function numberPart(c: JvController, id: JvToolId, f: NumberField): Part {
  const inputId = nextId("jv-num");
  const helpId = nextId("jv-help");
  const input = h("input", {
    type: "number",
    class: "input input-number",
    id: inputId,
    min: f.min,
    max: f.max,
    step: f.step,
    "aria-describedby": helpId,
    oninput: () => {
      const n = input.valueAsNumber;
      if (Number.isFinite(n)) c.setValue(id, f.id, n);
      else c.setValue(id, f.id, Number.NaN);
    },
  });
  const help = h("p", { class: "help", id: helpId });
  return {
    field: f,
    el: h(
      "div",
      { class: "choice" },
      h("label", { class: "field-label", for: inputId, text: f.legend }),
      h("div", { class: "input-row" }, input, f.unit && h("span", { class: "input-unit", text: f.unit })),
      help,
    ),
    update() {
      const v = c.session(id).values[f.id];
      if (document.activeElement !== input) input.value = typeof v === "number" && Number.isFinite(v) ? String(v) : "";
      const bad = typeof v !== "number" || !Number.isFinite(v) || v < f.min || v > f.max;
      input.setAttribute("aria-invalid", bad ? "true" : "false");
      help.textContent = bad ? t.jv.screen.invalidChoices : f.help ?? "";
      help.classList.toggle("help-bad", bad);
      help.hidden = help.textContent === "";
    },
  };
}

function togglePart(c: JvController, id: JvToolId, f: ToggleField): Part {
  const inputId = nextId("jv-toggle");
  const helpId = nextId("jv-help");
  const input = h("input", {
    type: "checkbox",
    role: "switch",
    class: "switch",
    id: inputId,
    "aria-describedby": helpId,
    onchange: () => c.setValue(id, f.id, input.checked),
  });
  const help = h("p", { class: "help", id: helpId, text: f.help ?? "", hidden: !f.help });
  return {
    field: f,
    el: h("div", { class: "choice choice-toggle" }, h("div", { class: "switch-row" }, input, h("label", { for: inputId, text: f.label })), help),
    update() {
      input.checked = c.session(id).values[f.id] === true;
    },
  };
}

function textPart(c: JvController, id: JvToolId, f: TextField): Part {
  const inputId = nextId("jv-text");
  const helpId = nextId("jv-help");
  const input = h("input", {
    type: "text",
    class: "input",
    id: inputId,
    placeholder: f.placeholder,
    autocomplete: "off",
    spellcheck: false,
    "aria-describedby": helpId,
    oninput: () => c.setValue(id, f.id, input.value),
  });
  const help = h("p", { class: "help", id: helpId });
  return {
    field: f,
    el: h("div", { class: "choice" }, h("label", { class: "field-label", for: inputId, text: f.legend }), input, help),
    update() {
      const v = String(c.session(id).values[f.id] ?? "");
      if (document.activeElement !== input) input.value = v;
      const bad = !textValid(f, v);
      input.setAttribute("aria-invalid", bad ? "true" : "false");
      help.textContent = bad ? f.invalidHelp : f.help ?? "";
      help.classList.toggle("help-bad", bad);
      help.hidden = help.textContent === "";
    },
  };
}

function filePart(c: JvController, id: JvToolId, f: FileField): Part {
  const helpId = nextId("jv-help");
  const name = h("p", { class: "path", "aria-live": "polite" });
  const choose = h("button", {
    type: "button",
    class: "btn",
    text: t.jv.screen.pickFile,
    "aria-describedby": helpId,
    onclick: () => void c.chooseFieldFile(id, f),
  });
  const remove = h("button", {
    type: "button",
    class: "btn btn-quiet",
    text: t.jv.screen.removeChosenFile,
    onclick: () => c.setFieldFile(id, f.id, null),
  });
  const help = h("p", { class: "help", id: helpId, text: f.help ?? "", hidden: !f.help });
  return {
    field: f,
    el: h("div", { class: "choice choice-file" }, h("p", { class: "field-label", text: f.legend }), h("div", { class: "button-row" }, choose, remove), name, help),
    update() {
      const p = c.session(id).fieldFiles[f.id];
      name.textContent = p ? fileName(p) : "";
      name.hidden = !p;
      remove.hidden = !p;
    },
  };
}
