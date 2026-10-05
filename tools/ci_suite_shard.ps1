# One attempt at one shard of the Windows test suite, teeing its output to a log.
#
# WHY THIS IS A SCRIPT. The shard is run up to twice (see `ci_classify_crash.ps1`), and the same
# command twice in a workflow is a copy that drifts. It also can be exercised locally against a
# synthetic crash, which a workflow step cannot.
#
# `-Files` bypasses the splitter and exists for that local exercise only; CI never passes it.
param(
    [Parameter(Mandatory)][int]$Shard,
    [Parameter(Mandatory)][string]$Log,
    [Parameter(Mandatory)][string]$NetworkTest,
    [string[]]$Files = @()
)

# The Actions pwsh default is 'Stop', under which a native program's stderr (faulthandler writes
# "Windows fatal exception" there) could abort the script before the log is complete.
$ErrorActionPreference = 'Continue'

if ($Files.Count -eq 0) {
    $Files = uv run --no-sync python tools/suite_shards.py --splits=2 --group=$Shard
    Write-Host "shard $Shard of 2: $($Files.Count) test files"
    if ($Files.Count -lt 1) { throw "the splitter produced no files for this shard" }
}
uv run --no-sync python -u -m pytest -q -ra --deselect $NetworkTest "--junitxml=suite-timings-windows-$Shard.xml" --durations=30 $Files 2>&1 | Tee-Object -FilePath $Log
exit $LASTEXITCODE
