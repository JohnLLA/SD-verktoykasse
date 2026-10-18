//! Lyddekoding: symphonia leser filen, første lydspor velges, kanalene mikses
//! til mono og resamples til 16 kHz f32 med rubato.
//!
//! Strømmende: [`AudioStream::read`] gir neste bit med 16 kHz-samples. Motoren
//! (engine.rs) henter omtrent 10 minutter av gangen, så verken råfilen eller
//! hele 16 kHz-bufferet for en fil på 3 timer ligger i minnet.
//!
//! Formatene i spesifikasjonen: mp3, m4a/AAC, wav, flac, ogg/Vorbis, mp4 og
//! mov (lydsporet). Kjente format som ikke støttes (webm, Opus, caf, aiff,
//! ALAC m.fl.) gjenkjennes på de første bytene eller på kodeken og gir
//! [`CoreError::UnsupportedFormat`] med formatnavnet, aldri filnavnet.

use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use rubato::{FftFixedIn, Resampler};
use symphonia::core::audio::SampleBuffer;
use symphonia::core::codecs::{CodecType, Decoder, DecoderOptions, CODEC_TYPE_NULL};
use symphonia::core::errors::Error as SymError;
use symphonia::core::formats::{FormatOptions, FormatReader};
use symphonia::core::io::{MediaSource, MediaSourceStream};
use symphonia::core::meta::MetadataOptions;
use symphonia::core::probe::Hint;

use super::error::{CoreError, CoreResult};

pub const TARGET_RATE: u32 = 16_000;
const CHUNK_IN: usize = 4096;
/// Priming-forsinkelse i AAC fra Apple-kodere (og de fleste andre: 2112 rammer).
/// symphonia 0.5 trekker den ikke fra i mp4/m4a, så lyden ble 48 ms for sen
/// (docs/spike.md). Vi hopper over så mange rammer i starten når containeren
/// ikke selv oppgir forsinkelsen.
pub const AAC_PRIMING_FRAMES: u64 = 2112;

/// Det vi vet om kilden. Ingen filnavn.
#[derive(Debug, Clone)]
pub struct SourceInfo {
    pub codec: String,
    pub sample_rate: u32,
    pub channels: usize,
    /// Antall rammer i kilden, hvis containeren oppgir det.
    pub n_frames: Option<u64>,
}

impl SourceInfo {
    /// Anslått lengde i 16 kHz-samples, hvis containeren oppgir lengden.
    pub fn expected_samples(&self) -> Option<u64> {
        match (self.n_frames, self.sample_rate) {
            (Some(n), r) if r > 0 => {
                Some((n as f64 * TARGET_RATE as f64 / r as f64).round() as u64)
            }
            _ => None,
        }
    }
}

/// `File` som teller hvor langt symphonia har lest, for framdrift når
/// containeren ikke oppgir lengden.
struct CountingFile {
    file: File,
    pos: Arc<AtomicU64>,
    len: Option<u64>,
}

impl Read for CountingFile {
    fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
        let n = self.file.read(buf)?;
        self.pos.fetch_add(n as u64, Ordering::Relaxed);
        Ok(n)
    }
}

impl Seek for CountingFile {
    fn seek(&mut self, to: SeekFrom) -> std::io::Result<u64> {
        let p = self.file.seek(to)?;
        self.pos.store(p, Ordering::Relaxed);
        Ok(p)
    }
}

impl MediaSource for CountingFile {
    fn is_seekable(&self) -> bool {
        true
    }
    fn byte_len(&self) -> Option<u64> {
        self.len
    }
}

/// Kjenner igjen format vi vet at symphonia 0.5 ikke leser, på de første
/// bytene. Uten dette leter proben gjennom hele filen og ender med en
/// meningsløs «unexpected end of file» (docs/spike.md).
pub fn sniff_unsupported(head: &[u8]) -> Option<&'static str> {
    let has = |needle: &[u8]| head.windows(needle.len()).any(|w| w == needle);
    if head.starts_with(&[0x1A, 0x45, 0xDF, 0xA3]) {
        return Some(if has(b"webm") { "webm" } else { "mkv" });
    }
    if head.starts_with(b"FORM")
        && head.len() >= 12
        && (&head[8..12] == b"AIFF" || &head[8..12] == b"AIFC")
    {
        return Some("aiff");
    }
    if head.starts_with(b"caff") {
        return Some("caf");
    }
    if head.starts_with(b"OggS") && has(b"OpusHead") {
        return Some("opus");
    }
    if head.starts_with(&[0x30, 0x26, 0xB2, 0x75, 0x8E, 0x66, 0xCF, 0x11]) {
        return Some("wma");
    }
    if head.starts_with(b"#!AMR") {
        return Some("amr");
    }
    None
}

