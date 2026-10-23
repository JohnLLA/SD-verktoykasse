// SPDX-License-Identifier: AGPL-3.0-or-later
//! En falsk pakke som prøver alt sandkassen skal stoppe (Mac).
//!
//! Testprogrammet er en kopi av denne testbinærfila, lagt inn i en pakke
//! (`bin/jv`). Kopien startes gjennom [`runner::command`] og `sandbox-exec`
//! med den samme profilen som appen bruker, og kjører bare testen
//! [`sandbox_probe_main`] (libtest: `<navn> <oppsett> --exact --ignored`). Den leser
//! oppsettet (en JSON-fil i utmappen), prøver hver ting og skriver resultatet
//! til utmappen. Uten oppsett (vanlig `cargo test --ignored`) gjør den ingenting.
//!
//! Et kopiert systemprogram (som /bin/sh) kan ikke brukes: macOS stopper
//! kopier av Apples egne programmer utenfor systemmappene.

use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fs;
use std::net::{TcpListener, TcpStream, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};

use super::super::args::{build, RunRequest};
use super::super::error::JvError;
use super::super::package::Manifest;
use super::super::runner::{self, Finished};
use super::{Access, Sandbox};

const PROBE_TEST: &str = "tools::jv::sandbox::probe::sandbox_probe_main";
const CONFIG_NAME: &str = "jv-probe-oppsett.json";
const RESULT_NAME: &str = "jv-probe-resultat.json";
const SELECTED_CONTENT: &[u8] = b"valgt fil\n";

#[derive(Debug, Serialize, Deserialize, Default)]
struct ProbeConfig {
    /// `probe`, `mark` (skriv en markør og avslutt) eller `sleep` (barn + sov).
    mode: String,
    selected: Vec<PathBuf>,
    out: PathBuf,
    home: PathBuf,
    home_secret: PathBuf,
    volumes_secret: PathBuf,
    port: u16,
}

fn outcome<T>(r: std::io::Result<T>) -> String {
    match r {
        Ok(_) => "ok".into(),
        Err(e) => format!("stoppet:{:?}", e.kind()),
    }
}

