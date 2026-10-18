// Kobler feilkodene fra Rust-kjernen til tekster på norsk. Brukeren får aldri
// se rå feilmeldinger eller stakkspor, bare tittel og råd fra språkfilen.

import { ERROR_CODES, type CoreError } from "../tools/transkribering/api";
import { t, type ErrorText } from "../i18n/nb";

const KNOWN = new Set<string>(ERROR_CODES);

/** Gjør alt som kan komme fra `invoke` (objekt, tekst, Error) om til en `CoreError`. */
export function toCoreError(e: unknown): CoreError {
  if (e && typeof e === "object" && "code" in e) {
    const code = (e as { code: unknown }).code;
    if (typeof code === "string" && KNOWN.has(code)) return e as CoreError;
  }
  return { code: "internal" };
}

export function isCancelled(e: CoreError): boolean {
  return e.code === "cancelled";
}

/** Tittel og råd for en feil. Ukjente koder gir den generelle meldingen. */
export function errorText(e: CoreError): ErrorText {
  const make = t.errors[e.code] as ((err: CoreError) => ErrorText) | undefined;
  return make ? make(e) : t.common.unknownError;
}

/** Tittel og råd som én tekst, til steder med liten plass. */
export function errorSentence(e: CoreError): string {
  const { title, hint } = errorText(e);
  return hint ? `${title}. ${hint}` : title;
}
