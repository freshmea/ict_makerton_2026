[CmdletBinding()]
param([switch]$Open)

$ErrorActionPreference = 'Stop'
$firmwareRoot = $PSScriptRoot
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $firmwareRoot)
$localToolchain = Join-Path $repositoryRoot '.local-tools/rustup/toolchains/1.90.0-x86_64-pc-windows-msvc/bin'
$savedEnvironment = @{}
$environmentNames = @('RUSTUP_HOME', 'CARGO_HOME', 'RUSTUP_TOOLCHAIN', 'RUSTC', 'RUSTDOC', 'RUSTDOCFLAGS')
foreach ($name in $environmentNames) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

try {
    if (Test-Path -LiteralPath (Join-Path $localToolchain 'cargo.exe')) {
        $env:RUSTUP_HOME = Join-Path $repositoryRoot '.local-tools/rustup'
        $env:CARGO_HOME = Join-Path $repositoryRoot '.local-tools/cargo'
        $env:RUSTUP_TOOLCHAIN = '1.90.0'
        $env:RUSTC = Join-Path $localToolchain 'rustc.exe'
        $env:RUSTDOC = Join-Path $localToolchain 'rustdoc.exe'
        $cargoCommand = Join-Path $localToolchain 'cargo.exe'
        $rustcCommand = $env:RUSTC
        $rustdocCommand = $env:RUSTDOC
    } else {
        $cargoCommand = (Get-Command cargo -ErrorAction Stop).Source
        $rustcCommand = (Get-Command rustc -ErrorAction Stop).Source
        $rustdocCommand = (Get-Command rustdoc -ErrorAction Stop).Source
    }

    $version = & $rustcCommand -vV
    if ($LASTEXITCODE -ne 0) { throw 'rustc version detection failed.' }
    $hostLine = $version | Where-Object { $_ -match '^host: ' } | Select-Object -First 1
    if (-not $hostLine) { throw 'rustc did not report a host target.' }
    $hostTarget = $hostLine.Substring(6).Trim()
    $env:RUSTDOCFLAGS = ($savedEnvironment['RUSTDOCFLAGS'] + ' -D rustdoc::broken_intra_doc_links -D rustdoc::bare_urls').Trim()
    $manifest = Join-Path $firmwareRoot 'Cargo.toml'
    $outputRoot = Join-Path $firmwareRoot 'target/learning-docs'
    $libraryOutput = Join-Path $outputRoot 'library'
    $deviceOutput = Join-Path $outputRoot 'device'

    & $cargoCommand doc --manifest-path $manifest --locked --offline --lib --target $hostTarget --no-deps --target-dir $libraryOutput
    if ($LASTEXITCODE -ne 0) { throw 'Library documentation build failed.' }

    & $cargoCommand rustdoc --manifest-path $manifest --locked --offline --bin pico2-device-bench --target thumbv8m.main-none-eabihf --target-dir $deviceOutput -- --document-private-items
    if ($LASTEXITCODE -ne 0) { throw 'Device runtime documentation build failed.' }

    $libraryIndex = Join-Path $libraryOutput "$hostTarget/doc/pico2_device_bench/index.html"
    $deviceIndex = Join-Path $deviceOutput 'thumbv8m.main-none-eabihf/doc/pico2_device_bench/index.html'
    $landingSource = Join-Path $firmwareRoot 'docs/index.md'
    foreach ($docRoot in @((Join-Path $libraryOutput "$hostTarget/doc"), (Join-Path $deviceOutput 'thumbv8m.main-none-eabihf/doc'))) {
        & $rustdocCommand $landingSource --output $docRoot
        if ($LASTEXITCODE -ne 0) { throw 'Documentation landing page build failed.' }
    }
    foreach ($index in @($libraryIndex, $deviceIndex)) {
        if (-not (Test-Path -LiteralPath $index)) { throw "Documentation index missing: $index" }
    }
    Write-Output "Library HTML: $libraryIndex"
    Write-Output "Device HTML: $deviceIndex"
    if ($Open) { Invoke-Item -LiteralPath $libraryIndex }
} finally {
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process')
    }
}
