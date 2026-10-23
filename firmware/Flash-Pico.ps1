<#
.SYNOPSIS
Flash a verified local RP2350 bench or integrated Device UF2 over USB.
.DESCRIPTION
Default mode requires an explicit COM port running bootloader=picotool-v1.
It stops outputs through the matching bench CLI, enters ROM, selects one
RP2350, loads with picotool verification, then checks the expected CDC status.
-Bootsel is for an already mounted ROM device and the one-time initial image.
No servo sweep or LED test is executed. Windows PowerShell 5.1 compatible.
.EXAMPLE
.\firmware\Flash-Pico.ps1 -Firmware NeoPixel -Port COM7 -Build
.EXAMPLE
.\firmware\Flash-Pico.ps1 -Firmware Servo -Bootsel -Build
.EXAMPLE
.\firmware\Flash-Pico.ps1 -Firmware SwitchMatrix -Port COM11 -Build
.EXAMPLE
.\firmware\Flash-Pico.ps1 -Firmware Device -Port COM11 -Build
#>
[CmdletBinding(DefaultParameterSetName = 'Cdc')]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('NeoPixel', 'Servo', 'SwitchMatrix', 'Device')]
    [string]$Firmware,

    [Parameter(Mandatory = $true, ParameterSetName = 'Cdc')]
    [Parameter(ParameterSetName = 'Bootsel')]
    [ValidatePattern('^COM[1-9][0-9]*$')]
    [string]$Port,

    [Parameter(Mandatory = $true, ParameterSetName = 'Bootsel')]
    [switch]$Bootsel,

    [switch]$Build,
    [string]$LogDirectory,
    [ValidateRange(5, 60)]
    [int]$TimeoutSeconds = 25
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$picoRepo = Split-Path -Parent $PSScriptRoot
$picoVariants = @{
    NeoPixel = @{ Suffix = 'neopixel'; Pid = 'caff'; Protocol = 'neopixel-bench-v1'; BuildHelper = 'Build-PicoNeoPixel.ps1' }
    Servo = @{ Suffix = 'servo'; Pid = 'cafe'; Protocol = 'servo-bench-v1'; BuildHelper = 'Build-PicoServo.ps1' }
    SwitchMatrix = @{ Suffix = 'switch-matrix'; Pid = 'cafd'; Protocol = 'switch-matrix-bench-v1'; BuildHelper = 'Build-PicoSwitchMatrix.ps1' }
    Device = @{ Suffix = 'device'; Pid = 'cafc'; Protocol = 'pico-device-v1'; BuildHelper = 'Build-PicoDevice.ps1' }
}
$picoSelectedVariant = $picoVariants[$Firmware]
$picoSuffix = $picoSelectedVariant.Suffix
$picoExpectedPid = $picoSelectedVariant.Pid
$picoExpectedProtocol = $picoSelectedVariant.Protocol
$picoProject = Join-Path $PSScriptRoot ('pico2-' + $picoSuffix + '-bench')
$picoImage = Join-Path $picoProject ('dist/pico2-' + $picoSuffix + '-bench.uf2')
$picoMetadata = Join-Path $picoProject 'dist/build-info.json'
$picoToolInstall = Join-Path $picoRepo '.local-tools/picotool/2.3.1'
$picoTranscriptStarted = $false
$picoLogReady = $false
$picoResult = [ordered]@{
    started_utc = [DateTime]::UtcNow.ToString('o')
    firmware = $Firmware
    requested_port = $Port
    bootsel_mode = [bool]$Bootsel
    image = $picoImage
    sha256 = $null
    transport = $null
    flash_verified = $false
    application_status_verified = $false
    application_port = $null
    completed = $false
    error = $null
}

function Invoke-PicoNative {
    param([string]$Executable, [string[]]$Arguments)
    Write-Host ('> ' + $Executable + ' ' + ($Arguments -join ' '))
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $nativeLines = @(& $Executable @Arguments 2>&1 | ForEach-Object { $_.ToString() })
        $nativeExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    foreach ($nativeLine in $nativeLines) { Write-Host $nativeLine }
    [PSCustomObject]@{ ExitCode = $nativeExit; Text = ($nativeLines -join "`n"); Lines = $nativeLines }
}

