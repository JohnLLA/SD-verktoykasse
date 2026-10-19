//! Biter, tidskoder og framdrift. Ren logikk uten whisper, så den kan testes.
//!
//! whisper.cpp regner ut mel-spektrogrammet for hele bufferet før den sjekker
//! avbryt-flagget, og en fil på 3 timer kostet 2 GB minne (docs/spike.md).
//! Motoren gir derfor whisper lyden i biter på omtrent 10 minutter, delt der
//! det er stillest i de siste 30 sekundene før grensen. Tidskodene i hver bit
//! forskyves med bitens start og klemmes til biten.

use super::decode::TARGET_RATE;
use super::types::Segment;

/// Standard bitlengde: 10 minutter.
pub const DEFAULT_CHUNK_SECS: u32 = 600;
/// Hvor langt tilbake fra grensen vi leter etter stillhet.
pub const DEFAULT_SEARCH_SECS: u32 = 30;
/// Minste lengde et segment får hvis whisper gir start = slutt.
pub const MIN_SEGMENT_MS: u64 = 200;
/// Anslått taletid per tegn for segmenter whisper legger ved eller etter
/// slutten av biten (omtrent 15 tegn i sekundet).
pub const FILL_MS_PER_CHAR: u64 = 60;
/// Lengste varighet et slikt segment får.
pub const MAX_FILL_MS: u64 = 10_000;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ChunkPlan {
    /// Største bit i samples.
    pub max_len: usize,
    /// Tidligste kuttpunkt i samples (max_len - søkevindu).
    pub min_len: usize,
}

impl ChunkPlan {
    pub fn new(chunk_secs: u32, search_secs: u32) -> Self {
        let chunk_secs = chunk_secs.max(2);
        let search = search_secs.min(chunk_secs / 2);
        let max_len = chunk_secs as usize * TARGET_RATE as usize;
        ChunkPlan {
            max_len,
            min_len: max_len - search as usize * TARGET_RATE as usize,
        }
    }
}

impl Default for ChunkPlan {
    fn default() -> Self {
        ChunkPlan::new(DEFAULT_CHUNK_SECS, DEFAULT_SEARCH_SECS)
    }
}

/// Velger hvor bufferet skal kuttes. `eof` betyr at det ikke kommer mer lyd.
/// Returnerer antall samples i neste bit (alltid > 0 hvis bufferet ikke er tomt).
pub fn find_cut(buf: &[f32], plan: ChunkPlan, eof: bool) -> usize {
    if buf.len() < plan.max_len || (eof && buf.len() <= plan.max_len) {
        return buf.len();
    }
    let lo = plan.min_len.min(buf.len());
    let hi = plan.max_len.min(buf.len());
    quietest_point(&buf[..hi], lo)
}

/// Midten av det stilleste vinduet på 300 ms mellom `lo` og slutten av `x`,
/// målt i rammer på 20 ms.
fn quietest_point(x: &[f32], lo: usize) -> usize {
    const FRAME: usize = (TARGET_RATE as usize) / 50; // 20 ms
    const WIN: usize = 15; // 15 × 20 ms = 300 ms
    let region = &x[lo..];
    let energies: Vec<f32> = region
        .chunks(FRAME)
        .map(|f| f.iter().map(|v| v * v).sum::<f32>())
        .collect();
    if energies.len() <= WIN {
        return x.len();
    }
    let mut sum: f32 = energies[..WIN].iter().sum();
    let mut best = (sum, 0usize);
    for i in WIN..energies.len() {
        sum += energies[i] - energies[i - WIN];
        if sum < best.0 {
            best = (sum, i + 1 - WIN);
        }
    }
    let center_frame = best.1 + WIN / 2;
    (lo + center_frame * FRAME).min(x.len()).max(1)
}

