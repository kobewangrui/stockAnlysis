Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$AndroidDir = Join-Path $Root "android"
$ToolsDir = Join-Path $Root "tools"
$JdkDir = Join-Path $ToolsDir "jdk17"
$Python311Dir = Join-Path $ToolsDir "python311"
$Python311Exe = Join-Path $Python311Dir "tools\python.exe"
$SdkDir = Join-Path $ToolsDir "android-sdk"
$CmdlineToolsDir = Join-Path $SdkDir "cmdline-tools\latest"
$GradleVersion = "8.9"
$GradleDir = Join-Path $ToolsDir "gradle-$GradleVersion"
$GradleExe = Join-Path $GradleDir "bin\gradle.bat"
$DistDir = Join-Path $Root "dist"
$ApkOut = Join-Path $DistDir "StockAnalysisAndroid-debug.apk"
$FriendlyApkOut = Join-Path $DistDir "StockAnalysis.apk"

function Invoke-Step {
  param(
    [string]$Title,
    [scriptblock]$Action
  )
  Write-Host ""
  Write-Host "==> $Title" -ForegroundColor Cyan
  & $Action
}

function Download-File {
  param(
    [string]$Url,
    [string]$Destination
  )
  Write-Host "Downloading $Url"
  Invoke-WebRequest -Uri $Url -OutFile $Destination
}

New-Item -ItemType Directory -Force $ToolsDir, $SdkDir, $DistDir | Out-Null

Invoke-Step "Prepare JDK 17" {
  $javaExe = Join-Path $JdkDir "bin\java.exe"
  if (-not (Test-Path -LiteralPath $javaExe)) {
    $jdkZip = Join-Path $ToolsDir "jdk17.zip"
    Download-File "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse?project=jdk" $jdkZip
    $tmp = Join-Path $ToolsDir "jdk17_tmp"
    if (Test-Path -LiteralPath $tmp) {
      Remove-Item -LiteralPath $tmp -Recurse -Force
    }
    New-Item -ItemType Directory -Force $tmp | Out-Null
    tar -xf $jdkZip -C $tmp
    $extracted = Get-ChildItem -LiteralPath $tmp -Directory | Select-Object -First 1
    if (-not $extracted) {
      throw "Failed to extract JDK"
    }
    if (Test-Path -LiteralPath $JdkDir) {
      Remove-Item -LiteralPath $JdkDir -Recurse -Force
    }
    Move-Item -LiteralPath $extracted.FullName -Destination $JdkDir
    Remove-Item -LiteralPath $tmp -Recurse -Force
  }
  & $javaExe -version
}

Invoke-Step "Prepare Python 3.11 for Chaquopy" {
  if (-not (Test-Path -LiteralPath $Python311Exe)) {
    $pythonZip = Join-Path $ToolsDir "python311.nupkg"
    Download-File "https://www.nuget.org/api/v2/package/python/3.11.9" $pythonZip
    if (Test-Path -LiteralPath $Python311Dir) {
      Remove-Item -LiteralPath $Python311Dir -Recurse -Force
    }
    New-Item -ItemType Directory -Force $Python311Dir | Out-Null
    tar -xf $pythonZip -C $Python311Dir
  }
  & $Python311Exe --version
}

Invoke-Step "Prepare Android command line tools" {
  $sdkManager = Join-Path $CmdlineToolsDir "bin\sdkmanager.bat"
  if (-not (Test-Path -LiteralPath $sdkManager)) {
    $cmdZip = Join-Path $ToolsDir "android-commandlinetools.zip"
    Download-File "https://dl.google.com/android/repository/commandlinetools-win-13114758_latest.zip" $cmdZip
    $tmp = Join-Path $ToolsDir "android-commandlinetools"
    if (Test-Path -LiteralPath $tmp) {
      Remove-Item -LiteralPath $tmp -Recurse -Force
    }
    New-Item -ItemType Directory -Force $tmp | Out-Null
    tar -xf $cmdZip -C $tmp
    New-Item -ItemType Directory -Force (Split-Path $CmdlineToolsDir -Parent) | Out-Null
    if (Test-Path -LiteralPath $CmdlineToolsDir) {
      Remove-Item -LiteralPath $CmdlineToolsDir -Recurse -Force
    }
    Move-Item -LiteralPath (Join-Path $tmp "cmdline-tools") -Destination $CmdlineToolsDir
    Remove-Item -LiteralPath $tmp -Recurse -Force
  }
}

Invoke-Step "Install Android SDK packages" {
  $env:JAVA_HOME = $JdkDir
  $env:ANDROID_HOME = $SdkDir
  $env:ANDROID_SDK_ROOT = $SdkDir
  $env:PATH = "$JdkDir\bin;$CmdlineToolsDir\bin;$SdkDir\platform-tools;$env:PATH"
  $sdkManager = Join-Path $CmdlineToolsDir "bin\sdkmanager.bat"

  1..30 | ForEach-Object { "y" } | & $sdkManager --sdk_root=$SdkDir --licenses | Out-Host
  & $sdkManager --sdk_root=$SdkDir "platform-tools" "platforms;android-35" "build-tools;35.0.0"
}

Invoke-Step "Prepare Gradle $GradleVersion" {
  if (-not (Test-Path -LiteralPath $GradleExe)) {
    $gradleZip = Join-Path $ToolsDir "gradle-$GradleVersion-bin.zip"
    Download-File "https://services.gradle.org/distributions/gradle-$GradleVersion-bin.zip" $gradleZip
    tar -xf $gradleZip -C $ToolsDir
  }
  & $GradleExe --version
}

Invoke-Step "Sync Python web sources into Android project" {
  Copy-Item -LiteralPath (Join-Path $Root "app.py") -Destination (Join-Path $AndroidDir "app\src\main\python\app.py") -Force
  $pythonDir = Join-Path $AndroidDir "app\src\main\python"
  foreach ($folder in @("templates", "static")) {
    $target = Join-Path $pythonDir $folder
    if (Test-Path -LiteralPath $target) {
      Remove-Item -LiteralPath $target -Recurse -Force
    }
    Copy-Item -LiteralPath (Join-Path $Root $folder) -Destination $target -Recurse -Force
  }
}

Invoke-Step "Build Android APK" {
  $localProperties = "sdk.dir=$($SdkDir.Replace('\', '\\'))"
  Set-Content -LiteralPath (Join-Path $AndroidDir "local.properties") -Value $localProperties -Encoding ASCII
  Push-Location $AndroidDir
  try {
    $pythonArg = "-PchaquopyBuildPython=$($Python311Exe.Replace('\', '/'))"
    & $GradleExe --no-daemon $pythonArg assembleDebug
  } finally {
    Pop-Location
  }

  $builtApk = Join-Path $AndroidDir "app\build\outputs\apk\debug\app-debug.apk"
  if (-not (Test-Path -LiteralPath $builtApk)) {
    throw "APK was not created at $builtApk"
  }
  Copy-Item -LiteralPath $builtApk -Destination $ApkOut -Force
  Copy-Item -LiteralPath $builtApk -Destination $FriendlyApkOut -Force
}

Write-Host ""
Write-Host "APK ready: $FriendlyApkOut" -ForegroundColor Green
Write-Host "Debug APK copy: $ApkOut"
