//! Spike: sjekk om `set_abort_callback_safe` i whisper-rs 0.16 virker.
//! Kjører med et flagg som er satt fra start; et korrekt avbrudd gir Err straks.
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::Arc;
use whisper_rs::{FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters};

fn main() {
    whisper_rs::install_logging_hooks();
    let model = std::env::args().nth(1).expect("usage: abort_safe_check <model>");
    let ctx = WhisperContext::new_with_params(&model, WhisperContextParameters::default()).unwrap();
    let mut state = ctx.create_state().unwrap();
    let pcm = vec![0.0f32; 16_000 * 120];
    let flag = Arc::new(AtomicBool::new(true));
    let calls = Arc::new(AtomicUsize::new(0));
    let mut p = FullParams::new(SamplingStrategy::Greedy { best_of: 1 });
    p.set_language(Some("no"));
    {
        let flag = flag.clone();
        let calls = calls.clone();
        p.set_abort_callback_safe(move || {
            calls.fetch_add(1, Ordering::Relaxed);
            flag.load(Ordering::Relaxed)
        });
    }
    let t = std::time::Instant::now();
    let r = state.full(p, &pcm);
    println!("result={:?} closure_calls={} elapsed_s={:.2}", r, calls.load(Ordering::Relaxed), t.elapsed().as_secs_f64());
}