/// Testprogrammet. Gjør ingenting uten oppsettsfila som argument.
#[test]
#[ignore = "startes bare som falsk pakke av sandkassetestene"]
// Barnet i «sleep» skal leve videre til avbryt dreper prosessgruppen.
#[allow(clippy::zombie_processes)]
fn sandbox_probe_main() {
    let Some(cfg_path) = std::env::args_os()
        .map(PathBuf::from)
        .find(|p| p.file_name().is_some_and(|n| n == CONFIG_NAME))
    else {
        return;
    };
    let cfg: ProbeConfig = serde_json::from_slice(&fs::read(&cfg_path).unwrap()).unwrap();
    let me = std::env::current_exe().unwrap();
    let pkg = me.parent().unwrap().parent().unwrap().to_path_buf();
    match cfg.mode.as_str() {
        "mark" => {
            fs::write(cfg.out.join("startet"), b"1").unwrap();
        }
        "sleep" => {
            if std::env::var_os("JV_PROBE_CHILD").is_some() {
                std::thread::sleep(Duration::from_secs(3));
                fs::write(cfg.out.join("barnet-levde"), b"1").unwrap();
                return;
            }
            Command::new(&me)
                .args(std::env::args_os().skip(1))
                .env("JV_PROBE_CHILD", "1")
                .spawn()
                .unwrap();
            eprintln!("{{\"progress\": 0.1}}");
            std::thread::sleep(Duration::from_secs(30));
        }
        _ => {
            let mut r: BTreeMap<&str, String> = BTreeMap::new();
            // Det som skal virke.
            for (i, p) in cfg.selected.iter().enumerate() {
                let ok = fs::read(p).map(|b| b == SELECTED_CONTENT);
                r.insert(
                    ["les_valgt_0", "les_valgt_1", "les_valgt_2"][i.min(2)],
                    match ok {
                        Ok(true) => "ok".into(),
                        Ok(false) => "feil innhold".into(),
                        Err(e) => format!("stoppet:{:?}", e.kind()),
                    },
                );
            }
            r.insert(
                "skriv_utmappe",
                outcome(fs::write(cfg.out.join("skrevet.txt"), b"x")),
            );
            let tmpdir = std::env::var_os("TMPDIR").map(PathBuf::from);
            r.insert(
                "skriv_tmpdir",
                outcome(match &tmpdir {
                    Some(t) => fs::write(t.join("tmp.txt"), b"x"),
                    None => Err(std::io::ErrorKind::NotFound.into()),
                }),
            );
            r.insert("les_pakken", outcome(fs::read(pkg.join("jv-package.json"))));
            // Det som skal stoppes.
            r.insert(
                "nett_127",
                outcome(TcpStream::connect_timeout(
                    &([127, 0, 0, 1], cfg.port).into(),
                    Duration::from_secs(2),
                )),
            );
            // Et navn som må slås opp (mDNSResponder). «localhost» løses lokalt
            // uten oppslag og sier ingenting om nett.
            r.insert("dns", outcome(("example.com", 80).to_socket_addrs()));
            r.insert("les_home", outcome(fs::read(&cfg.home_secret)));
            let mut via_data = OsString::from("/System/Volumes/Data");
            via_data.push(cfg.home_secret.as_os_str());
            r.insert(
                "les_home_via_data",
                outcome(fs::read(PathBuf::from(via_data))),
            );
            r.insert("liste_home", outcome(fs::read_dir(&cfg.home)));
            r.insert("les_volumes", outcome(fs::read(&cfg.volumes_secret)));
            r.insert(
                "skriv_home",
                outcome(fs::write(cfg.home.join(".jv-probe-skrevet"), b"x")),
            );
            r.insert(
                "skriv_tmp",
                outcome(fs::write("/private/tmp/jv-probe-skrevet", b"x")),
            );
            r.insert("skriv_pakken", outcome(fs::write(pkg.join("endret"), b"x")));
            r.insert(
                "skriv_ved_siden_av_utmappen",
                outcome(fs::write(
                    cfg.out.parent().unwrap().join("ved-siden-av.txt"),
                    b"x",
                )),
            );
            r.insert(
                "start_sh",
                outcome(Command::new("/bin/sh").args(["-c", "exit 0"]).status()),
            );
            r.insert(
                "start_open",
                outcome(
                    Command::new("/usr/bin/open")
                        .arg("https://example.com")
                        .status(),
                ),
            );
            r.insert(
                "start_perl",
                outcome(Command::new("/usr/bin/perl").args(["-e", "1"]).status()),
            );
            fs::write(
                cfg.out.join(RESULT_NAME),
                serde_json::to_vec_pretty(&r).unwrap(),
            )
            .unwrap();
        }
    }
}

// ------------------------------------------------------------- oppsett

fn tmp(name: &str) -> PathBuf {
    static N: AtomicUsize = AtomicUsize::new(0);
    let d = std::env::temp_dir().join(format!(
        "jv-probe-{name}-{}-{}",
        std::process::id(),
        N.fetch_add(1, Ordering::SeqCst)
    ));
    fs::create_dir_all(&d).unwrap();
    d
}

/// Den falske pakken (én per testprosess): en kopi av testbinærfila som `bin/jv`.
fn probe_package() -> &'static (PathBuf, Manifest) {
    static PKG: OnceLock<(PathBuf, Manifest)> = OnceLock::new();
    PKG.get_or_init(|| {
        let root = tmp("pakke").join("subtitles").join("1.0.0");
        fs::create_dir_all(root.join("bin")).unwrap();
        fs::copy(std::env::current_exe().unwrap(), root.join("bin/jv")).unwrap();
        let manifest = r#"{"schema":1,"id":"subtitles","version":"1.0.0","target":"aarch64-apple-darwin","entry":"bin/jv","path":["bin"]}"#;
        fs::write(root.join("jv-package.json"), manifest).unwrap();
        (root, serde_json::from_str(manifest).unwrap())
    })
}

fn probe_args(cfg_path: &Path) -> Vec<OsString> {
    vec![
        PROBE_TEST.into(),
        cfg_path.into(),
        "--exact".into(),
        "--ignored".into(),
        "--nocapture".into(),
        "--test-threads=1".into(),
        "-q".into(),
    ]
}

