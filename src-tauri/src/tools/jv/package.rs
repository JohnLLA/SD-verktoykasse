// SPDX-License-Identifier: AGPL-3.0-or-later
//! En installert verktøypakke: `jv-package.json`, miljø, kodesignatur,
//! prøvekjøring, installasjon og kjøring.
//!
//! Lagring: `<appdata>/verktoy/<id>/<versjon>/`. En ny versjon pakkes ut i
//! `<appdata>/verktoy/<id>/.ny-<versjon>/`, kontrolleres og prøvekjøres der, og
//! flyttes på plass først etterpå. Eldre versjoner slettes til slutt.

use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
#[cfg(target_os = "macos")]
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::Deserialize;
use sha2::{Digest, Sha256};

use super::archive;
use super::catalog::CatalogEntry;
use super::error::{JvError, JvResult};
use super::runner;
use crate::tools::transkribering::download::{self, HostPolicy};
use crate::tools::transkribering::models::{hex, ModelDirs, ModelEntry, VerifyCache};

pub const MANIFEST: &str = "jv-package.json";

/// Developer ID-teamet som skal ha signert pakkene (Mac).
pub const TEAM_ID: &str = "4F539U49GA";

#[derive(Debug, Clone, Deserialize)]
#[serde(untagged)]
pub enum EnvValue {
    One(String),
    Many(Vec<String>),
}

#[derive(Debug, Clone, Deserialize)]
pub struct Manifest {
    pub schema: u32,
    pub id: String,
    #[serde(default)]
    pub name: Option<String>,
    pub version: String,
    pub target: String,
    pub entry: String,
    #[serde(default)]
    pub path: Vec<String>,
    #[serde(default)]
    pub env: BTreeMap<String, EnvValue>,
    #[serde(default)]
    pub codesign: Vec<String>,
    #[serde(default)]
    pub min_os: Option<String>,
}

/// Variabler en pakke aldri får sette selv. Sammenlignes uten hensyn til store
/// og små bokstaver, siden Windows ikke skiller (`SYSTEMROOT` = `SystemRoot`).
const FORBIDDEN_ENV_PREFIXES: &[&str] = &["DYLD_", "LD_", "PYTHON", "PERL5", "_MEI", "PYI_"];
const FORBIDDEN_ENV: &[&str] = &[
    "PATH",
    "HOME",
    "TMPDIR",
    "TEMP",
    "TMP",
    "SystemRoot",
    "windir",
    "ComSpec",
    "PATHEXT",
    "USERPROFILE",
    "LOCALAPPDATA",
    "APPDATA",
    "__COMPAT_LAYER",
];

fn rel_ok(rel: &str) -> bool {
    !rel.is_empty()
        && !rel.starts_with('/')
        && !rel.contains('\\')
        && !rel.contains(':')
        && rel.split('/').all(|p| p != ".." && !p.is_empty())
}

pub fn read_manifest(root: &Path) -> JvResult<Manifest> {
    let mut text = String::new();
    fs::File::open(root.join(MANIFEST))
        .map_err(|_| JvError::ManifestInvalid { reason: "missing" })?
        .take(256 * 1024)
        .read_to_string(&mut text)
        .map_err(|_| JvError::ManifestInvalid { reason: "read" })?;
    let m: Manifest =
        serde_json::from_str(&text).map_err(|_| JvError::ManifestInvalid { reason: "json" })?;
    if m.schema != 1 {
        return Err(JvError::ManifestInvalid { reason: "schema" });
    }
    let all_paths = std::iter::once(&m.entry)
        .chain(m.path.iter())
        .chain(m.codesign.iter())
        .chain(m.env.values().flat_map(|v| match v {
            EnvValue::One(s) => std::slice::from_ref(s).iter(),
            EnvValue::Many(v) => v.iter(),
        }));
    for p in all_paths {
        if !rel_ok(p) {
            return Err(JvError::ManifestInvalid { reason: "path" });
        }
    }
    for name in m.env.keys() {
        let valid = !name.is_empty()
            && name
                .bytes()
                .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || b == b'_');
        if !valid
            || FORBIDDEN_ENV.iter().any(|f| f.eq_ignore_ascii_case(name))
            || FORBIDDEN_ENV_PREFIXES.iter().any(|p| name.starts_with(p))
        {
            return Err(JvError::ManifestInvalid { reason: "env" });
        }
    }
    Ok(m)
}

