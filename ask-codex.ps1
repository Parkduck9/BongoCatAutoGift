# Ask Codex (existing ChatGPT login, no API key) a question about this project.
# Read-only sandbox: Codex can read the project but cannot change files.
# Usage: powershell.exe -NoProfile -File 'D:\BongoCatAutoGift\ask-codex.ps1' -Prompt '...'
# Prints only Codex's final answer on stdout; progress goes to stderr.
param(
    [Parameter(Mandatory)] [string]$Prompt
)
$ErrorActionPreference = 'Stop'

# Installed with the Codex desktop app. If an app update moves it, update this path.
$Codex = 'C:\Users\User\AppData\Local\OpenAI\Codex\bin\2e5e00daee91c61d\codex.exe'
if (-not (Test-Path $Codex)) { throw "codex.exe not found: $Codex (update the path in ask-codex.ps1)" }

# Korean prompts/answers: PowerShell 5.1 defaults to ASCII/cp949 for native pipes.
$OutputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$answer = [IO.Path]::GetTempFileName()
try {
    $Prompt | & $Codex exec --skip-git-repo-check --sandbox read-only --color never `
        -C $PSScriptRoot -o $answer - | ForEach-Object { [Console]::Error.WriteLine($_) }
    if ($LASTEXITCODE -ne 0) { throw "codex exec failed with exit code $LASTEXITCODE" }
    Get-Content $answer -Raw -Encoding UTF8
} finally {
    Remove-Item $answer -ErrorAction SilentlyContinue
}
