Option Explicit

Dim shell
Dim fileSystem
Dim internalRoot
Dim projectRoot
Dim launcher
Dim command

Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")
internalRoot = fileSystem.GetParentFolderName(WScript.ScriptFullName)
projectRoot = fileSystem.GetParentFolderName(internalRoot)
launcher = fileSystem.BuildPath(internalRoot, "scripts\start_windows.ps1")
command = "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File """ & launcher & """"

shell.Run command, 1, False
