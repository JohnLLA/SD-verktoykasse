// SPDX-License-Identifier: AGPL-3.0-or-later
//! Kjøring av en installert pakke: argumentliste (aldri skall), rent miljø,
//! sandkasse (Mac), fremdrift fra stderr, rapport fra stdout og avbryt.
//!
//! - Mac: pakken startes gjennom `/usr/bin/sandbox-exec` med profilen i
//!   `sandbox/profil.sb` (uten nett, lesing bare av pakken og filene brukeren
//!   valgte, skriving bare i utmappen og en egen TMPDIR). Mangler
//!   `sandbox-exec`, eller avviser den profilen, kjøres verktøyet ikke.
//! - Pakken startes i en egen prosessgruppe (Mac) eller uten konsollvindu
//!   (Windows). Avbryt dreper hele treet, også underprosesser som ffmpeg,
//!   tesseract og ocrmypdfs arbeidere.
//! - stderr leses linje for linje: `{"progress": 0.42}` blir en hendelse.
//!   Andre linjer holdes (avgrenset) bare for å vise verktøyets norske
//!   feilmelding ved kode 1. Ingenting av det logges (regel 2), heller ikke
//!   feilmeldinger fra `sandbox-exec`.
//! - Rapporten på stdout brukes bare ved kode 0 og må være et JSON-objekt.

use std::ffi::OsString;
use std::io::{BufRead, BufReader, Read};
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc;
use std::time::{Duration, Instant};

use super::error::{JvError, JvResult};
use super::package::{command_env, join_rel, Manifest};
use super::sandbox::{Access, Sandbox, Scratch, SANDBOX_EXEC_FAILURE_CODES};

/// Største rapport vi leser fra stdout.
pub const MAX_REPORT_BYTES: u64 = 32 * 1024 * 1024;
/// Hvor mye av stderr (utenom fremdriftslinjer) vi holder.
const MAX_STDERR_KEEP: usize = 16 * 1024;

/// En kjøring klar til start: kommandoen og (Mac) mappen for kjøringen, som
/// slettes når kjøringen er ferdig.
#[derive(Debug)]
pub struct Launch {
    pub cmd: Command,
    scratch: Option<Scratch>,
    sandboxed: bool,
}

impl Launch {
    /// Mappen for kjøringen (profil og TMPDIR), hvis den finnes.
    pub fn scratch_dir(&self) -> Option<&Path> {
        self.scratch.as_ref().map(|s| s.dir())
    }
}

impl From<Command> for Launch {
    fn from(cmd: Command) -> Launch {
        Launch {
            cmd,
            scratch: None,
            sandboxed: false,
        }
    }
}

fn base_command(program: &Path, root: &Path, m: &Manifest) -> Command {
    let mut cmd = Command::new(program);
    cmd.env_clear()
        .envs(command_env(root, m))
        .current_dir(root)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        cmd.process_group(0);
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd
}

/// Kommandoen for pakkens `entry` med argumentene og det rene miljøet.
///
/// Mac: `sandbox-exec -f <profil> -D … <entry> <args>`, med `access` (filene
/// brukeren valgte og utmappen) som parametere og `TMPDIR` i en egen mappe for
/// kjøringen. Windows: `entry` direkte, som før (sandkasse kommer i et eget steg).
pub fn command(
    root: &Path,
    m: &Manifest,
    args: &[OsString],
    access: &Access,
    sandbox: &Sandbox,
) -> JvResult<Launch> {
    let entry = join_rel(root, &m.entry);
    #[cfg(target_os = "macos")]
    if sandbox.enabled() {
        let (scratch, sb_args) = sandbox.prepare(root, &m.id, access)?;
        let mut cmd = base_command(sandbox.exec(), root, m);
        cmd.args(sb_args)
            .arg(&entry)
            .args(args)
            .env("TMPDIR", scratch.tmp());
        return Ok(Launch {
            cmd,
            scratch: Some(scratch),
            sandboxed: true,
        });
    }
    let _ = (access, sandbox);
    let mut cmd = base_command(&entry, root, m);
    cmd.args(args);
    Ok(cmd.into())
}

