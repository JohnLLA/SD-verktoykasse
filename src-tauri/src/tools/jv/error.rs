// SPDX-License-Identifier: AGPL-3.0-or-later
//! Feil i jv-modulen. Meldingene har aldri filnavn eller innhold (regel 2).

use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum JvError {
    /// Signaturen på katalogen mangler eller stemmer ikke.
    CatalogSignature,
    /// Katalogen er signert, men innholdet er ugyldig.
    CatalogInvalid {
        reason: &'static str,
    },
    /// Verktøyet finnes ikke i katalogen for denne plattformen.
    NotForPlatform,
    /// SHA-256 eller størrelse på pakken stemmer ikke med katalogen.
    ChecksumMismatch,
    /// Arkivet har en sti, type eller symlenke som ikke er lov.
    UnsafeArchive {
        reason: &'static str,
    },
    /// Arkivet kunne ikke leses.
    ArchiveRead,
    /// `jv-package.json` mangler, er ugyldig eller passer ikke med katalogen.
    ManifestInvalid {
        reason: &'static str,
    },
    /// `codesign --verify` feilet (Mac).
    CodeSignature,
    /// Prøvekjøringen med `--version` feilet.
    TrialRunFailed,
    /// Nedlastingen feilet (detaljene ligger i Transkriberings feiltype).
    Download {
        kind: String,
    },
    Io {
        kind: String,
    },
}

pub type JvResult<T> = Result<T, JvError>;

impl fmt::Display for JvError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for JvError {}

impl From<std::io::Error> for JvError {
    fn from(e: std::io::Error) -> Self {
        JvError::Io {
            kind: format!("{:?}", e.kind()),
        }
    }
}
