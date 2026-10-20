// SPDX-License-Identifier: AGPL-3.0-or-later
//! Tester for jv-modulen (utover enhetstestene i `archive`, `args` og `runner`).
//!
//! - Katalog: signatur (riktig, endret, feil nøkkel, tom), eldre katalog avvises,
//!   siste kopi brukes uten nett, «Kommer for Windows».
//! - Pakke: feil SHA-256, prøvekjøring som feiler, god pakke erstatter gammel,
//!   avbrutt og gjenopptatt nedlasting, avbryt under installasjon.
//! - Kjøring med en falsk pakke: rapport, feilmelding og avbryt. Den falske
//!   pakken er et sh-skript på Mac og et cmd-skript i en .zip på Windows, så
//!   testene går på begge plattformene.
//! - Miljøet en pakke kjøres med (`command_env`), også for Windows.
//! - `full_chain` (ignorert som standard; krever pakkene fra
//!   `sidecar/build/bygg-mac.sh` og en katalog laget for testserveren):
//!   katalog fra en lokal testserver → signatur → nedlasting med brudd og
//!   gjenopptak → SHA-256 → utpakking → codesign → `--version` → kjøring på en
//!   testfil, for alle verktøyene i katalogen. Skriver bare tall, aldri filnavn eller
//!   tekst fra verktøyene. Se `sidecar/build/README.md`.

use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde_json::json;

use super::args::RunRequest;
use super::catalog::{
    self, Availability, CURRENT_TARGET, TARGET_MAC, TARGET_WINDOWS, TEST_PUBLIC_KEY,
};
use super::error::JvError;
use super::package::{self, SignatureCheck};
use super::runner::{self, Finished};
use super::service::{CatalogSource, Config, InstallPhase, Jv, ToolStatus};
use crate::tools::transkribering::download::HostPolicy;

const CATALOG: &[u8] = include_bytes!("testdata/tools.json");
const CATALOG_SIG: &str = include_str!("testdata/tools.json.sig");
const CATALOG_NEW: &[u8] = include_bytes!("testdata/tools-ny.json");
const CATALOG_NEW_SIG: &str = include_str!("testdata/tools-ny.json.sig");

