# wxsheep installer (Windows x64)
# Works without git: falls back to codeload zip download.
# Installs node (if missing), the two dependency repos, a verified frida
# prebuilt binding, and the patched proxy logger. Safe to re-run.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

$NODE_VER   = '22.22.2'
$NODE_DIR   = Join-Path $root 'runtime\node'
$FRIDA_URL  = 'https://gh-proxy.com/https://github.com/frida/frida/releases/download/17.18.0/frida-v17.18.0-napi-v8-win32-x64.tar.gz'
$FRIDA_SHA  = 'db67a1d9cd2f6b24df699406fadd6022571ad7c00e6c4782f634039da7c0302c'
$PROXY      = Join-Path $root 'dbg\WMPFDebugger'
$SOLVER     = Join-Path $root 'dbg\sheep-solver'
$TMP        = Join-Path $root '.tmp'

function Ok($m)   { Write-Host "[ok]   $m" -ForegroundColor Green }
function Info($m) { Write-Host "[..]   $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "[warn] $m" -ForegroundColor Yellow }
function Hold     { try { if (-not [Console]::IsInputRedirected) { Read-Host "Press Enter to exit" | Out-Null } } catch { } }
function Die($m)  { Write-Host "[FAIL] $m" -ForegroundColor Red; Write-Host ""; Hold; exit 1 }

# PS 5.1 turns stderr from native commands into terminating errors under
# ErrorActionPreference=Stop (yarn/npm/git all print warnings there).
# Run them with a relaxed preference and return the real exit code.
function Invoke-Native($Exe, $ArgList, $Echo) {
  $prev = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    if ($Echo) { & $Exe @ArgList 2>&1 | ForEach-Object { Write-Host "       $_" -ForegroundColor DarkGray } }
    else       { & $Exe @ArgList 2>&1 | Out-Null }
  } finally { $ErrorActionPreference = $prev }
  return $LASTEXITCODE
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " wxsheep installer" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# --- 1. node ---
$nodeCand = @("$env:ProgramFiles\nodejs", "$env:LOCALAPPDATA\nvs\node", "$env:APPDATA\npm")
foreach ($c in $nodeCand) { if ((Test-Path (Join-Path $c 'node.exe')) -and -not (Get-Command node -ErrorAction SilentlyContinue)) { $env:Path = "$c;$env:Path" } }
$localNode = Join-Path $NODE_DIR 'node.exe'
if (Test-Path $localNode) {
  $env:Path = "$NODE_DIR;$env:Path"
  Ok ("node " + (& $localNode -v) + "  (bundled runtime)")
} elseif (Get-Command node -ErrorAction SilentlyContinue) {
  Ok ("node " + (& node -v) + "  (system)")
} else {
  Info "downloading node $NODE_VER (~30 MB)"
  New-Item -ItemType Directory -Force -Path $TMP | Out-Null
  $zip = Join-Path $TMP 'node.zip'
  Invoke-WebRequest -Uri "https://npmmirror.com/mirrors/node/v$NODE_VER/node-v$NODE_VER-win-x64.zip" -OutFile $zip -UseBasicParsing
  Expand-Archive -Path $zip -DestinationPath (Join-Path $TMP 'node') -Force
  New-Item -ItemType Directory -Force -Path (Split-Path $NODE_DIR -Parent) | Out-Null
  Move-Item (Join-Path $TMP "node\node-v$NODE_VER-win-x64") $NODE_DIR -Force
  Remove-Item $zip -Force
  $env:Path = "$NODE_DIR;$env:Path"
  Ok ("node " + (& $localNode -v) + "  installed to runtime\node")
}

# --- 2. git (optional) ---
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  $cand = @(
    "$env:ProgramFiles\Git\cmd",
    "${env:ProgramFiles(x86)}\Git\cmd",
    "$env:LOCALAPPDATA\Programs\Git\cmd"
  )
  foreach ($c in $cand) { if (Test-Path (Join-Path $c 'git.exe')) { $env:Path = "$c;$env:Path"; break } }
}
$hasGit = [bool](Get-Command git -ErrorAction SilentlyContinue)
if ($hasGit) { Ok "git found (will clone)" } else { Info "git not found - will download source zips instead" }

# --- 3. fetch repos ---
function Get-Repo($dir, $gitUrl, $zipUrl, $inner, $probe, $label) {
  if (Test-Path (Join-Path $dir $probe)) { Ok "$label ready"; return }
  if ($hasGit) {
    if (Test-Path (Join-Path $dir '.git')) {
      Info "updating $label"
      Push-Location $dir; $null = Invoke-Native 'git' @('pull','--ff-only') $false; Pop-Location
      if (Test-Path (Join-Path $dir $probe)) { Ok "$label updated"; return }
    } else {
      Info "cloning $label"
      New-Item -ItemType Directory -Force -Path (Split-Path $dir -Parent) | Out-Null
      $null = Invoke-Native 'git' @('clone','--depth','1',$gitUrl,$dir) $false
      if (Test-Path (Join-Path $dir $probe)) { Ok "$label cloned"; return }
      Warn "clone did not produce expected files, falling back to zip"
    }
  }
  Info "downloading $label"
  New-Item -ItemType Directory -Force -Path $TMP | Out-Null
  $zip = Join-Path $TMP "$inner.zip"
  $ext = Join-Path $TMP "x-$inner"
  Invoke-WebRequest -Uri $zipUrl -OutFile $zip -UseBasicParsing
  if (Test-Path $ext) { Remove-Item $ext -Recurse -Force }
  Expand-Archive -Path $zip -DestinationPath $ext -Force
  if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
  New-Item -ItemType Directory -Force -Path (Split-Path $dir -Parent) | Out-Null
  Move-Item (Join-Path $ext $inner) $dir -Force
  Remove-Item $zip -Force
  Remove-Item $ext -Recurse -Force -ErrorAction SilentlyContinue
  if (Test-Path (Join-Path $dir $probe)) { Ok "$label downloaded" } else { Die "${label}: unexpected archive layout" }
}
Get-Repo $SOLVER 'https://github.com/GlrAoc/sheep-solver.git' 'https://codeload.github.com/GlrAoc/sheep-solver/zip/refs/heads/main' 'sheep-solver-main' 'oneclick.cmd' 'sheep-solver'
Get-Repo $PROXY  'https://github.com/evi0s/WMPFDebugger.git' 'https://codeload.github.com/evi0s/WMPFDebugger/zip/refs/heads/main' 'WMPFDebugger-main' 'src\index.ts' 'WMPFDebugger'

