; Tauri 默认清理 $LOCALAPPDATA\${BUNDLEID}，而 HearNotes 的 data
; 位于安装目录。只有用户勾选“删除应用数据”且不是软件更新时才清理。
!macro NSIS_HOOK_POSTUNINSTALL
  ${If} $DeleteAppDataCheckboxState = 1
  ${AndIf} $UpdateMode <> 1
    SetShellVarContext current
    RmDir /r "$INSTDIR\data"
    RmDir "$INSTDIR"
  ${EndIf}
!macroend
