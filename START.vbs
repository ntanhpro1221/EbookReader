Option Explicit

Dim shell
Dim fileSystem
Dim projectRoot
Dim launcher
Dim command

Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")
projectRoot = fileSystem.GetParentFolderName(WScript.ScriptFullName)
launcher = fileSystem.BuildPath(projectRoot, "_internal\scripts\start_windows.ps1")
command = "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File """ & launcher & """"

shell.Run command, 0, False
