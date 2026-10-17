//! Spike: dekod en fil til 16 kHz mono og skriv nøkkeltall. Skriver aldri filnavnet.
use std::time::Instant;

fn main() {
    let path = std::env::args_os().nth(1).expect("usage: decode <file> [--dump out.f32]");
    let dump = std::env::args().skip(2).collect::<Vec<_>>();
    let t = Instant::now();
    match spike::decode_to_16k_mono(std::path::Path::new(&path), |_, _| {}) {
        Ok(d) => {
            let secs_in = d.frames_in as f64 / d.info.sample_rate as f64;
            let secs_out = d.samples.len() as f64 / spike::TARGET_RATE as f64;
            let peak = d.samples.iter().fold(0f32, |m, s| m.max(s.abs()));
            println!(
                "codec={} rate={} ch={} n_frames_hdr={:?} frames_in={} secs_in={:.3} samples_out={} secs_out={:.3} diff_ms={:.1} peak={:.3} out_mb={:.1} time_s={:.2}",
                d.info.codec, d.info.sample_rate, d.info.channels, d.info.n_frames, d.frames_in,
                secs_in, d.samples.len(), secs_out, (secs_out - secs_in) * 1000.0, peak,
                (d.samples.len() * 4) as f64 / 1e6, t.elapsed().as_secs_f64()
            );
            if dump.len() == 2 && dump[0] == "--dump" {
                let bytes: Vec<u8> = d.samples.iter().flat_map(|s| s.to_le_bytes()).collect();
                std::fs::write(&dump[1], bytes).unwrap();
            }
        }
        Err(e) => {
            println!("error: {e}");
            std::process::exit(2);
        }
    }
}
