param(
    [string]$ProjectRoot = "C:\Users\Administrator\Documents\Unreal Projects\MyProject",
    [string]$Region = "us-east-1",
    [string]$AccessKey,
    [string]$SecretKey,
    [string]$SessionToken = "",
    [string]$Bucket = "",
    [string]$Key = "strands/StrandsInputServer-UE5.6-0.1.0.zip"
)

$ErrorActionPreference = 'Stop'

function New-PluginZip {
    param([string]$Root, [string]$ZipPath)

    if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }

    $items = @(
        (Join-Path $Root 'Plugins\StrandsInputServer\StrandsInputServer.uplugin'),
        (Join-Path $Root 'Plugins\StrandsInputServer\README.md'),
        (Join-Path $Root 'Plugins\StrandsInputServer\Source'),
        (Join-Path $Root 'Plugins\StrandsInputServer\Config'),
        (Join-Path $Root 'Tools\StrandsInputClient\send_cmd.ps1'),
        (Join-Path $Root 'Tools\StrandsInputClient\send_cmd.py'),
        (Join-Path $Root 'Tools\StrandsInputClient\RebuildAndTest-StrandsInputServer.ps1')
    )

    # Ensure required files/folders exist
    foreach ($p in $items) {
        if (-not (Test-Path $p)) {
            Write-Warning "Path missing (skipping): $p"
        }
    }

    Compress-Archive -Path $items -DestinationPath $ZipPath -CompressionLevel Optimal
    Write-Host "Created bundle:" $ZipPath
}

function Resolve-AwsExe {
    $candidate = $null
    $cmd = Get-Command aws -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Path) {
        return $cmd.Path
    }
    $paths = @(
        "C:\Program Files\Amazon\AWSCLIV2\aws.exe",
        "C:\Program Files\Amazon\AWSCLIV2\aws.cmd",
        "C:\Program Files\Amazon\AWSCLIV2\aws"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { return $p }
    }
    return $null
}
function Ensure-AwsCli {
    $aws = Resolve-AwsExe
    if (-not $aws) {
        throw "AWS CLI not found. Please install AWS CLI v2."
    }
    return $aws
}

function New-UniqueBucketName {
    param([string]$Prefix = 'strands-input-server-ue56')
    $ts = Get-Date -Format 'yyyyMMddHHmmss'
    $rand = Get-Random -Maximum 100000
    return ("{0}-{1}-{2}" -f $Prefix, $ts, $rand).ToLower()
}

# 1) Create zip
$zip = Join-Path $ProjectRoot 'StrandsInputServer-UE5.6-0.1.0.zip'
New-PluginZip -Root $ProjectRoot -ZipPath $zip

# 2) Setup AWS env (scoped to this process)
$env:AWS_ACCESS_KEY_ID = $AccessKey
$env:AWS_SECRET_ACCESS_KEY = $SecretKey
$env:AWS_DEFAULT_REGION = $Region
if ($SessionToken) { $env:AWS_SESSION_TOKEN = $SessionToken }

# 3) Check CLI
$AwsExe = Ensure-AwsCli

# 4) Bucket (generate if not provided)
if (-not $Bucket -or $Bucket.Trim().Length -eq 0) {
    $Bucket = New-UniqueBucketName
}

# 5) Create bucket (handle us-east-1 special case)
if ($Region -eq 'us-east-1') {
    & $AwsExe s3api create-bucket --bucket $Bucket | Out-Null
} else {
    & $AwsExe s3api create-bucket --bucket $Bucket --create-bucket-configuration LocationConstraint=$Region | Out-Null
}
Write-Host "Created bucket:" $Bucket "in region" $Region

# 6) Upload object (private)
$uri = "s3://{0}/{1}" -f $Bucket, $Key
& $AwsExe s3 cp $zip $uri --acl private | Out-Null
Write-Host "Uploaded to:" $uri

# 7) Output summary (no secrets)
"Bucket: $Bucket"
"Key: $Key"
"S3 URI: $uri"

# 8) Clear env secrets
$env:AWS_ACCESS_KEY_ID = ""
$env:AWS_SECRET_ACCESS_KEY = ""
$env:AWS_SESSION_TOKEN = ""