fn codec_name(c: CodecType) -> String {
    use symphonia::core::codecs::*;
    let n = match c {
        CODEC_TYPE_MP3 => "mp3",
        CODEC_TYPE_MP2 => "mp2",
        CODEC_TYPE_MP1 => "mp1",
        CODEC_TYPE_AAC => "aac",
        CODEC_TYPE_FLAC => "flac",
        CODEC_TYPE_VORBIS => "vorbis",
        CODEC_TYPE_OPUS => "opus",
        CODEC_TYPE_ALAC => "alac",
        CODEC_TYPE_EAC3 => "eac3",
        CODEC_TYPE_WMA => "wma",
        CODEC_TYPE_DCA => "dts",
        CODEC_TYPE_WAVPACK => "wavpack",
        CODEC_TYPE_ADPCM_IMA_WAV => "adpcm",
        CODEC_TYPE_ADPCM_MS => "adpcm",
        CODEC_TYPE_SPEEX => "speex",
        _ => {
            // pcm-varianter og alt annet
            let s = format!("{c}");
            return if s.is_empty() { "ukjent".into() } else { s };
        }
    };
    n.to_string()
}

fn ext_of(path: &Path) -> Option<String> {
    path.extension()
        .and_then(|e| e.to_str())
        .map(|e| e.to_ascii_lowercase())
}

/// Strømmende dekoder til 16 kHz mono f32.
pub struct AudioStream {
    format: Box<dyn FormatReader>,
    decoder: Box<dyn Decoder>,
    track_id: u32,
    info: SourceInfo,
    resampler: Option<FftFixedIn<f32>>,
    /// Mono-samples i kildens rate som venter på resampleren.
    pending: Vec<f32>,
    /// Ferdige 16 kHz-samples som ikke er hentet ennå.
    ready: Vec<f32>,
    sbuf: Option<SampleBuffer<f32>>,
    /// Rammer (per kanal) som er dekodet og brukt, etter at priming er hoppet over.
    frames_in: u64,
    /// Rammer som fortsatt skal hoppes over i starten (AAC-priming).
    skip_frames: u64,
    delay_left: usize,
    /// 16 kHz-samples levert ut av `read`.
    emitted: u64,
    rate: u32,
    finished: bool,
    bytes_pos: Arc<AtomicU64>,
    bytes_len: Option<u64>,
}

