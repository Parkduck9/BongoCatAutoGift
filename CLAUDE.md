# Codex integration on this PC

Codex CLI is installed and the Windows user is already signed in with ChatGPT.
Use the existing Codex login; OPENAI_API_KEY is not required for this integration.
Never read, copy, print, or embed authentication tokens in project files.

When the user asks you to consult Codex, invoke this project's launcher through your shell tool:

```powershell
powershell.exe -NoProfile -File 'D:\BongoCatAutoGift\ask-codex.ps1' -Prompt 'Your question and relevant context'
```

The launcher uses the installed executable directly, so Claude does not need Codex on PATH.
It runs Codex in this project with a read-only sandbox and returns its answer on stdout.
Codex consults and reviews; Claude implements requested changes after evaluating the answer.
Use the normal Windows user session so Codex can access its existing login. An isolated
account or sandbox may report not logged in even though the Windows user is logged in.
If execution fails, report the actual error; do not invent an API key or another auth path.
If the installed executable moves after an app update, update its path in ask-codex.ps1.

The installed Codex version has removed `codex mcp-server`; use this launcher.

## Development approach

Form a theory, gather evidence, and only fix a root cause once the evidence supports it.
Make minimal, focused changes. Keep one clear path, fail fast, avoid backups and fallbacks,
and give each function one responsibility.
