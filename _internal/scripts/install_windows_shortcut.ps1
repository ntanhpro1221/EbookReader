param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = "Stop"

$AppName = "Ebook Reader"
$Launcher = Join-Path $ProjectRoot "_internal\Ebook Reader.vbs"
$Icon = Join-Path $ProjectRoot "_internal\ebook_reader\assets\ebook_reader.ico"
$ProgramsRoot = [Environment]::GetFolderPath([Environment+SpecialFolder]::Programs)
$RootShortcutPath = Join-Path $ProjectRoot "$AppName.lnk"
$StartMenuShortcutPath = Join-Path $ProgramsRoot "$AppName.lnk"
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

function Set-AppShortcut([string]$ShortcutPath) {
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $NeedsSave = -not (Test-Path -LiteralPath $ShortcutPath -PathType Leaf) `
        -or $Shortcut.TargetPath -ne $Launcher `
        -or -not [string]::IsNullOrEmpty($Shortcut.Arguments) `
        -or $Shortcut.WorkingDirectory -ne $ProjectRoot `
        -or $Shortcut.IconLocation -ne $IconLocation

    if ($NeedsSave) {
        $Shortcut.TargetPath = $Launcher
        $Shortcut.Arguments = ""
        $Shortcut.WorkingDirectory = $ProjectRoot
        $Shortcut.IconLocation = $IconLocation
        $Shortcut.Description = $AppName
        $Shortcut.Save()
    }
}

Set-AppShortcut $RootShortcutPath
Set-AppShortcut $StartMenuShortcutPath
Write-Output $RootShortcutPath, $StartMenuShortcutPath
