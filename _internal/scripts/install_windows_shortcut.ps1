param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = "Stop"

$AppName = "E Book Reader"
$Launcher = Join-Path $ProjectRoot "$AppName.vbs"
$Icon = Join-Path $ProjectRoot "_internal\e_book_reader\assets\e_book_reader.ico"
$ProgramsRoot = [Environment]::GetFolderPath([Environment+SpecialFolder]::Programs)
$ShortcutPath = Join-Path $ProgramsRoot "$AppName.lnk"
$Wscript = Join-Path $env:SystemRoot "System32\wscript.exe"
$Arguments = "`"$Launcher`""
$IconLocation = "$Icon,0"

if (-not (Test-Path -LiteralPath $Launcher -PathType Leaf)) {
    throw "Không tìm thấy launcher: $Launcher"
}
if (-not (Test-Path -LiteralPath $Icon -PathType Leaf)) {
    throw "Không tìm thấy icon: $Icon"
}
if ([string]::IsNullOrWhiteSpace($ProgramsRoot)) {
    throw "Không xác định được thư mục Start Menu của người dùng."
}

New-Item -ItemType Directory -Force -Path $ProgramsRoot | Out-Null
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$NeedsSave = -not (Test-Path -LiteralPath $ShortcutPath -PathType Leaf) `
    -or $Shortcut.TargetPath -ne $Wscript `
    -or $Shortcut.Arguments -ne $Arguments `
    -or $Shortcut.WorkingDirectory -ne $ProjectRoot `
    -or $Shortcut.IconLocation -ne $IconLocation

if ($NeedsSave) {
    $Shortcut.TargetPath = $Wscript
    $Shortcut.Arguments = $Arguments
    $Shortcut.WorkingDirectory = $ProjectRoot
    $Shortcut.IconLocation = $IconLocation
    $Shortcut.Description = $AppName
    $Shortcut.Save()
}

Write-Output $ShortcutPath
