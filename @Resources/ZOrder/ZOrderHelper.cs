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
// KeepDialogsOnTop=0 turns this off: the skin then leaves NoZOrder.txt next to the helper.
//
// It also keeps what is typed in the skin's text boxes. The InputText plugin gives the
// skin the text only on Enter: a click elsewhere (e.g. on the card's Save) closes the box
// and drops it. While Typed.txt exists next to this helper (the skin creates it when it
// opens a box and deletes it when the box closes), the text of the Rainmeter text box that
// has the keyboard is copied into it, after a "WC" line (see edit.typedTake in Calendar.lua).
// When the skin wrote END in it, the cursor goes after the text first: the plugin selects
// the text it shows, and typing on after a click (e.g. on Task) would replace it. The box is
// read only while it has the keyboard (the plugin selects the text when it gets it), and a
// box that becomes empty is copied only when it stays so: a closing box reads as empty for
// a moment. Ctrl+Backspace, which types a DEL character in the plugin's box (a WinForms text
// box), deletes the word before the cursor instead, as in other text boxes.
//
// And it lets the skin follow the cursor while its resize grip is held: Rainmeter tells a
// skin only where the mouse was pressed and released. While Resize.txt exists (the skin
// creates it, with its config name, when the grip is pressed), the cursor position over the
// skin's window is sent to Calendar.lua (ResizeMove) the way Rainmeter.exe sends bangs.
//
// Built on first load by launch.cmd with the C# compiler included in Windows (.NET 4,
// C# 5 syntax only). It exits by itself when Rainmeter closes.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

static class ZOrderHelper
{
    delegate void WinEventProc(IntPtr hook, uint ev, IntPtr hwnd, int idObject, int idChild, uint thread, uint time);
    delegate bool EnumProc(IntPtr hwnd, IntPtr param);