impl AudioStream {
    pub fn open(path: &Path) -> CoreResult<Self> {
        let mut file = File::open(path).map_err(|e| CoreError::from_io(&e))?;
        let len = file.metadata().ok().map(|m| m.len());
        if len == Some(0) {
            return Err(CoreError::EmptyAudio);
        }

        // Kjente, ikke støttede format først.
        let mut head = [0u8; 256];
        let n = read_up_to(&mut file, &mut head).map_err(|e| CoreError::from_io(&e))?;
        if let Some(f) = sniff_unsupported(&head[..n]) {
            return Err(CoreError::UnsupportedFormat { format: f.into() });
        }
        file.seek(SeekFrom::Start(0))
            .map_err(|e| CoreError::from_io(&e))?;

        let ext = ext_of(path);
        let pos = Arc::new(AtomicU64::new(0));
        let src = CountingFile {
            file,
            pos: pos.clone(),
            len,
        };
        let mss = MediaSourceStream::new(Box::new(src), Default::default());
        let mut hint = Hint::new();
        if let Some(e) = &ext {
            hint.with_extension(e);
        }
        let unsupported_container = || CoreError::UnsupportedFormat {
            format: ext.clone().unwrap_or_else(|| "ukjent".into()),
        };
        let probed = symphonia::default::get_probe()
            .format(
                &hint,
                mss,
                &FormatOptions {
                    enable_gapless: true,
                    ..Default::default()
                },
                &MetadataOptions::default(),
            )
            .map_err(|e| match e {
                SymError::Unsupported(_) => unsupported_container(),
                // Proben leser til slutten når den ikke kjenner formatet.
                SymError::IoError(io) if io.kind() == std::io::ErrorKind::UnexpectedEof => {
                    unsupported_container()
                }
                SymError::IoError(io) => CoreError::from_io(&io),
                _ => CoreError::DecodeFailed,
            })?;
        let format = probed.format;

        // Første spor med en kjent lydkodek (mp4/mov kan ha video først).
        let track = format
            .tracks()
            .iter()
            .find(|t| {
                t.codec_params.codec != CODEC_TYPE_NULL && t.codec_params.sample_rate.is_some()
            })
            .or_else(|| {
                format
                    .tracks()
                    .iter()
                    .find(|t| t.codec_params.codec != CODEC_TYPE_NULL)
            })
            .ok_or(CoreError::NoAudioTrack)?;
        let track_id = track.id;
        let params = track.codec_params.clone();
        let codec = codec_name(params.codec);

        let decoder = symphonia::default::get_codecs()
            .make(&params, &DecoderOptions::default())
            .map_err(|e| match e {
                SymError::Unsupported(_) => CoreError::UnsupportedFormat {
                    format: codec.clone(),
                },
                _ => CoreError::DecodeFailed,
            })?;

        let is_mp4 = matches!(ext.as_deref(), Some("m4a" | "mp4" | "mov" | "m4v" | "3gp"))
            || head[..n].get(4..8) == Some(b"ftyp")
            || head[..n].get(4..8) == Some(b"moov");
        let skip_frames = if params.codec == symphonia::core::codecs::CODEC_TYPE_AAC
            && params.delay.is_none()
            && is_mp4
        {
            AAC_PRIMING_FRAMES
        } else {
            0
        };
        let n_frames = params.n_frames.map(|n| n.saturating_sub(skip_frames));

        let info = SourceInfo {
            codec,
            sample_rate: params.sample_rate.unwrap_or(0),
            channels: params.channels.map(|c| c.count()).unwrap_or(0),
            n_frames,
        };
        Ok(AudioStream {
            format,
            decoder,
            track_id,
            rate: info.sample_rate,
            info,
            resampler: None,
            pending: Vec::with_capacity(CHUNK_IN * 2),
            ready: Vec::new(),
            sbuf: None,
            frames_in: 0,
            skip_frames,
            delay_left: 0,
            emitted: 0,
            finished: false,
            bytes_pos: pos,
            bytes_len: len,
        })
    }

    pub fn info(&self) -> &SourceInfo {
        &self.info
    }

    /// Antall 16 kHz-samples levert så langt.
    pub fn emitted(&self) -> u64 {
        self.emitted
    }

    /// Andel av filen som er lest (0..=1), fra antall rammer hvis lengden er
    /// kjent, ellers fra byteposisjonen.
    pub fn fraction_read(&self) -> Option<f64> {
        if let Some(n) = self.info.n_frames.filter(|n| *n > 0) {
            return Some((self.frames_in as f64 / n as f64).clamp(0.0, 1.0));
        }
        let len = self.bytes_len.filter(|l| *l > 0)?;
        Some((self.bytes_pos.load(Ordering::Relaxed) as f64 / len as f64).clamp(0.0, 1.0))
    }

    /// Anslått total lengde i 16 kHz-samples.
    pub fn estimated_total_samples(&self) -> Option<u64> {
        if self.finished {
            return Some(self.emitted + self.ready.len() as u64);
        }
        if let Some(n) = self.info.expected_samples() {
            return Some(n.max(self.emitted));
        }
        let f = self.fraction_read()?;
        if f < 0.001 {
            return None;
        }
        Some(((self.emitted + self.ready.len() as u64) as f64 / f) as u64)
    }

    /// Legger opptil `max` nye samples til `out`. Returnerer antall lagt til;
    /// 0 betyr at filen er ferdig.
    pub fn read(&mut self, out: &mut Vec<f32>, max: usize) -> CoreResult<usize> {
        let mut added = 0;
        while added < max {
            if !self.ready.is_empty() {
                let take = (max - added).min(self.ready.len());
                out.extend_from_slice(&self.ready[..take]);
                self.ready.drain(..take);
                added += take;
                self.emitted += take as u64;
                continue;
            }
            if self.finished {
                break;
            }
            self.decode_more()?;
        }
        Ok(added)
    }

