[CmdletBinding()]
param(
    [string] $PackageVersion = "0.0.0-dev",
    [string] $Python = "python",
    [switch] $SkipClean
)

$ErrorActionPreference = "Stop"

$isWindowsHost = [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
if (-not $isWindowsHost) {
    throw "This build script must run on Windows because the tools use Windows HID APIs."
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$allowedRoot = $repoRoot
$allowedRootWithSeparator = $allowedRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

function Resolve-RepoPath {
    param([Parameter(Mandatory = $true)][string] $Path)

    $fullPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $Path))
    $isRepoRoot = $fullPath.Equals($allowedRoot, [StringComparison]::OrdinalIgnoreCase)
    $isUnderRepoRoot = $fullPath.StartsWith($allowedRootWithSeparator, [StringComparison]::OrdinalIgnoreCase)
    if (-not ($isRepoRoot -or $isUnderRepoRoot)) {
        throw "Refusing to operate outside repo root: $fullPath"
    }
    return $fullPath
}

function Remove-RepoPath {
    param([Parameter(Mandatory = $true)][string] $Path)

    $fullPath = Resolve-RepoPath -Path $Path
    if (Test-Path -LiteralPath $fullPath) {
        Write-Host "Removing: $fullPath"
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
}

function Invoke-Logged {
    param(
        [Parameter(Mandatory = $true)][string] $FilePath,
        [Parameter(Mandatory = $true)][string[]] $ArgumentList
    )

    $formattedArgs = ($ArgumentList | ForEach-Object { "[" + $_ + "]" }) -join " "
    Write-Host "argv: [$FilePath] $formattedArgs"
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath"
    }
}

$distRoot = Resolve-RepoPath -Path "dist"
$pyinstallerWork = Resolve-RepoPath -Path "build\pyinstaller"
$releaseRoot = Resolve-RepoPath -Path "release"
$packageRoot = Resolve-RepoPath -Path "build\package\arduino-hid-monitor"
$binRoot = Join-Path $packageRoot "bin"
$docRoot = Join-Path $packageRoot "docs"

if (-not $SkipClean) {
    Remove-RepoPath -Path "build\pyinstaller"
    Remove-RepoPath -Path "build\package"
    Remove-RepoPath -Path "dist"
    Remove-RepoPath -Path "release"
}

New-Item -ItemType Directory -Force -Path $distRoot, $pyinstallerWork, $releaseRoot, $binRoot, $docRoot | Out-Null

$commonPathArg = Resolve-RepoPath -Path "tools\common"
$discoveryPath = Resolve-RepoPath -Path "tools\hid-discovery\hid_discovery.py"
$monitorPath = Resolve-RepoPath -Path "tools\hid-monitor\hid_monitor.py"

$pyinstallerBaseArgs = @(
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--console",
    "--paths",
    $commonPathArg,
    "--distpath",
    $distRoot,
    "--workpath",
    $pyinstallerWork
)

$discoverySpecPathArg = "--specpath"
$discoverySpecPathValue = $pyinstallerWork
$discoveryNameArg = "--name"
$discoveryNameValue = "hid-discovery"
$discoveryArgs = $pyinstallerBaseArgs + @(
    $discoverySpecPathArg,
    $discoverySpecPathValue,
    $discoveryNameArg,
    $discoveryNameValue,
    $discoveryPath
)
Invoke-Logged -FilePath $Python -ArgumentList $discoveryArgs

$monitorSpecPathArg = "--specpath"
$monitorSpecPathValue = $pyinstallerWork
$monitorNameArg = "--name"
$monitorNameValue = "hid-monitor"
$monitorArgs = $pyinstallerBaseArgs + @(
    $monitorSpecPathArg,
    $monitorSpecPathValue,
    $monitorNameArg,
    $monitorNameValue,
    $monitorPath
)
Invoke-Logged -FilePath $Python -ArgumentList $monitorArgs

Copy-Item -LiteralPath (Join-Path $distRoot "hid-discovery.exe") -Destination (Join-Path $binRoot "hid-discovery.exe") -Force
Copy-Item -LiteralPath (Join-Path $distRoot "hid-monitor.exe") -Destination (Join-Path $binRoot "hid-monitor.exe") -Force
Copy-Item -LiteralPath (Resolve-RepoPath -Path "LICENSE") -Destination (Join-Path $packageRoot "LICENSE") -Force
Copy-Item -LiteralPath (Resolve-RepoPath -Path "README.md") -Destination (Join-Path $packageRoot "README.md") -Force
Copy-Item -LiteralPath (Resolve-RepoPath -Path "docs\package_index_integration.md") -Destination (Join-Path $docRoot "package_index_integration.md") -Force
Copy-Item -LiteralPath (Resolve-RepoPath -Path "docs\hid_monitor_packet_protocol.md") -Destination (Join-Path $docRoot "hid_monitor_packet_protocol.md") -Force

$metadataPath = Join-Path $packageRoot "metadata.json"
$metadata = [ordered]@{
    name = "arduino-hid-monitor"
    version = $PackageVersion
    protocol = "hid-monitor"
    defaultVid = "1209"
    defaultPid = "C003"
    platform = "windows-amd64"
}
$metadata | ConvertTo-Json | Set-Content -LiteralPath $metadataPath -Encoding UTF8

$archiveName = "arduino-hid-monitor-$PackageVersion-windows-amd64.zip"
$archivePath = Join-Path $releaseRoot $archiveName
$packageItems = Get-ChildItem -LiteralPath $packageRoot | ForEach-Object { $_.FullName }
Compress-Archive -LiteralPath $packageItems -DestinationPath $archivePath -Force

$hash = Get-FileHash -LiteralPath $archivePath -Algorithm SHA256
$shaPath = "$archivePath.sha256"
$shaLine = $hash.Hash.ToLowerInvariant() + " *" + $archiveName
Set-Content -LiteralPath $shaPath -Value $shaLine -Encoding ASCII

Write-Host "Archive: $archivePath"
Write-Host "SHA256:  $shaPath"
