// Versjonssjekk: automatisk ved oppstart og manuelt fra Innstillinger.
// Er bryteren «Se etter ny versjon når appen starter» av, kalles ikke
// `checkForUpdate` (appen gjør ingen nettkall). Knappen «Se etter ny versjon
// nå» sjekker bare når den trykkes. Testet i update-check.test.ts.

import { loadVersionCheck } from "../lib/settings";
import type { Platform, UpdateCheckResult } from "../platform/types";
import type { UpdateNotice } from "./update-notice";

export interface UpdateCheckDeps {
  platform: Pick<Platform, "settings" | "checkForUpdate" | "checkForUpdateNow" | "installUpdate">;
  notice: Pick<UpdateNotice, "show" | "installing" | "failed">;
  /** Spør brukeren hvis noe pågår i appen. Gir `true` hvis oppdateringen kan starte. */
  confirmInstall: () => Promise<boolean>;
}

/** Viser varselet «Det finnes en ny versjon» og kobler «Oppdater nå» til installasjonen. */
function offer(deps: UpdateCheckDeps, version: string): void {
  const { platform, notice, confirmInstall } = deps;
  const install = async (): Promise<void> => {
    if (!(await confirmInstall())) return;
    notice.installing();
    if (!(await platform.installUpdate())) notice.failed(() => void install());
  };
  notice.show(version, () => void install());
}

/** Returnerer `true` hvis det ble spurt om ny versjon (bryteren var på). */
export async function runStartupUpdateCheck(deps: UpdateCheckDeps): Promise<boolean> {
  if (!(await loadVersionCheck(deps.platform.settings))) return false;
  const version = await deps.platform.checkForUpdate();
  if (version !== null) offer(deps, version);
  return true;
}

/** Knappen «Se etter ny versjon nå». Sjekker uansett bryteren. */
export async function runManualUpdateCheck(deps: UpdateCheckDeps): Promise<UpdateCheckResult> {
  const r = await deps.platform.checkForUpdateNow();
  if (r.status === "available") offer(deps, r.version);
  return r;
}
