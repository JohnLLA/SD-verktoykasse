//! Transkribering med whisper.cpp (whisper-rs).
//!
//! [`run_job`] kjører i en bakgrunnstråd (commands.rs starter den): dekoder
//! lyden strømmende, gir whisper biter på omtrent 10 minutter (chunk.rs),
//! sender segmenter og framdrift fortløpende via `emit`, og stopper når
//! `cancel` settes. whisper.cpp sjekker flagget før og etter hvert
//! 30-sekundersvindu og i dekoderen, men ikke midt i koderen; på en treg PC
//! kan det ta ett vindu (Windows-CI, 2 vCPU: 13,9 s). Grensesnittet venter
//! ikke på det: `cancel`-kommandoen svarer med en gang (jobs.rs).
//!
//! Funn fra spiken som er tatt hensyn til her:
//! - `set_abort_callback_safe` i whisper-rs 0.16 har en minnefeil. Vi bruker
//!   egne `extern "C"`-callbacks for avbryt, segmenter og framdrift.
//! - En panikk i en callback kan ikke rulle tilbake gjennom C og avslutter hele
//!   prosessen. Alle callbacks fanger panikk med `catch_unwind`, og en fanget
//!   panikk avbryter jobben med [`CoreError::Internal`].
//! - Framdriften fra whisper kan gå over 100 og klemmes; tidskoder klemmes til
//!   biten (og dermed til lydlengden).
//! - whisper.cpp sin logging slås av (`install_logging_hooks`), så modellsti
//!   o.l. ikke havner på stderr. Teksten logges aldri.
//! - CPU uten AVX2/FMA/F16C/BMI2 (x86) stoppes med en tydelig feil før
//!   whisper lastes, i stedet for «illegal instruction».

use std::ffi::{c_int, c_void, CStr};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Once;
use std::time::Instant;

use whisper_rs::whisper_rs_sys;
use whisper_rs::{
    FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters, WhisperError,
};

use super::chunk::{eta_ms, find_cut, place_segment, samples_to_ms, ChunkPlan, Progress};
use super::decode::{AudioStream, TARGET_RATE};
use super::error::{CoreError, CoreResult};
use super::keepawake::KeepAwake;
use super::models::VariantOptions;
use super::system;
use super::types::{Decoding, Malform, Segment};

/// Biter kortere enn dette (0,3 s) sendes ikke til whisper; de gir bare hallusinasjoner.
const MIN_CHUNK_SAMPLES: usize = (TARGET_RATE as usize) * 3 / 10;
/// Så mange tegn fra slutten av forrige bit gis som `initial_prompt` til neste.
const PROMPT_TAIL_CHARS: usize = 200;

static LOGGING: Once = Once::new();

/// Gjør whisper.cpp og ggml stille. Trygt å kalle flere ganger.
pub fn silence_whisper_logging() {
    LOGGING.call_once(whisper_rs::install_logging_hooks);
}

#[derive(Debug, Clone)]
pub struct JobRequest {
    pub audio: PathBuf,
    pub model_path: PathBuf,
    pub malform: Malform,
    pub options: VariantOptions,
    pub decoding: Decoding,
    /// `None`: fysiske kjerner, høyst 8.
    pub threads: Option<usize>,
    pub use_gpu: bool,
    pub plan: ChunkPlan,
    /// Bare for tester: stopp etter så mange 16 kHz-samples.
    pub limit_samples: Option<u64>,
}

