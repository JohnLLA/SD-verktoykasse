// Kommandoene i jv-pluginen. Delt mellom build.rs (som lager tillatelsene
// `jv:allow-<kommando>` og `jv:default`) og modulen, så listen bare står ett
// sted. Må stemme med generate_handler! i jv/mod.rs.
pub const JV_COMMANDS: &[&str] = &[
    "jv_catalog",
    "jv_installed",
    "jv_install",
    "jv_remove",
    "jv_run",
    "jv_cancel",
];
