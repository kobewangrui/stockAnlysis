param(
  [switch]$SkipInstaller
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$SpecFile = Join-Path $Root "StockAnalysis.spec"
$DistDir = Join-Path $Root "dist"
$BuildDir = Join-Path $Root "build"
$PayloadDir = Join-Path $BuildDir "installer_payload"
$AppExe = Join-Path $DistDir "StockAnalysis.exe"
$SetupExe = Join-Path $DistDir "StockAnalysisSetup.exe"
$SedFile = Join-Path $BuildDir "StockAnalysisSetup.sed"

function Invoke-Step {
  param(
    [string]$Title,
    [scriptblock]$Action
  )
  Write-Host ""
  Write-Host "==> $Title" -ForegroundColor Cyan
  & $Action
}

Invoke-Step "Prepare Python environment" {
  if (-not (Test-Path -LiteralPath $VenvPython)) {
    python -m venv (Join-Path $Root ".venv")
  }
  & $VenvPython -m pip install --upgrade pip
  & $VenvPython -m pip install -r (Join-Path $Root "requirements.txt") -r (Join-Path $Root "requirements-build.txt")
}

Invoke-Step "Build single-file executable" {
  & $VenvPython -m PyInstaller --clean --noconfirm $SpecFile
  if (-not (Test-Path -LiteralPath $AppExe)) {
    throw "PyInstaller did not create $AppExe"
  }
}

if ($SkipInstaller) {
  Write-Host ""
  Write-Host "Executable ready: $AppExe" -ForegroundColor Green
  exit 0
}

Invoke-Step "Prepare installer payload" {
  if (Test-Path -LiteralPath $PayloadDir) {
    Remove-Item -LiteralPath $PayloadDir -Recurse -Force
  }
  New-Item -ItemType Directory -Force $PayloadDir | Out-Null
  Copy-Item -LiteralPath $AppExe -Destination (Join-Path $PayloadDir "StockAnalysis.exe") -Force
  Copy-Item -LiteralPath (Join-Path $Root "packaging\install.cmd") -Destination (Join-Path $PayloadDir "install.cmd") -Force
  Copy-Item -LiteralPath (Join-Path $Root "packaging\uninstall.cmd") -Destination (Join-Path $PayloadDir "uninstall.cmd") -Force
}

Invoke-Step "Build Windows installer with IExpress" {
  $iexpress = Get-Command iexpress -ErrorAction SilentlyContinue
  if (-not $iexpress) {
    Write-Warning "IExpress was not found. Installer skipped; executable is ready at $AppExe"
    return
  }

  $payloadPath = $PayloadDir.TrimEnd("\") + "\"
  $sed = @"
[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=Stock Analysis Dashboard has been installed.
TargetName=$SetupExe
FriendlyName=Stock Analysis Dashboard
AppLaunched=install.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=install.cmd
UserQuietInstCmd=install.cmd
SourceFiles=SourceFiles

[SourceFiles]
SourceFiles0=$payloadPath

[SourceFiles0]
%FILE0%=
%FILE1%=
%FILE2%=

[Strings]
FILE0="StockAnalysis.exe"
FILE1="install.cmd"
FILE2="uninstall.cmd"
"@
  Set-Content -LiteralPath $SedFile -Value $sed -Encoding ASCII
  & $iexpress.Source /N /Q $SedFile
  if (-not (Test-Path -LiteralPath $SetupExe)) {
    throw "IExpress did not create $SetupExe"
  }
}

Write-Host ""
Write-Host "Build complete." -ForegroundColor Green
Write-Host "Executable: $AppExe"
if (Test-Path -LiteralPath $SetupExe) {
  Write-Host "Installer:  $SetupExe"
}