# --- 4. patched logger (file overlay, no git apply needed) ---
$overlay = Join-Path $root 'overlay\WMPFDebugger\src\logger.ts'
$target  = Join-Path $PROXY 'src\logger.ts'
if ((Test-Path $overlay) -and (Test-Path $target)) {
  $a = (Get-FileHash $overlay -Algorithm SHA256).Hash
  $b = (Get-FileHash $target  -Algorithm SHA256).Hash
  if ($a -eq $b) { Ok "proxy logger already patched" }
  else { Copy-Item $overlay $target -Force; Ok "proxy logger patched (file log)" }
} else {
  Warn "logger overlay missing - proxy diagnostics will be limited"
}

# --- 5. pin frida version ---
$pkgPath = Join-Path $PROXY 'package.json'
if (Test-Path $pkgPath) {
  $pkg = Get-Content $pkgPath -Raw
  if ($pkg -match '"\^17\.18\.0"') {
    Set-Content -Path $pkgPath -Value ($pkg -replace '"frida":\s*"\^17\.18\.0"', '"frida": "17.18.0"') -NoNewline -Encoding ASCII
    Ok "frida pinned to 17.18.0 (binding match)"
  }
}

# --- 6. deps ---
$nm      = Join-Path $PROXY 'node_modules'
$fridaJs = Join-Path $nm 'frida\build\src\frida.js'
if (Test-Path $fridaJs) {
  Ok "npm deps already installed"
} else {
  $lock = Join-Path $PROXY 'yarn.lock'
  if (Test-Path $lock) {
    $c = Get-Content $lock -Raw
    if ($c -match 'registry\.yarnpkg\.com') {
      Set-Content -Path $lock -Value ($c -replace 'registry\.yarnpkg\.com', 'registry.npmmirror.com') -NoNewline -Encoding ASCII
      Ok "yarn.lock registry -> npmmirror"
    }
  }
  Push-Location $PROXY
  if (Get-Command yarn -ErrorAction SilentlyContinue) {
    Info "yarn install --ignore-scripts  (3-6 min, no native build)"
    $code = Invoke-Native 'yarn' @('install','--ignore-scripts') $true
  } else {
    Info "npm install --ignore-scripts  (3-6 min, no native build)"
    $code = Invoke-Native 'npm' @('install','--ignore-scripts','--no-audit','--no-fund','--registry=https://registry.npmmirror.com') $true
  }
  Pop-Location
  if (-not (Test-Path $fridaJs)) { Die "dependency install failed (exit $code) - see docs/ENVIRONMENT.md section 3" }
  Ok "npm deps installed"
}

# --- 7. frida binding ---
$binding = Join-Path $nm 'frida\build\frida_binding.node'
if (Test-Path $binding) {
  Ok ("frida binding present (" + [math]::Round((Get-Item $binding).Length / 1MB) + " MB)")
} else {
  Info "downloading frida prebuilt binding (~50 MB, sha256 verified)"
  New-Item -ItemType Directory -Force -Path $TMP | Out-Null
  $tgz = Join-Path $TMP 'frida.tar.gz'
  Invoke-WebRequest -Uri $FRIDA_URL -OutFile $tgz -UseBasicParsing
  $h = (Get-FileHash $tgz -Algorithm SHA256).Hash.ToLower()
  if ($h -ne $FRIDA_SHA) { Die "frida package sha256 mismatch: $h" }
  Ok "sha256 verified"
  $code = Invoke-Native 'tar' @('-xzf',$tgz,'-C',(Join-Path $nm 'frida')) $false
  if ($code -ne 0) { Die "extract failed (tar not available? needs Windows 10 1803+)" }
  Remove-Item $tgz -Force
  Ok "frida binding installed"
}

# --- 8. verify ---
$prev = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
Push-Location $PROXY
$check = & node -e "const f=require('frida'); console.log(typeof f.getDevice === 'function' ? 'FRIDA_LOAD_OK' : 'FRIDA_BAD_EXPORT')" 2>&1 | Out-String
Pop-Location
$ErrorActionPreference = $prev
if ("$check" -match 'FRIDA_LOAD_OK') { Ok "frida module loads" } else { Warn "frida self-check: $check" }

if (Test-Path $TMP) { Remove-Item $TMP -Recurse -Force -ErrorAction SilentlyContinue }

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " install complete" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  1) double-click  start.cmd"
Write-Host "  2) wait for   [proxy] hook ready ...   in that window"
Write-Host "  3) THEN open the miniapp from WeChat and enter a level"
Write-Host ""
Write-Host "  Order matters: the frida hook only applies to pages loaded"
Write-Host "  after the proxy is ready. Reversed order never works."
Write-Host ""
Hold