/// En fil på en ekstern disk (/Volumes). Ligger repoet på en ekstern disk
/// (John Inges Mac), brukes den; ellers (CI) lages en liten diskavbildning.
struct VolumeFile {
    path: PathBuf,
    mount: Option<PathBuf>,
}

impl VolumeFile {
    fn new() -> VolumeFile {
        let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        if manifest.starts_with("/Volumes/") {
            let dir = manifest
                .join("target")
                .join(format!("jv-probe-volum-{}", std::process::id()));
            fs::create_dir_all(&dir).unwrap();
            let path = dir.join("hemmelig.txt");
            fs::write(&path, b"hemmelig").unwrap();
            return VolumeFile { path, mount: None };
        }
        let image = tmp("volum").join("v.dmg");
        let name = format!("JVPROBE{}", std::process::id());
        let ok = Command::new("/usr/bin/hdiutil")
            .args([
                "create", "-quiet", "-size", "4m", "-fs", "HFS+", "-volname", &name,
            ])
            .arg(&image)
            .status()
            .unwrap()
            .success();
        assert!(ok, "hdiutil create");
        let out = Command::new("/usr/bin/hdiutil")
            .args(["attach", "-nobrowse", "-noverify", "-noautoopen"])
            .arg(&image)
            .output()
            .unwrap();
        assert!(out.status.success(), "hdiutil attach");
        let mount = String::from_utf8_lossy(&out.stdout)
            .lines()
            .filter_map(|l| l.split('\t').next_back())
            .map(|s| s.trim().to_string())
            .find(|s| s.starts_with("/Volumes/"))
            .map(PathBuf::from)
            .expect("monteringspunkt under /Volumes");
        let path = mount.join("hemmelig.txt");
        fs::write(&path, b"hemmelig").unwrap();
        VolumeFile {
            path,
            mount: Some(mount),
        }
    }
}

impl Drop for VolumeFile {
    fn drop(&mut self) {
        match &self.mount {
            Some(m) => {
                let _ = Command::new("/usr/bin/hdiutil")
                    .args(["detach", "-quiet", "-force"])
                    .arg(m)
                    .status();
            }
            None => {
                let _ = fs::remove_dir_all(self.path.parent().unwrap());
            }
        }
    }
}

/// En fil i HOME som ikke er valgt. Slettes etterpå.
struct HomeFile(PathBuf);

impl HomeFile {
    fn new() -> HomeFile {
        static N: AtomicUsize = AtomicUsize::new(0);
        let home = PathBuf::from(std::env::var_os("HOME").expect("HOME"));
        let p = home.join(format!(
            ".jv-probe-hemmelig-{}-{}",
            std::process::id(),
            N.fetch_add(1, Ordering::SeqCst)
        ));
        fs::write(&p, b"hemmelig").unwrap();
        HomeFile(p)
    }
}

impl Drop for HomeFile {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
    }
}

fn never() -> AtomicBool {
    AtomicBool::new(false)
}

fn scratch_entries(sb: &Sandbox) -> usize {
    fs::read_dir(sb.scratch_root())
        .map(|rd| rd.count())
        .unwrap_or(0)
}

// ------------------------------------------------------------- testene

/// Filnavn med mellomrom, æøå, `"`, `(`, `)`, `;`, `=` og bindestrek først.
const NASTY_NAME: &str = "-valgt \"fil\" (1); a=b æøå).txt";