/// Dreper prosessen og alt den har startet.
pub fn kill_tree(child: &mut Child) {
    let pid = child.id();
    #[cfg(unix)]
    {
        let group = format!("-{pid}");
        let _ = Command::new("/bin/kill")
            .args(["-TERM", &group])
            .env_clear()
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
        let start = Instant::now();
        while start.elapsed() < Duration::from_secs(2) {
            if matches!(child.try_wait(), Ok(Some(_))) {
                break;
            }
            std::thread::sleep(Duration::from_millis(20));
        }
        let _ = Command::new("/bin/kill")
            .args(["-KILL", &group])
            .env_clear()
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let sys = std::env::var_os("SystemRoot").unwrap_or_else(|| "C:\\Windows".into());
        let _ = Command::new(Path::new(&sys).join("System32").join("taskkill.exe"))
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .creation_flags(0x0800_0000)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    let _ = child.kill();
    let _ = child.wait();
}

#[derive(Debug, Clone, PartialEq)]
pub enum Finished {
    /// Kode 0 og en gyldig rapport.
    Report(serde_json::Value),
    /// Avbrutt av brukeren.
    Cancelled,
    /// Annen kode. `message` er verktøyets norske feilmelding («Feil: …» uten
    /// prefikset) ved kode 1, ellers `None`.
    Failed {
        error: JvError,
        message: Option<String>,
    },
}

enum Line {
    Progress(f64),
    Other(String),
}

fn parse_line(line: &str) -> Line {
    let t = line.trim();
    if t.starts_with("{\"progress\"") {
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(t) {
            if let Some(p) = v.get("progress").and_then(|p| p.as_f64()) {
                if p.is_finite() {
                    return Line::Progress(p.clamp(0.0, 1.0));
                }
            }
        }
    }
    Line::Other(line.to_string())
}

/// Den norske feilmeldingen fra verktøyet: siste linje som begynner med «Feil:».
fn user_message(stderr_tail: &[String]) -> Option<String> {
    stderr_tail
        .iter()
        .rev()
        .find_map(|l| l.trim().strip_prefix("Feil:").map(|m| m.trim().to_string()))
        .filter(|m| !m.is_empty())
        .map(|m| m.chars().take(2000).collect())
}

/// `sandbox-exec` selv feilet: kode 65 eller 71 og en linje som begynner med
/// «sandbox-exec:» på stderr. Verktøyene bruker bare 0, 1 og 2.
fn sandbox_exec_failed(code: Option<i32>, stderr_tail: &[String]) -> bool {
    code.is_some_and(|c| SANDBOX_EXEC_FAILURE_CODES.contains(&c))
        && stderr_tail
            .iter()
            .any(|l| l.trim_start().starts_with("sandbox-exec:"))
}

/// Kjører til slutt, til avbryt eller til `timeout`. `on_progress` får 0..1.
///
/// Mappen for kjøringen (Mac) slettes når funksjonen returnerer, også ved feil
/// og avbryt (etter at prosesstreet er drept).
pub fn run_job(
    launch: impl Into<Launch>,
    cancel: &AtomicBool,
    timeout: Option<Duration>,
    on_progress: &mut dyn FnMut(f64),
) -> JvResult<Finished> {
    let Launch {
        mut cmd,
        scratch,
        sandboxed,
    } = launch.into();
    let result = run_command(&mut cmd, sandboxed, cancel, timeout, on_progress);
    drop(cmd);
    drop(scratch);
    result
}

fn run_command(
    cmd: &mut Command,
    sandboxed: bool,
    cancel: &AtomicBool,
    timeout: Option<Duration>,
    on_progress: &mut dyn FnMut(f64),
) -> JvResult<Finished> {
    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(_) if sandboxed => return Err(JvError::SandboxFailed),
        Err(e) => return Err(e.into()),
    };
    let stdout = child.stdout.take().ok_or(JvError::Internal)?;
    let stderr = child.stderr.take().ok_or(JvError::Internal)?;
    let t_out = std::thread::spawn(move || {
        let mut v = Vec::new();
        let r = stdout.take(MAX_REPORT_BYTES + 1).read_to_end(&mut v);
        (v, r.is_ok())
    });
    let (tx, rx) = mpsc::channel::<Line>();
    let t_err = std::thread::spawn(move || {
        let reader = BufReader::new(stderr);
        for line in reader.split(b'\n') {
            let Ok(bytes) = line else { break };
            let text = String::from_utf8_lossy(&bytes).into_owned();
            if tx.send(parse_line(&text)).is_err() {
                break;
            }
        }
    });
    let start = Instant::now();
    let mut tail: Vec<String> = Vec::new();
    let mut tail_bytes = 0usize;
    let mut drain = |rx: &mpsc::Receiver<Line>, tail: &mut Vec<String>, tail_bytes: &mut usize| {
        while let Ok(l) = rx.try_recv() {
            match l {
                Line::Progress(p) => on_progress(p),
                Line::Other(s) => {
                    *tail_bytes += s.len();
                    tail.push(s);
                    while *tail_bytes > MAX_STDERR_KEEP && tail.len() > 1 {
                        *tail_bytes -= tail.remove(0).len();
                    }
                }
            }
        }
    };
    let status = loop {
        drain(&rx, &mut tail, &mut tail_bytes);
        if cancel.load(Ordering::SeqCst) {
            kill_tree(&mut child);
            let _ = t_out.join();
            let _ = t_err.join();
            return Ok(Finished::Cancelled);
        }
        if timeout.is_some_and(|t| start.elapsed() > t) {
            kill_tree(&mut child);
            let _ = t_out.join();
            let _ = t_err.join();
            return Ok(Finished::Failed {
                error: JvError::ToolFailed { exit_code: None },
                message: None,
            });
        }
        match child.try_wait() {
            Ok(Some(s)) => break s,
            Ok(None) => std::thread::sleep(Duration::from_millis(20)),
            Err(e) => {
                kill_tree(&mut child);
                return Err(e.into());
            }
        }
    };
    let _ = t_err.join();
    drain(&rx, &mut tail, &mut tail_bytes);
    let (out, read_ok) = t_out.join().unwrap_or_default();
    let code = status.code();
    if sandboxed && sandbox_exec_failed(code, &tail) {
        // Profilen ble avvist eller verktøyet kunne ikke startes: verktøyet har
        // ikke kjørt. Meldingen fra sandbox-exec (med stier) brukes ikke.
        return Ok(Finished::Failed {
            error: JvError::SandboxFailed,
            message: None,
        });
    }
    if code != Some(0) {
        let message = if code == Some(1) {
            user_message(&tail)
        } else {
            None
        };
        return Ok(Finished::Failed {
            error: JvError::ToolFailed { exit_code: code },
            message,
        });
    }
    if !read_ok || out.len() as u64 > MAX_REPORT_BYTES {
        return Ok(Finished::Failed {
            error: JvError::ReportInvalid,
            message: None,
        });
    }
    match serde_json::from_slice::<serde_json::Value>(&out) {
        Ok(v) if v.is_object() => Ok(Finished::Report(v)),
        _ => Ok(Finished::Failed {
            error: JvError::ReportInvalid,
            message: None,
        }),
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    fn script(body: &str) -> (std::path::PathBuf, Manifest) {
        static N: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
        let root = std::env::temp_dir().join(format!(
            "jv-runner-{}-{}",
            std::process::id(),
            N.fetch_add(1, Ordering::SeqCst)
        ));
        std::fs::create_dir_all(root.join("bin")).unwrap();
        std::fs::write(root.join("bin/jv"), format!("#!/bin/sh\n{body}\n")).unwrap();
        std::fs::set_permissions(root.join("bin/jv"), std::fs::Permissions::from_mode(0o755))
            .unwrap();
        let m: Manifest = serde_json::from_str(
            r#"{"schema":1,"id":"falsk","version":"1.0.0","target":"aarch64-apple-darwin","entry":"bin/jv","path":["bin"]}"#,
        )
        .unwrap();
        (root, m)
    }

    /// sh-skript kan ikke startes i sandkassen (sh står utenfor pakken):
    /// disse testene gjelder lesingen og avbryt, sandkassen testes i `tests.rs`.
    fn test_command(root: &Path, m: &Manifest) -> Launch {
        command(
            root,
            m,
            &[],
            &Access::default(),
            &Sandbox::disabled_for_tests(),
        )
        .unwrap()
    }

    fn run(body: &str, cancel_after: Option<Duration>) -> (Finished, Vec<f64>) {
        let (root, m) = script(body);
        let cancel = std::sync::Arc::new(AtomicBool::new(false));
        if let Some(d) = cancel_after {
            let c = cancel.clone();
            std::thread::spawn(move || {
                std::thread::sleep(d);
                c.store(true, Ordering::SeqCst);
            });
        }
        let mut seen = Vec::new();
        let r = run_job(test_command(&root, &m), &cancel, None, &mut |p| {
            seen.push(p)
        })
        .unwrap();
        (r, seen)
    }

    #[test]
    fn report_and_progress_are_read() {
        let (r, seen) = run(
            r#"echo '{"progress": 0.25}' >&2; echo 'noe annet' >&2; echo '{"progress": 1.5}' >&2
echo '{"tool":"falsk","summary":"ok","outputs":[]}'"#,
            None,
        );
        assert_eq!(seen, vec![0.25, 1.0]);
        match r {
            Finished::Report(v) => assert_eq!(v["summary"], "ok"),
            other => panic!("{other:?}"),
        }
    }

    #[test]
    fn report_is_ignored_unless_code_is_zero() {
        let (r, _) = run(
            r#"echo '{"summary":"ikke bruk"}'; echo 'Feil: Filen «x.pdf» er skadet.' >&2; exit 1"#,
            None,
        );
        assert_eq!(
            r,
            Finished::Failed {
                error: JvError::ToolFailed { exit_code: Some(1) },
                message: Some("Filen «x.pdf» er skadet.".into())
            }
        );
        let (r, _) = run(r#"echo 'Intern feil: boom' >&2; exit 2"#, None);
        assert_eq!(
            r,
            Finished::Failed {
                error: JvError::ToolFailed { exit_code: Some(2) },
                message: None
            }
        );
        let (r, _) = run("echo 'ikke json'", None);
        assert!(matches!(
            r,
            Finished::Failed {
                error: JvError::ReportInvalid,
                ..
            }
        ));
    }

    #[test]
    fn cancel_kills_the_whole_process_tree() {
        let marker = std::env::temp_dir().join(format!("jv-runner-barn-{}", std::process::id()));
        let _ = std::fs::remove_file(&marker);
        // Et barn som ville skrevet markøren etter 3 s, hvis det fikk leve.
        let body = format!(
            "(sleep 3; touch '{}') &\necho '{{\"progress\": 0.1}}' >&2\nsleep 30",
            marker.display()
        );
        // Avbryt så snart den første fremdriftslinjen er kommet (ikke etter en
        // fast tid, som kan være for kort når mange tester kjører samtidig).
        let (root, m) = script(&body);
        let cancel = AtomicBool::new(false);
        let mut seen = Vec::new();
        let t = Instant::now();
        let r = run_job(test_command(&root, &m), &cancel, None, &mut |p| {
            seen.push(p);
            cancel.store(true, Ordering::SeqCst);
        })
        .unwrap();
        assert_eq!(r, Finished::Cancelled);
        assert!(t.elapsed() < Duration::from_secs(20));
        assert_eq!(seen, vec![0.1]);
        std::thread::sleep(Duration::from_secs(4));
        assert!(!marker.exists(), "barneprosessen skal være drept");
    }
}
