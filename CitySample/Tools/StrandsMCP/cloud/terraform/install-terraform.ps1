# Requires: PowerShell 5+ on Windows Server 2022
# Installs Terraform to C:\Terraform and prints its version

$ErrorActionPreference = "Stop"

$version = "1.9.5"
$url = "https://releases.hashicorp.com/terraform/$version/terraform_${version}_windows_amd64.zip"
$zip = Join-Path $env:TEMP "terraform_$version.zip"
$dest = "C:\Terraform"

Write-Host "Downloading Terraform $version from $url ..."
Invoke-WebRequest -Uri $url -OutFile $zip

Write-Host "Creating destination folder $dest ..."
New-Item -ItemType Directory -Force -Path $dest | Out-Null

Write-Host "Expanding archive to $dest ..."
Expand-Archive -Path $zip -DestinationPath $dest -Force

Write-Host "Cleaning up zip ..."
Remove-Item $zip -Force

Write-Host "Terraform installed to $dest"
& "$dest\terraform.exe" -version