pub fn join_rel(root: &Path, rel: &str) -> PathBuf {
    rel.split('/').fold(root.to_path_buf(), |p, s| p.join(s))
}

/// Miljøet en pakke kjøres med: tomt, så bare PATH (pakkens mapper og
/// systemet), HOME, TMPDIR (Windows: SystemRoot, TEMP, TMP, USERPROFILE) og
/// pakkens egne variabler. Brukerens PATH, DYLD_* og PYTHON* slipper aldri inn.
pub fn command_env(root: &Path, m: &Manifest) -> Vec<(String, OsString)> {
    let mut out: Vec<(String, OsString)> = Vec::new();
    let mut path: Vec<PathBuf> = m.path.iter().map(|p| join_rel(root, p)).collect();
    #[cfg(windows)]
    {
        let sys = std::env::var_os("SystemRoot").unwrap_or_else(|| "C:\\Windows".into());
        path.push(PathBuf::from(&sys).join("System32"));
        path.push(PathBuf::from(&sys));
        for name in [
            "SystemRoot",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA",
        ] {
            if let Some(v) = std::env::var_os(name) {
                out.push((name.into(), v));
            }
        }
    }
    #[cfg(not(windows))]
    {
        for p in ["/usr/bin", "/bin", "/usr/sbin", "/sbin"] {
            path.push(PathBuf::from(p));
        }
        for name in ["HOME", "TMPDIR"] {
            if let Some(v) = std::env::var_os(name) {
                out.push((name.into(), v));
            }
        }
    }
    if let Ok(joined) = std::env::join_paths(&path) {
        out.push(("PATH".into(), joined));
    }
    for (name, value) in &m.env {
        let parts: Vec<PathBuf> = match value {
            EnvValue::One(s) => vec![join_rel(root, s)],
            EnvValue::Many(v) => v.iter().map(|s| join_rel(root, s)).collect(),
        };
        if let Ok(joined) = std::env::join_paths(&parts) {
            out.push((name.clone(), joined));
        }
    }
    out
}

/// Hvor streng kodesignatursjekken er.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SignatureCheck<'a> {
    /// Developer ID fra dette teamet (det appen bruker).
    Team(&'a str),
    /// Bare tester med falske pakker: ingen sjekk.
    #[cfg(test)]
    SkipForTests,
}

/// Mac: `codesign --verify --deep --strict` på hver bunt i `codesign`, med krav
/// om Developer ID fra teamet. `entry` må ligge inne i en av buntene, ellers
/// kunne en usignert fil bli kjørt.
#[cfg(target_os = "macos")]
// Utenfor tester har SignatureCheck bare én variant.
#[allow(clippy::infallible_destructuring_match)]
pub fn verify_codesign(root: &Path, m: &Manifest, check: SignatureCheck) -> JvResult<()> {
    let team = match check {
        SignatureCheck::Team(t) => t,
        #[cfg(test)]
        SignatureCheck::SkipForTests => return Ok(()),
    };
    let entry_covered = m
        .codesign
        .iter()
        .any(|b| m.entry.starts_with(&format!("{b}/")));
    if m.codesign.is_empty() || !entry_covered {
        return Err(JvError::CodeSignature);
    }
    for rel in &m.codesign {
        let ok = Command::new("/usr/bin/codesign")
            .args(["--verify", "--deep", "--strict"])
            .arg(format!(
                "-R=anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] exists \
                 and certificate leaf[field.1.2.840.113635.100.6.1.13] exists \
                 and certificate leaf[subject.OU] = \"{team}\""
            ))
            .arg(join_rel(root, rel))
            .env_clear()
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false);
        if !ok {
            return Err(JvError::CodeSignature);
        }
    }
    Ok(())
}

