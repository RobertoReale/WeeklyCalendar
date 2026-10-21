"""WeeklyCalendar test suite.

Runs @Resources/Calendar.lua in a Lua 5.1 interpreter (via the `lupa` package)
against a mock of the Rainmeter API, using the synthetic feeds in tests/fixtures.

    pip install lupa
    python tests/run_tests.py

Exit code 0 means every test passed.
"""
import calendar
import os
import re
import shutil
import sys
import tempfile
import traceback
from datetime import date, datetime, timedelta, timezone

from lupa.lua51 import LuaRuntime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA_FILE = os.path.join(ROOT, '@Resources', 'Calendar.lua')
INI_FILE = os.path.join(ROOT, 'WeeklyCalendar.ini')
SETTINGS_FILE = os.path.join(ROOT, '@Resources', 'Settings.inc')
FIXTURES = os.path.join(ROOT, 'tests', 'fixtures')

# Gives the tests access to the script's local functions and lets them control "now".
PRELUDE = """
local _realTime = os.time
_TEST_NOW = nil
os.time = function(t)
  if t ~= nil then return _realTime(t) end
  return _TEST_NOW or _realTime()
end
"""
EXPORTS = """
_WC = { parseICS = parseICS, buildOverrides = buildOverrides, buildInstances = buildInstances,
        daysFromCivil = daysFromCivil, cfg = cfg, LANGS = LANGS, toLatin1 = toLatin1 }
"""


def read_lua_source():
    raw = open(LUA_FILE, 'rb').read()
    if raw.startswith(b'\xff\xfe'):
        return raw[2:].decode('utf-16-le')
    return raw.decode('utf-8-sig')


def read_vars(path):
    out = {}
    for line in open(path, encoding='utf-8-sig'):
        m = re.match(r'^([A-Za-z0-9_]+)=(.*)$', line.strip())
        if m:
            out[m.group(1)] = m.group(2)
    return out


def ini_sections():
    text = open(INI_FILE, encoding='utf-8-sig').read()
    return set(re.findall(r'^\[([^\]]+)\]', text, re.M))


def utc(y, mo, d, h=0, mi=0):
    return calendar.timegm((y, mo, d, h, mi, 0))


class MockSkin:
    """Minimal stand-in for Rainmeter's SKIN object: records bangs and meter state."""

    def __init__(self, variables, sections):
        self.vars = variables
        self.sections = sections
        self.options = {}
        self.visible = {}
        self.logs = []
        self.bang_count = 0
        self.bangs = []
        self.unknown = set()
        self.measure_values = {}

    def _args(self, args):
        return list(args[1:]) if args and isinstance(args[0], MockSkin) else list(args)

    def GetVariable(self, *args):
        return self.vars.get(self._args(args)[0])

    def Bang(self, *args):
        a = self._args(args)
        self.bang_count += 1
        name = a[0]
        self.bangs.append(a)
        if name in ('!SetOption', '!HideMeter', '!ShowMeter', '!UpdateMeter',
                    '!DisableMeasure', '!EnableMeasure', '!CommandMeasure'):
            if a[1] not in self.sections:
                self.unknown.add(a[1])
        if name == '!SetOption':
            self.options[(a[1], a[2])] = a[3]
        elif name == '!ShowMeter':
            self.visible[a[1]] = True
        elif name == '!HideMeter':
            self.visible[a[1]] = False
        elif name == '!Log':
            self.logs.append(tuple(a[1:]))

    def GetMeasure(self, *args):
        value = self.measure_values.get(self._args(args)[0], '')

        class Measure:
            def GetStringValue(self, *a):
                return value
        return Measure()

    def opt(self, meter, option):
        return self.options.get((meter, option))

    def shown(self, meter):
        return self.visible.get(meter, False)


def new_runtime(skin):
    lua = LuaRuntime()
    lua.globals().SKIN = skin
    lua.execute(PRELUDE + read_lua_source() + EXPORTS)
    return lua


# ---------------------------------------------------------------------------
# Recurrence / timezone / parsing tests (no layout)
# ---------------------------------------------------------------------------
def load_instances(show_declined=True):
    skin = MockSkin({}, ini_sections())
    lua = new_runtime(skin)
    wc = lua.globals()._WC
    wc.cfg.lang = wc.LANGS.en
    wc.cfg.showDeclined = show_declined
    text = open(os.path.join(FIXTURES, 'sample.ics'), encoding='utf-8', newline='').read()
    wc.parseICS(text, 1)
    wc.buildOverrides()
    inst = wc.buildInstances(wc.daysFromCivil(2026, 12, 1), wc.daysFromCivil(2029, 1, 1))
    by_title = {}
    for i in range(1, len(inst) + 1):
        it = inst[i]
        by_title.setdefault(it.title, []).append(it)
    for lst in by_title.values():
        lst.sort(key=lambda it: it.s if it.kind == 'timed' else it.sDay)
    return by_title