    /// Dekoder neste pakke (eller tømmer resampleren ved slutten).
    fn decode_more(&mut self) -> CoreResult<()> {
        loop {
            let packet = match self.format.next_packet() {
                Ok(p) => p,
                Err(SymError::IoError(e)) if e.kind() == std::io::ErrorKind::UnexpectedEof => {
                    return self.finish();
                }
                Err(SymError::ResetRequired) => return self.finish(),
                Err(SymError::IoError(e)) => return Err(CoreError::from_io(&e)),
                Err(_) => return Err(CoreError::DecodeFailed),
            };
            if packet.track_id() != self.track_id {
                continue;
            }
            let decoded = match self.decoder.decode(&packet) {
                Ok(d) => d,
                // Ødelagte pakker hoppes over, som symphonia anbefaler.
                Err(SymError::DecodeError(_)) => continue,
                Err(SymError::IoError(e)) => return Err(CoreError::from_io(&e)),
                Err(SymError::Unsupported(_)) => {
                    return Err(CoreError::UnsupportedFormat {
                        format: self.info.codec.clone(),
                    })
                }
                Err(_) => return Err(CoreError::DecodeFailed),
            };
            let spec = *decoded.spec();
            let ch = spec.channels.count().max(1);
            let frames = decoded.frames();
            if frames == 0 {
                continue;
            }
            if self.rate == 0 {
                self.rate = spec.rate;
                self.info.sample_rate = spec.rate;
            }
            if spec.rate != self.rate {
                // Samplingsraten endret seg midt i strømmen. Sjeldent; ikke støttet.
                return Err(CoreError::DecodeFailed);
            }
            if self.info.channels == 0 {
                self.info.channels = ch;
            }
            let need_new = match &self.sbuf {
                Some(b) => b.capacity() < frames * ch,
                None => true,
            };
            if need_new {
                self.sbuf = Some(SampleBuffer::<f32>::new(frames as u64, spec));
            }
            let Some(sb) = self.sbuf.as_mut() else {
                return Err(CoreError::Internal);
            };
            sb.copy_interleaved_ref(decoded);
            let inter = sb.samples();
            let inv = 1.0 / ch as f32;
            let mut skipped = 0usize;
            for f in inter.chunks_exact(ch) {
                if self.skip_frames > 0 {
                    self.skip_frames -= 1;
                    skipped += 1;
                    continue;
                }
                self.pending.push(f.iter().sum::<f32>() * inv);
            }
            self.frames_in += (frames - skipped) as u64;

            if self.rate == TARGET_RATE {
                self.ready.append(&mut self.pending);
                if !self.ready.is_empty() {
                    return Ok(());
                }
                continue;
            }
            self.run_resampler()?;
            if !self.ready.is_empty() {
                return Ok(());
            }
        }
    }

    fn run_resampler(&mut self) -> CoreResult<()> {
        if self.resampler.is_none() {
            let r =
                FftFixedIn::<f32>::new(self.rate as usize, TARGET_RATE as usize, CHUNK_IN, 2, 1)
                    .map_err(|_| CoreError::DecodeFailed)?;
            self.delay_left = r.output_delay();
            self.resampler = Some(r);
        }
        let Some(r) = self.resampler.as_mut() else {
            return Err(CoreError::Internal);
        };
        let mut start = 0;
        while self.pending.len() - start >= r.input_frames_next() {
            let n = r.input_frames_next();
            let res = r
                .process(&[&self.pending[start..start + n]], None)
                .map_err(|_| CoreError::DecodeFailed)?;
            push_skip_delay(&mut self.ready, &res[0], &mut self.delay_left);
            start += n;
        }
        self.pending.drain(..start);
        Ok(())
    }