#[test]
fn fake_package_is_stopped_by_the_sandbox() {
    let (root, m) = probe_package();
    let work = tmp("arbeid");
    let appdata = tmp("appdata");
    let sb = Sandbox::new(&appdata);
    // Valgt fil med vanskelig navn (gjennom hvitelisten i args) og én med
    // linjeskift (rett inn i Access; args avviser linjeskift).
    let inn = work.join("inn");
    fs::create_dir_all(&inn).unwrap();
    let nasty = inn.join(NASTY_NAME);
    fs::write(&nasty, SELECTED_CONTENT).unwrap();
    let newline = inn.join("linje\nskift.txt");
    fs::write(&newline, SELECTED_CONTENT).unwrap();
    let not_selected = inn.join("ikke valgt.txt");
    fs::write(&not_selected, b"hemmelig").unwrap();
    let out = work.join("ut (resultat)");
    let req: RunRequest = serde_json::from_value(serde_json::json!({
        "inputs": [nasty],
        "out_dir": out,
    }))
    .unwrap();
    let mut access = build("subtitles", &req).unwrap().access;
    access.read.push(newline.clone());
    fs::create_dir_all(&out).unwrap();

    let home_file = HomeFile::new();
    let volume_file = VolumeFile::new();
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    listener.set_nonblocking(true).unwrap();
    let cfg = ProbeConfig {
        mode: "probe".into(),
        selected: vec![nasty.clone(), newline.clone()],
        out: out.clone(),
        home: PathBuf::from(std::env::var_os("HOME").unwrap()),
        home_secret: home_file.0.clone(),
        volumes_secret: volume_file.path.clone(),
        port: listener.local_addr().unwrap().port(),
    };
    let cfg_path = out.join(CONFIG_NAME);
    fs::write(&cfg_path, serde_json::to_vec(&cfg).unwrap()).unwrap();

    let launch = runner::command(root, m, &probe_args(&cfg_path), &access, &sb).unwrap();
    let scratch = launch.scratch_dir().unwrap().to_path_buf();
    assert!(
        scratch.starts_with(&appdata),
        "egen mappe i appens datamappe"
    );
    let r = runner::run_job(
        launch,
        &never(),
        Some(Duration::from_secs(120)),
        &mut |_| {},
    )
    .unwrap();
    // libtest skriver «running 1 test» på stdout, så rapporten er ikke JSON.
    assert!(
        matches!(
            r,
            Finished::Failed {
                error: JvError::ReportInvalid,
                ..
            }
        ),
        "{r:?}"
    );
    assert!(!scratch.exists(), "mappen for kjøringen skal være slettet");
    assert_eq!(scratch_entries(&sb), 0);

    let result: BTreeMap<String, String> =
        serde_json::from_slice(&fs::read(out.join(RESULT_NAME)).expect("resultatet")).unwrap();
    println!("{}", serde_json::to_string_pretty(&result).unwrap());
    for ok in [
        "les_valgt_0",
        "les_valgt_1",
        "skriv_utmappe",
        "skriv_tmpdir",
        "les_pakken",
    ] {
        assert_eq!(result[ok], "ok", "{ok} skal virke");
    }
    for stopped in [
        "nett_127",
        "dns",
        "les_home",
        "les_home_via_data",
        "liste_home",
        "les_volumes",
        "skriv_home",
        "skriv_tmp",
        "skriv_pakken",
        "skriv_ved_siden_av_utmappen",
        "start_sh",
        "start_open",
        "start_perl",
    ] {
        assert!(
            result[stopped].starts_with("stoppet:"),
            "{stopped} skal stoppes: {}",
            result[stopped]
        );
    }
    // Ingen tilkobling kom fram, og ingenting ble skrevet utenfor utmappen.
    assert!(listener.accept().is_err(), "ingen tilkobling til 127.0.0.1");
    assert!(!cfg.home.join(".jv-probe-skrevet").exists());
    assert!(!Path::new("/private/tmp/jv-probe-skrevet").exists());
    assert!(!root.join("endret").exists());
    assert!(!work.join("ved-siden-av.txt").exists());
    assert!(out.join("skrevet.txt").exists());
    let _ = not_selected;
    let _ = fs::remove_dir_all(&work);
    let _ = fs::remove_dir_all(&appdata);
}