def starts(lst):
    return [it.s for it in lst]


def test_bysetpos_last_weekday_with_builtin_zone():
    # Europe/Rome has no VTIMEZONE in the fixture: the built-in EU rule is used.
    got = starts(load_instances()['Last weekday'])
    assert got == [utc(2027, 1, 29, 8), utc(2027, 2, 26, 8), utc(2027, 3, 31, 7)], got


def test_bymonthday_and_byday_intersect():
    got = starts(load_instances()['Friday 13th'])
    assert got == [utc(2027, 8, 13, 12), utc(2028, 10, 13, 12)], got
    for t in got:
        assert datetime.fromtimestamp(t, timezone.utc).weekday() == 4  # Friday


def test_yearly_byday_without_bymonth():
    got = starts(load_instances()['Twentieth Monday'])
    assert got == [utc(2027, 5, 17, 10), utc(2028, 5, 15, 10)], got


def test_unsynced_dtstart_counts_as_first():
    got = starts(load_instances()['Unsynced start'])
    assert got == [utc(2027, 1, 6, 10), utc(2027, 1, 11, 10), utc(2027, 1, 18, 10)], got


def test_rdate_and_exdate():
    got = starts(load_instances()['Rdate and exdate'])
    assert got == [utc(2027, 2, 1, 15), utc(2027, 2, 10, 15)], got


def test_recurrence_id_override():
    inst = load_instances()
    assert starts(inst['Daily']) == [utc(2027, 3, 1, 9), utc(2027, 3, 3, 9)], starts(inst['Daily'])
    assert starts(inst['Moved']) == [utc(2027, 3, 2, 13)]


def test_us_dst_builtin_zone():
    inst = load_instances()
    assert starts(inst['New York winter']) == [utc(2027, 3, 10, 14)]
    assert starts(inst['New York summer']) == [utc(2027, 3, 15, 13)]


def test_windows_zone_name():
    assert starts(load_instances()['Windows zone']) == [utc(2027, 7, 1, 8)]


def test_vtimezone_is_used():
    assert starts(load_instances()['Custom VTIMEZONE']) == [utc(2027, 7, 1, 7)]


def test_declined_detection():
    inst = load_instances()
    assert inst['Declined meeting'][0].declined is True
    # Only the owner's PARTSTAT counts
    assert inst['Accepted meeting'][0].declined is False
    assert 'Declined meeting' not in load_instances(show_declined=False)
    assert 'Cancelled' not in inst


def test_yearly_bymonthday_applies_to_every_month():
    inst = load_instances()['First of month']
    got = [it.sDay for it in inst]
    lua_days = [(date(2027, m, 1) - date(1970, 1, 1)).days for m in (1, 2, 3)]
    assert got == lua_days, got


def test_utf8_text_and_unescape():
    assert 'Attività, università' in load_instances()


# ---------------------------------------------------------------------------
# Layout tests (full skin cycle against the mock)
# ---------------------------------------------------------------------------
class Skin:
    def __init__(self, ics='layout.ics', dir_prefix='wc_test_', feeds=None, **overrides):
        self.dir = tempfile.mkdtemp(prefix=dir_prefix)
        os.makedirs(os.path.join(self.dir, 'DownloadFile'))
        os.makedirs(os.path.join(self.dir, '@Resources'))
        shutil.copy(os.path.join(FIXTURES, ics), os.path.join(self.dir, 'DownloadFile', 'calendar1.ics'))
        # feeds: {2: 'holidays.ics', 3: 'tasks.ics'} - extra calendars, with a URL each
        for i, name in (feeds or {}).items():
            shutil.copy(os.path.join(FIXTURES, name), os.path.join(self.dir, 'DownloadFile', 'calendar%d.ics' % i))
            overrides.setdefault('IcalUrl%d' % i, 'https://example.com/feed%d.ics' % i)
        variables = read_vars(SETTINGS_FILE)
        variables.update({
            'IcalUrl1': 'https://calendar.google.com/calendar/ical/me%40example.com/private-x/basic.ics',
            'CURRENTPATH': self.dir + os.sep,
            '@': os.path.join(self.dir, '@Resources') + os.sep,
            'Language': 'en', 'StartHour': '8', 'EndHour': '20', 'AutoScroll': '1',
            'AutoScrollHour': '14', 'FirstDay': '1',
        })
        variables.update({k: str(v) for k, v in overrides.items()})
        self.mock = MockSkin(variables, ini_sections())
        self.lua = new_runtime(self.mock)
        self.g = self.lua.globals()

    def at(self, y, mo, d, h, mi=0, s=0):
        self.g._TEST_NOW = self.lua.eval(
            'os.time({year=%d,month=%d,day=%d,hour=%d,min=%d,sec=%d})' % (y, mo, d, h, mi, s))

    def start(self, *now):
        self.at(*now)
        self.g.Initialize()
        self.g.Update()
        return self

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def check_clean(self):
        assert not self.mock.unknown, 'bangs to missing sections: %s' % self.mock.unknown
        errors = [l for l in self.mock.logs if l[-1] in ('Error',)]
        assert not errors, errors

    def all_day(self):
        """Shown all-day chips as {text: meter index}."""
        return {self.mock.opt('ADTx%d' % i, 'Text'): i for i in range(1, 22) if self.mock.shown('ADTx%d' % i)}

    def event_titles(self):
        out = []
        for i in range(1, 81):
            if self.mock.shown('EvT%d' % i):
                out.append(self.mock.opt('EvT%d' % i, 'Text'))
        return out


