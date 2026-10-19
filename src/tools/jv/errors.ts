// Kobler jv-feilkodene til tekster på norsk. Brukeren ser aldri rå feilmeldinger.

import { t, type ErrorText } from "../../i18n/nb";
import type { JvError } from "./api";

export function jvErrorText(e: JvError): ErrorText {
  const make = t.jvErrors[e.code] as ((err: JvError) => ErrorText) | undefined;
  return make ? make(e) : t.common.unknownError;
}