/// Windows: ingen kontroll ennå. Pakkene er usignert til LLA har sertifikat
/// («Windows: binærfilene signeres når LLA har sertifikat. Til da er de
/// usignert», spesifikasjonen). Spesifikasjonen sier ikke hvordan appen skal
/// kontrollere Authenticode, og det finnes ingen godkjent crate for det
/// (WinVerifyTrust). `jv-package.json` for Windows har derfor `codesign: []`.
/// Integriteten hviler på signert katalog og SHA-256 på pakken, som på Mac.
#[cfg(not(target_os = "macos"))]
pub fn verify_codesign(_root: &Path, _m: &Manifest, _check: SignatureCheck) -> JvResult<()> {
    Ok(())
}

#[derive(Debug, Deserialize)]
pub struct VersionInfo {
    pub id: String,
    pub version: String,
}

/// Prøvekjøring: `--version` må gi kode 0 og riktig id og versjon innen to minutter.
pub fn trial_run(root: &Path, m: &Manifest) -> JvResult<VersionInfo> {
    let cmd = runner::command(root, m, &["--version".into()]);
    let never = AtomicBool::new(false);
    match runner::run_job(cmd, &never, Some(Duration::from_secs(120)), &mut |_| {})? {
        runner::Finished::Report(v) => {
            let v: VersionInfo = serde_json::from_value(v).map_err(|_| JvError::TrialRunFailed)?;
            if v.id != m.id || v.version != m.version {
                return Err(JvError::TrialRunFailed);
            }
            Ok(v)
        }
        _ => Err(JvError::TrialRunFailed),
    }
}

pub fn sha256_file(path: &Path) -> JvResult<(String, u64)> {
    let mut f = fs::File::open(path)?;
    let mut h = Sha256::new();
    let mut buf = vec![0u8; 1 << 20];
    let mut n_total = 0u64;
    loop {
        let n = f.read(&mut buf)?;
        if n == 0 {
            break;
        }
        h.update(&buf[..n]);
        n_total += n as u64;
    }
    Ok((hex(&h.finalize()), n_total))
}

/// Navnet nedlastingen får i nedlastingsmappen (`<navn>.bin.part` under
/// nedlasting, `<navn>.bin` når SHA-256 stemmer).
pub fn download_name(entry: &CatalogEntry) -> String {
    format!("jv-{}-{}-{}", entry.id, entry.version, entry.target)
}

/// Laster ned pakken med koden fra modellnedlastingen (gjenopptak, biter,
/// SHA-256, fremdrift). Returnerer stien til den kontrollerte filen. En avbrutt
/// nedlasting blir liggende som `.part` og fortsetter neste gang.
pub fn download_package(
    entry: &CatalogEntry,
    download_dir: &Path,
    policy: &HostPolicy,
    cancel: &AtomicBool,
    progress: download::ProgressFn,
) -> JvResult<PathBuf> {
    let model_entry = ModelEntry {
        id: download_name(entry),
        variant: "jv".into(),
        style: None,
        size: String::new(),
        quant: String::new(),
        repo: String::new(),
        revision: String::new(),
        file: String::new(),
        url: entry.url.clone(),
        bytes: entry.bytes,
        sha256: entry.sha256.clone(),
        note: None,
    };
    let dirs = ModelDirs {
        app_dir: download_dir.to_path_buf(),
        custom_dir: None,
    };
    let cache = Mutex::new(VerifyCache::default());
    download::download_model(&model_entry, &dirs, policy, &cache, cancel, progress)
        .map_err(JvError::from)
}

#[derive(Debug, Default, Clone)]
pub struct InstallTimes {
    pub sha256: Duration,
    pub extract: Duration,
    pub codesign: Duration,
    pub trial_run: Duration,
}

