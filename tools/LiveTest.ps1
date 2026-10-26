<#
  Drives the real skin with real mouse input, for checks the Lua tests cannot make
  (tooltips, dragging, what a press or the wheel does). Run it with PowerShell 7:

    pwsh -File tools\LiveTest.ps1 -Front -Steps "move 600 500; down; glide 660 540; up; pos"

  Steps, separated by ";" (coordinates are skin coordinates, as in Calendar.lua):
    move X Y          put the cursor there
    glide X Y [MS]    move there in 20 steps (Rainmeter sees every step)
    down / up         left button        rdown / rup   right button
    tap               a quick click (press and release at once, as a touchpad tap)
    wheel N           mouse wheel (120 = one notch up, -120 down)
    type TEXT         type text into the focused window (Unicode, e.g. a title in InputText)
    key NAME          press a key: enter, esc, tab, back, delete, end, home, left, right, a-z;
                      with ctrl+ / shift+ in front (ctrl+a, ctrl+back, shift+home, ctrl+shift+left)
    wait MS           pause
    lua CODE          !CommandMeasure MeasureScript "CODE" (e.g. SetView('month'))
    shot FILE X Y W H screenshot of a skin area, tooltips included
    pos               print the skin position from Rainmeter.ini (did a press move it?)
    fg                print the foreground window (does an InputText box have the keyboard?)
    log [N]           print the last N lines (default 5) of Rainmeter.log

  -Front brings the skin above other windows for the test (!ZPos 2) and back to the
  desktop at the end (!ZPos -2); "shot" then raises the tooltip above the skin again.
  The cursor goes back where it was. Do not touch the mouse while it runs.

  Notes: SendInput needs the 40-byte x64 INPUT structure (a wrong size fails silently).
  Rainmeter is not DPI aware here, so Windows scales the skin: screen = scale * (WindowX + x).
  Tooltips are layered windows: the capture uses CAPTUREBLT to include them.
