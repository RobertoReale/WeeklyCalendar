// WeeklyCalendar z-order helper.
//
// Rainmeter keeps "On Desktop" skins (ZPos=-2) visible in "Show desktop" mode by making
// them topmost. Windows 11 often enters that mode just by clicking the desktop, so a
// dialog opened from there (e.g. "Empty Recycle Bin") appears behind the calendar.
//
// While Rainmeter is in that mode, this helper moves those skins just below the window
// that becomes active (so dialogs and windows are always above the calendar) and puts
// them back when the desktop is active again. Outside that mode it does nothing.
// Window classes and z-order rules follow Rainmeter's System.cpp / Skin.cpp.
//
// Built on first load by launch.cmd with the C# compiler included in Windows (.NET 4,
// C# 5 syntax only). It exits by itself when Rainmeter closes.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

static class ZOrderHelper
{
    delegate void WinEventProc(IntPtr hook, uint ev, IntPtr hwnd, int idObject, int idChild, uint thread, uint time);

    [DllImport("user32.dll")] static extern IntPtr SetWinEventHook(uint min, uint max, IntPtr mod, WinEventProc proc, uint pid, uint tid, uint flags);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr FindWindow(string cls, string name);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr hwnd, uint cmd);
    [DllImport("user32.dll")] static extern int GetWindowLong(IntPtr hwnd, int index);
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr hwnd, StringBuilder buf, int max);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);

    const uint EVENT_SYSTEM_FOREGROUND = 3;
    const uint GW_HWNDPREV = 3;
    const int GWL_EXSTYLE = -20;
    const int WS_EX_TOPMOST = 0x8;
    static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
    static readonly IntPtr HWND_NOTOPMOST = new IntPtr(-2);
    // Same flags Rainmeter uses: SWP_NOSENDCHANGING bypasses the skin's own z-order lock.
    const uint FLAGS = 0x0001 | 0x0002 | 0x0010 | 0x0200 | 0x0400; // NOSIZE|NOMOVE|NOACTIVATE|NOOWNERZORDER|NOSENDCHANGING

    static readonly HashSet<string> Ignored = new HashSet<string> {
        "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "RainmeterMeterWindow",
        "RainmeterSystem", "RainmeterTrayClass", "#32768", "NotifyIconOverflowWindow",
        "TopLevelWindowForOverflowXamlIsland", "Windows.UI.Core.CoreWindow", "ForegroundStaging",
        "MultitaskingViewFrame", "XamlExplorerHostIslandWindow", "XamlExplorerHostIslandWindow_WASDK",
    };

    static readonly List<IntPtr> lowered = new List<IntPtr>();
    static WinEventProc hookProc; // referenced so the delegate is not garbage collected
    static int missing;

    [STAThread]
    static void Main()
    {
        bool first;
        using (var mutex = new Mutex(true, @"Local\WeeklyCalendarZOrderHelper", out first))
        {
            if (!first) return;
            hookProc = (h, e, hwnd, o, c, t, tm) => Check();
            SetWinEventHook(EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, IntPtr.Zero, hookProc, 0, 0, 0);
            var timer = new System.Windows.Forms.Timer();
            timer.Interval = 250;
            timer.Tick += delegate { Check(); };
            timer.Start();
            Application.Run();
        }
    }

    static string ClassOf(IntPtr hwnd)
    {
        var sb = new StringBuilder(64);
        GetClassName(hwnd, sb, sb.Capacity);
        return sb.ToString();
    }

    static bool IsTopmost(IntPtr hwnd)
    {
        return (GetWindowLong(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST) != 0;
    }

    // The topmost window right above the skins Rainmeter raised (they go just below it)
    static IntPtr TopmostAnchor(IntPtr helper)
    {
        for (IntPtr w = GetWindow(helper, GW_HWNDPREV); w != IntPtr.Zero; w = GetWindow(w, GW_HWNDPREV))
        {
            if (!IsTopmost(w)) break;
            if (ClassOf(w) != "RainmeterMeterWindow") return w;
        }
        return HWND_TOPMOST;
    }

    static void Check()
    {
        IntPtr helper = FindWindow("RainmeterSystem", "PositioningHelper");
        if (helper == IntPtr.Zero)
        {
            if (++missing > 40) Application.Exit(); // Rainmeter closed (~10 s)
            return;
        }
        missing = 0;

        // Rainmeter makes its positioning helper topmost only in "Show desktop" mode
        if (!IsTopmost(helper))
        {
            lowered.Clear();
            return;
        }

        IntPtr fg = GetForegroundWindow();
        if (fg == IntPtr.Zero) return;
        string cls = ClassOf(fg);

        if (cls == "Progman" || cls == "WorkerW")
        {
            // Desktop active again: put the skins back where Rainmeter keeps them,
            // right below the backmost topmost window that is not a skin
            IntPtr after = TopmostAnchor(helper);
            foreach (IntPtr w in lowered)
            {
                if (IsWindow(w) && !IsTopmost(w))
                {
                    SetWindowPos(w, after, 0, 0, 0, 0, FLAGS);
                    after = w;
                }
            }
            lowered.Clear();
            return;
        }

        if (Ignored.Contains(cls) || IsTopmost(fg) || !IsWindowVisible(fg)) return;

        // Skins raised by Rainmeter sit right above the helper, at the bottom of the topmost band
        var skins = new List<IntPtr>();
        for (IntPtr w = GetWindow(helper, GW_HWNDPREV); w != IntPtr.Zero && IsTopmost(w); w = GetWindow(w, GW_HWNDPREV))
        {
            if (ClassOf(w) != "RainmeterMeterWindow") break;
            skins.Insert(0, w); // keep them in z-order, top first
        }
        if (skins.Count == 0) return;

        IntPtr below = fg;
        foreach (IntPtr w in skins)
        {
            SetWindowPos(w, HWND_NOTOPMOST, 0, 0, 0, 0, FLAGS);
            SetWindowPos(w, below, 0, 0, 0, 0, FLAGS);
            below = w;
            if (!lowered.Contains(w)) lowered.Add(w);
        }
    }
}