def with_skin(fn):
    def run():
        sk = Skin()
        try:
            fn(sk)
            sk.check_clean()
        finally:
            sk.close()
    run.__name__ = fn.__name__
    return run


@with_skin
def test_layout_hidden_event_indicators(sk):
    sk.start(2027, 3, 3, 12)  # Wednesday 12:00, view 08-20 (week starts Monday 1 March)
    m = sk.mock
    # Tuesday (index 1): "Early run" 06:00 is above the view
    assert m.shown('HidUp1') and m.opt('HidUp1', 'Text') == '▲ 1', m.opt('HidUp1', 'Text')
    assert 'ScrollToHour(6)' in m.opt('HidUp1', 'LeftMouseUpAction')
    assert 'Early run' in m.opt('HidUp1', 'ToolTipText')
    # Wednesday (index 2): "Late dinner" 22:00-23:00 is below the view
    assert m.shown('HidDn2') and m.opt('HidDn2', 'Text') == '▼ 1'
    assert 'ScrollToHour(11)' in m.opt('HidDn2', 'LeftMouseUpAction')
    assert not m.shown('HidUp0') and not m.shown('HidDn0')
    # Clicking the indicator scrolls so the event becomes visible
    sk.g.ScrollToHour(11)
    assert not m.shown('HidDn2')
    assert 'Late dinner' in ' '.join(sk.event_titles())
    assert m.shown('HidUp1')  # Tuesday's 06:00 event is still above the 11-23 view
    assert not m.shown('HidUp2')  # Wednesday's 11:30 event is inside it


@with_skin
def test_layout_more_all_day_tooltip(sk):
    sk.start(2027, 3, 3, 12)
    m = sk.mock
    texts = [m.opt('ADTx%d' % i, 'Text') for i in range(1, 22) if m.shown('ADTx%d' % i)]
    assert texts == ['All day 1', 'All day 2', '+3 more'], texts
    more = [i for i in range(1, 22) if m.opt('ADTx%d' % i, 'Text') == '+3 more'][0]
    assert m.opt('ADTx%d' % more, 'ToolTipText') == 'All day 3#CRLF#All day 4#CRLF#All day 5'


@with_skin
def test_layout_declined_is_outlined(sk):
    sk.start(2027, 3, 3, 12)
    m = sk.mock
    idx = [i for i in range(1, 81) if m.opt('EvT%d' % i, 'Text') == 'Declined meeting'][0]
    shape = m.opt('EvBg%d' % idx, 'Shape')
    assert 'Fill Color 255,255,255,255' in shape and 'Stroke Color 3,155,229,255' in shape, shape
    assert 'Declined' in m.opt('EvBg%d' % idx, 'ToolTipText')
    assert 'Attività università' in sk.event_titles()


def test_layout_hide_declined():
    sk = Skin(ShowDeclined=0)
    try:
        sk.start(2027, 3, 3, 12)
        assert 'Declined meeting' not in sk.event_titles()
        sk.check_clean()
    finally:
        sk.close()


@with_skin
def test_layout_past_fade_updates_on_its_own(sk):
    sk.start(2027, 3, 3, 12)
    m = sk.mock
    idx = [i for i in range(1, 81) if (m.opt('EvT%d' % i, 'Text') or '').startswith('Ending soon')][0]
    assert 'Fill Color 3,155,229,255' in m.opt('EvBg%d' % idx, 'Shape')
    sk.at(2027, 3, 3, 12, 2)
    sk.g.Update()
    assert 'Fill Color 3,155,229,255' not in m.opt('EvBg%d' % idx, 'Shape'), m.opt('EvBg%d' % idx, 'Shape')


