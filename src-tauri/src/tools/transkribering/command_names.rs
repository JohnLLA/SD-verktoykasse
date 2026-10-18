// Kommandoene i Transkribering-pluginen. Delt mellom build.rs (som lager
// tillatelsene `transkribering:allow-<kommando>` og `transkribering:default`)
// og modulen, så listen bare står ett sted. Må stemme med generate_handler! i mod.rs.
pub const TRANSKRIBERING_COMMANDS: &[&str] = &[
    "check_system",
    "list_models",
    "download_model",
    "delete_model",
    "set_model_dir",
    "transcribe",
    "cancel",
    "suggest_export_path",
    "export",
];
