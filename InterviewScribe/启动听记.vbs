Option Explicit
Dim fso, sh, base, runtime, script, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)
runtime = sh.ExpandEnvironmentStrings("%USERPROFILE%") & "\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
If Not fso.FileExists(runtime) Then
  runtime = sh.ExpandEnvironmentStrings("%USERPROFILE%") & "\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
End If
If Not fso.FileExists(runtime) Then
  MsgBox "Python runtime not found. Please see README.md.", 16, "Meeting Scribe"
  WScript.Quit 1
End If
script = base & "\launch.py"
cmd = Chr(34) & runtime & Chr(34) & " " & Chr(34) & script & Chr(34)
sh.Run cmd, 0, False
