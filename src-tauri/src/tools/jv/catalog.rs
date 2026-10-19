// SPDX-License-Identifier: AGPL-3.0-or-later
//! `tools.json`: katalogen over verktøypakkene, signert med minisign.
//!
//! Rekkefølgen er fast: først signaturen (over de rå bytene), så JSON-en.
//! En katalog med feil signatur leses aldri. Bare forhåndshashede
//! signaturer («ED») godtas, ikke den gamle typen.

use minisign_verify::{PublicKey, Signature};
use serde::Deserialize;

use super::error::{JvError, JvResult};

/// Plattformene katalogen kjenner.
pub const TARGET_MAC: &str = "aarch64-apple-darwin";
pub const TARGET_WINDOWS: &str = "x86_64-pc-windows-msvc";

/// Plattformen denne appen er bygget for.
#[cfg(target_os = "macos")]
pub const CURRENT_TARGET: &str = TARGET_MAC;
#[cfg(not(target_os = "macos"))]
pub const CURRENT_TARGET: &str = TARGET_WINDOWS;

/// Offentlig TESTNØKKEL (ikke hemmelig, se `sidecar/build/jvpack/catalog.py`).
/// Appen stoler bare på den i tester. Den ekte nøkkelen lages av John Inge og
/// bygges inn i steg 6.2; den er en annen enn oppdateringsnøkkelen.
#[cfg(test)]
pub const TEST_PUBLIC_KEY: &str = "RWTFfRytwwVmgKnJsuxEairT7gRXXXln9Rww6j6VoszCOejDf1lKLaBj";

/// Største katalog vi leser (den er noen få kB).
pub const MAX_CATALOG_BYTES: usize = 1024 * 1024;

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct CatalogEntry {
    pub id: String,
    pub name: String,
    pub version: String,
    pub target: String,
    pub url: String,
    pub bytes: u64,
    pub sha256: String,
    pub min_app_version: String,
    #[serde(default)]
    pub min_os: Option<String>,
    #[serde(default)]
    pub notes: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Catalog {
    pub schema: u32,
    pub tools: Vec<CatalogEntry>,
}

/// Hva skjermen for et verktøy skal vise.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Availability<'a> {
    /// Pakken finnes for plattformen og passer med appversjonen.
    Available(&'a CatalogEntry),
    /// Pakken krever en nyere app.
    NeedsNewerApp(&'a CatalogEntry),
    /// Ingen linje for plattformen: «Kommer for Windows» (eller Mac), ingen knapp.
    NotForPlatform,
}

/// Sjekker signaturen og leser katalogen. `public_key` er base64-linjen fra
/// minisigns `.pub`-fil.
pub fn verify_and_parse(json: &[u8], signature: &str, public_key: &str) -> JvResult<Catalog> {
    if json.len() > MAX_CATALOG_BYTES {
        return Err(JvError::CatalogInvalid {
            reason: "too_large",
        });
    }
    let pk = PublicKey::from_base64(public_key).map_err(|_| JvError::CatalogSignature)?;
    let sig = Signature::decode(signature).map_err(|_| JvError::CatalogSignature)?;
    pk.verify(json, &sig, false)
        .map_err(|_| JvError::CatalogSignature)?;
    let catalog: Catalog =
        serde_json::from_slice(json).map_err(|_| JvError::CatalogInvalid { reason: "json" })?;
    validate(&catalog)?;
    Ok(catalog)
}

fn is_id(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 32
        && s.bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}

fn is_version(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 32
        && s.bytes().all(|b| b.is_ascii_digit() || b == b'.')
        && !s.starts_with('.')
        && !s.ends_with('.')
}

fn validate(c: &Catalog) -> JvResult<()> {
    if c.schema != 1 {
        return Err(JvError::CatalogInvalid { reason: "schema" });
    }
    let mut seen = std::collections::HashSet::new();
    for e in &c.tools {
        if !is_id(&e.id) {
            return Err(JvError::CatalogInvalid { reason: "id" });
        }
        if !is_version(&e.version) || !is_version(&e.min_app_version) {
            return Err(JvError::CatalogInvalid { reason: "version" });
        }
        if e.target != TARGET_MAC && e.target != TARGET_WINDOWS {
            return Err(JvError::CatalogInvalid { reason: "target" });
        }
        if e.sha256.len() != 64
            || !e
                .sha256
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            return Err(JvError::CatalogInvalid { reason: "sha256" });
        }
        if e.bytes == 0 {
            return Err(JvError::CatalogInvalid { reason: "bytes" });
        }
        if !e.url.starts_with("https://") {
            return Err(JvError::CatalogInvalid { reason: "url" });
        }
        if !seen.insert((e.id.clone(), e.target.clone())) {
            return Err(JvError::CatalogInvalid {
                reason: "duplicate",
            });
        }
    }
    Ok(())
}

/// Sammenligner versjoner som «1.2.10» tall for tall.
pub fn version_at_least(have: &str, need: &str) -> bool {
    let parse = |s: &str| -> Vec<u64> { s.split('.').map(|p| p.parse().unwrap_or(0)).collect() };
    let (a, b) = (parse(have), parse(need));
    for i in 0..a.len().max(b.len()) {
        let (x, y) = (
            a.get(i).copied().unwrap_or(0),
            b.get(i).copied().unwrap_or(0),
        );
        if x != y {
            return x > y;
        }
    }
    true
}

impl Catalog {
    pub fn availability<'a>(
        &'a self,
        id: &str,
        target: &str,
        app_version: &str,
    ) -> Availability<'a> {
        match self.tools.iter().find(|e| e.id == id && e.target == target) {
            None => Availability::NotForPlatform,
            Some(e) if !version_at_least(app_version, &e.min_app_version) => {
                Availability::NeedsNewerApp(e)
            }
            Some(e) => Availability::Available(e),
        }
    }
}
