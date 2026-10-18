// Kontrakten mellom skallet og verktøyene. Et nytt verktøy legges til med en
// mappe under `src/tools/`, en `ToolDefinition` og én linje i `registry.ts`,
// uten å endre de andre verktøyene (regel 6).

import type { Platform } from "../platform/types";

export interface ToolContext {
  platform: Platform;
  /** Kort beskjed til skjermlesere og en synlig melding nederst. */
  announce(message: string): void;
  /** Viser verktøyet (f.eks. når filer slippes i vinduet mens et annet vindu er åpent). */
  activate(): void;
}

export type Busy = "running" | "unsaved" | null;

export interface ToolInstance {
  /** Tegner verktøyets skjerm. Kalles én gang; skjermen beholdes når man bytter side. */
  mountScreen(root: HTMLElement): void;
  /** Tegner verktøyets del av Innstillinger. `refresh` kalles hver gang siden vises. */
  mountSettings?(root: HTMLElement): { refresh(): void };
  /** Starter opp (lytter på hendelser, leser innstillinger). */
  init?(): Promise<void>;
  /** Skjermen vises nå. */
  onShow?(): void;
  /** Pågår noe, eller er noe ikke lagret? Brukes når appen skal lukkes. */
  busy?(): Busy;
}

export interface ToolDefinition {
  /** Samme id som Rust-verktøyet (`src-tauri/src/tools/mod.rs`). */
  id: string;
  name: string;
  description: string;
  /** Navn på ikon i `ui/icons.ts`. */
  icon: string;
  create(ctx: ToolContext): ToolInstance;
}
