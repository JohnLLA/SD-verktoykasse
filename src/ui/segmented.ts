// Segmenterte knapper (radioknapper med knappeutseende). Pil-taster flytter
// valget, Tab hopper videre, skjermlesere leser «gruppe, valg 1 av 2».

import { h, nextId } from "./dom";

export interface SegmentedOption<V extends string> {
  value: V;
  label: string;
}

export interface Segmented<V extends string> {
  el: HTMLFieldSetElement;
  set(value: V): void;
}

export function segmented<V extends string>(opts: {
  legend: string;
  options: readonly SegmentedOption<V>[];
  value: V;
  onChange: (value: V) => void;
  /** Id til tekst som forklarer gruppen (aria-describedby). */
  describedBy?: string;
}): Segmented<V> {
  const name = nextId("seg");
  const inputs = new Map<V, HTMLInputElement>();
  const items = opts.options.map((o) => {
    const id = `${name}-${o.value}`;
    const input = h("input", {
      type: "radio",
      name,
      id,
      value: o.value,
      checked: o.value === opts.value,
      onchange: () => {
        if (input.checked) opts.onChange(o.value);
      },
    });
    inputs.set(o.value, input);
    return h("span", { class: "segc-item" }, input, h("label", { for: id, text: o.label }));
  });
  const el = h(
    "fieldset",
    { class: "segc", "aria-describedby": opts.describedBy },
    h("legend", { text: opts.legend }),
    h("div", { class: "segc-row" }, ...items),
  );
  return {
    el,
    set(value) {
      const input = inputs.get(value);
      if (input) input.checked = true;
    },
  };
}
