[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Use-LocalRust.ps1')
$picoProject = Join-Path $PSScriptRoot 'pico2-device-bench'
$picoDist = Join-Path $picoProject 'dist'
New-Item -ItemType Directory -Path $picoDist -Force | Out-Null
Push-Location $picoProject
try {
    & cargo build --release --locked
    if ($LASTEXITCODE -ne 0) { throw 'Firmware build failed.' }
    $picoElf = Join-Path $picoProject 'target/thumbv8m.main-none-eabihf/release/pico2-device-bench'
    $picoUf2 = Join-Path $picoDist 'pico2-device-bench.uf2'
    & elf2uf2-rs convert --family rp2350-arm-s $picoElf $picoUf2 *> (Join-Path $picoDist 'conversion.log')
    if ($LASTEXITCODE -ne 0) { throw 'RP2350 UF2 conversion failed. Use the pinned converter revision in README.' }
    $picoBytes = [IO.File]::ReadAllBytes($picoUf2)
    if ($picoBytes.Length -eq 0 -or $picoBytes.Length % 512 -ne 0) { throw 'Invalid UF2 size.' }
    $picoBlocks = $picoBytes.Length / 512
    $picoSeen = @{}
    for ($picoOffset = 0; $picoOffset -lt $picoBytes.Length; $picoOffset += 512) {
        $picoWord = { param($n) [BitConverter]::ToUInt32($picoBytes, $picoOffset + 4 * $n) }
        if ((& $picoWord 0) -ne 0x0a324655 -or (& $picoWord 1) -ne [Convert]::ToUInt32('9e5d5157', 16) -or (& $picoWord 127) -ne 0x0ab16f30) { throw 'Invalid UF2 magic.' }
        if (((& $picoWord 2) -band 0x2000) -eq 0 -or (& $picoWord 7) -ne [Convert]::ToUInt32('e48bff59', 16)) { throw 'Wrong UF2 family; require RP2350 Arm Secure.' }
        $picoAddress = & $picoWord 3
        $picoPayload = & $picoWord 4
        $picoNumber = & $picoWord 5
        if ($picoPayload -gt 476 -or $picoPayload -eq 0 -or $picoAddress -lt 0x10000000 -or ([uint64]$picoAddress + $picoPayload) -gt 0x10400000) { throw 'Invalid flash payload range.' }
        if ((& $picoWord 6) -ne $picoBlocks -or $picoNumber -ge $picoBlocks -or $picoSeen.ContainsKey($picoNumber)) { throw 'Invalid UF2 block numbering.' }
        $picoSeen[$picoNumber] = $true
    }
    $picoHash = (Get-FileHash -LiteralPath $picoUf2 -Algorithm SHA256).Hash
    $picoInfo = [ordered]@{
        target = 'thumbv8m.main-none-eabihf'
        rust = (& rustc --version)
        converter_revision = 'f14bf2d981772cd9fbe5bac33b685719caac1add'
        family = '0xe48bff59'
        blocks = $picoBlocks
        bytes = $picoBytes.Length
        sha256 = $picoHash
    }
    $picoInfo | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $picoDist 'build-info.json') -Encoding utf8
    Write-Output "Verified RP2350 UF2: $picoUf2"
    Write-Output "SHA256: $picoHash"
} finally {
    Pop-Location
}

