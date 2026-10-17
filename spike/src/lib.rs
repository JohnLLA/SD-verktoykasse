//! Spike, steg 0. Ikke appkode. Strømmende dekoding med symphonia og
//! resampling til 16 kHz mono f32 med rubato.
//!
//! Prinsipp: pakke for pakke fra symphonia, miks til mono i en liten
//! mellombuffer, send faste biter gjennom rubato, legg resultatet i én
//! utdatavektor. Bare utdata (16 kHz mono f32) vokser med fillengden.

use std::fs::File;
use std::path::Path;

use rubato::{FftFixedIn, Resampler};
use symphonia::core::audio::{AudioBufferRef, SampleBuffer};
use symphonia::core::codecs::{DecoderOptions, CODEC_TYPE_NULL};
use symphonia::core::errors::Error as SymError;
use symphonia::core::formats::FormatOptions;
use symphonia::core::io::MediaSourceStream;
use symphonia::core::meta::MetadataOptions;
use symphonia::core::probe::Hint;

pub const TARGET_RATE: u32 = 16_000;
const CHUNK_IN: usize = 4096;

#[derive(Debug)]
pub enum DecodeError {
    /// Containeren eller kodeken er ikke støttet. Tar med det vi vet om formatet
    /// (filending og ev. kodek), aldri filnavnet.
    Unsupported { what: String },
    NoAudioTrack,
    Io(std::io::Error),
    Other(String),
}

impl std::fmt::Display for DecodeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            DecodeError::Unsupported { what } => write!(f, "unsupported format: {what}"),
            DecodeError::NoAudioTrack => write!(f, "no audio track"),
            DecodeError::Io(e) => write!(f, "io error: {}", e.kind()),
            DecodeError::Other(s) => write!(f, "decode error: {s}"),
        }
    }
}

#[derive(Debug, Clone)]
pub struct SourceInfo {
    pub codec: String,
    pub sample_rate: u32,
    pub channels: usize,
    /// Antall rammer i kilden, hvis containeren oppgir det.
    pub n_frames: Option<u64>,
}

pub struct Decoded {
    pub info: SourceInfo,
    pub samples: Vec<f32>,
    /// Faktisk antall dekodede rammer (per kanal) før resampling.
    pub frames_in: u64,
}

fn codec_name(c: symphonia::core::codecs::CodecType) -> String {
    use symphonia::core::codecs::*;
    let n = match c {
        CODEC_TYPE_MP3 => "mp3",
        CODEC_TYPE_AAC => "aac",
        CODEC_TYPE_FLAC => "flac",
        CODEC_TYPE_VORBIS => "vorbis",
        CODEC_TYPE_OPUS => "opus",
        CODEC_TYPE_ALAC => "alac",
        CODEC_TYPE_PCM_S16LE => "pcm_s16le",
        CODEC_TYPE_PCM_S24LE => "pcm_s24le",
        CODEC_TYPE_PCM_F32LE => "pcm_f32le",
        _ => return format!("{c}"),
    };
    n.to_string()
}

