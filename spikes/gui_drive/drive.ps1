# Drive and photograph the running app WITHOUT touching the desktop.
#
# WHY THIS EXISTS. The previous recipe used SetCursorPos + mouse_event +
# SendKeys, which drive the machine's real input queue: the cursor jumps,
# the app must hold focus for every single step, and the user cannot use
# their computer while a run is in progress. It also fails in ways that
# look like app bugs -- a console window stealing focus mid-sequence sent
# a paste into the wrong window and the run read as "the app ignored the
# import".
#
# Everything here targets a WINDOW HANDLE instead:
#
#   Save-AppShot   PrintWindow(PW_RENDERFULLCONTENT) renders the window
#                  into a bitmap. Needs no focus, works when the window
#                  is behind others.
#   Invoke-AppClick / Invoke-AppKey
#                  PostMessage to that handle. No cursor movement, no
#                  activation, no interference with whatever the user is
#                  doing in another window.
#
# Assert-AppWindow replaces the old foreground check and is strictly
# safer: the old one asked "is the app in front", which is a race, while
# this asks "does this handle belong to the process I mean", which is not.
#
# PREFER THE IN-APP DRIVER. `OPENCHEM_DRIVE` (see
# src/openchem/app/debug_drive.py) performs app actions from inside the
# process and needs no synthetic input at all. Reach for the clicks here
# only for something the driver cannot express.

# NO `Set-StrictMode` here. Dot-sourcing this file applies it to the
# CALLER's session, where it broke the harness's own exit-code handling
# ("$LASTEXITCODE cannot be retrieved because it has not been set") and
# read as a failure of the capture that had in fact just succeeded.

Add-Type -AssemblyName System.Drawing

if (-not ("OpenChemDrive.Win32" -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
namespace OpenChemDrive {
  public class Win32 {
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern int GetWindowThreadProcessId(IntPtr h, out int pid);
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr h);
    public struct RECT { public int Left, Top, Right, Bottom; }
    public struct POINT { public int X, Y; }
  }
}
'@
}

$script:PW_RENDERFULLCONTENT = 2
$script:WM_MOUSEMOVE   = 0x0200
$script:WM_LBUTTONDOWN = 0x0201
$script:WM_LBUTTONUP   = 0x0202
$script:WM_KEYDOWN     = 0x0100
$script:WM_KEYUP       = 0x0101
$script:MK_LBUTTON     = 0x0001


function Get-AppWindow {
    <#
      .SYNOPSIS
      The main window handle of the running OpenChem Studio, with its pid.

      The GUI belongs to a CHILD process: launching `uv run python -m
      openchem.main` leaves the parent owning only a console, with
      MainWindowHandle == 0. Find it by title across every process rather
      than by walking down from the launcher.
    #>
    param([string]$TitleLike = 'OpenChem Studio*')

    $proc = Get-Process | Where-Object { $_.MainWindowTitle -like $TitleLike } | Select-Object -First 1
    if (-not $proc) { throw "No window matching '$TitleLike' -- is the app running?" }
    [pscustomobject]@{ Handle = $proc.MainWindowHandle; Pid = $proc.Id; Title = $proc.MainWindowTitle }
}


function Assert-AppWindow {
    <#
      .SYNOPSIS
      Refuse to send anything to a handle that is not the app's.

      Replaces the old "is the app the foreground window" guard. That one
      protected against input landing in someone else's window and was
      raced by anything that stole focus; this cannot be raced, because
      the handle either belongs to the expected process or it does not.
    #>
    param([Parameter(Mandatory)] $Window)

    if (-not [OpenChemDrive.Win32]::IsWindow($Window.Handle)) {
        throw "Window handle $($Window.Handle) no longer exists."
    }
    $owner = 0
    [void][OpenChemDrive.Win32]::GetWindowThreadProcessId($Window.Handle, [ref]$owner)
    if ($owner -ne $Window.Pid) {
        throw "Handle $($Window.Handle) belongs to pid $owner, not $($Window.Pid) -- refusing to send input."
    }
}


