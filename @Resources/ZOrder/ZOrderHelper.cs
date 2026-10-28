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
// And it suggests places while the place of an event is typed, as Google Calendar does:
// while Places.txt exists (the skin writes it when it opens that box), what is typed there
// is searched on photon.komoot.io (OpenStreetMap data) a moment after the typing stops, and
// the places found go to PlacesOut.txt for the skin (PlaceList). While they show, Up and
// Down choose one (PlaceSel), Enter puts the chosen one in the box before the plugin gets
// the Enter, and Esc hides them.
//
// Built on first load by launch.cmd with the C# compiler included in Windows (.NET 4,
// C# 5 syntax only). It exits by itself when Rainmeter closes.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Net;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

static class ZOrderHelper
{
    delegate void WinEventProc(IntPtr hook, uint ev, IntPtr hwnd, int idObject, int idChild, uint thread, uint time);
    delegate bool EnumProc(IntPtr hwnd, IntPtr param);
    delegate IntPtr KeyboardProc(int code, IntPtr wp, IntPtr lp);

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
    [DllImport("user32.dll")] static extern IntPtr SetWindowsHookEx(int id, KeyboardProc proc, IntPtr mod, uint thread);
    [DllImport("user32.dll")] static extern bool UnhookWindowsHookEx(IntPtr hook);
    [DllImport("user32.dll")] static extern IntPtr CallNextHookEx(IntPtr hook, int code, IntPtr wp, IntPtr lp);
    [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
    [DllImport("user32.dll")] static extern int GetMessage(out MSG msg, IntPtr hwnd, uint min, uint max);
    [DllImport("user32.dll")] static extern bool PeekMessage(out MSG msg, IntPtr hwnd, uint min, uint max, uint remove);
    [DllImport("user32.dll")] static extern bool PostThreadMessage(uint thread, uint msg, IntPtr wp, IntPtr lp);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern IntPtr GetModuleHandle(string name);

    [StructLayout(LayoutKind.Sequential)] struct POINT { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] struct MSG { public IntPtr hwnd; public uint message; public IntPtr wParam, lParam; public uint time; public POINT pt; }
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
            // The fast timer runs only while Typed.txt or Resize.txt exists: the skin creates one
            // when it opens a box or when the grip is pressed. A watcher wakes it at once; Check()
            // does too (every 250 ms) in case the watcher missed the file.
            typing = new System.Windows.Forms.Timer();
            typing.Interval = 40;
            typing.Tick += delegate
            {
                bool typed = CopyTyped();
                bool resizing = FollowResize();
                if (!typed && !resizing) typing.Stop();
            };
            sync = new Control();
            IntPtr handle = sync.Handle; // (creates the window on this thread: the events arrive here)
            keyProc = OnKey;
            ServicePointManager.SecurityProtocol |= (SecurityProtocolType)3072; // TLS 1.2
            var watcher = new FileSystemWatcher(AppDomain.CurrentDomain.BaseDirectory);
            watcher.NotifyFilter = NotifyFilters.FileName | NotifyFilters.LastWrite;
            watcher.SynchronizingObject = sync;
            FileSystemEventHandler wake = delegate { WakeTyping(); };
            watcher.Created += wake;
            watcher.Changed += wake;
            watcher.Renamed += delegate { WakeTyping(); };
            watcher.EnableRaisingEvents = true;
            WakeTyping();
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

    static System.Windows.Forms.Timer typing; // copies Typed.txt / follows Resize.txt (40 ms)

    // Starts the typing timer when one of its files exists (it stops itself when neither does)
    static void WakeTyping()
    {
        if (typing != null && !typing.Enabled && (File.Exists(typedPath) || File.Exists(resizePath))) typing.Start();
    }

    // False when there is nothing to copy (no Typed.txt): the timer may stop
    static bool CopyTyped()
    {
        if (rainmeterPid == 0 || !File.Exists(typedPath))
        {
            typedBox = IntPtr.Zero;
            PlacesEnd();
            return false;
        }
        IntPtr fg = GetForegroundWindow();
        uint pid;
        uint thread = GetWindowThreadProcessId(fg, out pid);
        if (fg == IntPtr.Zero || pid != rainmeterPid || ClassOf(fg) == "RainmeterMeterWindow") return true;
        IntPtr box = TextBoxOf(fg);
        if (box == IntPtr.Zero || FocusOf(thread) != box) return true;
        string text = TextOf(box);
        if (text == null) return true;
        if (text.IndexOf('\x7f') >= 0) text = DeleteWords(box, text);
        PlacesTick(box, text);
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
            if (box == typedBox && text == typedText && copied) return true;
            if (text != "") emptyBox = IntPtr.Zero;
            else if (copied && had.Length > 3 && box != emptyBox)
            {
                emptyBox = box;
                return true;
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
        return true;
    }

    // False when there is nothing to follow (no Resize.txt): the timer may stop
    static bool FollowResize()
    {
        if (rainmeterPid == 0 || !File.Exists(resizePath))
        {
            resizeSkin = IntPtr.Zero;
            resizeSent = null;
            return false;
        }
        POINT p;
        if (!GetCursorPos(out p)) return true;
        if (resizeSkin == IntPtr.Zero || !IsWindow(resizeSkin))
        {
            // The grip was just pressed: the window under the cursor is the skin's
            IntPtr w = GetAncestor(WindowFromPoint(p), GA_ROOT);
            uint pid;
            GetWindowThreadProcessId(w, out pid);
            if (pid != rainmeterPid || ClassOf(w) != "RainmeterMeterWindow") return true;
            resizeSkin = w;
        }
        string config;
        try { config = File.ReadAllText(resizePath).Trim(); }
        catch (IOException) { return true; }
        catch (UnauthorizedAccessException) { return true; }
        RECT r;
        if (config == "" || config.Contains("\"") || !GetWindowRect(resizeSkin, out r)) return true;
        string bang = string.Format("!CommandMeasure MeasureScript \"ResizeMove({0}, {1}, {2}, {3})\" \"{4}\"",
            p.X - r.Left, p.Y - r.Top, r.Right - r.Left, r.Bottom - r.Top, config);
        if (bang == resizeSent) return true;
        resizeSent = bang;
        Bang(bang);
        return true;
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

    // ---- Place suggestions ----------------------------------------------------------------
    // Places.txt: the skin's config, the number of the box (its Lua actions give it back), the
    // language (en, de, fr: names in it; else as they are written locally) and where to search
    // first (a place, "lat,lon", or nothing: the country of Windows' region settings).
    // PlacesOut.txt: "WC <box number>", then a line per place: name, where, the text to keep
    // (tab separated). Photon is a free service: a search goes out only a moment after the
    // typing stops, one at a time, and what was found is kept for the next time.
    class PlaceBox { public string config, lang, near; public int n; }

    static readonly string placesPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Places.txt");
    static readonly string placesOutPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "PlacesOut.txt");
    static readonly UTF8Encoding Utf8 = new UTF8Encoding(false);
    const string PhotonUrl = "https://photon.komoot.io/api/?q=";
    const int Pause = 250;   // ms of no typing before a search
    const int Spacing = 300; // ms between two searches (3 s after the service said it is busy)
    static Control sync;     // runs the answers of the searches on the main thread
    static string plFile;    // what Places.txt had, and the box it described
    static PlaceBox pl;
    static string plBase;    // the text the box opened with: not searched until it changes
    static string plText;    // the text last seen
    static int plDue;        // when to search plText (0: nothing to search)
    static bool plBusy;      // a request on its way
    static int plFree;       // no request before this time
    static bool plHidden;    // Esc hid the list: not shown again until the text changes
    static string plShown;   // the search whose places show
    static PlaceBox plNoNear; // the box for which where to search could not be found: searched everywhere
    static readonly Dictionary<string, string[]> plCache = new Dictionary<string, string[]>();
    static readonly Dictionary<string, string> plBias = new Dictionary<string, string>(); // near -> &lat=..&lon=..
    // (read by the keyboard hook's thread)
    static volatile string[] plRows; // the texts of the places shown, or null
    static volatile IntPtr plBox;
    static volatile int plSel;       // the place chosen with the keyboard (1..), 0: none

    static bool Due(int time) { return Environment.TickCount - time >= 0; }

    // The box Places.txt describes, or null
    static PlaceBox ReadPlaces()
    {
        string t;
        try
        {
            if (!File.Exists(placesPath)) return null;
            t = File.ReadAllText(placesPath, Utf8);
        }
        catch (IOException) { return pl; }
        catch (UnauthorizedAccessException) { return pl; }
        if (t == plFile && pl != null) return pl;
        string[] lines = t.Replace("\r", "").Split('\n');
        int n;
        if (lines.Length < 2 || !int.TryParse(lines[1].Trim(), out n)) return null;
        var b = new PlaceBox { config = lines[0].Trim(), n = n };
        b.lang = lines.Length > 2 ? lines[2].Trim().ToLowerInvariant() : "";
        b.near = lines.Length > 3 ? lines[3].Trim() : "";
        if (b.config == "" || b.config.Contains("\"")) return null;
        plFile = t;
        return b;
    }

    // Every 40 ms while the box that has the keyboard shows text
    static void PlacesTick(IntPtr box, string text)
    {
        PlaceBox b = ReadPlaces();
        if (b == null)
        {
            PlacesEnd();
            return;
        }
        if (pl == null || b.n != pl.n || box != plBox)
        {
            // A new box: what it shows is not searched (the place an edited event has)
            PlacesEnd();
            pl = b;
            plBox = box;
            plText = text;
            plBase = Query(text);
            if (!plBias.ContainsKey(NearKey(b))) plDue = Environment.TickCount; // (where to search; it opens the connection)
            return;
        }
        if (text != plText)
        {
            plText = text;
            plHidden = false;
            string q = Query(text);
            string[] rows;
            if (q.Length < 3)
            {
                plDue = 0;
                Show(null, null);
            }
            else if (plCache.TryGetValue(CacheKey(q), out rows))
            {
                plDue = 0;
                Show(q, rows);
            }
            else plDue = (Environment.TickCount + Pause) | 1; // (never 0)
        }
        if (plDue != 0 && !plBusy && Due(plDue) && Due(plFree)) Search();
    }

    // The box closed: nothing shows, no search goes out
    static void PlacesEnd()
    {
        pl = null;
        plFile = plBase = plText = plShown = null;
        plRows = null;
        plBox = IntPtr.Zero;
        plSel = 0;
        plDue = 0;
        plHidden = false;
        Hook(false);
    }

    static string Query(string text)
    {
        string q = string.Join(" ", (text ?? "").Split(new[] { ' ', '\t', '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries));
        return q.Length > 200 ? q.Substring(0, 200) : q;
    }

    static string NearKey(PlaceBox b) { return b.lang + "|" + b.near; }

    static string CacheKey(string q) { return NearKey(pl) + "|" + q.ToLowerInvariant(); }

    static string LangParam(string lang)
    {
        return (lang == "en" || lang == "de" || lang == "fr") ? "&lang=" + lang : "";
    }

    // Searches what the box has (first where to search, once)
    static void Search()
    {
        plDue = 0;
        PlaceBox b = pl;
        string bias;
        if (!plBias.TryGetValue(NearKey(b), out bias))
        {
            if (b != plNoNear)
            {
                FindNear(b);
                return;
            }
            bias = "";
        }
        string q = Query(plText);
        if (q.Length < 3 || q == plBase) return;
        string key = CacheKey(q);
        plBusy = true;
        Fetch(PhotonUrl + Uri.EscapeDataString(q) + "&limit=15" + LangParam(b.lang) + bias, delegate(string json, int status)
        {
            plBusy = false;
            plFree = Environment.TickCount + Wait(json, status);
            string[] rows = json != null ? Rows(json) : null;
            if (rows != null) plCache[key] = rows;
            if (pl != b) return;
            if (rows == null && plDue == 0 && Query(plText) == q) plDue = plFree | 1; // (try again)
            else if (rows != null && Query(plText) == q) Show(q, rows);
        });
    }

    // Where to search first: the place of PlaceSearchNear (or "lat,lon"), else the country of
    // Windows' region settings. Then the search.
    static void FindNear(PlaceBox b)
    {
        string key = NearKey(b);
        string[] ll = b.near.Split(',');
        double lat, lon;
        if (ll.Length == 2 && double.TryParse(ll[0].Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out lat)
            && double.TryParse(ll[1].Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out lon))
        {
            plBias[key] = Bias(lat, lon, null);
            plDue = Environment.TickCount | 1;
            return;
        }
        string q = b.near, tag = "place", zoom = null;
        if (q == "")
        {
            q = CountryName();
            tag = "place:country";
            zoom = "5";
        }
        if (q == null)
        {
            plBias[key] = "";
            plDue = Environment.TickCount | 1;
            return;
        }
        plBusy = true;
        Fetch(PhotonUrl + Uri.EscapeDataString(q) + "&limit=1&osm_tag=" + tag + LangParam(b.lang), delegate(string json, int status)
        {
            plBusy = false;
            plFree = Environment.TickCount + Wait(json, status);
            if (json != null)
            {
                // (nothing found: searched everywhere)
                double[] p = FirstPoint(json);
                plBias[key] = p != null ? Bias(p[1], p[0], zoom) : "";
            }
            else plNoNear = b; // (tried again for the next box)
            if (pl == b) plDue = plFree | 1;
        });
    }

    // ms before the next request: more after a refusal (busy) or no answer (offline)
    static int Wait(string json, int status)
    {
        return json != null ? Spacing : (status == 429 || status == 503) ? 3000 : 5000;
    }

    static string Bias(double lat, double lon, string zoom)
    {
        return "&lat=" + lat.ToString("0.#####", CultureInfo.InvariantCulture) + "&lon="
            + lon.ToString("0.#####", CultureInfo.InvariantCulture) + (zoom != null ? "&zoom=" + zoom : "");
    }

    // English name of the country of Windows' region settings (Italy), or null
    static string CountryName()
    {
        try
        {
            using (var k = Registry.CurrentUser.OpenSubKey(@"Control Panel\International\Geo"))
            {
                string code = k != null ? k.GetValue("Name") as string : null;
                if (!string.IsNullOrEmpty(code)) return new RegionInfo(code).EnglishName;
            }
        }
        catch (Exception) { }
        try { return RegionInfo.CurrentRegion.EnglishName; }
        catch (Exception) { return null; }
    }

    // Gets url on a thread of the pool; done(json or null, HTTP status or 0) runs on this thread
    static void Fetch(string url, Action<string, int> done)
    {
        ThreadPool.QueueUserWorkItem(delegate
        {
            string json = null;
            int status = 0;
            try
            {
                var req = (HttpWebRequest)WebRequest.Create(url);
                req.UserAgent = "WeeklyCalendar (Rainmeter skin; https://github.com/RobertoReale/WeeklyCalendar)";
                req.Timeout = req.ReadWriteTimeout = 8000;
                req.AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate;
                using (var resp = (HttpWebResponse)req.GetResponse())
                using (var r = new StreamReader(resp.GetResponseStream(), Encoding.UTF8))
                {
                    status = (int)resp.StatusCode;
                    json = r.ReadToEnd();
                }
            }
            catch (WebException e)
            {
                var resp = e.Response as HttpWebResponse;
                if (resp != null) status = (int)resp.StatusCode;
            }
            catch (Exception) { }
            try { sync.BeginInvoke((MethodInvoker)delegate { done(json, status); }); }
            catch (Exception) { }
        });
    }

    static Dictionary<string, object> Obj(object o) { return o as Dictionary<string, object>; }

    static object[] Features(string json)
    {
        try
        {
            var root = Obj(new JavaScriptSerializer().DeserializeObject(json));
            object f;
            return root != null && root.TryGetValue("features", out f) ? f as object[] : null;
        }
        catch (Exception) { return null; }
    }

    // [lon, lat] of the first place found
    static double[] FirstPoint(string json)
    {
        object[] fs = Features(json);
        if (fs == null || fs.Length == 0) return null;
        try
        {
            var geo = Obj(Obj(fs[0])["geometry"]);
            var c = (object[])geo["coordinates"];
            return new[] { Convert.ToDouble(c[0], CultureInfo.InvariantCulture), Convert.ToDouble(c[1], CultureInfo.InvariantCulture) };
        }
        catch (Exception) { return null; }
    }

    // A text of the answer on one line, without tabs
    static string Prop(Dictionary<string, object> p, string k)
    {
        object v;
        if (p == null || !p.TryGetValue(k, out v) || v == null) return "";
        var sb = new StringBuilder();
        foreach (char ch in v.ToString()) sb.Append(char.IsControl(ch) ? ' ' : ch);
        return Query(sb.ToString());
    }

    static void AddPart(List<string> parts, string s)
    {
        if (s != "" && !parts.Contains(s)) parts.Add(s);
    }

    // Up to 5 places: name, where (street, town, area, country) and the text the event keeps,
    // as Google's addresses ("Viale Romagna, 12, 20133 Milano, Italia"); null: not an answer
    static string[] Rows(string json)
    {
        object[] fs = Features(json);
        if (fs == null) return null;
        var rows = new List<string>();
        var seen = new HashSet<string>();
        foreach (object f in fs)
        {
            if (rows.Count == 5) break;
            Dictionary<string, object> p;
            try { p = Obj(Obj(f)["properties"]); }
            catch (Exception) { continue; }
            string name = Prop(p, "name"), street = Prop(p, "street"), num = Prop(p, "housenumber");
            string postcode = Prop(p, "postcode"), town = Prop(p, "city"), county = Prop(p, "county");
            string state = Prop(p, "state"), country = Prop(p, "country"), type = Prop(p, "type");
            if (Minor(Prop(p, "osm_key"), Prop(p, "osm_value"))) continue;
            bool area = type == "city" || type == "county" || type == "state" || type == "country";
            if (town == "") town = Prop(p, "locality");
            if (area) town = "";
            string region = county != "" && county != town ? county : state;
            string road = street != "" ? (num != "" ? street + ", " + num : street) : "";
            string title = name;
            if (title == "") { title = road; road = ""; }
            if (title == "") continue;
            var where = new List<string> { title };
            AddPart(where, road);
            AddPart(where, town);
            AddPart(where, region);
            AddPart(where, country);
            where.RemoveAt(0);
            var keep = new List<string> { title };
            AddPart(keep, road);
            if (town != "" && town != title) keep.Add(postcode != "" ? postcode + " " + town : town);
            else if (area) AddPart(keep, region);
            AddPart(keep, country);
            string sub = string.Join(", ", where.ToArray());
            if (!seen.Add(title + "\t" + sub)) continue; // (the pieces of one street)
            rows.Add(title + "\t" + sub + "\t" + string.Join(", ", keep.ToArray()));
        }
        return rows.ToArray();
    }

    // Stops, platforms, entrances, tunnels...: many have the name of the place looked for
    static bool Minor(string key, string value)
    {
        switch (key)
        {
            case "public_transport": case "tunnel": case "entrance": case "barrier": return true;
            case "railway": return value != "station" && value != "halt";
            case "highway":
                switch (value)
                {
                    case "bus_stop": case "platform": case "elevator": case "crossing": case "traffic_signals":
                    case "stop": case "give_way": case "turning_circle": case "street_lamp": case "speed_camera":
                    case "emergency_access_point": case "motorway_junction": return true;
                }
                return false;
        }
        return false;
    }

    // Shows rows (null: hides what shows) through PlacesOut.txt and PlaceList
    static void Show(string q, string[] rows)
    {
        if (pl == null) return;
        bool none = rows == null || rows.Length == 0;
        if (none ? plRows == null : (plHidden || q == plShown)) return;
        var keep = new List<string>();
        if (!none) foreach (string r in rows) keep.Add(r.Split('\t')[2]);
        try { File.WriteAllText(placesOutPath, "WC " + pl.n + "\n" + (none ? "" : string.Join("\n", rows)), Utf8); }
        catch (IOException) { return; }
        catch (UnauthorizedAccessException) { return; }
        plShown = none ? null : q;
        plSel = 0;
        plRows = none ? null : keep.ToArray();
        Bang(string.Format("!CommandMeasure MeasureScript \"PlaceList({0})\" \"{1}\"", pl.n, pl.config));
        Hook(!none);
    }

    // ---- Keys while places show: on a thread of its own, so that a busy moment of this one
    // (a bang Rainmeter takes its time with) never slows down the keyboard. The hook is set
    // only while places show, and acts only while their box has the keyboard.
    static KeyboardProc keyProc; // referenced so the delegate is not garbage collected
    static uint hookThread;
    static bool hookOn;
    const uint WM_APP = 0x8000;

    static void Hook(bool on)
    {
        if (on == hookOn) return;
        hookOn = on;
        if (hookThread == 0)
        {
            if (!on) return;
            var ready = new ManualResetEvent(false);
            var t = new Thread(delegate()
            {
                MSG m;
                PeekMessage(out m, IntPtr.Zero, 0, 0, 0); // (creates its message queue)
                hookThread = GetCurrentThreadId();
                ready.Set();
                IntPtr hook = IntPtr.Zero;
                while (GetMessage(out m, IntPtr.Zero, 0, 0) > 0)
                {
                    if (m.message == WM_APP + 1 && hook == IntPtr.Zero) hook = SetWindowsHookEx(13, keyProc, GetModuleHandle(null), 0); // WH_KEYBOARD_LL
                    else if (m.message == WM_APP + 2 && hook != IntPtr.Zero)
                    {
                        UnhookWindowsHookEx(hook);
                        hook = IntPtr.Zero;
                    }
                }
            });
            t.IsBackground = true;
            t.Start();
            ready.WaitOne(2000);
        }
        PostThreadMessage(hookThread, on ? WM_APP + 1 : WM_APP + 2, IntPtr.Zero, IntPtr.Zero);
    }

    static IntPtr OnKey(int code, IntPtr wp, IntPtr lp)
    {
        if (code >= 0 && wp.ToInt64() == 0x100) // WM_KEYDOWN
        {
            int vk = Marshal.ReadInt32(lp);
            if ((vk == 0x26 || vk == 0x28 || vk == 0x0D || vk == 0x1B) && PlaceKey(vk)) return new IntPtr(1);
        }
        return CallNextHookEx(IntPtr.Zero, code, wp, lp);
    }

    // Up / Down (0x26 / 0x28), Enter (0x0D) or Esc (0x1B) in the box: true when it is used up
    static bool PlaceKey(int vk)
    {
        string[] rows = plRows;
        IntPtr box = plBox;
        if (rows == null || box == IntPtr.Zero) return false;
        if ((GetAsyncKeyState(0x11) & 0x8000) != 0 || (GetAsyncKeyState(0x12) & 0x8000) != 0) return false; // Ctrl, Alt
        uint pid;
        if (FocusOf(GetWindowThreadProcessId(GetForegroundWindow(), out pid)) != box) return false;
        if (vk == 0x1B)
        {
            Post(delegate
            {
                plHidden = true;
                plDue = 0;
                Show(null, null);
            });
            return true;
        }
        if (vk == 0x0D)
        {
            // The chosen place goes into the box: the plugin then gets the Enter with it
            int s = plSel;
            if (s < 1 || s > rows.Length) return false;
            IntPtr r;
            SendMessageTimeout(box, WM_SETTEXT, IntPtr.Zero, rows[s - 1], SMTO_ABORTIFHUNG, 200, out r);
            CaretToEnd(box, rows[s - 1]);
            try
            {
                byte[] data = Utf8.GetBytes("WC\n" + rows[s - 1]);
                using (var f = new FileStream(typedPath, FileMode.Truncate, FileAccess.Write, FileShare.ReadWrite | FileShare.Delete))
                {
                    f.Write(data, 0, data.Length);
                }
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
            plRows = null;
            return false;
        }
        // Down from the last one, or Up from the first, goes back to the text typed
        int sel = plSel + (vk == 0x28 ? 1 : -1);
        if (sel > rows.Length) sel = 0;
        if (sel < 0) sel = rows.Length;
        plSel = sel;
        Post(delegate
        {
            if (pl != null && plRows != null) Bang(string.Format("!CommandMeasure MeasureScript \"PlaceSel({0}, {1})\" \"{2}\"", pl.n, sel, pl.config));
        });
        return true;
    }

    static void Post(MethodInvoker fn)
    {
        try { sync.BeginInvoke(fn); }
        catch (Exception) { }
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
        WakeTyping();

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
