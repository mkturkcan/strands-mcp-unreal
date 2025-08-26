param(
    [string]$ProjectRoot = "C:\Users\Administrator\Documents\Unreal Projects\MyProject",
    [string]$Region = "us-east-1",
    [string]$AccessKey,
    [string]$SecretKey,
    [string]$SessionToken = "",
    [string]$Key = "strands/StrandsInputServer-UE5.6-0.1.0.zip"
)

$ErrorActionPreference = 'Stop'
$outFile = Join-Path $ProjectRoot 'S3_Upload_Result.txt'

try {
    # Generate globally-unique bucket name (lowercase, hyphens only)
    $bucket = ('strands-input-server-ue56-{0}-{1}' -f (Get-Date -Format 'yyyyMMddHHmmss'), (Get-Random -Maximum 100000))

    # Call packaging + upload script with explicit bucket
    & (Join-Path $ProjectRoot 'Tools\StrandsInputClient\PackageAndUpload-Strands.ps1') `
        -ProjectRoot $ProjectRoot `
        -Region $Region `
        -AccessKey $AccessKey `
        -SecretKey $SecretKey `
        -SessionToken $SessionToken `
        -Bucket $bucket `
        -Key $Key

    $lines = @(
        "Status: Success"
        "Bucket: $bucket"
        "Key: $Key"
        "Region: $Region"
        ("S3 URI: s3://{0}/{1}" -f $bucket, $Key)
    )
    $lines -join "`r`n" | Out-File -FilePath $outFile -Encoding UTF8
    Write-Host "Wrote result to $outFile"
}
catch {
    $lines = @(
        "Status: Error"
        ("Message: {0}" -f $_.Exception.Message)
    )
    $lines -join "`r`n" | Out-File -FilePath $outFile -Encoding UTF8
    exit 1
}
