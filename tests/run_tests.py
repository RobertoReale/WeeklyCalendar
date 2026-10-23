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


# Harmless press action of every item: without one, Rainmeter drags the whole skin
NO_DRAG = '[!SetVariable WCPressed 1]'


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

    def tip(self, meter):
        """Tooltip shown while the cursor rests on meter ('' when it has none)."""
        self.g.TipOver(meter)
        text = self.mock.opt('Tip', 'ToolTipText') if self.mock.shown('Tip') else ''
        self.g.TipLeave(meter)
        return text

    def all_day(self):
        """Shown all-day chips as {text: meter index}."""
        return {self.mock.opt('ADTx%d' % i, 'Text'): i for i in range(1, 71) if self.mock.shown('ADTx%d' % i)}

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
    assert 'Early run' in sk.tip('HidUp1')
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
    texts = [m.opt('ADTx%d' % i, 'Text') for i in range(1, 71) if m.shown('ADTx%d' % i)]
    assert texts == ['All day 1', 'All day 2', '+3 more'], texts
    more = [i for i in range(1, 71) if m.opt('ADTx%d' % i, 'Text') == '+3 more'][0]
    assert sk.tip('ADTx%d' % more) == ('All day 3#CRLF#All day 4#CRLF#All day 5'
                                                    '#CRLF##CRLF#Click: show all#CRLF#Middle-click: open in Google Calendar')
    assert m.opt('ADTx%d' % more, 'LeftMouseUpAction') == '[!CommandMeasure MeasureScript "ExpandAllDay()"]'
    assert m.opt('ADTx%d' % more, 'MiddleMouseUpAction').startswith('["https://calendar.google.com/calendar/r/day/2027/3/4')


def ad_texts(sk):
    return [sk.mock.opt('ADTx%d' % i, 'Text') for i in range(1, 71) if sk.mock.shown('ADTx%d' % i)]


def test_all_day_rows_setting():
    sk = Skin(AllDayRows=2)
    ref = Skin()
    try:
        sk.start(2027, 3, 3, 12)
        ref.start(2027, 3, 3, 12)
        assert ad_texts(sk) == ['All day 1', '+4 more'], ad_texts(sk)
        assert int(sk.mock.opt('HL1', 'Y')) < int(ref.mock.opt('HL1', 'Y'))
        sk.check_clean()
    finally:
        sk.close()
        ref.close()


@with_skin
def test_all_day_row_expands_and_collapses(sk):
    sk.start(2027, 3, 3, 12)
    m = sk.mock
    y0 = int(m.opt('HL1', 'Y'))
    assert not m.shown('AdCollapse')
    sk.g.ExpandAllDay()
    assert ad_texts(sk) == ['All day %d' % k for k in range(1, 6)], ad_texts(sk)
    assert m.shown('AdCollapse') and m.shown('AdCollapseTxt')
    assert sk.tip('AdCollapse') == 'Show fewer'
    assert int(m.opt('HL1', 'Y')) == y0 + 2 * 22
    sk.g.CollapseAllDay()
    assert ad_texts(sk) == ['All day 1', 'All day 2', '+3 more']
    assert not m.shown('AdCollapse') and sk.tip('AdCollapse') == ''
    assert int(m.opt('HL1', 'Y')) == y0
    # Still expanded in a week without all-day items: no band, no button
    sk.g.ExpandAllDay()
    sk.g.ShiftWeek(1)
    assert ad_texts(sk) == [] and not m.shown('AdCollapse')
    assert int(m.opt('HL1', 'Y')) == 56 + 68  # gridTop right under the day headers
    sk.g.ShiftWeek(-1)
    assert len(ad_texts(sk)) == 5


def test_expanded_all_day_row_is_capped():
    sk = Skin(Height=400)
    try:
        sk.start(2027, 3, 3, 12)
        sk.g.ExpandAllDay()  # (400 - 152) * 0.4 / 22 = 4 rows
        assert ad_texts(sk) == ['All day 1', 'All day 2', 'All day 3', '+2 more'], ad_texts(sk)
        more = [i for i in range(1, 71) if sk.mock.opt('ADTx%d' % i, 'Text') == '+2 more'][0]
        # Expanding again would not show more: the click opens the day instead
        assert sk.mock.opt('ADTx%d' % more, 'LeftMouseUpAction').startswith('["https://calendar.google.com/')
        sk.check_clean()
    finally:
        sk.close()


@with_skin
def test_layout_declined_is_outlined(sk):
    sk.start(2027, 3, 3, 12)
    m = sk.mock
    idx = [i for i in range(1, 81) if m.opt('EvT%d' % i, 'Text') == 'Declined meeting'][0]
    shape = m.opt('EvBg%d' % idx, 'Shape')
    assert 'Fill Color 255,255,255,255' in shape and 'Stroke Color 3,155,229,255' in shape, shape
    assert 'Declined' in sk.tip('EvBg%d' % idx)
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


def day_nums(sk):
    return [sk.mock.opt('DayNum%d' % i, 'Text') for i in range(7) if sk.mock.shown('DayNum%d' % i)]


