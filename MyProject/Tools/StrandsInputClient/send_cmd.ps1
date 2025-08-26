param(
    [string]$Server = '127.0.0.1',
    [int]$Port = 17777,
    [ValidateSet('move','look','jump','sprint')]
    [string]$Cmd,
    [double]$Forward = 0.0,
    [double]$Right = 0.0,
    [double]$Duration = [double]::NaN,
    [double]$YawRate = 0.0,
    [double]$PitchRate = 0.0,
    [Nullable[bool]]$Enabled = $null,
    [int]$HoldMs = 50
)

try {
    $data = @{ cmd = $Cmd }

    switch ($Cmd) {
        'move' {
            $data.forward = $Forward
            $data.right = $Right
            if (-not [double]::IsNaN($Duration)) { $data.duration = $Duration }
        }
        'look' {
            $data.yawRate = $YawRate
            $data.pitchRate = $PitchRate
            if (-not [double]::IsNaN($Duration)) { $data.duration = $Duration }
        }
        'jump' {
            # no extra fields
        }
        'sprint' {
            if ($Enabled -ne $null) { $data.enabled = [bool]$Enabled } else {
                throw "For 'sprint', please pass -Enabled \$true or \$false."
            }
        }
        default {
            throw "Unknown cmd '$Cmd'"
        }
    }

    $json = $data | ConvertTo-Json -Compress
    $line = $json + "`n"

    $client = New-Object System.Net.Sockets.TcpClient
    $client.Connect($Server, $Port)
    try {
        $stream = $client.GetStream()
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($line)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush()
        if ($HoldMs -gt 0) { Start-Sleep -Milliseconds $HoldMs }
    }
    finally {
        if ($null -ne $stream) { $stream.Dispose() }
        $client.Close()
    }

    Write-Output "Sent: $json"
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
