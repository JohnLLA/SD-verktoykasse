import type { Kvalitet, Malform, Stil } from "./api";
import { t } from "../../i18n/nb";

const c = t.transkribering.choices;

export const malformLabel = (m: Malform): string => c.malform[m];
export const stilLabel = (s: Stil): string => c.stil[s];
export const kvalitetLabel = (k: Kvalitet): string => c.kvalitet[k];
