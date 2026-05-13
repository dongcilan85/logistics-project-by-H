Set WshShell = CreateObject("WScript.Shell")
strScriptPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.Run chr(34) & strScriptPath & "\run_agent_silent.bat" & Chr(34), 0
Set WshShell = Nothing
