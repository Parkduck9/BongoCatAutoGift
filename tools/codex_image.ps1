# Generate an image with Codex CLI (ChatGPT OAuth login, no API key).
# Usage: powershell -File tools\codex_image.ps1 -PromptFile docs\md\prompts\prompt_v1.txt -Out docs\html\goal\goal_v1.png
param(
    [Parameter(Mandatory)] [string]$PromptFile,
    [Parameter(Mandatory)] [string]$Out
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent

# codex.exe ships with the Codex desktop app; its hash folder changes on updates.
$codex = Get-ChildItem "$env:LOCALAPPDATA\OpenAI\Codex\bin\*\codex.exe" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
if (-not $codex) { throw "codex.exe not found. Install/open the Codex desktop app." }

$desc = Get-Content (Join-Path $root $PromptFile) -Raw -Encoding UTF8
$outAbs = Join-Path $root $Out
New-Item -ItemType Directory -Force (Split-Path $outAbs) | Out-Null

$instr = @"
Use your built-in image generation tool to create ONE image (landscape, about 1536x1024) from this description:

$desc

After generating, copy the resulting PNG file to exactly this path: $outAbs
Do not create or modify any other files. Reply with the final file path only.
"@

# PowerShell 5.1 pipes to native exes as ASCII by default; Korean needs UTF-8.
$OutputEncoding = [Text.UTF8Encoding]::new($false)
$instr | & $codex exec --skip-git-repo-check --sandbox workspace-write -C $root -
if (-not (Test-Path $outAbs)) { throw "Image not found at $outAbs" }
Write-Host "OK: $outAbs"
