# Changelog / 更新日志

## 1.1.4

- Fixed desktop exports by passing the selected format, filename, and content through Tauri IPC to the native Windows Save As dialog. / 修复桌面版导出，将格式、文件名和内容正确传递到 Tauri，并使用 Windows 原生“另存为”窗口保存。
- Localized result warnings, review flags, and validation errors in Chinese, Japanese, and English. / 为结果警告、待核标记和校验错误补充中日英翻译。

## 1.1.3

- Fixed desktop exports by opening the native Windows Save As dialog and writing TXT, Markdown, SRT, or JSON to the user-selected path. / 修复桌面版导出，使用 Windows 原生“另存为”窗口，将 TXT、Markdown、SRT 或 JSON 保存到用户选择的位置。
- Reworked the Japanese interface copy for natural, consistent desktop-app wording. / 全面润色日语界面文案，使表达更自然并统一桌面软件用语。
- Localized live transcription stages, GPU fallback notices, recording-language names, and model-update stages according to the selected display language. / 转写阶段、GPU 回退提示、录音语言名称和模型更新阶段现在会随界面语言显示。
- Standardized untouched speaker labels as `Speaker A`, `Speaker B`, and `Needs review` across all interface languages while preserving names entered by the user. / 所有界面的默认说话人名称统一为 `Speaker A`、`Speaker B` 和 `Needs review`，用户自行输入的姓名保持不变。
- Preserved unsaved edits when switching the interface language and retained compatibility with progress data and speaker labels created by older versions. / 切换界面语言时保留未保存的修改，并兼容旧版本生成的进度数据和默认说话人名称。

## 1.1.2

- Published a uniquely versioned update package to verify the new in-app download progress dialog from 1.1.1. / 发布独立版本的更新包，用于从 1.1.1 实际验证新版应用内下载进度弹窗。
- Retained the signed update flow and the two-stage background engine cleanup before installation. / 保留签名更新流程及安装前的两阶段后台引擎清理。
- Refreshed release metadata and architecture documentation for update-path verification. / 更新发布元数据和系统架构文档中的更新路径验证说明。

## 1.1.1

- Added an in-app update progress dialog with percentage, downloaded size, total size, transfer speed, signature verification, and installation stages. / 增加软件更新进度弹窗，显示百分比、已下载大小、总大小、下载速度、签名验证和安装阶段。
- Fixed Windows update installation failures by stopping the transcription engine process tree and waiting for file handles to be released before launching NSIS; the installer also performs a compatibility cleanup for updates started by older versions. / 修复 Windows 更新安装失败：启动 NSIS 前结束转写引擎进程树并等待文件句柄释放；安装器也会兼容清理由旧版本发起更新时残留的进程。
- Updated the system architecture documentation and multilingual interface text. / 更新系统架构文档和多语言界面文字。

## 1.1.0

- Switched the desktop UI to bundled Tauri assets so signed application updates work without using the Python HTTP page as the window origin. / 桌面界面改为使用 Tauri 内置资源，使签名软件更新不再依赖 Python HTTP 页面作为窗口来源。
- Restricted the local transcription API to approved Tauri origins and added explicit CORS handling. / 限制本机转写接口仅接受获准的 Tauri 页面来源，并补充明确的跨域处理。
- Updated the release metadata and architecture documentation for the 1.0.2 to 1.1 update test. / 更新发布元数据和系统架构文档，用于验证从 1.0.2 更新至 1.1。

## 1.0.2

- Added startup and manual application update checks with signed update installation. / 增加启动时与手动的软件更新检查，并支持签名验证后安装更新。
- Improved model installation guidance and update notifications. / 改进模型安装引导和更新提醒。
- Fixed model runtime loading and uninstaller data cleanup issues. / 修复模型运行库加载与卸载残留数据问题。
- Updated the bilingual README, screenshots, icons, and architecture documentation. / 更新中英文说明、截图、图标和系统架构文档。

## 1.0.1 (development / 开发版)

- Added the Tauri 2 Windows desktop packaging scaffold. / 增加 Tauri 2 Windows 桌面包装工程骨架。
- Added a PyInstaller build script for the Python transcription sidecar. / 增加 Python 转写引擎 Sidecar 构建脚本。
- Added the Tauri updater configuration and signature verification entry point. / 增加 Tauri 更新配置和签名验证入口。
- Added hybrid, full-GPU, and CPU processing modes plus quality profiles. / 增加混合加速、全部 GPU、仅 CPU 和精度档位。
- Fixed `WinError 5` when progress files are written concurrently on Windows. / 修复 Windows 并发写入进度文件时的 `WinError 5`。
- Added CUDA speaker diarization with automatic CPU fallback. / 增加 CUDA 说话人分离和自动 CPU 回退。
- Prepared the project for public development and added an AI-generation disclosure. / 为公开开发做准备，并增加 AI 生成声明。

Each release records user-visible changes, fixes, and known limitations here.

每次发布均在此记录用户可见的变化、修复和已知限制。
