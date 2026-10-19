// Det grensesnittet trenger fra maskinen rundt seg: dialoger, dra-og-slipp,
// avspilling, utklippstavle, innstillinger. Tauri-versjonen ligger i
// `tauri.ts`; prøvevisningen (`src/dev`) bruker en annen. Alt i grensesnittet
// går gjennom dette, så logikken kan kjøres uten Tauri.

import type { Os } from "../lib/platform-info";
import type { SettingsStore } from "../lib/settings";

export interface SavePathOptions {
  title: string;
  /** Hel sti med foreslått filnavn. */
  defaultPath: string;
  /** Filendelse uten punktum, f.eks. `docx`. */
  extension: string;
  filterName: string;
}

export interface DropHandlers {
  /** Filer sluppet i vinduet. */
  onFiles(paths: string[]): void;
  /** Filer dras over vinduet (`true`) eller forlot det (`false`). */
  onHover(over: boolean): void;
}

export type UpdateCheckResult =
  | { status: "available"; version: string }
  | { status: "none" }
  | { status: "failed" };

export interface Platform {
  os: Os;
  settings: SettingsStore;
  /** Åpner filvelgeren. Tom liste hvis brukeren angrer. */
  pickFiles(opts: { title: string; filterName: string; extensions: string[] }): Promise<string[]>;
  pickFolder(title: string): Promise<string | null>;
  pickSavePath(opts: SavePathOptions): Promise<string | null>;
  /** Returnerer en funksjon som slutter å lytte. */
  onDrop(handlers: DropHandlers): Promise<() => void>;
  /** Adresse lydelementet kan spille av for en lokal fil, eller `null` hvis det ikke går. */
  playbackUrl(path: string): Promise<string | null>;
  /** Viser filen i Finder/Utforsker. */
  reveal(path: string): Promise<void>;
  copyText(text: string): Promise<boolean>;
  appVersion(): Promise<string | null>;
  /**
   * Spør om det finnes en nyere versjon. Gir versjonsnummeret, eller `null`
   * hvis det ikke finnes noen, sjekken feilet eller bryteren er av.
   * Det eneste nettkallet appen gjør uten at brukeren ber om det.
   */
  checkForUpdate(): Promise<string | null>;
  /**
   * Brukeren trykket «Se etter ny versjon nå». Gjør nettkallet uansett
   * hva bryteren for automatisk sjekk står på.
   */
  checkForUpdateNow(): Promise<UpdateCheckResult>;
  /** Laster ned og installerer funnet oppdatering, og starter appen på nytt. `false` ved feil. */
  installUpdate(): Promise<boolean>;
  /**
   * `guard` kalles når brukeren lukker vinduet. Gir den `false`, blir
   * vinduet åpent. Returnerer en funksjon som fjerner vakten.
   */
  onCloseRequested(guard: () => Promise<boolean>): Promise<() => void>;
}