/// Strømmende dekoding + resampling. `progress` kalles med (rammer lest, totalt hvis kjent).
pub fn decode_to_16k_mono(
    path: &Path,
    mut progress: impl FnMut(u64, Option<u64>),
) -> Result<Decoded, DecodeError> {
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| e.to_ascii_lowercase());
    let file = File::open(path).map_err(DecodeError::Io)?;
    let mss = MediaSourceStream::new(Box::new(file), Default::default());
    let mut hint = Hint::new();
    if let Some(e) = &ext {
        hint.with_extension(e);
    }
    let probed = symphonia::default::get_probe()
        .format(
            &hint,
            mss,
            &FormatOptions { enable_gapless: true, ..Default::default() },
            &MetadataOptions::default(),
        )
        .map_err(|e| match e {
            SymError::Unsupported(_) => DecodeError::Unsupported {
                what: format!("container .{}", ext.clone().unwrap_or_default()),
            },
            SymError::IoError(io) => DecodeError::Io(io),
            other => DecodeError::Other(other.to_string()),
        })?;
    let mut format = probed.format;

    // Første spor med en kjent lydkodek (mp4/mov kan ha video først).
    let track = format
        .tracks()
        .iter()
        .find(|t| t.codec_params.codec != CODEC_TYPE_NULL && t.codec_params.sample_rate.is_some())
        .ok_or(DecodeError::NoAudioTrack)?;
    let track_id = track.id;
    let params = track.codec_params.clone();
    let codec = codec_name(params.codec);

    let mut decoder = symphonia::default::get_codecs()
        .make(&params, &DecoderOptions::default())
        .map_err(|e| match e {
            SymError::Unsupported(_) => DecodeError::Unsupported { what: format!("codec {codec}") },
            other => DecodeError::Other(other.to_string()),
        })?;

    let sample_rate = params.sample_rate.unwrap_or(0);
    let channels = params.channels.map(|c| c.count()).unwrap_or(0);
    let mut info = SourceInfo { codec, sample_rate, channels, n_frames: params.n_frames };

    // Utdata: forhåndsreserver hvis lengden er kjent, så vi slipper doblinger.
    let mut out: Vec<f32> = Vec::new();
    if let (Some(n), true) = (params.n_frames, sample_rate > 0) {
        out.reserve_exact((n as f64 * TARGET_RATE as f64 / sample_rate as f64) as usize + CHUNK_IN);
    }

    let mut resampler: Option<FftFixedIn<f32>> = None;
    let mut pending: Vec<f32> = Vec::with_capacity(CHUNK_IN * 2);
    let mut sbuf: Option<SampleBuffer<f32>> = None;
    let mut frames_in: u64 = 0;
    let mut delay_left: usize = 0;

    loop {
        let packet = match format.next_packet() {
            Ok(p) => p,
            Err(SymError::IoError(e)) if e.kind() == std::io::ErrorKind::UnexpectedEof => break,
            Err(SymError::ResetRequired) => break,
            Err(e) => return Err(DecodeError::Other(e.to_string())),
        };
        if packet.track_id() != track_id {
            continue;
        }
        let decoded: AudioBufferRef = match decoder.decode(&packet) {
            Ok(d) => d,
            // Ødelagte pakker hoppes over, som symphonia anbefaler.
            Err(SymError::DecodeError(_)) => continue,
            Err(e) => return Err(DecodeError::Other(e.to_string())),
        };
        let spec = *decoded.spec();
        let ch = spec.channels.count();
        if info.sample_rate == 0 {
            info.sample_rate = spec.rate;
        }
        if info.channels == 0 {
            info.channels = ch;
        }
        let frames = decoded.frames();
        if frames == 0 {
            continue;
        }
        if sbuf.as_ref().map(|b| b.capacity() < frames * ch).unwrap_or(true) {
            sbuf = Some(SampleBuffer::<f32>::new(frames as u64, spec));
        }
        let sb = sbuf.as_mut().unwrap();
        sb.copy_interleaved_ref(decoded);
        let inter = sb.samples();
        // Miks til mono (snitt av kanalene).
        let inv = 1.0 / ch as f32;
        for f in inter.chunks_exact(ch) {
            pending.push(f.iter().sum::<f32>() * inv);
        }
        frames_in += frames as u64;
        progress(frames_in, info.n_frames);

        if spec.rate == TARGET_RATE {
            out.extend_from_slice(&pending);
            pending.clear();
            continue;
        }
        if resampler.is_none() {
            let r = FftFixedIn::<f32>::new(spec.rate as usize, TARGET_RATE as usize, CHUNK_IN, 2, 1)
                .map_err(|e| DecodeError::Other(e.to_string()))?;
            delay_left = r.output_delay();
            resampler = Some(r);
        }
        let r = resampler.as_mut().unwrap();
        let mut start = 0;
        while pending.len() - start >= r.input_frames_next() {
            let n = r.input_frames_next();
            let res = r
                .process(&[&pending[start..start + n]], None)
                .map_err(|e| DecodeError::Other(e.to_string()))?;
            push_skip_delay(&mut out, &res[0], &mut delay_left);
            start += n;
        }
        pending.drain(..start);
    }

    if let Some(r) = resampler.as_mut() {
        // Resten + tøm forsinkelsen i filteret.
        if !pending.is_empty() {
            let res = r
                .process_partial(Some(&[&pending[..]]), None)
                .map_err(|e| DecodeError::Other(e.to_string()))?;
            push_skip_delay(&mut out, &res[0], &mut delay_left);
        }
        let res = r
            .process_partial::<&[f32]>(None, None)
            .map_err(|e| DecodeError::Other(e.to_string()))?;
        push_skip_delay(&mut out, &res[0], &mut delay_left);
        // Kutt til forventet lengde.
        let expected =
            (frames_in as f64 * TARGET_RATE as f64 / info.sample_rate as f64).round() as usize;
        out.truncate(expected);
    } else if !pending.is_empty() {
        out.extend_from_slice(&pending);
    }
    out.shrink_to_fit();
    Ok(Decoded { info, samples: out, frames_in })
}

fn push_skip_delay(out: &mut Vec<f32>, data: &[f32], delay_left: &mut usize) {
    if *delay_left >= data.len() {
        *delay_left -= data.len();
        return;
    }
    out.extend_from_slice(&data[*delay_left..]);
    *delay_left = 0;
}
