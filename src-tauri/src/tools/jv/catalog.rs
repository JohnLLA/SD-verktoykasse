// SPDX-License-Identifier: AGPL-3.0-or-later
//! `tools.json`: katalogen over verktøypakkene, signert med minisign.
//!
//! Rekkefølgen er fast: først signaturen (over de rå bytene), så JSON-en.
//! En katalog med feil signatur leses aldri. Bare forhåndshashede
//! signaturer («ED») godtas, ikke den gamle typen.

use minisign_verify::{PublicKey, Signature};
use serde::{Deserialize, Serialize};

use super::error::{JvError, JvResult};

/// Plattformene katalogen kjenner.
pub const TARGET_MAC: &str = "aarch64-apple-darwin";
pub const TARGET_WINDOWS: &str = "x86_64-pc-windows-msvc";

/// Plattformen denne appen er bygget for.
#[cfg(target_os = "macos")]
pub const CURRENT_TARGET: &str = TARGET_MAC;
#[cfg(not(target_os = "macos"))]
pub const CURRENT_TARGET: &str = TARGET_WINDOWS;

// =====================================================================
// KATALOGNØKKELEN – PLASSHOLDER. John Inge setter inn den offentlige nøkkelen.
//
// 1. Lag nøkkelparet (én gang, på egen maskin):   minisign -G -p katalog.pub -s katalog.key
// 2. Sikkerhetskopier katalog.key og passordet. Mistes nøkkelen, kan appene
//    ikke få nye verktøy før appen er oppdatert med en ny nøkkel.
// 3. Lim inn den andre linjen i katalog.pub (begynner med «RW…») mellom
//    anførselstegnene i PUBLIC_KEY under, og bygg appen på nytt.
//
// Den skal være en annen nøkkel enn oppdateringsnøkkelen i tauri.conf.json.
// Så lenge PUBLIC_KEY er tom, avviser appen alle kataloger (CatalogKeyMissing),
// med mindre appen er bygget med JV_CATALOG_PUBLIC_KEY=<nøkkel> (lokal beta,
// se sidecar/build/README.md).
// =====================================================================
pub const PUBLIC_KEY: &str = "";

/// Den offentlige nøkkelen appen stoler på: `JV_CATALOG_PUBLIC_KEY` ved bygging
/// (lokal beta) eller [`PUBLIC_KEY`]. `None` hvis ingen er satt.
pub fn trusted_public_key() -> Option<&'static str> {
    match option_env!("JV_CATALOG_PUBLIC_KEY") {
        Some(k) if !k.trim().is_empty() => Some(k.trim()),
        _ if !PUBLIC_KEY.trim().is_empty() => Some(PUBLIC_KEY.trim()),
        _ => None,
    }
}

/// Offentlig TESTNØKKEL (ikke hemmelig, se `sidecar/build/jvpack/catalog.py`).
/// Appen stoler bare på den i tester.
#[cfg(test)]
pub const TEST_PUBLIC_KEY: &str = "RWTFfRytwwVmgKnJsuxEairT7gRXXXln9Rww6j6VoszCOejDf1lKLaBj";

/// Katalogen ligger i den faste releasen `katalog` i release-repoet.
pub const CATALOG_URL: &str =
    "https://github.com/JohnLLA/lla-verktoykasse-releases/releases/download/katalog/tools.json";
pub const CATALOG_SIG_URL: &str =
    "https://github.com/JohnLLA/lla-verktoykasse-releases/releases/download/katalog/tools.json.sig";

/// Vertene katalogen og pakkene kan hentes fra: GitHub og CDN-et for vedlegg.
pub const RELEASE_HOSTS: &[&str] = &[
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
];

/// De ni journalistverktøyene, i menyrekkefølge.
pub const KNOWN_TOOLS: &[&str] = &[
    "compare",
    "metadata",
    "keyframes",
    "loudness",
    "subtitles",
    "pdf-tables",
    "ocr",
    "redact",
    "nynorsk",
];

/// Største katalog vi leser (den er noen få kB).
pub const MAX_CATALOG_BYTES: usize = 1024 * 1024;

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
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
    /// `timestamp:` fra den signerte kommentaren (sekunder). 0 hvis den mangler.
    #[serde(skip)]
    pub signed_at: u64,
}

/// Hva skjermen for et verktøy skal vise.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Availability<'a> {
    /// Pakken finnes for plattformen og passer med appversjonen.
    Available(&'a CatalogEntry),
    /// Pakken krever en nyere app.
    NeedsNewerApp(&'a CatalogEntry),
    /// Pakken krever en nyere versjon av operativsystemet (Mac: `min_os`).
    NeedsNewerOs(&'a CatalogEntry),
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
    let mut catalog: Catalog =
        serde_json::from_slice(json).map_err(|_| JvError::CatalogInvalid { reason: "json" })?;
    validate(&catalog)?;
    catalog.signed_at = signed_timestamp(sig.trusted_comment());
    Ok(catalog)
}

/// `timestamp:<sekunder>` fra den signerte kommentaren (minisign skriver den selv).
fn signed_timestamp(trusted_comment: &str) -> u64 {
    trusted_comment
        .split('\t')
        .find_map(|p| p.trim().strip_prefix("timestamp:"))
        .and_then(|v| v.trim().parse().ok())
        .unwrap_or(0)
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
        if e.min_os.as_deref().is_some_and(|v| !is_version(v)) {
            return Err(JvError::CatalogInvalid { reason: "version" });
        }
        // Bare https. Testene (full_chain) bruker en lokal testserver over http.
        let local_test = cfg!(test) && e.url.starts_with("http://127.0.0.1:");
        if !e.url.starts_with("https://") && !local_test {
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
    /// `os_version`: macOS-versjonen (`None` på Windows eller hvis ukjent;
    /// da sjekkes ikke `min_os`).
    pub fn availability<'a>(
        &'a self,
        id: &str,
        target: &str,
        app_version: &str,
        os_version: Option<&str>,
    ) -> Availability<'a> {
        match self.tools.iter().find(|e| e.id == id && e.target == target) {
            None => Availability::NotForPlatform,
            Some(e) if !version_at_least(app_version, &e.min_app_version) => {
                Availability::NeedsNewerApp(e)
            }
            Some(e)
                if matches!((os_version, e.min_os.as_deref()),
                    (Some(have), Some(need)) if !version_at_least(have, need)) =>
            {
                Availability::NeedsNewerOs(e)
            }
            Some(e) => Availability::Available(e),
        }
    }
}
