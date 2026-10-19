// SPDX-License-Identifier: AGPL-3.0-or-later
//! Logikken bak jv-kommandoene, uten Tauri, så den kan testes direkte.
//!
//! Mapper i appens datamappe:
//!
//! ```text
//! verktoy/<id>/<versjon>/        installert pakke (jv-package.json, jv-<id>.app …)
//! verktoy/<id>/.ny-<versjon>/    under kontroll; flyttes på plass først etter prøvekjøring
//! verktoy/.nedlasting/           jv-<id>-<versjon>-<target>.bin(.part), gjenopptas
//! verktoy/.katalog/              siste kontrollerte tools.json og tools.json.sig
//! ```
//!
//! Nett: bare [`Jv::catalog`] med `fetch = true` og [`Jv::install`], og bare
//! når brukeren ber om det. Ingenting hentes ved oppstart eller i bakgrunnen.

use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

use serde::Serialize;

use crate::tools::transkribering::download::HostPolicy;

use super::args::{build_args, RunRequest};
use super::catalog::{
    self, Availability, Catalog, CatalogEntry, CURRENT_TARGET, KNOWN_TOOLS, MAX_CATALOG_BYTES,
};
use super::error::{JvError, JvResult};
use super::package::{self, SignatureCheck};
use super::{net, runner};

pub type JobId = u64;

/// Lisensen for verktøyene selv (Om-vinduet). Tredjepartsdelene står i
/// `Lisenser/` i hver pakke.
pub const TOOL_LICENSE: &str = "AGPL-3.0-or-later";

const MAX_SIG_BYTES: usize = 4096;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ToolStatus {
    /// Kan lastes ned (eller er lastet ned).
    Available,
    NeedsNewerApp,
    NeedsNewerOs,
    /// «Kommer for Windows» (eller Mac): ingen linje for plattformen.
    NotForPlatform,
    /// Ingen kontrollert katalog ennå.
    Unknown,
}

#[derive(Debug, Clone, Serialize)]
pub struct ToolView {
    pub id: String,
    pub status: ToolStatus,
    /// Linjen fra katalogen for denne plattformen (navn, versjon, størrelse, notat).
    pub entry: Option<CatalogEntry>,
    pub installed_version: Option<String>,
    pub update_available: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CatalogSource {
    /// Nettopp hentet og kontrollert.
    Network,
    /// Siste kontrollerte kopi på disken.
    Cache,
    /// Ingen katalog.
    None,
}

#[derive(Debug, Clone, Serialize)]
pub struct CatalogView {
    pub target: &'static str,
    pub source: CatalogSource,
    /// Feilen ved henting (for eksempel ikke nett). Da vises siste kopi.
    pub error: Option<JvError>,
    pub tools: Vec<ToolView>,
}

#[derive(Debug, Clone, Serialize)]
pub struct InstalledView {
    pub id: String,
    pub name: String,
    pub version: String,
    pub bytes: u64,
    pub license: &'static str,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum InstallPhase {
    Download,
    /// SHA-256, utpakking, kodesignatur og prøvekjøring.
    Install,
}

struct Job {
    tool_id: String,
    cancel: Arc<AtomicBool>,
}

pub struct Jv {
    tools_dir: PathBuf,
    download_dir: PathBuf,
    catalog_dir: PathBuf,
    policy: HostPolicy,
    public_key: Option<String>,
    catalog_url: String,
    sig_url: String,
    app_version: String,
    os_version: Option<String>,
    signature: SignatureCheck<'static>,
    jobs: Mutex<HashMap<JobId, Job>>,
    next: AtomicU64,
}

/// macOS-versjonen (`sw_vers`), for `min_os` i katalogen. `None` på Windows.
pub fn os_version() -> Option<String> {
    #[cfg(target_os = "macos")]
    {
        let out = Command::new("/usr/bin/sw_vers")
            .arg("-productVersion")
            .env_clear()
            .output()
            .ok()?;
        let v = String::from_utf8(out.stdout).ok()?.trim().to_string();
        (!v.is_empty() && v.bytes().all(|b| b.is_ascii_digit() || b == b'.')).then_some(v)
    }
    #[cfg(not(target_os = "macos"))]
    {
        None
    }
}

pub struct Config {
    pub data_dir: PathBuf,
    pub app_version: String,
    pub os_version: Option<String>,
    pub public_key: Option<String>,
    pub catalog_url: String,
    pub sig_url: String,
    pub policy: HostPolicy,
    pub signature: SignatureCheck<'static>,
}

impl Config {
    /// Oppsettet appen bruker: release-repoet, katalognøkkelen og Developer ID-kravet.
    pub fn production(app_data_dir: PathBuf, app_version: String) -> Config {
        Config {
            data_dir: app_data_dir.join("verktoy"),
            app_version,
            os_version: os_version(),
            public_key: catalog::trusted_public_key().map(str::to_string),
            catalog_url: catalog::CATALOG_URL.into(),
            sig_url: catalog::CATALOG_SIG_URL.into(),
            policy: HostPolicy::https_only(catalog::RELEASE_HOSTS),
            signature: SignatureCheck::Team(package::TEAM_ID),
        }
    }
}

fn write_atomic(path: &Path, data: &[u8]) -> JvResult<()> {
    let tmp = path.with_extension("tmp");
    fs::write(&tmp, data)?;
    fs::rename(&tmp, path)?;
    Ok(())
}

impl Jv {
    pub fn new(cfg: Config) -> Jv {
        Jv {
            download_dir: cfg.data_dir.join(".nedlasting"),
            catalog_dir: cfg.data_dir.join(".katalog"),
            tools_dir: cfg.data_dir,
            policy: cfg.policy,
            public_key: cfg.public_key,
            catalog_url: cfg.catalog_url,
            sig_url: cfg.sig_url,
            app_version: cfg.app_version,
            os_version: cfg.os_version,
            signature: cfg.signature,
            jobs: Mutex::new(HashMap::new()),
            next: AtomicU64::new(1),
        }
    }