/// Installerer en nedlastet pakke. Rekkefølgen er fast:
/// SHA-256 → utpakking i midlertidig mappe → manifest mot katalogen →
/// kodesignatur (Mac) → `--version` → flytt på plass → slett eldre versjoner.
/// Feiler et steg (eller avbryter brukeren), slettes den midlertidige mappen og
/// den gamle versjonen står urørt.
pub fn install(
    entry: &CatalogEntry,
    archive: &Path,
    tools_dir: &Path,
    check: SignatureCheck,
    cancel: &AtomicBool,
) -> JvResult<(PathBuf, InstallTimes)> {
    let cancelled = || -> JvResult<()> {
        if cancel.load(Ordering::SeqCst) {
            Err(JvError::Cancelled)
        } else {
            Ok(())
        }
    };
    let mut times = InstallTimes::default();
    let t = Instant::now();
    let (sum, len) = sha256_file(archive)?;
    times.sha256 = t.elapsed();
    if sum != entry.sha256 || len != entry.bytes {
        let _ = fs::remove_file(archive);
        return Err(JvError::ChecksumMismatch);
    }
    let tool_dir = tools_dir.join(&entry.id);
    fs::create_dir_all(&tool_dir)?;
    let staging = tool_dir.join(format!(".ny-{}", entry.version));
    if staging.exists() {
        fs::remove_dir_all(&staging)?;
    }
    fs::create_dir_all(&staging)?;
    let result = (|| -> JvResult<()> {
        cancelled()?;
        let t = Instant::now();
        archive::extract(archive, &staging)?;
        cancelled()?;
        times.extract = t.elapsed();
        let m = read_manifest(&staging)?;
        if m.id != entry.id || m.version != entry.version || m.target != entry.target {
            return Err(JvError::ManifestInvalid { reason: "mismatch" });
        }
        let t = Instant::now();
        verify_codesign(&staging, &m, check)?;
        times.codesign = t.elapsed();
        cancelled()?;
        let t = Instant::now();
        trial_run(&staging, &m)?;
        times.trial_run = t.elapsed();
        cancelled()
    })();
    if let Err(e) = result {
        let _ = fs::remove_dir_all(&staging);
        return Err(e);
    }
    let final_dir = tool_dir.join(&entry.version);
    if final_dir.exists() {
        // Samme versjon på nytt (reparasjon): bytt ut.
        let old = tool_dir.join(format!(".gammel-{}", entry.version));
        let _ = fs::remove_dir_all(&old);
        fs::rename(&final_dir, &old)?;
        fs::rename(&staging, &final_dir)?;
        let _ = fs::remove_dir_all(&old);
    } else {
        fs::rename(&staging, &final_dir)?;
    }
    // Eldre versjoner slettes først nå, etter vellykket prøvekjøring.
    for e in fs::read_dir(&tool_dir)?.flatten() {
        if e.file_name() != std::ffi::OsStr::new(&entry.version) {
            let _ = fs::remove_dir_all(e.path());
        }
    }
    let _ = fs::remove_file(archive);
    Ok((final_dir, times))
}

/// Et installert verktøy.
#[derive(Debug, Clone)]
pub struct Installed {
    pub root: PathBuf,
    pub manifest: Manifest,
}

/// Den installerte versjonen av `id` i `tools_dir/<id>/<versjon>/`, eller `None`.
/// Mapper som begynner med «.» (under installasjon) telles ikke. Finnes flere
/// versjoner (skal ikke skje), brukes den høyeste.
pub fn installed(tools_dir: &Path, id: &str) -> Option<Installed> {
    let dir = tools_dir.join(id);
    let mut best: Option<Installed> = None;
    for e in fs::read_dir(&dir).ok()?.flatten() {
        let name = e.file_name().to_string_lossy().into_owned();
        if name.starts_with('.') || !e.path().is_dir() {
            continue;
        }
        let Ok(m) = read_manifest(&e.path()) else {
            continue;
        };
        if m.id != id || m.version != name || m.target != super::catalog::CURRENT_TARGET {
            continue;
        }
        let newer = best
            .as_ref()
            .is_none_or(|b| !super::catalog::version_at_least(&b.manifest.version, &m.version));
        if newer {
            best = Some(Installed {
                root: e.path(),
                manifest: m,
            });
        }
    }
    best
}

/// Plass på disken (filer, ikke symlenker).
pub fn dir_size(p: &Path) -> u64 {
    let mut total = 0;
    if let Ok(rd) = fs::read_dir(p) {
        for e in rd.flatten() {
            let Ok(md) = e.path().symlink_metadata() else {
                continue;
            };
            if md.is_dir() {
                total += dir_size(&e.path());
            } else if md.is_file() {
                total += md.len();
            }
        }
    }
    total
}