fn tmp(name: &str) -> PathBuf {
    static N: AtomicUsize = AtomicUsize::new(0);
    let d = std::env::temp_dir().join(format!(
        "jv-test-{name}-{}-{}-{}",
        std::process::id(),
        N.fetch_add(1, Ordering::SeqCst),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    std::fs::create_dir_all(&d).unwrap();
    d
}

// ------------------------------------------------------------- katalog

#[test]
fn catalog_with_valid_signature_is_read() {
    let c = catalog::verify_and_parse(CATALOG, CATALOG_SIG, TEST_PUBLIC_KEY).unwrap();
    assert_eq!(c.tools.len(), 2);
    assert_eq!(c.signed_at, 0);
    let n = catalog::verify_and_parse(CATALOG_NEW, CATALOG_NEW_SIG, TEST_PUBLIC_KEY).unwrap();
    assert!(n.signed_at > 1_700_000_000);
}

#[test]
fn catalog_with_one_changed_byte_is_rejected() {
    let mut bad = CATALOG.to_vec();
    let i = bad.iter().position(|&b| b == b'0').unwrap();
    bad[i] = b'1';
    assert_eq!(
        catalog::verify_and_parse(&bad, CATALOG_SIG, TEST_PUBLIC_KEY).unwrap_err(),
        JvError::CatalogSignature
    );
    // Riktig katalog med signaturen til en annen katalog.
    assert_eq!(
        catalog::verify_and_parse(CATALOG, CATALOG_NEW_SIG, TEST_PUBLIC_KEY).unwrap_err(),
        JvError::CatalogSignature
    );
}

#[test]
fn catalog_with_other_key_or_no_signature_is_rejected() {
    // Oppdateringsnøkkelen (tauri.conf.json) er en annen nøkkel og skal ikke virke.
    let updater_key = "RWQtJQJzou88KUXq4GmshwdmYlBMQLfGduEl9Ed9lBARY+TRZ9kPHGos";
    assert_eq!(
        catalog::verify_and_parse(CATALOG, CATALOG_SIG, updater_key).unwrap_err(),
        JvError::CatalogSignature
    );
    assert_eq!(
        catalog::verify_and_parse(CATALOG, "", TEST_PUBLIC_KEY).unwrap_err(),
        JvError::CatalogSignature
    );
}

#[test]
fn production_key_is_a_placeholder_until_john_inge_sets_it() {
    // Plassholderen er tom; appen stoler da ikke på noen katalog (CatalogKeyMissing),
    // med mindre den er bygget med JV_CATALOG_PUBLIC_KEY. Testnøkkelen er aldri med.
    assert_ne!(catalog::PUBLIC_KEY, TEST_PUBLIC_KEY);
    if let Some(k) = catalog::trusted_public_key() {
        assert_ne!(k, TEST_PUBLIC_KEY, "testnøkkelen skal aldri bygges inn");
    }
}

#[test]
fn tool_without_windows_line_is_coming_for_windows() {
    let c = catalog::verify_and_parse(CATALOG, CATALOG_SIG, TEST_PUBLIC_KEY).unwrap();
    // Runde A: katalogen har bare Mac-linjer.
    assert!(matches!(
        c.availability("subtitles", TARGET_MAC, "0.1.0", Some("14.5")),
        Availability::Available(_)
    ));
    assert_eq!(
        c.availability("subtitles", TARGET_WINDOWS, "0.1.0", None),
        Availability::NotForPlatform
    );
    assert_eq!(
        c.availability("nynorsk", TARGET_MAC, "0.1.0", None),
        Availability::NotForPlatform
    );
    assert!(matches!(
        c.availability("ocr", TARGET_MAC, "0.0.9", None),
        Availability::NeedsNewerApp(_)
    ));
    // ocr krever macOS 14 i testkatalogen.
    assert!(matches!(
        c.availability("ocr", TARGET_MAC, "0.1.0", Some("13.6.1")),
        Availability::NeedsNewerOs(_)
    ));
    assert!(matches!(
        c.availability("ocr", TARGET_MAC, "0.1.0", Some("14.0")),
        Availability::Available(_)
    ));
}

#[test]
fn version_comparison() {
    assert!(catalog::version_at_least("0.10.0", "0.9.3"));
    assert!(catalog::version_at_least("1.0", "1.0.0"));
    assert!(!catalog::version_at_least("0.1.0", "0.1.1"));
    assert!(!catalog::version_at_least("26.0", "26.6.2"));
}

// ------------------------------------------------------------- testserver

/// Liten HTTP-server over en mappe, med Range og valgfritt brudd i første
/// forespørsel mot hver pakke. Forespørslene logges (sti og Range) så testene
/// kan sjekke at ingenting annet sendes.
struct DirServer {
    port: u16,
    requests: Arc<AtomicUsize>,
    log: Arc<Mutex<Vec<String>>>,
}

impl DirServer {
    fn start(dir: PathBuf, cut_first_after: Option<usize>) -> DirServer {
        Self::start_on(dir, cut_first_after, 0)
    }

    fn start_on(dir: PathBuf, cut_first_after: Option<usize>, port: u16) -> DirServer {
        let l = TcpListener::bind(("127.0.0.1", port)).unwrap();
        let port = l.local_addr().unwrap().port();
        let requests = Arc::new(AtomicUsize::new(0));
        let log = Arc::new(Mutex::new(Vec::new()));
        let (reqs, log2) = (requests.clone(), log.clone());
        let cut_done = Arc::new(Mutex::new(std::collections::HashSet::new()));
        std::thread::spawn(move || {
            for s in l.incoming().flatten() {
                let dir = dir.clone();
                let reqs = reqs.clone();
                let log = log2.clone();
                let cut_done = cut_done.clone();
                std::thread::spawn(move || {
                    let _ = serve(s, &dir, &reqs, &log, cut_first_after, &cut_done);
                });
            }
        });
        DirServer {
            port,
            requests,
            log,
        }
    }

    fn url(&self, name: &str) -> String {
        format!("http://127.0.0.1:{}/{name}", self.port)
    }
}

fn serve(
    mut s: TcpStream,
    dir: &Path,
    reqs: &AtomicUsize,
    log: &Mutex<Vec<String>>,
    cut: Option<usize>,
    cut_done: &Mutex<std::collections::HashSet<String>>,
) -> std::io::Result<()> {
    let mut r = BufReader::new(s.try_clone()?);
    let mut line = String::new();
    r.read_line(&mut line)?;
    let path = line.split_whitespace().nth(1).unwrap_or("/").to_string();
    let mut range = None;
    let mut headers = Vec::new();
    loop {
        let mut h = String::new();
        r.read_line(&mut h)?;
        if h == "\r\n" || h.is_empty() {
            break;
        }
        if let Some((k, v)) = h.split_once(':') {
            headers.push(k.trim().to_ascii_lowercase());
            if k.eq_ignore_ascii_case("range") {
                range = Some(v.trim().trim_start_matches("bytes=").to_string());
            }
        }
    }
    reqs.fetch_add(1, Ordering::SeqCst);
    headers.sort();
    log.lock()
        .unwrap()
        .push(format!("{path} {}", headers.join(",")));
    let name = path.trim_start_matches('/');
    let not_found = "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
    if name.contains('/') || name.contains("..") {
        return write!(s, "{not_found}");
    }
    let Ok(data) = std::fs::read(dir.join(name)) else {
        return write!(s, "{not_found}");
    };
    let len = data.len();
    let Some(rg) = range else {
        write!(
            s,
            "HTTP/1.1 200 OK\r\nContent-Length: {len}\r\nConnection: close\r\n\r\n"
        )?;
        return s.write_all(&data);
    };
    let (a, z) = rg.split_once('-').unwrap();
    let start: usize = a.parse().unwrap();
    let end = if z.is_empty() {
        len - 1
    } else {
        z.parse::<usize>().unwrap().min(len - 1)
    };
    let body = &data[start..=end];
    write!(
        s,
        "HTTP/1.1 206 Partial Content\r\nContent-Range: bytes {start}-{end}/{len}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        body.len()
    )?;
    let should_cut = (name.ends_with(".tar.gz") || name.ends_with(".zip"))
        && cut.is_some()
        && cut_done.lock().unwrap().insert(name.to_string());
    if should_cut {
        s.write_all(&body[..cut.unwrap().min(body.len())])?;
        s.flush()?;
        let _ = s.shutdown(std::net::Shutdown::Both);
        return Ok(());
    }
    s.write_all(body)
}

fn test_jv(data: &Path, server: &DirServer, catalog_name: &str) -> Jv {
    Jv::new(Config {
        data_dir: data.join("verktoy"),
        app_version: "0.2.0".into(),
        os_version: Some("26.6.2".into()),
        public_key: Some(TEST_PUBLIC_KEY.into()),
        catalog_url: server.url(catalog_name),
        sig_url: server.url(&format!("{catalog_name}.sig")),
        policy: HostPolicy::for_tests(&["127.0.0.1"]),
        signature: SignatureCheck::SkipForTests,
    })
}

fn catalog_dir() -> PathBuf {
    let d = tmp("katalogserver");
    std::fs::write(d.join("tools.json"), CATALOG).unwrap();
    std::fs::write(d.join("tools.json.sig"), CATALOG_SIG).unwrap();
    std::fs::write(d.join("tools-ny.json"), CATALOG_NEW).unwrap();
    std::fs::write(d.join("tools-ny.json.sig"), CATALOG_NEW_SIG).unwrap();
    let mut bad = CATALOG_NEW.to_vec();
    bad[10] ^= 1;
    std::fs::write(d.join("tools-feil.json"), bad).unwrap();
    std::fs::write(d.join("tools-feil.json.sig"), CATALOG_NEW_SIG).unwrap();
    d
}

// ------------------------------------------------------------- katalog i tjenesten

#[test]
fn catalog_is_fetched_only_when_asked_and_cached_copy_is_used_offline() {
    let server = DirServer::start(catalog_dir(), None);
    let data = tmp("appdata");
    let jv = test_jv(&data, &server, "tools-ny.json");

    // fetch = false: ingen nett, ingen katalog ennå.
    let v = jv.catalog(false);
    assert_eq!(server.requests.load(Ordering::SeqCst), 0);
    assert_eq!(v.source, CatalogSource::None);
    assert!(v.tools.iter().all(|t| t.status == ToolStatus::Unknown));
    assert_eq!(v.tools.len(), catalog::KNOWN_TOOLS.len());

    // fetch = true: henter, kontrollerer og lagrer.
    let v = jv.catalog(true);
    assert_eq!(v.source, CatalogSource::Network);
    assert_eq!(v.error, None);
    let log = server.log.lock().unwrap().clone();
    assert_eq!(log.len(), 2);
    // Ingenting om brukeren: bare vert, user-agent og standardfelt.
    for l in &log {
        let headers = l.split_once(' ').unwrap().1;
        for h in headers.split(',') {
            assert!(
                [
                    "host",
                    "user-agent",
                    "accept",
                    "accept-encoding",
                    "connection"
                ]
                .contains(&h),
                "{h}"
            );
        }
    }
    let status = |v: &super::service::CatalogView, id: &str| {
        v.tools.iter().find(|t| t.id == id).unwrap().status
    };
    if CURRENT_TARGET == TARGET_MAC {
        assert_eq!(status(&v, "subtitles"), ToolStatus::Available);
        assert_eq!(status(&v, "nynorsk"), ToolStatus::NotForPlatform);
    } else {
        // Windows i runde A: alle ni er «Kommer for Windows».
        assert!(v
            .tools
            .iter()
            .all(|t| t.status == ToolStatus::NotForPlatform));
    }

    // Uten nett (serveren peker til en fil som ikke finnes): siste kopi brukes.
    let offline = test_jv(&data, &server, "finnes-ikke.json");
    let v = offline.catalog(true);
    assert_eq!(v.source, CatalogSource::Cache);
    assert!(matches!(v.error, Some(JvError::Download { .. })));
    assert!(v.tools.iter().any(|t| t.entry.is_some()) || CURRENT_TARGET != TARGET_MAC);

    // En katalog med feil signatur avvises og erstatter ikke den gode.
    let bad = test_jv(&data, &server, "tools-feil.json");
    let v = bad.catalog(true);
    assert_eq!(v.error, Some(JvError::CatalogSignature));
    assert_eq!(v.source, CatalogSource::Cache);

    // En eldre (men gyldig) katalog avvises også.
    let old = test_jv(&data, &server, "tools.json");
    let v = old.catalog(true);
    assert_eq!(v.error, Some(JvError::CatalogOutdated));
    assert_eq!(v.source, CatalogSource::Cache);
    assert_eq!(
        old.cached_catalog().unwrap().signed_at,
        catalog::verify_and_parse(CATALOG_NEW, CATALOG_NEW_SIG, TEST_PUBLIC_KEY)
            .unwrap()
            .signed_at
    );
}

#[test]
fn catalog_without_public_key_is_never_trusted() {
    let server = DirServer::start(catalog_dir(), None);
    let data = tmp("appdata");
    let mut cfg = Config::production(data.clone(), "0.2.0".into());
    cfg.public_key = None;
    cfg.catalog_url = server.url("tools-ny.json");
    cfg.sig_url = server.url("tools-ny.json.sig");
    cfg.policy = HostPolicy::for_tests(&["127.0.0.1"]);
    let jv = Jv::new(cfg);
    let v = jv.catalog(true);
    assert_eq!(v.error, Some(JvError::CatalogKeyMissing));
    assert_eq!(
        server.requests.load(Ordering::SeqCst),
        0,
        "uten nøkkel hentes ingenting"
    );
}

#[test]
fn production_config_only_allows_the_release_repo_over_https() {
    let cfg = Config::production(tmp("appdata"), "0.2.0".into());
    assert!(cfg.policy.check(catalog::CATALOG_URL).is_ok());
    assert!(cfg
        .policy
        .check("https://release-assets.githubusercontent.com/github-production-release-asset/x")
        .is_ok());
    assert!(cfg.policy.check("http://github.com/x").is_err());
    assert!(cfg.policy.check("https://huggingface.co/x").is_err());
    assert!(cfg.policy.check("https://127.0.0.1/x").is_err());
    assert!(matches!(
        cfg.signature,
        SignatureCheck::Team(package::TEAM_ID)
    ));
}

#[test]
fn install_needs_a_checked_catalog_and_the_right_platform() {
    let server = DirServer::start(catalog_dir(), None);
    let jv = test_jv(&tmp("appdata"), &server, "tools-ny.json");
    assert_eq!(
        jv.installable_entry("subtitles").unwrap_err(),
        JvError::CatalogMissing
    );
    jv.catalog(true);
    assert_eq!(
        jv.installable_entry("nynorsk").unwrap_err(),
        JvError::NotForPlatform
    );
    assert_eq!(
        jv.installable_entry("ukjent").unwrap_err(),
        JvError::UnknownTool
    );
    if CURRENT_TARGET == TARGET_WINDOWS {
        assert_eq!(
            jv.installable_entry("subtitles").unwrap_err(),
            JvError::NotForPlatform
        );
    }
}

// ------------------------------------------------------------- falsk pakke

/// Skriptet den falske pakken kjører når argumentet ikke er `--version`:
/// `sh` på Mac, `cmd` på Windows.
struct Body<'a> {
    #[cfg_attr(windows, allow(dead_code))]
    sh: &'a str,
    #[cfg_attr(not(windows), allow(dead_code))]
    cmd: &'a str,
}

/// `entry` i den falske pakken.
#[cfg(unix)]
const FAKE_ENTRY: &str = "bin/jv";
#[cfg(windows)]
const FAKE_ENTRY: &str = "bin/jv.cmd";

/// En falsk pakke: et skript som `entry`, pakket med systemets tar
/// (`.tar.gz` på Mac, `.zip` med tar.exe på Windows, som de ekte pakkene).
fn fake_package_with(
    id: &str,
    version_output: &str,
    body: Body,
) -> (PathBuf, catalog::CatalogEntry) {
    let src = tmp("falsk-src");
    std::fs::create_dir_all(src.join("bin")).unwrap();
    let script_path = src.join(FAKE_ENTRY);
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let script = format!(
            "#!/bin/sh\nif [ \"$1\" = --version ]; then echo '{version_output}'; exit 0; fi\n{}\n",
            body.sh
        );
        std::fs::write(&script_path, script).unwrap();
        std::fs::set_permissions(&script_path, std::fs::Permissions::from_mode(0o755)).unwrap();
    }
    #[cfg(windows)]
    {
        let script = format!(
            "@echo off\r\nif \"%~1\"==\"--version\" (\r\n  echo {version_output}\r\n  exit /b 0\r\n)\r\n{}\r\n",
            body.cmd.replace('\n', "\r\n")
        );
        std::fs::write(&script_path, script).unwrap();
    }
    std::fs::write(
        src.join(package::MANIFEST),
        format!(
            r#"{{"schema":1,"id":"{id}","name":"Falsk","version":"1.0.0","target":"{CURRENT_TARGET}","entry":"{FAKE_ENTRY}","path":["bin"],"env":{{"JV_FALSK":"{FAKE_ENTRY}"}},"codesign":["{FAKE_ENTRY}"]}}"#
        ),
    )
    .unwrap();
    let suffix = if cfg!(windows) { "zip" } else { "tar.gz" };
    let arch = tmp("falsk-arkiv").join(format!("jv-{id}-1.0.0-{CURRENT_TARGET}.{suffix}"));
    let mut tar = if cfg!(windows) {
        let root = std::env::var_os("SystemRoot").unwrap_or_else(|| "C:\\Windows".into());
        let mut c =
            std::process::Command::new(PathBuf::from(root).join("System32").join("tar.exe"));
        c.arg("-a").arg("-cf");
        c
    } else {
        let mut c = std::process::Command::new("tar");
        c.env("COPYFILE_DISABLE", "1").arg("-czf");
        c
    };
    assert!(tar
        .arg(&arch)
        .arg("-C")
        .arg(&src)
        .args(["jv-package.json", "bin"])
        .status()
        .unwrap()
        .success());
    let (sha, bytes) = package::sha256_file(&arch).unwrap();
    let entry = catalog::CatalogEntry {
        id: id.into(),
        name: "Falsk".into(),
        version: "1.0.0".into(),
        target: CURRENT_TARGET.into(),
        url: format!("https://example.invalid/falsk.{suffix}"),
        bytes,
        sha256: sha,
        min_app_version: "0.1.0".into(),
        min_os: None,
        notes: String::new(),
    };
    (arch, entry)
}

