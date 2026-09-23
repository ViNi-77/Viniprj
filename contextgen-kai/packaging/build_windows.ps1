# 通常ビルド: Gitで取得したOCRを検査して同梱する。OCR単体の再構築はbuild_ocr_windows.ps1。
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
& python packaging/verify_ocr_bundle.py --root ocr
if ($LASTEXITCODE -ne 0) { throw 'Git-bundled OCR verification failed; restore ocr from Git before building' }
& python -m PyInstaller --noconfirm --clean packaging/windows.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
$Dist = Join-Path $ProjectRoot 'dist\ContextgenKai'
$Ocr = Join-Path $Dist 'ocr'
$Licenses = Join-Path $Dist 'THIRD_PARTY_LICENSES'
Copy-Item "$ProjectRoot\ocr" $Ocr -Recurse -Force
New-Item -ItemType Directory -Force $Licenses | Out-Null
Copy-Item "$Ocr\licenses\*" $Licenses -Force
& python packaging/collect_python_licenses.py "$Licenses\python"
if ($LASTEXITCODE -ne 0) { throw 'Dependency notices failed' }
Copy-Item "$PSScriptRoot\WINDOWS_README.txt" "$Dist\最初にお読みください.txt"
$RootFiles = @('README.md', '仕様書兼要件定義書.md', 'アプリ概要とバージョン履歴.md', 'アプリ基本設計基準書.md',
    'contextgen改_操作マニュアル.html', '起動.bat', '更新.bat', 'start_windows.bat', 'update_windows.bat', 'IMPLEMENTATION_CONTRACT.md')
foreach ($File in $RootFiles) {
    if (-not (Test-Path "$ProjectRoot\$File")) { throw "Distribution document or entry point is missing: $File" }
    Copy-Item "$ProjectRoot\$File" "$Dist\$File" -Force
}
foreach ($Folder in @('docs', 'images')) {
    Copy-Item "$ProjectRoot\$Folder" "$Dist\$Folder" -Recurse -Force
}
$Bundle = Get-Content "$Ocr\BUNDLE-MANIFEST.json" -Raw | ConvertFrom-Json
$Version = (& python -c 'from contextgen_kai import __version__; print(__version__)').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot read application version' }
$Manifest = @{
    application = 'contextgen-kai'; version = $Version; source_revision = (& git -C $ProjectRoot rev-parse HEAD).Trim();
    ocr_origin = 'git-bundled'; ocr_bundle_manifest_sha256 = (Get-FileHash "$Ocr\BUNDLE-MANIFEST.json" -Algorithm SHA256).Hash.ToLower();
    vcpkg_commit = $Bundle.vcpkg_commit; tesseract = $Bundle.tesseract_version;
    tesseract_process_code_page = $Bundle.process_code_page; tesseract_sha256 = $Bundle.files.'tesseract.exe'.sha256;
    tessdata_commit = $Bundle.tessdata_commit; ocr_build_origin = $Bundle.origin
}
$Manifest | ConvertTo-Json -Depth 8 | Set-Content "$Dist\BUILD-MANIFEST.json" -Encoding utf8
# 開発環境のPATHを外した状態で、EXEと日本語・英語データの同梱を確認する。
$OldPath = $env:PATH
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    & "$Ocr\tesseract.exe" --version
    if ($LASTEXITCODE -ne 0) { throw 'Bundled OCR cannot start without developer PATH' }
    $Languages = & "$Ocr\tesseract.exe" --list-langs --tessdata-dir "$Ocr\tessdata"
    if ($LASTEXITCODE -ne 0 -or $Languages -notcontains 'jpn' -or $Languages -notcontains 'eng') {
        throw 'Bundled Japanese-English OCR data cannot load'
    }
} finally { $env:PATH = $OldPath }
