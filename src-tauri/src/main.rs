#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::{Arc, Mutex};
use tauri::RunEvent;
use tauri_plugin_shell::{process::CommandChild, ShellExt};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

/// 只结束 HearNotes 自己启动的 sidecar 进程树。
/// Windows 下使用 /T，确保正在转写的 worker 子进程也一起退出。
fn stop_sidecar(child: CommandChild) {
    let pid = child.pid();

    #[cfg(target_os = "windows")]
    {
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let _ = std::process::Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
    }

    #[cfg(not(target_os = "windows"))]
    {
        let _ = child.kill();
    }
}

fn main() {
    // 保存进程句柄，以便用户关闭窗口、退出程序或安装更新时统一清理。
    let sidecar_child = Arc::new(Mutex::new(None::<CommandChild>));
    let setup_child = Arc::clone(&sidecar_child);

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(move |app| {
            let sidecar = app.shell().sidecar("hearnotes-engine")?;
            let (_rx, child) = sidecar
                .args(["--no-browser"])
                .env("HEARNOTES_TAURI", "1")
                .spawn()?;
            *setup_child.lock().expect("sidecar lock poisoned") = Some(child);
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building HearNotes");

    app.run(move |_app_handle, event| {
        if matches!(event, RunEvent::Exit) {
            if let Some(child) = sidecar_child.lock().expect("sidecar lock poisoned").take() {
                stop_sidecar(child);
            }
        }
    });
}
