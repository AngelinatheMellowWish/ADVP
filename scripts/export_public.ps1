# Export a sanitized public snapshot of ADVP.
# The canonical full repository stays private. This script copies only allowlisted
# paths, scans for secrets/absolute paths, runs gitleaks if available, and creates
# a fresh Git repository with a version tag. It never pushes automatically.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/export_public.ps1 -Target ..\advp-public
#   powershell -ExecutionPolicy Bypass -File scripts/export_public.ps1 -Target ..\exports\advp-public -Force -NoGit

param(
    [Parameter(Mandatory = $true)][string]$Target,
    [switch]$Force,
    [switch]$NoGit
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$version = (Get-Content -LiteralPath (Join-Path $root "VERSION") -Raw).Trim()

$targetPath = if ([System.IO.Path]::IsPathRooted($Target)) {
    [System.IO.Path]::GetFullPath($Target)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $root $Target))
}

if ($targetPath.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Target must be outside the source repository: $targetPath"
}
if (Test-Path -LiteralPath $targetPath) {
    if (-not $Force) {
        throw "Target already exists: $targetPath (use -Force to replace)"
    }
    Remove-Item -LiteralPath $targetPath -Recurse -Force
}
New-Item -ItemType Directory -Path $targetPath | Out-Null

$excludeDirs = @(
    "node_modules", ".venv", "venv", ".git", "logs", "workspace", "data",
    "derived", "exports", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "build", "dist", "coverage", ".idea", ".vscode"
)
$excludeFiles = @("api_key.txt", ".env", "*.local", "~`$*")

function Copy-AllowlistedDirectory {
    param([string]$Relative)
    $source = Join-Path $root $Relative
    if (-not (Test-Path -LiteralPath $source)) { return }
    $dest = Join-Path $targetPath $Relative
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    & robocopy $source $dest /E /NFL /NDL /NJH /NJS /NP /XD @excludeDirs /XF @excludeFiles | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed for $Relative (exit $LASTEXITCODE)"
    }
}

$directories = @("docs", "scripts", ".github", "examples", "src", "backend", "frontend")
foreach ($dir in $directories) {
    Copy-AllowlistedDirectory -Relative $dir
}

$files = @(
    "README.md", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "VERSION",
    "CHANGELOG.md", "SECURITY.md", "CONTRIBUTING.md", ".gitignore",
    ".gitattributes", ".env.example", "package.json", "package-lock.json",
    "commitlint.config.cjs", ".markdownlint.json"
)
foreach ($file in $files) {
    $source = Join-Path $root $file
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $targetPath $file) -Force
    }
}

# Remove local-only artifacts that may have slipped through.
Get-ChildItem -LiteralPath $targetPath -Recurse -Force -File |
    Where-Object {
        $_.Name -eq "api_key.txt" -or
        $_.Name -eq ".env" -or
        $_.Name -like "~`$*" -or
        $_.FullName -match "\\logs\\" -or
        $_.FullName -match "\\data\\"
    } |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }

# Sanitization scan.
$textExtensions = @(
    ".md", ".txt", ".py", ".ps1", ".json", ".yml", ".yaml", ".html", ".css",
    ".js", ".ts", ".tsx", ".jsx", ".toml", ".cfg", ".ini", ".example", ".cjs"
)
$patterns = @(
    "sk-[A-Za-z0-9]{20,}",
    "sk-ant-[A-Za-z0-9_-]{20,}",
    "ghp_[A-Za-z0-9]{20,}",
    "AKIA[0-9A-Z]{16}",
    "-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----",
    "[A-Za-z]:\\[^\\\s]+",
    "192\.168\.[0-9]{1,3}\.[0-9]{1,3}",
    "\b10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\b"
)
$findings = @()
Get-ChildItem -LiteralPath $targetPath -Recurse -File |
    Where-Object { $textExtensions -contains $_.Extension.ToLowerInvariant() } |
    ForEach-Object {
        $file = $_
        foreach ($pattern in $patterns) {
            $match = Select-String -LiteralPath $file.FullName -Pattern $pattern -AllMatches -ErrorAction SilentlyContinue
            if ($match) {
                $findings += "$($file.FullName): matched $pattern"
            }
        }
    }
if ($findings.Count -gt 0) {
    $findings | ForEach-Object { Write-Host "SANITIZE: $_" }
    throw "Sanitization scan failed; public export aborted"
}

$gitleaks = Get-Command gitleaks -ErrorAction SilentlyContinue
if ($gitleaks) {
    & $gitleaks.Source detect --source $targetPath --no-git --redact --verbose
    if ($LASTEXITCODE -ne 0) {
        throw "gitleaks found potential secrets; public export aborted"
    }
} else {
    Write-Warning "gitleaks not found; install it before publishing the public repository"
}

if (-not $NoGit) {
    Push-Location $targetPath
    try {
        & git init -b main | Out-Null
        & git add -A
        & git commit -m "chore(release): public snapshot v$version" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "git commit failed" }
        & git tag "v$version"
        Write-Host "OK: public snapshot initialized and tagged v$version"
        Write-Host "Next:"
        Write-Host "  git -C `"$targetPath`" remote add origin <public-repo-url>"
        Write-Host "  git -C `"$targetPath`" push -u origin main --tags"
    } finally {
        Pop-Location
    }
} else {
    Write-Host "OK: public snapshot written to $targetPath (Git skipped)"
}

Write-Host "Review the snapshot manually before pushing. Never commit secrets or user data."
