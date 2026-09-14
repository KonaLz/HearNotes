#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use serde::Serialize;
use serde_json::{json, Value};
use tauri::{AppHandle, RunEvent, State};
use tauri_plugin_shell::{process::CommandChild, ShellExt};
use tauri_plugin_updater::UpdaterExt;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;
#[cfg(target_os = "windows")]
use windows_sys::Win32::{
    Foundation::{CloseHandle, WAIT_OBJECT_0},
    System::Threading::{OpenProcess, WaitForSingleObject},
};

#[derive(Clone)]
struct AppState {
    sidecar: Arc<Mutex<Option<CommandChild>>>,
    update: Arc<Mutex<UpdateProgress>>,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct UpdateProgress {
    phase: String,
    downloaded: u64,
    total: Option<u64>,
    bytes_per_second: u64,
    percent: Option<f64>,
    error: Option<String>,
}

impl Default for UpdateProgress {
    fn default() -> Self {
        Self {
            phase: "idle".into(),
            downloaded: 0,
            total: None,
            bytes_per_second: 0,
            percent: None,
            error: None,
        }
    }
}

fn set_update_progress(target: &Arc<Mutex<UpdateProgress>>, value: UpdateProgress) {
    if let Ok(mut progress) = target.lock() {
        *progress = value;
    }
}

/// 只结束 HearNotes 自己启动的 sidecar 进程树。
/// Windows 下使用 /T，确保正在转写的 worker 子进程也一起退出。
fn stop_sidecar(child: CommandChild) -> Result<(), String> {
    let pid = child.pid();

    #[cfg(target_os = "windows")]
    {
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        const PROCESS_SYNCHRONIZE: u32 = 0x0010_0000;
        let _ = std::process::Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();

        // 更新器会直接结束主进程，不会触发普通窗口退出流程，因此在安装前
        // 明确等待 sidecar 释放文件句柄，避免 NSIS 无法覆盖引擎文件。
        let handle = unsafe { OpenProcess(PROCESS_SYNCHRONIZE, 0, pid) };
        if !handle.is_null() {
            let result = unsafe { WaitForSingleObject(handle, 5_000) };
            unsafe { CloseHandle(handle) };
            if result != WAIT_OBJECT_0 {
                return Err("HearNotes engine did not exit before installation.".into());
            }
        }
        std::thread::sleep(Duration::from_millis(500));
        Ok(())
    }

    #[cfg(not(target_os = "windows"))]
    {
        child.kill().map_err(|error| error.to_string())
    }
}

#[tauri::command]
fn get_app_update_progress(state: State<'_, AppState>) -> UpdateProgress {
    state
        .update
        .lock()
        .map(|progress| progress.clone())
        .unwrap_or_default()
}

/// 联网读取公开发布页的 latest.json，并把可显示的信息交给前端。
#[tauri::command]
async fn check_app_update(app: AppHandle) -> Result<Value, String> {
    let update = app
        .updater()
        .map_err(|error| error.to_string())?
        .check()
        .await
        .map_err(|error| error.to_string())?;

    Ok(match update {
        Some(update) => json!({
            "available": true,
            "currentVersion": update.current_version,
            "version": update.version,
            "notes": update.body.unwrap_or_default(),
            "date": update.date.map(|value| value.to_string()),
        }),
        None => json!({ "available": false }),
    })
}

/// 安装前会再次检查版本，下载完成后由 Tauri 校验签名并启动安装程序。
#[tauri::command]
async fn install_app_update(app: AppHandle, state: State<'_, AppState>) -> Result<(), String> {
    let progress = Arc::clone(&state.update);
    set_update_progress(
        &progress,
        UpdateProgress { phase: "checking".into(), ..Default::default() },
    );

    let update = app
        .updater()
        .map_err(|error| error.to_string())?
        .check()
        .await
        .map_err(|error| error.to_string())?
        .ok_or_else(|| "No application update is available.".to_string())?;

    let download_progress = Arc::clone(&progress);
    let verify_progress = Arc::clone(&progress);
    let started = Instant::now();
    let mut downloaded = 0_u64;
    let bytes = update
        .download(
            move |chunk_length, total| {
                downloaded += chunk_length as u64;
                let elapsed = started.elapsed().as_secs_f64().max(0.001);
                let percent = total
                    .filter(|value| *value > 0)
                    .map(|value| downloaded as f64 * 100.0 / value as f64);
                set_update_progress(
                    &download_progress,
                    UpdateProgress {
                        phase: "downloading".into(),
                        downloaded,
                        total,
                        bytes_per_second: (downloaded as f64 / elapsed) as u64,
                        percent,
                        error: None,
                    },
                );
            },
            move || {
                set_update_progress(
                    &verify_progress,
                    UpdateProgress { phase: "verifying".into(), ..Default::default() },
                );
            },
        )
        .await
        .map_err(|error| {
            let message = error.to_string();
            set_update_progress(
                &progress,
                UpdateProgress { phase: "error".into(), error: Some(message.clone()), ..Default::default() },
            );
            message
        })?;

    set_update_progress(
        &progress,
        UpdateProgress { phase: "stopping".into(), ..Default::default() },
    );
    let child = state
        .sidecar
        .lock()
        .map_err(|_| "HearNotes engine state is unavailable.".to_string())?
        .take();
    if let Some(child) = child {
        if let Err(message) = stop_sidecar(child) {
            set_update_progress(
                &progress,
                UpdateProgress { phase: "error".into(), error: Some(message.clone()), ..Default::default() },
            );
            return Err(message);
        }
    }

    set_update_progress(
        &progress,
        UpdateProgress { phase: "installing".into(), ..Default::default() },
    );
    update.install(bytes).map_err(|error| error.to_string())
}

fn main() {
    // 保存进程句柄，以便用户关闭窗口、退出程序或安装更新时统一清理。
    let state = AppState {
        sidecar: Arc::new(Mutex::new(None::<CommandChild>)),
        update: Arc::new(Mutex::new(UpdateProgress::default())),
    };
    let run_state = state.clone();
    let setup_state = state.clone();

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(state)
        .invoke_handler(tauri::generate_handler![
            check_app_update,
            get_app_update_progress,
            install_app_update
        ])
        .setup(move |app| {
            let sidecar = app.shell().sidecar("hearnotes-engine")?;
            let (_rx, child) = sidecar
                .args(["--no-browser"])
                .env("HEARNOTES_TAURI", "1")
                .spawn()?;
            *setup_state.sidecar.lock().expect("sidecar lock poisoned") = Some(child);
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building HearNotes");

    app.run(move |_app_handle, event| {
        if matches!(event, RunEvent::Exit) {
            if let Some(child) = run_state.sidecar.lock().expect("sidecar lock poisoned").take() {
                let _ = stop_sidecar(child);
            }
        }
    });
}
