#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri_plugin_shell::ShellExt;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            let sidecar = app.shell().sidecar("meeting-scribe-engine")?;
            let (_rx, _child) = sidecar
                .args(["--no-browser"])
                .env("MEETINGSCRIBE_TAURI", "1")
                .spawn()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Meeting Scribe");
}
