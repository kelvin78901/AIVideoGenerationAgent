# Status line: "<model> · 上下文 N% · 5 小时额度 N%".
# Also records session_id + context usage to .claude/state/context.json for hooks/context-guard.ps1.
# Invoked as: powershell -NoProfile -File <repo>/.claude/statusline.ps1  (JSON on stdin)

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Format-Pct($value) {
    if ($null -eq $value) { return '—' }
    return ('{0}%' -f [math]::Round([double]$value))
}

try {
    $raw = [Console]::In.ReadToEnd()
    $data = $raw | ConvertFrom-Json

    $model = '?'
    if ($data.model -and $data.model.display_name) { $model = $data.model.display_name }

    $ctxPct = $null
    if ($data.context_window) { $ctxPct = $data.context_window.used_percentage }

    $fiveHour = $null
    if ($data.rate_limits -and $data.rate_limits.five_hour) { $fiveHour = $data.rate_limits.five_hour.used_percentage }

    $stateDir = Join-Path (Split-Path -Parent $PSCommandPath) 'state'
    if (-not (Test-Path $stateDir)) { New-Item -ItemType Directory -Force -Path $stateDir | Out-Null }
    $state = [ordered]@{
        session_id      = $data.session_id
        used_percentage = $ctxPct
        updated_at      = (Get-Date).ToUniversalTime().ToString('o')
    }
    $json = $state | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText((Join-Path $stateDir 'context.json'), $json, (New-Object System.Text.UTF8Encoding $false))

    [Console]::Out.Write(('{0} · 上下文 {1} · 5 小时额度 {2}' -f $model, (Format-Pct $ctxPct), (Format-Pct $fiveHour)))
}
catch {
    [Console]::Out.Write('statusline error')
}
exit 0
