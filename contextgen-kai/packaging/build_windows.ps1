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
& python -m PyInstaller --noconfirm --clean packaging/windows.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
$Dist = Join-Path $ProjectRoot 'dist\ContextgenKai'
$Ocr = Join-Path $Dist 'ocr'
$Tessdata = Join-Path $Ocr 'tessdata'
$Licenses = Join-Path $Dist 'THIRD_PARTY_LICENSES'
New-Item -ItemType Directory -Force $Ocr,$Tessdata,$Licenses | Out-Null
Copy-Item "$InstallRoot\x64-contextgen-static\tools\tesseract\*" $Ocr -Recurse -Force
# 全ビルド依存関係の upstream copyright を保持する。
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
& python packaging/collect_python_licenses.py "$Licenses\python"
if ($LASTEXITCODE -ne 0) { throw 'Dependency notices failed' }
Copy-Item "$PSScriptRoot\WINDOWS_README.txt" "$Dist\最初にお読みください.txt"
Copy-Item "$ProjectRoot\docs" "$Dist\docs" -Recurse
Copy-Item "$ProjectRoot\start_windows.bat" "$Dist\start_windows.bat"
$Manifest = @{ application = 'contextgen-kai'; version = '0.1.0'; vcpkg_commit = $ExpectedRevision; tesseract = '5.5.1'; tessdata_commit = $DataRevision; hashes = $Hashes }
$Manifest | ConvertTo-Json -Depth 5 | Set-Content "$Dist\BUILD-MANIFEST.json" -Encoding utf8
# 環境 PATH 上の OCR/DLL に依存せず起動できることを確認する。
$OldPath = $env:PATH
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    & "$Ocr\tesseract.exe" --version
    if ($LASTEXITCODE -ne 0) { throw 'Bundled OCR cannot start without developer PATH' }
    & "$Ocr\tesseract.exe" --list-langs --tessdata-dir "$Tessdata"
    if ($LASTEXITCODE -ne 0) { throw 'Bundled tessdata cannot load' }
} finally { $env:PATH = $OldPath }