    fn key(&self) -> JvResult<&str> {
        self.public_key.as_deref().ok_or(JvError::CatalogKeyMissing)
    }

    // ------------------------------------------------------------ katalog

    /// Siste kontrollerte katalog på disken. Signaturen sjekkes på nytt hver gang.
    pub fn cached_catalog(&self) -> JvResult<Catalog> {
        let json =
            fs::read(self.catalog_dir.join("tools.json")).map_err(|_| JvError::CatalogMissing)?;
        let sig = fs::read_to_string(self.catalog_dir.join("tools.json.sig"))
            .map_err(|_| JvError::CatalogMissing)?;
        catalog::verify_and_parse(&json, &sig, self.key()?)
    }

    /// Henter, kontrollerer og lagrer katalogen. En katalog som er eldre enn den
    /// som allerede er kontrollert (signert tidsstempel), avvises.
    fn fetch_catalog(&self) -> JvResult<Catalog> {
        let key = self.key()?;
        let json = net::fetch_small(&self.policy, &self.catalog_url, MAX_CATALOG_BYTES)?;
        let sig = net::fetch_small(&self.policy, &self.sig_url, MAX_SIG_BYTES)?;
        let sig = String::from_utf8(sig).map_err(|_| JvError::CatalogSignature)?;
        let fresh = catalog::verify_and_parse(&json, &sig, key)?;
        if let Ok(old) = self.cached_catalog() {
            if fresh.signed_at < old.signed_at {
                return Err(JvError::CatalogOutdated);
            }
        }
        fs::create_dir_all(&self.catalog_dir)?;
        // Signaturen først: en halvskrevet katalog med gammel signatur avvises ved lesing.
        write_atomic(&self.catalog_dir.join("tools.json.sig"), sig.as_bytes())?;
        write_atomic(&self.catalog_dir.join("tools.json"), &json)?;
        Ok(fresh)
    }