fn fake_package(version_output: &str) -> (PathBuf, catalog::CatalogEntry) {
    fake_package_with(
        "falsk",
        version_output,
        Body {
            sh: "exit 3",
            cmd: "exit /b 3",
        },
    )
}

fn never() -> AtomicBool {
    AtomicBool::new(false)
}

#[test]
fn package_with_wrong_sha256_is_rejected_and_deleted() {
    let (arch, mut entry) = fake_package(r#"{"id":"falsk","version":"1.0.0"}"#);
    entry.sha256 = "0".repeat(64);
    let tools = tmp("verktoy");
    assert_eq!(
        package::install(
            &entry,
            &arch,
            &tools,
            SignatureCheck::SkipForTests,
            &never()
        )
        .unwrap_err(),
        JvError::ChecksumMismatch
    );
    assert!(!arch.exists(), "pakken med feil sum skal slettes");
    assert!(!tools.join("falsk").join("1.0.0").exists());
}

#[test]
fn failing_trial_run_keeps_old_version() {
    // --version svarer med feil id: prøvekjøringen skal feile.
    let (arch, entry) = fake_package(r#"{"id":"feil","version":"9.9.9"}"#);
    let tools = tmp("verktoy");
    let old = tools.join("falsk").join("0.9.0");
    std::fs::create_dir_all(&old).unwrap();
    assert_eq!(
        package::install(
            &entry,
            &arch,
            &tools,
            SignatureCheck::SkipForTests,
            &never()
        )
        .unwrap_err(),
        JvError::TrialRunFailed
    );
    assert!(old.exists(), "den gamle versjonen skal stå urørt");
    assert!(!tools.join("falsk").join(".ny-1.0.0").exists());
    assert!(!tools.join("falsk").join("1.0.0").exists());
    // Og en --version som ikke svarer i det hele tatt (kode 0, men ikke JSON).
    let (arch, entry) = fake_package("ikke json");
    assert_eq!(
        package::install(
            &entry,
            &arch,
            &tools,
            SignatureCheck::SkipForTests,
            &never()
        )
        .unwrap_err(),
        JvError::TrialRunFailed
    );
    assert!(old.exists());
}

#[test]
fn cancel_during_install_leaves_nothing_half_installed() {
    let (arch, entry) = fake_package(r#"{"id":"falsk","version":"1.0.0"}"#);
    let tools = tmp("verktoy");
    let cancel = AtomicBool::new(true);
    assert_eq!(
        package::install(&entry, &arch, &tools, SignatureCheck::SkipForTests, &cancel).unwrap_err(),
        JvError::Cancelled
    );
    assert!(package::installed(&tools, "falsk").is_none());
    assert!(!tools.join("falsk").join(".ny-1.0.0").exists());
}

#[test]
fn good_fake_package_replaces_old_version() {
    let (arch, entry) = fake_package(r#"{"id":"falsk","version":"1.0.0"}"#);
    let tools = tmp("verktoy");
    let old = tools.join("falsk").join("0.9.0");
    std::fs::create_dir_all(&old).unwrap();
    let (root, _) = package::install(
        &entry,
        &arch,
        &tools,
        SignatureCheck::SkipForTests,
        &never(),
    )
    .unwrap();
    assert_eq!(root, tools.join("falsk").join("1.0.0"));
    assert!(
        !old.exists(),
        "den gamle versjonen slettes etter vellykket prøvekjøring"
    );
    // Miljøet peker inn i pakken.
    let m = package::read_manifest(&root).unwrap();
    let env = package::command_env(&root, &m);
    let jv = env.iter().find(|(k, _)| k == "JV_FALSK").unwrap();
    assert_eq!(
        std::path::PathBuf::from(&jv.1),
        package::join_rel(&root, FAKE_ENTRY)
    );
    let path = env.iter().find(|(k, _)| k == "PATH").unwrap();
    assert!(path
        .1
        .to_string_lossy()
        .starts_with(&*root.join("bin").to_string_lossy()));
    // Brukerens miljø slipper ikke inn.
    assert!(env
        .iter()
        .all(|(k, _)| !k.starts_with("DYLD_") && !k.starts_with("PYTHON")));
}

#[cfg(target_os = "macos")]
#[test]
fn unsigned_package_is_rejected_with_team_requirement() {
    let (arch, entry) = fake_package(r#"{"id":"falsk","version":"1.0.0"}"#);
    let tools = tmp("verktoy");
    assert_eq!(
        package::install(
            &entry,
            &arch,
            &tools,
            SignatureCheck::Team(package::TEAM_ID),
            &never()
        )
        .unwrap_err(),
        JvError::CodeSignature
    );
}

#[test]
fn manifest_cannot_point_outside_or_set_dangerous_env() {
    let d = tmp("manifest");
    for bad in [
        r#"{"schema":1,"id":"x","version":"1","target":"t","entry":"../jv"}"#,
        r#"{"schema":1,"id":"x","version":"1","target":"t","entry":"/bin/sh"}"#,
        r#"{"schema":1,"id":"x","version":"1","target":"t","entry":"jv","env":{"DYLD_INSERT_LIBRARIES":"a"}}"#,
        r#"{"schema":1,"id":"x","version":"1","target":"t","entry":"jv","env":{"PATH":"a"}}"#,
        r#"{"schema":1,"id":"x","version":"1","target":"t","entry":"jv","path":["C:/Windows"]}"#,
        r#"{"schema":1,"id":"x","version":"1","target":"t","entry":"jv\\jv.exe"}"#,
        // Windows skiller ikke på store og små bokstaver i variabelnavn.
        r#"{"schema":1,"id":"x","version":"1","target":"t","entry":"jv","env":{"SYSTEMROOT":"a"}}"#,
        r#"{"schema":1,"id":"x","version":"1","target":"t","entry":"jv","env":{"COMSPEC":"a"}}"#,
        r#"{"schema":1,"id":"x","version":"1","target":"t","entry":"jv","env":{"USERPROFILE":"a"}}"#,
        r#"{"schema":1,"id":"x","version":"1","target":"t","entry":"jv","env":{"PATHEXT":"a"}}"#,
        r#"{"schema":1,"id":"x","version":"1","target":"t","entry":"jv","env":{"Path":"a"}}"#,
    ] {
        std::fs::write(d.join(package::MANIFEST), bad).unwrap();
        assert!(
            matches!(
                package::read_manifest(&d),
                Err(JvError::ManifestInvalid { .. })
            ),
            "{bad}"
        );
    }
}

/// Miljøet en pakke kjøres med: bare systemets minimum og pakkens egne
/// variabler, med stier inn i pakken. Samme regler som `jvpack.pack.package_env`.
#[test]
fn command_env_is_clean_and_points_into_the_package() {
    let root = tmp("miljo");
    std::fs::write(
        root.join(package::MANIFEST),
        r#"{"schema":1,"id":"ocr","version":"1.0.0","target":"t","entry":"jv-ocr/jv.exe",
            "path":["jv-ocr/programmer/tesseract"],
            "env":{"JV_TESSERACT":"jv-ocr/programmer/tesseract/tesseract.exe",
                   "TESSDATA_PREFIX":"jv-ocr/data/tessdata",
                   "JV_TO":["a/b","c"]}}"#,
    )
    .unwrap();
    let m = package::read_manifest(&root).unwrap();
    let env = package::command_env(&root, &m);
    let get = |k: &str| {
        env.iter()
            .find(|(n, _)| n == k)
            .map(|(_, v)| PathBuf::from(v))
    };
    let allowed = [
        "PATH",
        "HOME",
        "TMPDIR",
        "SystemRoot",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
        "JV_TESSERACT",
        "TESSDATA_PREFIX",
        "JV_TO",
    ];
    for (k, _) in &env {
        assert!(allowed.contains(&k.as_str()), "uventet variabel {k}");
    }
    // Ingen variabel to ganger (Windows skiller ikke på store og små bokstaver).
    let mut names: Vec<String> = env.iter().map(|(k, _)| k.to_ascii_uppercase()).collect();
    names.sort();
    names.dedup();
    assert_eq!(names.len(), env.len());
    assert_eq!(
        get("JV_TESSERACT").unwrap(),
        root.join("jv-ocr")
            .join("programmer")
            .join("tesseract")
            .join("tesseract.exe")
    );
    assert_eq!(
        get("TESSDATA_PREFIX").unwrap(),
        root.join("jv-ocr").join("data").join("tessdata")
    );
    let to: Vec<PathBuf> = std::env::split_paths(&get("JV_TO").unwrap().into_os_string()).collect();
    assert_eq!(to, vec![root.join("a").join("b"), root.join("c")]);
    let path: Vec<PathBuf> =
        std::env::split_paths(&get("PATH").unwrap().into_os_string()).collect();
    assert_eq!(
        path[0],
        root.join("jv-ocr").join("programmer").join("tesseract")
    );
    #[cfg(windows)]
    {
        // Systemmappene og det Windows-programmer trenger for å starte, ikke mer.
        let sys =
            PathBuf::from(std::env::var_os("SystemRoot").unwrap_or_else(|| "C:\\Windows".into()));
        assert_eq!(path[1..], [sys.join("System32"), sys.clone()]);
        assert_eq!(get("SystemRoot").unwrap(), sys);
        assert!(
            get("TEMP").is_some(),
            "TEMP trengs av Python og PyInstaller"
        );
        assert!(get("HOME").is_none() && get("TMPDIR").is_none());
    }
    #[cfg(not(windows))]
    {
        let system: Vec<PathBuf> = ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]
            .iter()
            .map(PathBuf::from)
            .collect();
        assert_eq!(path[1..], system[..]);
        assert!(get("SystemRoot").is_none() && get("USERPROFILE").is_none());
    }
}

// ------------------------------------------------------------- nedlasting

#[test]
fn interrupted_and_cancelled_download_resumes_and_installs_nothing_half() {
    // En «pakke» på 3 MB fra testserveren. Første forespørsel brytes etter 1 MB.
    let dir = tmp("pakkeserver");
    let data: Vec<u8> = (0..3 * 1024 * 1024u32).map(|i| (i % 251) as u8).collect();
    let name = "jv-falsk-1.0.0-test.tar.gz";
    std::fs::write(dir.join(name), &data).unwrap();
    let (sha, bytes) = package::sha256_file(&dir.join(name)).unwrap();
    let server = DirServer::start(dir, Some(1024 * 1024));
    let entry = catalog::CatalogEntry {
        id: "falsk".into(),
        name: "Falsk".into(),
        version: "1.0.0".into(),
        target: "test".into(),
        url: server.url(name),
        bytes,
        sha256: sha,
        min_app_version: "0.1.0".into(),
        min_os: None,
        notes: String::new(),
    };
    let downloads = tmp("nedlasting");
    let policy = HostPolicy::for_tests(&["127.0.0.1"]);

    // 1. Avbryt etter første fremdrift: .part blir liggende, ingen ferdig fil.
    let cancel = AtomicBool::new(false);
    let r = package::download_package(&entry, &downloads, &policy, &cancel, &mut |done, _| {
        if done > 0 {
            cancel.store(true, Ordering::SeqCst);
        }
    });
    assert_eq!(r.unwrap_err(), JvError::Cancelled);
    let part = downloads.join(format!("{}.bin.part", package::download_name(&entry)));
    let partial = std::fs::metadata(&part).map(|m| m.len()).unwrap_or(0);
    assert!(
        partial > 0 && partial < bytes,
        "delvis nedlasting skal ligge igjen"
    );
    assert!(!downloads
        .join(format!("{}.bin", package::download_name(&entry)))
        .exists());

    // 2. Gjenoppta: fortsetter fra der den slapp (Range), og SHA-256 stemmer til slutt.
    let before = server.requests.load(Ordering::SeqCst);
    let mut first_progress = None;
    let done = package::download_package(&entry, &downloads, &policy, &never(), &mut |d, _| {
        first_progress.get_or_insert(d);
    })
    .unwrap();
    assert_eq!(first_progress, Some(partial), "skal starte der den slapp");
    assert_eq!(std::fs::read(&done).unwrap(), data);
    assert!(server.requests.load(Ordering::SeqCst) > before);
    let log = server.log.lock().unwrap().clone();
    assert!(log.iter().all(|l| l.starts_with(&format!("/{name} "))));
}

#[test]
fn download_with_wrong_sha256_is_deleted() {
    let dir = tmp("pakkeserver");
    let name = "jv-falsk-1.0.0-test.tar.gz";
    std::fs::write(dir.join(name), vec![7u8; 200_000]).unwrap();
    let server = DirServer::start(dir, None);
    let entry = catalog::CatalogEntry {
        id: "falsk".into(),
        name: "Falsk".into(),
        version: "1.0.0".into(),
        target: "test".into(),
        url: server.url(name),
        bytes: 200_000,
        sha256: "0".repeat(64),
        min_app_version: "0.1.0".into(),
        min_os: None,
        notes: String::new(),
    };
    let downloads = tmp("nedlasting");
    let policy = HostPolicy::for_tests(&["127.0.0.1"]);
    let r = package::download_package(&entry, &downloads, &policy, &never(), &mut |_, _| {});
    assert_eq!(r.unwrap_err(), JvError::ChecksumMismatch);
    assert_eq!(std::fs::read_dir(&downloads).unwrap().count(), 0);
}

// ------------------------------------------------------------- kjøring

fn installed_fake(body: Body) -> (Jv, PathBuf) {
    let (arch, entry) =
        fake_package_with("subtitles", r#"{"id":"subtitles","version":"1.0.0"}"#, body);
    let data = tmp("appdata");
    let server = DirServer::start(catalog_dir(), None);
    let jv = test_jv(&data, &server, "tools-ny.json");
    package::install(
        &entry,
        &arch,
        jv.tools_dir(),
        SignatureCheck::SkipForTests,
        &never(),
    )
    .unwrap();
    let work = tmp("arbeid");
    std::fs::write(work.join("intervju.json"), b"{}").unwrap();
    (jv, work)
}

fn subtitles_request(work: &Path) -> RunRequest {
    serde_json::from_value(json!({
        "inputs": [work.join("intervju.json")],
        "out_dir": work.join("ut"),
        "options": {"max_chars": 40}
    }))
    .unwrap()
}

#[test]
fn run_reads_report_and_progress_from_fake_package() {
    // Skriptet sjekker at argumentene kom som forventet og svarer som et verktøy.
    let body = Body {
        sh: r#"[ "$1" = subtitles ] && [ "$3" = --max-chars ] && [ "$4" = 40 ] && [ "$5" = --out ] || exit 9
echo '{"progress": 0.5}' >&2
echo "{\"tool\":\"subtitles\",\"summary\":\"1 fil\",\"outputs\":[],\"warnings\":[],\"env\":\"$JV_FALSK\"}""#,
        // Windows: stien får «/» så den kan stå i JSON uten escape.
        cmd: r#"if not "%~1"=="subtitles" exit /b 9
if not "%~3"=="--max-chars" exit /b 9
if not "%~4"=="40" exit /b 9
if not "%~5"=="--out" exit /b 9
1>&2 echo {"progress": 0.5}
set "E=%JV_FALSK:\=/%"
echo {"tool":"subtitles","summary":"1 fil","outputs":[],"warnings":[],"env":"%E%"}"#,
    };
    let (jv, work) = installed_fake(body);
    let installed = jv.installed();
    assert_eq!(installed.len(), 1);
    assert_eq!(installed[0].license, "AGPL-3.0-or-later");
    let cmd = jv
        .prepare_run("subtitles", &subtitles_request(&work))
        .unwrap();
    let mut seen = Vec::new();
    match runner::run_job(cmd, &never(), None, &mut |p| seen.push(p)).unwrap() {
        Finished::Report(r) => {
            assert_eq!(r["summary"], "1 fil");
            assert!(r["env"].as_str().unwrap().ends_with(FAKE_ENTRY));
        }
        other => panic!("{other:?}"),
    }
    assert_eq!(seen, vec![0.5]);
}

#[test]
fn run_can_be_cancelled_and_one_job_per_tool() {
    let (jv, work) = installed_fake(Body {
        sh: "echo '{\"progress\": 0.1}' >&2; sleep 30",
        cmd: "1>&2 echo {\"progress\": 0.1}\nping -n 31 127.0.0.1 >nul",
    });
    let (job, cancel) = jv.begin("subtitles").unwrap();
    assert_eq!(jv.begin("subtitles").unwrap_err(), JvError::Busy);
    assert_eq!(jv.remove("subtitles").unwrap_err(), JvError::Busy);
    let cmd = jv
        .prepare_run("subtitles", &subtitles_request(&work))
        .unwrap();
    let t = Instant::now();
    let jv = Arc::new(jv);
    let jv2 = jv.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(300));
        assert!(jv2.cancel(job));
    });
    assert_eq!(
        runner::run_job(cmd, &cancel, None, &mut |_| {}).unwrap(),
        Finished::Cancelled
    );
    assert!(t.elapsed() < Duration::from_secs(10));
    jv.end(job);
    assert!(!jv.cancel(job));
    // Etter jobben kan verktøyet fjernes.
    jv.remove("subtitles").unwrap();
    assert!(jv.installed().is_empty());
    assert_eq!(
        jv.prepare_run("subtitles", &subtitles_request(&work))
            .unwrap_err(),
        JvError::NotInstalled
    );
}

#[test]
fn run_rejects_arguments_outside_the_whitelist() {
    let (jv, work) = installed_fake(Body {
        sh: "exit 0",
        cmd: "exit /b 0",
    });
    let mut req = subtitles_request(&work);
    req.options.insert("--shell".into(), json!("rm -rf /"));
    assert_eq!(
        jv.prepare_run("subtitles", &req).unwrap_err(),
        JvError::InvalidArgs {
            reason: "unknown_option"
        }
    );
}

#[cfg(target_os = "macos")]
#[test]
fn package_with_broken_signature_is_not_run() {
    let (jv, work) = installed_fake(Body {
        sh: "exit 0",
        cmd: "exit /b 0",
    });
    let inst = package::installed(jv.tools_dir(), "subtitles").unwrap();
    assert_eq!(
        package::verify_codesign(
            &inst.root,
            &inst.manifest,
            SignatureCheck::Team(package::TEAM_ID)
        )
        .unwrap_err(),
        JvError::CodeSignature
    );
    let _ = work;
}

// ------------------------------------------------------------- hele kjeden

/// Fast port for `full_chain`: katalogen lages med
/// `--base-url http://127.0.0.1:47613` (sidecar/build/README.md).
const FULL_CHAIN_PORT: u16 = 47613;

/// Testfil og valg per verktøy (fra sidecar/jv/testdata).
fn full_chain_case(id: &str, testdata: &Path, out: &Path) -> serde_json::Value {
    let t = |p: &str| testdata.join(p);
    match id {
        "compare" => {
            json!({"inputs": [t("compare/vedtak_v1.txt"), t("compare/vedtak_v2.txt")], "out_dir": out})
        }
        "metadata" => {
            json!({"command": "vask", "inputs": [t("metadata/bilde_gps.jpg")], "out_dir": out})
        }
        "keyframes" => {
            json!({"inputs": [t("keyframes/klipp.mp4")], "out_dir": out, "options": {"every_seconds": 2}})
        }
        "loudness" => {
            json!({"inputs": [t("loudness/lav.wav")], "out_dir": out, "options": {"target": "podcast"}})
        }
        "subtitles" => json!({"inputs": [t("subtitles/transkripsjon.json")], "out_dir": out}),
        "pdf-tables" => json!({"inputs": [t("pdf-tables/budsjett.pdf")], "out_dir": out}),
        // Ingen utmappe: tabellen står i rapporten.
        "datawrapper" => {
            json!({"command": "lag", "inputs": [t("datawrapper/ssb_befolkning.xlsx")]})
        }
        "ocr" => json!({"inputs": [t("ocr/skannet_side.pdf")], "out_dir": out}),
        "redact" => {
            json!({"command": "finn", "inputs": [t("redact/personopplysninger.pdf")], "out_dir": out})
        }
        "nynorsk" => {
            json!({"inputs": [t("nynorsk/avsnitt_nb.txt")], "out_dir": out, "options": {"to": "nn"}})
        }
        _ => unreachable!(),
    }
}

#[test]
#[ignore = "krever pakkene og katalogen fra sidecar/build; sett JV_DIST"]
fn full_chain() {
    let dist = PathBuf::from(std::env::var("JV_DIST").expect("JV_DIST"));
    let testdata = std::fs::canonicalize(dist.join("../../../jv/testdata")).unwrap();
    let server = DirServer::start_on(dist.clone(), Some(3 * 1024 * 1024), FULL_CHAIN_PORT);
    let data = std::env::var("JV_TEST_DATA_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| tmp("appdata"));
    let jv = Jv::new(Config {
        data_dir: data.join("verktoy"),
        app_version: "0.2.0".into(),
        os_version: super::service::os_version(),
        public_key: Some(TEST_PUBLIC_KEY.into()),
        catalog_url: server.url("tools.json"),
        sig_url: server.url("tools.json.sig"),
        policy: HostPolicy::for_tests(&["127.0.0.1"]),
        signature: SignatureCheck::Team(package::TEAM_ID),
    });

    let t = Instant::now();
    let view = jv.catalog(true);
    assert_eq!(view.source, CatalogSource::Network, "{:?}", view.error);
    println!(
        "katalog: hentet og kontrollert på {} ms",
        t.elapsed().as_millis()
    );

    let ids: Vec<String> = std::env::var("JV_IDS")
        .map(|s| s.split(',').map(str::to_string).collect())
        .unwrap_or_else(|_| catalog::KNOWN_TOOLS.iter().map(|s| s.to_string()).collect());
    for id in &ids {
        let entry = jv.installable_entry(id).expect("i katalogen");
        let before = server.requests.load(Ordering::SeqCst);
        let mut phases = (0u64, 0u64);
        let t = Instant::now();
        let mut t_download = Duration::ZERO;
        let version = jv
            .install(id, &never(), &mut |phase, done, _| match phase {
                InstallPhase::Download => phases.0 = done,
                InstallPhase::Install => {
                    t_download = t.elapsed();
                    phases.1 += 1
                }
            })
            .expect("installasjon");
        let t_install = t.elapsed() - t_download;
        assert_eq!(version, entry.version);
        assert_eq!(phases.0, entry.bytes);
        let n_req = server.requests.load(Ordering::SeqCst) - before;
        if entry.bytes > 3 * 1024 * 1024 {
            assert!(n_req >= 2, "bruddet skal gi minst én ny forespørsel");
        }
        let inst = package::installed(jv.tools_dir(), id).unwrap();

        let mut starts = Vec::new();
        for _ in 0..3 {
            let t = Instant::now();
            package::trial_run(&inst.root, &inst.manifest).unwrap();
            starts.push(t.elapsed().as_millis());
        }

        let out = tmp("ut");
        let req: RunRequest =
            serde_json::from_value(full_chain_case(id, &testdata, &out.join("resultat"))).unwrap();
        let t = Instant::now();
        let cmd = jv.prepare_run(id, &req).expect("argumenter og signatur");
        let t_codesign = t.elapsed();
        let mut progress = 0usize;
        let t = Instant::now();
        let result = runner::run_job(cmd, &never(), None, &mut |_| progress += 1).unwrap();
        let t_run = t.elapsed();
        let report = match result {
            Finished::Report(r) => r,
            other => panic!("{id}: {other:?}"),
        };
        if id == "datawrapper" {
            // Tabellen skal være lik fasiten, byte for byte (skrives ikke ut, regel 2).
            let want =
                std::fs::read(testdata.join("datawrapper/ssb_befolkning.fasit.tsv")).unwrap();
            assert_eq!(
                report["datawrapper"]["tsv"].as_str().map(str::as_bytes),
                Some(&want[..])
            );
        }
        let outputs = report["outputs"].as_array().map(|a| a.len()).unwrap_or(0);
        println!(
            "{id}: arkiv {:.1} MB, utpakket {:.1} MB | nedlasting {} ms ({n_req} forespørsler) | \
             kontroll+utpakking+codesign+prøvekjøring {} ms | --version x3 {:?} ms | \
             codesign før kjøring {} ms | kjøring {} ms ({progress} fremdriftslinjer, {outputs} utfiler)",
            entry.bytes as f64 / 1e6,
            package::dir_size(&inst.root) as f64 / 1e6,
            t_download.as_millis(),
            t_install.as_millis(),
            starts,
            t_codesign.as_millis(),
            t_run.as_millis(),
        );
        let _ = std::fs::remove_dir_all(&out);
    }
}
