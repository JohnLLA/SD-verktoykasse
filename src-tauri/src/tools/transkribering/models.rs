//! Modellkatalogen (`models.json`), modellvalg og hvor modellene ligger.
//!
//! `models.json` bygges inn i appen ved kompilering og sjekkes ved oppstart:
//! bare https, bare vertene i `download_hosts` (som igjen må være blant
//! [`ALLOWED_HOSTS`]), SHA-256 på 64 heksadesimaltegn og en modell for hver
//! kombinasjon av stil og kvalitet. Modellvalget er datastyrt: hvilken variant
//! «tolket» bruker, står i `style_to_variant` (semantic i dag; kan byttes til
//! hovedmodellen `main` uten kodeendring, se docs/spike.md).
//!
//! Plassering: nedlastede modeller ligger i appens datamappe som `<id>.bin`.
//! Brukeren kan i tillegg peke på en egen (gjerne delt) modellmappe. Der leter
//! vi etter `<id>.bin` eller `<reponavn>/<fil>` slik Hugging Face lagrer dem.
//! Filer i egen mappe sjekkes mot SHA-256 første gang de brukes; resultatet
//! huskes så lenge størrelse og endringstid er de samme.

use std::collections::{BTreeMap, HashMap};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use super::error::{CoreError, CoreResult};
use super::types::{Kvalitet, Stil};

/// Den innebygde katalogen fra roten av repoet.
pub const MODELS_JSON: &str = include_str!("../../../../models.json");

/// Vertene appen noen gang laster ned fra, uansett hva `models.json` sier.
/// Hugging Face sender videre til CDN under `*.hf.co` (docs/spike.md).
pub const ALLOWED_HOSTS: &[&str] = &["huggingface.co", "*.hf.co"];

#[derive(Debug, Clone, Default, Deserialize, Serialize, PartialEq)]
pub struct VariantOptions {
    /// Tidsstempler per token. Trengs for verbatim, som ellers gir hele
    /// 30-sekundersvinduer som segmenter (docs/spike.md).
    #[serde(default)]
    pub token_timestamps: bool,
    /// Største segmentlengde i tegn (0 = whispers standard).
    #[serde(default)]
    pub max_len: u32,
    #[serde(default)]
    pub split_on_word: bool,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
pub struct ModelEntry {
    pub id: String,
    pub variant: String,
    #[serde(default)]
    pub style: Option<String>,
    pub size: String,
    pub quant: String,
    pub repo: String,
    pub revision: String,
    pub file: String,
    pub url: String,
    pub bytes: u64,
    pub sha256: String,
    #[serde(default)]
    pub note: Option<String>,
}

impl ModelEntry {
    /// Filnavnet appen lagrer modellen under.
    pub fn local_file_name(&self) -> String {
        format!("{}.bin", self.id)
    }

