# 更新日志

## 1.0.1（当前开发版）

- 增加 Tauri 2 Windows 桌面包装工程骨架。
- 增加 Python 转写引擎 Sidecar 构建脚本。
- 增加 Tauri Updater 配置和更新签名校验入口。
- 增加“智能加速／全部使用 GPU／仅 CPU”和速度精度档位。
- 修复 Windows 并发写入进度文件时的 `WinError 5`。
- 说话人分离支持 CUDA 版 sherpa-onnx，并在失败时回退 CPU。

## 发布说明约定

每次发布使用一个新的 SemVer 版本号，并在本文件记录用户可见的变化、修复和已知限制。构建工作流会把同样的内容写入 GitHub 发布仓库的更新清单。
