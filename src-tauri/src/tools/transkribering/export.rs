//! Eksport: txt (med eller uten tidskoder), srt, vtt og docx.
//!
//! - Standard filnavn: `<lydfil>.<målform>.<stil>.<ending>` i samme mappe som
//!   lydfilen, f.eks. `intervju.nynorsk.tolket.docx`.
//! - Topptekst i txt, vtt (som `NOTE`) og docx: filnavn, dato, målform, stil,
//!   modell og en linje om at teksten er maskintranskribert. Teksten i
//!   toppteksten kommer fra grensesnittets språkfil ([`HeaderLabels`]), så alle
//!   brukertekster ligger ett sted. srt har ingen kommentarsyntaks; en
//!   topptekst der ville blitt vist som undertekst, så srt får ingen.
//! - Teksten skrives slik den er (lydrett etterbehandles ikke). Vi fjerner bare
//!   det formatet ikke tåler: kontrolltegn, og `-->`/tomme linjer i srt/vtt.
//! - Skriver aldri over en fil uten `overwrite = true`, som grensesnittet bare
//!   sender etter at brukeren har bekreftet.

use std::io::Write;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use super::error::{CoreError, CoreResult};
use super::types::{Malform, Segment, Stil};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ExportFormat {
    Txt,
    Srt,
    Vtt,
    Docx,
}

impl ExportFormat {
    pub fn extension(self) -> &'static str {
        match self {
            ExportFormat::Txt => "txt",
            ExportFormat::Srt => "srt",
            ExportFormat::Vtt => "vtt",
            ExportFormat::Docx => "docx",
        }
    }
}

/// Tekstene i toppteksten, fra språkfilen i grensesnittet.
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
pub struct HeaderLabels {
    pub file: String,
    pub date: String,
    pub malform: String,
    pub stil: String,
    pub model: String,
    pub bokmal: String,
    pub nynorsk: String,
    pub lydrett: String,
    pub tolket: String,
    /// «Teksten er maskintranskribert og må kontrolleres mot lyden.»
    pub notice: String,
}

#[derive(Debug, Clone)]
pub struct ExportMeta {
    /// Bare filnavnet til lydfilen, ikke hele stien.
    pub audio_file_name: String,
    /// Datoen slik grensesnittet viser den (lokal tid).
    pub date: String,
    pub malform: Malform,
    pub stil: Stil,
    /// For eksempel `NbAiLab/nb-whisper-medium-verbatim (q5_0)`.
    pub model: String,
    pub labels: HeaderLabels,
}

pub fn header_lines(m: &ExportMeta) -> Vec<String> {
    let l = &m.labels;
    let malform = match m.malform {
        Malform::Bokmal => &l.bokmal,
        Malform::Nynorsk => &l.nynorsk,
    };
    let stil = match m.stil {
        Stil::Lydrett => &l.lydrett,
        Stil::Tolket => &l.tolket,
    };
    vec![
        format!("{}: {}", l.file, m.audio_file_name),
        format!("{}: {}", l.date, m.date),
        format!("{}: {}", l.malform, malform),
        format!("{}: {}", l.stil, stil),
        format!("{}: {}", l.model, m.model),
        l.notice.clone(),
    ]
    .into_iter()
    .map(|s| one_line(&clean(&s)))
    .collect()
}

/// `HH:MM:SS<sep>mmm`. Timer får minst to sifre og vokser ved behov.
pub fn timecode(ms: u64, sep: char) -> String {
    format!(
        "{:02}:{:02}:{:02}{}{:03}",
        ms / 3_600_000,
        (ms / 60_000) % 60,
        (ms / 1000) % 60,
        sep,
        ms % 1000
    )
}

/// `[HH:MM:SS]` for txt og docx.
pub fn short_timecode(ms: u64) -> String {
    format!(
        "[{:02}:{:02}:{:02}]",
        ms / 3_600_000,
        (ms / 60_000) % 60,
        (ms / 1000) % 60
    )
}

/// Fjerner kontrolltegn (utenom linjeskift og tab) som txt/xml ikke tåler.
fn clean(s: &str) -> String {
    s.chars()
        .filter(|c| !c.is_control() || *c == '\n' || *c == '\t')
        .collect()
}

