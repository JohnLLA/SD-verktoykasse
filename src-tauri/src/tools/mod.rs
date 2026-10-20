//! Verktøyregisteret. Hvert verktøy er en egen modul og en egen Tauri-plugin.
//! Et nytt verktøy legges til med én linje i `TOOLS` og én i `register`
//! (pluss mappen i frontend og oppføringen i `src/tools/registry.ts`, steg 2),
//! uten å røre de andre verktøyene.

pub mod transkribering;

// Journalistverktøyene: én plugin (`jv`) for katalog, nedlasting og kjøring av
// de ti verktøypakkene. Menyoppføringene lages i frontend (steg 6.3).
pub mod jv;

use tauri::{Builder, Runtime};

/// ID-ene til verktøyene, i rekkefølgen de vises.
pub const TOOLS: &[&str] = &[transkribering::ID];

pub fn register<R: Runtime>(builder: Builder<R>) -> Builder<R> {
    builder
        .plugin(transkribering::plugin())
        .plugin(jv::plugin())
}
