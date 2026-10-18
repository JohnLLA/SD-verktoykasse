include!("src/tools/transkribering/command_names.rs");

fn main() {
    println!("cargo:rerun-if-changed=src/tools/transkribering/command_names.rs");
    println!("cargo:rerun-if-changed=../models.json");
    let attrs = tauri_build::Attributes::new().plugin(
        "transkribering",
        tauri_build::InlinedPlugin::new()
            .commands(TRANSKRIBERING_COMMANDS)
            .default_permission(tauri_build::DefaultPermissionRule::AllowAllCommands),
    );
    if let Err(e) = tauri_build::try_build(attrs) {
        println!("cargo:warning=tauri-build failed: {e:#}");
        std::process::exit(1);
    }
}