/// Gjør et segment fra whisper om til et segment i filens tid.
///
/// `t0_cs`/`t1_cs` er whispers tider i centisekunder fra starten av biten.
/// Tidene forskyves med `chunk_start_ms`, klemmes til `[chunk_start, chunk_end]`
/// (verbatim kan gi slutt etter at lyden er slutt), og et segment med null
/// lengde får [`MIN_SEGMENT_MS`] innenfor biten. Teksten får bare fjernet
/// mellomrom i endene; tomme segmenter blir `None`. Lydrett tekst endres ikke.
///
/// De siste segmentene i en bit får ofte tider ved eller etter slutten av lyden
/// (docs/kvalitet.md, «Funn i appen» punkt 2). Klemt til biten ville de fått
/// null lengde. Et slikt segment slutter i stedet ved slutten av biten og
/// starter der `prev` (forrige segment i filen) sluttet, men ikke mer enn et
/// anslag ut fra tekstlengden før slutten ([`FILL_MS_PER_CHAR`], høyst
/// [`MAX_FILL_MS`]). Er det ikke plass etter `prev`, legges det over slutten
/// av `prev`, men aldri før starten av `prev`, så rekkefølgen holder.
pub fn place_segment(
    t0_cs: i64,
    t1_cs: i64,
    text: &str,
    chunk_start_ms: u64,
    chunk_end_ms: u64,
    prev: Option<&Segment>,
) -> Option<Segment> {
    let text = text.trim();
    if text.is_empty() {
        return None;
    }
    let rel0 = (t0_cs.max(0) as u64).saturating_mul(10);
    let rel1 = (t1_cs.max(0) as u64).saturating_mul(10);
    let end_limit = chunk_end_ms.max(chunk_start_ms);
    let mut start = chunk_start_ms.saturating_add(rel0).min(end_limit);
    let mut end = chunk_start_ms.saturating_add(rel1).clamp(start, end_limit);
    if end == start {
        end = (start + MIN_SEGMENT_MS).min(end_limit);
    }
    if end == end_limit && end - start < MIN_SEGMENT_MS {
        let chars = text.chars().count() as u64;
        let want = chars
            .saturating_mul(FILL_MS_PER_CHAR)
            .clamp(MIN_SEGMENT_MS, MAX_FILL_MS);
        let (prev_start, prev_end) =
            prev.map_or((chunk_start_ms, chunk_start_ms), |p| (p.start_ms, p.end_ms));
        let floor = prev_start.clamp(chunk_start_ms, end_limit);
        let after_prev = prev_end.clamp(chunk_start_ms, end_limit);
        let by_text = end_limit.saturating_sub(want);
        start = if end_limit - after_prev >= MIN_SEGMENT_MS {
            after_prev.max(by_text)
        } else {
            floor.max(by_text)
        }
        .min(start)
        // Whisper kan gi en start før forrige segments start; rekkefølgen skal holde.
        .max(floor);
        end = end_limit;
    }
    Some(Segment {
        start_ms: start,
        end_ms: end,
        text: text.to_string(),
    })
}

pub fn samples_to_ms(samples: u64) -> u64 {
    samples * 1000 / TARGET_RATE as u64
}

/// Framdrift for hele jobben, klemt til 0–100 og aldri bakover.
///
/// whispers egen framdrift går over 100 når verbatim prøver på nytt
/// (docs/spike.md), så den klemmes før den brukes.
#[derive(Debug, Clone)]
pub struct Progress {
    last: f64,
}

impl Default for Progress {
    fn default() -> Self {
        Self::new()
    }
}

impl Progress {
    pub fn new() -> Self {
        Progress { last: 0.0 }
    }

