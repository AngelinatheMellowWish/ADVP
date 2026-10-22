# Build the Word requirements document and update its TOC/page fields.
# Requires Microsoft Word for the field update; falls back gracefully.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/build_docx.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/build_docx.ps1 -Pdf

param(
    [switch]$Pdf
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$docx = Join-Path $root "docs\需求说明书.docx"

Push-Location $root
try {
    & python scripts/build_docx.py
    if ($LASTEXITCODE -ne 0) {
        throw "build_docx.py failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $doc = $word.Documents.Open($docx, $false, $false)
    $doc.Fields.Update() | Out-Null
    foreach ($toc in $doc.TablesOfContents) {
        $toc.Update() | Out-Null
    }
    $doc.Save()
    if ($Pdf) {
        $pdfPath = Join-Path $root "docs\需求说明书.pdf"
        $doc.ExportAsFixedFormat($pdfPath, 17)
        Write-Host "OK: preview PDF $pdfPath"
    }
    $doc.Close($false)
    try { $word.Quit() } catch { }
    Write-Host "OK: Word fields and TOC updated"
} catch {
    Write-Warning "Word COM unavailable; the DOCX is valid but its TOC will update when opened in Word. $($_.Exception.Message)"
}

Write-Host "Done. Remember to run scripts/check_version.py before committing."
