// SPDX-License-Identifier: AGPL-3.0-or-later
//! Argumentene til et jv-verktøy, bygget fra en hviteliste per verktøy.
//!
//! Grensesnittet sender ikke en argumentliste, men en [`RunRequest`]: filer
//! (fra dialog eller slipp), utmappe, eventuelt underkommando og navngitte
//! valg. Her blir den til `jv <id> …`:
//!
//! - Bare valg som står i hvitelisten for verktøyet, med typesjekk og grenser.
//!   Ukjente valg, feil type og verdier utenfor grensene avvises.
//! - Tekstverdier er faste valg (`podcast`, `nn` …) eller sjekket mot et
//!   strengt mønster (`--pages`). Fri tekst går aldri videre.
//! - Alle stier må være absolutte. En absolutt sti begynner aldri med `-`, så
//!   et filnavn kan ikke bli tolket som et valg. NUL og linjeskift avvises.
//! - Kommandoen startes med en argumentliste, aldri gjennom et skall.

use std::collections::BTreeMap;
use std::ffi::OsString;
use std::path::Path;

use serde::Deserialize;
use serde_json::Value;

use super::error::{JvError, JvResult};

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RunRequest {
    /// Underkommando: `vis`/`vask` (metadata), `finn`/`sladd` (redact) og
    /// `analyser`/`lag` (datawrapper).
    #[serde(default)]
    pub command: Option<String>,
    /// Inngangsfiler (eller mapper der verktøyet tar mapper).
    pub inputs: Vec<String>,
    /// Utmappen. Kreves av alle unntatt `metadata vis` og `datawrapper`.
    #[serde(default)]
    pub out_dir: Option<String>,
    /// Navngitte valg, se hvitelisten under.
    #[serde(default)]
    pub options: BTreeMap<String, Value>,
}

fn invalid(reason: &'static str) -> JvError {
    JvError::InvalidArgs { reason }
}

/// Hva slags inngang et verktøy tar.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Inputs {
    /// Én eller flere filer.
    Files,
    /// Én eller flere filer eller mapper.
    FilesOrDirs,
    /// Nøyaktig så mange filer.
    Exactly(usize),
}

fn check_path(raw: &str) -> JvResult<OsString> {
    if raw.is_empty() || raw.len() > 4096 {
        return Err(invalid("path"));
    }
    if raw.contains('\0') || raw.contains('\n') || raw.contains('\r') {
        return Err(invalid("path"));
    }
    let p = Path::new(raw);
    if !p.is_absolute() || raw.starts_with('-') {
        return Err(invalid("path_not_absolute"));
    }
    Ok(OsString::from(raw))
}

fn check_inputs(req: &RunRequest, kind: Inputs) -> JvResult<Vec<OsString>> {
    match kind {
        Inputs::Exactly(n) if req.inputs.len() != n => return Err(invalid("input_count")),
        _ if req.inputs.is_empty() => return Err(invalid("input_count")),
        _ if req.inputs.len() > 500 => return Err(invalid("input_count")),
        _ => {}
    }
    let mut out = Vec::new();
    for raw in &req.inputs {
        let p = check_path(raw)?;
        let md = std::fs::metadata(&p).map_err(|_| invalid("input_missing"))?;
        let ok = md.is_file() || (kind == Inputs::FilesOrDirs && md.is_dir());
        if !ok {
            return Err(invalid("input_type"));
        }
        out.push(p);
    }
    Ok(out)
}

fn check_out_dir(req: &RunRequest) -> JvResult<OsString> {
    let raw = req.out_dir.as_deref().ok_or(invalid("out_missing"))?;
    let p = check_path(raw)?;
    match std::fs::metadata(&p) {
        Ok(md) if md.is_dir() => Ok(p),
        Ok(_) => Err(invalid("out_not_dir")),
        // Verktøyene lager utmappen selv; foreldermappen må finnes.
        Err(_) => match Path::new(&p).parent() {
            Some(parent) if parent.is_dir() => Ok(p),
            _ => Err(invalid("out_parent_missing")),
        },
    }
}

/// Valgene som er lov for et verktøy, og hvordan de blir til argumenter.
struct Options<'a> {
    map: &'a BTreeMap<String, Value>,
    used: Vec<&'static str>,
}

impl<'a> Options<'a> {
    fn new(map: &'a BTreeMap<String, Value>) -> Self {
        Options {
            map,
            used: Vec::new(),
        }
    }

