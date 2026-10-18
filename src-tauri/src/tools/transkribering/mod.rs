//! Transkribering: lokal tale-til-tekst med NB-Whisper (whisper.cpp).
//!
//! Verktøyet er en egen Tauri-plugin (`transkribering`), så det kan legges til
//! eller fjernes i registeret (`tools/mod.rs`) uten å røre andre verktøy.
//!
//! Moduler:
//! - `decode`: symphonia + rubato, strømmende til 16 kHz mono.
//! - `chunk`: biter på ~10 min, tidskoder på tvers av biter, framdrift.
//! - `models`: `models.json`, modellvalg, modellmapper, SHA-256.
//! - `download`: nedlasting med gjenopptak (eneste nettkode i verktøyet).
//! - `engine`: whisper med framdrift, segmenter og avbryt.
//! - `export`: txt, srt, vtt, docx, filnavn og topptekst.
//! - `keepawake`: hindrer dvale under jobber.
//! - `system`: CPU-sjekk (AVX2), kjerner, minne.
//! - `jobs`: jobbtabell, avbryt og «opptatt».
//! - `commands`: Tauri-kommandoene og -hendelsene.

pub mod chunk;
pub mod commands;
pub mod decode;
pub mod download;
pub mod engine;
pub mod error;
pub mod export;
pub mod jobs;
pub mod keepawake;
pub mod models;
pub mod system;
pub mod types;

include!("command_names.rs");

use tauri::plugin::{Builder, TauriPlugin};
use tauri::{Manager, Runtime};

/// ID i verktøyregisteret og navnet på Tauri-pluginen.
pub const ID: &str = "transkribering";

pub fn plugin<R: Runtime>() -> TauriPlugin<R> {
    Builder::new(ID)
        .invoke_handler(tauri::generate_handler![
            commands::check_system,
            commands::list_models,
            commands::download_model,
            commands::delete_model,
            commands::set_model_dir,
            commands::transcribe,
            commands::cancel,
            commands::suggest_export_path,
            commands::export,
        ])
        .setup(|app, _api| {
            engine::silence_whisper_logging();
            let data_dir = app.path().app_data_dir()?;
            let state = commands::Transkribering::new(data_dir)?;
            app.manage(state);
            Ok(())
        })
        .build()
}

#[cfg(test)]
mod tests {
    #[test]
    fn command_list_matches_handler() {
        // generate_handler! over og listen build.rs bruker for tillatelser må være like.
        let src = include_str!("mod.rs");
        let start = src.find("generate_handler![").unwrap();
        let end = start + src[start..].find("])").unwrap();
        let handled: Vec<&str> = src[start..end]
            .split("commands::")
            .skip(1)
            .map(|s| s.split(',').next().unwrap().trim())
            .collect();
        assert_eq!(handled, super::TRANSKRIBERING_COMMANDS);
    }

    #[test]
    fn capability_grants_the_plugin() {
        let cap = include_str!("../../../capabilities/default.json");
        assert!(cap.contains("\"transkribering:default\""));
    }
}
