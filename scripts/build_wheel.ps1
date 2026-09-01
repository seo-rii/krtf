#Requires -Version 5.1
<#
.SYNOPSIS
    Windows wrapper around scripts/build_wheel.py.

.DESCRIPTION
    All the work lives in build_wheel.py so Windows and Linux run the same
    code path and the wrappers cannot drift apart. This one only picks an
    interpreter, enforces the minimum version, and forces UTF-8 - which is
    not optional here: the sources and fixtures are full of Korean, and a
    child Python on Windows still defaults to the ANSI code page unless
    PYTHONUTF8 says otherwise.

.EXAMPLE
    .\scripts\build_wheel.ps1
    .\scripts\build_wheel.ps1 -NoVerify
    .\scripts\build_wheel.ps1 -Keep
#>
[CmdletBinding()]
param(
    [switch]$NoVerify,
    [switch]$Keep
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# Try candidates in order and take the first that is genuinely >= 3.11
# rather than trusting the name. `python` on a stock Windows PATH is often
# the Microsoft Store stub, which answers every invocation without being
# an interpreter; the launcher (`py -3`) is usually the real one.
$candidates = @()
if ($env:VIRTUAL_ENV -and (Test-Path "$env:VIRTUAL_ENV\Scripts\python.exe")) {
    $candidates += , @("$env:VIRTUAL_ENV\Scripts\python.exe", @())
}
if (Get-Command py -ErrorAction SilentlyContinue) {
    $candidates += , @((Get-Command py).Source, @('-3'))
}
if (Get-Command python -ErrorAction SilentlyContinue) {
    $candidates += , @((Get-Command python).Source, @())
}

$py = $null
$pyArgs = @()
$probe = 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
foreach ($candidate in $candidates) {
    $exe, $exeArgs = $candidate
    try {
        & $exe @exeArgs -c $probe 2>$null
        if ($LASTEXITCODE -eq 0) { $py = $exe; $pyArgs = $exeArgs; break }
    } catch {
        continue   # not an interpreter at all; try the next candidate
    }
}

if (-not $py) {
    $tried = ($candidates | ForEach-Object { $_[0] }) -join ', '
    Write-Error "no Python >= 3.11 found (tried: $tried). Activate a venv, or install a newer Python."
}

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

$scriptArgs = @("$here\build_wheel.py")
if ($NoVerify) { $scriptArgs += '--no-verify' }
if ($Keep) { $scriptArgs += '--keep' }

& $py @pyArgs @scriptArgs
exit $LASTEXITCODE
