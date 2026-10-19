// SPDX-License-Identifier: AGPL-3.0-or-later
//! Tester for spiken (steg 6.1).
//!
//! - Katalog: signatur (riktig, endret, feil nøkkel), «Kommer for Windows».
//! - Pakke: feil SHA-256, prøvekjøring som feiler (falsk pakke).
//! - `spike_full_chain` (ignorert som standard; krever pakkene fra
//!   `sidecar/build/bygg-mac.sh`): katalog fra en lokal testserver → signatur →
//!   nedlasting med brudd og gjenopptak → SHA-256 → utpakking → codesign →
//!   `--version` → kjøring på testfilen. Skriver bare tall, aldri filnavn
//!   eller tekst fra verktøyene.
//!
//!     JV_SPIKE_DIST=../sidecar/build/out/dist cargo test spike_full_chain -- --ignored --nocapture

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use super::catalog::{self, Availability, TARGET_MAC, TARGET_WINDOWS, TEST_PUBLIC_KEY};
use super::error::JvError;
use super::package;
use crate::tools::transkribering::download::HostPolicy;

const CATALOG: &[u8] = include_bytes!("testdata/tools.json");
const CATALOG_SIG: &str = include_str!("testdata/tools.json.sig");

fn tmp(name: &str) -> PathBuf {
    static N: AtomicUsize = AtomicUsize::new(0);
    let d = std::env::temp_dir().join(format!(
        "jv-spike-{name}-{}-{}-{}",
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
fn tool_without_windows_line_is_coming_for_windows() {
    let c = catalog::verify_and_parse(CATALOG, CATALOG_SIG, TEST_PUBLIC_KEY).unwrap();
    // Runde A: katalogen har bare Mac-linjer.
    assert!(matches!(
        c.availability("subtitles", TARGET_MAC, "0.1.0"),
        Availability::Available(_)
    ));
    assert_eq!(
        c.availability("subtitles", TARGET_WINDOWS, "0.1.0"),
        Availability::NotForPlatform
    );
    assert_eq!(
        c.availability("nynorsk", TARGET_MAC, "0.1.0"),
        Availability::NotForPlatform
    );
    assert!(matches!(
        c.availability("ocr", TARGET_MAC, "0.0.9"),
        Availability::NeedsNewerApp(_)
    ));
}

#[test]
fn version_comparison() {
    assert!(catalog::version_at_least("0.10.0", "0.9.3"));
    assert!(catalog::version_at_least("1.0", "1.0.0"));
    assert!(!catalog::version_at_least("0.1.0", "0.1.1"));
}

// ------------------------------------------------------------- falsk pakke

/// En falsk pakke: et skallskript som `entry`, pakket med systemets tar.
#[cfg(unix)]
fn fake_package(version_output: &str) -> (PathBuf, catalog::CatalogEntry) {
    use std::os::unix::fs::PermissionsExt;
    let src = tmp("falsk-src");
    std::fs::create_dir_all(src.join("bin")).unwrap();
    let script = format!(
        "#!/bin/sh\nif [ \"$1\" = --version ]; then echo '{version_output}'; exit 0; fi\nexit 3\n"
    );
    std::fs::write(src.join("bin/jv"), script).unwrap();
    std::fs::set_permissions(src.join("bin/jv"), std::fs::Permissions::from_mode(0o755)).unwrap();
    std::fs::write(
        src.join(package::MANIFEST),
        r#"{"schema":1,"id":"falsk","version":"1.0.0","target":"aarch64-apple-darwin","entry":"bin/jv","path":["bin"],"env":{"JV_FALSK":"bin/jv"},"codesign":["bin/jv"]}"#,
    )
    .unwrap();
    let arch = tmp("falsk-arkiv").join("falsk.tar.gz");
    assert!(std::process::Command::new("tar")
        .env("COPYFILE_DISABLE", "1")
        .arg("-czf")
        .arg(&arch)
        .arg("-C")
        .arg(&src)
        .args(["jv-package.json", "bin"])
        .status()
        .unwrap()
        .success());
    let (sha, bytes) = package::sha256_file(&arch).unwrap();
    let entry = catalog::CatalogEntry {
        id: "falsk".into(),
        name: "Falsk".into(),
        version: "1.0.0".into(),
        target: TARGET_MAC.into(),
        url: "https://example.invalid/falsk.tar.gz".into(),
        bytes,
        sha256: sha,
        min_app_version: "0.1.0".into(),
        min_os: None,
        notes: String::new(),
    };
    (arch, entry)
}

#[cfg(unix)]
#[test]
fn package_with_wrong_sha256_is_rejected_and_deleted() {
    let (arch, mut entry) = fake_package(r#"{"id":"falsk","version":"1.0.0"}"#);
    entry.sha256 = "0".repeat(64);
    let tools = tmp("verktoy");
    assert_eq!(
        package::install(&entry, &arch, &tools, package::SignatureCheck::SkipForTests).unwrap_err(),
        JvError::ChecksumMismatch
    );
    assert!(!arch.exists(), "pakken med feil sum skal slettes");
    assert!(!tools.join("falsk").join("1.0.0").exists());
}

#[cfg(unix)]
#[test]
fn failing_trial_run_keeps_old_version() {
    // --version svarer med feil id: prøvekjøringen skal feile.
    let (arch, entry) = fake_package(r#"{"id":"feil","version":"9.9.9"}"#);
    let tools = tmp("verktoy");
    let old = tools.join("falsk").join("0.9.0");
    std::fs::create_dir_all(&old).unwrap();
    assert_eq!(
        package::install(&entry, &arch, &tools, package::SignatureCheck::SkipForTests).unwrap_err(),
        JvError::TrialRunFailed
    );
    assert!(old.exists(), "den gamle versjonen skal stå urørt");
    assert!(!tools.join("falsk").join(".ny-1.0.0").exists());
    assert!(!tools.join("falsk").join("1.0.0").exists());
}

#[cfg(unix)]
#[test]
fn good_fake_package_replaces_old_version() {
    let (arch, entry) = fake_package(r#"{"id":"falsk","version":"1.0.0"}"#);
    let tools = tmp("verktoy");
    let old = tools.join("falsk").join("0.9.0");
    std::fs::create_dir_all(&old).unwrap();
    let (root, _) =
        package::install(&entry, &arch, &tools, package::SignatureCheck::SkipForTests).unwrap();
    assert_eq!(root, tools.join("falsk").join("1.0.0"));
    assert!(
        !old.exists(),
        "den gamle versjonen slettes etter vellykket prøvekjøring"
    );
    // Miljøet peker inn i pakken.
    let m = package::read_manifest(&root).unwrap();
    let env = package::command_env(&root, &m);
    let jv = env.iter().find(|(k, _)| k == "JV_FALSK").unwrap();
    assert_eq!(std::path::PathBuf::from(&jv.1), root.join("bin").join("jv"));
    let path = env.iter().find(|(k, _)| k == "PATH").unwrap();
    assert!(path
        .1
        .to_string_lossy()
        .starts_with(&*root.join("bin").to_string_lossy()));
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
            package::SignatureCheck::Team(package::TEAM_ID)
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

// ------------------------------------------------------------- hele kjeden

/// Liten HTTP-server over en mappe, med Range og valgfritt brudd i første
/// forespørsel mot hver pakke.
struct DirServer {
    port: u16,
    requests: Arc<AtomicUsize>,
}

impl DirServer {
    fn start(dir: PathBuf, cut_first_after: Option<usize>) -> DirServer {
        let l = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = l.local_addr().unwrap().port();
        let requests = Arc::new(AtomicUsize::new(0));
        let reqs = requests.clone();
        let cut_done = Arc::new(Mutex::new(std::collections::HashSet::new()));
        std::thread::spawn(move || {
            for s in l.incoming().flatten() {
                let dir = dir.clone();
                let reqs = reqs.clone();
                let cut_done = cut_done.clone();
                std::thread::spawn(move || {
                    let _ = serve(s, &dir, &reqs, cut_first_after, &cut_done);
                });
            }
        });
        DirServer { port, requests }
    }
}

use std::sync::Mutex;

fn serve(
    mut s: TcpStream,
    dir: &Path,
    reqs: &AtomicUsize,
    cut: Option<usize>,
    cut_done: &Mutex<std::collections::HashSet<String>>,
) -> std::io::Result<()> {
    let mut r = BufReader::new(s.try_clone()?);
    let mut line = String::new();
    r.read_line(&mut line)?;
    let path = line.split_whitespace().nth(1).unwrap_or("/").to_string();
    let mut range = None;
    loop {
        let mut h = String::new();
        r.read_line(&mut h)?;
        if h == "\r\n" || h.is_empty() {
            break;
        }
        if let Some((k, v)) = h.split_once(':') {
            if k.eq_ignore_ascii_case("range") {
                range = Some(v.trim().trim_start_matches("bytes=").to_string());
            }
        }
    }
    reqs.fetch_add(1, Ordering::SeqCst);
    let name = path.trim_start_matches('/');
    if name.contains('/') || name.contains("..") {
        return write!(
            s,
            "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        );
    }
    let Ok(data) = std::fs::read(dir.join(name)) else {
        return write!(
            s,
            "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        );
    };
    let len = data.len();
    let (start, end) = match range {
        Some(rg) => {
            let (a, z) = rg.split_once('-').unwrap();
            let a: usize = a.parse().unwrap();
            let z = if z.is_empty() {
                len - 1
            } else {
                z.parse::<usize>().unwrap().min(len - 1)
            };
            (a, z)
        }
        None => (0, len - 1),
    };
    let body = &data[start..=end];
    write!(
        s,
        "HTTP/1.1 206 Partial Content\r\nContent-Range: bytes {start}-{end}/{len}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        body.len()
    )?;
    let should_cut = name.ends_with(".tar.gz")
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

fn http_get(url: &str) -> Vec<u8> {
    let agent: ureq::Agent = ureq::Agent::config_builder()
        .http_status_as_error(false)
        .build()
        .into();
    let mut resp = agent.get(url).call().unwrap();
    let mut v = Vec::new();
    resp.body_mut()
        .as_reader()
        .take(catalog::MAX_CATALOG_BYTES as u64 + 1)
        .read_to_end(&mut v)
        .unwrap();
    v
}

fn ms(d: Duration) -> String {
    format!("{} ms", d.as_millis())
}

#[test]
#[ignore = "krever pakkene fra sidecar/build/bygg-mac.sh; sett JV_SPIKE_DIST"]
fn spike_full_chain() {
    let dist = PathBuf::from(std::env::var("JV_SPIKE_DIST").expect("JV_SPIKE_DIST"));
    let testdata = dist.join("../../../jv/testdata");
    let server = DirServer::start(dist.clone(), Some(3 * 1024 * 1024));
    let base = format!("http://127.0.0.1:{}", server.port);

    // 1. Katalog fra testserveren, signaturen før alt annet.
    let t = Instant::now();
    let json = http_get(&format!("{base}/tools.json"));
    let sig = String::from_utf8(http_get(&format!("{base}/tools.json.sig"))).unwrap();
    let cat = catalog::verify_and_parse(&json, &sig, TEST_PUBLIC_KEY).expect("signatur");
    println!("katalog: hentet og kontrollert på {}", ms(t.elapsed()));

    let data_dir = std::env::var("JV_SPIKE_DATA_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| tmp("appdata"));
    let tools_dir = data_dir.join("verktoy");
    let downloads = data_dir.join("nedlasting");
    let policy = HostPolicy::for_tests(&["127.0.0.1"]);

    for (id, args) in [
        ("subtitles", vec!["subtitles/transkripsjon.json"]),
        ("ocr", vec!["ocr/skannet_side.pdf"]),
    ] {
        let entry = match cat.availability(id, catalog::CURRENT_TARGET, "0.1.0") {
            Availability::Available(e) => e.clone(),
            other => panic!("{id}: {other:?}"),
        };
        // Katalogen peker på GitHub; testen sender det til testserveren.
        let file = entry.url.rsplit('/').next().unwrap().to_string();
        let local = catalog::CatalogEntry {
            url: format!("{base}/{file}"),
            ..entry.clone()
        };

        // 2. Nedlasting: første forespørsel brytes etter 3 MB, koden gjenopptar.
        let before = server.requests.load(Ordering::SeqCst);
        let cancel = AtomicBool::new(false);
        let mut last = 0u64;
        let t = Instant::now();
        let archive =
            package::download_package(&local, &downloads, &policy, &cancel, &mut |done, _| {
                last = done
            })
            .expect("nedlasting");
        let t_download = t.elapsed();
        assert_eq!(last, entry.bytes);
        let n_req = server.requests.load(Ordering::SeqCst) - before;
        assert!(n_req >= 2, "bruddet skal gi minst én ny forespørsel");

        // 3–5. SHA-256, utpakking, codesign med team-krav, --version, flytt på plass.
        let (root, times) = package::install(
            &entry,
            &archive,
            &tools_dir,
            package::SignatureCheck::Team(package::TEAM_ID),
        )
        .expect("install");
        let m = package::read_manifest(&root).unwrap();

        // Oppstartstid: --version fem ganger (første er «kald» etter utpakking).
        let mut starts = Vec::new();
        for _ in 0..5 {
            let t = Instant::now();
            package::trial_run(&root, &m).unwrap();
            starts.push(t.elapsed().as_millis());
        }

        // 6. Kjør verktøyet på testfilen.
        let out_dir = tmp("ut");
        let mut argv: Vec<std::ffi::OsString> = vec![id.into()];
        argv.extend(args.iter().map(|a| testdata.join(a).into_os_string()));
        argv.extend(["--out".into(), out_dir.clone().into_os_string()]);
        let t = Instant::now();
        let out = package::run(&root, &m, &argv, Duration::from_secs(600)).unwrap();
        let t_run = t.elapsed();
        assert_eq!(out.code, Some(0), "kode");
        let report: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
        let outputs = report["outputs"].as_array().unwrap();
        assert!(!outputs.is_empty());
        for o in outputs {
            assert!(Path::new(o["path"].as_str().unwrap()).is_file());
        }
        let progress_lines = out
            .stderr
            .split(|&b| b == b'\n')
            .filter(|l| l.starts_with(b"{\"progress\""))
            .count();

        let unpacked = dir_size(&root);
        println!(
            "{id}: arkiv {:.1} MB, utpakket {:.1} MB | nedlasting (lokal, med brudd, {n_req} forespørsler) {} | \
             sha256 {} | utpakking {} | codesign {} | prøvekjøring {} | --version x5: {:?} ms | \
             kjøring {} ({progress_lines} fremdriftslinjer, {} utfiler)",
            entry.bytes as f64 / 1e6,
            unpacked as f64 / 1e6,
            ms(t_download),
            ms(times.sha256),
            ms(times.extract),
            ms(times.codesign),
            ms(times.trial_run),
            starts,
            ms(t_run),
            outputs.len(),
        );
        let _ = std::fs::remove_dir_all(&out_dir);
    }
}

fn dir_size(p: &Path) -> u64 {
    let mut total = 0;
    if let Ok(rd) = std::fs::read_dir(p) {
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
