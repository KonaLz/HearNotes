# Release and Update Guide / 发布与更新说明

After the repository is made public, `KonaLz/meeting-scribe-tauri` will contain the source code and signed Windows release artifacts. Users will be able to download public updates without a GitHub PAT.

仓库正式公开后，`KonaLz/meeting-scribe-tauri` 将同时保存源代码和经过签名的 Windows 发布文件。用户下载公开更新时不需要 GitHub PAT。

## Initial setup / 首次配置

1. Install Node.js, Rust, Tauri CLI, Python 3.11, and PyInstaller. / 安装 Node.js、Rust、Tauri CLI、Python 3.11 和 PyInstaller。
2. Run `npm install`. / 执行 `npm install`。
3. Generate an updater signing key with `tauri signer generate`. / 使用 `tauri signer generate` 生成更新签名密钥。
4. Store the private key and password in the GitHub Actions secrets `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`. / 将私钥和密码保存到同名 GitHub Actions Secrets。
5. Replace `REPLACE_WITH_TAURI_PUBLIC_KEY` in `src-tauri/tauri.conf.json` with the generated public key. / 将生成的公钥写入 Tauri 配置中的占位符。

The signing private key must never be committed. The application contains only the public verification key.

签名私钥不得提交到仓库；应用程序内只保存用于验证的公钥。

## Release flow / 发布流程

```text
Update code and CHANGELOG.md / 修改代码和更新日志
    ↓
Create and push a version tag / 创建并推送版本标签
    ↓
GitHub Actions builds Windows NSIS/MSI installers
    ↓
Signed artifacts and latest.json are attached to the public GitHub Release
    ↓
HearNotes checks latest.json and asks before installing the update
```

Example / 示例：

```powershell
git tag v1.0.2
git push origin v1.0.2
```

## Models / 模型

Speech and speaker models are downloaded from the upstream sources listed in the main README. They are excluded from Git releases unless a future release explicitly states otherwise. Review every upstream model license before redistributing model files.

语音识别和说话人模型从主 README 所列的原始来源下载。除非未来的发布说明明确指出，否则模型文件不包含在 GitHub Release 中。重新分发模型前必须检查各模型的许可证。

## AI disclosure / AI 生成声明

The release configuration and documentation were created with AI assistance and must be reviewed before production publishing.

发布配置和说明文档由 AI 辅助生成，正式发布前应由维护者检查。
