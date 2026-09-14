# Changelog / 更新日志

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