impl JobRequest {
    pub fn new(
        audio: PathBuf,
        model_path: PathBuf,
        malform: Malform,
        options: VariantOptions,
    ) -> Self {
        JobRequest {
            audio,
            model_path,
            malform,
            options,
            decoding: Decoding::default(),
            threads: None,
            use_gpu: cfg!(target_os = "macos"),
            plan: ChunkPlan::default(),
            limit_samples: None,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum EngineEvent {
    /// Framdrift 0–100 for hele filen og anslått gjenværende tid.
    Progress {
        percent: f64,
        eta_ms: Option<u64>,
    },
    Segment(Segment),
}

#[derive(Debug, Clone)]
pub struct JobResult {
    pub segments: Vec<Segment>,
    /// Lengden på lyden som ble transkribert.
    pub duration_ms: u64,
    pub chunks: usize,
}

/// Flagg som avbryt-callbacken leser. Kan kalles fra ggml sine tråder, så bare atomics.
struct AbortFlags<'a> {
    cancel: &'a AtomicBool,
    failed: AtomicBool,
}

/// Tilstand for segment- og framdrifts-callbackene (kalles på jobbtråden).
struct CallbackCtx<'a, 'e> {
    flags: &'a AbortFlags<'a>,
    emit: &'e mut dyn FnMut(EngineEvent),
    segments: &'e mut Vec<Segment>,
    progress: &'e mut Progress,
    started: Instant,
    chunk_start_ms: u64,
    chunk_end_ms: u64,
    chunk_start: u64,
    chunk_len: u64,
    total_est: Option<u64>,
}

unsafe extern "C" fn abort_cb(user: *mut c_void) -> bool {
    if user.is_null() {
        return true;
    }
    let r = catch_unwind(AssertUnwindSafe(|| {
        // SAFETY: `user` peker på `AbortFlags` som lever til `full()` har returnert.
        let f = unsafe { &*(user as *const AbortFlags) };
        f.cancel.load(Ordering::Relaxed) || f.failed.load(Ordering::Relaxed)
    }));
    r.unwrap_or(true)
}

unsafe extern "C" fn segment_cb(
    _ctx: *mut whisper_rs_sys::whisper_context,
    state: *mut whisper_rs_sys::whisper_state,
    n_new: c_int,
    user: *mut c_void,
) {
    if user.is_null() || state.is_null() {
        return;
    }
    let user = user as *mut CallbackCtx;
    let r = catch_unwind(AssertUnwindSafe(|| {
        // SAFETY: `user` peker på `CallbackCtx` på jobbtrådens stakk, som lever
        // til `full()` har returnert. whisper kaller denne på samme tråd.
        let cb = unsafe { &mut *user };
        // SAFETY: `state` er gyldig under callbacken (whisper.cpp sin kontrakt).
        let n = unsafe { whisper_rs_sys::whisper_full_n_segments_from_state(state) };
        for i in (n - n_new).max(0)..n {
            // SAFETY: som over; i er innenfor 0..n.
            let (t0, t1, ptr) = unsafe {
                (
                    whisper_rs_sys::whisper_full_get_segment_t0_from_state(state, i),
                    whisper_rs_sys::whisper_full_get_segment_t1_from_state(state, i),
                    whisper_rs_sys::whisper_full_get_segment_text_from_state(state, i),
                )
            };
            if ptr.is_null() {
                continue;
            }
            // SAFETY: whisper gir en nullterminert streng som lever ut callbacken.
            let text = unsafe { CStr::from_ptr(ptr) }.to_string_lossy();
            if let Some(seg) = place_segment(t0, t1, &text, cb.chunk_start_ms, cb.chunk_end_ms) {
                cb.segments.push(seg.clone());
                (cb.emit)(EngineEvent::Segment(seg));
            }
        }
    }));
    if r.is_err() {
        // SAFETY: flags er en delt referanse til atomics.
        unsafe { (*user).flags.failed.store(true, Ordering::Relaxed) };
    }
}

unsafe extern "C" fn progress_cb(
    _ctx: *mut whisper_rs_sys::whisper_context,
    _state: *mut whisper_rs_sys::whisper_state,
    pct: c_int,
    user: *mut c_void,
) {
    if user.is_null() {
        return;
    }
    let user = user as *mut CallbackCtx;
    let r = catch_unwind(AssertUnwindSafe(|| {
        // SAFETY: som i segment_cb.
        let cb = unsafe { &mut *user };
        let before = cb.progress.current();
        let p = cb
            .progress
            .update(cb.chunk_start, cb.chunk_len, pct, cb.total_est);
        if p > before {
            let eta = eta_ms(cb.started.elapsed().as_millis() as u64, p);
            (cb.emit)(EngineEvent::Progress {
                percent: p,
                eta_ms: eta,
            });
        }
    }));
    if r.is_err() {
        // SAFETY: som over.
        unsafe { (*user).flags.failed.store(true, Ordering::Relaxed) };
    }
}

fn whisper_error(e: WhisperError) -> CoreError {
    match e {
        WhisperError::GenericError(c) => CoreError::Whisper { whisper_code: c },
        _ => CoreError::Whisper { whisper_code: -1 },
    }
}

/// Slutten av forrige bit, som `initial_prompt` for neste. Uten NUL-tegn.
pub fn prompt_tail(segments: &[Segment]) -> String {
    let mut tail = String::new();
    for s in segments.iter().rev() {
        if tail.chars().count() >= PROMPT_TAIL_CHARS {
            break;
        }
        tail = if tail.is_empty() {
            s.text.clone()
        } else {
            format!("{} {}", s.text, tail)
        };
    }
    let n = tail.chars().count();
    let t: String = tail
        .chars()
        .skip(n.saturating_sub(PROMPT_TAIL_CHARS))
        .filter(|c| *c != '\0')
        .collect();
    t.trim().to_string()
}

fn load_model(req: &JobRequest) -> CoreResult<WhisperContext> {
    let missing = system::missing_cpu_features();
    if !missing.is_empty() {
        return Err(CoreError::CpuUnsupported { missing });
    }
    let path = req.model_path.to_str().ok_or(CoreError::InvalidPath)?;
    if !req.model_path.is_file() {
        return Err(CoreError::ModelLoadFailed);
    }
    silence_whisper_logging();
    let mut cp = WhisperContextParameters::default();
    cp.use_gpu(req.use_gpu);
    WhisperContext::new_with_params(path, cp).map_err(|_| CoreError::ModelLoadFailed)
}

/// Kjører en hel jobb. Kalles på en egen tråd; `emit` kalles på samme tråd.
pub fn run_job(
    req: &JobRequest,
    cancel: &AtomicBool,
    emit: &mut dyn FnMut(EngineEvent),
) -> CoreResult<JobResult> {
    if cancel.load(Ordering::Relaxed) {
        return Err(CoreError::Cancelled);
    }
    // Lyden åpnes først, så format-feil kommer før modellen lastes.
    let mut stream = AudioStream::open(&req.audio)?;
    let ctx = load_model(req)?;
    let mut state = ctx.create_state().map_err(|_| CoreError::ModelLoadFailed)?;
    let _awake = KeepAwake::start();

    let threads = system::whisper_threads(req.threads) as c_int;
    let lang = req.malform.whisper_language();
    let plan = req.plan;
    let started = Instant::now();
    let mut progress = Progress::new();
    let mut segments: Vec<Segment> = Vec::new();
    let mut buf: Vec<f32> = Vec::with_capacity(plan.max_len);
    let mut offset: u64 = 0;
    let mut eof = false;
    let mut chunks = 0usize;
    emit(EngineEvent::Progress {
        percent: 0.0,
        eta_ms: None,
    });

    loop {
        // Fyll bufferet til én bit (eller filslutt).
        while !eof && buf.len() < plan.max_len {
            if cancel.load(Ordering::Relaxed) {
                return Err(CoreError::Cancelled);
            }
            let want = (plan.max_len - buf.len()).min(TARGET_RATE as usize * 30);
            let n = stream.read(&mut buf, want)?;
            if n == 0 {
                eof = true;
            }
            if let Some(limit) = req.limit_samples {
                let have = offset + buf.len() as u64;
                if have >= limit {
                    buf.truncate((limit - offset.min(limit)) as usize);
                    eof = true;
                }
            }
        }
        if buf.is_empty() {
            break;
        }
        let cut = find_cut(&buf, plan, eof).clamp(1, buf.len());
        let total_est = if req.limit_samples.is_some() && eof {
            Some(offset + buf.len() as u64)
        } else {
            stream
                .estimated_total_samples()
                .map(|t| match req.limit_samples {
                    Some(l) => t.min(l),
                    None => t,
                })
        };

        if cut >= MIN_CHUNK_SAMPLES {
            let chunk = &buf[..cut];
            let strategy = match req.decoding {
                Decoding::Beam5 => SamplingStrategy::BeamSearch {
                    beam_size: 5,
                    patience: -1.0,
                },
                Decoding::Greedy => SamplingStrategy::Greedy { best_of: 1 },
            };
            let mut p = FullParams::new(strategy);
            p.set_n_threads(threads);
            p.set_language(Some(lang));
            p.set_translate(false);
            p.set_print_special(false);
            p.set_print_progress(false);
            p.set_print_realtime(false);
            p.set_print_timestamps(false);
            if req.options.token_timestamps {
                p.set_token_timestamps(true);
            }
            if req.options.max_len > 0 {
                p.set_max_len(req.options.max_len as c_int);
            }
            if req.options.split_on_word {
                p.set_split_on_word(true);
            }
            let prompt = prompt_tail(&segments);
            if !prompt.is_empty() {
                p.set_initial_prompt(&prompt);
            }

            let flags = AbortFlags {
                cancel,
                failed: AtomicBool::new(false),
            };
            let mut chunk_segments: Vec<Segment> = Vec::new();
            let result = {
                let mut cb = CallbackCtx {
                    flags: &flags,
                    emit: &mut *emit,
                    segments: &mut chunk_segments,
                    progress: &mut progress,
                    started,
                    chunk_start_ms: samples_to_ms(offset),
                    chunk_end_ms: samples_to_ms(offset + cut as u64),
                    chunk_start: offset,
                    chunk_len: cut as u64,
                    total_est,
                };
                let cb_ptr = &mut cb as *mut CallbackCtx as *mut c_void;
                let flags_ptr = &flags as *const AbortFlags as *mut c_void;
                // SAFETY: pekerne gjelder `cb` og `flags`, som lever til `full()`
                // har returnert i denne blokken. Callbackene fanger panikk.
                unsafe {
                    p.set_abort_callback(Some(abort_cb));
                    p.set_abort_callback_user_data(flags_ptr);
                    p.set_new_segment_callback(Some(segment_cb));
                    p.set_new_segment_callback_user_data(cb_ptr);
                    p.set_progress_callback(Some(progress_cb));
                    p.set_progress_callback_user_data(cb_ptr);
                }
                state.full(p, chunk)
            };
            segments.append(&mut chunk_segments);
            if cancel.load(Ordering::Relaxed) {
                return Err(CoreError::Cancelled);
            }
            if flags.failed.load(Ordering::Relaxed) {
                return Err(CoreError::Internal);
            }
            result.map_err(whisper_error)?;
            chunks += 1;
        }

        offset += cut as u64;
        buf.drain(..cut);
        let total_for_progress = if eof && buf.is_empty() {
            Some(offset)
        } else {
            total_est
        };
        let before = progress.current();
        let pct = progress.update(offset, 0, 0, total_for_progress);
        if pct > before {
            emit(EngineEvent::Progress {
                percent: pct,
                eta_ms: eta_ms(started.elapsed().as_millis() as u64, pct),
            });
        }
        if eof && buf.is_empty() {
            break;
        }
    }
    emit(EngineEvent::Progress {
        percent: progress.finish(),
        eta_ms: Some(0),
    });
    Ok(JobResult {
        segments,
        duration_ms: samples_to_ms(offset),
        chunks,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    fn fixture(name: &str) -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("src/tools/transkribering/testdata")
            .join(name)
    }

    #[test]
    fn ggml_is_built_for_portable_cpu() {
        // GGML_NATIVE=OFF (.cargo/config.toml): ingen instruksjoner fra byggemaskinen
        // som brukerens maskin kan mangle. Skrives til testloggen for CI.
        let info = whisper_rs::print_system_info();
        println!("whisper.cpp: {}", info.trim());
        #[cfg(target_arch = "x86_64")]
        {
            for f in ["AVX2 = 1", "FMA = 1", "F16C = 1"] {
                assert!(info.contains(f), "mangler {f}");
            }
            assert!(!info.contains("AVX512 = 1"), "AVX-512 skal ikke være med");
        }
        #[cfg(target_arch = "aarch64")]
        {
            assert!(!info.contains("SME = 1"), "SME (M4/M5) skal ikke være med");
        }
    }

    #[test]
    fn prompt_tail_is_short_and_keeps_end() {
        let segs: Vec<Segment> = (0..50)
            .map(|i| Segment {
                start_ms: i,
                end_ms: i + 1,
                text: format!("setning nummer {i} med æøå"),
            })
            .collect();
        let t = prompt_tail(&segs);
        assert!(t.chars().count() <= PROMPT_TAIL_CHARS);
        assert!(t.ends_with("setning nummer 49 med æøå"));
        assert_eq!(prompt_tail(&[]), "");
    }

    #[test]
    fn cancel_before_start() {
        let req = JobRequest::new(
            fixture("tone.mp3"),
            PathBuf::from("finnes-ikke.bin"),
            Malform::Bokmal,
            VariantOptions::default(),
        );
        let r = run_job(&req, &AtomicBool::new(true), &mut |_| {});
        assert!(matches!(r, Err(CoreError::Cancelled)));
    }

    #[test]
    fn unsupported_audio_fails_before_model_is_loaded() {
        let req = JobRequest::new(
            fixture("tone.webm"),
            PathBuf::from("finnes-ikke.bin"),
            Malform::Bokmal,
            VariantOptions::default(),
        );
        let r = run_job(&req, &AtomicBool::new(false), &mut |_| {});
        assert_eq!(
            r.err(),
            Some(CoreError::UnsupportedFormat {
                format: "webm".into()
            })
        );
    }

    #[test]
    fn bad_model_file_gives_error_not_crash() {
        let d = std::env::temp_dir().join(format!("lla-motor-{} æøå", std::process::id()));
        std::fs::create_dir_all(&d).unwrap();
        let m = d.join("tull.bin");
        std::fs::write(&m, vec![7u8; 4096]).unwrap();
        let req = JobRequest::new(
            fixture("tone.mp3"),
            m,
            Malform::Nynorsk,
            VariantOptions::default(),
        );
        let r = run_job(&req, &AtomicBool::new(false), &mut |_| {});
        assert_eq!(r.err(), Some(CoreError::ModelLoadFailed));
        let req = JobRequest::new(
            fixture("tone.mp3"),
            d.join("mangler.bin"),
            Malform::Nynorsk,
            VariantOptions::default(),
        );
        assert_eq!(
            run_job(&req, &AtomicBool::new(false), &mut |_| {}).err(),
            Some(CoreError::ModelLoadFailed)
        );
    }

    // ---- Tester mot ekte modell og lyd. Kjøres i CI med `--ignored` når
    // LLA_TEST_MODEL_DIR (modeller som `<id>.bin`) og LLA_TEST_AUDIO_DIR
    // (king.mp3 og knuthamsun.mp3 fra NbAiLab) er satt. Skriver bare tall,
    // aldri transkribert tekst.

    fn real(model_id: &str, audio: &str) -> Option<(PathBuf, PathBuf)> {
        let md = std::env::var_os("LLA_TEST_MODEL_DIR")?;
        let ad = std::env::var_os("LLA_TEST_AUDIO_DIR")?;
        let m = Path::new(&md).join(format!("{model_id}.bin"));
        let a = Path::new(&ad).join(audio);
        (m.is_file() && a.is_file()).then_some((m, a))
    }

    fn real_or_skip(model_id: &str, audio: &str) -> (PathBuf, PathBuf) {
        match real(model_id, audio) {
            Some(x) => x,
            None => panic!(
                "sett LLA_TEST_MODEL_DIR og LLA_TEST_AUDIO_DIR (mangler {model_id} eller {audio})"
            ),
        }
    }

    fn use_gpu() -> bool {
        cfg!(target_os = "macos") && std::env::var_os("LLA_TEST_NO_GPU").is_none()
    }

    fn check_segments(segs: &[Segment], duration_ms: u64) {
        assert!(!segs.is_empty());
        let mut prev = 0;
        for s in segs {
            assert!(s.start_ms >= prev, "rekkefølge");
            assert!(s.end_ms >= s.start_ms);
            assert!(
                s.end_ms <= duration_ms,
                "slutt {} etter lyden {}",
                s.end_ms,
                duration_ms
            );
            assert!(!s.text.is_empty() && s.text == s.text.trim());
            prev = s.start_ms;
        }
    }

    #[test]
    #[ignore = "krever modell og lyd (LLA_TEST_MODEL_DIR, LLA_TEST_AUDIO_DIR)"]
    fn real_lydrett_bokmal_across_chunks() {
        let (m, a) = real_or_skip("nb-whisper-small-verbatim-q5_0", "king.mp3");
        let catalog = super::super::models::Catalog::builtin().unwrap();
        let entry = catalog.get("nb-whisper-small-verbatim-q5_0").unwrap();
        let mut req = JobRequest::new(a, m, Malform::Bokmal, catalog.options_for(entry));
        req.decoding = Decoding::Greedy;
        req.use_gpu = use_gpu();
        req.plan = ChunkPlan::new(25, 5);
        req.limit_samples = Some(60 * 16_000);
        let mut events = Vec::new();
        let t = Instant::now();
        let r = run_job(&req, &AtomicBool::new(false), &mut |e| events.push(e)).unwrap();
        println!(
            "lydrett no: {} biter, {} segmenter, {:.1} s",
            r.chunks,
            r.segments.len(),
            t.elapsed().as_secs_f64()
        );
        assert_eq!(r.duration_ms, 60_000);
        assert!(r.chunks >= 3);
        check_segments(&r.segments, r.duration_ms);
        // Segmenter fra alle tre bitene, med tider i filens tid.
        assert!(r.segments.iter().any(|s| s.start_ms < 20_000));
        assert!(r
            .segments
            .iter()
            .any(|s| s.start_ms >= 25_000 && s.start_ms < 50_000));
        assert!(r.segments.iter().any(|s| s.start_ms >= 45_000));
        // Verbatim med ordtidsstempler: ingen hele 30-sekundersvinduer.
        assert!(r.segments.iter().all(|s| s.end_ms - s.start_ms <= 25_000));
        let text: String = r
            .segments
            .iter()
            .map(|s| s.text.as_str())
            .collect::<Vec<_>>()
            .join(" ");
        assert!(
            text.contains("nordmenn"),
            "forventet bokmål fra kongens tale"
        );
        // Lydrett: ikke etterbehandlet til stor forbokstav.
        assert!(r.segments[0].text.starts_with(|c: char| !c.is_uppercase()));
        // Hendelsene: segmentene i samme rekkefølge, framdrift stigende til 100.
        let ev_segs: Vec<&Segment> = events
            .iter()
            .filter_map(|e| {
                if let EngineEvent::Segment(s) = e {
                    Some(s)
                } else {
                    None
                }
            })
            .collect();
        assert_eq!(ev_segs.len(), r.segments.len());
        let pcts: Vec<f64> = events
            .iter()
            .filter_map(|e| {
                if let EngineEvent::Progress { percent, .. } = e {
                    Some(*percent)
                } else {
                    None
                }
            })
            .collect();
        assert!(pcts.windows(2).all(|w| w[1] >= w[0]));
        assert!(pcts.iter().all(|p| (0.0..=100.0).contains(p)));
        assert_eq!(pcts.last().copied(), Some(100.0));
    }

    #[test]
    #[ignore = "krever modell og lyd (LLA_TEST_MODEL_DIR, LLA_TEST_AUDIO_DIR)"]
    fn real_tolket_nynorsk() {
        let (m, a) = real_or_skip("nb-whisper-small-semantic-q5_0", "king.mp3");
        let mut req = JobRequest::new(a, m, Malform::Nynorsk, VariantOptions::default());
        req.decoding = Decoding::Greedy;
        req.use_gpu = use_gpu();
        req.limit_samples = Some(40 * 16_000);
        let t = Instant::now();
        let r = run_job(&req, &AtomicBool::new(false), &mut |_| {}).unwrap();
        println!(
            "tolket nn: {} segmenter, {:.1} s",
            r.segments.len(),
            t.elapsed().as_secs_f64()
        );
        check_segments(&r.segments, r.duration_ms);
        let text: String = r
            .segments
            .iter()
            .map(|s| s.text.to_lowercase())
            .collect::<Vec<_>>()
            .join(" ");
        let nn = ["ikkje", "frå", "nordlendingar", "kvar", "regionar"];
        assert!(
            nn.iter().any(|w| text.contains(w)),
            "forventet nynorske former"
        );
    }

    #[test]
    #[ignore = "krever modell og lyd (LLA_TEST_MODEL_DIR, LLA_TEST_AUDIO_DIR)"]
    fn real_cancel_stops_within_seconds() {
        // Avbryter mens whisper regner (ved første framdrift fra whisper i den
        // første biten på 10 min), og måler tiden til run_job returnerer.
        // Bitene gjør at det ikke venter på mel-spektrogrammet for hele filen.
        let (m, a) = real_or_skip("nb-whisper-small-semantic-q5_0", "knuthamsun.mp3");
        let mut req = JobRequest::new(a, m, Malform::Bokmal, VariantOptions::default());
        req.use_gpu = use_gpu();
        let cancel = AtomicBool::new(false);
        let mut set_at: Option<Instant> = None;
        let t = Instant::now();
        let r = run_job(&req, &cancel, &mut |e| {
            if let EngineEvent::Progress { percent, .. } = e {
                if percent > 0.0 && set_at.is_none() {
                    set_at = Some(Instant::now());
                    cancel.store(true, Ordering::Relaxed);
                }
            }
        });
        let returned = Instant::now();
        assert!(matches!(r, Err(CoreError::Cancelled)), "{r:?}");
        let at = set_at.expect("whisper rapporterte framdrift");
        let latency = returned.duration_since(at).as_secs_f64();
        println!(
            "avbryt: satt etter {:.1} s, {latency:.2} s fra flagg til retur",
            at.duration_since(t).as_secs_f64()
        );
        // whisper.cpp sjekker flagget mellom 30-sekundersvinduene, ikke midt i
        // koderen. Grensesnittet får `done` med en gang (jobs.rs); her måles
        // hvor lenge maskinen fortsatt regner. Windows-CI (2 vCPU): 13,9 s.
        assert!(latency < 30.0, "avbryt tok {latency:.1} s");
    }
}