function Get-PicoCli {
    param([string]$Kind)
    Join-Path $picoRepo ('tools/pico-' + $Kind + '-bench/target/release/pico-' + $Kind + '-bench.exe')
}

function Get-PicoPorts {
    $listing = Invoke-PicoNative -Executable (Get-PicoCli 'neopixel') -Arguments @('list')
    if ($listing.ExitCode -ne 0) { throw 'USB port enumeration failed. No serial commands were sent.' }
    foreach ($entry in $listing.Lines) {
        if ($entry -match '^(COM[1-9][0-9]*) USB c0de:(cafe|caff|cafd|cafc)\b') {
            [PSCustomObject]@{ Port = $Matches[1]; Pid = $Matches[2].ToLowerInvariant() }
        }
    }
}

function Assert-PicoStatus {
    param([string]$Text, [string]$Protocol, [switch]$RequireBootloader)
    $records = @($Text -split "`n" | Where-Object { $_ -match '^STATUS\s' })
    if ($records.Count -ne 1) { throw 'Expected exactly one firmware STATUS record.' }
    $fields = $records[0].Trim() -split '\s+'
    foreach ($key in @('protocol', 'oe_high')) {
        if (@($fields | Where-Object { $_ -match ('^' + $key + '=') }).Count -ne 1) {
            throw ('Missing or ambiguous STATUS field: ' + $key)
        }
    }
    if ($fields -notcontains ('protocol=' + $Protocol) -or $fields -notcontains 'oe_high=1') {
        throw 'Unexpected firmware identity or servo OE state. Further commands were refused.'
    }
    if ($RequireBootloader -and (@($fields | Where-Object { $_ -match '^bootloader=' }).Count -ne 1 -or $fields -notcontains 'bootloader=picotool-v1')) {
        throw 'This older firmware needs one initial BOOTSEL upload of an updated image. After that, USB updates work without pressing BOOTSEL. No bootloader command was sent.'
    }
    $records[0]
}

function Get-PicoRomParents {
    # Parent USB nodes only: exclude MI_xx interfaces and stale disconnected nodes.
    @(Get-CimInstance -ClassName Win32_PnPEntity | Where-Object {
        $_.Present -eq $true -and $_.DeviceID -match '^USB\\VID_2E8A&PID_(0003|000F)\\[^\\]+$'
    })
}

function Get-PicoBootselDrives {
    foreach ($drive in [IO.DriveInfo]::GetDrives()) {
        if (-not $drive.IsReady) { continue }
        $infoFile = Join-Path $drive.RootDirectory.FullName 'INFO_UF2.TXT'
        if (-not (Test-Path -LiteralPath $infoFile -PathType Leaf)) { continue }
        $driveInfo = Get-Content -LiteralPath $infoFile -Raw
        if ($driveInfo -match '(?im)^Model:\s*RP2350\s*$' -and $driveInfo -match '(?im)^Board-ID:\s*RP2350\s*$') {
            [PSCustomObject]@{ Root = $drive.RootDirectory.FullName; Info = $driveInfo }
        }
    }
}