@with_skin
def test_layout_redundant_bangs_are_skipped(sk):
    sk.start(2027, 3, 3, 12)
    before = sk.mock.bang_count
    sk.g.ScrollHours(1)
    first = sk.mock.bang_count - before
    sk.g.ScrollHours(-1)
    before = sk.mock.bang_count
    sk.g.ResetScroll()   # same view as the one already on screen
    again = sk.mock.bang_count - before
    assert again < 10, again
    assert first < 600, first


@with_skin
def test_week_navigation_survives_week_rollover(sk):
    sk.start(2027, 3, 7, 23, 59)          # Sunday night, week of 1 March
    sk.g.ShiftWeek(1)                     # look at the week of 8 March
    assert sk.mock.opt('DayNum0', 'Text') == '8'
    sk.at(2027, 3, 8, 0, 1)               # a new week begins
    sk.g.Update()
    assert sk.mock.opt('DayNum0', 'Text') == '8', sk.mock.opt('DayNum0', 'Text')
    sk.g.ShiftWeek(-1)
    assert sk.mock.opt('DayNum0', 'Text') == '1'
    sk.g.GoToday()
    assert sk.mock.opt('DayNum0', 'Text') == '8'


def test_italian_translation_and_context_menu():
    sk = Skin(Language='it')
    try:
        sk.start(2027, 3, 3, 12)
        m = sk.mock
        assert m.opt('Rainmeter', 'ContextTitle') == 'Aggiorna ora'
        assert m.opt('Rainmeter', 'ContextTitle7') == 'Indirizzi calendario'
        assert m.opt('CalAppTitle', 'Text') == 'Calendario'
        assert m.opt('BtnPrev', 'ToolTipText') == 'Settimana precedente'
        assert int(m.opt('BtnToday', 'X')) > 142  # moved right of the longer title
        sk.check_clean()
    finally:
        sk.close()


def test_dark_theme_and_color_override():
    sk = Skin(Theme='dark', NowColor='1,2,3,255')
    try:
        sk.start(2027, 3, 3, 12)
        m = sk.mock
        assert 'Fill Color 30,31,32,255' in m.opt('BG', 'Shape')
        assert m.opt('DayNum0', 'FontColor') == '227,227,227,255'
        assert '1,2,3,255' in m.opt('NowLine', 'Shape')
        sk.check_clean()
    finally:
        sk.close()


@with_skin
def test_reload_clears_only_its_own_feed_error(sk):
    sk.mock.vars['IcalUrl2'] = 'https://example.com/second.ics'
    sk.start(2027, 3, 3, 12)
    sk.g.NetError(1)
    sk.g.Reload(2)
    assert 'offline' in sk.mock.opt('TbSync', 'Text')
    sk.g.Reload(1)
    assert 'offline' not in sk.mock.opt('TbSync', 'Text')


@with_skin
def test_private_file_is_created(sk):
    sk.start(2027, 3, 3, 12)
    text = open(os.path.join(sk.dir, '@Resources', 'Private.inc'), encoding='utf-8').read()
    assert 'IcalUrl1=' in text and 'MyEmail=' in text


@with_skin
def test_many_weeks_without_errors(sk):
    sk.start(2027, 3, 3, 12)
    for n in [-1] * 10 + [1] * 25:
        sk.g.ShiftWeek(n)
    for d in [1] * 20 + [-1] * 20:
        sk.g.ScrollHours(d)


def test_tasks_and_holidays():
    sk = Skin(feeds={2: 'holidays.ics', 3: 'tasks.ics'}, Language='it')
    try:
        sk.start(2027, 3, 3, 12)  # Wednesday
        m, ad = sk.mock, sk.all_day()
        purple = '142,36,170,255'
        # Open task due today: circle, full color, after the holiday of the same day
        i = [v for k, v in ad.items() if k.startswith('○ Simulazione')][0]  # truncated to fit
        assert i > ad['Festa di prova'], ad
        assert 'Fill Color ' + purple in m.opt('ADBg%d' % i, 'Shape')
        assert m.opt('ADTx%d' % i, 'InlineSetting') == ''
        assert 'Attività' in m.opt('ADBg%d' % i, 'ToolTipText')
        # Completed task: check mark, title struck through, faded, escaped comma restored
        i = ad['✓ Esercizi, parte 2']
        assert m.opt('ADTx%d' % i, 'InlineSetting') == 'Strikethrough'
        assert m.opt('ADTx%d' % i, 'InlinePattern') == r'^\S+ (.*)$'
        assert 'Fill Color ' + purple not in m.opt('ADBg%d' % i, 'Shape')
        assert 'Attività completata' in m.opt('ADBg%d' % i, 'ToolTipText')
        # Open task on a past day: faded, not struck through
        i = ad['○ Ripasso']
        # Task notes after a blank line, one tooltip line per line of the notes
        assert m.opt('ADBg%d' % i, 'ToolTipText').endswith('#CRLF##CRLF#capitoli 1-3#CRLF#esercizi 4, 5 ( x)')
        assert 'Fill Color ' + purple not in m.opt('ADBg%d' % i, 'Shape')
        assert m.opt('ADTx%d' % i, 'InlineSetting') == ''
        # Holiday: its own color
        assert 'Fill Color 11,128,67,255' in m.opt('ADBg%d' % ad['Festa di prova'], 'Shape')
        sk.check_clean()
    finally:
        sk.close()


