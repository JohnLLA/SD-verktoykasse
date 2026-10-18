//! Modellnedlasting. Dette er det eneste stedet i Transkribering som går på nett.
//!
//! - Bare https og bare vertene i `models.json` (`huggingface.co`, `*.hf.co`).
//!   Omdirigeringer følges manuelt, og hver ny vert sjekkes før vi kobler til.
//! - Filen hentes i biter med HTTP Range til `<id>.bin.part` i appens
//!   modellmappe. Brudd kan gjenopptas: neste forsøk fortsetter fra der filen
//!   slapp, også etter at appen er startet på nytt.
//! - Biter gir også et øvre tak på hvor lenge én forespørsel kan henge (ureq
//!   har ingen tidsgrense per lesing), så avbryt og feil ikke blir hengende.
//! - SHA-256 og størrelse sjekkes mot `models.json` til slutt. Feil sum: filen
//!   slettes. Først da får den navnet `<id>.bin`.
//!
//! Ingenting om lyd eller tekst sendes. Forespørslene har bare URL-en fra
//! `models.json`, `Range` og en nøytral `User-Agent`.

use std::fs::{File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use sha2::{Digest, Sha256};

use super::error::{CoreError, CoreResult};
use super::models::{
    ensure_verified, hex, host_matches, url_host, Catalog, Location, ModelDirs, ModelEntry,
    VerifyCache, ALLOWED_HOSTS,
};

/// Størrelse på hver Range-forespørsel.
pub const PIECE_BYTES: u64 = 16 * 1024 * 1024;
const MAX_REDIRECTS: usize = 8;
const MAX_RETRIES: u32 = 5;

/// Hvilke verter og skjema nedlastingen får bruke.
#[derive(Debug, Clone)]
pub struct HostPolicy {
    hosts: Vec<String>,
    allow_http: bool,
}

impl HostPolicy {
    /// Vertene fra `models.json`, men bare de som også står i [`ALLOWED_HOSTS`].
    pub fn production(catalog: &Catalog) -> Self {
        let hosts = catalog
            .download_hosts
            .iter()
            .filter(|h| ALLOWED_HOSTS.contains(&h.as_str()))
            .cloned()
            .collect();
        HostPolicy {
            hosts,
            allow_http: false,
        }
    }

    #[cfg(test)]
    pub fn for_tests(hosts: &[&str]) -> Self {
        HostPolicy {
            hosts: hosts.iter().map(|s| s.to_string()).collect(),
            allow_http: true,
        }
    }

    pub fn check(&self, url: &str) -> CoreResult<()> {
        let (scheme, host) = url_host(url).ok_or(CoreError::HostNotAllowed {
            host: String::new(),
        })?;
        let scheme_ok = scheme == "https" || (self.allow_http && scheme == "http");
        if !scheme_ok || !host_matches(&host, &self.hosts) {
            return Err(CoreError::HostNotAllowed { host });
        }
        Ok(())
    }
}

/// Lager HTTP-klienten. Systemets sertifikatlager brukes (rustls-platform-verifier),
/// så nedlasting virker også bak bedriftsproxyer med egne rotsertifikater.
/// Proxy: `HTTPS_PROXY`/`HTTP_PROXY`/`ALL_PROXY` først, ellers (Windows) den
/// faste proxyen i Windows' Internett-innstillinger (`win-system-proxy`).
fn agent(policy: &HostPolicy) -> ureq::Agent {
    use ureq::tls::{RootCerts, TlsConfig};
    let tls = TlsConfig::builder()
        .root_certs(RootCerts::PlatformVerifier)
        .build();
    let cfg = ureq::Agent::config_builder()
        .max_redirects(0)
        .http_status_as_error(false)
        .https_only(!policy.allow_http)
        .tls_config(tls)
        .user_agent("lla-verktoykasse")
        .timeout_connect(Some(Duration::from_secs(30)))
        .timeout_recv_response(Some(Duration::from_secs(60)))
        // Én bit på 16 MB må komme innen 10 min (≈ 28 kB/s).
        .timeout_recv_body(Some(Duration::from_secs(600)))
        .build();
    ureq::Agent::new_with_config(cfg)
}

fn resolve_location(current: &str, location: &str) -> Option<String> {
    if location.starts_with("https://") || location.starts_with("http://") {
        return Some(location.to_string());
    }
    if location.starts_with('/') && !location.starts_with("//") {
        let uri: ureq::http::Uri = current.parse().ok()?;
        let scheme = uri.scheme_str()?;
        let auth = uri.authority()?.as_str();
        return Some(format!("{scheme}://{auth}{location}"));
    }
    None
}

enum Fetched {
    /// 206: bytes fra `start`.
    Partial {
        body: ureq::BodyReader<'static>,
        final_url: String,
    },
    /// 200: hele filen (serveren ignorerte Range).
    Full {
        body: ureq::BodyReader<'static>,
        final_url: String,
    },
    /// URL-en (signert CDN-adresse) virker ikke lenger. Start fra `models.json`-URL-en.
    Expired,
    /// 416: start er forbi slutten.
    RangeNotSatisfiable,
}

fn parse_content_range_start(v: &str) -> Option<u64> {
    // "bytes 100-199/1000"
    let rest = v.trim().strip_prefix("bytes")?.trim_start();
    let (range, _) = rest.split_once('/')?;
    let (start, _) = range.split_once('-')?;
    start.trim().parse().ok()
}

fn fetch(
    agent: &ureq::Agent,
    policy: &HostPolicy,
    url: &str,
    start: u64,
    end: u64,
    resolved: bool,
) -> CoreResult<Fetched> {
    let mut url = url.to_string();
    for _ in 0..=MAX_REDIRECTS {
        policy.check(&url)?;
        let resp = agent
            .get(&url)
            .header("Range", &format!("bytes={start}-{end}"))
            .call()
            .map_err(|_| CoreError::Network)?;
        let status = resp.status().as_u16();
        match status {
            301 | 302 | 303 | 307 | 308 => {
                let loc = resp
                    .headers()
                    .get("location")
                    .and_then(|v| v.to_str().ok())
                    .and_then(|l| resolve_location(&url, l))
                    .ok_or(CoreError::HttpStatus { status })?;
                url = loc;
            }
            206 => {
                let cr = resp
                    .headers()
                    .get("content-range")
                    .and_then(|v| v.to_str().ok())
                    .and_then(parse_content_range_start);
                if cr != Some(start) {
                    return Err(CoreError::HttpStatus { status });
                }
                return Ok(Fetched::Partial {
                    body: resp.into_body().into_reader(),
                    final_url: url,
                });
            }
            200 => {
                return Ok(Fetched::Full {
                    body: resp.into_body().into_reader(),
                    final_url: url,
                })
            }
            416 => return Ok(Fetched::RangeNotSatisfiable),
            401 | 403 | 404 | 410 if resolved => return Ok(Fetched::Expired),
            _ => return Err(CoreError::HttpStatus { status }),
        }
    }
    Err(CoreError::HttpStatus { status: 310 })
}

/// Framdrift: (lastet ned, totalt) i byte.
pub type ProgressFn<'a> = &'a mut dyn FnMut(u64, u64);

struct PartFile {
    file: File,
    hasher: Sha256,
    pos: u64,
}

impl PartFile {
    /// Åpner `.part`-filen og hasher det som allerede ligger der.
    fn open(path: &PathBuf, max: u64, cancel: &AtomicBool) -> CoreResult<Self> {
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(path)?;
        let mut len = file.metadata()?.len();
        if len > max {
            file.set_len(0)?;
            len = 0;
        }
        let mut hasher = Sha256::new();
        file.seek(SeekFrom::Start(0))?;
        let mut buf = vec![0u8; 1 << 20];
        let mut left = len;
        while left > 0 {
            if cancel.load(Ordering::Relaxed) {
                return Err(CoreError::Cancelled);
            }
            let want = left.min(buf.len() as u64) as usize;
            let n = file.read(&mut buf[..want])?;
            if n == 0 {
                break;
            }
            hasher.update(&buf[..n]);
            left -= n as u64;
        }
        let pos = len - left;
        file.seek(SeekFrom::Start(pos))?;
        Ok(PartFile { file, hasher, pos })
    }

    fn restart(&mut self) -> CoreResult<()> {
        self.file.set_len(0)?;
        self.file.seek(SeekFrom::Start(0))?;
        self.hasher = Sha256::new();
        self.pos = 0;
        Ok(())
    }

    /// Kopierer høyst `limit` byte fra `body`. Returnerer `Err(Network)` ved
    /// brudd; det som er skrevet til da, er beholdt og hashet.
    fn copy_from(
        &mut self,
        body: &mut dyn Read,
        limit: u64,
        total: u64,
        cancel: &AtomicBool,
        progress: ProgressFn,
    ) -> CoreResult<u64> {
        let mut buf = vec![0u8; 256 * 1024];
        let mut copied = 0u64;
        let mut since_report = 0u64;
        while copied < limit {
            if cancel.load(Ordering::Relaxed) {
                return Err(CoreError::Cancelled);
            }
            let want = (limit - copied).min(buf.len() as u64) as usize;
            let n = match body.read(&mut buf[..want]) {
                Ok(0) => break,
                Ok(n) => n,
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
                Err(_) => return Err(CoreError::Network),
            };
            self.file.write_all(&buf[..n])?;
            self.hasher.update(&buf[..n]);
            self.pos += n as u64;
            copied += n as u64;
            since_report += n as u64;
            if since_report >= 1 << 20 {
                progress(self.pos, total);
                since_report = 0;
            }
        }
        progress(self.pos, total);
        Ok(copied)
    }
}

/// Laster ned (eller gjenopptar) en modell til appens modellmappe og sjekker
/// SHA-256. Returnerer stien til den ferdige filen.
///
/// Ligger filen der fra før med riktig størrelse, sjekkes den mot SHA-256 én
/// gang (resultatet huskes i `cache`). Feil sum: filen slettes og lastes ned
/// på nytt. En ferdig nedlasting merkes som sjekket i `cache`; kalleren lagrer
/// cachen.
pub fn download_model(
    entry: &ModelEntry,
    dirs: &ModelDirs,
    policy: &HostPolicy,
    cache: &Mutex<VerifyCache>,
    cancel: &AtomicBool,
    progress: ProgressFn,
) -> CoreResult<PathBuf> {
    policy.check(&entry.url)?;
    std::fs::create_dir_all(&dirs.app_dir)?;
    let dest = dirs.app_path(entry);
    if std::fs::metadata(&dest)
        .map(|m| m.len() == entry.bytes)
        .unwrap_or(false)
    {
        match ensure_verified(&dest, Location::App, entry, cache, cancel) {
            Ok(_) => {
                progress(entry.bytes, entry.bytes);
                return Ok(dest);
            }
            // Filen er slettet av ensure_verified; last ned på nytt.
            Err(CoreError::ChecksumMismatch) => {}
            Err(e) => return Err(e),
        }
    }
    let part_path = dirs.part_path(entry);
    let total = entry.bytes;
    let mut part = PartFile::open(&part_path, total, cancel)?;
    progress(part.pos, total);

    let agent = agent(policy);
    let mut resolved: Option<String> = None;
    let mut retries = 0u32;
    let mut restarted = false;
    while part.pos < total {
        if cancel.load(Ordering::Relaxed) {
            return Err(CoreError::Cancelled);
        }
        let start = part.pos;
        let end = (start + PIECE_BYTES).min(total) - 1;
        let url = resolved.clone().unwrap_or_else(|| entry.url.clone());
        let result = fetch(&agent, policy, &url, start, end, resolved.is_some());
        let step: CoreResult<()> = match result {
            Ok(Fetched::Partial {
                mut body,
                final_url,
            }) => {
                resolved = Some(final_url);
                let want = end - start + 1;
                match part.copy_from(&mut body, want, total, cancel, progress) {
                    Ok(n) if n < want => Err(CoreError::Network),
                    Ok(_) => Ok(()),
                    Err(e) => Err(e),
                }
            }
            Ok(Fetched::Full {
                mut body,
                final_url,
            }) => {
                // Serveren ignorerte Range: hele filen kommer. Start på nytt.
                resolved = Some(final_url);
                part.restart()?;
                match part.copy_from(&mut body, total, total, cancel, progress) {
                    Ok(n) if n < total => Err(CoreError::Network),
                    Ok(_) => Ok(()),
                    Err(e) => Err(e),
                }
            }
            Ok(Fetched::Expired) => {
                resolved = None;
                Err(CoreError::Network)
            }
            Ok(Fetched::RangeNotSatisfiable) if !restarted => {
                restarted = true;
                part.restart()?;
                Ok(())
            }
            Ok(Fetched::RangeNotSatisfiable) => Err(CoreError::HttpStatus { status: 416 }),
            Err(e) => Err(e),
        };
        match step {
            Ok(()) => retries = 0,
            // Nettverksbrudd og midlertidige serverfeil (5xx) prøves på nytt.
            Err(CoreError::Network) | Err(CoreError::HttpStatus { status: 500..=599 }) => {
                // Teller forsøk på rad uten framgang.
                if part.pos > start {
                    retries = 0;
                }
                retries += 1;
                if retries > MAX_RETRIES {
                    part.file.sync_all().ok();
                    return Err(CoreError::Network);
                }
                // Kort pause; ny forespørsel går via huggingface.co for fersk CDN-adresse.
                resolved = None;
                sleep_unless_cancelled(Duration::from_millis(500 * retries as u64), cancel)?;
            }
            Err(e) => {
                part.file.sync_all().ok();
                return Err(e);
            }
        }
    }
    part.file.sync_all()?;
    let PartFile { file, hasher, pos } = part;
    drop(file);
    if pos != total {
        let _ = std::fs::remove_file(&part_path);
        return Err(CoreError::SizeMismatch);
    }
    let sum = hex(&hasher.finalize());
    if sum != entry.sha256 {
        let _ = std::fs::remove_file(&part_path);
        return Err(CoreError::ChecksumMismatch);
    }
    std::fs::rename(&part_path, &dest)?;
    cache
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .mark(&dest, entry);
    Ok(dest)
}

fn sleep_unless_cancelled(d: Duration, cancel: &AtomicBool) -> CoreResult<()> {
    let step = Duration::from_millis(50);
    let mut left = d;
    while left > Duration::ZERO {
        if cancel.load(Ordering::Relaxed) {
            return Err(CoreError::Cancelled);
        }
        let s = left.min(step);
        std::thread::sleep(s);
        left -= s;
    }
    Ok(())
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use std::io::{BufRead, BufReader};
    use std::net::{TcpListener, TcpStream};
    use std::sync::{Arc, Mutex};

    /// Liten HTTP-server for testene. `/m.bin` gir `data` med Range-støtte,
    /// `/start` sender videre til `/m.bin`, `/evil` sender videre til en vert
    /// som ikke er tillatt. `cut_first` bryter forbindelsen etter så mange
    /// byte i de første forespørslene.
    type RequestLog = Arc<Mutex<Vec<(String, Option<String>)>>>;

    pub struct TestServer {
        pub port: u16,
        pub requests: RequestLog,
    }

    #[derive(Clone)]
    pub struct Behaviour {
        pub data: Arc<Vec<u8>>,
        /// Antall forespørsler mot /m.bin som brytes, og etter hvor mange byte.
        pub cut_requests: usize,
        pub cut_after: usize,
        pub ignore_range: bool,
        /// Når bruddene er brukt opp: svar med denne statusen i stedet for data.
        pub then_status: Option<u16>,
    }

    impl TestServer {
        pub fn start(b: Behaviour) -> TestServer {
            let l = TcpListener::bind("127.0.0.1:0").unwrap();
            let port = l.local_addr().unwrap().port();
            let requests = Arc::new(Mutex::new(Vec::new()));
            let reqs = requests.clone();
            let cuts = Arc::new(Mutex::new(b.cut_requests));
            std::thread::spawn(move || {
                for s in l.incoming() {
                    let Ok(s) = s else { continue };
                    let b = b.clone();
                    let reqs = reqs.clone();
                    let cuts = cuts.clone();
                    std::thread::spawn(move || {
                        let _ = handle(s, port, &b, &reqs, &cuts);
                    });
                }
            });
            TestServer { port, requests }
        }

        pub fn url(&self, path: &str) -> String {
            format!("http://127.0.0.1:{}{}", self.port, path)
        }

        pub fn ranges(&self) -> Vec<Option<String>> {
            self.requests
                .lock()
                .unwrap()
                .iter()
                .filter(|r| r.0 == "/m.bin")
                .map(|r| r.1.clone())
                .collect()
        }
    }

    fn handle(
        mut s: TcpStream,
        port: u16,
        b: &Behaviour,
        reqs: &Mutex<Vec<(String, Option<String>)>>,
        cuts: &Mutex<usize>,
    ) -> std::io::Result<()> {
        let mut r = BufReader::new(s.try_clone()?);
        let mut line = String::new();
        r.read_line(&mut line)?;
        let path = line.split_whitespace().nth(1).unwrap_or("/").to_string();
        let mut range = None;
        loop {
            let mut h = String::new();
            r.read_line(&mut h)?;
            if h == "\r\n" || h.is_empty() {
                break;
            }
            if let Some((k, v)) = h.split_once(':') {
                if k.eq_ignore_ascii_case("range") {
                    range = Some(v.trim().to_string());
                }
            }
        }
        reqs.lock().unwrap().push((path.clone(), range.clone()));
        match path.as_str() {
            "/start" => write!(s, "HTTP/1.1 302 Found\r\nLocation: /m.bin\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"),
            "/abs" => write!(s, "HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:{port}/m.bin\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"),
            "/evil" => write!(s, "HTTP/1.1 302 Found\r\nLocation: http://evil.example.com/m.bin\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"),
            "/m.bin" if b.then_status.is_some() && *cuts.lock().unwrap() == 0 => {
                write!(s, "HTTP/1.1 {} Feil\r\nContent-Length: 0\r\nConnection: close\r\n\r\n", b.then_status.unwrap_or(500))
            }
            "/m.bin" => {
                let len = b.data.len();
                let (start, end, partial) = match (&range, b.ignore_range) {
                    (Some(r), false) => {
                        let r = r.trim_start_matches("bytes=");
                        let (a, z) = r.split_once('-').unwrap();
                        let a: usize = a.parse().unwrap();
                        let z: usize = if z.is_empty() { len - 1 } else { z.parse::<usize>().unwrap().min(len - 1) };
                        if a >= len {
                            write!(s, "HTTP/1.1 416 Range Not Satisfiable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")?;
                            return Ok(());
                        }
                        (a, z, true)
                    }
                    _ => (0, len - 1, false),
                };
                let body = &b.data[start..=end];
                if partial {
                    write!(s, "HTTP/1.1 206 Partial Content\r\nContent-Range: bytes {start}-{end}/{len}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n", body.len())?;
                } else {
                    write!(s, "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n", body.len())?;
                }
                let cut = {
                    let mut c = cuts.lock().unwrap();
                    if *c > 0 {
                        *c -= 1;
                        true
                    } else {
                        false
                    }
                };
                if cut {
                    s.write_all(&body[..b.cut_after.min(body.len())])?;
                    s.flush()?;
                    let _ = s.shutdown(std::net::Shutdown::Both);
                    return Ok(());
                }
                s.write_all(body)
            }
            _ => write!(s, "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"),
        }
    }

    pub fn test_data(n: usize) -> Vec<u8> {
        let mut x: u32 = 12345;
        (0..n)
            .map(|_| {
                x ^= x << 13;
                x ^= x >> 17;
                x ^= x << 5;
                x as u8
            })
            .collect()
    }

    fn sha(d: &[u8]) -> String {
        hex(&Sha256::digest(d))
    }

    pub fn entry_for(url: String, data: &[u8]) -> ModelEntry {
        ModelEntry {
            id: "test-modell".into(),
            variant: "verbatim".into(),
            style: None,
            size: "small".into(),
            quant: "q5_0".into(),
            repo: "NbAiLab/test".into(),
            revision: "r".into(),
            file: "m.bin".into(),
            url,
            bytes: data.len() as u64,
            sha256: sha(data),
            note: None,
        }
    }

    fn dirs(tag: &str) -> ModelDirs {
        let d =
            std::env::temp_dir().join(format!("lla-nedlasting-{tag}-{} æøå", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        ModelDirs {
            app_dir: d,
            custom_dir: None,
        }
    }

    fn policy() -> HostPolicy {
        HostPolicy::for_tests(&["127.0.0.1"])
    }

    fn no_cancel() -> AtomicBool {
        AtomicBool::new(false)
    }

    fn cache() -> Mutex<VerifyCache> {
        Mutex::new(VerifyCache::default())
    }

    #[test]
    fn existing_file_with_right_size_but_wrong_content_is_not_used() {
        let data = Arc::new(test_data(120_000));
        let srv = TestServer::start(Behaviour {
            data: data.clone(),
            cut_requests: 0,
            cut_after: 0,
            ignore_range: false,
            then_status: None,
        });
        let e = entry_for(srv.url("/m.bin"), &data);
        let d = dirs("feil-innhold");
        std::fs::create_dir_all(&d.app_dir).unwrap();
        // Riktig størrelse, feil innhold.
        std::fs::write(d.app_path(&e), vec![0u8; data.len()]).unwrap();
        let c = cache();
        let p = download_model(&e, &d, &policy(), &c, &no_cancel(), &mut |_, _| {}).unwrap();
        assert_eq!(
            std::fs::read(&p).unwrap(),
            *data,
            "filen skal være lastet ned på nytt"
        );
        assert_eq!(srv.ranges().len(), 1);
        // Den nye filen er merket som sjekket: neste kall verken hasher på nytt
        // (cachen sier ja) eller går på nett.
        assert!(c.lock().unwrap().is_verified(&p, &e));
        download_model(&e, &d, &policy(), &c, &no_cancel(), &mut |_, _| {}).unwrap();
        assert_eq!(srv.ranges().len(), 1);
    }

    #[test]
    fn existing_correct_file_is_checked_once_without_network() {
        let data = Arc::new(test_data(50_000));
        let srv = TestServer::start(Behaviour {
            data: data.clone(),
            cut_requests: 0,
            cut_after: 0,
            ignore_range: false,
            then_status: None,
        });
        let e = entry_for(srv.url("/m.bin"), &data);
        let d = dirs("riktig-fra-for");
        std::fs::create_dir_all(&d.app_dir).unwrap();
        std::fs::write(d.app_path(&e), &*data).unwrap();
        let c = cache();
        download_model(&e, &d, &policy(), &c, &no_cancel(), &mut |_, _| {}).unwrap();
        assert!(srv.ranges().is_empty());
        assert!(c.lock().unwrap().is_verified(&d.app_path(&e), &e));
    }

    #[test]
    fn downloads_via_redirect_in_pieces_and_verifies() {
        let data = Arc::new(test_data((PIECE_BYTES as usize) * 2 + 12345));
        let srv = TestServer::start(Behaviour {
            data: data.clone(),
            cut_requests: 0,
            cut_after: 0,
            ignore_range: false,
            then_status: None,
        });
        let e = entry_for(srv.url("/start"), &data);
        let d = dirs("ok");
        let mut last = (0, 0);
        let p = download_model(&e, &d, &policy(), &cache(), &no_cancel(), &mut |a, b| {
            last = (a, b)
        })
        .unwrap();
        assert_eq!(std::fs::read(&p).unwrap(), *data);
        assert_eq!(last, (data.len() as u64, data.len() as u64));
        assert!(!d.part_path(&e).exists());
        // Tre biter. Første via /start, resten direkte mot den omdirigerte adressen.
        let r = srv.ranges();
        assert_eq!(r.len(), 3, "{r:?}");
        assert_eq!(
            r[0].as_deref(),
            Some(format!("bytes=0-{}", PIECE_BYTES - 1).as_str())
        );
        assert_eq!(
            r[2].as_deref(),
            Some(format!("bytes={}-{}", 2 * PIECE_BYTES, data.len() - 1).as_str())
        );
        // Allerede nedlastet: ingen nye forespørsler.
        download_model(&e, &d, &policy(), &cache(), &no_cancel(), &mut |_, _| {}).unwrap();
        assert_eq!(srv.ranges().len(), 3);
    }

    #[test]
    fn broken_connection_is_resumed_with_range() {
        let data = Arc::new(test_data(300_000));
        let srv = TestServer::start(Behaviour {
            data: data.clone(),
            cut_requests: 2,
            cut_after: 70_000,
            ignore_range: false,
            then_status: None,
        });
        let e = entry_for(srv.url("/abs"), &data);
        let d = dirs("brudd");
        let p = download_model(&e, &d, &policy(), &cache(), &no_cancel(), &mut |_, _| {}).unwrap();
        assert_eq!(std::fs::read(&p).unwrap(), *data);
        let r = srv.ranges();
        assert_eq!(r[0].as_deref(), Some("bytes=0-299999"));
        assert_eq!(r[1].as_deref(), Some("bytes=70000-299999"));
        assert_eq!(r[2].as_deref(), Some("bytes=140000-299999"));
    }

    #[test]
    fn resume_after_restart_continues_from_part_file() {
        let data = Arc::new(test_data(200_000));
        // Første økt: forbindelsen brytes etter 50 000 byte, og så svarer serveren 404.
        let srv = TestServer::start(Behaviour {
            data: data.clone(),
            cut_requests: 1,
            cut_after: 50_000,
            ignore_range: false,
            then_status: Some(404),
        });
        let e = entry_for(srv.url("/m.bin"), &data);
        let d = dirs("gjenoppta");
        let first = download_model(&e, &d, &policy(), &cache(), &no_cancel(), &mut |_, _| {});
        assert_eq!(first, Err(CoreError::HttpStatus { status: 404 }));
        let have = std::fs::metadata(d.part_path(&e)).unwrap().len();
        assert_eq!(have, 50_000);
        // Andre økt (ny «app-start») mot en server som virker.
        let srv2 = TestServer::start(Behaviour {
            data: data.clone(),
            cut_requests: 0,
            cut_after: 0,
            ignore_range: false,
            then_status: None,
        });
        let e2 = entry_for(srv2.url("/m.bin"), &data);
        let p = download_model(&e2, &d, &policy(), &cache(), &no_cancel(), &mut |_, _| {}).unwrap();
        assert_eq!(std::fs::read(&p).unwrap(), *data);
        assert_eq!(srv2.ranges(), vec![Some(format!("bytes={have}-199999"))]);
    }

    #[test]
    fn wrong_checksum_discards_file() {
        let data = Arc::new(test_data(100_000));
        let srv = TestServer::start(Behaviour {
            data: data.clone(),
            cut_requests: 0,
            cut_after: 0,
            ignore_range: false,
            then_status: None,
        });
        let mut e = entry_for(srv.url("/m.bin"), &data);
        e.sha256 = sha(b"noe helt annet");
        let d = dirs("feilsum");
        assert_eq!(
            download_model(&e, &d, &policy(), &cache(), &no_cancel(), &mut |_, _| {}),
            Err(CoreError::ChecksumMismatch)
        );
        assert!(!d.part_path(&e).exists());
        assert!(!d.app_path(&e).exists());
    }

    #[test]
    fn corrupted_part_file_is_caught_by_checksum() {
        let data = Arc::new(test_data(100_000));
        let srv = TestServer::start(Behaviour {
            data: data.clone(),
            cut_requests: 0,
            cut_after: 0,
            ignore_range: false,
            then_status: None,
        });
        let e = entry_for(srv.url("/m.bin"), &data);
        let d = dirs("korrupt");
        std::fs::create_dir_all(&d.app_dir).unwrap();
        std::fs::write(d.part_path(&e), vec![0u8; 40_000]).unwrap();
        assert_eq!(
            download_model(&e, &d, &policy(), &cache(), &no_cancel(), &mut |_, _| {}),
            Err(CoreError::ChecksumMismatch)
        );
        assert!(!d.part_path(&e).exists());
        // Neste forsøk starter fra null og lykkes.
        download_model(&e, &d, &policy(), &cache(), &no_cancel(), &mut |_, _| {}).unwrap();
    }

    #[test]
    fn server_ignoring_range_restarts_cleanly() {
        let data = Arc::new(test_data(90_000));
        let srv = TestServer::start(Behaviour {
            data: data.clone(),
            cut_requests: 0,
            cut_after: 0,
            ignore_range: true,
            then_status: None,
        });
        let e = entry_for(srv.url("/m.bin"), &data);
        let d = dirs("200");
        std::fs::create_dir_all(&d.app_dir).unwrap();
        std::fs::write(d.part_path(&e), &data[..30_000]).unwrap();
        let p = download_model(&e, &d, &policy(), &cache(), &no_cancel(), &mut |_, _| {}).unwrap();
        assert_eq!(std::fs::read(&p).unwrap(), *data);
    }

    #[test]
    fn redirect_to_other_host_is_refused() {
        let data = Arc::new(test_data(1000));
        let srv = TestServer::start(Behaviour {
            data: data.clone(),
            cut_requests: 0,
            cut_after: 0,
            ignore_range: false,
            then_status: None,
        });
        let e = entry_for(srv.url("/evil"), &data);
        let d = dirs("vert");
        assert_eq!(
            download_model(&e, &d, &policy(), &cache(), &no_cancel(), &mut |_, _| {}),
            Err(CoreError::HostNotAllowed {
                host: "evil.example.com".into()
            })
        );
        // Ingen forespørsel gikk dit (serveren så bare /evil).
        assert!(srv.requests.lock().unwrap().iter().all(|r| r.0 == "/evil"));
    }

    #[test]
    fn production_policy_only_allows_hugging_face_over_https() {
        let c = Catalog::builtin().unwrap();
        let p = HostPolicy::production(&c);
        assert!(p
            .check("https://huggingface.co/NbAiLab/x/resolve/r/f.bin")
            .is_ok());
        assert!(p.check("https://us.aws.cdn.hf.co/xet/abc").is_ok());
        assert!(p.check("http://huggingface.co/x").is_err());
        assert!(p.check("https://example.com/x").is_err());
        assert!(p.check("https://127.0.0.1/x").is_err());
        assert!(p.check("https://huggingface.co.evil.net/x").is_err());
        for m in &c.models {
            assert!(p.check(&m.url).is_ok(), "{}", m.id);
        }
    }

    #[test]
    fn cancel_keeps_part_for_later() {
        let data = Arc::new(test_data(400_000));
        let srv = TestServer::start(Behaviour {
            data: data.clone(),
            cut_requests: 0,
            cut_after: 0,
            ignore_range: false,
            then_status: None,
        });
        let e = entry_for(srv.url("/m.bin"), &data);
        let d = dirs("avbryt");
        let cancel = AtomicBool::new(false);
        // Avbryt ved første framdriftsmelding etter start.
        let mut calls = 0;
        let r = download_model(&e, &d, &policy(), &cache(), &cancel, &mut |_, _| {
            calls += 1;
            if calls == 1 {
                cancel.store(true, Ordering::Relaxed);
            }
        });
        assert_eq!(r, Err(CoreError::Cancelled));
        assert!(d.part_path(&e).exists());
        assert!(!d.app_path(&e).exists());
    }

    // ---- Mot ekte Hugging Face. Kjøres i CI med `--ignored`. ----

    /// Modellene integrasjonstestene trenger, lastet ned med appens egen kode.
    pub const CI_MODELS: &[&str] = &[
        "nb-whisper-small-verbatim-q5_0",
        "nb-whisper-small-semantic-q5_0",
    ];

    fn ci_model_dir() -> PathBuf {
        match std::env::var_os("LLA_TEST_MODEL_DIR") {
            Some(d) => PathBuf::from(d),
            None => panic!("sett LLA_TEST_MODEL_DIR"),
        }
    }

    #[test]
    #[ignore = "laster ned fra huggingface.co (LLA_TEST_MODEL_DIR)"]
    fn real_download_from_hugging_face() {
        let c = Catalog::builtin().unwrap();
        let policy = HostPolicy::production(&c);
        let dirs = ModelDirs {
            app_dir: ci_model_dir(),
            custom_dir: None,
        };
        for id in CI_MODELS {
            let e = c.get(id).unwrap();
            let t = std::time::Instant::now();
            let p =
                download_model(e, &dirs, &policy, &cache(), &no_cancel(), &mut |_, _| {}).unwrap();
            assert_eq!(std::fs::metadata(&p).unwrap().len(), e.bytes);
            println!("{id}: klar etter {:.1} s", t.elapsed().as_secs_f64());
        }
    }

    #[test]
    #[ignore = "laster ned 2 MB fra huggingface.co (LLA_TEST_MODEL_DIR med ferdig modell)"]
    fn real_range_resume_through_cdn_redirect() {
        let c = Catalog::builtin().unwrap();
        let policy = HostPolicy::production(&c);
        let e = c.get(CI_MODELS[0]).unwrap();
        let full = ci_model_dir().join(e.local_file_name());
        let reference = std::fs::read(&full).expect("kjør real_download_from_hugging_face først");
        let d = dirs("hf");
        for target in [1u64 << 20, 2 << 20] {
            let cancel = AtomicBool::new(false);
            let r = download_model(e, &d, &policy, &cache(), &cancel, &mut |got, _| {
                if got >= target {
                    cancel.store(true, Ordering::Relaxed);
                }
            });
            assert_eq!(r, Err(CoreError::Cancelled));
        }
        let part = std::fs::read(d.part_path(e)).unwrap();
        assert!(part.len() as u64 >= 2 << 20, "{}", part.len());
        assert_eq!(
            part[..],
            reference[..part.len()],
            "gjenopptatt fil avviker fra originalen"
        );
        let _ = std::fs::remove_dir_all(&d.app_dir);
    }

    #[test]
    fn helpers() {
        assert_eq!(parse_content_range_start("bytes 100-199/1000"), Some(100));
        assert_eq!(parse_content_range_start("bytes */1000"), None);
        assert_eq!(
            resolve_location("https://huggingface.co/a/b", "/api/c"),
            Some("https://huggingface.co/api/c".into())
        );
        assert_eq!(
            resolve_location("https://huggingface.co/a/b", "https://x.hf.co/c"),
            Some("https://x.hf.co/c".into())
        );
        assert_eq!(
            resolve_location("https://huggingface.co/a/b", "//evil.com/c"),
            None
        );
        assert_eq!(
            resolve_location("https://huggingface.co/a/b", "relativ"),
            None
        );
    }
}
