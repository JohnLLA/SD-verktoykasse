// SPDX-License-Identifier: AGPL-3.0-or-later
//! Feil i jv-modulen. De går til grensesnittet som en kode med noen få, trygge
//! felt (`{"code": "checksum_mismatch"}`), og grensesnittet lager den norske
//! teksten. Meldingene har aldri filnavn, stier eller innhold (regel 2).

use std::fmt;

use serde::Serialize;

use crate::tools::transkribering::error::CoreError;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "code", rename_all = "snake_case")]
pub enum JvError {
    /// Signaturen på katalogen mangler eller stemmer ikke.
    CatalogSignature,
    /// Katalogen er signert, men innholdet er ugyldig.
    CatalogInvalid {
        reason: &'static str,
    },
    /// Katalogen er eldre enn den appen allerede har kontrollert.
    CatalogOutdated,
    /// Ingen kontrollert katalog ennå (aldri hentet, og nettet er nede).
    CatalogMissing,
    /// Appen er bygget uten offentlig katalognøkkel (plassholderen i catalog.rs).
    CatalogKeyMissing,
    /// Ukjent verktøy-id.
    UnknownTool,
    /// Verktøyet finnes ikke i katalogen for denne plattformen («Kommer for Windows»).
    NotForPlatform,
    /// Pakken krever en nyere versjon av appen.
    NeedsNewerApp {
        min_app_version: String,
    },
    /// Pakken krever en nyere macOS.
    NeedsNewerOs {
        min_os: String,
    },
    /// Verktøyet er ikke installert.
    NotInstalled,
    /// Verktøyet lastes ned, kjører eller fjernes allerede.
    Busy,
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
    /// Verktøyet kunne ikke startes i sandkassen (Mac): `sandbox-exec` mangler
    /// eller avviste profilen. Da kjøres det ikke («Verktøyet kunne ikke startes
    /// i beskyttet modus.»).
    SandboxFailed,
    /// Verktøyet avsluttet med en annen kode enn 0 (1: brukerfeil, 2: intern feil).
    /// Den norske meldingen fra verktøyet sendes ved siden av, aldri i loggen.
    ToolFailed {
        exit_code: Option<i32>,
    },
    /// Verktøyet ga kode 0, men rapporten på stdout var ikke gyldig JSON.
    ReportInvalid,
    /// Argumentene passer ikke med hvitelisten for verktøyet.
    InvalidArgs {
        reason: &'static str,
    },
    /// Nedlastingen feilet. `cause` er feilen fra nedlastingskoden i Transkribering.
    Download {
        cause: CoreError,
    },
    /// Brukeren avbrøt.
    Cancelled,
    Io {
        kind: String,
    },
    /// Intern feil, også fanget panikk.
    Internal,
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

impl From<CoreError> for JvError {
    fn from(e: CoreError) -> Self {
        match e {
            CoreError::ChecksumMismatch | CoreError::SizeMismatch => JvError::ChecksumMismatch,
            CoreError::Cancelled => JvError::Cancelled,
            other => JvError::Download { cause: other },
        }
    }
}
