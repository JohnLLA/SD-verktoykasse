// SPDX-License-Identifier: AGPL-3.0-or-later
//! Journalistverktøyene (jv): katalog, nedlasting, kontroll, installasjon og
//! kjøring av verktøypakkene (docs/spesifikasjon-journalistverktoy.md).
//!
//! **Spike (steg 6.1).** Modulen er ikke registrert i `tools/mod.rs` og har
//! ingen Tauri-kommandoer ennå. Den viser at kjeden virker fra en Rust-test:
//! signert katalog → nedlasting (koden fra modellnedlastingen) → SHA-256 →
//! trygg utpakking → `codesign --verify` (Mac) → `--version` → kjøring på en
//! testfil. Kommandoene (`jv_catalog`, `jv_install` …) kommer i steg 6.2.
//!
//! - `catalog`: `tools.json` med minisign-signatur. Signaturen sjekkes før
//!   noe i katalogen leses.
//! - `archive`: trygg utpakking. Systemets `tar` (bsdtar, finnes på macOS og
//!   Windows 10+) gjør arkivet om til en ukomprimert tar-strøm; all kontroll av
//!   stier, typer og symlenker skjer her i Rust.
//! - `package`: `jv-package.json`, miljøet, kodesignatur, prøvekjøring,
//!   installasjon og kjøring.
//!
//! Ingenting her logger filnavn, filinnhold eller tekst fra verktøyene (regel 2).

pub mod archive;
pub mod catalog;
pub mod error;
pub mod package;

#[cfg(test)]
mod spike_tests;