#>
param([string]$Steps, [switch]$Front, [string]$Config = 'WeeklyCalendar')

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Text; using System.Runtime.InteropServices;
public class LiveTest {
  [StructLayout(LayoutKind.Explicit, Size = 40)]
  public struct INPUT {
    [FieldOffset(0)] public uint type;
    [FieldOffset(8)] public int dx; [FieldOffset(12)] public int dy;
    [FieldOffset(16)] public uint mouseData; [FieldOffset(20)] public uint flags;
    [FieldOffset(24)] public uint time; [FieldOffset(32)] public IntPtr extra;
  }
  public struct POINT { public int X; public int Y; }
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] static extern uint SendInput(uint n, INPUT[] i, int size);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] static extern int GetSystemMetrics(int i);
  [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
  [DllImport("user32.dll")] public static extern uint GetDpiForSystem();
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
  // Keys go to the foreground window: only type into Rainmeter's own windows
  public static uint ForegroundPid() { uint p; GetWindowThreadProcessId(GetForegroundWindow(), out p); return p; }
  public static string ForegroundName() {
    var c = new StringBuilder(64); var t = new StringBuilder(128); IntPtr h = GetForegroundWindow();
    GetClassName(h, c, 64); GetWindowText(h, t, 128);
    return "pid " + ForegroundPid() + ", class " + c + ", title '" + t + "'";
  }
  [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int hh, uint f);
  [DllImport("user32.dll")] static extern IntPtr GetDC(IntPtr h);
  [DllImport("user32.dll")] static extern int ReleaseDC(IntPtr h, IntPtr dc);
  [DllImport("gdi32.dll")] static extern bool BitBlt(IntPtr d, int x, int y, int w, int h, IntPtr s, int sx, int sy, uint op);
  [DllImport("gdi32.dll")] static extern IntPtr CreateCompatibleDC(IntPtr dc);
  [DllImport("gdi32.dll")] static extern IntPtr CreateCompatibleBitmap(IntPtr dc, int w, int h);
  [DllImport("gdi32.dll")] static extern IntPtr SelectObject(IntPtr dc, IntPtr o);
  [DllImport("gdi32.dll")] static extern bool DeleteDC(IntPtr dc);
  [DllImport("gdi32.dll")] public static extern bool DeleteObject(IntPtr o);

  public static uint Mouse(uint flags, int x, int y, int data) {
    INPUT[] a = new INPUT[1];
    a[0].dx = (int)((x * 65535L) / (GetSystemMetrics(0) - 1));
    a[0].dy = (int)((y * 65535L) / (GetSystemMetrics(1) - 1));
    a[0].mouseData = (uint)data;
    a[0].flags = flags | 0x8000 | 0x0001; // ABSOLUTE | MOVE
    return SendInput(1, a, Marshal.SizeOf(typeof(INPUT)));
  }
  // Keyboard: a virtual key (vk) or, with vk = 0, a Unicode character (KEYEVENTF_UNICODE).
  // KEYBDINPUT shares the union at offset 8: wVk (2 bytes), wScan (2), dwFlags (4).
  public static uint Key(ushort vk, char ch, bool up) {
    INPUT[] a = new INPUT[1];
    a[0].type = 1;
    a[0].dx = vk | (ch << 16);
    a[0].dy = (vk == 0 ? 0x0004 : 0) | (up ? 0x0002 : 0);
    return SendInput(1, a, Marshal.SizeOf(typeof(INPUT)));
  }
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  // Tooltip windows and InputText boxes of a process back on top (the skin was raised above them)
  public static void RaiseTooltips(uint pid) {
    EnumWindows((h, l) => {
      uint p; GetWindowThreadProcessId(h, out p);
      var c = new StringBuilder(64); GetClassName(h, c, 64);
      var t = new StringBuilder(64); GetWindowText(h, t, 64);
      if (p == pid && (c.ToString() == "tooltips_class32" || t.ToString() == "InputBox"))
        SetWindowPos(h, new IntPtr(-1), 0, 0, 0, 0, 0x0013);
      return true; }, IntPtr.Zero);
  }
  // Screen capture including layered windows such as tooltips (SRCCOPY | CAPTUREBLT)
  public static IntPtr Capture(int x, int y, int w, int h) {
    IntPtr src = GetDC(IntPtr.Zero), mem = CreateCompatibleDC(src);
    IntPtr hbm = CreateCompatibleBitmap(src, w, h), old = SelectObject(mem, hbm);
    BitBlt(mem, 0, 0, w, h, src, x, y, 0x00CC0020 | 0x40000000);
    SelectObject(mem, old); DeleteDC(mem); ReleaseDC(IntPtr.Zero, src);
    return hbm;
  }
}
"@
[LiveTest]::SetProcessDPIAware() | Out-Null
$rm = 'C:\Program Files\Rainmeter\Rainmeter.exe'

function SkinPos {
  $ini = [IO.File]::ReadAllText("$env:APPDATA\Rainmeter\Rainmeter.ini")
  $sec = $ini.Substring($ini.IndexOf("[$Config]"))
  [int]([regex]::Match($sec, 'WindowX=(-?\d+)').Groups[1].Value), [int]([regex]::Match($sec, 'WindowY=(-?\d+)').Groups[1].Value)
}
$wx, $wy = SkinPos
$scale = [LiveTest]::GetDpiForSystem() / 96.0
function PX([double]$x) { [int](($wx + $x) * $scale) }
function PY([double]$y) { [int](($wy + $y) * $scale) }

