//! Måleverktøy for steg 3 (kvalitet). Utviklerverktøy, ikke en del av appen.
//!
//! Kjører appens egen kjerne (`run_job` i `tools::transkribering::engine`) mot
//! én lydfil med én modell, og skriver segmentene og målingene til en JSON-fil.
//! Python-skriptene i `tools/maling/` styrer alle kombinasjonene.
//!
//! Bygges bare med `--features maling`, så vanlig `cargo test` og CI ikke
//! bygger det:
//!
//! ```text
//! cargo run --release --features maling --example maal -- run \
//!     --model-dir ~/lla-test/modeller --model-id nb-whisper-medium-verbatim-q5_0 \
//!     --audio klipp.wav --malform nynorsk --decoding beam5 --out resultat.json
//! cargo run --release --features maling --example maal -- decode --in x.mp3 --out x.wav
//! ```
//!
//! Utskriften på stdout er bare tall. Teksten går til `--out`-filen og skal
//! bare brukes med offentlig testlyd (regel 2 gjelder appens logger).

use std::path::PathBuf;
use std::sync::atomic::AtomicBool;
use std::time::Instant;

use lla_verktoykasse_lib::tools::transkribering::decode;
use lla_verktoykasse_lib::tools::transkribering::engine::{run_job, JobRequest};
use lla_verktoykasse_lib::tools::transkribering::models::Catalog;
use lla_verktoykasse_lib::tools::transkribering::system;
use lla_verktoykasse_lib::tools::transkribering::types::{Decoding, Malform};
use serde_json::json;

fn arg(args: &[String], name: &str) -> Option<String> {
    args.iter()
        .position(|a| a == name)
        .and_then(|i| args.get(i + 1).cloned())
}

fn flag(args: &[String], name: &str) -> bool {
    args.iter().any(|a| a == name)
}

/// Toppverdi for resident set size (arbeidsminne) i byte for denne prosessen.
#[cfg(unix)]
fn peak_rss_bytes() -> Option<u64> {
    // struct rusage: to timeval (2 x 16 byte på 64-bit macOS og Linux), så ru_maxrss.
    // macOS oppgir byte, Linux kilobyte.
    extern "C" {
        fn getrusage(who: i32, usage: *mut i64) -> i32;
    }
    let mut buf = [0i64; 36];
    // SAFETY: bufferet er større enn struct rusage (144 byte på 64-bit).
    let r = unsafe { getrusage(0, buf.as_mut_ptr()) };
    if r != 0 {
        return None;
    }
    let v = buf[4].max(0) as u64;
    Some(if cfg!(target_os = "macos") { v } else { v * 1024 })
}

#[cfg(windows)]
fn peak_rss_bytes() -> Option<u64> {
    #[repr(C)]
    struct ProcessMemoryCounters {
        cb: u32,
        page_fault_count: u32,
        peak_working_set_size: usize,
        working_set_size: usize,
        quota_peak_paged_pool_usage: usize,
        quota_paged_pool_usage: usize,
        quota_peak_non_paged_pool_usage: usize,
        quota_non_paged_pool_usage: usize,
        pagefile_usage: usize,
        peak_pagefile_usage: usize,
    }
    #[link(name = "kernel32")]
    extern "system" {
        fn GetCurrentProcess() -> isize;
        fn K32GetProcessMemoryInfo(h: isize, c: *mut ProcessMemoryCounters, cb: u32) -> i32;
    }
    // SAFETY: struct-layouten følger PROCESS_MEMORY_COUNTERS i Win32.
    unsafe {
        let mut c: ProcessMemoryCounters = std::mem::zeroed();
        c.cb = std::mem::size_of::<ProcessMemoryCounters>() as u32;
        if K32GetProcessMemoryInfo(GetCurrentProcess(), &mut c, c.cb) == 0 {
            return None;
        }
        Some(c.peak_working_set_size as u64)
    }
}

#[cfg(not(any(unix, windows)))]
fn peak_rss_bytes() -> Option<u64> {
    None
}

fn write_wav(path: &PathBuf, samples: &[f32]) -> std::io::Result<()> {
    use std::io::Write;
    let mut f = std::io::BufWriter::new(std::fs::File::create(path)?);
    let data_len = (samples.len() * 2) as u32;
    f.write_all(b"RIFF")?;
    f.write_all(&(36 + data_len).to_le_bytes())?;
    f.write_all(b"WAVEfmt ")?;
    f.write_all(&16u32.to_le_bytes())?;
    f.write_all(&1u16.to_le_bytes())?; // PCM
    f.write_all(&1u16.to_le_bytes())?; // mono
    f.write_all(&decode::TARGET_RATE.to_le_bytes())?;
    f.write_all(&(decode::TARGET_RATE * 2).to_le_bytes())?;
    f.write_all(&2u16.to_le_bytes())?;
    f.write_all(&16u16.to_le_bytes())?;
    f.write_all(b"data")?;
    f.write_all(&data_len.to_le_bytes())?;
    for s in samples {
        let v = (s.clamp(-1.0, 1.0) * 32767.0).round() as i16;
        f.write_all(&v.to_le_bytes())?;
    }
    f.flush()
}

