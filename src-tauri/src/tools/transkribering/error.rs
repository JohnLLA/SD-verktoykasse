//! Feiltyper for Transkribering.
//!
//! Feilene går til grensesnittet som en kode med noen få, trygge felt
//! (`{"code": "unsupported_format", "format": "webm"}`). Grensesnittet lager
//! den norske teksten fra språkfilen. Ingen feil inneholder filnavn, stier
//! eller transkribert tekst (regel 2), og `Display` er bare for utviklere.

use serde::Serialize;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "code", rename_all = "snake_case")]
pub enum CoreError {
    /// Filen finnes ikke eller kan ikke åpnes.
    FileNotFound,
    /// Formatet eller kodeken støttes ikke. `format` er et kort, kjent navn
    /// (for eksempel `webm`, `opus`, `caf`, `aiff`, `alac`) eller filendelsen.
    UnsupportedFormat { format: String },
    /// Filen har ikke noe lydspor vi kan lese.
    NoAudioTrack,
    /// Filen er lest, men inneholdt ingen lyd.
    EmptyAudio,
    /// Lyden kunne ikke dekodes (ødelagt fil e.l.).
    DecodeFailed,
    /// Ukjent modell-ID.
    UnknownModel,
    /// Modellen er ikke lastet ned (eller finnes ikke i modellmappen).
    ModelMissing { model_id: String },
    /// Modellfilen kunne ikke lastes av whisper.cpp.
    ModelLoadFailed,
    /// Modellen ligger i en egen (delt) modellmappe og slettes ikke av appen.
    ModelInSharedFolder,
    /// `models.json` er ugyldig. `reason` er en kort teknisk forklaring.
    InvalidCatalog { reason: String },
    /// Nedlastingen ble sendt til en vert som ikke står på listen.
    HostNotAllowed { host: String },
    /// Serveren svarte med en uventet HTTP-status.
    HttpStatus { status: u16 },
    /// Nettverksfeil (ingen forbindelse, tidsavbrudd, TLS).
    Network,
    /// Den nedlastede filen har feil SHA-256 og er slettet.
    ChecksumMismatch,
    /// Den nedlastede filen har feil størrelse.
    SizeMismatch,
    /// Det er ikke nok plass på disken.
    DiskFull,
    /// Prosessoren mangler instruksjoner som whisper.cpp er bygget for (AVX2 o.l.).
    CpuUnsupported { missing: Vec<String> },
    /// En annen transkribering kjører allerede.
    Busy,
    /// Den samme modellen lastes allerede ned.
    AlreadyDownloading,
    /// Jobben ble avbrutt av brukeren.
    Cancelled,
    /// whisper.cpp returnerte en feil med denne koden.
    Whisper { whisper_code: i32 },
    /// Filen finnes fra før. Grensesnittet må spørre og kalle på nytt med `overwrite`.
    FileExists,
    /// Mappen finnes ikke eller er ikke en mappe.
    NotADirectory,
    /// Stien kan ikke brukes (for eksempel ikke gyldig UTF-8 for whisper.cpp).
    InvalidPath,
    /// Ingen tilgang til filen eller mappen.
    PermissionDenied,
    /// Annen inn/ut-feil. `kind` er `std::io::ErrorKind` som tekst, uten sti.
    Io { kind: String },
    /// Intern feil, også fanget panikk. Skal ikke skje.
    Internal,
}

impl CoreError {
    pub fn from_io(e: &std::io::Error) -> Self {
        use std::io::ErrorKind as K;
        match e.kind() {
            K::NotFound => CoreError::FileNotFound,
            K::PermissionDenied => CoreError::PermissionDenied,
            K::AlreadyExists => CoreError::FileExists,
            K::StorageFull => CoreError::DiskFull,
            K::NotADirectory => CoreError::NotADirectory,
            k => CoreError::Io {
                kind: format!("{k:?}"),
            },
        }
    }
}

impl From<std::io::Error> for CoreError {
    fn from(e: std::io::Error) -> Self {
        CoreError::from_io(&e)
    }
}

impl std::fmt::Display for CoreError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // Bare koden og de trygge feltene. Aldri sti eller tekst.
        match serde_json::to_string(self) {
            Ok(s) => f.write_str(&s),
            Err(_) => f.write_str("{\"code\":\"internal\"}"),
        }
    }
}

impl std::error::Error for CoreError {}

pub type CoreResult<T> = Result<T, CoreError>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn serializes_as_code_with_fields() {
        let e = CoreError::UnsupportedFormat {
            format: "webm".into(),
        };
        assert_eq!(
            serde_json::to_string(&e).unwrap(),
            r#"{"code":"unsupported_format","format":"webm"}"#
        );
        assert_eq!(
            serde_json::to_string(&CoreError::Busy).unwrap(),
            r#"{"code":"busy"}"#
        );
    }

    #[test]
    fn io_error_never_carries_path() {
        let e = std::io::Error::other("/Users/kilde/hemmelig intervju.mp3");
        let c = CoreError::from_io(&e);
        assert!(!c.to_string().contains("hemmelig"));
    }
}
