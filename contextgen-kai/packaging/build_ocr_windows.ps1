# OCR自体の更新時のみ使用。通常の配布ビルドはGit同梱OCRを使う。
param([Parameter(Mandatory=$true)][string]$VcpkgRoot)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$VcpkgRoot = (Resolve-Path $VcpkgRoot).Path
$ExpectedRevision = 'ef7dbf94b9198bc58f45951adcf1f041fcbc5ea0'
$Revision = (& git -C $VcpkgRoot rev-parse HEAD).Trim()
if ($Revision -ne $ExpectedRevision) { throw "vcpkg revision mismatch: $Revision" }
& "$VcpkgRoot\bootstrap-vcpkg.bat" -disableMetrics
if ($LASTEXITCODE -ne 0) { throw 'vcpkg bootstrap failed' }
$InstallRoot = Join-Path $ProjectRoot 'build\vcpkg-installed'
& "$VcpkgRoot\vcpkg.exe" install 'tesseract:x64-contextgen-static' "--overlay-triplets=$PSScriptRoot\triplets" "--x-install-root=$InstallRoot" --disable-metrics
if ($LASTEXITCODE -ne 0) { throw 'Tesseract source build failed' }
$Ocr = Join-Path $ProjectRoot 'build\ocr-native'
if (Test-Path $Ocr) { Remove-Item $Ocr -Recurse -Force }
$Tessdata = Join-Path $Ocr 'tessdata'
$Licenses = Join-Path $Ocr 'licenses'
New-Item -ItemType Directory -Force $Ocr,$Tessdata,$Licenses | Out-Null
Copy-Item "$InstallRoot\x64-contextgen-static\tools\tesseract\tesseract.exe" $Ocr
# Native CRTのnarrow argv/fopenをUTF-8に統一。元の権限・互換性情報は保持。
$SdkBin = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
$Mt = Get-ChildItem $SdkBin -Directory | Sort-Object Name -Descending | ForEach-Object {
    $Candidate = Join-Path $_.FullName 'x64\mt.exe'
    if (Test-Path $Candidate) { $Candidate }
} | Select-Object -First 1
if (-not $Mt) { throw 'Windows SDK mt.exe was not found' }
$TesseractExe = Join-Path $Ocr 'tesseract.exe'
$OriginalManifest = Join-Path $ProjectRoot 'build\tesseract-original.manifest'
$VerifiedManifest = Join-Path $ProjectRoot 'build\tesseract-embedded.manifest'
& $Mt "-inputresource:$TesseractExe;#1" "-out:$OriginalManifest" -nologo
if ($LASTEXITCODE -ne 0) { throw 'Cannot preserve the existing Tesseract manifest' }
& $Mt -manifest $OriginalManifest "$PSScriptRoot\tesseract-utf8.manifest" "-outputresource:$TesseractExe;#1" -nologo
if ($LASTEXITCODE -ne 0) { throw 'UTF-8 process manifest merge failed' }
& $Mt "-inputresource:$TesseractExe;#1" "-out:$VerifiedManifest" -nologo
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify the embedded manifest' }
[xml]$ManifestXml = Get-Content $VerifiedManifest -Raw
$CodePageNode = $ManifestXml.SelectSingleNode("//*[local-name()='activeCodePage']")
if (-not $CodePageNode -or $CodePageNode.InnerText -ne 'UTF-8') { throw 'UTF-8 process code page is missing' }
Get-ChildItem "$InstallRoot\x64-contextgen-static\share" -Directory | ForEach-Object {
    $Copyright = Join-Path $_.FullName 'copyright'
    if (Test-Path $Copyright) { Copy-Item $Copyright (Join-Path $Licenses ($_.Name + '-LICENSE.txt')) }
}
$DataRevision = '65727574dfcd264acbb0c3e07860e4e9e9b22185'
$Hashes = @{
    'eng.traineddata' = '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2';
    'jpn.traineddata' = '1f5de9236d2e85f5fdf4b3c500f2d4926f8d9449f28f5394472d9e8d83b91b4d';
    'LICENSE' = 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30'
}
foreach ($File in $Hashes.Keys) {
    $Target = Join-Path $Tessdata $File
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/$DataRevision/$File" -OutFile $Target
    if ((Get-FileHash $Target -Algorithm SHA256).Hash.ToLower() -ne $Hashes[$File]) { throw "Checksum mismatch: $File" }
}
$Files = @{}
Get-ChildItem $Ocr -Recurse -File | ForEach-Object {
    $Relative = $_.FullName.Substring($Ocr.Length + 1).Replace('\','/')
    $Files[$Relative] = @{ sha256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(); size = $_.Length }
}
$Manifest = @{
    schema_version = 1; platform = 'windows-x64'; tesseract_version = '5.5.1'; process_code_page = 'UTF-8';
    vcpkg_commit = $ExpectedRevision; tessdata_commit = $DataRevision;
    origin = @{ kind = 'native-rebuild'; source_revision = (& git -C $ProjectRoot rev-parse HEAD).Trim() };
    files = $Files
}
$Manifest | ConvertTo-Json -Depth 8 | Set-Content "$Ocr\BUNDLE-MANIFEST.json" -Encoding utf8
& python packaging/verify_ocr_bundle.py --root $Ocr
if ($LASTEXITCODE -ne 0) { throw 'Rebuilt OCR verification failed' }
Write-Host "Rebuilt OCR is in $Ocr. Review it and test on Windows before replacing the Git-tracked ocr folder."
