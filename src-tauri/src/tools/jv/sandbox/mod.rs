// SPDX-License-Identifier: AGPL-3.0-or-later
//! Sandkassen for verktøyene på Mac: hver kjøring startes som
//! `/usr/bin/sandbox-exec -f <profil> -D NAVN=verdi … <entry> <args>`.
//!
//! - Profilen er den faste malen i `profil.sb`, bygget inn med `include_str!`.
//!   Stier sendes aldri inn i profilteksten, bare som `-D`-parametere. Det
//!   eneste som legges til, er linjer med parameternavn
//!   (`(allow file-read* (literal (param "IN_3")))`), én per fil brukeren valgte.
//! - Stiene gjøres kanoniske (`canonicalize`) før de sendes inn: `/var` og
//!   `/private/var` er samme sted, og profilen treffer bare den virkelige stien.
//! - Hver kjøring får en egen mappe i appens datamappe
//!   (`verktoy/.kjoring/<app-pid>-<n>/`) med profilen og `tmp/`, som blir
//!   `TMPDIR`. Mappen slettes når kjøringen er ferdig, også ved feil og avbryt
//!   ([`Scratch`] rydder i `Drop`). Mapper etter kjøringer som krasjet (appen
//!   som laget dem, kjører ikke lenger), slettes når neste kjøring starter.
//! - Feil lukker: mangler `sandbox-exec`, eller avviser den profilen, kjøres
//!   verktøyet ikke ([`JvError::SandboxFailed`]). Det finnes ingen innstilling
//!   for å slå sandkassen av; bare tester kan lage en [`Sandbox`] uten.
//! - Windows: ikke brukt i dette steget (AppContainer kommer i et eget steg).
//!
//! Ingenting her logger stier eller feilmeldinger fra `sandbox-exec` (regel 2).

// Bare Mac starter verktøy i sandkassen; profilbyggingen testes på begge.
#![cfg_attr(not(target_os = "macos"), allow(dead_code))]

use std::ffi::OsString;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use super::error::{JvError, JvResult};

/// Profilmalen (se `profil.sb`).
pub const PROFILE_TEMPLATE: &str = include_str!("profil.sb");

/// `sandbox-exec` er en del av macOS.
pub const SANDBOX_EXEC: &str = "/usr/bin/sandbox-exec";

/// Mappen under `verktoy/` med én undermappe per kjøring.
pub const SCRATCH_DIR: &str = ".kjoring";

/// Koder `sandbox-exec` avslutter med når profilen avvises (65, `EX_DATAERR`)
/// eller programmet ikke kan startes (71, `EX_OSERR`). Verktøyene selv bruker 0, 1 og 2.
pub const SANDBOX_EXEC_FAILURE_CODES: [i32; 2] = [65, 71];

/// Tolkere utenfor pakken som skript i pakken kan starte gjennom `#!`-linjen
/// (`process-exec-interpreter`, ikke vanlig start). Bare `metadata`:
/// exiftool er et Perl-skript som kjøres med macOS' egen Perl.
pub fn interpreters(tool_id: &str) -> &'static [&'static str] {
    match tool_id {
        "metadata" => &["/usr/bin/perl"],
        _ => &[],
    }
}

/// Det en kjøring får lese og skrive, fra hvitelisten i `args`.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Access {
    /// Filene og mappene brukeren valgte (og planfil og termliste).
    pub read: Vec<PathBuf>,
    /// Utmappen (finnes kanskje ikke ennå). `None`: verktøyet skriver ingen filer.
    pub write_dir: Option<PathBuf>,
}

/// En lesbar sti i profilen: en fil (`literal`) eller en mappe (`subpath`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReadPath {
    pub path: PathBuf,
    pub is_dir: bool,
}

/// Alle stier for én kjøring, kanoniske.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Resolved {
    pub home: PathBuf,
    pub package: PathBuf,
    pub out: PathBuf,
    pub tmp: PathBuf,
    pub read: Vec<ReadPath>,
    pub interpreters: Vec<PathBuf>,
}

