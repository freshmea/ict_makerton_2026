# Dot-source this file before building the Pico firmware or host bench tool.
$picoRepoRoot = Split-Path -Parent $PSScriptRoot
$env:RUSTUP_HOME = Join-Path $picoRepoRoot '.local-tools/rustup'
$env:CARGO_HOME = Join-Path $picoRepoRoot '.local-tools/cargo'
$env:RUSTUP_TOOLCHAIN = '1.90.0'
$picoCargoBin = Join-Path $env:CARGO_HOME 'bin'
if (($env:PATH -split ';') -notcontains $picoCargoBin) {
    $env:PATH = $picoCargoBin + ';' + $env:PATH
}
