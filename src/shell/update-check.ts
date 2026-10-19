// Versjonssjekk ved oppstart. Er bryteren «Se etter ny versjon når appen
// starter» av, kalles `checkForUpdate` aldri, så appen gjør ingen nettkall.
// Testet i update-check.test.ts.

import { loadVersionCheck } from "../lib/settings";
import type { Platform } from "../platform/types";
import type { UpdateNotice } from "./update-notice";

export interface UpdateCheckDeps {
  platform: Pick<Platform, "settings" | "checkForUpdate" | "installUpdate">;
  notice: Pick<UpdateNotice, "show" | "installing" | "failed">;
  /** Spør brukeren hvis noe pågår i appen. Gir `true` hvis oppdateringen kan starte. */
  confirmInstall: () => Promise<boolean>;
}

/** Returnerer `true` hvis det ble spurt om ny versjon (bryteren var på). */
export async function runStartupUpdateCheck(deps: UpdateCheckDeps): Promise<boolean> {
  const { platform, notice, confirmInstall } = deps;
  if (!(await loadVersionCheck(platform.settings))) return false;

  const version = await platform.checkForUpdate();
  if (version === null) return true;

  const install = async (): Promise<void> => {
    if (!(await confirmInstall())) return;
    notice.installing();
    if (!(await platform.installUpdate())) notice.failed(() => void install());
  };
  notice.show(version, () => void install());
  return true;
}