    [DllImport("user32.dll")] static extern IntPtr SetWinEventHook(uint min, uint max, IntPtr mod, WinEventProc proc, uint pid, uint tid, uint flags);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr FindWindow(string cls, string name);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr hwnd, uint cmd);
    [DllImport("user32.dll")] static extern int GetWindowLong(IntPtr hwnd, int index);
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr hwnd, StringBuilder buf, int max);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr parent, EnumProc proc, IntPtr param);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr SendMessageTimeout(IntPtr hwnd, uint msg, IntPtr wp, IntPtr lp, uint flags, uint ms, out IntPtr result);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr SendMessageTimeout(IntPtr hwnd, uint msg, IntPtr wp, StringBuilder lp, uint flags, uint ms, out IntPtr result);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr SendMessageTimeout(IntPtr hwnd, uint msg, IntPtr wp, string lp, uint flags, uint ms, out IntPtr result);
    [DllImport("user32.dll")] static extern IntPtr SendMessageTimeout(IntPtr hwnd, uint msg, IntPtr wp, ref COPYDATASTRUCT lp, uint flags, uint ms, out IntPtr result);
    [DllImport("user32.dll")] static extern bool GetCursorPos(out POINT p);
    [DllImport("user32.dll")] static extern IntPtr WindowFromPoint(POINT p);
    [DllImport("user32.dll")] static extern IntPtr GetAncestor(IntPtr hwnd, uint flags);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr hwnd, out RECT r);
    [DllImport("user32.dll")] static extern bool GetGUIThreadInfo(uint thread, ref GUITHREADINFO info);

    [StructLayout(LayoutKind.Sequential)] struct POINT { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] struct COPYDATASTRUCT { public IntPtr dwData; public int cbData; public IntPtr lpData; }
    [StructLayout(LayoutKind.Sequential)] struct GUITHREADINFO
    {
        public int cbSize, flags;
        public IntPtr hwndActive, hwndFocus, hwndCapture, hwndMenuOwner, hwndMoveSize, hwndCaret;
        public RECT rcCaret;
    }

    const uint EVENT_SYSTEM_FOREGROUND = 3;
    const uint GW_HWNDPREV = 3;
    const int GWL_EXSTYLE = -20;
    const int WS_EX_TOPMOST = 0x8;
    const int GWL_STYLE = -16;
    const int ES_PASSWORD = 0x20;
    const uint WM_SETTEXT = 0x000C, WM_GETTEXT = 0x000D, WM_GETTEXTLENGTH = 0x000E, EM_GETSEL = 0x00B0, EM_SETSEL = 0x00B1, EM_SCROLLCARET = 0x00B7;
    const uint SMTO_ABORTIFHUNG = 0x2;
    const uint WM_COPYDATA = 0x004A, GA_ROOT = 2;
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
    static uint rainmeterPid;

    static readonly string typedPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Typed.txt");
    static readonly string noZOrderPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "NoZOrder.txt");
    static IntPtr typedBox;  // the box and the text last copied
    static string typedText;
    static IntPtr caretBox;  // the box whose cursor went after its text, and until when to keep it there
    static string caretText;
    static int caretUntil;
    static IntPtr emptyBox;  // a box seen empty once (copied when seen so again)
    static readonly string resizePath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Resize.txt");
    static IntPtr resizeSkin; // the window of the skin being resized and the bang last sent
    static string resizeSent;

    [STAThread]
    static void Main()
    {
        // An older build (WeeklyCalendarZOrder<N>.exe, see launch.cmd) still running gives way
        string me = Process.GetCurrentProcess().ProcessName;
        foreach (var p in Process.GetProcesses())
        {
            try
            {
                if (p.ProcessName.StartsWith("WeeklyCalendarZOrder") && p.ProcessName != me)
                {
                    p.Kill();
                    p.WaitForExit(2000);
                }
            }
            catch (Exception) { }
        }
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
            var typing = new System.Windows.Forms.Timer();
            typing.Interval = 40;
            typing.Tick += delegate { CopyTyped(); FollowResize(); };
            typing.Start();
            Application.Run();
        }
    }

    // The text box (not a password) of a Rainmeter window, or zero
    static IntPtr TextBoxOf(IntPtr window)
    {
        IntPtr found = IntPtr.Zero;
        EnumChildWindows(window, (w, p) =>
        {
            string cls = ClassOf(w);
            if ((cls == "Edit" || cls.Contains(".EDIT.")) && (GetWindowLong(w, GWL_STYLE) & ES_PASSWORD) == 0)
            {
                found = w;
                return false;
            }
            return true;
        }, IntPtr.Zero);
        return found;
    }

    static string TextOf(IntPtr box)
    {
        IntPtr len;
        if (SendMessageTimeout(box, WM_GETTEXTLENGTH, IntPtr.Zero, IntPtr.Zero, SMTO_ABORTIFHUNG, 200, out len) == IntPtr.Zero) return null;
        var sb = new StringBuilder(len.ToInt32() + 1);
        IntPtr got;
        if (SendMessageTimeout(box, WM_GETTEXT, new IntPtr(sb.Capacity), sb, SMTO_ABORTIFHUNG, 200, out got) == IntPtr.Zero) return null;
        return sb.ToString();
    }

    // The window that has the keyboard in a thread
    static IntPtr FocusOf(uint thread)
    {
        var info = new GUITHREADINFO();
        info.cbSize = Marshal.SizeOf(info);
        return GetGUIThreadInfo(thread, ref info) ? info.hwndFocus : IntPtr.Zero;
    }

    static void CaretToEnd(IntPtr box, string text)
    {
        IntPtr r;
        SendMessageTimeout(box, EM_SETSEL, new IntPtr(text.Length), new IntPtr(text.Length), SMTO_ABORTIFHUNG, 200, out r);
        SendMessageTimeout(box, EM_SCROLLCARET, IntPtr.Zero, IntPtr.Zero, SMTO_ABORTIFHUNG, 200, out r);
    }

    // Ctrl+Backspace typed DEL characters: each deletes itself and the word before it
    static string DeleteWords(IntPtr box, string text)
    {
        int caret = 0;
        for (int i = text.IndexOf('\x7f'); i >= 0; i = text.IndexOf('\x7f'))
        {
            int j = i;
            while (j > 0 && char.IsWhiteSpace(text[j - 1])) j--;
            while (j > 0 && !char.IsWhiteSpace(text[j - 1])) j--;
            text = text.Substring(0, j) + text.Substring(i + 1);
            caret = j;
        }
        IntPtr r;
        SendMessageTimeout(box, WM_SETTEXT, IntPtr.Zero, text, SMTO_ABORTIFHUNG, 200, out r);
        SendMessageTimeout(box, EM_SETSEL, new IntPtr(caret), new IntPtr(caret), SMTO_ABORTIFHUNG, 200, out r);
        return text;
    }

    // True when all the text of the box is selected
    static bool SelectsAll(IntPtr box, string text)
    {
        IntPtr sel;
        if (text.Length == 0 || SendMessageTimeout(box, EM_GETSEL, IntPtr.Zero, IntPtr.Zero, SMTO_ABORTIFHUNG, 200, out sel) == IntPtr.Zero) return false;
        long s = sel.ToInt64();
        return (s & 0xFFFF) == 0 && ((s >> 16) & 0xFFFF) == text.Length;
    }

    static void CopyTyped()
    {
        if (rainmeterPid == 0 || !File.Exists(typedPath))
        {
            typedBox = IntPtr.Zero;
            return;
        }
        IntPtr fg = GetForegroundWindow();
        uint pid;
        uint thread = GetWindowThreadProcessId(fg, out pid);
        if (fg == IntPtr.Zero || pid != rainmeterPid || ClassOf(fg) == "RainmeterMeterWindow") return;
        IntPtr box = TextBoxOf(fg);
        if (box == IntPtr.Zero || FocusOf(thread) != box) return;
        string text = TextOf(box);
        if (text == null) return;
        if (text.IndexOf('\x7f') >= 0) text = DeleteWords(box, text);
        try
        {
            // (no copy in it: the skin opened another box since the last one)
            string had = File.ReadAllText(typedPath);
            bool copied = had.StartsWith("WC\n");
            if (had == "END")
            {
                CaretToEnd(box, text);
                caretBox = box;
                caretText = text;
                caretUntil = Environment.TickCount + 250;
            }
            else if (box == caretBox && text == caretText && Environment.TickCount - caretUntil < 0 && SelectsAll(box, text))
            {
                CaretToEnd(box, text); // the plugin selected it again
            }
            if (box == typedBox && text == typedText && copied) return;
            if (text != "") emptyBox = IntPtr.Zero;
            else if (copied && had.Length > 3 && box != emptyBox)
            {
                emptyBox = box;
                return;
            }
            byte[] data = new UTF8Encoding(false).GetBytes("WC\n" + text);
            // Truncate: never creates the file the skin has deleted
            using (var f = new FileStream(typedPath, FileMode.Truncate, FileAccess.Write, FileShare.ReadWrite | FileShare.Delete))
            {
                f.Write(data, 0, data.Length);
            }
            typedBox = box;
            typedText = text;
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }

    static void FollowResize()
    {
        if (rainmeterPid == 0 || !File.Exists(resizePath))
        {
            resizeSkin = IntPtr.Zero;
            resizeSent = null;
            return;
        }
        POINT p;
        if (!GetCursorPos(out p)) return;
        if (resizeSkin == IntPtr.Zero || !IsWindow(resizeSkin))
        {
            // The grip was just pressed: the window under the cursor is the skin's
            IntPtr w = GetAncestor(WindowFromPoint(p), GA_ROOT);
            uint pid;
            GetWindowThreadProcessId(w, out pid);
            if (pid != rainmeterPid || ClassOf(w) != "RainmeterMeterWindow") return;
            resizeSkin = w;
        }
        string config;
        try { config = File.ReadAllText(resizePath).Trim(); }
        catch (IOException) { return; }
        catch (UnauthorizedAccessException) { return; }
        RECT r;
        if (config == "" || config.Contains("\"") || !GetWindowRect(resizeSkin, out r)) return;
        string bang = string.Format("!CommandMeasure MeasureScript \"ResizeMove({0}, {1}, {2}, {3})\" \"{4}\"",
            p.X - r.Left, p.Y - r.Top, r.Right - r.Left, r.Bottom - r.Top, config);
        if (bang == resizeSent) return;
        resizeSent = bang;
        Bang(bang);
    }

    // As Rainmeter.exe passes a bang to the running Rainmeter
    static void Bang(string command)
    {
        IntPtr rainmeter = FindWindow("DummyRainWClass", null);
        if (rainmeter == IntPtr.Zero) return;
        IntPtr text = Marshal.StringToHGlobalUni(command);
        try
        {
            var cds = new COPYDATASTRUCT { dwData = new IntPtr(1), cbData = (command.Length + 1) * 2, lpData = text };
            IntPtr r;
            SendMessageTimeout(rainmeter, WM_COPYDATA, IntPtr.Zero, ref cds, SMTO_ABORTIFHUNG, 500, out r);
        }
        finally { Marshal.FreeHGlobal(text); }
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
        GetWindowThreadProcessId(helper, out rainmeterPid);

        // KeepDialogsOnTop=0: the skin leaves this file, and only the typing is kept
        if (File.Exists(noZOrderPath))
        {
            lowered.Clear();
            return;
        }

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
