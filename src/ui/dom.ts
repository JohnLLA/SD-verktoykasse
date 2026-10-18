// Minimal DOM-hjelper. All tekst settes med `textContent`, aldri `innerHTML`,
// så filnavn og transkribert tekst aldri kan tolkes som kode.

type Prop = string | number | boolean | EventListener | null | undefined;
export type Props = Record<string, Prop>;
export type Child = Node | string | null | undefined | false;

const PROPERTY_KEYS = new Set(["value", "checked", "disabled", "hidden", "indeterminate", "src"]);

export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Props = {},
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.className = String(value);
    else if (key === "text") el.textContent = String(value);
    else if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (PROPERTY_KEYS.has(key)) {
      (el as unknown as Record<string, unknown>)[key] = value;
    } else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, String(value));
  }
  append(el, children);
  return el;
}

export function append(el: Element, children: readonly Child[]): void {
  for (const c of children) {
    if (c === null || c === undefined || c === false) continue;
    el.append(typeof c === "string" ? document.createTextNode(c) : c);
  }
}

export function clear(el: Element): void {
  el.replaceChildren();
}

export function replace(el: Element, ...children: Child[]): void {
  clear(el);
  append(el, children);
}

let uid = 0;
export function nextId(prefix: string): string {
  uid += 1;
  return `${prefix}-${uid}`;
}
