# SessionStart hook (startup / resume / clear / compact / fork): print the handoff file and
# repo state to stdout so a fresh session starts with the current progress in context.

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$repo = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSCommandPath))
$progress = Join-Path $repo 'docs/studio/PROGRESS.md'

[Console]::Out.WriteLine('=== docs/studio/PROGRESS.md ===')
if (Test-Path $progress) {
    [Console]::Out.WriteLine((Get-Content -Raw -Encoding UTF8 $progress))
}
else {
    [Console]::Out.WriteLine('(PROGRESS.md not found)')
}

[Console]::Out.WriteLine('=== git status --short ===')
$status = git -C $repo status --short 2>$null
if ($status) { $status | ForEach-Object { [Console]::Out.WriteLine($_) } } else { [Console]::Out.WriteLine('(clean)') }

[Console]::Out.WriteLine('=== git log -5 --oneline ===')
git -C $repo log -5 --oneline 2>$null | ForEach-Object { [Console]::Out.WriteLine($_) }
exit 0