    /// `fetch = false`: bare siste kontrollerte kopi, ingen nett.
    /// `fetch = true`: hent fra nett; feiler det, brukes siste kopi og feilen sendes med.
    pub fn catalog(&self, fetch: bool) -> CatalogView {
        let (cat, source, error) = if fetch {
            match self.fetch_catalog() {
                Ok(c) => (Some(c), CatalogSource::Network, None),
                Err(e) => match self.cached_catalog() {
                    Ok(c) => (Some(c), CatalogSource::Cache, Some(e)),
                    Err(_) => (None, CatalogSource::None, Some(e)),
                },
            }
        } else {
            match self.cached_catalog() {
                Ok(c) => (Some(c), CatalogSource::Cache, None),
                Err(JvError::CatalogMissing) => (None, CatalogSource::None, None),
                Err(e) => (None, CatalogSource::None, Some(e)),
            }
        };
        let tools = KNOWN_TOOLS
            .iter()
            .map(|id| {
                let installed = package::installed(&self.tools_dir, id).map(|i| i.manifest.version);
                let (status, entry) = match &cat {
                    None => (ToolStatus::Unknown, None),
                    Some(c) => match c.availability(
                        id,
                        CURRENT_TARGET,
                        &self.app_version,
                        self.os_version.as_deref(),
                    ) {
                        Availability::Available(e) => (ToolStatus::Available, Some(e.clone())),
                        Availability::NeedsNewerApp(e) => {
                            (ToolStatus::NeedsNewerApp, Some(e.clone()))
                        }
                        Availability::NeedsNewerOs(e) => {
                            (ToolStatus::NeedsNewerOs, Some(e.clone()))
                        }
                        Availability::NotForPlatform => (ToolStatus::NotForPlatform, None),
                    },
                };
                let update_available = status == ToolStatus::Available
                    && match (&installed, &entry) {
                        (Some(have), Some(e)) => !catalog::version_at_least(have, &e.version),
                        _ => false,
                    };
                ToolView {
                    id: id.to_string(),
                    status,
                    entry,
                    installed_version: installed,
                    update_available,
                }
            })
            .collect();
        CatalogView {
            target: CURRENT_TARGET,
            source,
            error,
            tools,
        }
    }

    // ------------------------------------------------------------ installert

    pub fn installed(&self) -> Vec<InstalledView> {
        KNOWN_TOOLS
            .iter()
            .filter_map(|id| package::installed(&self.tools_dir, id))
            .map(|i| InstalledView {
                id: i.manifest.id.clone(),
                name: i
                    .manifest
                    .name
                    .clone()
                    .unwrap_or_else(|| i.manifest.id.clone()),
                version: i.manifest.version.clone(),
                bytes: package::dir_size(&i.root),
                license: TOOL_LICENSE,
            })
            .collect()
    }

    // ------------------------------------------------------------ jobber

    fn check_id(id: &str) -> JvResult<()> {
        if KNOWN_TOOLS.contains(&id) {
            Ok(())
        } else {
            Err(JvError::UnknownTool)
        }
    }

    /// Registrerer en jobb for verktøyet. Ett verktøy har høyst én jobb om gangen
    /// (nedlasting, kjøring eller fjerning).
    pub fn begin(&self, tool_id: &str) -> JvResult<(JobId, Arc<AtomicBool>)> {
        Self::check_id(tool_id)?;
        let mut jobs = self.jobs.lock().unwrap_or_else(|e| e.into_inner());
        if jobs.values().any(|j| j.tool_id == tool_id) {
            return Err(JvError::Busy);
        }
        let id = self.next.fetch_add(1, Ordering::SeqCst);
        let cancel = Arc::new(AtomicBool::new(false));
        jobs.insert(
            id,
            Job {
                tool_id: tool_id.to_string(),
                cancel: cancel.clone(),
            },
        );
        Ok((id, cancel))
    }

    pub fn end(&self, job: JobId) {
        self.jobs
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .remove(&job);
    }