/// Kanonisk sti. Finnes den ikke (en utmappe verktøyet lager selv), brukes den
/// kanoniske foreldermappen med det siste leddet.
pub fn canonical(p: &Path) -> JvResult<PathBuf> {
    if let Ok(c) = fs::canonicalize(p) {
        return Ok(c);
    }
    let parent = p.parent().ok_or(JvError::SandboxFailed)?;
    let name = p.file_name().ok_or(JvError::SandboxFailed)?;
    let parent = fs::canonicalize(parent).map_err(|_| JvError::InvalidArgs {
        reason: "out_parent_missing",
    })?;
    Ok(parent.join(name))
}

impl Resolved {
    /// Gjør stiene kanoniske. `tmp` er den midlertidige mappen for kjøringen.
    pub fn new(
        package: &Path,
        tool_id: &str,
        access: &Access,
        tmp: &Path,
        home: Option<&Path>,
    ) -> JvResult<Resolved> {
        let tmp = fs::canonicalize(tmp).map_err(|_| JvError::SandboxFailed)?;
        let package = fs::canonicalize(package).map_err(|_| JvError::SandboxFailed)?;
        // Uten HOME stenges hele /Users (står i profilen uansett).
        let home = home
            .and_then(|h| fs::canonicalize(h).ok())
            .unwrap_or_else(|| PathBuf::from("/Users"));
        let mut read = Vec::with_capacity(access.read.len());
        for p in &access.read {
            let path = fs::canonicalize(p).map_err(|_| JvError::InvalidArgs {
                reason: "input_missing",
            })?;
            let is_dir = path.is_dir();
            read.push(ReadPath { path, is_dir });
        }
        let out = match &access.write_dir {
            Some(d) => canonical(d)?,
            None => tmp.clone(),
        };
        Ok(Resolved {
            home,
            package,
            out,
            tmp,
            read,
            interpreters: interpreters(tool_id).iter().map(PathBuf::from).collect(),
        })
    }

    /// Profilteksten: malen og linjer med parameternavn. Ingen stier.
    pub fn profile(&self) -> String {
        let mut s = String::with_capacity(PROFILE_TEMPLATE.len() + 64 * self.read.len());
        s.push_str(PROFILE_TEMPLATE);
        if !s.ends_with('\n') {
            s.push('\n');
        }
        for (i, r) in self.read.iter().enumerate() {
            let filter = if r.is_dir { "subpath" } else { "literal" };
            s.push_str(&format!(
                "(allow file-read* ({filter} (param \"IN_{i}\")))\n"
            ));
        }
        for i in 0..self.interpreters.len() {
            s.push_str(&format!(
                "(allow process-exec-interpreter (literal (param \"INTERP_{i}\")))\n"
            ));
        }
        s
    }

    /// `-D NAVN=verdi` for hver parameter, i samme rekkefølge hver gang.
    pub fn params(&self) -> Vec<(String, PathBuf)> {
        let mut v = vec![
            ("HOME".to_string(), self.home.clone()),
            ("PKG".to_string(), self.package.clone()),
            ("OUT".to_string(), self.out.clone()),
            ("TMP".to_string(), self.tmp.clone()),
        ];
        for (i, r) in self.read.iter().enumerate() {
            v.push((format!("IN_{i}"), r.path.clone()));
        }
        for (i, p) in self.interpreters.iter().enumerate() {
            v.push((format!("INTERP_{i}"), p.clone()));
        }
        v
    }

    /// Argumentene til `sandbox-exec` foran `entry`: `-f <profil> -D NAVN=verdi …`.
    pub fn sandbox_args(&self, profile_file: &Path) -> Vec<OsString> {
        let mut a: Vec<OsString> = vec!["-f".into(), profile_file.into()];
        for (name, path) in self.params() {
            let mut kv = OsString::from(format!("{name}="));
            kv.push(path.as_os_str());
            a.push("-D".into());
            a.push(kv);
        }
        a
    }
}

/// Hvordan verktøy startes. I appen alltid gjennom `/usr/bin/sandbox-exec`.
#[derive(Debug, Clone)]
pub struct Sandbox {
    exec: PathBuf,
    scratch_root: PathBuf,
    #[cfg(test)]
    enabled: bool,
    #[cfg(test)]
    profile_override: Option<String>,
}

