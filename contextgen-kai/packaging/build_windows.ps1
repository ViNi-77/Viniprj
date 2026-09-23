# 通常ビルド: Gitで取得したOCRを検査して同梱する。OCR単体の再構築はbuild_ocr_windows.ps1。
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
& python packaging/verify_ocr_bundle.py --root ocr
if ($LASTEXITCODE -ne 0) { throw 'Git-bundled OCR verification failed; restore ocr from Git before building' }
& python -m PyInstaller --noconfirm --clean packaging/windows.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
$Dist = Join-Path $ProjectRoot 'dist\ContextgenKai'
$Internal = Join-Path $Dist '_internal'
$Ocr = Join-Path $Internal 'ocr'
$Licenses = Join-Path $Internal 'THIRD_PARTY_LICENSES'
$ManualImages = Join-Path $Internal 'manual\images'
$BuildOutput = Join-Path $ProjectRoot 'build'
New-Item -ItemType Directory -Force $Ocr, "$Ocr\tessdata", $Licenses, $ManualImages, $BuildOutput | Out-Null
# 通常利用に必要なOCR実行材だけを配置し、Git用の来歴・検査文書は配布しない。
Copy-Item "$ProjectRoot\ocr\tesseract.exe" "$Ocr\tesseract.exe" -Force
foreach ($File in @('eng.traineddata', 'jpn.traineddata', 'LICENSE')) {
    Copy-Item "$ProjectRoot\ocr\tessdata\$File" "$Ocr\tessdata\$File" -Force
}
Copy-Item "$ProjectRoot\ocr\licenses\*" $Licenses -Force
Copy-Item "$ProjectRoot\ocr\tessdata\LICENSE" "$Licenses\tessdata-LICENSE.txt" -Force
# フォルダ選択で使うTcl/Tkの権利表示も同じ場所へ集約し、元の付属文書は残す。
$TclPatch = (& python -c 'import tkinter, sys; print(tkinter.Tcl().eval(sys.argv[1]))' 'info patchlevel').Trim()
if ($LASTEXITCODE -ne 0 -or $TclPatch -notmatch '^\d+\.\d+\.\d+$') { throw 'Cannot identify bundled Tcl version' }
$TclLibrary = (& python -c 'import tkinter, sys; print(tkinter.Tcl().eval(sys.argv[1]))' 'info library').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot locate Tcl runtime data' }
$PythonPrefix = (& python -c 'import sys; print(sys.base_prefix)').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot locate Python runtime' }
$TclNotice = @((Join-Path $TclLibrary 'license.terms'), (Join-Path $PythonPrefix 'docs\license.tcltk')) |
    Where-Object { Test-Path $_ -PathType Leaf } | Select-Object -First 1