function Save-AppShot {
    <#
      .SYNOPSIS
      Photograph the window without focusing or raising it.

      PW_RENDERFULLCONTENT (2) is what makes this work for a Qt window;
      plain PrintWindow(0) gives a blank or stale bitmap for
      hardware-composited content.
    #>
    param(
        [Parameter(Mandatory)] $Window,
        [Parameter(Mandatory)] [string] $Path
    )
    Assert-AppWindow $Window

    $rect = New-Object OpenChemDrive.Win32+RECT
    [void][OpenChemDrive.Win32]::GetWindowRect($Window.Handle, [ref]$rect)
    $width = $rect.Right - $rect.Left
    $height = $rect.Bottom - $rect.Top
    if ($width -le 0 -or $height -le 0) { throw "Window has no area ($width x $height)." }

    $bitmap = New-Object System.Drawing.Bitmap $width, $height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $hdc = $graphics.GetHdc()
    $ok = [OpenChemDrive.Win32]::PrintWindow($Window.Handle, $hdc, $script:PW_RENDERFULLCONTENT)
    $graphics.ReleaseHdc($hdc)
    $graphics.Dispose()
    if (-not $ok) { $bitmap.Dispose(); throw "PrintWindow failed." }

    $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    $bitmap.Dispose()
    [pscustomobject]@{ Path = $Path; Width = $width; Height = $height }
}


function ConvertTo-AppClient {
    <#
      .SYNOPSIS
      Screen coordinates -> client coordinates for this window.

      Posted mouse messages carry CLIENT coordinates, so a screen position
      read off a screenshot has to be shifted by the client origin. The
      old recipe's "subtract 8 for a maximized window" fudge is not needed
      here: the client origin is asked for rather than guessed.
    #>
    param(
        [Parameter(Mandatory)] $Window,
        [Parameter(Mandatory)] [int] $X,
        [Parameter(Mandatory)] [int] $Y
    )
    $origin = New-Object OpenChemDrive.Win32+POINT
    $origin.X = 0; $origin.Y = 0
    [void][OpenChemDrive.Win32]::ClientToScreen($Window.Handle, [ref]$origin)
    [pscustomobject]@{ X = $X - $origin.X; Y = $Y - $origin.Y }
}


function Invoke-AppClick {
    <#
      .SYNOPSIS
      Click inside the window without moving the real cursor.

      Coordinates are SCREEN coordinates by default, so they can be read
      straight off a `Save-AppShot` capture; pass -Client if you already
      have client-relative ones.
    #>
    param(
        [Parameter(Mandatory)] $Window,
        [Parameter(Mandatory)] [int] $X,
        [Parameter(Mandatory)] [int] $Y,
        [switch] $Client,
        # Coordinates read straight off a `Save-AppShot` PNG, which is the
        # window rect -- so its origin is the window's top-left corner,
        # NOT the client area's. This does the shift for you.
        [switch] $FromCapture,
        [int] $SettleMs = 250
    )
    Assert-AppWindow $Window

    if ($FromCapture) {
        $rect = New-Object OpenChemDrive.Win32+RECT
        [void][OpenChemDrive.Win32]::GetWindowRect($Window.Handle, [ref]$rect)
        $point = ConvertTo-AppClient $Window ($rect.Left + $X) ($rect.Top + $Y)
    }
    elseif ($Client) { $point = [pscustomobject]@{ X = $X; Y = $Y } }
    else { $point = ConvertTo-AppClient $Window $X $Y }
    $lparam = [IntPtr](($point.Y -shl 16) -bor ($point.X -band 0xFFFF))

    [void][OpenChemDrive.Win32]::PostMessage($Window.Handle, $script:WM_MOUSEMOVE, [IntPtr]::Zero, $lparam)
    [void][OpenChemDrive.Win32]::PostMessage($Window.Handle, $script:WM_LBUTTONDOWN, [IntPtr]$script:MK_LBUTTON, $lparam)
    Start-Sleep -Milliseconds 40
    [void][OpenChemDrive.Win32]::PostMessage($Window.Handle, $script:WM_LBUTTONUP, [IntPtr]::Zero, $lparam)
    Start-Sleep -Milliseconds $SettleMs
}


function Invoke-AppKey {
    <#
      .SYNOPSIS
      Send one virtual-key press to the window. `-Key` is a VK code.
      #>
    param(
        [Parameter(Mandatory)] $Window,
        [Parameter(Mandatory)] [int] $Key,
        [int] $SettleMs = 150
    )
    Assert-AppWindow $Window
    [void][OpenChemDrive.Win32]::PostMessage($Window.Handle, $script:WM_KEYDOWN, [IntPtr]$Key, [IntPtr]0)
    Start-Sleep -Milliseconds 30
    [void][OpenChemDrive.Win32]::PostMessage($Window.Handle, $script:WM_KEYUP, [IntPtr]$Key, [IntPtr]0)
    Start-Sleep -Milliseconds $SettleMs
}