impl Sandbox {
    /// Sandkassen appen bruker. `tools_dir` er `<appdata>/verktoy`.
    pub fn new(tools_dir: &Path) -> Sandbox {
        Sandbox {
            exec: PathBuf::from(SANDBOX_EXEC),
            scratch_root: tools_dir.join(SCRATCH_DIR),
            #[cfg(test)]
            enabled: true,
            #[cfg(test)]
            profile_override: None,
        }
    }

    /// Bare tester: falske pakker som er sh-skript (sh står utenfor pakken og
    /// kan ikke startes i sandkassen). Ingen sandkasse og ingen egen TMPDIR.
    #[cfg(test)]
    pub fn disabled_for_tests() -> Sandbox {
        Sandbox {
            exec: PathBuf::from(SANDBOX_EXEC),
            scratch_root: std::env::temp_dir().join("jv-ingen-sandkasse"),
            enabled: false,
            profile_override: None,
        }
    }

    /// Bare tester: en annen `sandbox-exec` (for eksempel en sti som ikke finnes).
    #[cfg(test)]
    pub fn with_exec(mut self, exec: &Path) -> Sandbox {
        self.exec = exec.to_path_buf();
        self
    }

    /// Bare tester: en ødelagt profil.
    #[cfg(test)]
    pub fn with_profile(mut self, text: &str) -> Sandbox {
        self.profile_override = Some(text.to_string());
        self
    }

    pub fn enabled(&self) -> bool {
        #[cfg(test)]
        {
            self.enabled
        }
        #[cfg(not(test))]
        {
            true
        }
    }

    pub fn exec(&self) -> &Path {
        &self.exec
    }

    pub fn scratch_root(&self) -> &Path {
        &self.scratch_root
    }

    fn profile_text(&self, r: &Resolved) -> String {
        #[cfg(test)]
        if let Some(p) = &self.profile_override {
            return p.clone();
        }
        r.profile()
    }

    /// Lager mappen for en kjøring (og rydder etter krasjede kjøringer først),
    /// skriver profilen og gir argumentene til `sandbox-exec`.
    pub fn prepare(
        &self,
        package: &Path,
        tool_id: &str,
        access: &Access,
    ) -> JvResult<(Scratch, Vec<OsString>)> {
        if !self.exec.is_file() {
            return Err(JvError::SandboxFailed);
        }
        let scratch = Scratch::create(&self.scratch_root)?;
        let home = std::env::var_os("HOME").map(PathBuf::from);
        let r = Resolved::new(package, tool_id, access, &scratch.tmp(), home.as_deref())?;
        let profile = scratch.dir.join("profil.sb");
        fs::write(&profile, self.profile_text(&r)).map_err(|_| JvError::SandboxFailed)?;
        let args = r.sandbox_args(&profile);
        Ok((scratch, args))
    }
}

/// Mappen for én kjøring: `profil.sb` og `tmp/` (TMPDIR). Slettes i `Drop`.
#[derive(Debug)]
pub struct Scratch {
    dir: PathBuf,
}

static NEXT_SCRATCH: AtomicU64 = AtomicU64::new(1);

impl Scratch {
    fn create(root: &Path) -> JvResult<Scratch> {
        fs::create_dir_all(root).map_err(|_| JvError::SandboxFailed)?;
        clean_stale(root);
        let pid = std::process::id();
        loop {
            let n = NEXT_SCRATCH.fetch_add(1, Ordering::SeqCst);
            let dir = root.join(format!("{pid}-{n}"));
            match fs::create_dir(&dir) {
                Ok(()) => {
                    let s = Scratch { dir };
                    fs::create_dir(s.tmp()).map_err(|_| JvError::SandboxFailed)?;
                    return Ok(s);
                }
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(_) => return Err(JvError::SandboxFailed),
            }
        }
    }

    pub fn dir(&self) -> &Path {
        &self.dir
    }