@with_skin
def test_past_all_day_events_fade(sk):
    sk.start(2027, 3, 5, 12)  # Friday: Thursday's all-day events are over
    m = sk.mock
    i = sk.all_day()['All day 1']
    assert 'Fill Color 3,155,229,255' not in m.opt('ADBg%d' % i, 'Shape'), m.opt('ADBg%d' % i, 'Shape')
    sk.at(2027, 3, 4, 12)     # the same week seen on Thursday: not faded yet
    sk.g.GoToday()
    i = sk.all_day()['All day 1']
    assert 'Fill Color 3,155,229,255' in m.opt('ADBg%d' % i, 'Shape')


def test_unreadable_feed_is_reported():
    sk = Skin(feeds={3: 'not_ical.html'})
    try:
        sk.start(2027, 3, 3, 12)
        sk.g.Reload(3)
        m = sk.mock
        assert 'feed error' in m.opt('TbSync', 'Text'), m.opt('TbSync', 'Text')
        assert 'calendar 3' in m.opt('TbSync', 'ToolTipText')
        assert sk.event_titles(), 'the working feed must still be shown'
    finally:
        sk.close()


def test_helper_started_only_when_enabled():
    for value, expected in (('1', True), ('0', False)):
        sk = Skin(KeepDialogsOnTop=value)
        try:
            sk.start(2027, 3, 3, 12)
            calls = []
            sk.mock.Bang = lambda *a: calls.append(sk.mock._args(a))
            sk.g.StartHelper()
            assert (['!CommandMeasure', 'MeasureZOrderHelper', 'Run'] in calls) == expected, (value, calls)
        finally:
            sk.close()


def test_google_tasks_script_output():
    """Runs tools/GoogleTasksFeed.gs under Node with a fake Tasks API and parses the result."""
    node = shutil.which('node')
    if not node:
        print('      (skipped: node not installed)')
        return
    import json
    import subprocess
    script = open(os.path.join(ROOT, 'tools', 'GoogleTasksFeed.gs'), encoding='utf-8').read()
    harness = script + r"""
var calls = [];
var Utilities = { formatDate: function () { return '20270301T080000Z'; } };
var Tasks = {
  Tasklists: { list: function (a) { calls.push(['lists', a]); return { items: [{ id: 'L1', title: 'Le mie attività' }] }; } },
  Tasks: { list: function (id, a) {
    calls.push(['tasks', a]);
    if (!a.pageToken) return { nextPageToken: 'p2', items: [
      { id: 'a', title: 'Esame; parte 1, scritto', status: 'needsAction', due: '2027-03-03T00:00:00.000Z' },
      { id: 'b', title: 'Senza data', status: 'needsAction' } ] };
    return { items: [
      { id: 'c', title: 'Fatto', status: 'completed', due: '2027-03-02T00:00:00.000Z', notes: 'riga 1\nriga 2' },
      { id: 'd', title: 'Cancellato', status: 'needsAction', due: '2027-03-02T00:00:00.000Z', deleted: true } ] };
  } }
};
process.stdout.write(JSON.stringify({ ics: buildFeed(), calls: calls }));
"""
    res = subprocess.run([node, '-e', harness], capture_output=True, encoding='utf-8')
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert 'X-WC-TASKLIST:L1\r\nX-WC-TASKID:a\r\n' in out['ics'], out['ics']
    assert 'pageToken' not in out['calls'][1][1] and out['calls'][2][1]['pageToken'] == 'p2'
    assert out['calls'][1][1]['showHidden'] is True and out['calls'][1][1]['showCompleted'] is True
    lua = new_runtime(MockSkin({}, ini_sections()))
    wc = lua.globals()._WC
    wc.cfg.lang = wc.LANGS.en
    wc.cfg.showDeclined = True
    wc.parseICS(out['ics'], 3)
    wc.buildOverrides()
    first = wc.daysFromCivil(2027, 3, 1)
    inst = wc.buildInstances(first, first + 7)
    got = sorted((inst[i].title, inst[i].task, inst[i].sDay - first) for i in range(1, len(inst) + 1))
    assert got == [('Esame; parte 1, scritto', 'open', 2), ('Fatto', 'done', 1)], got

    # doGet(?action=complete|reopen&list=..&task=..) patches the task and answers OK
    harness = script + r"""
var patches = [];
var ContentService = { MimeType: { ICAL: 'ical' }, createTextOutput: function (s) {
  return { text: s, setMimeType: function () { return this; } }; } };
var Tasks = { Tasks: { patch: function (res, list, task) {
  if (task === 'missing') throw new Error('Not Found');
  patches.push([res, list, task]); } } };
process.stdout.write(JSON.stringify({
  done: doGet({ parameter: { action: 'complete', list: 'L1', task: 'a' } }).text,
  open: doGet({ parameter: { action: 'reopen', list: 'L1', task: 'c' } }).text,
  bad: doGet({ parameter: { action: 'complete', list: 'L1', task: 'missing' } }).text,
  patches: patches }));
"""
    res = subprocess.run([node, '-e', harness], capture_output=True, encoding='utf-8')
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert out['done'] == 'OK' and out['open'] == 'OK', out
    assert out['bad'].startswith('ERROR'), out
    assert out['patches'] == [[{'status': 'completed'}, 'L1', 'a'],
                              [{'status': 'needsAction', 'completed': None}, 'L1', 'c']], out['patches']


