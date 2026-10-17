//! Spike: transkriber én fil med én modell og ett språk, skriv segmenter og tider.
//! Skriver aldri filnavn. Teksten skrives til stdout fordi det er hele poenget med
//! spiken; i appen går teksten bare til grensesnittet, aldri til logg.
//!
//! Bruk:
//!   transcribe --model M --lang no|nn --audio A [--threads N] [--beam N]
//!              [--max-secs S] [--cancel-after-ms MS] [--no-gpu] [--no-text]
//!              [--verbose] [--flash-attn]

use std::ffi::c_void;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

use whisper_rs::{FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters};

struct Args {
    model: String,
    lang: String,
    audio: String,
    threads: i32,
    beam: i32,
    max_secs: Option<f64>,
    cancel_after_ms: Option<u64>,
    gpu: bool,
    text: bool,
    verbose: bool,
    flash_attn: bool,
    no_fallback: bool,
    max_len: i32,
    dtw: Option<String>,
}

fn parse() -> Args {
    let mut a = Args {
        model: String::new(),
        lang: "no".into(),
        audio: String::new(),
        threads: std::thread::available_parallelism().map(|n| n.get().min(8) as i32).unwrap_or(4),
        beam: 0,
        max_secs: None,
        cancel_after_ms: None,
        gpu: true,
        text: true,
        verbose: false,
        flash_attn: false,
        no_fallback: false,
        max_len: 0,
        dtw: None,
    };
    let v: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < v.len() {
        let next = |i: usize| v.get(i + 1).cloned().expect("missing value");
        match v[i].as_str() {
            "--model" => { a.model = next(i); i += 1 }
            "--lang" => { a.lang = next(i); i += 1 }
            "--audio" => { a.audio = next(i); i += 1 }
            "--threads" => { a.threads = next(i).parse().unwrap(); i += 1 }
            "--beam" => { a.beam = next(i).parse().unwrap(); i += 1 }
            "--max-secs" => { a.max_secs = Some(next(i).parse().unwrap()); i += 1 }
            "--cancel-after-ms" => { a.cancel_after_ms = Some(next(i).parse().unwrap()); i += 1 }
            "--no-gpu" => a.gpu = false,
            "--no-text" => a.text = false,
            "--verbose" => a.verbose = true,
            "--flash-attn" => a.flash_attn = true,
            "--no-fallback" => a.no_fallback = true,
            "--max-len" => { a.max_len = next(i).parse().unwrap(); i += 1 }
            "--dtw" => { a.dtw = Some(next(i)); i += 1 }
            o => panic!("unknown arg {o}"),
        }
        i += 1;
    }
    a
}

/// Avbryt-callback for whisper.cpp. Leser et AtomicBool via rå peker.
/// Vi bruker IKKE `set_abort_callback_safe` i whisper-rs 0.16: trampolinen der
/// tolker brukerpekeren som `F` mens den peker på en `Box<dyn FnMut>` (se docs/spike.md).
unsafe extern "C" fn abort_cb(user: *mut c_void) -> bool {
    let flag = &*(user as *const AtomicBool);
    flag.load(Ordering::Relaxed)
}

fn fmt_ts(cs: i64) -> String {
    // whisper gir tid i centisekunder
    let ms = cs * 10;
    format!("{:02}:{:02}:{:02}.{:03}", ms / 3_600_000, (ms / 60_000) % 60, (ms / 1000) % 60, ms % 1000)
}

