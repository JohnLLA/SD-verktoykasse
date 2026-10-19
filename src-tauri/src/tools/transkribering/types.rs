//! Felles typer som går mellom kjernen og grensesnittet.
//!
//! Verdiene serialiseres som de norske ordene fra spesifikasjonen
//! (`"bokmål"`, `"nynorsk"`, `"lydrett"`, `"tolket"`, `"rask"`, `"anbefalt"`,
//! `"best"`). Det er identifikatorer, ikke visningstekst: visningstekstene
//! ligger i språkfilen i grensesnittet.

use serde::{Deserialize, Serialize};

/// Målform. Styrer Whisper-språket: `no` for bokmål, `nn` for nynorsk.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Malform {
    #[serde(rename = "bokmål")]
    Bokmal,
    #[serde(rename = "nynorsk")]
    Nynorsk,
}

impl Malform {
    /// Språkkoden whisper.cpp får.
    pub fn whisper_language(self) -> &'static str {
        match self {
            Malform::Bokmal => "no",
            Malform::Nynorsk => "nn",
        }
    }

    /// Ordet som brukes i filnavnet `<lydfil>.<målform>.<stil>.<ending>`.
    /// `bokmal` uten å (John Inges beslutning, se spesifikasjonen).
    pub fn file_word(self) -> &'static str {
        match self {
            Malform::Bokmal => "bokmal",
            Malform::Nynorsk => "nynorsk",
        }
    }
}

/// Stil. Lydrett = verbatim-modell. Tolket = hovedmodellen `nb-whisper-<størrelse>`
/// (`style_to_variant.tolket = "main"` i `models.json`, docs/kvalitet.md).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Stil {
    Lydrett,
    Tolket,
}

impl Stil {
    pub fn key(self) -> &'static str {
        match self {
            Stil::Lydrett => "lydrett",
            Stil::Tolket => "tolket",
        }
    }
}

/// Kvalitet. Styrer modellstørrelsen via `quality_to_size` i `models.json`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Kvalitet {
    Rask,
    Anbefalt,
    Best,
}

impl Kvalitet {
    pub fn key(self) -> &'static str {
        match self {
            Kvalitet::Rask => "rask",
            Kvalitet::Anbefalt => "anbefalt",
            Kvalitet::Best => "best",
        }
    }

    pub const ALL: [Kvalitet; 3] = [Kvalitet::Rask, Kvalitet::Anbefalt, Kvalitet::Best];
}

/// Søkestrategi i whisper. Beam 5 er standard (avgjort etter steg 3,
/// docs/kvalitet.md); greedy («Raskere») kan velges i innstillingene.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum Decoding {
    #[default]
    Beam5,
    Greedy,
}

/// Ett ferdig segment. Tider i millisekunder fra starten av filen.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Segment {
    pub start_ms: u64,
    pub end_ms: u64,
    /// Teksten slik modellen ga den, bare med mellomrom fjernet i endene.
    /// Lydrett tekst etterbehandles ikke (regel 4).
    pub text: String,
}