def test_latin1_path_conversion():
    lua = new_runtime(MockSkin({}, ini_sections()))
    # Lua decimal escapes: \195\169 is "é" in UTF-8, \233 is "é" in Latin-1
    assert lua.eval(r"_WC.toLatin1('C:\\Users\\Jos\195\169') == 'C:\\Users\\Jos\233'")
    assert lua.eval(r"_WC.toLatin1('plain') == 'plain'")
    assert lua.eval(r"_WC.toLatin1('\226\150\178') == nil")  # U+25B2 has no Latin-1 byte


def test_skin_folder_with_accented_name():
    import ctypes
    if ctypes.windll.kernel32.GetACP() != 1252:
        print('      (skipped: ANSI code page is not 1252)')
        return
    sk = Skin(dir_prefix='wc_test_José_')
    try:
        sk.start(2027, 3, 3, 12)
        # "Late dinner" is outside the view; its indicator proves the feed was read
        assert sk.mock.shown('HidDn2'), 'calendar file was not read from the accented path'
        sk.check_clean()
    finally:
        sk.close()


def test_lua_file_is_utf16_with_bom():
    # Rainmeter 4.5 only treats Lua strings as UTF-8 when the script is UTF-16 LE with BOM
    assert open(LUA_FILE, 'rb').read(2) == b'\xff\xfe', 'Calendar.lua must be saved as UTF-16 LE with BOM'


@with_skin
def test_pixel_snapped_coordinates_and_sharp_grid(sk):
    sk.start(2027, 3, 3, 12)
    m = sk.mock
    # All string and shape meter positions/dimensions are integer-snapped (no fractional blur)
    for (meter, opt), val in m.options.items():
        if opt in ('X', 'Y', 'W', 'H'):
            assert re.match(r'^-?\d+$', str(val)), (meter, opt, val)
    # 1px grid lines sit on exact .5 coordinates so Direct2D renders crisp 1-pixel strokes
    for k in range(1, 20):
        key = 'Shape' if k == 1 else ('Shape%d' % k)
        s = m.opt('Grid', key) or ''
        if s.startswith('Line '):
            coords = s.split('|')[0].replace('Line ', '').strip().split(',')
            assert any(c.endswith('.5') for c in coords), (key, s)


def test_overrides_are_scoped_per_feed():
    ics1 = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        "BEGIN:VEVENT\r\nUID:shared@test\r\nDTSTART:20270301T090000Z\r\nDTEND:20270301T100000Z\r\n"
        "RRULE:FREQ=DAILY;COUNT=2\r\nSUMMARY:Feed1 Daily\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:shared@test\r\nRECURRENCE-ID:20270302T090000Z\r\n"
        "DTSTART:20270302T140000Z\r\nDTEND:20270302T150000Z\r\nSUMMARY:Feed1 Moved\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    ics2 = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        "BEGIN:VEVENT\r\nUID:shared@test\r\nDTSTART:20270301T090000Z\r\nDTEND:20270301T100000Z\r\n"
        "RRULE:FREQ=DAILY;COUNT=2\r\nSUMMARY:Feed2 Daily\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    lua = new_runtime(MockSkin({}, ini_sections()))
    wc = lua.globals()._WC
    wc.cfg.lang = wc.LANGS.en
    wc.cfg.showDeclined = True
    wc.parseICS(ics1, 1)
    wc.parseICS(ics2, 2)
    wc.buildOverrides()
    first = wc.daysFromCivil(2027, 3, 1)
    inst = wc.buildInstances(first, first + 7)
    f2 = [inst[i].s for i in range(1, len(inst) + 1) if inst[i].title == 'Feed2 Daily']
    assert f2 == [utc(2027, 3, 1, 9), utc(2027, 3, 2, 9)], f2


