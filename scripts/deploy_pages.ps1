# 把 docs/ 部署到 Cloudflare Pages
#
# 用法:
#   pwsh scripts/deploy_pages.ps1
#   pwsh scripts/deploy_pages.ps1 -TokenFile <路径> -NodeDir <node 所在目录>
#
# token 需要权限: Account > Cloudflare Pages > Edit

param(
  [string]$Project   = "delta-codes",
  [string]$TokenFile = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) ".cf-token"),
  [string]$NodeDir   = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$docs = Join-Path $root "docs"

if (-not (Test-Path $docs)) { throw "找不到 docs 目录: $docs" }
if (-not (Test-Path $TokenFile)) { throw "找不到 token 文件: $TokenFile`n请把 Cloudflare API Token 写入该文件（无换行）" }

$token = (Get-Content $TokenFile -Raw).Trim()
if (-not $token) { throw "token 文件是空的: $TokenFile" }

# ---- 定位 node（wrangler 的 shim 需要 node 在 PATH 里）----
if ($NodeDir -and (Test-Path (Join-Path $NodeDir "node.exe"))) {
  $nodeDir = $NodeDir
} else {
  $cmd = Get-Command node -ErrorAction SilentlyContinue
  if ($cmd) {
    $nodeDir = Split-Path -Parent $cmd.Source
  } elseif ($env:DSH_HOME) {
    $nodeDir = Join-Path $env:DSH_HOME "dsh-runtimes\dsh-primary-runtime\dependencies\node\bin"
  } else {
    $nodeDir = ""
  }
}
if (-not $nodeDir -or -not (Test-Path (Join-Path $nodeDir "node.exe"))) {
  throw "找不到 node.exe。请用 -NodeDir 指定（当前猜测: '$nodeDir'）"
}
$node = Join-Path $nodeDir "node.exe"

# pnpm.mjs 与 node 同级往上找
$deps = Split-Path -Parent (Split-Path -Parent $nodeDir)   # .../dependencies
$pnpm = Join-Path $deps "pnpm\bin\pnpm.mjs"
if (-not (Test-Path $pnpm)) { throw "找不到 pnpm.mjs: $pnpm" }

$env:PATH = "$nodeDir;" + $env:PATH
$env:npm_config_yes = "true"
$env:CLOUDFLARE_API_TOKEN = $token
$env:CLOUDFLARE_ACCOUNT_ID = "c9edadde3416e33b1d2501ae4fc1f10f"

Write-Host "[..] node   = $node"
Write-Host "[..] 部署   = $docs"
Write-Host "[..] 项目   = $Project"
Write-Host ""

& $node $pnpm dlx wrangler@3 pages deploy $docs --project-name=$Project --branch=main --commit-dirty=true 2>&1 |
  Where-Object { $_ -notmatch '^Progress:' -and $_ -notmatch '^\s*$' }

if ($LASTEXITCODE -ne 0) { throw "wrangler 退出码 $LASTEXITCODE" }

Write-Host ""
Write-Host "[ok] Cloudflare Pages 部署完成  ->  https://hajimiovo.top/"