$orig = New-Object LiveTest+POINT; [LiveTest]::GetCursorPos([ref]$orig) | Out-Null
$cur = @($orig.X, $orig.Y)
if ($Front) { & $rm '!ZPos' '2' $Config; Start-Sleep -Milliseconds 400 }
try {
  foreach ($s in ($Steps -split ';')) {
    $a = $s.Trim() -split '\s+', 2
    $arg = if ($a.Count -gt 1) { $a[1] } else { '' }
    $v = $arg -split '\s+'
    switch ($a[0]) {
      'move'  { $cur = @((PX $v[0]), (PY $v[1])); [LiveTest]::Mouse(0, $cur[0], $cur[1], 0) | Out-Null; Start-Sleep -Milliseconds 60 }
      'glide' { $to = @((PX $v[0]), (PY $v[1])); $ms = if ($v.Count -gt 2) { [int]$v[2] } else { 600 }
                for ($k = 1; $k -le 20; $k++) {
                  [LiveTest]::Mouse(0, [int]($cur[0] + ($to[0] - $cur[0]) * $k / 20), [int]($cur[1] + ($to[1] - $cur[1]) * $k / 20), 0) | Out-Null
                  Start-Sleep -Milliseconds ([int]($ms / 20)) }
                $cur = $to }
      'down'  { if ([LiveTest]::Mouse(0x0002, $cur[0], $cur[1], 0) -ne 1) { throw 'SendInput failed' }; Start-Sleep -Milliseconds 80 }
      'up'    { [LiveTest]::Mouse(0x0004, $cur[0], $cur[1], 0) | Out-Null; Start-Sleep -Milliseconds 80 }
      'tap'   { [LiveTest]::Mouse(0x0002, $cur[0], $cur[1], 0) | Out-Null; [LiveTest]::Mouse(0x0004, $cur[0], $cur[1], 0) | Out-Null
                Start-Sleep -Milliseconds 80 }
      'rdown' { [LiveTest]::Mouse(0x0008, $cur[0], $cur[1], 0) | Out-Null; Start-Sleep -Milliseconds 80 }
      'rup'   { [LiveTest]::Mouse(0x0010, $cur[0], $cur[1], 0) | Out-Null; Start-Sleep -Milliseconds 80 }
      'wheel' { [LiveTest]::Mouse(0x0800, $cur[0], $cur[1], [int]$arg) | Out-Null; Start-Sleep -Milliseconds 400 }
      { $_ -in 'type', 'key' } {
                if ([LiveTest]::ForegroundPid() -ne (Get-Process Rainmeter).Id) { throw "$($a[0]): the foreground window is not Rainmeter's" } }
      'type'  { foreach ($ch in $arg.ToCharArray()) {
                  [LiveTest]::Key(0, $ch, $false) | Out-Null; [LiveTest]::Key(0, $ch, $true) | Out-Null
                  Start-Sleep -Milliseconds 15 } }
      'key'   { $mods = @(); $name = $arg
                while ($name -match '^(ctrl|shift)\+(.+)$') { $mods += @{ ctrl = 0x11; shift = 0x10 }[$Matches[1]]; $name = $Matches[2] }
                $vk = @{ enter = 0x0D; esc = 0x1B; tab = 0x09; back = 0x08; delete = 0x2E; end = 0x23; home = 0x24
                         left = 0x25; right = 0x27 }[$name]
                if (-not $vk -and $name -match '^[a-z]$') { $vk = [int][char]$name.ToUpper() }
                if (-not $vk) { throw "unknown key: $arg" }
                foreach ($k in $mods) { [LiveTest]::Key($k, [char]0, $false) | Out-Null }
                [LiveTest]::Key($vk, [char]0, $false) | Out-Null; [LiveTest]::Key($vk, [char]0, $true) | Out-Null
                foreach ($k in $mods) { [LiveTest]::Key($k, [char]0, $true) | Out-Null }
                Start-Sleep -Milliseconds 100 }
      'wait'  { Start-Sleep -Milliseconds ([int]$arg) }
      'lua'   { & $rm '!CommandMeasure' 'MeasureScript' $arg $Config; Start-Sleep -Milliseconds 300 }
      'pos'   { $px, $py = SkinPos; "skin at $px,$py" }
      'fg'    { "foreground: " + [LiveTest]::ForegroundName() + " (Rainmeter: pid " + (Get-Process Rainmeter).Id + ")" }
      'log'   { $n = if ($arg) { [int]$arg } else { 5 }; Get-Content "$env:APPDATA\Rainmeter\Rainmeter.log" -Tail $n }
      'shot'  { [LiveTest]::RaiseTooltips((Get-Process Rainmeter).Id); Start-Sleep -Milliseconds 100
                $hbm = [LiveTest]::Capture((PX $v[1]), (PY $v[2]), [int]([double]$v[3] * $scale), [int]([double]$v[4] * $scale))
                $bmp = [System.Drawing.Image]::FromHbitmap($hbm); [LiveTest]::DeleteObject($hbm) | Out-Null
                $bmp.Save($v[0], [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose() }
      ''      { }
      default { throw "unknown step: $($a[0])" }
    }
  }
} finally {
  [LiveTest]::Mouse(0, $orig.X, $orig.Y, 0) | Out-Null
  if ($Front) { & $rm '!ZPos' '-2' $Config }
}