def test_day_view():
    sk = Skin(View='day')
    try:
        sk.start(2027, 3, 3, 12)  # Wednesday
        m = sk.mock
        assert day_nums(sk) == ['3'], day_nums(sk)
        assert m.opt('DayName0', 'Text') == 'WED'
        assert m.opt('TbTitle', 'Text') == 'March 3, 2027', m.opt('TbTitle', 'Text')
        assert m.opt('TodayCircle', 'Shape').startswith('Ellipse 98,'), m.opt('TodayCircle', 'Shape')
        widths = [int(m.opt('EvBg%d' % i, 'W')) for i in range(1, 81) if m.shown('EvBg%d' % i)]
        assert widths and min(widths) > 1000, widths
        assert sk.tip('BtnPrev') == 'Previous day'
        assert m.opt('ViewSeg1', 'FontColor') == '4,30,73,255'   # selected segment
        assert m.opt('ViewSeg3', 'FontColor') == '31,31,31,255'
        assert m.shown('HidDn0') and not m.shown('HidDn1')        # "Late dinner", only today's column
        sk.g.ShiftWeek(1)                                         # the wheel moves one day
        assert day_nums(sk) == ['4'] and len(sk.all_day()) == 3
        sk.check_clean()
    finally:
        sk.close()


@with_skin
def test_three_day_view_and_switching(sk):
    sk.start(2027, 3, 3, 12)
    m = sk.mock
    assert day_nums(sk) == [str(d) for d in range(1, 8)]
    sk.g.SetView('3day')
    assert day_nums(sk) == ['3', '4', '5'], day_nums(sk)
    assert ['!WriteKeyValue', 'Variables', 'View', '3day',
            os.path.join(sk.dir, '@Resources') + os.sep + 'Private.inc'] in m.bangs
    assert m.opt('TbTitle', 'Text') == 'March 2027'
    assert sk.all_day() and m.shown('HidDn0')  # all-day row and hidden-hour badges work here too
    sk.g.ShiftView(1)
    assert day_nums(sk) == ['6', '7', '8'], day_nums(sk)
    assert m.opt('TbTitle', 'Text') == 'March 2027' and not m.shown('TodayCircle')
    # Another range shown: switching keeps its first day
    sk.g.SetView('day')
    assert day_nums(sk) == ['6']
    sk.g.GoToday()
    assert day_nums(sk) == ['3']
    sk.g.SetView('week')
    assert day_nums(sk) == [str(d) for d in range(1, 8)]
    for n in [-1] * 5 + [1] * 10:
        sk.g.ShiftView(n)
    sk.g.SetView('bogus')
    assert day_nums(sk) == [str(d) for d in range(5, 12)], day_nums(sk)  # 5 weeks on: 5-11 April


def test_view_switcher_short_labels_and_description_line():
    sk = Skin(Width=700)
    try:
        sk.start(2027, 3, 3, 12)
        assert [sk.mock.opt('ViewSeg%d' % k, 'Text') for k in (1, 2, 3)] == ['D', '3D', 'W']
        assert sk.tip('ViewHit1') == 'View: Day'
        sk.check_clean()
    finally:
        sk.close()
    ics = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
           "BEGIN:VEVENT\r\nUID:long\r\nDTSTART:20270303T090000\r\nDTEND:20270303T120000\r\n"
           "SUMMARY:Workshop\r\nDESCRIPTION:\\n  Bring the slides\\nand a laptop\r\nEND:VEVENT\r\n"
           "END:VCALENDAR\r\n")
    for view, expected in (('day', True), ('week', False)):
        sk = Skin(View=view)
        try:
            open(os.path.join(sk.dir, 'DownloadFile', 'calendar1.ics'), 'w', encoding='utf-8').write(ics)
            sk.start(2027, 3, 3, 8)
            i = event_meter(sk, 'Workshop')
            detail = sk.mock.opt('EvD%d' % i, 'Text')
            assert ('Bring the slides' in detail) == expected, (view, detail)
        finally:
            sk.close()


def test_italian_translation_and_context_menu():
    sk = Skin(Language='it')
    try:
        sk.start(2027, 3, 3, 12)
        m = sk.mock
        assert m.opt('Rainmeter', 'ContextTitle') == 'Aggiorna ora'
        assert m.opt('Rainmeter', 'ContextTitle7') == 'Indirizzi calendario'
        assert m.opt('CalAppTitle', 'Text') == 'Calendario'
        assert sk.tip('BtnPrev') == 'Settimana precedente'
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
        assert 'Attività' in sk.tip('ADBg%d' % i)
        # Completed task: check mark, title struck through, faded, escaped comma restored
        i = ad['✓ Esercizi, parte 2']
        assert m.opt('ADTx%d' % i, 'InlineSetting') == 'Strikethrough'
        assert m.opt('ADTx%d' % i, 'InlinePattern') == r'^\S+ (.*)$'
        assert 'Fill Color ' + purple not in m.opt('ADBg%d' % i, 'Shape')
        assert 'Attività completata' in sk.tip('ADBg%d' % i)
        # Open task on a past day: faded, not struck through
        i = ad['○ Ripasso']
        # Task notes after a blank line, one tooltip line per line of the notes
        assert sk.tip('ADBg%d' % i).endswith('#CRLF##CRLF#capitoli 1-3#CRLF#esercizi 4, 5 ( x)')
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
        assert 'calendar 3' in sk.tip('TbSync')
        assert sk.event_titles(), 'the working feed must still be shown'
    finally:
        sk.close()


