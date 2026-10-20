// SPDX-License-Identifier: AGPL-3.0-or-later
//! Journalistverktøyene (jv): katalog, nedlasting, kontroll, installasjon,
//! kjøring, avbryt og fjerning av verktøypakkene
//! (docs/spesifikasjon-journalistverktoy.md).
//!
//! Verktøyet er en egen Tauri-plugin (`jv`) med kommandoene i `commands`.
//!
//! - `catalog`: `tools.json` med minisign-signatur. Signaturen sjekkes før
//!   noe i katalogen leses. Den offentlige nøkkelen står i
//!   `catalog::PUBLIC_KEY`.
//! - `net`: henting av katalogen (bare https, bare vertene i release-repoet).
//! - `archive`: trygg utpakking. Systemets `tar` (bsdtar, finnes på macOS og
//!   Windows 10+) gjør arkivet om til en ukomprimert tar-strøm; all kontroll av
//!   stier, typer og symlenker skjer her i Rust.
//! - `package`: `jv-package.json`, miljøet, kodesignatur, prøvekjøring,
//!   nedlasting (koden fra modellnedlastingen i Transkribering) og installasjon.
//! - `plan`: planfilen fra `redact finn`, lest for visning og lagret med avkrysningene.
//! - `args`: argumentene fra en hviteliste per verktøy, aldri skall.
//! - `runner`: kjøring med fremdrift, rapport og avbryt av hele prosesstreet.
//! - `service`: logikken bak kommandoene (uten Tauri, testbar).
//! - `commands`: Tauri-kommandoene og -hendelsene.
//!
//! Ingenting her logger filnavn, filinnhold eller tekst fra verktøyene (regel 2).

pub mod archive;
pub mod args;
pub mod catalog;
pub mod commands;
pub mod error;
pub mod net;
pub mod package;
pub mod plan;
pub mod runner;
pub mod service;

include!("command_names.rs");

use tauri::plugin::{Builder, TauriPlugin};
use tauri::{Manager, Runtime};

/// Navnet på Tauri-pluginen.
pub const ID: &str = "jv";

pub fn plugin<R: Runtime>() -> TauriPlugin<R> {
    Builder::new(ID)
        .invoke_handler(tauri::generate_handler![
            commands::jv_catalog,
            commands::jv_installed,
            commands::jv_install,
            commands::jv_remove,
            commands::jv_run,
            commands::jv_cancel,
            commands::jv_read_plan,
            commands::jv_save_plan,
        ])
        .setup(|app, _api| {
            let data_dir = app.path().app_data_dir()?;
            let version = app.package_info().version.to_string();
            app.manage(service::Jv::new(service::Config::production(
                data_dir, version,
            )));
            Ok(())
        })
        .build()
}

#[cfg(test)]
mod tests;

#[cfg(test)]
mod plugin_tests {
    #[test]
    fn command_list_matches_handler() {
        let src = include_str!("mod.rs");
        let start = src.find("generate_handler![").unwrap();
        let end = start + src[start..].find("])").unwrap();
        let handled: Vec<&str> = src[start..end]
            .split("commands::")
            .skip(1)
            .map(|s| s.split(',').next().unwrap().trim())
            .collect();
        assert_eq!(handled, super::JV_COMMANDS);
    }

    #[test]
    fn capability_grants_only_the_plugin_and_no_shell_or_http() {
        let cap = include_str!("../../../capabilities/default.json");
        assert!(cap.contains("\"jv:default\""));
        for forbidden in ["shell:", "http:", "fs:"] {
            assert!(!cap.contains(forbidden), "{forbidden}");
        }
    }
}