fn main() {
    let a = parse();
    if !a.verbose {
        // Uten log-/tracing-feature betyr dette: whisper.cpp og ggml logger ingenting.
        whisper_rs::install_logging_hooks();
    }
    println!("whisper.cpp {}  system: {}", whisper_rs::WHISPER_CPP_VERSION, whisper_rs::print_system_info().trim());

    // 1. Dekod
    let t0 = Instant::now();
    let dec = spike::decode_to_16k_mono(std::path::Path::new(&a.audio), |_, _| {}).unwrap_or_else(|e| {
        eprintln!("decode failed: {e}");
        std::process::exit(2)
    });
    let mut pcm = dec.samples;
    if let Some(s) = a.max_secs {
        pcm.truncate((s * spike::TARGET_RATE as f64) as usize);
    }
    let audio_secs = pcm.len() as f64 / spike::TARGET_RATE as f64;
    let t_decode = t0.elapsed().as_secs_f64();

    // 2. Last modell
    let t1 = Instant::now();
    let mut cp = WhisperContextParameters::default();
    cp.use_gpu(a.gpu).flash_attn(a.flash_attn);
    if let Some(d) = &a.dtw {
        use whisper_rs::{DtwMode, DtwModelPreset, DtwParameters};
        let preset = match d.as_str() {
            "small" => DtwModelPreset::Small,
            "medium" => DtwModelPreset::Medium,
            "large" => DtwModelPreset::LargeV3,
            o => panic!("unknown dtw preset {o}"),
        };
        cp.dtw_parameters(DtwParameters { mode: DtwMode::ModelPreset { model_preset: preset }, ..Default::default() });
    }
    let ctx = WhisperContext::new_with_params(&a.model, cp).expect("failed to load model");
    let mut state = ctx.create_state().expect("failed to create state");
    let t_load = t1.elapsed().as_secs_f64();

    // 3. Parametre
    let strategy = if a.beam > 0 {
        SamplingStrategy::BeamSearch { beam_size: a.beam, patience: -1.0 }
    } else {
        SamplingStrategy::Greedy { best_of: 1 }
    };
    let mut p = FullParams::new(strategy);
    p.set_n_threads(a.threads);
    p.set_language(Some(&a.lang));
    p.set_translate(false);
    p.set_print_special(false);
    p.set_print_progress(false);
    p.set_print_realtime(false);
    p.set_print_timestamps(false);
    if a.no_fallback {
        p.set_temperature_inc(0.0);
    }
    if a.max_len > 0 {
        p.set_token_timestamps(true);
        p.set_max_len(a.max_len);
        p.set_split_on_word(true);
    }

    let cancel = Arc::new(AtomicBool::new(false));
    unsafe {
        p.set_abort_callback(Some(abort_cb));
        p.set_abort_callback_user_data(Arc::as_ptr(&cancel) as *mut c_void);
    }

    let first_seg: Arc<Mutex<Option<f64>>> = Arc::new(Mutex::new(None));
    let n_segs = Arc::new(Mutex::new(0usize));
    {
        let first_seg = first_seg.clone();
        let n_segs = n_segs.clone();
        let show = a.text;
        let start = Instant::now();
        p.set_segment_callback_safe_lossy(move |s: whisper_rs::SegmentCallbackData| {
            let mut f = first_seg.lock().unwrap();
            if f.is_none() {
                *f = Some(start.elapsed().as_secs_f64());
            }
            *n_segs.lock().unwrap() += 1;
            if show {
                println!("[{} --> {}] {}", fmt_ts(s.start_timestamp), fmt_ts(s.end_timestamp), s.text.trim());
            }
        });
    }
    let last_pct = Arc::new(Mutex::new(-1));
    {
        let last_pct = last_pct.clone();
        p.set_progress_callback_safe(move |pct: i32| {
            *last_pct.lock().unwrap() = pct;
        });
    }

    let cancel_set_at: Arc<Mutex<Option<Instant>>> = Arc::new(Mutex::new(None));
    if let Some(ms) = a.cancel_after_ms {
        let c = cancel.clone();
        let at = cancel_set_at.clone();
        std::thread::spawn(move || {
            std::thread::sleep(std::time::Duration::from_millis(ms));
            *at.lock().unwrap() = Some(Instant::now());
            c.store(true, Ordering::Relaxed);
        });
    }

    // 4. Kjør
    let t2 = Instant::now();
    let res = state.full(p, &pcm);
    let t_run = t2.elapsed().as_secs_f64();
    let returned = Instant::now();

    let n = state.full_n_segments();
    println!(
        "result={:?} lang={} model_load_s={:.2} decode_s={:.2} audio_s={:.1} run_s={:.2} speed_x_realtime={:.1} rtf={:.4} first_segment_after_s={:.2} segments={} last_progress={}",
        res.as_ref().map(|_| "ok").map_err(|e| format!("{e:?}")),
        a.lang, t_load, t_decode, audio_secs, t_run, audio_secs / t_run, t_run / audio_secs,
        first_seg.lock().unwrap().unwrap_or(-1.0), n, *last_pct.lock().unwrap()
    );
    if let Some(at) = *cancel_set_at.lock().unwrap() {
        println!("cancel_latency_ms={:.0}", returned.duration_since(at).as_secs_f64() * 1000.0);
    }
    let _ = n_segs;
}