    /// `TMPDIR` for kjøringen.
    pub fn tmp(&self) -> PathBuf {
        self.dir.join("tmp")
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        // En underprosess som ble drept, kan ha skrevet det siste i samme øyeblikk.
        for _ in 0..3 {
            if fs::remove_dir_all(&self.dir).is_ok() || !self.dir.exists() {
                return;
            }
            std::thread::sleep(std::time::Duration::from_millis(50));
        }
    }
}

/// Om en prosess med denne pid-en kjører (`kill -0`).
fn process_alive(pid: u32) -> bool {
    #[cfg(unix)]
    {
        std::process::Command::new("/bin/kill")
            .args(["-0", &pid.to_string()])
            .env_clear()
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(true)
    }
    #[cfg(not(unix))]
    {
        let _ = pid;
        true
    }
}

/// Sletter mapper fra kjøringer i en app som ikke kjører lenger (krasj).
/// Mapper fra denne appen slettes av [`Scratch`] selv.
pub fn clean_stale(root: &Path) {
    let me = std::process::id();
    let Ok(rd) = fs::read_dir(root) else { return };
    for e in rd.flatten() {
        let name = e.file_name().to_string_lossy().into_owned();
        let pid = name.split('-').next().and_then(|p| p.parse::<u32>().ok());
        let stale = match pid {
            Some(p) if p == me => false,
            Some(p) => !process_alive(p),
            // Ukjent navn: ikke vårt, men ligger i vår mappe. Slett.
            None => true,
        };
        if stale {
            let _ = fs::remove_dir_all(e.path());
        }
    }
}

#[cfg(all(test, target_os = "macos"))]
mod probe;

#[cfg(all(test, target_os = "macos"))]
mod tests {
    use super::*;

    /// Filnavn som ville ødelagt en profil der stiene sto i teksten.
    const NASTY: &[&str] = &[
        "med mellomrom.pdf",
        "æøå ÆØÅ.txt",
        "anførsel \"tegn\".pdf",
        "parentes (1).pdf",
        "slutt)).pdf",
        "semi;kolon.txt",
        "linje\nskift.txt",
        "-begynner-med-bindestrek.txt",
        "\")(allow default)(allow network*)(\";.txt",
        "lik=tegn.txt",
    ];

    fn tmp(name: &str) -> PathBuf {
        static N: AtomicU64 = AtomicU64::new(0);
        let d = std::env::temp_dir().join(format!(
            "jv-sandkasse-{name}-{}-{}",
            std::process::id(),
            N.fetch_add(1, Ordering::SeqCst)
        ));
        fs::create_dir_all(&d).unwrap();
        d
    }

    fn setup(names: &[&str]) -> (PathBuf, PathBuf, PathBuf, Vec<PathBuf>) {
        let base = tmp("profil");
        let pkg = base.join("pakke");
        let t = base.join("tmp");
        let inn = base.join("inn");
        for d in [&pkg, &t, &inn] {
            fs::create_dir_all(d).unwrap();
        }
        let files: Vec<PathBuf> = names
            .iter()
            .map(|n| {
                let p = inn.join(n);
                fs::write(&p, b"x").unwrap();
                p
            })
            .collect();
        (base, pkg, t, files)
    }

