#Requires -Version 5.1
<#
.SYNOPSIS
  llm-wiki Windows PowerShell install wrapper

.DESCRIPTION
  Fixes the combined encoding problem on Windows PowerShell 5.1:
    - console default is GB2312 (CP936) on Chinese Windows
    - $OutputEncoding defaults to ASCII (CP1252)
    - Python subprocess sys.stdout.encoding defaults to gbk (cp936)
  This wrapper forces UTF-8 across all three layers so install.sh Chinese
  output and hook-generated JSON are not garbled (issue #16).

  Steps:
    1. chcp 65001 (console code page)
    2. [Console]::InputEncoding / OutputEncoding = UTF-8
    3. $OutputEncoding = UTF-8 (how PS decodes subprocess stdout)
    4. PYTHONIOENCODING=utf-8 (Python subprocess output)
    5. Invoke bash install.sh, forwarding all args

  All Write-Host output is kept ASCII-only so this script works even when
  PowerShell 5.1 parses the .ps1 file under Chinese ANSI (GBK) codepage
  with no BOM. The actual Chinese UI comes from install.sh after handoff.

.EXAMPLE
  PS> powershell -ExecutionPolicy Bypass -File install.ps1 --platform claude

.EXAMPLE
  PS> powershell -ExecutionPolicy Bypass -File install.ps1 --platform codex --dry-run

.NOTES
  - Requires Git for Windows (Git Bash) or WSL to provide bash on PATH
  - PowerShell 7+ users default to UTF-8 and can run bash install.sh directly
  - This wrapper adjusts environment only; it does not alter install.sh logic
#>

[CmdletBinding()]
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$RemainingArgs
)

$ErrorActionPreference = 'Stop'

# 1. Switch console code page to UTF-8
$null = & chcp.com 65001

# 2. Console input/output encoding
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 3. How PS decodes subprocess stdout bytes
$OutputEncoding = [System.Text.Encoding]::UTF8

# 4. Force Python subprocess stdout/stderr to UTF-8
$env:PYTHONIOENCODING = 'utf-8'

# 5. Detect bash
$bashCmd = Get-Command bash -ErrorAction SilentlyContinue
if (-not $bashCmd) {
  Write-Host "[llm-wiki] Error: bash not found on PATH." -ForegroundColor Red
  Write-Host "          Install Git for Windows first: https://git-scm.com/download/win" -ForegroundColor Red
  exit 1
}

# Script root (use $PSScriptRoot to avoid null $MyInvocation.MyCommand.Path under -File)
$scriptDir = $PSScriptRoot
if ([string]::IsNullOrEmpty($scriptDir)) {
  $scriptDir = Split-Path -Parent $PSCommandPath
}
$installSh = Join-Path -Path $scriptDir -ChildPath 'install.sh'

if (-not (Test-Path $installSh)) {
  Write-Host "[llm-wiki] Error: install.sh not found at $installSh" -ForegroundColor Red
  exit 1
}

Write-Host "[llm-wiki] UTF-8 environment ready, launching install.sh..." -ForegroundColor Cyan

# Forward args
if ($null -eq $RemainingArgs -or $RemainingArgs.Count -eq 0) {
  & bash $installSh
} else {
  & bash $installSh @RemainingArgs
}

exit $LASTEXITCODE