def test_event_conference_url_and_Empty_task():
    ics = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        "BEGIN:VEVENT\r\nUID:u1\r\nDTSTART:20270303T100000Z\r\nDTEND:20270303T120000Z\r\n"
        "SUMMARY:Call\r\nDESCRIPTION:Join at https://meet.google.com/abc-defg-hij now\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:u2\r\nDTSTART;VALUE=DATE:20270303\r\nSUMMARY:   \r\n"
        "X-WC-TASK:COMPLETED\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    sk = Skin()
    try:
        open(os.path.join(sk.dir, 'DownloadFile', 'calendar1.ics'), 'w', encoding='utf-8').write(ics)
        sk.start(2027, 3, 3, 12)
        m = sk.mock
        idx = [i for i in range(1, 81) if m.opt('EvT%d' % i, 'Text') == 'Call'][0]
        # Not a Google event id: the left click opens its day in Google Calendar, the middle click the link
        assert m.opt('EvBg%d' % idx, 'LeftMouseUpAction') == \
            '["https://calendar.google.com/calendar/r/day/2027/3/3?authuser=me%40example.com"]'
        assert m.opt('EvBg%d' % idx, 'MiddleMouseUpAction') == '["https://meet.google.com/abc-defg-hij"]'
        assert m.opt('EvBg%d' % idx, 'ToolTipText').endswith('#CRLF##CRLF#Middle-click: open the link')
        ad = sk.all_day()
        assert '✓ (no title)' in ad, ad
        sk.check_clean()
    finally:
        sk.close()


GOOGLE_ICS = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
    "BEGIN:VEVENT\r\nUID:abc123@google.com\r\nDTSTART:20270303T100000Z\r\nDTEND:20270303T110000Z\r\n"
    "SUMMARY:Lezione\r\n"
    "DESCRIPTION:<b>Aula</b> 3.0.3<br>Portare il <a href=\"https://example.com/x\">libro</a> &amp; appunti"
    "\\n\\n-::~:~::~:~:~:~:~:~::~:~::-\\nJoin with Google Meet: https://meet.google.com/abc-defg-hij"
    "\\nPlease do not edit this section.\\n-::~:~::~:~:~:~:~:~::~:~::-\r\n"
    "END:VEVENT\r\n"
    "BEGIN:VEVENT\r\nUID:rec@google.com\r\nDTSTART:20270301T090000Z\r\nDTEND:20270301T093000Z\r\n"
    "RRULE:FREQ=DAILY;COUNT=5\r\nSUMMARY:Daily\r\nEND:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


def google_skin(**overrides):
    sk = Skin(**overrides)
    open(os.path.join(sk.dir, 'DownloadFile', 'calendar1.ics'), 'w', encoding='utf-8').write(GOOGLE_ICS)
    sk.start(2027, 3, 3, 8)
    return sk


def event_meter(sk, title):
    return [i for i in range(1, 81) if sk.mock.shown('EvT%d' % i)
            and sk.mock.opt('EvT%d' % i, 'Text').startswith(title)][0]


def eid_link(event_id, cal='me@example.com'):
    import base64
    from urllib.parse import quote
    eid = base64.b64encode(('%s %s' % (event_id, cal)).encode()).decode().rstrip('=')
    return 'https://calendar.google.com/calendar/event?eid=%s&authuser=me%%40example.com' % quote(eid, safe='')


def test_event_description_tooltip_is_cleaned():
    sk = google_skin()
    try:
        tip = sk.mock.opt('EvBg%d' % event_meter(sk, 'Lezione'), 'ToolTipText')
        # HTML turned into lines, entities decoded, Google Meet block left out
        assert tip.startswith('Lezione#CRLF#'), tip
        assert '#CRLF##CRLF#Aula 3.0.3#CRLF#Portare il libro & appunti' in tip, tip
        assert 'Meet' not in tip and '::' not in tip and '<' not in tip, tip
        sk.check_clean()
    finally:
        sk.close()


