# Read one attempt's log and say whether it CRASHED, as opposed to failing or passing.
#
# A crash is: a fatal exception was printed, AND no pytest summary line exists, AND no test is
# reported FAILED or ERROR. All three, because each alone is ambiguous: a crash prints no summary,
# but so does a timeout kill; a real failure can be followed by a crash at teardown; and a run
# that printed FAILED lines has already told you something real, which a retry must never hide.
#
# Prints `crashed=true|false` (for $GITHUB_OUTPUT), and, for a crash, the lines that identify the
# victim. Those are what measure the crash rate over time, which is the only way to learn whether
# any fix worked: the crash cannot be reproduced locally.
param([Parameter(Mandatory)][string]$Log, [int]$Shard = 0)

if (-not (Test-Path -LiteralPath $Log)) { Write-Output "crashed=false"; exit 0 }
$text = Get-Content -LiteralPath $Log -Raw
$fatal = [regex]::Match($text, 'Windows fatal exception[^\r\n]*|Fatal Python error[^\r\n]*')
$reported = [regex]::Matches($text, '(?m)^(FAILED|ERROR) ').Count
$summary = [regex]::IsMatch($text, '(?m)^\d+ (passed|failed|error)[^\r\n]* in [\d.]+s')

$crashed = $fatal.Success -and ($reported -eq 0) -and (-not $summary)
Write-Output "crashed=$($crashed.ToString().ToLower())"
if (-not $crashed) { exit 0 }

# The crashing thread's own frames outside site-packages: where the test run was when it died.
$after = $text.Substring($fatal.Index)
$frames = [regex]::Matches($after, '(?m)^\s*File "([^"]+)", line (\d+) in (\S+)') |
    Where-Object { $_.Groups[1].Value -notmatch 'site-packages|<frozen' } |
    Select-Object -First 3 |
    ForEach-Object { "$($_.Groups[1].Value -replace '^.*OpenChem-Studio[\\/]OpenChem-Studio[\\/]','')`:$($_.Groups[2].Value) $($_.Groups[3].Value)" }
$progress = [regex]::Matches($text.Substring(0, $fatal.Index), '\[\s*(\d+)%\]') | Select-Object -Last 1
$where = if ($progress) { "$($progress.Groups[1].Value)%" } else { "before the first progress line" }
$victim = if ($frames) { $frames -join ' <- ' } else { 'no frame outside pytest' }
Write-Output "detail=shard $Shard crashed at $where; $($fatal.Value); top frames: $victim"