def test_sixth_calendar_keeps_its_color_and_tasks():
    sk = Skin(feeds={6: 'tasks.ics'})
    try:
        sk.start(2027, 3, 3, 12)
        m = sk.mock
        i = [v for k, v in sk.all_day().items() if k.startswith('○ Simulazione')][0]
        assert 'Fill Color 97,97,97,255' in m.opt('ADBg%d' % i, 'Shape'), m.opt('ADBg%d' % i, 'Shape')
        sk.g.ToggleTask(i)
        m.bangs.clear()
        m.measure_values['MeasureTaskAction'] = 'OK'
        sk.g.TaskResult()
        assert ['!CommandMeasure', 'MeasureICS6', 'Update'] in m.bangs, m.bangs
        sk.check_clean()
    finally:
        sk.close()


@with_skin
def test_empty_slots_are_disabled(sk):
    sk.start(2027, 3, 3, 12)
    for i in (2, 3, 4, 5, 6):
        assert ['!DisableMeasure', 'MeasureICS%d' % i] in sk.mock.bangs, i
    assert ['!EnableMeasure', 'MeasureICS1'] in sk.mock.bangs
    text = open(os.path.join(sk.dir, '@Resources', 'Private.inc'), encoding='utf-8').read()
    assert 'IcalUrl6=' in text


def test_unreadable_fifth_feed_is_reported():
    sk = Skin(feeds={5: 'not_ical.html'})
    try:
        sk.start(2027, 3, 3, 12)
        sk.g.Reload(5)
        assert 'feed error' in sk.mock.opt('TbSync', 'Text')
        assert 'calendar 5' in sk.tip('TbSync')
        sk.check_clean()
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


def test_pressing_an_item_does_not_move_the_skin():
    # Rainmeter drags the whole skin when the button is pressed where no meter has a
    # LeftMouseDownAction: every clickable meter gets one (StyItem), except the drop layer,
    # which is shown only while a task is dragged
    text = open(INI_FILE, encoding='utf-8-sig').read()
    style = re.search(r'(?ms)^\[StyItem\]\n(.*?)\n\n', text).group(1)
    assert 'LeftMouseDownAction=' in style
    bad = []
    for sec in re.split(r'(?m)^(?=\[)', text):
        m = re.match(r'\[([^\]]+)\]', sec)
        if m and re.search(r'(?m)^LeftMouseUpAction=', sec) and not m.group(1).startswith('Drag') \
                and not re.search(r'(?m)^LeftMouseDownAction=', sec) and 'StyItem' not in sec:
            bad.append(m.group(1))
    assert bad == [], bad


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
        assert sk.tip('EvBg%d' % idx).endswith('#CRLF##CRLF#Middle-click: open the link')
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
        tip = sk.tip('EvBg%d' % event_meter(sk, 'Lezione'))
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
        assert 'Middle-click: open in Google Calendar' in sk.tip('EvBg%d' % i)
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
        # The chip is pressed to drag it (a click opens the task's day through DragDrop),
        # the circle checks it
        assert m.opt('ADBg%d' % i, 'LeftMouseDownAction') == '[!CommandMeasure MeasureScript "DragStart(%d)"]' % i
        assert m.opt('ADChk%d' % i, 'LeftMouseDownAction') == NO_DRAG
        assert m.shown('ADChk%d' % i) and sk.tip('ADChk%d' % i) == 'Mark complete'
        assert m.opt('ADChk%d' % i, 'LeftMouseUpAction') == '[!CommandMeasure MeasureScript "ToggleTask(%d)"]' % i
        assert 'Ellipse' in m.opt('ADChk%d' % i, 'MouseOverAction')
        # Tasks from an older script (no list id): the button says to update the script
        old = ad['○ Ripasso']
        assert 'GoogleTasksFeed.gs' in sk.tip('ADChk%d' % old)
        m.bangs.clear()
        sk.g.ToggleTask(old)
        assert ['!CommandMeasure', 'MeasureTaskAction', 'Run'] not in m.bangs
        assert 'update the Tasks script' in m.opt('TbSync', 'Text'), m.opt('TbSync', 'Text')

        m.bangs.clear()
        sk.g.ToggleTask(i)
        assert ['!SetOption', 'MeasureTaskAction', 'Parameter',
                '-s -f -L -m 30 https://example.com/feed3.ics?action=complete&list=L1&task=t-open'] in m.bangs, m.bangs
        assert ['!CommandMeasure', 'MeasureTaskAction', 'Run'] in m.bangs
        # Shown as completed at once
        i = [v for k, v in sk.all_day().items() if k.startswith('✓ Simulazione')][0]
        assert m.opt('ADTx%d' % i, 'InlineSetting') == 'Strikethrough'
        assert sk.tip('ADChk%d' % i) == 'Mark uncompleted'

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

        # A change Google does not confirm is undone; an old script answers with the feed
        i = [v for k, v in sk.all_day().items() if k.startswith('✓ Simulazione')][0]
        sk.g.ToggleTask(i)
        assert any(k.startswith('○ Simulazione') for k in sk.all_day())
        m.measure_values['MeasureTaskAction'] = 'BEGIN:VCALENDAR'
        sk.g.TaskResult()
        assert any(k.startswith('✓ Simulazione') for k in sk.all_day()), sk.all_day()
        assert 'update the Tasks script' in m.opt('TbSync', 'Text'), m.opt('TbSync', 'Text')
        sk.g.ToggleTask(i)
        m.measure_values['MeasureTaskAction'] = ''  # no answer (curl failed)
        sk.g.TaskResult()
        assert 'task not saved' in m.opt('TbSync', 'Text'), m.opt('TbSync', 'Text')

        # Script authorized for reading only: say how to allow editing, with Google's reason
        sk.g.ToggleTask(i)
        m.measure_values['MeasureTaskAction'] = (
            "ERROR Non disponi dell'autorizzazione necessaria per chiamare tasks.tasks.patch. "
            "Autorizzazioni obbligatorie: https://www.googleapis.com/auth/tasks.\n")
        sk.g.TaskResult()
        assert any(k.startswith('✓ Simulazione') for k in sk.all_day()), sk.all_day()
        assert m.opt('TbSync', 'Text').endswith('allow editing tasks'), m.opt('TbSync', 'Text')
        tip = sk.tip('TbSync')
        assert 'run the function authorize' in tip and 'Google: Non disponi' in tip, tip
        # A confirmed change clears the notice
        sk.g.ToggleTask(i)
        m.measure_values['MeasureTaskAction'] = 'OK'
        sk.g.TaskResult()
        assert 'allow editing' not in m.opt('TbSync', 'Text'), m.opt('TbSync', 'Text')
        sk.check_clean()
    finally:
        sk.close()