    /// Siste del av reponavnet, f.eks. `nb-whisper-small-verbatim`.
    pub fn repo_name(&self) -> &str {
        self.repo.rsplit('/').next().unwrap_or(&self.repo)
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct Catalog {
    pub schema_version: u32,
    #[serde(default)]
    pub license: String,
    #[serde(default)]
    pub license_holder: String,
    pub download_hosts: Vec<String>,
    pub default_quant: String,
    pub style_to_variant: HashMap<String, String>,
    pub quality_to_size: HashMap<String, String>,
    #[serde(default)]
    pub variant_options: HashMap<String, VariantOptions>,
    pub models: Vec<ModelEntry>,
}

fn invalid(reason: impl Into<String>) -> CoreError {
    CoreError::InvalidCatalog {
        reason: reason.into(),
    }
}

/// Om `host` passer et av mønstrene (`huggingface.co` eller `*.hf.co`).
pub fn host_matches(host: &str, patterns: &[impl AsRef<str>]) -> bool {
    let host = host.trim_end_matches('.').to_ascii_lowercase();
    patterns.iter().any(|p| {
        let p = p.as_ref().to_ascii_lowercase();
        match p.strip_prefix("*.") {
            Some(suffix) => host.len() > suffix.len() + 1 && host.ends_with(&format!(".{suffix}")),
            None => host == p,
        }
    })
}

/// Vert og skjema fra en URL. `None` hvis URL-en ikke kan tolkes.
pub fn url_host(url: &str) -> Option<(String, String)> {
    let uri: ureq::http::Uri = url.parse().ok()?;
    let scheme = uri.scheme_str()?.to_ascii_lowercase();
    let host = uri.host()?.to_ascii_lowercase();
    Some((scheme, host))
}

impl Catalog {
    pub fn builtin() -> CoreResult<Catalog> {
        Catalog::parse(MODELS_JSON)
    }

    pub fn parse(json: &str) -> CoreResult<Catalog> {
        let c: Catalog = serde_json::from_str(json).map_err(|e| invalid(format!("json: {e}")))?;
        c.validate()?;
        Ok(c)
    }

    fn validate(&self) -> CoreResult<()> {
        if self.schema_version != 1 {
            return Err(invalid("schema_version"));
        }
        if self.download_hosts.is_empty() {
            return Err(invalid("download_hosts is empty"));
        }
        for h in &self.download_hosts {
            if !ALLOWED_HOSTS.contains(&h.as_str()) {
                return Err(invalid(format!("download host not allowed: {h}")));
            }
        }
        let mut ids = std::collections::HashSet::new();
        for m in &self.models {
            if !ids.insert(m.id.as_str()) {
                return Err(invalid(format!("duplicate id {}", m.id)));
            }
            if m.id.is_empty()
                || !m
                    .id
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.')
            {
                return Err(invalid(format!("bad id {}", m.id)));
            }
            if m.sha256.len() != 64
                || !m
                    .sha256
                    .chars()
                    .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
            {
                return Err(invalid(format!("bad sha256 for {}", m.id)));
            }
            if m.bytes == 0 {
                return Err(invalid(format!("bytes is 0 for {}", m.id)));
            }
            let Some((scheme, host)) = url_host(&m.url) else {
                return Err(invalid(format!("bad url for {}", m.id)));
            };
            if scheme != "https" {
                return Err(invalid(format!("url must be https for {}", m.id)));
            }
            if !host_matches(&host, &self.download_hosts) {
                return Err(invalid(format!(
                    "url host not in download_hosts for {}",
                    m.id
                )));
            }
            if !m
                .url
                .ends_with(&format!("/{}/resolve/{}/{}", m.repo, m.revision, m.file))
            {
                return Err(invalid(format!(
                    "url does not match repo/revision/file for {}",
                    m.id
                )));
            }
            if !["verbatim", "semantic", "main"].contains(&m.variant.as_str()) {
                return Err(invalid(format!("unknown variant for {}", m.id)));
            }
        }
        for stil in [Stil::Lydrett, Stil::Tolket] {
            for kv in Kvalitet::ALL {
                self.select(stil, kv)?;
            }
        }
        // Lydrett skal alltid være verbatim (spesifikasjonen, regel 4).
        if self.style_to_variant.get("lydrett").map(String::as_str) != Some("verbatim") {
            return Err(invalid("lydrett must map to verbatim"));
        }
        Ok(())
    }

    pub fn get(&self, id: &str) -> Option<&ModelEntry> {
        self.models.iter().find(|m| m.id == id)
    }

    /// Modellen for en kombinasjon av stil og kvalitet, med standard kvantisering.
    pub fn select(&self, stil: Stil, kvalitet: Kvalitet) -> CoreResult<&ModelEntry> {
        let variant = self
            .style_to_variant
            .get(stil.key())
            .ok_or_else(|| invalid(format!("style_to_variant.{}", stil.key())))?;
        let size = self
            .quality_to_size
            .get(kvalitet.key())
            .ok_or_else(|| invalid(format!("quality_to_size.{}", kvalitet.key())))?;
        self.models
            .iter()
            .find(|m| &m.variant == variant && &m.size == size && m.quant == self.default_quant)
            .ok_or_else(|| invalid(format!("no model for {}/{}", stil.key(), kvalitet.key())))
    }

    pub fn options_for(&self, entry: &ModelEntry) -> VariantOptions {
        self.variant_options
            .get(&entry.variant)
            .cloned()
            .unwrap_or_default()
    }

    /// Alle seks kombinasjoner og modell-ID-en de bruker.
    pub fn choices(&self) -> Vec<Choice> {
        let mut v = Vec::new();
        for stil in [Stil::Lydrett, Stil::Tolket] {
            for kvalitet in Kvalitet::ALL {
                if let Ok(m) = self.select(stil, kvalitet) {
                    v.push(Choice {
                        stil,
                        kvalitet,
                        model_id: m.id.clone(),
                    });
                }
            }
        }
        v
    }
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Choice {
    pub stil: Stil,
    pub kvalitet: Kvalitet,
    pub model_id: String,
}

/// Hvor modellen ble funnet.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Location {
    /// Appens egen modellmappe (lastet ned og sjekket av appen).
    App,
    /// Brukerens egen modellmappe.
    Custom,
}

#[derive(Debug, Clone)]
pub struct ModelDirs {
    pub app_dir: PathBuf,
    pub custom_dir: Option<PathBuf>,
}

impl ModelDirs {
    pub fn app_path(&self, m: &ModelEntry) -> PathBuf {
        self.app_dir.join(m.local_file_name())
    }

    pub fn part_path(&self, m: &ModelEntry) -> PathBuf {
        self.app_dir.join(format!("{}.part", m.local_file_name()))
    }

    fn custom_candidates(&self, m: &ModelEntry) -> Vec<PathBuf> {
        match &self.custom_dir {
            Some(d) => vec![
                d.join(m.local_file_name()),
                d.join(m.repo_name()).join(&m.file),
            ],
            None => Vec::new(),
        }
    }

    /// Finner modellen. Egen mappe først, så appens mappe. Bare filer med
    /// riktig størrelse telles.
    pub fn locate(&self, m: &ModelEntry) -> Option<(PathBuf, Location)> {
        let ok = |p: &Path| {
            std::fs::metadata(p)
                .map(|md| md.is_file() && md.len() == m.bytes)
                .unwrap_or(false)
        };
        for p in self.custom_candidates(m) {
            if ok(&p) {
                return Some((p, Location::Custom));
            }
        }
        let p = self.app_path(m);
        if ok(&p) {
            return Some((p, Location::App));
        }
        None
    }

    /// Byte som allerede er lastet ned av en avbrutt nedlasting.
    pub fn partial_bytes(&self, m: &ModelEntry) -> u64 {
        std::fs::metadata(self.part_path(m))
            .map(|md| md.len())
            .unwrap_or(0)
    }
}

/// Status for én modell, til grensesnittet.
#[derive(Debug, Clone, Serialize)]
pub struct ModelStatus {
    pub id: String,
    pub variant: String,
    pub size: String,
    pub quant: String,
    pub repo: String,
    pub bytes: u64,
    pub installed: bool,
    pub location: Option<Location>,
    /// Byte fra en avbrutt nedlasting som kan gjenopptas.
    pub partial_bytes: u64,
}

pub fn status(m: &ModelEntry, dirs: &ModelDirs) -> ModelStatus {
    let loc = dirs.locate(m);
    ModelStatus {
        id: m.id.clone(),
        variant: m.variant.clone(),
        size: m.size.clone(),
        quant: m.quant.clone(),
        repo: m.repo.clone(),
        bytes: m.bytes,
        installed: loc.is_some(),
        location: loc.map(|l| l.1),
        partial_bytes: dirs.partial_bytes(m),
    }
}

/// Sletter en nedlastet modell (og en ev. halvferdig nedlasting) fra appens
/// mappe. Filer i egen modellmappe slettes ikke: den kan være delt.
pub fn delete(m: &ModelEntry, dirs: &ModelDirs) -> CoreResult<()> {
    let app = dirs.app_path(m);
    let part = dirs.part_path(m);
    let had_app = app.exists();
    let had_part = part.exists();
    if !had_app && !had_part {
        if dirs.locate(m).map(|l| l.1) == Some(Location::Custom) {
            return Err(CoreError::ModelInSharedFolder);
        }
        return Ok(());
    }
    if had_app {
        std::fs::remove_file(&app)?;
    }
    if had_part {
        std::fs::remove_file(&part)?;
    }
    Ok(())
}

/// SHA-256 av en fil, som små bokstaver. Avbrytes med `cancel`.
pub fn hash_file(path: &Path, cancel: &AtomicBool) -> CoreResult<String> {
    let mut f = std::fs::File::open(path)?;
    let mut h = Sha256::new();
    let mut buf = vec![0u8; 1 << 20];
    loop {
        if cancel.load(Ordering::Relaxed) {
            return Err(CoreError::Cancelled);
        }
        let n = f.read(&mut buf)?;
        if n == 0 {
            break;
        }
        h.update(&buf[..n]);
    }
    Ok(hex(&h.finalize()))
}

pub fn hex(bytes: &[u8]) -> String {
    const H: &[u8; 16] = b"0123456789abcdef";
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        s.push(H[(b >> 4) as usize] as char);
        s.push(H[(b & 15) as usize] as char);
    }
    s
}

/// Husker hvilke filer i egen modellmappe som er sjekket mot SHA-256.
/// Nøkkel: stien. Verdi: størrelse, endringstid og summen som stemte.
#[derive(Debug, Default, Serialize, Deserialize)]
pub struct VerifyCache {
    entries: BTreeMap<String, VerifiedFile>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
struct VerifiedFile {
    bytes: u64,
    mtime: u64,
    sha256: String,
}

fn fingerprint(path: &Path) -> Option<(u64, u64)> {
    let md = std::fs::metadata(path).ok()?;
    let mtime = md
        .modified()
        .ok()?
        .duration_since(std::time::UNIX_EPOCH)
        .ok()?
        .as_secs();
    Some((md.len(), mtime))
}

impl VerifyCache {
    pub fn load(path: &Path) -> VerifyCache {
        std::fs::read_to_string(path)
            .ok()
            .and_then(|s| serde_json::from_str(&s).ok())
            .unwrap_or_default()
    }

