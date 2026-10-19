//! Verktøyregisteret. Hvert verktøy er en egen modul og en egen Tauri-plugin.
//! Et nytt verktøy legges til med én linje i `TOOLS` og én i `register`
//! (pluss mappen i frontend og oppføringen i `src/tools/registry.ts`, steg 2),
//! uten å røre de andre verktøyene.

pub mod transkribering;

// Journalistverktøyene. Spike (steg 6.1): ikke registrert ennå, ingen kommandoer.
pub mod jv;

use tauri::{Builder, Runtime};

/// ID-ene til verktøyene, i rekkefølgen de vises.
pub const TOOLS: &[&str] = &[transkribering::ID];

pub fn register<R: Runtime>(builder: Builder<R>) -> Builder<R> {
    builder.plugin(transkribering::plugin())
}