# ---------------------------------------------------------------------------
# Dragging a task to another day
# ---------------------------------------------------------------------------
DAY_W = (1400 - 64 - 14) / 7          # Width in Settings.inc, time gutter and right margin
DAY_LINK = '["https://calendar.google.com/calendar/r/day/2027/3/3?authuser=me%40example.com"]'
DRAG_METERS = ['DragArea', 'DragHi', 'DragPrev', 'DragPrevTx'] + ['DragZone%d' % i for i in range(7)]


def task_chip(sk, prefix='○ Simulazione'):
    return [v for k, v in sk.all_day().items() if k.startswith(prefix)][0]


def chip_col(sk, i):
    return int((int(sk.mock.opt('ADBg%d' % i, 'X')) - 64) // DAY_W)


def task_params(sk):
    return [b[3] for b in sk.mock.bangs if b[:3] == ['!SetOption', 'MeasureTaskAction', 'Parameter']]


def drag_skin(**kw):
    sk = Skin(feeds={3: 'tasks.ics'}, **kw)
    sk.start(2027, 3, 3, 12)  # Wednesday: the open task is in column 2
    return sk


def test_drag_chip_actions():
    sk = drag_skin()
    try:
        m = sk.mock
        i = task_chip(sk)
        for meter in ('ADBg%d' % i, 'ADTx%d' % i):
            assert m.opt(meter, 'LeftMouseDownAction') == '[!CommandMeasure MeasureScript "DragStart(%d)"]' % i
            assert m.opt(meter, 'LeftMouseUpAction') == '' and m.opt(meter, 'MouseActionCursorName') == 'SizeAll'
        assert sk.tip('ADBg%d' % i).endswith('#CRLF##CRLF#Drag to another day to move it')
        # Not draggable: tasks of an older script (no ids) and events
        for title in ('○ Ripasso', 'All day 1'):
            j = sk.all_day()[title]
            assert m.opt('ADBg%d' % j, 'LeftMouseDownAction') == NO_DRAG, title
            assert m.opt('ADBg%d' % j, 'LeftMouseUpAction') != '' and m.opt('ADBg%d' % j, 'MouseActionCursorName') == 'Hand'
        assert not any(m.shown(d) for d in DRAG_METERS)
        # The drop layer is placed by the layout: one zone per column, from the header to the grid bottom
        assert [m.opt('DragZone%d' % c, 'X') for c in range(7)] == [str(int(64 + c * DAY_W + 0.5)) for c in range(7)]
        assert m.opt('DragZone0', 'Y') == '56' and m.opt('DragZone0', 'H') == str(int(m.vars['Height']) - 28 - 56)
        sk.check_clean()
    finally:
        sk.close()
    # The day view has nowhere to drag to
    sk = drag_skin(View='day')
    try:
        assert sk.mock.opt('ADBg%d' % task_chip(sk), 'LeftMouseDownAction') == NO_DRAG
        assert sk.mock.opt('ADBg%d' % task_chip(sk), 'LeftMouseUpAction') == DAY_LINK
    finally:
        sk.close()


def test_drag_click_opens_the_day():
    sk = drag_skin()
    try:
        m = sk.mock
        i = task_chip(sk)
        sk.g.DragStart(i)
        assert m.shown('DragArea') and all(m.shown('DragZone%d' % c) for c in range(7))
        m.bangs.clear()
        sk.g.DragOver(2)          # the zones appear under the cursor: its own column
        sk.g.DragDrop(2)
        assert [DAY_LINK] in m.bangs, m.bangs
        assert not task_params(sk) and not any(m.shown(d) for d in DRAG_METERS)
        sk.check_clean()
    finally:
        sk.close()


def test_drag_moves_the_task():
    sk = drag_skin()
    try:
        m = sk.mock
        i = task_chip(sk)
        assert chip_col(sk, i) == 2
        friday = [j for j in sk.all_day().values() if chip_col(sk, j) == 4]
        purple = '142,36,170'
        sk.g.DragStart(i)
        sk.g.DragOver(2)
        sk.g.DragOver(4)
        # Friday's column is highlighted and the task previewed in its first free row
        assert m.shown('DragHi') and m.opt('DragHi', 'X') == str(int(64 + 4 * DAY_W + 0.5) + 2)
        assert 'Fill Color %s,28' % purple in m.opt('DragHi', 'Shape')
        assert m.shown('DragPrev') and m.opt('DragPrev', 'Y') == str(56 + 68 + 3 + len(friday) * 22)
        assert m.opt('DragPrevTx', 'Text').startswith('○ Simulazione')
        assert m.opt('TbSync', 'Text') == 'Move to Fri 5'
        assert purple not in m.opt('ADBg%d' % i, 'Shape')   # the source chip fades
        m.bangs.clear()
        sk.g.DragDrop(4)
        assert task_params(sk) == ['-s -f -L -m 30 https://example.com/feed3.ics'
                                   '?action=move&list=L1&task=t-open&due=2027-03-05'], task_params(sk)
        assert ['!CommandMeasure', 'MeasureTaskAction', 'Run'] in m.bangs
        # Shown on Friday at once, in its own color again
        i = task_chip(sk)
        assert chip_col(sk, i) == 4 and purple in m.opt('ADBg%d' % i, 'Shape')
        assert not any(m.shown(d) for d in DRAG_METERS)
        assert 'Move to' not in m.opt('TbSync', 'Text')
        # Google confirms: the feed is downloaded again, and it has the new date
        m.bangs.clear()
        m.measure_values['MeasureTaskAction'] = 'OK'
        sk.g.TaskResult()
        assert ['!CommandMeasure', 'MeasureICS3', 'Update'] in m.bangs
        feed = os.path.join(sk.dir, 'DownloadFile', 'calendar3.ics')
        text = open(feed, encoding='utf-8', newline='').read()
        open(feed, 'w', encoding='utf-8', newline='').write(text.replace('20270303', '20270305', 1))
        sk.g.Reload(3)
        assert chip_col(sk, task_chip(sk)) == 4

        # Script authorized for reading only: the task goes back
        sk.g.DragStart(task_chip(sk))
        sk.g.DragOver(1)
        sk.g.DragDrop(1)
        assert chip_col(sk, task_chip(sk)) == 1
        m.measure_values['MeasureTaskAction'] = 'ERROR Missing scope https://www.googleapis.com/auth/tasks'
        sk.g.TaskResult()
        assert chip_col(sk, task_chip(sk)) == 4
        assert m.opt('TbSync', 'Text').endswith('allow editing tasks'), m.opt('TbSync', 'Text')
        sk.check_clean()
    finally:
        sk.close()


def test_drag_then_complete_before_the_answer():
    sk = drag_skin()
    try:
        m = sk.mock
        sk.g.DragStart(task_chip(sk))
        sk.g.DragOver(4)
        sk.g.DragDrop(4)
        sk.g.ToggleTask(task_chip(sk))               # sent after the move
        i = task_chip(sk, '✓ Simulazione')
        assert chip_col(sk, i) == 4
        m.bangs.clear()
        m.measure_values['MeasureTaskAction'] = 'ERROR Backend Error'
        sk.g.TaskResult()                            # the move failed: the completion stays
        i = task_chip(sk, '✓ Simulazione')
        assert chip_col(sk, i) == 2, chip_col(sk, i)
        assert task_params(sk)[-1].endswith('action=complete&list=L1&task=t-open'), task_params(sk)
        m.measure_values['MeasureTaskAction'] = 'OK'
        sk.g.TaskResult()
        assert chip_col(sk, task_chip(sk, '✓ Simulazione')) == 2
        sk.check_clean()
    finally:
        sk.close()


def test_drag_cancel():
    sk = drag_skin()
    try:
        m = sk.mock
        i = task_chip(sk)
        shape, sync = m.opt('ADBg%d' % i, 'Shape'), m.opt('TbSync', 'Text')
        for cancel in ('right click', 'back home', 'timeout'):
            sk.g.DragStart(i)
            sk.g.DragOver(4)
            if cancel == 'right click':
                sk.g.DragCancel(1)                   # the left button is still down
                assert m.shown('DragArea') and not m.shown('DragZone2') and not m.shown('DragHi')
                sk.g.DragCancel()                    # its release, over DragArea
            elif cancel == 'back home':
                sk.g.DragOver(2)
                assert not m.shown('DragHi') and m.opt('TbSync', 'Text') == sync
                sk.g.DragDrop(2)
            else:
                sk.g.ScrollHours(1)                  # no layout while dragging
                assert m.shown('DragHi') and m.opt('ADBg%d' % i, 'Shape') != shape
                sk.at(2027, 3, 3, 12, 0, 25)
                sk.g.Update()
                sk.at(2027, 3, 3, 12)
            assert not any(m.shown(d) for d in DRAG_METERS), cancel
            assert m.opt('ADBg%d' % i, 'Shape') == shape and m.opt('TbSync', 'Text') == sync, cancel
            assert not task_params(sk) and task_chip(sk) == i, cancel
        sk.g.DragCancel()                            # the cursor leaves the skin: nothing to do
        sk.g.DragOver(3)
        sk.g.DragDrop(3)
        assert not task_params(sk) and not m.shown('DragHi')
        sk.check_clean()
    finally:
        sk.close()


def test_google_tasks_script_move():
    node = shutil.which('node')
    if not node:
        print('      (skipped: node not installed)')
        return
    import json
    import subprocess
    script = open(os.path.join(ROOT, 'tools', 'GoogleTasksFeed.gs'), encoding='utf-8').read()
    harness = script + r"""
var patches = [];
var ContentService = { MimeType: { ICAL: 'ical' }, createTextOutput: function (s) {
  return { text: s, setMimeType: function () { return this; } }; } };
var Tasks = { Tasks: { patch: function (res, list, task) {
  if (task === 'missing') throw new Error('Not Found');
  patches.push([res, list, task]); } } };
function move(p) { p.action = 'move'; return doGet({ parameter: p }).text; }
process.stdout.write(JSON.stringify({
  ok: move({ list: 'L1', task: 'a', due: '2027-03-05' }),
  badDate: move({ list: 'L1', task: 'a', due: '5/3/2027' }),
  noDate: move({ list: 'L1', task: 'a' }),
  noTask: move({ list: 'L1', due: '2027-03-05' }),
  missing: move({ list: 'L1', task: 'missing', due: '2027-03-05' }),
  patches: patches }));
"""
    res = subprocess.run([node, '-e', harness], capture_output=True, encoding='utf-8')
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert out['ok'] == 'OK', out
    assert out['badDate'] == 'ERROR bad date' and out['noDate'] == 'ERROR bad date', out
    assert out['noTask'].startswith('ERROR') and out['missing'] == 'ERROR Not Found', out
    assert out['patches'] == [[{'due': '2027-03-05T00:00:00.000Z'}, 'L1', 'a']], out['patches']


# ---------------------------------------------------------------------------
# Month view
# ---------------------------------------------------------------------------
def epoch_day(y, mo, d):
    return (date(y, mo, d) - date(1970, 1, 1)).days


def month_lines(sk):
    """Shown month lines as [(cell number, text, meter)]."""
    m, out = sk.mock, []
    boxes = [(c, int(m.opt('MHit%d' % c, 'X')), int(m.opt('MHit%d' % c, 'Y')),
              int(m.opt('MHit%d' % c, 'W')), int(m.opt('MHit%d' % c, 'H')))
             for c in range(1, 43) if m.shown('MHit%d' % c)]
    for i in range(1, 211):
        if m.shown('MLn%d' % i):
            x, y = int(m.opt('MLn%d' % i, 'X')), int(m.opt('MLn%d' % i, 'Y'))
            cell = [c for c, bx, by, bw, bh in boxes if bx <= x < bx + bw and by <= y < by + bh]
            out.append((cell[0], m.opt('MLn%d' % i, 'Text'), 'MLn%d' % i))
    return out


def cells_shown(sk):
    return [c for c in range(1, 43) if sk.mock.shown('MHit%d' % c)]


def test_month_view_grid():
    sk = Skin(View='month', feeds={3: 'tasks.ics'})
    try:
        sk.start(2027, 3, 3, 12)  # March 2027 starts on a Monday: 5 weeks
        m = sk.mock
        assert cells_shown(sk) == list(range(1, 36)), cells_shown(sk)
        assert m.opt('TbTitle', 'Text') == 'March 2027' and not m.shown('TbWeek')
        assert m.opt('ViewSeg4', 'Text') == 'Month' and m.opt('ViewSeg4', 'FontColor') == '4,30,73,255'
        assert sk.tip('BtnNext') == 'Next month'
        assert [m.opt('DayName%d' % c, 'Text') for c in range(7)] == ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
        # Today: white number on the blue circle; the next month's days are muted
        assert m.opt('MNum3', 'Text') == '3' and m.opt('MNum3', 'FontColor') == '255,255,255,255'
        assert m.opt('TodayCircle', 'Shape').startswith('Ellipse %s,%s,12' % (m.opt('MNum3', 'X'), m.opt('MNum3', 'Y')))
        assert m.shown('TodayCircle')
        assert m.opt('MNum1', 'Text') == '1 Mar' and m.opt('MNum2', 'FontColor') == '31,31,31,255'
        assert m.opt('MNum32', 'Text') == '1 Apr' and m.opt('MNum32', 'FontColor') == '116,119,117,255'
        # A day opens in the day view; the middle click opens it in Google Calendar
        mar4 = epoch_day(2027, 3, 4)
        assert m.opt('MHit4', 'LeftMouseUpAction') == '[!CommandMeasure MeasureScript "SetView(\'day\', %d)"]' % mar4
        assert m.opt('MNum4', 'MiddleMouseUpAction').startswith('["https://calendar.google.com/calendar/r/day/2027/3/4')
        assert sk.tip('MHit4').startswith('March 4, 2027#CRLF#Click: open this day')
        # Only the month's meters: the week view's are hidden, the now line too
        for meter in ('EvBg1', 'ADBg1', 'HL1', 'TzLabel', 'DayNum0', 'BtnUpHour', 'NowLine', 'HidDn2'):
            assert not m.shown(meter), meter
        # Tasks: same chip as in the week view, struck through when completed
        lines = month_lines(sk)
        done = [l for l in lines if l[1].startswith('✓ Esercizi')][0]
        assert done[0] == 2 and m.opt(done[2], 'InlineSetting') == 'Strikethrough'
        task = [l for l in lines if l[1].startswith('○ Simulazione')][0]
        assert task[0] == 3 and m.opt(task[2], 'InlineSetting') == ''
        # The wheel and the arrows change the month: February 2027 has 4 weeks, August 6
        sk.g.ScrollHours(-1)
        assert m.opt('TbTitle', 'Text') == 'February 2027' and cells_shown(sk) == list(range(1, 29))
        assert not m.shown('MLn%d' % (len(month_lines(sk)) + 1))
        for _ in range(6):
            sk.g.ShiftView(1)
        assert m.opt('TbTitle', 'Text') == 'August 2027' and cells_shown(sk) == list(range(1, 43))
        assert m.opt('MNum1', 'Text') == '26' and m.opt('MNum7', 'Text') == '1 Aug'
        assert not m.shown('TodayCircle')
        sk.g.GoToday()
        assert m.opt('TbTitle', 'Text') == 'March 2027'
        # December -> January of the next year
        for _ in range(10):
            sk.g.ShiftView(1)
        assert m.opt('TbTitle', 'Text') == 'January 2028', m.opt('TbTitle', 'Text')
        sk.check_clean()
    finally:
        sk.close()


def test_month_view_more_and_items():
    sk = Skin(View='month', Height=500)  # small cells: two lines each
    try:
        sk.start(2027, 3, 3, 12)
        m = sk.mock
        thu = [l for l in month_lines(sk) if l[0] == 4]
        assert len(thu) == 2 and thu[0][1] == 'All day 1' and thu[1][1].startswith('+'), thu
        more = thu[1][2]
        mar4 = epoch_day(2027, 3, 4)
        assert m.opt(more, 'LeftMouseUpAction') == '[!CommandMeasure MeasureScript "SetView(\'day\', %d)"]' % mar4
        tip = sk.tip(more)
        assert tip.startswith('All day 2#CRLF#All day 3'), tip
        assert tip.endswith('Click: open this day#CRLF#Middle-click: open in Google Calendar'), tip
        assert m.opt(more, 'FontColor') == '116,119,117,255'
        # From the month to that day
        sk.g.SetView('day', mar4)
        assert day_nums(sk) == ['4'] and not m.shown('MHit1') and not m.shown('MLn1')
        sk.check_clean()
    finally:
        sk.close()


def test_month_view_lines_match_the_week_view():
    sk = google_skin()
    try:
        m = sk.mock
        i = event_meter(sk, 'Lezione')
        week_tip, week_act = sk.tip('EvBg%d' % i), m.opt('EvBg%d' % i, 'LeftMouseUpAction')
        sk.g.SetView('month')
        assert ['!WriteKeyValue', 'Variables', 'View', 'month',
                os.path.join(sk.dir, '@Resources') + os.sep + 'Private.inc'] in m.bangs
        line = [l for l in month_lines(sk) if l[1].endswith('Lezione')][0]
        assert line[0] == 3 and re.match(r'^\d\d:\d\d Lezione$', line[1]), line
        assert sk.tip(line[2]) == week_tip
        assert m.opt(line[2], 'LeftMouseUpAction') == week_act
        assert m.opt(line[2], 'Padding') == '14,0,4,0'   # after the dot
        # The daily event: one line per day, with its feed's color in the dot (faded once over)
        daily = [l for l in month_lines(sk) if l[1].endswith('Daily')]
        assert [l[0] for l in daily] == [1, 2, 3, 4, 5], daily
        shp = m.opt('MShp4', 'Shape')
        assert shp.startswith('Ellipse 10,') and '3,155,229,255' in shp, shp
        assert '3,155,229,255' not in m.opt('MShp1', 'Shape')
        # Back to the week: the month's meters are hidden again
        sk.g.SetView('week')
        assert not any(m.shown('MLn%d' % k) for k in range(1, 211)) and not m.shown('MHit1')
        assert m.shown('TzLabel') and event_meter(sk, 'Lezione')
        sk.check_clean()
    finally:
        sk.close()


def test_month_view_drag_a_task():
    sk = Skin(View='month', feeds={3: 'tasks.ics'})
    try:
        sk.start(2027, 3, 3, 12)
        m, g = sk.mock, sk.g
        purple = '142,36,170'

        def task_line():
            return [l for l in month_lines(sk) if l[1].startswith('○ Simulazione')][0]

        def shapes(meter):
            return {k: v for (mt, k), v in m.options.items() if mt == meter and k.startswith('Shape')}

        cell, _, ln = task_line()
        k = int(ln[3:])
        assert cell == 3
        assert m.opt(ln, 'LeftMouseDownAction') == '[!CommandMeasure MeasureScript "DragStart(%d)"]' % k
        assert m.opt(ln, 'LeftMouseUpAction') == '' and m.opt(ln, 'MouseActionCursorName') == 'SizeAll'
        assert sk.tip(ln).endswith('#CRLF##CRLF#Drag to another day to move it'), sk.tip(ln)
        # Not draggable: a task of an older script (no ids), an event, "+N more"
        other = [l for l in month_lines(sk) if l[1].startswith('○ Ripasso')][0][2]
        assert m.opt(other, 'LeftMouseDownAction') == NO_DRAG and m.opt(other, 'LeftMouseUpAction') != ''
        assert m.opt(other, 'MouseActionCursorName') == 'Hand'
        # One drop zone per cell
        for c in (0, 4, 34):
            assert [m.opt('DragZone%d' % c, o) for o in 'XYWH'] == [m.opt('MHit%d' % (c + 1), o) for o in 'XYWH']

        # A click: the zones appear, the release on its own cell opens the day
        g.DragStart(k)
        assert all(m.shown('DragZone%d' % c) for c in range(35)) and not m.shown('DragZone35')
        m.bangs.clear()
        g.DragOver(2)
        g.DragDrop(2)
        assert [DAY_LINK] in m.bangs and not task_params(sk)
        assert not any(m.shown('DragZone%d' % c) for c in range(42)) and not m.shown('DragArea')

        # To Friday 5: the cell is highlighted, the task previewed after its all-day items
        before = shapes('MShp3')
        fri_allday = [l for l in month_lines(sk) if l[0] == 5 and not re.match(r'^\d\d:\d\d ', l[1])]
        g.DragStart(k)
        g.DragOver(2)
        g.DragOver(4)
        x5, y5 = int(m.opt('MHit5', 'X')), int(m.opt('MHit5', 'Y'))
        assert m.shown('DragHi') and m.opt('DragHi', 'X') == str(x5 + 2) and m.opt('DragHi', 'Y') == str(y5 + 2)
        assert 'Fill Color %s,28' % purple in m.opt('DragHi', 'Shape')
        assert m.opt('DragPrev', 'Y') == str(y5 + 26 + len(fri_allday) * 18) and m.opt('DragPrev', 'H') == '16'
        assert m.opt('DragPrevTx', 'Text').startswith('○ Simulazione')
        assert m.opt('TbSync', 'Text') == 'Move to Fri 5'
        changed = [o for o, v in shapes('MShp3').items() if v != before[o]]
        assert len(changed) == 1 and purple not in shapes('MShp3')[changed[0]], changed   # faded
        g.DragDrop(4)
        assert task_params(sk) == ['-s -f -L -m 30 https://example.com/feed3.ics'
                                   '?action=move&list=L1&task=t-open&due=2027-03-05'], task_params(sk)
        assert task_line()[0] == 5 and not m.shown('DragHi')
        assert 'Move to' not in m.opt('TbSync', 'Text')

        # The wheel changes the month only after the drop; a right click cancels
        m.measure_values['MeasureTaskAction'] = 'OK'
        g.TaskResult()
        k = int(task_line()[2][3:])
        g.DragStart(k)
        g.DragOver(10)
        g.ScrollHours(1)
        assert m.opt('TbTitle', 'Text') == 'March 2027' and m.shown('DragHi')
        g.DragCancel(1)
        g.DragCancel()
        assert m.opt('TbTitle', 'Text') == 'April 2027' and not m.shown('DragHi')
        sk.check_clean()
    finally:
        sk.close()


def test_month_view_pixel_snapping_and_dark_theme():
    sk = Skin(View='month', Theme='dark', feeds={2: 'holidays.ics', 3: 'tasks.ics'})
    try:
        sk.start(2027, 3, 3, 12)
        m = sk.mock
        for (meter, opt), val in m.options.items():
            if opt in ('X', 'Y', 'W', 'H'):
                assert re.match(r'^-?\d+$', str(val)), (meter, opt, val)
        for k in range(1, 12):
            s = m.opt('Grid', 'Shape' if k == 1 else 'Shape%d' % k)
            assert s.startswith('Line ') and '.5' in s, (k, s)
        assert m.opt('MNum10', 'FontColor') == '227,227,227,255'
        sk.check_clean()
    finally:
        sk.close()


def test_one_tooltip_carrier():
    sk = Skin(View='month', feeds={3: 'tasks.ics'})
    try:
        sk.start(2027, 3, 3, 12)
        m, g = sk.mock, sk.g
        # No meter has a tooltip of its own: Rainmeter would create a window for each
        assert [k for k in m.options if k[1] == 'ToolTipText' and k[0] != 'Tip'] == []
        assert not m.shown('Tip')
        task = [l for l in month_lines(sk) if l[1].startswith('○ Simulazione')][0][2]
        # Entering the cell, then a line in it: the line (on top) wins, whatever the order
        g.TipOver('MHit3')
        assert m.shown('Tip') and m.opt('Tip', 'ToolTipText').startswith('March 3, 2027')
        assert m.opt('Tip', 'X') == m.opt('MHit3', 'X') and m.opt('Tip', 'W') == m.opt('MHit3', 'W')
        g.TipOver(task)
        assert m.opt('Tip', 'ToolTipText').startswith('○ Simulazione Tema di Esame#CRLF#Task')
        assert m.opt('Tip', 'H') == '16' and m.opt('Tip', 'Y') == str(int(m.opt(task, 'Y')) - 8)
        g.TipLeave('MHit3'); g.TipOver('MHit3')
        assert m.opt('Tip', 'ToolTipText').startswith('○ Simulazione')
        # Back on the cell background, then out of the skin
        g.TipLeave(task)
        assert m.opt('Tip', 'ToolTipText').startswith('March 3, 2027')
        g.TipLeave('MHit3')
        assert not m.shown('Tip')
        # A layout under a resting cursor: the carrier follows, or hides when the item is gone
        g.TipOver(task)
        g.SetView('week')
        assert not m.shown('Tip')
        i = task_chip(sk)
        g.TipOver('ADTx%d' % i)
        assert m.opt('Tip', 'ToolTipText').startswith('○ Simulazione')
        g.TipOver('ADChk%d' % i)
        assert m.opt('Tip', 'ToolTipText') == 'Mark complete'
        assert "TipLeave('ADChk%d')" % i in m.opt('ADChk%d' % i, 'MouseLeaveAction')
        g.TipLeave('ADChk%d' % i)
        g.ShiftView(1)                             # the chip's slot now holds another item
        assert not m.shown('Tip') or not m.opt('Tip', 'ToolTipText').startswith('○ Simulazione')
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
