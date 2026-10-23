[CmdletBinding()]
param(
    [Parameter(Position=0)]
    [ValidateSet('List','Status','Scan','Sweep','Stop','Config')]
    [string]$Command = 'List',
    [string]$Port,
    [ValidateRange(500,2500)][int]$MinUs = 1000,
    [ValidateRange(500,2500)][int]$MaxUs = 2000
)

$ErrorActionPreference = 'Stop'
if (-not ('System.IO.Ports.SerialPort' -as [type])) {
    Add-Type -AssemblyName System.IO.Ports
}
$portNames = @([System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object)
if ($Command -eq 'List') {
    if ($portNames.Count -eq 0) { Write-Output 'No serial ports were enumerated.' }
    foreach ($portName in $portNames) { Write-Output $portName }
    # Read-only USB identity information when the host exposes it. No ports are opened.
    try {
        Get-CimInstance Win32_PnPEntity -Filter "Name LIKE '%(COM%'" -ErrorAction Stop |
            Select-Object Name, PNPDeviceID | Format-List
    } catch { Write-Verbose 'PnP identity details unavailable; use Device Manager to identify the Pico port.' }
    return
}
if ([string]::IsNullOrWhiteSpace($Port) -or $portNames -notcontains $Port) {
    throw 'Choose an enumerated Pico port explicitly with -Port COM8; run List first.'
}
if ($Command -eq 'Config' -and $MinUs -ge $MaxUs) { throw 'Require MinUs < MaxUs.' }
if ($Command -ne 'Config' -and ($PSBoundParameters.ContainsKey('MinUs') -or $PSBoundParameters.ContainsKey('MaxUs'))) {
    throw 'MinUs/MaxUs are accepted only for Config.'
}

$script:device = New-Object System.IO.Ports.SerialPort($Port, 115200, 'None', 8, 'One')
$script:device.ReadTimeout = 40
$script:device.WriteTimeout = 500
$script:device.NewLine = "`n"
$script:device.DtrEnable = $true
$script:device.RtsEnable = $false
$script:pending = New-Object System.Text.StringBuilder
$script:clock = [System.Diagnostics.Stopwatch]::StartNew()
$mustStop = $false

function Send-DeviceCommand([string]$Text) {
    $script:device.WriteLine($Text)
}

function Read-DeviceLine([long]$DeadlineMs) {
    while ($script:clock.ElapsedMilliseconds -lt $DeadlineMs) {
        try { $value = $script:device.ReadByte() }
        catch [System.TimeoutException] { continue }
        if ($value -lt 0) { throw 'Serial port closed.' }
        if ($value -eq 10) {
            $line = $script:pending.ToString().TrimEnd([char]13)
            [void]$script:pending.Clear()
            if ($line.Length -gt 0) { return $line }
        } else {
            if ($script:pending.Length -ge 1024) { throw 'Overlong device response.' }
            [void]$script:pending.Append([char]$value)
        }
    }
    return $null
}

function Wait-DeviceLine([string]$Prefix, [int]$TimeoutMs) {
    $deadline = $script:clock.ElapsedMilliseconds + $TimeoutMs
    while ($script:clock.ElapsedMilliseconds -lt $deadline) {
        $line = Read-DeviceLine $deadline
        if ($null -eq $line) { break }
        if ($line -ne 'OK PING') { Write-Host $line }
        if ($line.StartsWith('ERR ')) { throw $line }
        if ($line.StartsWith($Prefix)) { return $line }
    }
    throw "Timed out waiting for '$Prefix'."
}

try {
    $script:device.Open()
    # This request cannot move a servo. No other command precedes the identity check.
    Send-DeviceCommand 'status'
    $status = Wait-DeviceLine 'STATUS ' 4000
    if (($status -split '\s+') -notcontains 'protocol=servo-bench-v1') {
        throw 'Unexpected firmware identity; refusing further commands.'
    }
    switch ($Command) {
        'Status' { }
        'Stop' {
            Send-DeviceCommand 'stop'
            [void](Wait-DeviceLine 'OK STOP' 2000)
        }
        'Scan' {
            Send-DeviceCommand 'scan'
            [void](Wait-DeviceLine 'SCAN DONE ' 8000)
        }
        'Config' {
            Send-DeviceCommand "config $MinUs $MaxUs"
            [void](Wait-DeviceLine 'OK CONFIG ' 2000)
        }
        'Sweep' {
            # Explicit Sweep is the sole motion operation. The device never runs it at boot.
            $mustStop = $true
            Send-DeviceCommand 'arm'
            [void](Wait-DeviceLine 'OK ARM' 2000)
            Send-DeviceCommand 'sweep'
            $deadline = $script:clock.ElapsedMilliseconds + 120000
            $nextPing = $script:clock.ElapsedMilliseconds
            $accepted = $false
            $done = $false
            while ($script:clock.ElapsedMilliseconds -lt $deadline) {
                if ($script:clock.ElapsedMilliseconds -ge $nextPing) {
                    Send-DeviceCommand 'ping'
                    $nextPing = $script:clock.ElapsedMilliseconds + 200
                }
                $line = Read-DeviceLine ([Math]::Min($nextPing, $deadline))
                if ($null -eq $line) { continue }
                if ($line -ne 'OK PING') { Write-Host $line }
                if ($line -eq 'OK SWEEP') { $accepted = $true }
                if ($line.StartsWith('ERR ') -or $line.StartsWith('EVENT STOP ')) { throw $line }
                if ($line -eq 'EVENT DONE' -and $accepted) { $done = $true; break }
            }
            if (-not $done) { throw 'Sweep timed out.' }
            Send-DeviceCommand 'stop'
            [void](Wait-DeviceLine 'OK STOP' 2000)
            $mustStop = $false
        }
    }
} finally {
    if ($mustStop -and $script:device.IsOpen) {
        try { Send-DeviceCommand 'stop' } catch { Write-Warning 'STOP delivery failed; firmware lease timeout must stop the outputs.' }
    }
    if ($script:device.IsOpen) { $script:device.Close() }
    $script:device.Dispose()
    $script:clock.Stop()
}
