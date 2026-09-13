# 发布与更新说明

源码仓库：`KonaLz/meeting-scribe-tauri`（私有）。

发布仓库：`KonaLz/meeting-scribe-releases`（只存安装包、`.sig` 和 `latest.json`，不存源码、模型、录音或密钥）。

## 首次配置

1. 安装 Node.js、Rust、Tauri CLI，并执行 `npm install`。
2. 使用 `tauri signer generate` 生成 Tauri 更新签名密钥。
3. 将私钥和密码保存到 GitHub Actions Secrets：
   - `TAURI_SIGNING_PRIVATE_KEY`
   - `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`
4. 将生成的公钥替换 `src-tauri/tauri.conf.json` 中的 `REPLACE_WITH_TAURI_PUBLIC_KEY`。
5. 确认 `scripts/build-engine.ps1` 能在干净 Windows 环境构建 Sidecar。

## 发布流程

```text
修改代码和 CHANGELOG.md
    ↓
git tag v1.0.2
git push origin v1.0.2
    ↓
GitHub Actions 构建 Windows NSIS/MSI
    ↓
上传安装包与签名到发布仓库
    ↓
生成 latest.json
```

注意：公开发布仓库只用于让最终用户无需 PAT 下载签名安装包。私有源码仓库仍然保存完整源代码和工作流。