#[test]
fn cancel_kills_the_sandboxed_process_tree_and_removes_the_scratch_dir() {
    let (root, m) = probe_package();
    let work = tmp("avbryt");
    let appdata = tmp("appdata");
    let sb = Sandbox::new(&appdata);
    let out = work.join("ut");
    fs::create_dir_all(&out).unwrap();
    let cfg = ProbeConfig {
        mode: "sleep".into(),
        out: out.clone(),
        ..Default::default()
    };
    let cfg_path = out.join(CONFIG_NAME);
    fs::write(&cfg_path, serde_json::to_vec(&cfg).unwrap()).unwrap();
    let access = Access {
        read: vec![],
        write_dir: Some(out.clone()),
    };
    let launch = runner::command(root, m, &probe_args(&cfg_path), &access, &sb).unwrap();
    let scratch = launch.scratch_dir().unwrap().to_path_buf();
    let cancel = AtomicBool::new(false);
    let mut seen = Vec::new();
    let t = Instant::now();
    let r = runner::run_job(launch, &cancel, None, &mut |p| {
        seen.push(p);
        cancel.store(true, Ordering::SeqCst);
    })
    .unwrap();
    assert_eq!(r, Finished::Cancelled);
    assert_eq!(seen, vec![0.1], "fremdriften leses gjennom sandkassen");
    assert!(t.elapsed() < Duration::from_secs(20));
    assert!(!scratch.exists(), "mappen for kjøringen slettes ved avbryt");
    std::thread::sleep(Duration::from_secs(4));
    assert!(
        !out.join("barnet-levde").exists(),
        "barneprosessen skal være drept"
    );
    let _ = fs::remove_dir_all(&work);
    let _ = fs::remove_dir_all(&appdata);
}

#[test]
fn nothing_runs_without_sandbox_exec_or_with_a_broken_profile() {
    let (root, m) = probe_package();
    let work = tmp("feil-lukker");
    let appdata = tmp("appdata");
    let out = work.join("ut");
    fs::create_dir_all(&out).unwrap();
    let cfg = ProbeConfig {
        mode: "mark".into(),
        out: out.clone(),
        ..Default::default()
    };
    let cfg_path = out.join(CONFIG_NAME);
    fs::write(&cfg_path, serde_json::to_vec(&cfg).unwrap()).unwrap();
    let access = Access {
        read: vec![],
        write_dir: Some(out.clone()),
    };
    let args = probe_args(&cfg_path);

    // 1. sandbox-exec mangler (falsk sti): ingenting startes, ingen mappe lages.
    let missing = Sandbox::new(&appdata).with_exec(Path::new("/finnes/ikke/sandbox-exec"));
    assert_eq!(
        runner::command(root, m, &args, &access, &missing).unwrap_err(),
        JvError::SandboxFailed
    );
    assert_eq!(scratch_entries(&missing), 0);

    // 2. Profilen avvises av sandbox-exec: verktøyet starter ikke.
    for broken in [
        "(version 1)(allow default)(deny ukjent-operasjon)",
        "(version 1)(allow file-read* (literal (param \"FINNES_IKKE\")))",
        "ikke en profil (",
    ] {
        let sb = Sandbox::new(&appdata).with_profile(broken);
        let launch = runner::command(root, m, &args, &access, &sb).unwrap();
        let r =
            runner::run_job(launch, &never(), Some(Duration::from_secs(60)), &mut |_| {}).unwrap();
        assert_eq!(
            r,
            Finished::Failed {
                error: JvError::SandboxFailed,
                message: None
            },
            "{broken}"
        );
        assert!(!out.join("startet").exists(), "{broken}");
        assert_eq!(scratch_entries(&sb), 0);
    }

    // 3. Kontroll: med den ekte profilen starter den.
    let sb = Sandbox::new(&appdata);
    let launch = runner::command(root, m, &args, &access, &sb).unwrap();
    let _ = runner::run_job(launch, &never(), Some(Duration::from_secs(60)), &mut |_| {});
    assert!(out.join("startet").exists());
    let _ = fs::remove_dir_all(&work);
    let _ = fs::remove_dir_all(&appdata);
}

#[test]
fn trial_run_with_a_failing_sandbox_is_a_sandbox_error() {
    let (root, m) = probe_package();
    let appdata = tmp("appdata");
    let sb = Sandbox::new(&appdata).with_profile("(version 1)(deny ukjent-operasjon)");
    assert_eq!(
        super::super::package::trial_run(root, m, &sb).unwrap_err(),
        JvError::SandboxFailed
    );
    let _ = fs::remove_dir_all(&appdata);
}