def test_click_opens_event_in_google_calendar():
    sk = google_skin()
    try:
        m = sk.mock
        i = event_meter(sk, 'Lezione')
        assert m.opt('EvBg%d' % i, 'LeftMouseUpAction') == '["%s"]' % eid_link('abc123')
        assert m.opt('EvT%d' % i, 'LeftMouseUpAction') == '["%s"]' % eid_link('abc123')
        # The Meet link found in the description: middle click
        assert m.opt('EvBg%d' % i, 'MiddleMouseUpAction') == '["https://meet.google.com/abc-defg-hij"]'
        # Occurrence of a recurring event: "<id>_<original start in UTC>"
        i = event_meter(sk, 'Daily')
        assert m.opt('EvBg%d' % i, 'LeftMouseUpAction') == '["%s"]' % eid_link('rec_20270301T090000Z')
        assert m.opt('EvBg%d' % i, 'MiddleMouseUpAction') == ''
        sk.check_clean()
    finally:
        sk.close()
    sk = google_skin(ClickAction='link')
    try:
        m = sk.mock
        i = event_meter(sk, 'Lezione')
        assert m.opt('EvBg%d' % i, 'LeftMouseUpAction') == '["https://meet.google.com/abc-defg-hij"]'
        assert m.opt('EvBg%d' % i, 'MiddleMouseUpAction') == '["%s"]' % eid_link('abc123')
        assert 'Middle-click: open in Google Calendar' in m.opt('EvBg%d' % i, 'ToolTipText')
        # Without a link the left click still opens Google Calendar
        i = event_meter(sk, 'Daily')
        assert m.opt('EvBg%d' % i, 'LeftMouseUpAction') == '["%s"]' % eid_link('rec_20270301T090000Z')
    finally:
        sk.close()


def test_task_check_button():
    sk = Skin(feeds={3: 'tasks.ics'})
    try:
        sk.start(2027, 3, 3, 12)
        m = sk.mock
        ad = sk.all_day()
        i = [v for k, v in ad.items() if k.startswith('○ Simulazione')][0]
        # The chip opens the task's day in Google Calendar, the circle checks it
        assert m.opt('ADBg%d' % i, 'LeftMouseUpAction') == \
            '["https://calendar.google.com/calendar/r/day/2027/3/3?authuser=me%40example.com"]'
        assert m.shown('ADChk%d' % i) and m.opt('ADChk%d' % i, 'ToolTipText') == 'Mark complete'
        assert m.opt('ADChk%d' % i, 'LeftMouseUpAction') == '[!CommandMeasure MeasureScript "ToggleTask(%d)"]' % i
        assert 'Ellipse' in m.opt('ADChk%d' % i, 'MouseOverAction')
        # Tasks from an older script (no list id) have no button
        assert not m.shown('ADChk%d' % ad['○ Ripasso'])

        m.bangs.clear()
        sk.g.ToggleTask(i)
        assert ['!SetOption', 'MeasureTaskAction', 'Parameter',
                '-s -f -L -m 30 https://example.com/feed3.ics?action=complete&list=L1&task=t-open'] in m.bangs, m.bangs
        assert ['!CommandMeasure', 'MeasureTaskAction', 'Run'] in m.bangs
        # Shown as completed at once
        i = [v for k, v in sk.all_day().items() if k.startswith('✓ Simulazione')][0]
        assert m.opt('ADTx%d' % i, 'InlineSetting') == 'Strikethrough'
        assert m.opt('ADChk%d' % i, 'ToolTipText') == 'Mark uncompleted'

        # Google confirms: the tasks feed is downloaded again
        m.bangs.clear()
        m.measure_values['MeasureTaskAction'] = 'OK'
        sk.g.TaskResult()
        assert ['!CommandMeasure', 'MeasureICS3', 'Update'] in m.bangs, m.bangs
        feed = os.path.join(sk.dir, 'DownloadFile', 'calendar3.ics')
        text = open(feed, encoding='utf-8', newline='').read()
        open(feed, 'w', encoding='utf-8', newline='').write(text.replace('NEEDS-ACTION', 'COMPLETED', 1))
        sk.g.Reload(3)
        assert any(k.startswith('✓ Simulazione') for k in sk.all_day())

        # A change Google does not confirm (e.g. the old script answers with the feed) is undone
        i = [v for k, v in sk.all_day().items() if k.startswith('✓ Simulazione')][0]
        sk.g.ToggleTask(i)
        assert any(k.startswith('○ Simulazione') for k in sk.all_day())
        m.measure_values['MeasureTaskAction'] = 'BEGIN:VCALENDAR'
        sk.g.TaskResult()
        assert any(k.startswith('✓ Simulazione') for k in sk.all_day()), sk.all_day()
        assert 'task not saved' in m.opt('TbSync', 'Text'), m.opt('TbSync', 'Text')
        sk.check_clean()
    finally:
        sk.close()


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith('test_') and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print('ok    ' + name)
        except Exception:
            failed += 1
            print('FAIL  ' + name)
            traceback.print_exc()
    print('\n%d passed, %d failed' % (len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
