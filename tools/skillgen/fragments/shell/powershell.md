If the scan path contains a line break (a newline or carriage return), stop and ask the user for a different path. Do not run the block below: a path line could end the here-string early and run the lines after it as shell.

```powershell
# Detect Python with graphify — uv/pipx-aware (fixes #831)
New-Item -ItemType Directory -Force -Path graphify-out | Out-Null
$GRAPHIFY_PYTHON = $null

function Find-GraphifyPython {
    # 1. uv tool install — 'uv tool dir' is authoritative, respects UV_TOOL_DIR automatically
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        $uvDir = (uv tool dir 2>$null).Trim()
        if ($uvDir) {
            $py = Join-Path $uvDir "graphifyy\Scripts\python.exe"
            if (Test-Path $py) {
                & $py -c "import graphify" 2>$null
                if ($LASTEXITCODE -eq 0) { return $py }
            }
        }
    }
    # 2. pipx install — 'pipx environment' respects PIPX_HOME automatically
    if (Get-Command pipx -ErrorAction SilentlyContinue) {
        $venvs = (pipx environment --value PIPX_LOCAL_VENVS 2>$null).Trim()
        if ($venvs) {
            $py = Join-Path $venvs "graphifyy\Scripts\python.exe"
            if (Test-Path $py) {
                & $py -c "import graphify" 2>$null
                if ($LASTEXITCODE -eq 0) { return $py }
            }
        }
    }
    # 3. Active venv / conda / pip-into-current-env
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pyCmd) {
        & $pyCmd.Source -c "import graphify" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return (& $pyCmd.Source -c "import sys; print(sys.executable)").Trim()
        }
    }
    return $null
}

# Try to find the right Python (uv → pipx → active env)
$GRAPHIFY_PYTHON = Find-GraphifyPython

# Not found — install then re-detect
if (-not $GRAPHIFY_PYTHON) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv tool install --upgrade graphifyy -q 2>&1 | Select-Object -Last 3
    } else {
        pip install graphifyy -q 2>&1 | Select-Object -Last 3
    }
    $GRAPHIFY_PYTHON = Find-GraphifyPython
}

# Save interpreter path — all subsequent steps read this.
# `Out-File -Encoding utf8` always writes a BOM on Windows PowerShell 5.1 (utf8NoBOM
# only exists from PowerShell 6), and that BOM rides into the saved path, so the hook
# rebuild fails with WinError 123 (#3028). WriteAllText with an explicit BOM-less
# encoding writes the bytes POSIX writes, and adds no trailing newline.
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
# Remove last run's markers first, then write each through a temp file and a rename,
# and stop with the file name if a write fails (#4346), so a full disk can't leave an
# empty or stale marker behind.
$OutDir = Join-Path $PWD 'graphify-out'
foreach ($name in '.graphify_python', '.graphify_root') {
    Remove-Item -LiteralPath (Join-Path $OutDir $name) -Force -ErrorAction SilentlyContinue
}
function Save-GraphifyMarker([string]$Name, [string]$Text) {
    if (-not $Text) { throw "graphify: nothing to write to graphify-out\$Name" }
    $path = Join-Path $OutDir $Name
    $tmp = "$path.tmp"
    try {
        [System.IO.File]::WriteAllText($tmp, $Text, $Utf8NoBom)
        Move-Item -LiteralPath $tmp -Destination $path -Force -ErrorAction Stop
    } catch {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
        throw "graphify: could not write graphify-out\$Name ($($_.Exception.Message); is the disk full?)"
    }
}
Save-GraphifyMarker '.graphify_python' ([string]$GRAPHIFY_PYTHON)
# Save scan root so `graphify update` (no args) knows where to look next time.
# PowerShell never expands the scan path: it is captured through a single-quoted
# (literal) here-string, not the command line. A path with a line break is refused,
# because a line starting with '@ would end the here-string early and run the lines
# after it as script code.
$InputPathRaw = @'
INPUT_PATH
'@
$InputPathChecked = $InputPathRaw -replace '\n$', ''
if ($InputPathChecked.Contains("`n") -or $InputPathChecked.Contains("`r")) { throw 'graphify: the scan path has a line break, so it was not used; give a single-line path' }
Save-GraphifyMarker '.graphify_root' (Resolve-Path $InputPathRaw.Trim()).Path
```

If the import succeeds, print nothing and move straight to Step 2.

**In every subsequent block, run Python through the saved interpreter — `& (Get-Content graphify-out\.graphify_python)` in place of a bare `python3` — so every step uses the interpreter that actually has graphify.**
