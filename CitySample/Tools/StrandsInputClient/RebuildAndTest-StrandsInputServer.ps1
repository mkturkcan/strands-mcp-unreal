param(
    [string]$ProjectPath = "C:\Users\Administrator\Documents\Unreal Projects\MyProject\MyProject.uproject",
    [string]$Map = "/Game/ThirdPerson/Lvl_ThirdPerson",
    [int]$HoldMs = 100
)

$ErrorActionPreference = 'Stop'

function Find-BuildBat {
    $bat = Get-ChildItem -Path 'C:\Program Files\Epic Games' -Recurse -Filter Build.bat -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -like '*\Engine\Build\BatchFiles\Build.bat' } |
        Select-Object -First 1 -ExpandProperty FullName
    if (-not $bat) { throw "Unreal Build.bat not found under C:\Program Files\Epic Games" }
    return $bat
}

function Find-UnrealEditorExe {
    $ue = Get-ChildItem -Path 'C:\Program Files\Epic Games' -Recurse -Filter UnrealEditor.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -like '*\Engine\Binaries\Win64\UnrealEditor.exe' } |
        Select-Object -First 1 -ExpandProperty FullName
    if (-not $ue) { throw "UnrealEditor.exe not found under C:\Program Files\Epic Games" }
    return $ue
}

$root = Split-Path $ProjectPath -Parent
$plugin = Join-Path $root 'Plugins\StrandsInputServer'
$log = Join-Path $root 'Saved\Logs\MyProject.log'
$client = Join-Path $root 'Tools\StrandsInputClient\send_cmd.ps1'

Write-Host "Stopping Unreal Editor if running..."
Get-Process -Name 'UnrealEditor','UnrealEditor-Cmd' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Write-Host "Cleaning plugin binaries to force rebuild..."
Remove-Item -Recurse -Force (Join-Path $plugin 'Binaries') -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force (Join-Path $plugin 'Intermediate') -ErrorAction SilentlyContinue

$buildBat = Find-BuildBat
Write-Host "Using Build.bat: $buildBat"

Write-Host "Building MyProjectEditor (Development Win64)..."
$out = Join-Path $root 'Saved\Logs\UBT-Build-Strands.log'
& $buildBat MyProjectEditor Win64 Development -Project="$ProjectPath" -WaitMutex -FromMsBuild *>&1 | Tee-Object -FilePath $out
if ($LASTEXITCODE -ne 0) { throw "UBT build failed with code $LASTEXITCODE (see $out)" }
Write-Host "Build succeeded. UBT log: $out"

$ue = Find-UnrealEditorExe
Write-Host "Launching UnrealEditor game session..."
$args = "`"$ProjectPath`" $Map -game -log -windowed -ResX=1280 -ResY=720"
Start-Process -FilePath $ue -ArgumentList $args

Write-Host "Waiting for StrandsInputServer to listen..."
for ($i=0; $i -lt 120; $i++) {
    if (Test-Path $log) {
        $tail = Get-Content -Path $log -Tail 400 -ErrorAction SilentlyContinue
        if ($tail -match 'StrandsInputServer: Listening on 127\.0\.0\.1') {
            Write-Host "Server listening detected."
            break
        }
    }
    Start-Sleep -Milliseconds 500
}

if (-not (Test-Path $client)) { throw "Client script not found at $client" }

Write-Host "Sending test commands (jump, move, look)..."
powershell -NoProfile -ExecutionPolicy Bypass -File $client -Cmd jump -HoldMs $HoldMs
Start-Sleep -Milliseconds 500
powershell -NoProfile -ExecutionPolicy Bypass -File $client -Cmd move -Forward 1 -Duration 1 -HoldMs $HoldMs
Start-Sleep -Milliseconds 500
powershell -NoProfile -ExecutionPolicy Bypass -File $client -Cmd look -YawRate 90 -Duration 1 -HoldMs $HoldMs

Write-Host "Recent log tail (should include 'Received cmd' and 'Jumping'):"
if (Test-Path $log) {
    Get-Content -Path $log -Tail 400
} else {
    Write-Warning "Log file not found: $log"
}