    /// Setter avbryt-flagget. Nedlastingen stopper ved neste bit og beholder
    /// `.part`; en kjøring drepes med hele prosesstreet.
    pub fn cancel(&self, job: JobId) -> bool {
        match self
            .jobs
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .get(&job)
        {
            Some(j) => {
                j.cancel.store(true, Ordering::SeqCst);
                true
            }
            None => false,
        }
    }

    // ------------------------------------------------------------ installer

    /// Linjen i (siste kontrollerte) katalog for verktøyet, hvis den kan installeres her.
    pub fn installable_entry(&self, id: &str) -> JvResult<CatalogEntry> {
        Self::check_id(id)?;
        let cat = self.cached_catalog()?;
        match cat.availability(
            id,
            CURRENT_TARGET,
            &self.app_version,
            self.os_version.as_deref(),
        ) {
            Availability::Available(e) => Ok(e.clone()),
            Availability::NotForPlatform => Err(JvError::NotForPlatform),
            Availability::NeedsNewerApp(e) => Err(JvError::NeedsNewerApp {
                min_app_version: e.min_app_version.clone(),
            }),
            Availability::NeedsNewerOs(e) => Err(JvError::NeedsNewerOs {
                min_os: e.min_os.clone().unwrap_or_default(),
            }),
        }
    }

    /// Laster ned og installerer (blokkerer; kalles fra en egen tråd).
    /// Returnerer den installerte versjonen.
    pub fn install(
        &self,
        id: &str,
        cancel: &AtomicBool,
        progress: &mut dyn FnMut(InstallPhase, u64, u64),
    ) -> JvResult<String> {
        let entry = self.installable_entry(id)?;
        self.policy.check(&entry.url).map_err(JvError::from)?;
        let archive = package::download_package(
            &entry,
            &self.download_dir,
            &self.policy,
            cancel,
            &mut |done, total| progress(InstallPhase::Download, done, total),
        )?;
        progress(InstallPhase::Install, 0, 0);
        match package::install(&entry, &archive, &self.tools_dir, self.signature, cancel) {
            Ok(_) => Ok(entry.version),
            Err(e) => {
                // En kontrollert, men ubrukelig pakke lastes ned på nytt neste gang.
                if e != JvError::Cancelled {
                    let _ = fs::remove_file(&archive);
                }
                Err(e)
            }
        }
    }

    /// Fjerner verktøyet og påbegynte nedlastinger av det.
    pub fn remove(&self, id: &str) -> JvResult<()> {
        let (job, _) = self.begin(id)?;
        let result = (|| -> JvResult<()> {
            let dir = self.tools_dir.join(id);
            if dir.exists() {
                fs::remove_dir_all(&dir)?;
            }
            let prefix = format!("jv-{id}-");
            if let Ok(rd) = fs::read_dir(&self.download_dir) {
                for e in rd.flatten() {
                    let name = e.file_name().to_string_lossy().into_owned();
                    // «jv-pdf-tables-…» skal ikke treffe et verktøy som heter «pdf».
                    let rest = name.strip_prefix(&prefix);
                    if rest.is_some_and(|r| r.starts_with(|c: char| c.is_ascii_digit())) {
                        let _ = fs::remove_file(e.path());
                    }
                }
            }
            Ok(())
        })();
        self.end(job);
        result
    }

    // ------------------------------------------------------------ kjør

    /// Bygger kommandoen for en kjøring: installert pakke, kodesignatur (Mac),
    /// argumenter fra hvitelisten og rent miljø.
    pub fn prepare_run(&self, id: &str, req: &RunRequest) -> JvResult<Command> {
        Self::check_id(id)?;
        let inst = package::installed(&self.tools_dir, id).ok_or(JvError::NotInstalled)?;
        // Mac: en pakke med ødelagt signatur kjøres ikke (sjekkes ved hver kjøring).
        package::verify_codesign(&inst.root, &inst.manifest, self.signature)?;
        let args = build_args(id, req)?;
        Ok(runner::command(&inst.root, &inst.manifest, &args))
    }

    #[cfg(test)]
    pub fn tools_dir(&self) -> &Path {
        &self.tools_dir
    }
}