    pub fn save(&self, path: &Path) -> CoreResult<()> {
        let s = serde_json::to_string_pretty(self).map_err(|_| CoreError::Internal)?;
        if let Some(d) = path.parent() {
            std::fs::create_dir_all(d)?;
        }
        std::fs::write(path, s)?;
        Ok(())
    }

    pub fn is_verified(&self, path: &Path, m: &ModelEntry) -> bool {
        let Some((bytes, mtime)) = fingerprint(path) else {
            return false;
        };
        self.entries
            .get(&path.to_string_lossy().to_string())
            .map(|v| v.bytes == bytes && v.mtime == mtime && v.sha256 == m.sha256)
            .unwrap_or(false)
    }

    pub fn mark(&mut self, path: &Path, m: &ModelEntry) {
        if let Some((bytes, mtime)) = fingerprint(path) {
            self.entries.insert(
                path.to_string_lossy().to_string(),
                VerifiedFile {
                    bytes,
                    mtime,
                    sha256: m.sha256.clone(),
                },
            );
        }
    }
}

/// Sjekker en modell i egen mappe mot SHA-256 hvis det ikke er gjort før.
/// Modeller i appens mappe er sjekket ved nedlasting. En fil med feil sum i
/// egen mappe slettes ikke (den kan være delt), men brukes heller ikke.
pub fn ensure_verified(
    path: &Path,
    loc: Location,
    m: &ModelEntry,
    cache: &mut VerifyCache,
    cancel: &AtomicBool,
) -> CoreResult<bool> {
    if loc == Location::App || cache.is_verified(path, m) {
        return Ok(false);
    }
    let sum = hash_file(path, cancel)?;
    if sum != m.sha256 {
        return Err(CoreError::ChecksumMismatch);
    }
    cache.mark(path, m);
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmpdir(tag: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("lla-modeller-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    #[test]
    fn builtin_catalog_is_valid() {
        let c = Catalog::builtin().unwrap();
        assert_eq!(c.models.len(), 18);
        assert_eq!(c.choices().len(), 6);
    }

    #[test]
    fn selection_follows_spec() {
        let c = Catalog::builtin().unwrap();
        let m = c.select(Stil::Lydrett, Kvalitet::Anbefalt).unwrap();
        assert_eq!(m.id, "nb-whisper-medium-verbatim-q5_0");
        assert_eq!(m.repo, "NbAiLab/nb-whisper-medium-verbatim");
        let m = c.select(Stil::Tolket, Kvalitet::Rask).unwrap();
        assert_eq!(m.id, "nb-whisper-small-semantic-q5_0");
        let m = c.select(Stil::Tolket, Kvalitet::Best).unwrap();
        assert_eq!(m.size, "large");
        assert!(
            c.options_for(c.select(Stil::Lydrett, Kvalitet::Rask).unwrap())
                .token_timestamps
        );
        assert!(
            !c.options_for(c.select(Stil::Tolket, Kvalitet::Rask).unwrap())
                .token_timestamps
        );
    }

    #[test]
    fn tolket_can_switch_to_main_model_by_data_only() {
        let json = MODELS_JSON.replace(r#""tolket": "semantic""#, r#""tolket": "main""#);
        assert_ne!(json, MODELS_JSON);
        let c = Catalog::parse(&json).unwrap();
        assert_eq!(
            c.select(Stil::Tolket, Kvalitet::Anbefalt).unwrap().id,
            "nb-whisper-medium-q5_0"
        );
        // Lydrett er låst til verbatim.
        let bad = MODELS_JSON.replace(r#""lydrett": "verbatim""#, r#""lydrett": "main""#);
        assert!(Catalog::parse(&bad).is_err());
    }

    fn mutate(f: impl Fn(&mut serde_json::Value)) -> String {
        let mut v: serde_json::Value = serde_json::from_str(MODELS_JSON).unwrap();
        f(&mut v);
        serde_json::to_string(&v).unwrap()
    }

    #[test]
    fn bad_catalogs_are_rejected() {
        let cases: Vec<(&str, String)> = vec![
            (
                "kort sum",
                mutate(|v| v["models"][0]["sha256"] = "abc".into()),
            ),
            (
                "store bokstaver",
                mutate(|v| {
                    v["models"][0]["sha256"] =
                        "8982B4A4E365F3F64A60CA12ABB7382132E59B2A1040D52AB8DDD577948A5C96".into()
                }),
            ),
            (
                "ikke hex",
                mutate(|v| v["models"][0]["sha256"] = "z".repeat(64).into()),
            ),
            (
                "http",
                mutate(|v| {
                    let u = v["models"][0]["url"]
                        .as_str()
                        .unwrap()
                        .replace("https://", "http://");
                    v["models"][0]["url"] = u.into();
                }),
            ),
            (
                "annen vert",
                mutate(|v| {
                    let u = v["models"][0]["url"]
                        .as_str()
                        .unwrap()
                        .replace("huggingface.co", "example.com");
                    v["models"][0]["url"] = u.into();
                }),
            ),
            (
                "vert som ligner",
                mutate(|v| {
                    let u = v["models"][0]["url"]
                        .as_str()
                        .unwrap()
                        .replace("huggingface.co", "huggingface.co.evil.net");
                    v["models"][0]["url"] = u.into();
                }),
            ),
            (
                "ny vert i lista",
                mutate(|v| {
                    v["download_hosts"]
                        .as_array_mut()
                        .unwrap()
                        .push("example.com".into())
                }),
            ),
            ("null byte", mutate(|v| v["models"][0]["bytes"] = 0.into())),
            (
                "dobbel id",
                mutate(|v| v["models"][1]["id"] = v["models"][0]["id"].clone()),
            ),
            (
                "mangler kombinasjon",
                mutate(|v| v["quality_to_size"]["best"] = "huge".into()),
            ),
            (
                "url passer ikke fil",
                mutate(|v| v["models"][0]["file"] = "annen.bin".into()),
            ),
            ("schema", mutate(|v| v["schema_version"] = 2.into())),
        ];
        for (name, json) in cases {
            assert!(
                matches!(Catalog::parse(&json), Err(CoreError::InvalidCatalog { .. })),
                "{name}"
            );
        }
    }

    #[test]
    fn host_patterns() {
        let p = ["huggingface.co", "*.hf.co"];
        assert!(host_matches("huggingface.co", &p));
        assert!(host_matches("HuggingFace.co.", &p));
        assert!(host_matches("us.aws.cdn.hf.co", &p));
        assert!(host_matches("cas-bridge.xethub.hf.co", &p));
        assert!(!host_matches("hf.co", &p));
        assert!(!host_matches("evilhf.co", &p));
        assert!(!host_matches("huggingface.co.evil.net", &p));
        assert!(!host_matches("cdn-lfs.huggingface.co", &p));
    }

    fn fake_entry(bytes: u64, sha: &str) -> ModelEntry {
        ModelEntry {
            id: "test-model".into(),
            variant: "verbatim".into(),
            style: None,
            size: "small".into(),
            quant: "q5_0".into(),
            repo: "NbAiLab/nb-whisper-test".into(),
            revision: "abc".into(),
            file: "ggml-model-q5_0.bin".into(),
            url: "https://huggingface.co/NbAiLab/nb-whisper-test/resolve/abc/ggml-model-q5_0.bin"
                .into(),
            bytes,
            sha256: sha.into(),
            note: None,
        }
    }

    #[test]
    fn locate_prefers_custom_dir_and_checks_size() {
        let d = tmpdir("finn æøå");
        let app = d.join("app");
        let custom = d.join("Delt mappe ÆØÅ");
        std::fs::create_dir_all(&app).unwrap();
        std::fs::create_dir_all(custom.join("nb-whisper-test")).unwrap();
        let m = fake_entry(5, &"0".repeat(64));
        let dirs = ModelDirs {
            app_dir: app.clone(),
            custom_dir: Some(custom.clone()),
        };
        assert!(dirs.locate(&m).is_none());
        std::fs::write(dirs.app_path(&m), b"12345").unwrap();
        assert_eq!(dirs.locate(&m).unwrap().1, Location::App);
        // Hugging Face-oppsett i egen mappe: <repo>/<fil>.
        std::fs::write(custom.join("nb-whisper-test/ggml-model-q5_0.bin"), b"12345").unwrap();
        assert_eq!(dirs.locate(&m).unwrap().1, Location::Custom);
        // Feil størrelse telles ikke.
        std::fs::write(custom.join("nb-whisper-test/ggml-model-q5_0.bin"), b"123").unwrap();
        assert_eq!(dirs.locate(&m).unwrap().1, Location::App);
    }

    #[test]
    fn delete_only_touches_app_dir() {
        let d = tmpdir("slett");
        let app = d.join("app");
        let custom = d.join("delt");
        std::fs::create_dir_all(&app).unwrap();
        std::fs::create_dir_all(&custom).unwrap();
        let m = fake_entry(3, &"0".repeat(64));
        let dirs = ModelDirs {
            app_dir: app,
            custom_dir: Some(custom.clone()),
        };
        std::fs::write(custom.join("test-model.bin"), b"abc").unwrap();
        assert_eq!(delete(&m, &dirs), Err(CoreError::ModelInSharedFolder));
        assert!(custom.join("test-model.bin").exists());
        std::fs::write(dirs.app_path(&m), b"abc").unwrap();
        std::fs::write(dirs.part_path(&m), b"a").unwrap();
        delete(&m, &dirs).unwrap();
        assert!(!dirs.app_path(&m).exists());
        assert!(!dirs.part_path(&m).exists());
        assert!(custom.join("test-model.bin").exists());
    }

    #[test]
    fn custom_files_are_hashed_once_and_wrong_sum_is_rejected() {
        let d = tmpdir("sjekk");
        let p = d.join("m.bin");
        std::fs::write(&p, b"hei").unwrap();
        // En gyldig, men feil sum.
        let other = "a5e9a6a5e3ec1e9a4c1e0c2f8d6b0a9e0a4f2b0f8a1d2c3b4e5f60718293a4b5";
        let real = hash_file(&p, &AtomicBool::new(false)).unwrap();
        assert_eq!(real.len(), 64);
        assert_ne!(real, other);
        let mut cache = VerifyCache::default();
        let cancel = AtomicBool::new(false);
        let wrong = fake_entry(3, other);
        assert_eq!(
            ensure_verified(&p, Location::Custom, &wrong, &mut cache, &cancel),
            Err(CoreError::ChecksumMismatch)
        );
        assert!(p.exists(), "filer i egen mappe slettes ikke");
        let right = fake_entry(3, &real);
        assert_eq!(
            ensure_verified(&p, Location::Custom, &right, &mut cache, &cancel),
            Ok(true)
        );
        assert_eq!(
            ensure_verified(&p, Location::Custom, &right, &mut cache, &cancel),
            Ok(false)
        );
        // Lagres og leses.
        let cp = d.join("verified.json");
        cache.save(&cp).unwrap();
        let back = VerifyCache::load(&cp);
        assert!(back.is_verified(&p, &right));
        assert!(!back.is_verified(&p, &wrong));
    }

    #[test]
    fn sha256_known_vector() {
        let d = tmpdir("vektor");
        let p = d.join("abc");
        std::fs::write(&p, b"abc").unwrap();
        assert_eq!(
            hash_file(&p, &AtomicBool::new(false)).unwrap(),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
        assert_eq!(
            hash_file(&p, &AtomicBool::new(true)),
            Err(CoreError::Cancelled)
        );
    }
}