fn one_line(s: &str) -> String {
    s.split(['\n', '\r'])
        .map(str::trim)
        .filter(|l| !l.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
}

/// Cue-tekst i srt/vtt: ingen tomme linjer (avslutter cuen) og ingen `-->`.
fn cue_text(s: &str) -> String {
    let t: Vec<&str> = s.lines().map(str::trim).filter(|l| !l.is_empty()).collect();
    clean(&t.join("\n")).replace("-->", "->")
}

fn ordered(segments: &[Segment]) -> impl Iterator<Item = (u64, u64, &str)> {
    segments
        .iter()
        .map(|s| (s.start_ms, s.end_ms.max(s.start_ms), s.text.as_str()))
}

pub fn to_txt(segments: &[Segment], meta: &ExportMeta, timestamps: bool) -> String {
    let mut out = String::new();
    for l in header_lines(meta) {
        out.push_str(&l);
        out.push('\n');
    }
    out.push('\n');
    for (start, _, text) in ordered(segments) {
        let t = one_line(&clean(text));
        if t.is_empty() {
            continue;
        }
        if timestamps {
            out.push_str(&short_timecode(start));
            out.push(' ');
        }
        out.push_str(&t);
        out.push('\n');
    }
    out
}

pub fn to_srt(segments: &[Segment]) -> String {
    let mut out = String::new();
    let mut n = 0;
    for (start, end, text) in ordered(segments) {
        let t = cue_text(text);
        if t.is_empty() {
            continue;
        }
        n += 1;
        out.push_str(&format!(
            "{n}\r\n{} --> {}\r\n",
            timecode(start, ','),
            timecode(end, ',')
        ));
        out.push_str(&t.replace('\n', "\r\n"));
        out.push_str("\r\n\r\n");
    }
    out
}

pub fn to_vtt(segments: &[Segment], meta: &ExportMeta) -> String {
    let mut out = String::from("WEBVTT\n\nNOTE\n");
    for l in header_lines(meta) {
        out.push_str(&l.replace("-->", "->"));
        out.push('\n');
    }
    out.push('\n');
    for (start, end, text) in ordered(segments) {
        let t = cue_text(text);
        if t.is_empty() {
            continue;
        }
        out.push_str(&format!(
            "{} --> {}\n{}\n\n",
            timecode(start, '.'),
            timecode(end, '.'),
            t
        ));
    }
    out
}

pub fn to_docx(segments: &[Segment], meta: &ExportMeta, timestamps: bool) -> CoreResult<Vec<u8>> {
    use docx_rs::{Docx, Paragraph, Run};
    let mut doc = Docx::new();
    let lines = header_lines(meta);
    let last = lines.len().saturating_sub(1);
    for (i, l) in lines.into_iter().enumerate() {
        let mut run = Run::new().add_text(l).size(18).color("555555");
        if i == last {
            run = run.italic();
        }
        doc = doc.add_paragraph(Paragraph::new().add_run(run));
    }
    doc = doc.add_paragraph(Paragraph::new());
    for (start, _, text) in ordered(segments) {
        let t = one_line(&clean(text));
        if t.is_empty() {
            continue;
        }
        let mut p = Paragraph::new();
        if timestamps {
            p = p.add_run(
                Run::new()
                    .add_text(format!("{} ", short_timecode(start)))
                    .color("777777"),
            );
        }
        p = p.add_run(Run::new().add_text(t));
        doc = doc.add_paragraph(p);
    }
    let mut buf = std::io::Cursor::new(Vec::new());
    doc.build()
        .pack(&mut buf)
        .map_err(|_| CoreError::Internal)?;
    Ok(buf.into_inner())
}

pub fn render(
    format: ExportFormat,
    segments: &[Segment],
    meta: &ExportMeta,
    timestamps: bool,
) -> CoreResult<Vec<u8>> {
    Ok(match format {
        ExportFormat::Txt => to_txt(segments, meta, timestamps).into_bytes(),
        ExportFormat::Srt => to_srt(segments).into_bytes(),
        ExportFormat::Vtt => to_vtt(segments, meta).into_bytes(),
        ExportFormat::Docx => to_docx(segments, meta, timestamps)?,
    })
}

/// `<mappe>/<lydfil uten ending>.<målform>.<stil>.<ending>`.
pub fn default_export_path(
    audio: &Path,
    malform: Malform,
    stil: Stil,
    format: ExportFormat,
) -> PathBuf {
    let stem = audio
        .file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .filter(|s| !s.trim().is_empty())
        .unwrap_or_else(|| "transkripsjon".to_string());
    let name = format!(
        "{stem}.{}.{}.{}",
        malform.file_word(),
        stil.key(),
        format.extension()
    );
    match audio.parent() {
        Some(p) => p.join(name),
        None => PathBuf::from(name),
    }
}

/// Skriver filen. Uten `overwrite` lages den bare hvis den ikke finnes
/// (atomisk, `create_new`), ellers [`CoreError::FileExists`]. Med `overwrite`
/// skrives en midlertidig fil i samme mappe som så flyttes over den gamle, så
/// en feil underveis aldri etterlater en halv fil der den gamle var.
pub fn write_file(path: &Path, bytes: &[u8], overwrite: bool) -> CoreResult<()> {
    if !overwrite {
        let mut f = match std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(path)
        {
            Ok(f) => f,
            Err(e) => return Err(CoreError::from_io(&e)),
        };
        if let Err(e) = f.write_all(bytes).and_then(|_| f.sync_all()) {
            drop(f);
            let _ = std::fs::remove_file(path);
            return Err(CoreError::from_io(&e));
        }
        return Ok(());
    }
    let dir = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let name = path
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_default();
    let tmp = dir.join(format!(".{name}.{}.tmp", std::process::id()));
    let res = (|| -> std::io::Result<()> {
        let mut f = std::fs::File::create(&tmp)?;
        f.write_all(bytes)?;
        f.sync_all()?;
        drop(f);
        std::fs::rename(&tmp, path)
    })();
    if let Err(e) = res {
        let _ = std::fs::remove_file(&tmp);
        return Err(CoreError::from_io(&e));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn labels() -> HeaderLabels {
        HeaderLabels {
            file: "Fil".into(),
            date: "Dato".into(),
            malform: "Målform".into(),
            stil: "Stil".into(),
            model: "Modell".into(),
            bokmal: "Bokmål".into(),
            nynorsk: "Nynorsk".into(),
            lydrett: "Lydrett".into(),
            tolket: "Tolket".into(),
            notice: "Teksten er maskintranskribert og må kontrolleres mot lyden.".into(),
        }
    }

    fn meta() -> ExportMeta {
        ExportMeta {
            audio_file_name: "intervju æøå.mp3".into(),
            date: "18. oktober 2026".into(),
            malform: Malform::Nynorsk,
            stil: Stil::Tolket,
            model: "NbAiLabBeta/nb-whisper-medium-semantic (q5_0)".into(),
            labels: labels(),
        }
    }

    fn segs() -> Vec<Segment> {
        vec![
            Segment {
                start_ms: 0,
                end_ms: 2_500,
                text: "Hei, og velkomen.".into(),
            },
            Segment {
                start_ms: 61_234,
                end_ms: 65_000,
                text: "kva meiner du om det".into(),
            },
            Segment {
                start_ms: 3_725_007,
                end_ms: 3_730_999,
                text: "Over ein time <&> inn.".into(),
            },
        ]
    }

    #[test]
    fn timecodes() {
        assert_eq!(timecode(0, ','), "00:00:00,000");
        assert_eq!(timecode(61_234, ','), "00:01:01,234");
        assert_eq!(timecode(3_725_007, '.'), "01:02:05.007");
        assert_eq!(timecode(10 * 3_600_000 + 59_999, ','), "10:00:59,999");
        assert_eq!(timecode(100 * 3_600_000, '.'), "100:00:00.000");
        assert_eq!(short_timecode(3_725_007), "[01:02:05]");
    }

    #[test]
    fn header_has_all_fields() {
        let h = header_lines(&meta());
        assert_eq!(
            h,
            vec![
                "Fil: intervju æøå.mp3",
                "Dato: 18. oktober 2026",
                "Målform: Nynorsk",
                "Stil: Tolket",
                "Modell: NbAiLabBeta/nb-whisper-medium-semantic (q5_0)",
                "Teksten er maskintranskribert og må kontrolleres mot lyden.",
            ]
        );
    }

    #[test]
    fn txt_with_and_without_timestamps() {
        let with = to_txt(&segs(), &meta(), true);
        assert!(with.starts_with("Fil: intervju æøå.mp3\nDato: 18. oktober 2026\n"));
        assert!(with.contains("må kontrolleres mot lyden.\n\n[00:00:00] Hei, og velkomen.\n"));
        assert!(with.contains("[00:01:01] kva meiner du om det\n"));
        assert!(with.ends_with("[01:02:05] Over ein time <&> inn.\n"));
        let without = to_txt(&segs(), &meta(), false);
        assert!(without
            .contains("\n\nHei, og velkomen.\nkva meiner du om det\nOver ein time <&> inn.\n"));
        assert!(!without.contains("[00:"));
    }

    #[test]
    fn srt_format() {
        let s = to_srt(&segs());
        assert_eq!(
            s,
            "1\r\n00:00:00,000 --> 00:00:02,500\r\nHei, og velkomen.\r\n\r\n\
             2\r\n00:01:01,234 --> 00:01:05,000\r\nkva meiner du om det\r\n\r\n\
             3\r\n01:02:05,007 --> 01:02:10,999\r\nOver ein time <&> inn.\r\n\r\n"
        );
        assert!(!s.contains("Fil:"), "srt har ingen topptekst");
    }

    #[test]
    fn vtt_format() {
        let v = to_vtt(&segs(), &meta());
        assert!(v.starts_with("WEBVTT\n\nNOTE\nFil: intervju æøå.mp3\n"));
        assert!(v.contains("00:00:00.000 --> 00:00:02.500\nHei, og velkomen.\n\n"));
        assert!(v.contains("01:02:05.007 --> 01:02:10.999\nOver ein time <&> inn.\n\n"));
    }

    #[test]
    fn cue_text_is_made_safe_but_words_are_kept() {
        let s = vec![
            Segment {
                start_ms: 0,
                end_ms: 1000,
                text: "a --> b\n\nc".into(),
            },
            Segment {
                start_ms: 1000,
                end_ms: 1000,
                text: "   ".into(),
            },
            Segment {
                start_ms: 2000,
                end_ms: 1500,
                text: "slutt før start".into(),
            },
        ];
        let srt = to_srt(&s);
        assert_eq!(
            srt,
            "1\r\n00:00:00,000 --> 00:00:01,000\r\na -> b\r\nc\r\n\r\n2\r\n00:00:02,000 --> 00:00:02,000\r\nslutt før start\r\n\r\n"
        );
        let vtt = to_vtt(&s, &meta());
        assert_eq!(vtt.matches(" --> ").count(), 2);
    }

    #[test]
    fn lydrett_text_is_exported_unchanged() {
        let s = vec![Segment {
            start_ms: 0,
            end_ms: 1000,
            text: "nordmenn er nordlendinger trøndere".into(),
        }];
        let mut m = meta();
        m.stil = Stil::Lydrett;
        assert!(to_txt(&s, &m, false).ends_with("\nnordmenn er nordlendinger trøndere\n"));
        assert!(to_srt(&s).contains("\r\nnordmenn er nordlendinger trøndere\r\n"));
    }

    #[test]
    fn docx_contains_header_and_text() {
        let bytes = to_docx(&segs(), &meta(), true).unwrap();
        assert!(bytes.starts_with(b"PK"));
        let doc = docx_rs::read_docx(&bytes).unwrap();
        let json = doc.json();
        for needle in [
            "Fil: intervju æøå.mp3",
            "Målform: Nynorsk",
            "Teksten er maskintranskribert",
            "[01:02:05] ",
            "Over ein time <&> inn.",
            "kva meiner du om det",
        ] {
            let esc = serde_json::to_string(needle).unwrap();
            assert!(json.contains(&esc[1..esc.len() - 1]), "mangler {needle}");
        }
        let without = docx_rs::read_docx(&to_docx(&segs(), &meta(), false).unwrap())
            .unwrap()
            .json();
        assert!(!without.contains("[00:01:01]"));
    }

    #[test]
    fn file_name_rule() {
        let p = default_export_path(
            Path::new("/x/Intervjuer/intervju.mp3"),
            Malform::Nynorsk,
            Stil::Tolket,
            ExportFormat::Docx,
        );
        assert_eq!(p, Path::new("/x/Intervjuer/intervju.nynorsk.tolket.docx"));
        let p = default_export_path(
            Path::new("møte i bystyret.m4a"),
            Malform::Bokmal,
            Stil::Lydrett,
            ExportFormat::Srt,
        );
        assert_eq!(p, Path::new("møte i bystyret.bokmål.lydrett.srt"));
        let p = default_export_path(
            Path::new("/a/opptak.2026.10.18.wav"),
            Malform::Bokmal,
            Stil::Tolket,
            ExportFormat::Txt,
        );
        assert_eq!(p, Path::new("/a/opptak.2026.10.18.bokmål.tolket.txt"));
        let p = default_export_path(
            Path::new("/a/.mp3"),
            Malform::Bokmal,
            Stil::Tolket,
            ExportFormat::Vtt,
        );
        assert_eq!(p.file_name().unwrap(), ".mp3.bokmål.tolket.vtt");
    }

    #[test]
    fn never_overwrites_without_confirmation() {
        let d = std::env::temp_dir().join(format!("lla-eksport-{} æøå", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        let p = d.join("intervju.bokmål.tolket.txt");
        write_file(&p, b"forste", false).unwrap();
        assert_eq!(write_file(&p, b"andre", false), Err(CoreError::FileExists));
        assert_eq!(std::fs::read(&p).unwrap(), b"forste");
        write_file(&p, b"andre", true).unwrap();
        assert_eq!(std::fs::read(&p).unwrap(), b"andre");
        // Ingen midlertidige filer igjen.
        assert_eq!(std::fs::read_dir(&d).unwrap().count(), 1);
        assert!(matches!(
            write_file(&d.join("finnes-ikke/x.txt"), b"x", false),
            Err(CoreError::FileNotFound)
        ));
    }
}