    /// `chunk_start`/`chunk_len` i samples, `whisper_pct` fra whisper (kan være
    /// utenfor 0–100), `total` er anslått lengde i samples hvis kjent.
    pub fn update(
        &mut self,
        chunk_start: u64,
        chunk_len: u64,
        whisper_pct: i32,
        total: Option<u64>,
    ) -> f64 {
        let frac = (whisper_pct.clamp(0, 100) as f64) / 100.0;
        let pos = chunk_start as f64 + frac * chunk_len as f64;
        let p = match total {
            Some(t) if t > 0 => (pos / t as f64 * 100.0).clamp(0.0, 99.9),
            _ => self.last,
        };
        if p > self.last {
            self.last = p;
        }
        self.last
    }

    pub fn finish(&mut self) -> f64 {
        self.last = 100.0;
        self.last
    }

    pub fn current(&self) -> f64 {
        self.last
    }
}

/// Anslått gjenværende tid i ms fra brukt tid og framdrift i prosent.
/// `None` til det er gått litt tid og framdriften er over 2 %.
pub fn eta_ms(elapsed_ms: u64, percent: f64) -> Option<u64> {
    if percent < 2.0 || elapsed_ms < 3000 || percent >= 100.0 {
        return None;
    }
    let total = elapsed_ms as f64 * 100.0 / percent;
    Some((total - elapsed_ms as f64).max(0.0) as u64)
}

#[cfg(test)]
mod tests {
    use super::*;

    const R: usize = TARGET_RATE as usize;

    #[test]
    fn plan_default_is_ten_minutes_with_30_s_window() {
        let p = ChunkPlan::default();
        assert_eq!(p.max_len, 600 * R);
        assert_eq!(p.min_len, 570 * R);
    }

    #[test]
    fn cut_lands_in_silence_inside_window() {
        let plan = ChunkPlan::new(20, 6);
        // 25 s med «lyd», stille mellom 16,0 og 16,6 s.
        let mut buf: Vec<f32> = (0..25 * R)
            .map(|i| ((i % 37) as f32 / 37.0) - 0.5)
            .collect();
        for v in &mut buf[16 * R..(16 * R + R * 6 / 10)] {
            *v = 0.0;
        }
        let cut = find_cut(&buf, plan, false);
        let s = cut as f64 / R as f64;
        assert!(s > 16.0 && s < 16.6, "kutt ved {s}");
    }

    #[test]
    fn cut_without_silence_stays_inside_window() {
        let plan = ChunkPlan::new(20, 6);
        let buf = vec![0.3f32; 30 * R];
        let cut = find_cut(&buf, plan, false);
        assert!(cut >= plan.min_len && cut <= plan.max_len);
    }

    #[test]
    fn short_or_final_buffer_is_taken_whole() {
        let plan = ChunkPlan::new(20, 6);
        assert_eq!(find_cut(&vec![0.1; 5 * R], plan, true), 5 * R);
        assert_eq!(find_cut(&vec![0.1; 20 * R], plan, true), 20 * R);
    }

    #[test]
    fn segments_are_offset_and_clamped_across_chunks() {
        // Bit 2 starter ved 9:58,500 og slutter ved 19:57,000.
        let start = 598_500;
        let end = 1_197_000;
        let s = place_segment(150, 420, "  hei og hå  ", start, end, None).unwrap();
        assert_eq!((s.start_ms, s.end_ms), (600_000, 602_700));
        assert_eq!(s.text, "hei og hå");
        // Verbatim kan gi slutt etter lyden: klemmes til bitens slutt.
        let s = place_segment(59_000, 62_000, "x", start, end, None).unwrap();
        assert_eq!((s.start_ms, s.end_ms), (1_188_500, 1_197_000));
        // Start etter slutten av biten: aldri null lengde (se egen test).
        let s = place_segment(70_000, 71_000, "x", start, end, None).unwrap();
        assert_eq!((s.start_ms, s.end_ms), (end - MIN_SEGMENT_MS, end));
        // Null lengde får minstelengde.
        let s = place_segment(100, 100, "x", 0, 10_000, None).unwrap();
        assert_eq!((s.start_ms, s.end_ms), (1000, 1000 + MIN_SEGMENT_MS));
        // Negative tider og tom tekst.
        let s = place_segment(-5, -1, "x", 1000, 5000, None).unwrap();
        assert_eq!(s.start_ms, 1000);
        assert!(place_segment(0, 10, "   ", 0, 1000, None).is_none());
    }