    fn finish(&mut self) -> CoreResult<()> {
        if self.finished {
            return Ok(());
        }
        self.finished = true;
        let expected = self.expected_total();
        if let Some(r) = self.resampler.as_mut() {
            if !self.pending.is_empty() {
                let res = r
                    .process_partial(Some(&[&self.pending[..]]), None)
                    .map_err(|_| CoreError::DecodeFailed)?;
                push_skip_delay(&mut self.ready, &res[0], &mut self.delay_left);
                self.pending.clear();
            }
            // Tøm forsinkelsen i filteret.
            let mut guard = 0;
            while self.emitted + (self.ready.len() as u64) < expected && guard < 8 {
                let res = r
                    .process_partial::<&[f32]>(None, None)
                    .map_err(|_| CoreError::DecodeFailed)?;
                push_skip_delay(&mut self.ready, &res[0], &mut self.delay_left);
                guard += 1;
            }
            // Kutt til nøyaktig lengde (kildens rammer omregnet til 16 kHz).
            let keep = expected.saturating_sub(self.emitted) as usize;
            self.ready.truncate(keep);
        } else if !self.pending.is_empty() {
            self.ready.append(&mut self.pending);
        }
        if self.emitted == 0 && self.ready.is_empty() {
            return Err(CoreError::EmptyAudio);
        }
        Ok(())
    }

    fn expected_total(&self) -> u64 {
        if self.rate == 0 {
            return 0;
        }
        (self.frames_in as f64 * TARGET_RATE as f64 / self.rate as f64).round() as u64
    }
}

fn read_up_to(f: &mut File, buf: &mut [u8]) -> std::io::Result<usize> {
    let mut n = 0;
    while n < buf.len() {
        let k = f.read(&mut buf[n..])?;
        if k == 0 {
            break;
        }
        n += k;
    }
    Ok(n)
}

fn push_skip_delay(out: &mut Vec<f32>, data: &[f32], delay_left: &mut usize) {
    if *delay_left >= data.len() {
        *delay_left -= data.len();
        return;
    }
    out.extend_from_slice(&data[*delay_left..]);
    *delay_left = 0;
}