    #[test]
    fn nasty_file_names_only_appear_as_parameters() {
        let (base, pkg, t, files) = setup(NASTY);
        let out = base.join("ut (ny); \"mappe\"\n");
        let access = Access {
            read: files.clone(),
            write_dir: Some(out.clone()),
        };
        let r = Resolved::new(&pkg, "subtitles", &access, &t, None).unwrap();
        let profile = r.profile();
        // Malen er uendret, og det som er lagt til, er bare parameterlinjer.
        assert!(profile.starts_with(PROFILE_TEMPLATE));
        let added: Vec<&str> = profile[PROFILE_TEMPLATE.len()..].lines().collect();
        assert_eq!(added.len(), NASTY.len());
        for (i, line) in added.iter().enumerate() {
            assert_eq!(
                *line,
                format!("(allow file-read* (literal (param \"IN_{i}\")))")
            );
        }
        // Ingen sti eller del av et filnavn står i profilen.
        for name in NASTY {
            assert!(!profile.contains(name), "{name:?}");
        }
        // (HOME er «/Users» uten HOME, og den står i malen som fast systemsti.)
        for (name, path) in r.params().into_iter().filter(|(n, _)| n != "HOME") {
            assert!(!profile.contains(&*path.to_string_lossy()), "{name}");
        }
        assert!(!profile.contains(&*base.to_string_lossy()));
        // Stiene står uendret (kanoniske) i hver sin -D-parameter.
        let args = r.sandbox_args(Path::new("/x/profil.sb"));
        assert_eq!(args[0], "-f");
        assert_eq!(args[1], "/x/profil.sb");
        let mut d_values = Vec::new();
        for pair in args[2..].chunks(2) {
            assert_eq!(pair[0], "-D");
            d_values.push(pair[1].clone());
        }
        for (i, f) in files.iter().enumerate() {
            let mut want = OsString::from(format!("IN_{i}="));
            want.push(fs::canonicalize(f).unwrap());
            assert!(d_values.contains(&want), "IN_{i}");
        }
        let mut want_out = OsString::from("OUT=");
        want_out.push(
            fs::canonicalize(&base)
                .unwrap()
                .join("ut (ny); \"mappe\"\n"),
        );
        assert!(d_values.contains(&want_out));
        // Ingen -D-verdi begynner med «-» (alle er NAVN=…).
        assert!(d_values
            .iter()
            .all(|v| !v.to_string_lossy().starts_with('-')));
        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn one_and_many_inputs_and_folders() {
        let (base, pkg, t, files) = setup(&["a.pdf"]);
        let one = Access {
            read: files.clone(),
            write_dir: None,
        };
        let r = Resolved::new(&pkg, "ocr", &one, &t, None).unwrap();
        assert_eq!(r.read.len(), 1);
        // Uten utmappe er OUT den midlertidige mappen (ingen ekstra skrivetilgang).
        assert_eq!(r.out, r.tmp);
        assert!(r
            .profile()
            .ends_with("(allow file-read* (literal (param \"IN_0\")))\n"));

        let names: Vec<String> = (0..200).map(|i| format!("fil {i}.pdf")).collect();
        let refs: Vec<&str> = names.iter().map(String::as_str).collect();
        let (base2, pkg2, t2, mut many) = setup(&refs);
        let folder = base2.join("mappe");
        fs::create_dir_all(&folder).unwrap();
        many.push(folder);
        let r = Resolved::new(
            &pkg2,
            "ocr",
            &Access {
                read: many,
                write_dir: None,
            },
            &t2,
            None,
        )
        .unwrap();
        let profile = r.profile();
        let added: Vec<&str> = profile[PROFILE_TEMPLATE.len()..].lines().collect();
        assert_eq!(added.len(), 201);
        assert_eq!(
            added[200],
            "(allow file-read* (subpath (param \"IN_200\")))"
        );
        assert_eq!(r.params().len(), 4 + 201);
        let _ = fs::remove_dir_all(&base);
        let _ = fs::remove_dir_all(&base2);
    }

    #[test]
    fn paths_are_canonical() {
        let (base, pkg, t, files) = setup(&["fil.txt"]);
        // En symlenke til fila: profilen får den virkelige stien.
        let link = base.join("lenke.txt");
        #[cfg(unix)]
        std::os::unix::fs::symlink(&files[0], &link).unwrap();
        #[cfg(not(unix))]
        fs::copy(&files[0], &link).unwrap();
        let r = Resolved::new(
            &pkg,
            "subtitles",
            &Access {
                read: vec![link],
                write_dir: Some(base.join("ny-utmappe")),
            },
            &t,
            None,
        )
        .unwrap();
        #[cfg(unix)]
        assert_eq!(r.read[0].path, fs::canonicalize(&files[0]).unwrap());
        assert_eq!(r.out, fs::canonicalize(&base).unwrap().join("ny-utmappe"));
        assert_eq!(r.package, fs::canonicalize(&pkg).unwrap());
        #[cfg(target_os = "macos")]
        {
            // temp_dir() er /var/folders/…, den virkelige stien er /private/var/folders/….
            assert!(r.tmp.starts_with("/private/"));
            assert!(r.read[0].path.starts_with("/private/"));
        }
        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn missing_input_or_out_parent_is_an_error() {
        let (base, pkg, t, _) = setup(&[]);
        let r = Resolved::new(
            &pkg,
            "subtitles",
            &Access {
                read: vec![base.join("finnes-ikke.txt")],
                write_dir: None,
            },
            &t,
            None,
        );
        assert_eq!(
            r.unwrap_err(),
            JvError::InvalidArgs {
                reason: "input_missing"
            }
        );
        let r = Resolved::new(
            &pkg,
            "subtitles",
            &Access {
                read: vec![],
                write_dir: Some(base.join("finnes-ikke").join("ut")),
            },
            &t,
            None,
        );
        assert!(matches!(r, Err(JvError::InvalidArgs { .. })));
        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn only_metadata_gets_perl_as_interpreter() {
        let (base, pkg, t, _) = setup(&[]);
        let r = Resolved::new(&pkg, "metadata", &Access::default(), &t, None).unwrap();
        assert_eq!(r.interpreters, vec![PathBuf::from("/usr/bin/perl")]);
        assert!(r
            .profile()
            .ends_with("(allow process-exec-interpreter (literal (param \"INTERP_0\")))\n"));
        for id in super::super::catalog::KNOWN_TOOLS {
            if *id != "metadata" {
                assert!(interpreters(id).is_empty(), "{id}");
            }
        }
        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn template_has_the_main_rules_and_no_concrete_user_paths() {
        let p = PROFILE_TEMPLATE;
        for rule in [
            "(allow default)",
            "(deny network*)",
            "(deny mach-lookup)",
            "(deny file-write*)",
            "(subpath (param \"OUT\"))",
            "(subpath (param \"TMP\"))",
            "(literal \"/dev/null\")",
            "(literal \"/dev/dtracehelper\")",
            "(subpath (param \"HOME\"))",
            "(subpath \"/Volumes\")",
            "(subpath (param \"PKG\"))",
            "(deny process-exec*)",
            "(allow process-exec* (subpath (param \"PKG\")))",
        ] {
            assert!(p.contains(rule), "{rule}");
        }
        // Ingen åpning for nett eller for programmer utenfor pakken.
        let code: String = p
            .lines()
            .filter(|l| !l.trim_start().starts_with(";;"))
            .collect::<Vec<_>>()
            .join("\n");
        assert!(!code.contains("(allow network"));
        assert!(!code.contains("(allow mach-lookup"));
        assert!(!code.contains("/bin/sh"));
        assert_eq!(code.matches("(allow process-exec").count(), 1);
        assert_eq!(code.matches("(allow file-write*").count(), 1);
    }

    #[test]
    fn scratch_dir_is_removed_on_drop_and_stale_dirs_are_cleaned() {
        let root = tmp("kjoring");
        // En mappe fra en app som ikke kjører lenger (pid som ikke finnes).
        let stale = root.join("999999999-1");
        fs::create_dir_all(stale.join("tmp")).unwrap();
        fs::write(stale.join("tmp/rest"), b"x").unwrap();
        let s = Scratch::create(&root).unwrap();
        assert!(!stale.exists(), "mapper etter krasj skal ryddes");
        assert!(s.tmp().is_dir());
        let dir = s.dir().to_path_buf();
        fs::write(s.tmp().join("fil"), b"x").unwrap();
        drop(s);
        assert!(!dir.exists());
        // En mappe fra en app som kjører (denne), står.
        let mine = root.join(format!("{}-999", std::process::id()));
        fs::create_dir_all(&mine).unwrap();
        clean_stale(&root);
        assert!(mine.exists());
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn missing_sandbox_exec_fails_before_anything_is_created() {
        let root = tmp("uten-sandbox-exec");
        let sb = Sandbox::new(&root).with_exec(Path::new("/finnes/ikke/sandbox-exec"));
        assert_eq!(
            sb.prepare(&root, "subtitles", &Access::default())
                .unwrap_err(),
            JvError::SandboxFailed
        );
        assert!(!root.join(SCRATCH_DIR).exists());
        let _ = fs::remove_dir_all(&root);
    }
}