function Assert-PicoUf2 {
    $metadata = Get-Content -LiteralPath $picoMetadata -Raw | ConvertFrom-Json
    $bytes = [IO.File]::ReadAllBytes($picoImage)
    $hash = (Get-FileHash -LiteralPath $picoImage -Algorithm SHA256).Hash
    if ($metadata.target -ne 'thumbv8m.main-none-eabihf' -or $metadata.family -ne '0xe48bff59' -or $metadata.sha256 -ne $hash -or $metadata.bytes -ne $bytes.Length) {
        throw 'UF2 build metadata, target, family, size or SHA-256 mismatch. Rebuild the selected firmware.'
    }
    if ($bytes.Length -eq 0 -or ($bytes.Length % 512) -ne 0) { throw 'Invalid UF2 size.' }
    $blockCount = [int]($bytes.Length / 512)
    if ($metadata.blocks -ne $blockCount) { throw 'UF2 block count differs from build metadata.' }
    $seen = @{}
    for ($offset = 0; $offset -lt $bytes.Length; $offset += 512) {
        $words = New-Object 'UInt32[]' 8
        for ($wordIndex = 0; $wordIndex -lt 8; $wordIndex++) { $words[$wordIndex] = [BitConverter]::ToUInt32($bytes, $offset + 4 * $wordIndex) }
        if ($words[0] -ne 0x0a324655 -or $words[1] -ne [Convert]::ToUInt32('9e5d5157', 16) -or [BitConverter]::ToUInt32($bytes, $offset + 508) -ne 0x0ab16f30) { throw 'Invalid UF2 block magic.' }
        if (($words[2] -band 0x2000) -eq 0 -or $words[7] -ne [Convert]::ToUInt32('e48bff59', 16)) { throw 'UF2 family must be RP2350 Arm Secure.' }
        if ($words[4] -eq 0 -or $words[4] -gt 476 -or $words[3] -lt 0x10000000 -or ([uint64]$words[3] + $words[4]) -gt 0x10400000) { throw 'UF2 payload is outside the Pico 2 flash region.' }
        if ($words[6] -ne $blockCount -or $words[5] -ge $blockCount -or $seen.ContainsKey($words[5])) { throw 'Invalid UF2 block numbering.' }
        $seen[$words[5]] = $true
    }
    $hash
}