/// Dekoder hele filen. Brukes i tester og verktøy; appen bruker [`AudioStream`].
pub fn decode_all(path: &Path) -> CoreResult<(SourceInfo, Vec<f32>)> {
    let mut s = AudioStream::open(path)?;
    let mut out = Vec::new();
    while s.read(&mut out, 1 << 20)? > 0 {}
    Ok((s.info().clone(), out))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::path::PathBuf;

    fn fixture(name: &str) -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("src/tools/transkribering/testdata")
            .join(name)
    }

    fn tmpdir(tag: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("lla-dekod-{tag}-{}", std::process::id()));
        let _ = std::fs::create_dir_all(&d);
        d
    }

    /// Skriver en PCM-wav. `kind`: 1 = heltall, 3 = flyttall.
    fn write_wav(path: &Path, rate: u32, ch: u16, bits: u16, kind: u16, frames: &[f32]) {
        let bps = (bits / 8) as u32;
        let data_len = frames.len() as u32 * ch as u32 * bps;
        let mut b = Vec::new();
        b.extend_from_slice(b"RIFF");
        b.extend_from_slice(&(36 + data_len).to_le_bytes());
        b.extend_from_slice(b"WAVEfmt ");
        b.extend_from_slice(&16u32.to_le_bytes());
        b.extend_from_slice(&kind.to_le_bytes());
        b.extend_from_slice(&ch.to_le_bytes());
        b.extend_from_slice(&rate.to_le_bytes());
        b.extend_from_slice(&(rate * ch as u32 * bps).to_le_bytes());
        b.extend_from_slice(&(ch * bits / 8).to_le_bytes());
        b.extend_from_slice(&bits.to_le_bytes());
        b.extend_from_slice(b"data");
        b.extend_from_slice(&data_len.to_le_bytes());
        for &s in frames {
            for c in 0..ch {
                // Kanal 1 er motsatt fase av kanal 0 med halv styrke, så miksen kan sjekkes.
                let v = if c == 0 { s } else { -s * 0.5 };
                match (kind, bits) {
                    (1, 16) => b.extend_from_slice(&((v * 32767.0) as i16).to_le_bytes()),
                    (1, 24) => {
                        let i = (v * 8_388_607.0) as i32;
                        b.extend_from_slice(&i.to_le_bytes()[..3]);
                    }
                    (3, 32) => b.extend_from_slice(&v.to_le_bytes()),
                    _ => panic!("ikke støttet i testen"),
                }
            }
        }
        std::fs::File::create(path).unwrap().write_all(&b).unwrap();
    }

    fn sine(rate: u32, secs: f64, hz: f64) -> Vec<f32> {
        let n = (rate as f64 * secs) as usize;
        (0..n)
            .map(|i| {
                (0.5 * (2.0 * std::f64::consts::PI * hz * i as f64 / rate as f64).sin()) as f32
            })
            .collect()
    }

    fn rms(x: &[f32]) -> f32 {
        (x.iter().map(|v| v * v).sum::<f32>() / x.len().max(1) as f32).sqrt()
    }

    #[test]
    fn wav_variants_resample_to_exact_length() {
        let d = tmpdir("wav");
        for (rate, ch, bits, kind) in [
            (48_000, 2, 16, 1),
            (44_100, 2, 24, 1),
            (22_050, 1, 32, 3),
            (16_000, 1, 16, 1),
            (8_000, 1, 16, 1),
        ] {
            let secs = 1.25;
            let src = sine(rate, secs, 440.0);
            let p = d.join(format!("t_{rate}_{ch}_{bits}.wav"));
            write_wav(&p, rate, ch, bits, kind, &src);
            let (info, out) = decode_all(&p).unwrap();
            assert_eq!(info.sample_rate, rate);
            assert_eq!(info.channels, ch as usize);
            let expected = (src.len() as f64 * 16_000.0 / rate as f64).round() as usize;
            assert_eq!(out.len(), expected, "rate {rate}");
            assert_eq!(out.len(), 20_000);
            // Sinus 0,5 i kanal 0 og -0,25 i kanal 1 → mono 0,125 i amplitude.
            let want = if ch == 2 { 0.125 } else { 0.5 } / std::f32::consts::SQRT_2;
            let mid = &out[2000..18000];
            assert!(
                (rms(mid) - want).abs() < 0.01,
                "rate {rate}: rms {} vs {want}",
                rms(mid)
            );
        }
    }

    #[test]
    fn streaming_read_in_small_pieces_gives_same_result() {
        let d = tmpdir("strom");
        let src = sine(44_100, 2.0, 300.0);
        let p = d.join("s.wav");
        write_wav(&p, 44_100, 2, 16, 1, &src);
        let (_, all) = decode_all(&p).unwrap();
        let mut s = AudioStream::open(&p).unwrap();
        let mut pieces = Vec::new();
        loop {
            let n = s.read(&mut pieces, 777).unwrap();
            if n == 0 {
                break;
            }
            assert!(n <= 777);
        }
        assert_eq!(pieces.len(), all.len());
        assert_eq!(s.emitted(), all.len() as u64);
        assert_eq!(s.estimated_total_samples(), Some(all.len() as u64));
        assert!(pieces.iter().zip(&all).all(|(a, b)| (a - b).abs() < 1e-6));
    }

    #[test]
    fn impulse_position_is_kept_after_resampling() {
        // Klikk ved nøyaktig 0,500 s i 44,1 kHz skal havne ved sample 8000 ±2.
        let d = tmpdir("klikk");
        let mut src = vec![0.0f32; 44_100];
        src[22_050] = 0.9;
        let p = d.join("k.wav");
        write_wav(&p, 44_100, 1, 16, 1, &src);
        let (_, out) = decode_all(&p).unwrap();
        let peak = out
            .iter()
            .enumerate()
            .max_by(|a, b| a.1.abs().total_cmp(&b.1.abs()))
            .map(|(i, _)| i)
            .unwrap();
        assert!((peak as i64 - 8000).abs() <= 2, "topp ved {peak}");
    }

    fn assert_fixture(name: &str, codec: &str, min_s: f64, max_s: f64) -> Vec<f32> {
        let (info, out) = decode_all(&fixture(name)).unwrap_or_else(|e| panic!("{name}: {e}"));
        assert_eq!(info.codec, codec, "{name}");
        let secs = out.len() as f64 / 16_000.0;
        assert!(secs >= min_s && secs <= max_s, "{name}: {secs} s");
        assert!(rms(&out) > 0.01, "{name}: stille");
        out
    }

    // Testfilene er laget av `testdata/lag-testfiler.sh`: 1,5 s med tone og
    // et klikk ved 1,000 s (se skriptet for verktøyene som ble brukt).
    #[test]
    fn decodes_fixture_formats() {
        for (name, codec) in [
            ("tone.mp3", "mp3"),
            ("tone.m4a", "aac"),
            ("tone.flac", "flac"),
            ("tone.ogg", "vorbis"),
            ("tone-video.mp4", "aac"),
            ("tone-video.mov", "aac"),
        ] {
            assert_fixture(name, codec, 1.45, 1.56);
        }
    }

    #[test]
    fn aac_priming_is_removed() {
        // Klikket ligger ved 1,000 s i kilden. Uten rettingen kom det 48 ms for sent.
        for name in ["tone.m4a", "tone-video.mov"] {
            let out = assert_fixture(name, "aac", 1.45, 1.56);
            let peak = click_position(&out);
            assert!((peak - 1.0).abs() < 0.006, "{name}: klikk ved {peak:.4} s");
        }
        let out = assert_fixture("tone.mp3", "mp3", 1.45, 1.56);
        assert!((click_position(&out) - 1.0).abs() < 0.006, "mp3");
    }

    /// Finner klikket: største utslag etter 0,95 s (tonen slutter ved 0,9 s).
    fn click_position(x: &[f32]) -> f64 {
        let from = 15_200;
        let (i, _) = x[from..]
            .iter()
            .enumerate()
            .max_by(|a, b| a.1.abs().total_cmp(&b.1.abs()))
            .unwrap();
        (from + i) as f64 / 16_000.0
    }

    #[test]
    fn unsupported_formats_are_named() {
        for (name, fmt) in [
            ("tone.webm", "webm"),
            ("tone.caf", "caf"),
            ("tone.aiff", "aiff"),
            ("tone-alac.m4a", "alac"),
            ("tone-opus.ogg", "opus"),
        ] {
            match AudioStream::open(&fixture(name)) {
                Err(CoreError::UnsupportedFormat { format }) => assert_eq!(format, fmt, "{name}"),
                Err(e) => panic!("{name}: feil type {e}"),
                Ok(_) => panic!("{name}: skulle feilet"),
            }
        }
    }

    #[test]
    fn sniffing_works_on_bytes() {
        let mut ogg = b"OggS\0\x02".to_vec();
        ogg.extend_from_slice(&[0u8; 22]);
        ogg.extend_from_slice(b"OpusHead");
        assert_eq!(sniff_unsupported(&ogg), Some("opus"));
        assert_eq!(sniff_unsupported(b"FORM\0\0\0\0AIFC"), Some("aiff"));
        assert_eq!(sniff_unsupported(b"caff\0\x01"), Some("caf"));
        assert_eq!(
            sniff_unsupported(&[0x1A, 0x45, 0xDF, 0xA3, 0, b'w', b'e', b'b', b'm']),
            Some("webm")
        );
        assert_eq!(
            sniff_unsupported(&[0x1A, 0x45, 0xDF, 0xA3, 0, b'm', b'a', b't']),
            Some("mkv")
        );
        assert_eq!(sniff_unsupported(b"RIFF\0\0\0\0WAVE"), None);
        assert_eq!(sniff_unsupported(b"ID3\x04"), None);
    }

    #[test]
    fn garbage_and_missing_files_give_clean_errors() {
        let d = tmpdir("søppel æøå");
        let p = d.join("tull.xyz");
        std::fs::write(&p, vec![0x55u8; 50_000]).unwrap();
        match AudioStream::open(&p) {
            Err(CoreError::UnsupportedFormat { format }) => assert_eq!(format, "xyz"),
            Err(e) => panic!("{e}"),
            Ok(_) => panic!("skulle feilet"),
        }
        assert!(matches!(
            AudioStream::open(&d.join("finnes-ikke.mp3")),
            Err(CoreError::FileNotFound)
        ));
        let empty = d.join("tom.wav");
        std::fs::write(&empty, b"").unwrap();
        assert!(matches!(
            AudioStream::open(&empty),
            Err(CoreError::EmptyAudio)
        ));
    }

    #[test]
    fn progress_fraction_moves_to_one() {
        let d = tmpdir("framdrift");
        let p = d.join("f.wav");
        write_wav(&p, 48_000, 2, 16, 1, &sine(48_000, 3.0, 200.0));
        let mut s = AudioStream::open(&p).unwrap();
        let mut buf = Vec::new();
        s.read(&mut buf, 16_000).unwrap();
        let f1 = s.fraction_read().unwrap();
        while s.read(&mut buf, 16_000).unwrap() > 0 {}
        let f2 = s.fraction_read().unwrap();
        assert!(f1 > 0.0 && f1 < 0.7, "{f1}");
        assert!((f2 - 1.0).abs() < 1e-9);
        assert_eq!(buf.len(), 48_000);
    }
}
