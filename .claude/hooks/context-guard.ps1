# PostToolUse hook: warn once per session when context usage crosses 60% and 75%.
# Reads .claude/state/context.json (written by .claude/statusline.ps1); only acts when its
# session_id matches the hook input. Sent thresholds are remembered in .claude/state/guard-<session>.txt (one per line).

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

try {
    $hookInput = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $sessionId = [string]$hookInput.session_id
    if (-not $sessionId) { exit 0 }

    $stateDir = Join-Path (Split-Path -Parent (Split-Path -Parent $PSCommandPath)) 'state'
    $ctxFile = Join-Path $stateDir 'context.json'
    if (-not (Test-Path $ctxFile)) { exit 0 }

    $ctx = Get-Content -Raw -Encoding UTF8 $ctxFile | ConvertFrom-Json
    if ([string]$ctx.session_id -ne $sessionId) { exit 0 }
    if ($null -eq $ctx.used_percentage) { exit 0 }
    $pct = [math]::Round([double]$ctx.used_percentage)

    $safeId = $sessionId -replace '[^A-Za-z0-9_-]', '_'
    $flagFile = Join-Path $stateDir ("guard-$safeId.txt")
    $sent = @()
    if (Test-Path $flagFile) { $sent = @(Get-Content -Encoding UTF8 $flagFile | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ }) }

    $message = $null
    if ($pct -ge 75 -and -not ($sent -contains 75)) {
        $message = "上下文已用 $pct%：不要再开始新的小步，马上把当前状态整理到能提交的样子，然后交接（跑测试、提交、更新 PROGRESS.md，告诉 Kelvin 输入 /clear 再输入 /continue）"
        $sent = @(60, 75)
    }
    elseif ($pct -ge 60 -and $pct -lt 75 -and -not ($sent -contains 60)) {
        $message = "上下文已用 $pct%：做完当前小步就收尾——跑测试、提交、更新 PROGRESS.md，然后停下，告诉 Kelvin 输入 /clear 再输入 /continue"
        $sent = @(60)
    }
    if (-not $message) { exit 0 }

    [System.IO.File]::WriteAllText($flagFile, (($sent -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding $false))

    $out = @{
        hookSpecificOutput = @{
            hookEventName     = 'PostToolUse'
            additionalContext = $message
        }
    }
    [Console]::Out.Write(($out | ConvertTo-Json -Compress -Depth 4))
}
catch {
    # A broken guard must never block tool use.
}
exit 0