    #[test]
    fn last_segments_at_end_of_audio_get_a_duration() {
        // nb-2 i steg 3: lyden er 135,9 s, og whisper legger de to siste
        // segmentene på eller etter slutten. Før: begge 135 900–135 900.
        let end = 135_900;
        let good = place_segment(12_800, 13_300, "og det var det", 0, end, None).unwrap();
        assert_eq!((good.start_ms, good.end_ms), (128_000, 133_000));
        // Kort tekst: anslaget (18 tegn × 60 ms) er kortere enn hullet på 2,9 s.
        let a = "takk for at du kom";
        let s = place_segment(13_590, 13_590, a, 0, end, Some(&good)).unwrap();
        assert_eq!((s.start_ms, s.end_ms), (end - 18 * FILL_MS_PER_CHAR, end));
        // Lang tekst: fyller hullet etter forrige segment, ikke lenger.
        let a = "takk for at du kom hit i dag og fortalte oss om dette her ja";
        let s1 = place_segment(13_590, 13_590, a, 0, end, Some(&good)).unwrap();
        assert_eq!((s1.start_ms, s1.end_ms), (133_000, end));
        let s2 = place_segment(13_700, 13_800, "ja", 0, end, Some(&s1)).unwrap();
        // Ingen plass etter s1: legges over slutten av s1, med anslått lengde.
        assert_eq!((s2.start_ms, s2.end_ms), (end - MIN_SEGMENT_MS, end));
        for (p, s) in [(&good, &s1), (&s1, &s2)] {
            assert!(s.end_ms > s.start_ms, "null lengde");
            assert!(s.start_ms >= p.start_ms, "rekkefølge");
            assert!(s.end_ms <= end, "etter lyden");
        }
        // Lang tekst og langt hull: anslaget ut fra teksten, høyst MAX_FILL_MS.
        let early = Segment {
            start_ms: 0,
            end_ms: 1_000,
            text: "x".into(),
        };
        let long = "a".repeat(500);
        let s = place_segment(20_000, 20_000, &long, 0, 60_000, Some(&early)).unwrap();
        assert_eq!((s.start_ms, s.end_ms), (60_000 - MAX_FILL_MS, 60_000));
        let s =
            place_segment(20_000, 20_000, "fem ord her nå da", 0, 60_000, Some(&early)).unwrap();
        assert_eq!(
            (s.start_ms, s.end_ms),
            (60_000 - 17 * FILL_MS_PER_CHAR, 60_000)
        );
        // Mellom biter: klemmes til denne bitens slutt, ikke filens.
        let s = place_segment(61_000, 61_000, "hei", 598_500, 1_197_000, None).unwrap();
        assert_eq!(
            (s.start_ms, s.end_ms),
            (1_197_000 - MIN_SEGMENT_MS, 1_197_000)
        );
        // Forrige segment fra en tidligere bit trekker ikke starten ut av biten.
        let s = place_segment(61_000, 61_000, &long, 598_500, 600_000, Some(&early)).unwrap();
        assert_eq!((s.start_ms, s.end_ms), (598_500, 600_000));
        // Whisper gir start før forrige segments start: klemmes til den.
        let prev = Segment {
            start_ms: 9_900,
            end_ms: 10_000,
            text: "x".into(),
        };
        let s = place_segment(985, 985, "ja", 0, 10_000, Some(&prev)).unwrap();
        assert_eq!((s.start_ms, s.end_ms), (9_900, 10_000));
        assert!(s.start_ms >= prev.start_ms && s.end_ms > s.start_ms);
        // Et kort, ekte segment midt i biten endres ikke.
        let s = place_segment(100, 115, "eh", 0, 10_000, Some(&early)).unwrap();
        assert_eq!((s.start_ms, s.end_ms), (1_000, 1_150));
    }

