//! LLAs verktøykasse: skallet. Selve verktøyene ligger i `tools/`.

pub mod tools;

/// Panikkmeldinger kan inneholde data fra der panikken skjedde. Vi skriver
/// bare hvor i koden den skjedde, aldri meldingen (regel 2: ingen tekst eller
/// filnavn i logger).
fn install_panic_hook() {
    std::panic::set_hook(Box::new(|info| {
        let loc = info
            .location()
            .map(|l| format!("{}:{}", l.file(), l.line()))
            .unwrap_or_default();
        eprintln!("panic at {loc}");
    }));
}

pub fn run() {
    install_panic_hook();
    let builder = tauri::Builder::default().plugin(tauri_plugin_store::Builder::new().build());
    let builder = tools::register(builder);
    if builder.run(tauri::generate_context!()).is_err() {
        eprintln!("the app failed to start");
        std::process::exit(1);
    }
}
