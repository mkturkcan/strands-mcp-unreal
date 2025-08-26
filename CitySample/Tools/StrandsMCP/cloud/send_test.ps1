Param(
  [string]$InvokeUrl = "https://duk8nab8xj.execute-api.us-west-2.amazonaws.com/invoke",
  [string]$Prompt = "Make the character jump once"
)

$ErrorActionPreference = "Stop"

$ts = Get-Date -Format yyyyMMddHHmmss
$rid = "req-$ts"
$sid = "session-$ts"

$body = @{
  prompt    = $Prompt
  requestId = $rid
  sessionId = $sid
}

$json = $body | ConvertTo-Json -Compress

Write-Host "RequestId=$rid"

try {
  $resp = Invoke-RestMethod -Method Post -Uri $InvokeUrl -ContentType "application/json" -Body $json
  $resp | ConvertTo-Json -Depth 5
} catch {
  Write-Host "Error: $($_.Exception.Message)"
  if ($_.Exception.Response -and $_.Exception.Response.GetResponseStream()) {
    $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
    $reader.ReadToEnd()
  }
  exit 1
}