    #[test]
    fn exported_tail_has_no_zero_duration() {
        // Ende til ende med srt/vtt: ingen tidskode med lik start og slutt.
        use super::super::export::to_srt;
        let end = 135_900;
        let mut segs: Vec<Segment> = Vec::new();
        for (t0, t1, text) in [
            (0, 500, "første"),
            (13_590, 13_590, "andre"),
            (13_590, 13_590, "tredje"),
        ] {
            let s = place_segment(t0, t1, text, 0, end, segs.last()).unwrap();
            segs.push(s);
        }
        assert!(segs.iter().all(|s| s.end_ms > s.start_ms));
        let srt = to_srt(&segs);
        let cues: Vec<&str> = srt.lines().filter(|l| l.contains(" --> ")).collect();
        assert_eq!(cues.len(), 3);
        for cue in cues {
            let (a, b) = cue.split_once(" --> ").unwrap();
            assert_ne!(a, b, "null varighet i srt: {cue}");
        }
        assert!(srt.contains("00:02:15,900"));
    }

    #[test]
    fn lydrett_text_is_not_changed() {
        let s = place_segment(
            0,
            100,
            " nordmenn er nordlendinger trøndere ",
            0,
            10_000,
            None,
        )
        .unwrap();
        assert_eq!(s.text, "nordmenn er nordlendinger trøndere");
    }

    #[test]
    fn chunks_cover_whole_file_and_times_follow() {
        // Simulerer motorens løkke: 2 t 5 min lyd, biter på 10 min.
        let plan = ChunkPlan::default();
        let total = (2 * 3600 + 300) * R;
        let mut offset = 0usize;
        let mut buf_len;
        let mut n = 0;
        let mut last_end = 0;
        while offset < total {
            buf_len = (total - offset).min(plan.max_len + R);
            let eof = offset + buf_len >= total;
            let buf = vec![0.2f32; buf_len];
            let cut = find_cut(&buf, plan, eof);
            assert!(cut > 0);
            let cs = samples_to_ms(offset as u64);
            let ce = samples_to_ms((offset + cut) as u64);
            let seg = place_segment(0, 3000, "x", cs, ce, None).unwrap();
            assert!(seg.start_ms >= last_end);
            last_end = seg.end_ms;
            offset += cut;
            n += 1;
        }
        assert_eq!(offset, total);
        assert!((13..=14).contains(&n), "{n} biter");
    }

    #[test]
    fn progress_is_clamped_and_monotonic() {
        let mut p = Progress::new();
        let r = R as u64;
        assert_eq!(p.update(0, 600 * r, 50, Some(1200 * r)), 25.0);
        // Verbatim gir 125 %: klemmes.
        assert_eq!(p.update(0, 600 * r, 125, Some(1200 * r)), 50.0);
        // Aldri bakover (ny bit starter med 0 %, men forrige var 100 %).
        assert_eq!(p.update(0, 600 * r, 10, Some(1200 * r)), 50.0);
        assert_eq!(p.update(600 * r, 600 * r, 0, Some(1200 * r)), 50.0);
        // Et for lavt lengdeanslag gir ikke over 100.
        assert!(p.update(600 * r, 600 * r, 100, Some(900 * r)) < 100.0);
        assert_eq!(p.finish(), 100.0);
        // Ukjent lengde: står stille.
        let mut q = Progress::new();
        assert_eq!(q.update(0, 10, 50, None), 0.0);
    }

    #[test]
    fn eta_needs_some_progress() {
        assert_eq!(eta_ms(1000, 50.0), None);
        assert_eq!(eta_ms(10_000, 1.0), None);
        assert_eq!(eta_ms(10_000, 50.0), Some(10_000));
        assert_eq!(eta_ms(30_000, 25.0), Some(90_000));
    }
}