    fn get(&mut self, key: &'static str) -> Option<&'a Value> {
        self.used.push(key);
        self.map.get(key).filter(|v| !v.is_null())
    }

    fn flag(&mut self, key: &'static str) -> JvResult<Option<bool>> {
        match self.get(key) {
            None => Ok(None),
            Some(Value::Bool(b)) => Ok(Some(*b)),
            Some(_) => Err(invalid("option_type")),
        }
    }

    fn number(&mut self, key: &'static str, min: f64, max: f64) -> JvResult<Option<f64>> {
        match self.get(key) {
            None => Ok(None),
            Some(Value::Number(n)) => {
                let v = n.as_f64().ok_or(invalid("option_type"))?;
                if !v.is_finite() || v < min || v > max {
                    return Err(invalid("option_range"));
                }
                Ok(Some(v))
            }
            Some(_) => Err(invalid("option_type")),
        }
    }

    fn integer(&mut self, key: &'static str, min: i64, max: i64) -> JvResult<Option<i64>> {
        match self.get(key) {
            None => Ok(None),
            Some(Value::Number(n)) => {
                let v = n.as_i64().ok_or(invalid("option_type"))?;
                if v < min || v > max {
                    return Err(invalid("option_range"));
                }
                Ok(Some(v))
            }
            Some(_) => Err(invalid("option_type")),
        }
    }

    fn choice(
        &mut self,
        key: &'static str,
        allowed: &[&'static str],
    ) -> JvResult<Option<&'static str>> {
        match self.get(key) {
            None => Ok(None),
            Some(Value::String(s)) => allowed
                .iter()
                .find(|a| **a == s.as_str())
                .copied()
                .map(Some)
                .ok_or(invalid("option_value")),
            Some(_) => Err(invalid("option_type")),
        }
    }

    fn path(&mut self, key: &'static str) -> JvResult<Option<OsString>> {
        match self.get(key) {
            None => Ok(None),
            Some(Value::String(s)) => {
                let p = check_path(s)?;
                if !Path::new(&p).is_file() {
                    return Err(invalid("input_missing"));
                }
                Ok(Some(p))
            }
            Some(_) => Err(invalid("option_type")),
        }
    }

    /// En ny utfil (`csv_file`): absolutt sti med endelsen `ext`, i en mappe som finnes.
    /// Verktøyet skriver aldri over en fil som finnes (det velger `-2`, `-3` …).
    fn out_file(&mut self, key: &'static str, ext: &str) -> JvResult<Option<OsString>> {
        match self.get(key) {
            None => Ok(None),
            Some(Value::String(s)) => {
                let p = check_path(s)?;
                let path = Path::new(&p);
                let ok_ext = path
                    .extension()
                    .and_then(|e| e.to_str())
                    .is_some_and(|e| e.eq_ignore_ascii_case(ext));
                if !ok_ext || path.is_dir() {
                    return Err(invalid("option_value"));
                }
                match path.parent() {
                    Some(parent) if parent.is_dir() => Ok(Some(p)),
                    _ => Err(invalid("out_parent_missing")),
                }
            }
            Some(_) => Err(invalid("option_type")),
        }
    }

    /// Arknavn i Excel: 1–31 tegn, ingen kontrolltegn og ingen av `: \ / ? * [ ]`.
    fn sheet_name(&mut self, key: &'static str) -> JvResult<Option<String>> {
        match self.get(key) {
            None => Ok(None),
            Some(Value::String(s)) if is_sheet_name(s) => Ok(Some(s.clone())),
            Some(Value::String(_)) => Err(invalid("option_value")),
            Some(_) => Err(invalid("option_type")),
        }
    }

    /// En liste med heltall i [min, max], uten like verdier, høyst `max_len` lang.
    fn integers(
        &mut self,
        key: &'static str,
        min: i64,
        max: i64,
        max_len: usize,
    ) -> JvResult<Vec<i64>> {
        match self.get(key) {
            None => Ok(Vec::new()),
            Some(Value::Array(items)) => {
                if items.len() > max_len {
                    return Err(invalid("option_range"));
                }
                let mut out: Vec<i64> = Vec::with_capacity(items.len());
                for item in items {
                    let v = item.as_i64().ok_or(invalid("option_type"))?;
                    if v < min || v > max {
                        return Err(invalid("option_range"));
                    }
                    if out.contains(&v) {
                        return Err(invalid("option_value"));
                    }
                    out.push(v);
                }
                Ok(out)
            }
            Some(_) => Err(invalid("option_type")),
        }
    }

    fn pages(&mut self, key: &'static str) -> JvResult<Option<String>> {
        match self.get(key) {
            None => Ok(None),
            Some(Value::String(s)) if is_page_list(s) => Ok(Some(s.clone())),
            Some(Value::String(_)) => Err(invalid("option_value")),
            Some(_) => Err(invalid("option_type")),
        }
    }

    /// Avviser valg som ikke står i hvitelisten.
    fn finish(self) -> JvResult<()> {
        if self.map.keys().any(|k| !self.used.contains(&k.as_str())) {
            return Err(invalid("unknown_option"));
        }
        Ok(())
    }
}

/// `3-7` eller `1,4-5`: bare sifre, komma og bindestrek.
fn is_page_list(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 100
        && s.split(',').all(|part| {
            let mut it = part.splitn(2, '-');
            let a = it.next().unwrap_or("");
            let b = it.next();
            let num =
                |x: &str| !x.is_empty() && x.len() <= 5 && x.bytes().all(|c| c.is_ascii_digit());
            num(a) && b.is_none_or(num)
        })
}

/// Arknavn slik Excel tillater dem. Navnet går videre som ett argument
/// (`--ark=<navn>`), så en innledende bindestrek kan ikke bli et valg.
fn is_sheet_name(s: &str) -> bool {
    let n = s.chars().count();
    (1..=31).contains(&n)
        && !s
            .chars()
            .any(|c| c.is_control() || matches!(c, ':' | '\\' | '/' | '?' | '*' | '[' | ']'))
}

/// Tall uten eksponent og uten unødvendige desimaler («0.3», «2», «-19.5»).
fn fmt_num(v: f64) -> String {
    let s = format!("{v:.3}");
    let s = s.trim_end_matches('0').trim_end_matches('.');
    if s == "-0" {
        "0".into()
    } else {
        s.to_string()
    }
}

fn push_out(argv: &mut Vec<OsString>, out: OsString) {
    argv.push("--out".into());
    argv.push(out);
}

/// Bygger argumentlisten `[<id>, …]` for verktøyet. Den kjørbare filen er pakkens `entry`.
pub fn build_args(tool_id: &str, req: &RunRequest) -> JvResult<Vec<OsString>> {
    let mut argv: Vec<OsString> = vec![tool_id.into()];
    let mut o = Options::new(&req.options);
    let no_command = |req: &RunRequest| {
        if req.command.is_some() {
            Err(invalid("command"))
        } else {
            Ok(())
        }
    };
    match tool_id {
        "compare" => {
            no_command(req)?;
            let files = check_inputs(req, Inputs::Exactly(2))?;
            argv.extend(files);
            if o.flag("ignore_whitespace")? == Some(false) {
                argv.push("--no-ignore-whitespace".into());
            }
            if o.flag("ignore_case")? == Some(true) {
                argv.push("--ignore-case".into());
            }
            push_out(&mut argv, check_out_dir(req)?);
        }
        "metadata" => {
            let cmd = match req.command.as_deref() {
                Some("vis") => "vis",
                Some("vask") => "vask",
                _ => return Err(invalid("command")),
            };
            argv.push(cmd.into());
            argv.extend(check_inputs(req, Inputs::FilesOrDirs)?);
            if cmd == "vask" {
                push_out(&mut argv, check_out_dir(req)?);
            } else if req.out_dir.is_some() {
                return Err(invalid("out_not_allowed"));
            }
        }
        "keyframes" => {
            no_command(req)?;
            argv.extend(check_inputs(req, Inputs::Files)?);
            let every = o.number("every_seconds", 0.1, 86_400.0)?;
            let scenes = o.number("scene_threshold", 0.01, 0.99)?;
            match (every, scenes) {
                (Some(e), None) => {
                    argv.push("--every".into());
                    argv.push(format!("{}s", fmt_num(e)).into());
                }
                (None, Some(t)) => {
                    argv.push("--scenes".into());
                    argv.push(fmt_num(t).into());
                }
                _ => return Err(invalid("keyframes_mode")),
            }
            push_out(&mut argv, check_out_dir(req)?);
        }
        "loudness" => {
            no_command(req)?;
            argv.extend(check_inputs(req, Inputs::Files)?);
            let target = o.choice("target", &["podcast", "broadcast"])?;
            let lufs = o.number("lufs", -70.0, -5.0)?;
            match (target, lufs) {
                (Some(t), None) => {
                    argv.push("--target".into());
                    argv.push(t.into());
                }
                (None, Some(l)) => argv.push(format!("--lufs={}", fmt_num(l)).into()),
                (None, None) => {}
                _ => return Err(invalid("loudness_target")),
            }
            push_out(&mut argv, check_out_dir(req)?);
        }
        "subtitles" => {
            no_command(req)?;
            argv.extend(check_inputs(req, Inputs::Files)?);
            if let Some(v) = o.integer("max_chars", 10, 100)? {
                argv.extend(["--max-chars".into(), v.to_string().into()]);
            }
            if let Some(v) = o.integer("max_lines", 1, 4)? {
                argv.extend(["--max-lines".into(), v.to_string().into()]);
            }
            for (key, flag, min, max) in [
                ("min_duration", "--min-duration", 0.1, 10.0),
                ("max_duration", "--max-duration", 0.5, 30.0),
                ("gap", "--gap", 0.0, 2.0),
            ] {
                if let Some(v) = o.number(key, min, max)? {
                    argv.extend([flag.into(), fmt_num(v).into()]);
                }
            }
            push_out(&mut argv, check_out_dir(req)?);
        }
        "pdf-tables" => {
            no_command(req)?;
            argv.extend(check_inputs(req, Inputs::Files)?);
            if let Some(p) = o.pages("pages")? {
                argv.extend(["--pages".into(), p.into()]);
            }
            if o.flag("merge")? == Some(true) {
                argv.push("--merge".into());
            }
            if o.flag("csv")? == Some(true) {
                argv.push("--csv".into());
            }
            push_out(&mut argv, check_out_dir(req)?);
        }
        "datawrapper" => {
            let cmd = match req.command.as_deref() {
                Some("analyser") => "analyser",
                Some("lag") => "lag",
                _ => return Err(invalid("command")),
            };
            argv.push(cmd.into());
            argv.extend(check_inputs(req, Inputs::Exactly(1))?);
            // Ingen utmappe: resultatet står i rapporten, og CSV-filen er valgfri.
            if req.out_dir.is_some() {
                return Err(invalid("out_not_allowed"));
            }
            if cmd == "lag" {
                if let Some(name) = o.sheet_name("sheet")? {
                    argv.push(format!("--ark={name}").into());
                }
                if let Some(n) = o.integer("table", 1, 10_000)? {
                    argv.push(format!("--tabell={n}").into());
                }
                if o.flag("with_sums")? == Some(true) {
                    argv.push("--med-sum".into());
                }
                if o.flag("transpose")? == Some(true) {
                    argv.push("--bytt".into());
                }
                for i in o.integers("remove_columns", 1, 16_384, 1_000)? {
                    argv.push(format!("--fjern-kolonne={i}").into());
                }
                if let Some(p) = o.out_file("csv_file", "csv")? {
                    argv.extend(["--csv".into(), p]);
                }
            }
            argv.push("--json".into());
        }
        "ocr" => {
            no_command(req)?;
            argv.extend(check_inputs(req, Inputs::FilesOrDirs)?);
            if o.flag("text")? == Some(true) {
                argv.push("--text".into());
            }
            push_out(&mut argv, check_out_dir(req)?);
        }
        "redact" => {
            let cmd = match req.command.as_deref() {
                Some("finn") => "finn",
                Some("sladd") => "sladd",
                _ => return Err(invalid("command")),
            };
            argv.push(cmd.into());
            argv.extend(check_inputs(req, Inputs::Exactly(1))?);
            if cmd == "finn" {
                if let Some(t) = o.path("terms_file")? {
                    argv.extend(["--terms".into(), t]);
                }
            } else {
                let plan = o.path("plan_file")?.ok_or(invalid("plan_missing"))?;
                argv.extend(["--plan".into(), plan]);
            }
            push_out(&mut argv, check_out_dir(req)?);
        }
        "nynorsk" => {
            no_command(req)?;
            argv.extend(check_inputs(req, Inputs::Files)?);
            let to = o
                .choice("to", &["nn", "nb"])?
                .ok_or(invalid("to_missing"))?;
            argv.extend(["--to".into(), to.into()]);
            push_out(&mut argv, check_out_dir(req)?);
        }
        _ => return Err(JvError::UnknownTool),
    }
    o.finish()?;
    Ok(argv)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::path::PathBuf;

    fn tmp() -> PathBuf {
        static N: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
        let d = std::env::temp_dir().join(format!(
            "jv-args-{}-{}",
            std::process::id(),
            N.fetch_add(1, std::sync::atomic::Ordering::SeqCst)
        ));
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    fn file(dir: &Path, name: &str) -> String {
        let p = dir.join(name);
        std::fs::write(&p, b"x").unwrap();
        p.to_string_lossy().into_owned()
    }

    fn req(inputs: Vec<String>, out: &Path, options: Value) -> RunRequest {
        RunRequest {
            command: None,
            inputs,
            out_dir: Some(out.to_string_lossy().into_owned()),
            options: serde_json::from_value(options).unwrap(),
        }
    }

    fn strs(v: &[OsString]) -> Vec<String> {
        v.iter().map(|s| s.to_string_lossy().into_owned()).collect()
    }

    #[test]
    fn subtitles_with_options() {
        let d = tmp();
        let f = file(&d, "intervju æøå; rm -rf.json");
        let r = req(
            vec![f.clone()],
            &d,
            json!({"max_chars": 37, "gap": 0.1, "min_duration": 1.0}),
        );
        let a = strs(&build_args("subtitles", &r).unwrap());
        assert_eq!(
            a,
            vec![
                "subtitles".to_string(),
                f,
                "--max-chars".into(),
                "37".into(),
                "--min-duration".into(),
                "1".into(),
                "--gap".into(),
                "0.1".into(),
                "--out".into(),
                d.to_string_lossy().into_owned()
            ]
        );
    }

    #[test]
    fn file_names_with_dash_spaces_and_double_dash_stay_one_argument() {
        let d = tmp();
        for name in ["-rf", "--", "--out", "a b ; c", "--help"] {
            let f = file(&d, name);
            let r = req(vec![f.clone()], &d, json!({}));
            let a = build_args("ocr", &r).unwrap();
            assert_eq!(a[1], OsString::from(&f));
            assert!(f.starts_with('/') || cfg!(windows));
        }
    }

    #[test]
    fn relative_and_dash_paths_are_rejected() {
        let d = tmp();
        for bad in ["-rf", "--", "relativ.pdf", "../x.pdf", ""] {
            let r = req(vec![bad.to_string()], &d, json!({}));
            assert!(
                matches!(build_args("ocr", &r), Err(JvError::InvalidArgs { .. })),
                "{bad}"
            );
        }
        let f = file(&d, "a.pdf");
        let mut r = req(vec![f], &d, json!({}));
        r.out_dir = Some("relativ".into());
        assert_eq!(
            build_args("ocr", &r).unwrap_err(),
            JvError::InvalidArgs {
                reason: "path_not_absolute"
            }
        );
    }

    #[test]
    fn unknown_option_wrong_type_and_range_are_rejected() {
        let d = tmp();
        let f = file(&d, "t.json");
        let cases = [
            (json!({"shell": "rm -rf /"}), "unknown_option"),
            (json!({"max_chars": "42"}), "option_type"),
            (json!({"max_chars": 1000}), "option_range"),
            (json!({"max_chars": 4.5}), "option_type"),
        ];
        for (opts, reason) in cases {
            let r = req(vec![f.clone()], &d, opts);
            assert_eq!(
                build_args("subtitles", &r).unwrap_err(),
                JvError::InvalidArgs { reason }
            );
        }
    }

    #[test]
    fn missing_input_and_folder_rules() {
        let d = tmp();
        let r = req(
            vec![d.join("finnes-ikke.pdf").to_string_lossy().into_owned()],
            &d,
            json!({}),
        );
        assert_eq!(build_args("ocr", &r).unwrap_err(), invalid("input_missing"));
        // ocr tar mapper, pdf-tables gjør ikke.
        let r = req(vec![d.to_string_lossy().into_owned()], &d, json!({}));
        assert!(build_args("ocr", &r).is_ok());
        assert_eq!(
            build_args("pdf-tables", &r).unwrap_err(),
            invalid("input_type")
        );
    }

    #[test]
    fn keyframes_needs_exactly_one_mode() {
        let d = tmp();
        let f = file(&d, "v.mp4");
        let ok = req(vec![f.clone()], &d, json!({"every_seconds": 2}));
        assert!(strs(&build_args("keyframes", &ok).unwrap()).contains(&"2s".to_string()));
        let ok = req(vec![f.clone()], &d, json!({"scene_threshold": 0.3}));
        assert!(strs(&build_args("keyframes", &ok).unwrap()).contains(&"0.3".to_string()));
        for opts in [
            json!({}),
            json!({"every_seconds": 2, "scene_threshold": 0.3}),
        ] {
            let r = req(vec![f.clone()], &d, opts);
            assert_eq!(
                build_args("keyframes", &r).unwrap_err(),
                invalid("keyframes_mode")
            );
        }
    }

    #[test]
    fn loudness_target_or_lufs() {
        let d = tmp();
        let f = file(&d, "a.wav");
        let r = req(vec![f.clone()], &d, json!({"lufs": -19}));
        assert!(strs(&build_args("loudness", &r).unwrap()).contains(&"--lufs=-19".to_string()));
        let r = req(vec![f.clone()], &d, json!({"target": "broadcast"}));
        assert!(strs(&build_args("loudness", &r).unwrap()).contains(&"broadcast".to_string()));
        let r = req(vec![f.clone()], &d, json!({"target": "--evil"}));
        assert_eq!(
            build_args("loudness", &r).unwrap_err(),
            invalid("option_value")
        );
    }

    #[test]
    fn redact_commands() {
        let d = tmp();
        let pdf = file(&d, "sak.pdf");
        let plan = file(&d, "sak.plan.json");
        let mut r = req(vec![pdf.clone()], &d, json!({}));
        assert_eq!(build_args("redact", &r).unwrap_err(), invalid("command"));
        r.command = Some("finn".into());
        assert_eq!(
            strs(&build_args("redact", &r).unwrap())[..3],
            ["redact", "finn", pdf.as_str()]
        );
        r.command = Some("sladd".into());
        assert_eq!(
            build_args("redact", &r).unwrap_err(),
            invalid("plan_missing")
        );
        r.options = serde_json::from_value(json!({"plan_file": plan})).unwrap();
        let a = strs(&build_args("redact", &r).unwrap());
        assert!(a.contains(&"--plan".to_string()) && a.contains(&plan));
        // finn tar ikke plan_file.
        r.command = Some("finn".into());
        assert_eq!(
            build_args("redact", &r).unwrap_err(),
            invalid("unknown_option")
        );
    }

    #[test]
    fn metadata_vis_has_no_out_and_vask_needs_it() {
        let d = tmp();
        let f = file(&d, "bilde.jpg");
        let mut r = req(vec![f], &d, json!({}));
        r.command = Some("vis".into());
        assert_eq!(
            build_args("metadata", &r).unwrap_err(),
            invalid("out_not_allowed")
        );
        r.out_dir = None;
        assert_eq!(strs(&build_args("metadata", &r).unwrap()).len(), 3);
        r.command = Some("vask".into());
        assert_eq!(
            build_args("metadata", &r).unwrap_err(),
            invalid("out_missing")
        );
    }

    #[test]
    fn datawrapper_analyser_and_lag() {
        let d = tmp();
        let x = file(&d, "tabell æøå; rm -rf.xlsx");
        let mut r = req(vec![x.clone()], &d, json!({}));
        r.out_dir = None;
        assert_eq!(
            build_args("datawrapper", &r).unwrap_err(),
            invalid("command")
        );
        r.command = Some("analyser".into());
        assert_eq!(
            strs(&build_args("datawrapper", &r).unwrap()),
            ["datawrapper", "analyser", x.as_str(), "--json"]
        );
        // analyser tar ingen valg, og ingen av kommandoene tar utmappe.
        r.options = serde_json::from_value(json!({"table": 2})).unwrap();
        assert_eq!(
            build_args("datawrapper", &r).unwrap_err(),
            invalid("unknown_option")
        );
        r.options.clear();
        r.out_dir = Some(d.to_string_lossy().into_owned());
        assert_eq!(
            build_args("datawrapper", &r).unwrap_err(),
            invalid("out_not_allowed")
        );
        r.out_dir = None;

        r.command = Some("lag".into());
        let csv = d.join("ut.csv").to_string_lossy().into_owned();
        r.options = serde_json::from_value(json!({
            "sheet": "-Ark 1 (2024)",
            "table": 2,
            "with_sums": true,
            "transpose": false,
            "remove_columns": [3, 1],
            "csv_file": csv,
        }))
        .unwrap();
        assert_eq!(
            strs(&build_args("datawrapper", &r).unwrap()),
            [
                "datawrapper",
                "lag",
                x.as_str(),
                "--ark=-Ark 1 (2024)",
                "--tabell=2",
                "--med-sum",
                "--fjern-kolonne=3",
                "--fjern-kolonne=1",
                "--csv",
                csv.as_str(),
                "--json"
            ]
        );
        // Bare én fil.
        let y = file(&d, "b.csv");
        let mut two = r.clone();
        two.inputs = vec![x.clone(), y];
        assert_eq!(
            build_args("datawrapper", &two).unwrap_err(),
            invalid("input_count")
        );
    }

    #[test]
    fn datawrapper_rejects_bad_values() {
        let d = tmp();
        let x = file(&d, "a.xlsx");
        std::fs::create_dir_all(d.join("mappe.csv")).unwrap();
        let cases = [
            (json!({"sheet": ""}), "option_value"),
            (json!({"sheet": "a/b"}), "option_value"),
            (json!({"sheet": "Ark[1]"}), "option_value"),
            (json!({"sheet": "linje\nskift"}), "option_value"),
            (json!({"sheet": "x".repeat(32)}), "option_value"),
            (json!({"sheet": 1}), "option_type"),
            (json!({"table": 0}), "option_range"),
            (json!({"table": "2"}), "option_type"),
            (json!({"remove_columns": 2}), "option_type"),
            (json!({"remove_columns": [0]}), "option_range"),
            (json!({"remove_columns": [2, 2]}), "option_value"),
            (json!({"remove_columns": ["2"]}), "option_type"),
            (json!({"remove_columns": vec![1; 1001]}), "option_range"),
            (json!({"csv_file": "relativ.csv"}), "path_not_absolute"),
            (json!({"csv_file": d.join("ut.txt")}), "option_value"),
            (json!({"csv_file": d.join("mappe.csv")}), "option_value"),
            (
                json!({"csv_file": d.join("finnes-ikke").join("ut.csv")}),
                "out_parent_missing",
            ),
            (json!({"with_sums": "ja"}), "option_type"),
            (json!({"shell": "rm -rf /"}), "unknown_option"),
        ];
        for (opts, reason) in cases {
            let mut r = req(vec![x.clone()], &d, opts.clone());
            r.out_dir = None;
            r.command = Some("lag".into());
            assert_eq!(
                build_args("datawrapper", &r).unwrap_err(),
                JvError::InvalidArgs { reason },
                "{opts}"
            );
        }
        assert!(is_sheet_name("Befolkning 2024"));
        assert!(is_sheet_name("Æøå – ‘tall’"));
    }

    #[test]
    fn page_list_pattern() {
        assert!(is_page_list("3-7"));
        assert!(is_page_list("1,4-5"));
        for bad in ["", "1;2", "1 -2", "-3", "3-", "a", "1,,2", "--out"] {
            assert!(!is_page_list(bad), "{bad}");
        }
    }

    #[test]
    fn compare_needs_two_files_and_nynorsk_needs_direction() {
        let d = tmp();
        let a = file(&d, "a.txt");
        let b = file(&d, "b.txt");
        let r = req(vec![a.clone()], &d, json!({}));
        assert_eq!(
            build_args("compare", &r).unwrap_err(),
            invalid("input_count")
        );
        let r = req(vec![a.clone(), b], &d, json!({"ignore_whitespace": false}));
        assert!(
            strs(&build_args("compare", &r).unwrap()).contains(&"--no-ignore-whitespace".into())
        );
        let r = req(vec![a.clone()], &d, json!({}));
        assert_eq!(
            build_args("nynorsk", &r).unwrap_err(),
            invalid("to_missing")
        );
        let r = req(vec![a], &d, json!({"to": "nn"}));
        assert!(build_args("nynorsk", &r).is_ok());
        assert_eq!(build_args("ukjent", &r).unwrap_err(), JvError::UnknownTool);
    }
}