try {
    if (-not $LogDirectory) {
        $LogDirectory = Join-Path $picoRepo ('tmp/pico-flash/' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff'))
    }
    $LogDirectory = [IO.Path]::GetFullPath($LogDirectory)
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    if ((Test-Path -LiteralPath (Join-Path $LogDirectory 'flash-transcript.txt')) -or (Test-Path -LiteralPath (Join-Path $LogDirectory 'flash-result.json'))) {
        throw 'The selected log directory already contains a flash record. Use a new directory to preserve the previous result.'
    }
    $picoLogReady = $true
    Start-Transcript -LiteralPath (Join-Path $LogDirectory 'flash-transcript.txt') | Out-Null
    $picoTranscriptStarted = $true
    Write-Host ('Flash logs: ' + $LogDirectory)

    if ($Build) {
        $buildHelper = $picoSelectedVariant.BuildHelper
        & (Join-Path $PSScriptRoot $buildHelper)
        . (Join-Path $PSScriptRoot 'Use-LocalRust.ps1')
        $hostKinds = @('neopixel', 'servo')
        if (Test-Path -LiteralPath (Join-Path $picoRepo 'tools/pico-switch-matrix-bench/Cargo.toml')) { $hostKinds += 'switch-matrix' }
        if (Test-Path -LiteralPath (Join-Path $picoRepo 'tools/pico-device-bench/Cargo.toml')) { $hostKinds += 'device' }
        foreach ($kind in $hostKinds) {
            $manifest = Join-Path $picoRepo ('tools/pico-' + $kind + '-bench/Cargo.toml')
            & cargo build --release --locked --offline --manifest-path $manifest
            if ($LASTEXITCODE -ne 0) { throw ('Host CLI build failed: ' + $kind) }
        }
    }
    foreach ($requiredFile in @($picoImage, $picoMetadata, (Get-PicoCli 'neopixel'), (Get-PicoCli 'servo'), (Get-PicoCli $picoSuffix))) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) { throw ('Required file is missing; use -Build: ' + $requiredFile) }
    }
    $picoResult.sha256 = Assert-PicoUf2
    Write-Host ('Verified UF2 SHA256: ' + $picoResult.sha256)

    $installInfo = Get-Content -LiteralPath (Join-Path $picoToolInstall 'install-info.json') -Raw | ConvertFrom-Json
    $picoExe = [IO.Path]::GetFullPath($installInfo.executable)
    if (-not $picoExe.StartsWith(([IO.Path]::GetFullPath($picoToolInstall).TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase) -or $installInfo.version -ne '2.3.1') { throw 'Unexpected local picotool installation. Run Install-PicoTool.ps1.' }
    if ((Get-FileHash -LiteralPath $picoExe -Algorithm SHA256).Hash -ne $installInfo.executable_sha256) { throw 'Local picotool executable SHA-256 mismatch.' }

    $beforePorts = @(Get-PicoPorts)
    $otherExpectedPorts = @($beforePorts | Where-Object { $_.Pid -eq $picoExpectedPid -and $_.Port -ne $Port } | ForEach-Object { $_.Port })
    if (-not $Bootsel) {
        $selectedPorts = @($beforePorts | Where-Object { $_.Port -eq $Port })
        if ($selectedPorts.Count -ne 1) { throw 'The explicit COM port is not exactly one known c0de:cafe/caff/cafd/cafc device. No serial commands were sent.' }
        $currentVariants = @($picoVariants.Values | Where-Object { $_.Pid -eq $selectedPorts[0].Pid })
        if ($currentVariants.Count -ne 1) { throw 'The current bench firmware mapping is ambiguous. No serial commands were sent.' }
        $currentKind = $currentVariants[0].Suffix
        $currentProtocol = $currentVariants[0].Protocol
        if (-not (Test-Path -LiteralPath (Get-PicoCli $currentKind) -PathType Leaf)) { throw 'The CLI for the current firmware is missing; use -Build. No serial commands were sent.' }
        $currentCli = Get-PicoCli $currentKind
        $status = Invoke-PicoNative -Executable $currentCli -Arguments @('--port', $Port, 'status')
        if ($status.ExitCode -ne 0) { throw 'Current firmware STATUS could not be verified. No bootloader command was sent.' }
        $null = Assert-PicoStatus -Text $status.Text -Protocol $currentProtocol -RequireBootloader
        if (@(Get-PicoRomParents).Count -ne 0) { throw 'A ROM-mode Pico is already connected. Disconnect the other ROM device before resetting the selected COM port.' }
        $bootRequest = Invoke-PicoNative -Executable $currentCli -Arguments @('--port', $Port, 'bootloader')
        if ($bootRequest.ExitCode -ne 0 -or $bootRequest.Text -notmatch '(?m)^OK BOOTLOADER\s*$') { throw 'STOP/BOOTLOADER acknowledgment failed. ROM entry is not assumed and no flash load was requested.' }
    }

    $romDeadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $romParents = @()
    do {
        $romParents = @(Get-PicoRomParents)
        if ($romParents.Count -gt 1) { throw 'Multiple RP-series ROM devices are connected; refusing to choose a flash target.' }
        if ($romParents.Count -eq 1) { break }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $romDeadline)
    if ($romParents.Count -ne 1) { throw 'Exactly one present RP2350 ROM USB parent is required. Inspect Windows USB permissions/drivers; no flash load was requested.' }
    if ($romParents[0].DeviceID -notmatch '^USB\\VID_2E8A&PID_000F\\([^\\]+)$') { throw 'The single ROM device is not RP2350. No flash load was requested.' }
    $romInstance = $Matches[1]
    $selection = @('--vid', '0x2e8a', '--pid', '0x000f')
    # A Windows-generated location suffix is not a USB serial descriptor.
    if ($romInstance -match '^[0-9A-Fa-f]{16,32}$') { $selection += @('--ser', $romInstance) }
    Write-Host ('Selected ROM USB parent: ' + $romParents[0].DeviceID)
    $picoResult['rom_usb_parent'] = $romParents[0].DeviceID

    # Unfiltered info exposes multiple accessible ROM devices. In 2.3.1,
    # bus/address headers appear only for multiple devices, never for a single one.
    $romInfo = Invoke-PicoNative -Executable $picoExe -Arguments @('info', '-d')
    $infoValid = $romInfo.ExitCode -eq 0 -and $romInfo.Text -notmatch 'Multiple RP-series devices' -and @([regex]::Matches($romInfo.Text, '(?m)^Device Information\s*$')).Count -eq 1 -and $romInfo.Text -match '(?im)^\s*type:\s+RP2350\b'
    if ($romInfo.Text -match 'Multiple RP-series devices') { throw 'picotool reports multiple ROM devices; no flash load was requested.' }
    if ($infoValid) {
        $selectedInfo = Invoke-PicoNative -Executable $picoExe -Arguments (@('info', '-d') + $selection)
        if ($selectedInfo.ExitCode -ne 0 -or $selectedInfo.Text -notmatch '(?im)^\s*type:\s+RP2350\b') { throw 'Selected RP2350 ROM identity was not verified; no flash load was requested.' }
        if (@(Get-PicoRomParents).Count -ne 1) { throw 'ROM device inventory changed before flashing; refusing to load.' }
        $load = Invoke-PicoNative -Executable $picoExe -Arguments (@('load', '-v', '-x', $picoImage) + $selection)
        if ($load.ExitCode -ne 0) { throw 'picotool load/verify/execute failed. Read the log before retrying; no fallback write was attempted.' }
        $picoResult.transport = 'picotool-load-verify-execute'
        $picoResult.flash_verified = $true
    } else {
        if (-not $Bootsel) { throw 'ROM USB was found, but picotool cannot verify it. If INFO_UF2.TXT is mounted, rerun with -Bootsel for the explicit mass-storage fallback; no button press is needed while already in ROM.' }
        $bootDrives = @(Get-PicoBootselDrives)
        if ($bootDrives.Count -ne 1) { throw 'Fallback requires exactly one mounted INFO_UF2.TXT with Model/Board-ID RP2350. No image was copied.' }
        if (@(Get-PicoRomParents).Count -ne 1) { throw 'ROM device inventory changed before the fallback copy.' }
        Write-Warning 'Using explicit BOOTSEL drive fallback. UF2 source/hash is verified; picotool flash readback verification is unavailable.'
        Write-Host $bootDrives[0].Info
        Copy-Item -LiteralPath $picoImage -Destination (Join-Path $bootDrives[0].Root ([IO.Path]::GetFileName($picoImage)))
        $picoResult.transport = 'bootsel-uf2-copy'
        $picoResult['bootsel_drive'] = $bootDrives[0].Root
    }

    $newDeadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $newPorts = @()
    do {
        $newPorts = @(Get-PicoPorts | Where-Object { $_.Pid -eq $picoExpectedPid -and $otherExpectedPorts -notcontains $_.Port })
        if ($newPorts.Count -gt 1) { throw 'More than one new expected CDC device appeared. Flash was attempted, but no arbitrary port was probed.' }
        if ($newPorts.Count -eq 1) { break }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $newDeadline)
    if ($newPorts.Count -ne 1) { throw 'The expected new CDC device did not appear; flash and application startup have not both been verified.' }
    $newStatus = Invoke-PicoNative -Executable (Get-PicoCli $picoSuffix) -Arguments @('--port', $newPorts[0].Port, 'status')
    if ($newStatus.ExitCode -ne 0) { throw 'New firmware CDC STATUS failed; application startup is unverified.' }
    $verifiedStatus = Assert-PicoStatus -Text $newStatus.Text -Protocol $picoExpectedProtocol -RequireBootloader
    $picoResult.application_status_verified = $true
    $picoResult.application_port = $newPorts[0].Port
    $picoResult['status'] = $verifiedStatus
    $picoResult.completed = $true
    Write-Host ('USB firmware update completed. Port: ' + $newPorts[0].Port)
    Write-Host ('Flash readback verified: ' + $picoResult.flash_verified)
} catch {
    $picoResult.error = $_.Exception.Message
    throw
} finally {
    $picoResult['finished_utc'] = [DateTime]::UtcNow.ToString('o')
    if ($picoLogReady -and $LogDirectory -and (Test-Path -LiteralPath $LogDirectory -PathType Container)) {
        $picoResult | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $LogDirectory 'flash-result.json') -Encoding UTF8
    }
    if ($picoTranscriptStarted) { Stop-Transcript | Out-Null }
}