if ($TclNotice) {
    Copy-Item $TclNotice "$Licenses\Tcl-LICENSE.txt" -Force
    $TclNoticeOrigin = 'Python runtime Tcl license.terms'
} else {
    # Windows Pythonで原文が省略されている場合だけ、実行材と同じ正式版の原文をビルド時に取得する。
    $TclTag = 'core-' + $TclPatch.Replace('.', '-')
    $TclNoticeOrigin = "https://raw.githubusercontent.com/tcltk/tcl/$TclTag/license.terms"
    Invoke-WebRequest -UseBasicParsing -Uri $TclNoticeOrigin -OutFile "$Licenses\Tcl-LICENSE.txt" -TimeoutSec 60
}
$TclNoticeText = [System.IO.File]::ReadAllText("$Licenses\Tcl-LICENSE.txt")
if ($TclNoticeText -notmatch 'copyrighted' -or $TclNoticeText -notmatch 'permission to use, copy, modify, distribute') { throw 'Invalid Tcl license document' }
$TkNotice = Join-Path $Internal '_tk_data\license.terms'
if (-not (Test-Path $TkNotice -PathType Leaf)) { throw 'Bundled Tk license document is missing' }
Copy-Item $TkNotice "$Licenses\Tk-LICENSE.txt" -Force
& python packaging/collect_python_licenses.py "$Licenses\python"
if ($LASTEXITCODE -ne 0) { throw 'Dependency notices failed' }
Copy-Item "$PSScriptRoot\WINDOWS_README.txt" "$Dist\最初にお読みください.txt" -Force
$ManualName = 'contextgen改_操作マニュアル.html'
$Manual = [System.IO.File]::ReadAllText("$ProjectRoot\$ManualName", [System.Text.Encoding]::UTF8)
# ソースのHTMLはimages/を維持し、配布HTMLだけ相対参照を_internalへ合わせる。
$Manual = $Manual.Replace('src="images/', 'src="_internal/manual/images/').Replace("src='images/", "src='_internal/manual/images/")
$Manual = $Manual.Replace('href="images/', 'href="_internal/manual/images/').Replace("href='images/", "href='_internal/manual/images/")
[System.IO.File]::WriteAllText("$Dist\$ManualName", $Manual, ([System.Text.UTF8Encoding]::new($false)))
# APIと同一の13枚+JS許可リストだけをコピー。撮影記録や追加PNGを自動では混ぜない。
$ManualAssets = @(& python -c 'from contextgen_kai.api import MANUAL_ASSETS; print(chr(10).join(sorted(MANUAL_ASSETS)))')
if ($LASTEXITCODE -ne 0) { throw 'Cannot read manual asset allowlist' }
foreach ($Asset in $ManualAssets) {
    if (-not (Test-Path "$ProjectRoot\images\$Asset" -PathType Leaf)) { throw "Manual asset is missing: $Asset" }
    Copy-Item "$ProjectRoot\images\$Asset" "$ManualImages\$Asset" -Force
}
# 利用者に見える直下はこの4点に限定する。旧構成の取り残しもビルド失敗にする。
$AllowedRoot = @('ContextgenKai.exe', $ManualName, '最初にお読みください.txt', '_internal')
$ActualRoot = @(Get-ChildItem $Dist -Force | ForEach-Object { $_.Name })
if (Compare-Object $AllowedRoot $ActualRoot) { throw 'Unexpected files in user distribution root' }
$Bundle = Get-Content "$ProjectRoot\ocr\BUNDLE-MANIFEST.json" -Raw | ConvertFrom-Json
$Version = (& python -c 'from contextgen_kai import __version__; print(__version__)').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot read application version' }
$Manifest = @{
    application = 'contextgen-kai'; version = $Version; source_revision = (& git -C $ProjectRoot rev-parse HEAD).Trim();
    distribution_layout = 'user-root-four-items';
    tcl_version = $TclPatch; tcl_license_source = $TclNoticeOrigin;
    tcl_license_sha256 = (Get-FileHash "$Licenses\Tcl-LICENSE.txt" -Algorithm SHA256).Hash.ToLower();
    tk_license_sha256 = (Get-FileHash "$Licenses\Tk-LICENSE.txt" -Algorithm SHA256).Hash.ToLower();
    ocr_origin = 'git-bundled'; ocr_bundle_manifest_sha256 = (Get-FileHash "$ProjectRoot\ocr\BUNDLE-MANIFEST.json" -Algorithm SHA256).Hash.ToLower();
    vcpkg_commit = $Bundle.vcpkg_commit; tesseract = $Bundle.tesseract_version;
    tesseract_process_code_page = $Bundle.process_code_page; tesseract_sha256 = $Bundle.files.'tesseract.exe'.sha256;
    tessdata_commit = $Bundle.tessdata_commit; ocr_build_origin = $Bundle.origin
}
# ビルド来歴は開発者向け検証成果物へ。利用者ZIPには混在させない。
$Manifest | ConvertTo-Json -Depth 8 | Set-Content "$BuildOutput\BUILD-MANIFEST.json" -Encoding utf8
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
