# Is the crystal render reproducible?
#
# KEEP THIS. It is the only reason the viewer's behaviour is knowable.
#
# Before it existed, changes to viewer.html were judged by taking one
# screenshot per change -- and the render failed about 40% of the time for
# an unrelated scheduling reason, so several conclusions of the form "this
# change broke it" were coin flips. Running this instead turned that into:
#
#     rAF retry, non-zero size check   3/5 drew, 2/5 blank
#     setTimeout retry                 5/5 drew, one at 44 ink (tiny)
#     setTimeout + minimum size        5/5 drew, 1411 ink, 0% spread
#
# and only then was it safe to tune the camera:
#
#     plain zoomTo()  1411    zoom(1.25)  2124    zoom(1.6)  3069 (clips)
#
# Run it after ANY change to viewer.html's crystal path. A single
# screenshot cannot tell a fix from luck.
#
# Five cold launches, the same CIF each time, and the result COUNTED
# rather than eyeballed: non-background pixels in the viewer region.
# A blank view scores ~0; a drawn cell scores thousands. Reading five
# numbers settles what a hundred screenshots could not.

param(
    [string]$Cif = "D:\Random Projects\OpenChem Studio\spikes\crystallography\halite.cif",
    [int]$Runs = 5
)

$s = "C:\Users\pmpd\AppData\Local\Temp\claude\D--Random-Projects-OpenChem-Studio\042a4ead-0391-4214-ae85-7d338691f2d1\scratchpad"
. "$s\gui.ps1"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Count-Ink($path, $x, $y, $w, $h) {
    $img = [System.Drawing.Bitmap]::FromFile($path)
    $inked = 0
    for ($py = $y; $py -lt ($y + $h); $py += 2) {
        for ($px = $x; $px -lt ($x + $w); $px += 2) {
            if ($px -ge $img.Width -or $py -ge $img.Height) { continue }
            $c = $img.GetPixel($px, $py)
            # Anything appreciably off white. The viewer background is
            # white, so spheres, cell lines and axis labels all count.
            if ($c.R -lt 240 -or $c.G -lt 240 -or $c.B -lt 240) { $inked++ }
        }
    }
    $img.Dispose()
    return $inked
}

$results = @()
for ($run = 1; $run -le $Runs; $run++) {
    Get-Process python -EA SilentlyContinue |
        Where-Object { $_.MainWindowTitle -like "OpenChem*" } |
        ForEach-Object { Stop-Process -Id $_.Id -Force }
    Start-Sleep -Seconds 3

    Set-Location "D:\Random Projects\OpenChem Studio"
    Start-Process -FilePath ".venv\Scripts\python.exe" -ArgumentList "-m","openchem.main" `
        -RedirectStandardOutput "$s\r$run.log" -RedirectStandardError "$s\r$run.err" | Out-Null
    Start-Sleep -Seconds 35

    $gui = Get-Process python -EA SilentlyContinue | Where-Object { $_.MainWindowTitle -like "OpenChem*" }
    if (-not $gui) { $results += [pscustomobject]@{Run=$run; Ink=-1; Note="app did not start"}; continue }
    $script:AppPid = $gui.Id

    $focused = $false
    foreach ($attempt in 1..5) {
        Focus-App; Start-Sleep -Milliseconds 900
        try { Assert-Mine | Out-Null; $focused = $true; break } catch { Start-Sleep -Seconds 2 }
    }
    if (-not $focused) { $results += [pscustomobject]@{Run=$run; Ink=-2; Note="focus refused"}; continue }

    Tap 25 39;  Start-Sleep -Milliseconds 900     # File
    Tap 75 239; Start-Sleep -Seconds 3            # Import Crystal Structure...
    Set-Clipboard -Value $Cif
    [System.Windows.Forms.SendKeys]::SendWait("^v"); Start-Sleep -Milliseconds 700
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}"); Start-Sleep -Seconds 8

    # Close the report dialog by its own window, not a guessed coordinate --
    # a missed click leaves a modal over the view and poisons the capture.
    $dlg = Get-AppWindows | Where-Object { $_.Title -like "Crystal Structure*" }
    if ($dlg) {
        [Win.Api]::SetForegroundWindow($dlg.Handle) | Out-Null
        Start-Sleep -Milliseconds 400
        [System.Windows.Forms.SendKeys]::SendWait("{ESC}")
        Start-Sleep -Seconds 2
    }
    Start-Sleep -Seconds 3

    Capture-App "$s\repro_$run.png" "OpenChem Studio*" | Out-Null
    # The 3D viewer region of the maximised window (capture coords).
    $ink = Count-Ink "$s\repro_$run.png" 200 120 1150 560
    $note = "dialog closed"
    if (-not $dlg) { $note = "NO DIALOG - import may have failed" }
    $results += [pscustomobject]@{Run=$run; Ink=$ink; Note=$note}
}

Get-Process python -EA SilentlyContinue |
    Where-Object { $_.MainWindowTitle -like "OpenChem*" } |
    ForEach-Object { Stop-Process -Id $_.Id -Force }

$results | Format-Table -AutoSize
$inks = ($results | Where-Object { $_.Ink -gt 0 } | ForEach-Object { $_.Ink })
if ($inks.Count -gt 0) {
    $min = ($inks | Measure-Object -Minimum).Minimum
    $max = ($inks | Measure-Object -Maximum).Maximum
    "drew: $($inks.Count)/$Runs   ink min $min  max $max  spread $([math]::Round(100*($max-$min)/[math]::Max($max,1),1))%"
} else {
    "nothing drew in any run"
}
