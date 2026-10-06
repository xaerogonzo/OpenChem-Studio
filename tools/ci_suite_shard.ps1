# One attempt at one shard of the Windows test suite, teeing its output to a log.
#
# WHY THIS IS A SCRIPT. The shard is run up to twice (see `ci_classify_crash.ps1`), and the same
# command twice in a workflow is a copy that drifts. It also can be exercised locally against a
# synthetic crash, which a workflow step cannot.
#
# `-Files` bypasses the splitter and exists for that local exercise only; CI never passes it.
#
# `-Splits` IS MANDATORY AND HAS NO DEFAULT, on purpose: the number of shards is the size of the workflow's matrix and
# nothing else (`tests.yml` passes `strategy.job-total`), so there is no second place for it to be wrong in. A default
# here would run a 2-way split in a 3-job matrix and drop a third of the suite while every job stayed green.
param(
    [Parameter(Mandatory)][int]$Shard,
    [Parameter(Mandatory)][int]$Splits,
    [Parameter(Mandatory)][string]$Log,
    [Parameter(Mandatory)][string]$NetworkTest,
    [string[]]$Files = @()
)

# The Actions pwsh default is 'Stop', under which a native program's stderr (faulthandler writes
# "Windows fatal exception" there) could abort the script before the log is complete.
$ErrorActionPreference = 'Continue'

if ($Files.Count -eq 0) {
    $Files = uv run --no-sync python tools/suite_shards.py --splits=$Splits --group=$Shard
    Write-Host "shard $Shard of ${Splits}: $($Files.Count) test files"
    if ($Files.Count -lt 1) { throw "the splitter produced no files for this shard" }
}
uv run --no-sync python -u -m pytest -q -ra --deselect $NetworkTest "--junitxml=suite-timings-windows-$Shard.xml" --durations=30 $Files 2>&1 | Tee-Object -FilePath $Log
exit $LASTEXITCODE