fn cmd_decode(args: &[String]) -> Result<(), String> {
    // Flere `--in` limes sammen i rekkefølge, med `--gap-ms` stillhet mellom (standard 0).
    let inputs: Vec<PathBuf> = args
        .windows(2)
        .filter(|w| w[0] == "--in")
        .map(|w| PathBuf::from(&w[1]))
        .collect();
    if inputs.is_empty() {
        return Err("mangler --in".into());
    }
    let out = PathBuf::from(arg(args, "--out").ok_or("mangler --out")?);
    let gap_ms: usize = arg(args, "--gap-ms")
        .map(|g| g.parse().map_err(|_| "ugyldig --gap-ms"))
        .transpose()?
        .unwrap_or(0);
    let gap = vec![0.0f32; decode::TARGET_RATE as usize * gap_ms / 1000];
    let mut all: Vec<f32> = Vec::new();
    for (i, input) in inputs.iter().enumerate() {
        let (_info, samples) = decode::decode_all(input).map_err(|e| format!("{e:?}"))?;
        if i > 0 {
            all.extend_from_slice(&gap);
        }
        all.extend_from_slice(&samples);
    }
    write_wav(&out, &all).map_err(|e| e.to_string())?;
    println!("samples={}", all.len());
    Ok(())
}

fn cmd_run(args: &[String]) -> Result<(), String> {
    let model_dir = PathBuf::from(arg(args, "--model-dir").ok_or("mangler --model-dir")?);
    let model_id = arg(args, "--model-id").ok_or("mangler --model-id")?;
    let audio = PathBuf::from(arg(args, "--audio").ok_or("mangler --audio")?);
    let out = PathBuf::from(arg(args, "--out").ok_or("mangler --out")?);
    let malform = match arg(args, "--malform").as_deref() {
        Some("bokmål") | Some("bokmal") => Malform::Bokmal,
        Some("nynorsk") => Malform::Nynorsk,
        _ => return Err("--malform må være bokmal eller nynorsk".into()),
    };
    let decoding = match arg(args, "--decoding").as_deref() {
        Some("beam5") | None => Decoding::Beam5,
        Some("greedy") => Decoding::Greedy,
        _ => return Err("--decoding må være beam5 eller greedy".into()),
    };
    let catalog = Catalog::builtin().map_err(|e| format!("{e:?}"))?;
    let entry = catalog.get(&model_id).ok_or("ukjent modell-ID")?;
    // Appens egne innstillinger per variant (models.json), slik appen bruker dem.
    // `--options <variant>` låner innstillingene til en annen variant (til å måle om
    // tidsstempler per token også hjelper semantic og hovedmodellen).
    let options = match arg(args, "--options") {
        Some(v) => catalog
            .variant_options
            .get(&v)
            .cloned()
            .ok_or("ukjent variant i --options")?,
        None => catalog.options_for(entry),
    };
    let model_path = model_dir.join(entry.local_file_name());

    let mut req = JobRequest::new(audio, model_path, malform, options);
    req.decoding = decoding;
    if flag(args, "--no-gpu") {
        req.use_gpu = false;
    }
    if let Some(t) = arg(args, "--threads") {
        req.threads = Some(t.parse().map_err(|_| "ugyldig --threads")?);
    }
    if let Some(s) = arg(args, "--limit-secs") {
        let s: u64 = s.parse().map_err(|_| "ugyldig --limit-secs")?;
        req.limit_samples = Some(s * decode::TARGET_RATE as u64);
    }
    let started = Instant::now();
    let result = run_job(&req, &AtomicBool::new(false), &mut |_| {}).map_err(|e| format!("{e:?}"))?;
    let wall = started.elapsed().as_secs_f64();
    let dur = result.duration_ms as f64 / 1000.0;
    let peak = peak_rss_bytes();
    let doc = json!({
        "model_id": model_id,
        "malform": malform.file_word(),
        "decoding": if decoding == Decoding::Beam5 { "beam5" } else { "greedy" },
        "options": arg(args, "--options").unwrap_or_else(|| entry.variant.clone()),
        "gpu": req.use_gpu,
        "threads": system::whisper_threads(req.threads),
        "duration_s": dur,
        "wall_s": wall,
        "speed_x": if wall > 0.0 { dur / wall } else { 0.0 },
        "peak_rss_mb": peak.map(|b| b as f64 / 1_048_576.0),
        "chunks": result.chunks,
        "segments": result.segments.iter().map(|s| json!({
            "start_ms": s.start_ms, "end_ms": s.end_ms, "text": s.text
        })).collect::<Vec<_>>(),
    });
    std::fs::write(&out, serde_json::to_vec(&doc).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    println!(
        "ok segments={} duration_s={:.1} wall_s={:.2} speed_x={:.1} peak_rss_mb={}",
        result.segments.len(),
        dur,
        wall,
        if wall > 0.0 { dur / wall } else { 0.0 },
        peak.map(|b| format!("{:.0}", b as f64 / 1_048_576.0))
            .unwrap_or_else(|| "?".into())
    );
    Ok(())
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let r = match args.first().map(String::as_str) {
        Some("run") => cmd_run(&args),
        Some("decode") => cmd_decode(&args),
        _ => Err("bruk: maal run|decode ... (se toppen av filen)".into()),
    };
    if let Err(e) = r {
        eprintln!("feil: {e}");
        std::process::exit(1);
    }
}
