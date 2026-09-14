; Tauri 默认清理 $LOCALAPPDATA\${BUNDLEID}，而 HearNotes 的 data
; 位于安装目录。只有用户勾选“删除应用数据”且不是软件更新时才清理。
; 旧版更新器可能在主程序退出后留下引擎进程。安装器在覆盖文件前再次
; 结束该进程树，使 1.0.2 等旧版本也能顺利升级到带修复的新版本。
!macro NSIS_HOOK_PREINSTALL
  ${If} $UpdateMode = 1
    nsExec::ExecToLog '"$SYSDIR\taskkill.exe" /IM hearnotes-engine.exe /T /F'
    Sleep 1000
  ${EndIf}
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ${If} $DeleteAppDataCheckboxState = 1
  ${AndIf} $UpdateMode <> 1
    SetShellVarContext current
    RmDir /r "$INSTDIR\data"
    RmDir "$INSTDIR"
  ${EndIf}
!macroend
