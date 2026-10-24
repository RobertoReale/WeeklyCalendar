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
        daysFromCivil = daysFromCivil, cfg = cfg, LANGS = LANGS, toLatin1 = toLatin1, edit = edit }
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
            'ClickAction': 'calendar',  # (test_click_shows_the_card checks card)
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
    assert 'IcalUrl1=' in text and 'MyEmail=' in text and 'TasksToken=' in text


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
        assert sk.tip('ADBg%d' % i).endswith('#CRLF##CRLF#capitoli 1-3#CRLF#esercizi 4, 5 ( x)'
                                            '#CRLF##CRLF#Clic destro: dettagli, modifica, elimina')
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


def test_helper_keeps_dialogs_on_top_only_when_enabled():
    # Always started (it keeps what is typed in the cards); NoZOrder.txt turns its z-order off
    for value, flag in (('1', False), ('0', True)):
        sk = Skin(KeepDialogsOnTop=value)
        try:
            folder = os.path.join(sk.dir, '@Resources', 'ZOrder')
            os.makedirs(folder)
            if not flag:
                open(os.path.join(folder, 'NoZOrder.txt'), 'w').close()   # left by KeepDialogsOnTop=0
            sk.start(2027, 3, 3, 12)
            calls = []
            sk.mock.Bang = lambda *a: calls.append(sk.mock._args(a))
            sk.g.StartHelper()
            assert ['!CommandMeasure', 'MeasureZOrderHelper', 'Run'] in calls, (value, calls)
            assert os.path.exists(os.path.join(folder, 'NoZOrder.txt')) == flag, value
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
var PropertiesService = { getScriptProperties: function () { return { getProperty: function () { return null; } }; } };
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
        assert sk.tip('EvBg%d' % idx).endswith('#CRLF##CRLF#Middle-click: open the link#CRLF#Right-click: details, edit, delete')
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


def test_click_shows_the_card():
    # ClickAction=card: a left click shows the details (as the right click); the middle
    # click opens Google Calendar, or the link of an event without one
    sk = google_skin(ClickAction='card')
    try:
        m, g = sk.mock, sk.g
        i = event_meter(sk, 'Lezione')
        for meter in ('EvBg%d' % i, 'EvT%d' % i):
            assert m.opt(meter, 'LeftMouseUpAction') == '[!CommandMeasure MeasureScript "ItemCard(\'ev\', %d)"]' % i
        assert m.opt('EvBg%d' % i, 'MiddleMouseUpAction') == '["%s"]' % eid_link('abc123')
        assert sk.tip('EvBg%d' % i).endswith('Middle-click: open in Google Calendar#CRLF#Click: details, edit, delete')
        run_action(sk, m.opt('EvBg%d' % i, 'LeftMouseUpAction'))
        assert m.shown('CrCard') and any(t.startswith('Lezione') for t in card_texts(sk)), card_texts(sk)
        assert 'Open in Google' in card_texts(sk) and 'Open link' in card_texts(sk)
        g.CardClose()
        sk.check_clean()
    finally:
        sk.close()
    # All-day chips and the lines of the month view; tasks too
    sk = Skin(feeds={3: 'tasks.ics'}, ClickAction='card', DragToMove='0')
    try:
        sk.start(2027, 3, 3, 12)
        m, g = sk.mock, sk.g
        i = [v for k, v in sk.all_day().items() if k.startswith('○ Simulazione')][0]
        assert m.opt('ADBg%d' % i, 'LeftMouseUpAction') == '[!CommandMeasure MeasureScript "ItemCard(\'ad\', %d)"]' % i
        run_action(sk, m.opt('ADBg%d' % i, 'LeftMouseUpAction'))
        assert m.shown('CrCard') and 'Simulazione Tema di Esame' in card_texts(sk), card_texts(sk)
        g.CardClose()
        g.SetView('month')
        lines = [k for k in range(1, 400) if 'MLn%d' % k in m.sections and m.shown('MLn%d' % k)
                 and 'Simulazione' in (m.opt('MLn%d' % k, 'Text') or '')]
        assert lines, 'no month line'
        act = m.opt('MLn%d' % lines[0], 'LeftMouseUpAction')
        assert act == '[!CommandMeasure MeasureScript "ItemCard(\'ml\', %d)"]' % lines[0], act
        run_action(sk, act)
        assert m.shown('CrCard') and 'Simulazione Tema di Esame' in card_texts(sk), card_texts(sk)
        g.CardClose()
        sk.check_clean()
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
        assert sk.tip('ADBg%d' % i).endswith('#CRLF##CRLF#Right-click: details, edit, delete#CRLF#Drag to another day to move it')
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


def test_drag_click_shows_the_card():
    # ClickAction=card: a click on an item that can be dragged shows its card too
    sk = drag_skin(ClickAction='card')
    try:
        m, g = sk.mock, sk.g
        i = task_chip(sk)
        g.DragStart(i)
        g.DragOver(2)
        g.DragDrop(2)
        assert m.shown('CrCard') and 'Simulazione Tema di Esame' in card_texts(sk), card_texts(sk)
        assert not task_params(sk)
        g.CardClose()
        sk.check_clean()
    finally:
        sk.close()
    sk = edit_skin(ClickAction='card')
    try:
        m, g = sk.mock, sk.g
        i = event_meter(sk, 'Lezione')
        start = slot_of(sk, clock_of(utc(2027, 3, 3, 10)))
        g.DragEvent(i, 10)
        g.DragSlot(start)
        g.DragSlotDrop(start)
        assert m.shown('CrCard') and card_texts(sk)[0] == 'Lezione', card_texts(sk)
        g.CardClose()
        sk.check_clean()
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


def test_google_tasks_script_birthdays():
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
var ContentService = { MimeType: { ICAL: 'ical' }, createTextOutput: function (s) {
  return { text: s, setMimeType: function () { return this; } }; } };
var Tasks = { Tasklists: { list: function () { return { items: [] }; } } };
var Calendar = { Events: { list: function (cal, a) {
  calls.push([cal, a]);
  if (!a.pageToken) return { nextPageToken: 'p2', items: [
    { id: 'b1_20270304', summary: "Marco's birthday, 30", start: { date: '2027-03-04' }, end: { date: '2027-03-05' },
      htmlLink: 'https://www.google.com/calendar/event?eid=YjE' },
    { id: 'b2', summary: 'Gone', status: 'cancelled', start: { date: '2027-03-05' } } ] };
  return { items: [ { id: 'b3', summary: 'Anna', start: { date: '2027-06-01' } } ] };
} } };
var withCal = doGet({ parameter: { feed: 'birthdays' } }).text;
var tasks = doGet({ parameter: {} }).text;
var failing = (Calendar.Events.list = function () { throw new Error('Not allowed'); }, buildBirthdays());
Calendar = undefined;
var noService = buildBirthdays();
process.stdout.write(JSON.stringify({ ics: withCal, tasks: tasks, calls: calls, failing: failing, noService: noService }));
"""
    res = subprocess.run([node, '-e', harness], capture_output=True, encoding='utf-8')
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    ics = out['ics']
    assert 'X-WR-CALNAME:Birthdays\r\n' in ics and 'X-WR-CALNAME:Google Tasks' in out['tasks']
    assert ('BEGIN:VEVENT\r\nUID:b1_20270304@birthdays.google.com\r\nDTSTAMP:20270301T080000Z\r\n'
            'DTSTART;VALUE=DATE:20270304\r\nDTEND;VALUE=DATE:20270305\r\n'
            "SUMMARY:Marco's birthday\\, 30\r\nURL:https://www.google.com/calendar/event?eid=YjE\r\nEND:VEVENT\r\n") in ics, ics
    assert 'Gone' not in ics and 'UID:b3@birthdays.google.com\r\nDTSTAMP:20270301T080000Z\r\nDTSTART;VALUE=DATE:20270601\r\nSUMMARY:Anna\r\n' in ics
    first = out['calls'][0]
    assert first[0] == 'primary' and first[1]['eventTypes'] == ['birthday'] and first[1]['singleEvents'] is True
    assert out['calls'][1][1]['pageToken'] == 'p2'
    assert out['failing'] == 'ERROR Not allowed' and out['noService'].startswith('ERROR add the Google Calendar API')


def test_birthdays_feed_in_the_skin():
    bday_url = SCRIPT_URL + '?feed=birthdays'
    sk = Skin(IcalUrl1=bday_url, IcalUrl3=SCRIPT_URL, feeds={3: 'tasks.ics'})
    try:
        open(os.path.join(sk.dir, 'DownloadFile', 'calendar1.ics'), 'w', encoding='utf-8', newline='').write(
            'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nX-WR-CALNAME:Birthdays\r\n'
            'BEGIN:VEVENT\r\nUID:b1@birthdays.google.com\r\nDTSTART;VALUE=DATE:20270304\r\nDTEND;VALUE=DATE:20270305\r\n'
            "SUMMARY:Marco's birthday\r\nURL:https://www.google.com/calendar/event?eid=YjE\r\nEND:VEVENT\r\n"
            'END:VCALENDAR\r\n')
        sk.start(2027, 3, 3, 12)
        m, g = sk.mock, sk.g
        assert g._WC.cfg.scriptFeed == 3                     # not the birthdays address
        i = sk.all_day()["Marco's birthday"]
        assert chip_col(sk, i) == 3
        assert m.opt('ADBg%d' % i, 'LeftMouseUpAction') == '["https://www.google.com/calendar/event?eid=YjE"]'
        texts = open_card(sk, 'ADBg%d' % i)
        assert 'Delete' not in texts and 'Edit' not in texts
        assert any('Birthdays come from Google Contacts' in t for t in texts), texts
        g.CardClose()
        # The script says what is missing
        open(os.path.join(sk.dir, 'DownloadFile', 'calendar1.ics'), 'w', encoding='utf-8', newline='').write(
            'ERROR add the Google Calendar API service to the Tasks script (README, "Birthdays")')
        g.Reload(1)
        assert 'Calendar 1: ERROR add the Google Calendar API service' in sk.tip('TbSync'), sk.tip('TbSync')
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
var PropertiesService = { getScriptProperties: function () { return { getProperty: function () { return null; } }; } };
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
        assert sk.tip(ln).endswith('#CRLF##CRLF#Right-click: details, edit, delete#CRLF#Drag to another day to move it'), sk.tip(ln)
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


# ---------------------------------------------------------------------------
# Creating items (cards)
# ---------------------------------------------------------------------------
SCRIPT_URL = 'https://script.google.com/macros/s/TEST/exec'
HOLIDAY_URL = ('https://calendar.google.com/calendar/ical/it.italian%23holiday%40group.v.calendar.google.com'
               '/public/basic.ics')
CARD_METERS = ['CrCard', 'CrDismiss', 'CrDraft', 'CrDraftTx'] + ['CrTx%d' % k for k in range(1, 21)]


def ini_order():
    text = open(INI_FILE, encoding='utf-8-sig').read()
    return re.findall(r'^\[([^\]]+)\]', text, re.M)


def card_texts(sk):
    return [sk.mock.opt('CrTx%d' % k, 'Text') for k in range(1, 21) if sk.mock.shown('CrTx%d' % k)]


def card_el(sk, text):
    """The card meter showing text."""
    return [m for m in ('CrTx%d' % k for k in range(1, 21))
            if sk.mock.shown(m) and sk.mock.opt(m, 'Text') == text][0]


def run_action(sk, action):
    """Runs the [!CommandMeasure MeasureScript "..."] bangs of a mouse action."""
    calls = re.findall(r'!CommandMeasure MeasureScript "([^"]*)"', action or '')
    assert calls, action
    for lua in calls:
        sk.lua.execute(lua)


def enc(s):
    from urllib.parse import quote
    return quote(s, safe='')


def utc_of_local(y, mo, d, h, mi=0, compact=False):
    """UTC time of a local time (the time zone of this computer, as Calendar.lua uses)."""
    import time
    t = datetime.fromtimestamp(time.mktime((y, mo, d, h, mi, 0, 0, 0, -1)), timezone.utc)
    return t.strftime('%Y%m%dT%H%M%SZ' if compact else '%Y-%m-%dT%H:%M:%SZ')


def clock_of(epoch):
    return datetime.fromtimestamp(epoch).strftime('%H:%M')


def create_skin(script=True, **kw):
    if script:
        kw.setdefault('IcalUrl3', SCRIPT_URL)
    sk = Skin(feeds={3: 'tasks.ics'}, **kw)
    sk.start(2027, 3, 3, 12)  # Wednesday; 08:00-20:00 visible
    return sk


def hour_y(sk):
    """Y of the hour labels: {'10:00': y}."""
    m = sk.mock
    return {m.opt('HL%d' % k, 'Text'): int(m.opt('HL%d' % k, 'Y')) for k in range(1, 26) if m.shown('HL%d' % k)}


def zone_y(sk, col, clock):
    """$MouseY$ in CrZone<col> of a time like '10:20'."""
    h, mi = (int(x) for x in clock.split(':'))
    ys = hour_y(sk)
    y0, y1 = ys['%02d:00' % h], ys['%02d:00' % (h + 1)]
    # one pixel lower: a label rounded up would fall in the half hour before
    return round(y0 + (y1 - y0) * mi / 60) + 1 - int(sk.mock.opt('CrZone%d' % col, 'Y'))


def add_event(sk, feed, vevent):
    path = os.path.join(sk.dir, 'DownloadFile', 'calendar%d.ics' % feed)
    text = open(path, encoding='utf-8', newline='').read()
    nl = '\r\n' if '\r\n' in text else '\n'
    text = text.replace('END:VCALENDAR', vevent.replace('\n', nl) + 'END:VCALENDAR')
    open(path, 'w', encoding='utf-8', newline='').write(text)


def test_create_event_card_and_draft():
    sk = create_skin()
    try:
        m, g = sk.mock, sk.g
        hl = hour_y(sk)
        m.bangs.clear()
        g.CreateAt(2, zone_y(sk, 2, '10:20'))          # Wednesday 10:20: an event 10:00-11:00
        assert all(m.shown(x) for x in ('CrCard', 'CrDismiss', 'CrDraft', 'CrDraftTx'))
        top, h = int(m.opt('CrDraft', 'Y')), int(m.opt('CrDraft', 'H'))
        assert abs(top - hl['10:00']) <= 1 and abs(top + h - hl['11:00']) <= 2, (top, h, hl)
        assert int(m.opt('CrZone2', 'X')) <= int(m.opt('CrDraft', 'X')) < int(m.opt('CrZone3', 'X'))
        assert m.opt('CrDraftTx', 'Text') == '(no title)#CRLF#10:00 – 11:00', m.opt('CrDraftTx', 'Text')
        texts = card_texts(sk)
        for t in ('Event', 'Task', 'Wed 3 Mar', '10:00', '11:00', 'All day', 'me@example.com', 'Save', 'More options'):
            assert t in texts, (t, texts)
        assert m.opt(card_el(sk, 'Event'), 'FontColor') == '4,30,73,255'      # selected
        # Save is always a button (a click on it closes the box: see test_text_typed_before_a_click)
        assert m.opt(card_el(sk, 'Save'), 'FontColor') == '255,255,255,255'
        assert m.opt(card_el(sk, 'Save'), 'LeftMouseUpAction') == '[!CommandMeasure MeasureScript "CreateSave()"]'
        # The title box opens over the title field, inside the card, right of the column
        assert ['!CommandMeasure', 'MeasureCreateInput', 'ExecuteBatch 1'] in m.bangs
        cx, cy, cw, ch = (int(m.opt('CrCard', o)) for o in 'XYWH')
        ix, iy = int(m.opt('MeasureCreateInput', 'X')), int(m.opt('MeasureCreateInput', 'Y'))
        assert cx < ix < cx + cw and cy < iy < cy + ch, (cx, cy, cw, ch, ix, iy)
        assert cx + 12 == int(m.opt('CrZone3', 'X')) + 8
        assert m.opt('MeasureCreateInput', 'SolidColor') == '255,255,255,255'
        assert 'Press Enter to save' in texts
        # Esc or a click elsewhere closes the box: the field shows the placeholder again
        g.CreateInputClosed()
        assert 'Add title' in card_texts(sk) and 'Press Enter to save' not in card_texts(sk)
        run_action(sk, m.opt(card_el(sk, 'Add title'), 'LeftMouseUpAction'))   # click: type again
        assert m.bangs.count(['!CommandMeasure', 'MeasureCreateInput', 'ExecuteBatch 1']) == 2

        # The wheel: the start moves the event, the end stays 15 min after the start
        start = card_el(sk, '10:00')
        assert m.opt(start, 'MouseScrollUpAction') == '[!CommandMeasure MeasureScript "CreateAdjust(\'start\', 1)"]'
        assert sk.tip(start) == 'Click to type, scroll to change'
        assert sk.tip(card_el(sk, 'Wed 3 Mar')) == 'Scroll to change'
        g.CreateAdjust('start', 1)
        assert '10:15' in card_texts(sk) and '11:15' in card_texts(sk)
        for _ in range(8):
            g.CreateAdjust('end', -1)
        assert '10:15' in card_texts(sk) and '10:30' in card_texts(sk), card_texts(sk)
        g.CreateAdjust('date', 1)
        assert 'Thu 4 Mar' in card_texts(sk)
        assert int(m.opt('CrZone3', 'X')) <= int(m.opt('CrDraft', 'X')) < int(m.opt('CrZone4', 'X'))
        # Task: date only, the list, no "More options"; a task draft in the all-day row
        g.CreateType('task')
        texts = card_texts(sk)
        assert 'My Tasks' in texts and '10:15' not in texts and 'More options' not in texts and 'All day' not in texts
        assert int(m.opt('CrDraft', 'H')) == 20 and m.opt('CrDraftTx', 'Text') == '○ (no title)'
        g.CreateType('event')
        g.CreateToggleAllDay()
        assert '10:15' not in card_texts(sk) and int(m.opt('CrDraft', 'H')) == 20
        sk.check_clean()

        # Closing hides every meter of the card and clears their actions
        g.CardClose()
        assert not any(m.shown(x) for x in CARD_METERS)
        assert all(m.opt('CrTx%d' % k, 'LeftMouseUpAction') in (None, '') for k in range(1, 21))

        # Sunday: the card goes left of the column; at the bottom it stays inside the skin
        g.CreateAt(6, int(m.opt('CrZone6', 'H')) - 3)
        cx, cy, cw, ch = (int(m.opt('CrCard', o)) for o in 'XYWH')
        assert cx + cw - 12 <= int(m.opt('CrZone6', 'X')) - 8 + 1, (cx, cw)
        assert cy + ch - 12 <= int(m.vars['Height']) - 8
        g.CardClose()
        # The toolbar "+": today at the next half hour
        assert sk.tip('CrNew') == 'Create'
        assert '[CrNew]' in open(INI_FILE, encoding='utf-8').read()
        g.TipOver('CrNew')
        g.CreateNew()                                  # LeftMouseUpAction of [CrNew]
        assert not m.shown('Tip')                      # the button's tooltip goes under the card
        assert '12:00' in card_texts(sk) and '13:00' in card_texts(sk) and 'Wed 3 Mar' in card_texts(sk)
        g.CardClose()
        sk.check_clean()
    finally:
        sk.close()


def test_text_typed_before_a_click():
    # The helper of @Resources/ZOrder copies the text of the open box into Typed.txt (the skin
    # creates the file when it opens a box): a click on Save or on another part of the card
    # closes the box without Enter, and the text stays.
    sk = create_skin()
    try:
        m, g = sk.mock, sk.g
        typed = os.path.join(sk.dir, '@Resources', 'ZOrder', 'Typed.txt')

        def helper(text):
            assert os.path.exists(typed)               # a box is open
            open(typed, 'w', encoding='utf-8', newline='').write('WC\n' + text)

        # Without the helper (no folder): Save with no title opens the box again
        g.CreateAt(2, zone_y(sk, 2, '10:20'))
        g.CreateInputClosed()
        assert 'Add title' in card_texts(sk)
        m.bangs.clear()
        run_action(sk, m.opt(card_el(sk, 'Save'), 'LeftMouseUpAction'))
        assert ['!CommandMeasure', 'MeasureCreateInput', 'ExecuteBatch 1'] in m.bangs and not task_params(sk)
        g.CreateInputClosed()
        g.CardClose()

        # With it: typed, then a click on Save
        os.makedirs(os.path.dirname(typed))
        g.CreateAt(2, zone_y(sk, 2, '10:20'))
        assert open(typed, encoding='utf-8').read() == 'END'     # the cursor after the text
        helper('prova "uno" #2')
        g.CreateInputClosed()                          # the click closes the box first
        assert not os.path.exists(typed)
        run_action(sk, m.opt(card_el(sk, 'Save'), 'LeftMouseUpAction'))
        assert task_params(sk)[-1].startswith('-s -f -L -m 30 ' + SCRIPT_URL + '?action=createevent&cal=&title='
                                              + enc('prova "uno" #2') + '&start='), task_params(sk)[-1]
        assert not m.shown('CrCard')
        m.measure_values['MeasureTaskAction'] = 'OK abc1@google.com'
        g.TaskResult()

        # A click on Task keeps the title; the box opens again with it
        g.CreateAt(3, zone_y(sk, 3, '10:20'))
        helper('Comprare il latte')
        g.CreateInputClosed()
        g.CreateType('task')
        assert m.opt('MeasureCreateInput', 'DefaultValue') == 'Comprare il latte'
        assert m.opt('CrDraftTx', 'Text') == '○ Comprare il latte'
        # the time box too: typed, then a click on Save
        g.CreateType('event')
        g.CreateInputClosed()
        run_action(sk, m.opt(card_el(sk, '10:00'), 'LeftMouseUpAction'))
        assert open(typed, encoding='utf-8').read() == ''         # a time: the plugin selects it
        helper('11:30')
        g.TimeInputClosed()
        assert '11:30' in card_texts(sk) and '12:30' in card_texts(sk), card_texts(sk)
        # Enter still saves; a later box starts empty again (no text of the one before)
        g.CardTitle()
        helper('Comprare il latte e il pane')
        m.vars['CreateTitle'] = 'Comprare il latte e il pane'
        g.CreateSubmit()
        assert task_params(sk)[-1].startswith('-s -f -L -m 30 ' + SCRIPT_URL + '?action=createevent&cal=&title='
                                              + enc('Comprare il latte e il pane') + '&start='
                                              + enc(utc_of_local(2027, 3, 4, 11, 30))), task_params(sk)[-1]
        assert not os.path.exists(typed)
        # Esc without changes (the helper copied the text as shown) or with nothing copied
        g.CreateAt(2, zone_y(sk, 2, '16:20'))
        g.CreateInputClosed()
        assert 'Add title' in card_texts(sk)
        g.CardTitle()
        helper('')
        g.CreateInputClosed()
        assert 'Add title' in card_texts(sk)
        g.CardClose()
        # A quick tap on Save, handled before the box closes: the text typed so far
        m.measure_values['MeasureTaskAction'] = 'OK abc2@google.com'
        g.TaskResult()
        g.CreateAt(4, zone_y(sk, 4, '09:20'))
        helper('Tap veloce')
        run_action(sk, m.opt(card_el(sk, 'Save'), 'LeftMouseUpAction'))
        assert task_params(sk)[-1].startswith('-s -f -L -m 30 ' + SCRIPT_URL + '?action=createevent&cal=&title=Tap%20veloce&start=')
        g.CreateInputClosed()                          # the close, later: nothing more
        assert not m.shown('CrCard') and not os.path.exists(typed)
        sk.check_clean()
    finally:
        sk.close()

    # The edit form: a new title typed, then Save; an emptied title keeps the old one
    sk = edit_skin()
    try:
        m, g = sk.mock, sk.g
        typed = os.path.join(sk.dir, '@Resources', 'ZOrder', 'Typed.txt')
        os.makedirs(os.path.dirname(typed))
        open_card(sk, 'ADBg%d' % task_chip(sk))
        g.ItemEdit()
        open(typed, 'w', encoding='utf-8', newline='').write('WC\n')
        g.CreateInputClosed()
        assert 'Simulazione Tema di Esame' in card_texts(sk)
        g.CardTitle()
        open(typed, 'w', encoding='utf-8', newline='').write('WC\nSimulazione 2')
        g.CreateInputClosed()
        run_action(sk, m.opt(card_el(sk, 'Save'), 'LeftMouseUpAction'))
        assert task_params(sk)[-1].endswith('?action=edittask&list=L1&task=t-open&title=Simulazione%202'), task_params(sk)[-1]
        sk.check_clean()
    finally:
        sk.close()


def test_type_the_times_in_the_card():
    sk = create_skin()
    try:
        m, g = sk.mock, sk.g
        parse = sk.lua.eval('function(t, e) return _WC.edit.parseClock(t, e) end')
        for text, want in [('9', 540), ('09', 540), ('930', 570), ('0930', 570), ('9:30', 570), ('9.30', 570),
                           ('9,30', 570), ('9h30', 570), ('21h', 1260), (' 9 : 30 ', 570), ('9:30 pm', 1290),
                           ('12 am', 0), ('12pm', 720), ('0:00', 0), ('23:59', 1439),
                           ('24:00', None), ('9:60', None), ('25', None), ('13 pm', None), ('abc', None), ('', None)]:
            assert parse(text, False) == want, (text, parse(text, False), want)
        assert parse('24:00', True) == 1440 and parse('0:00', True) == 1440
        g.CreateAt(2, zone_y(sk, 2, '10:20'))                      # 10:00 - 11:00
        start = card_el(sk, '10:00')
        assert m.opt(start, 'LeftMouseUpAction') == '[!CommandMeasure MeasureScript "CardTime(\'start\')"]'
        m.bangs.clear()
        run_action(sk, m.opt(start, 'LeftMouseUpAction'))
        assert ['!CommandMeasure', 'MeasureTimeInput', 'ExecuteBatch 1'] in m.bangs
        assert m.opt('MeasureTimeInput', 'DefaultValue') == '10:00'
        cx, cy = int(m.opt('CrCard', 'X')), int(m.opt('CrCard', 'Y'))
        bx, by = int(m.opt('MeasureTimeInput', 'X')), int(m.opt('MeasureTimeInput', 'Y'))
        sx = int(m.opt(start, 'X'))                                 # the chip's center
        assert bx < sx < bx + int(m.opt('MeasureTimeInput', 'W')) and cy < by < cy + int(m.opt('CrCard', 'H'))
        # Enter: the start moves the event, which keeps its hour; then the title box again
        m.vars['CreateTime'] = '1430'
        m.bangs.clear()
        g.TimeSubmit()
        assert '14:30' in card_texts(sk) and '15:30' in card_texts(sk), card_texts(sk)
        assert ['!CommandMeasure', 'MeasureCreateInput', 'ExecuteBatch 1'] in m.bangs
        assert m.opt('CrDraftTx', 'Text').endswith('14:30 – 15:30')
        # The end: after the start, or nothing changes
        run_action(sk, m.opt(card_el(sk, '15:30'), 'LeftMouseUpAction'))
        assert m.opt('MeasureTimeInput', 'DefaultValue') == '15:30'
        m.vars['CreateTime'] = '13'
        g.TimeSubmit()
        assert '15:30' in card_texts(sk)
        run_action(sk, m.opt(card_el(sk, '15:30'), 'LeftMouseUpAction'))
        m.vars['CreateTime'] = '17:45'
        g.TimeSubmit()
        assert '14:30' in card_texts(sk) and '17:45' in card_texts(sk)
        # Esc: nothing changes; a late start keeps the event inside the day
        run_action(sk, m.opt(card_el(sk, '14:30'), 'LeftMouseUpAction'))
        g.TimeInputClosed()
        assert '14:30' in card_texts(sk)
        run_action(sk, m.opt(card_el(sk, '14:30'), 'LeftMouseUpAction'))
        m.vars['CreateTime'] = '23:30'
        g.TimeSubmit()
        assert '23:30' in card_texts(sk) and '24:00' in card_texts(sk), card_texts(sk)
        # the wheel still works
        g.CreateAdjust('start', -2)
        assert '23:00' in card_texts(sk)
        g.CardClose()
        sk.check_clean()
    finally:
        sk.close()
    # The edit form of an event: typed, then saved
    sk = edit_skin()
    try:
        m, g = sk.mock, sk.g
        open_card(sk, 'EvBg%d' % event_meter(sk, 'Lezione'))
        g.ItemEdit()
        h0 = int(clock_of(utc(2027, 3, 3, 10))[:2])
        run_action(sk, m.opt(card_el(sk, '%02d:00' % h0), 'LeftMouseUpAction'))
        m.vars['CreateTime'] = '%d:15' % (h0 + 2)
        g.TimeSubmit()
        g.ItemSave()
        assert 'start=' + enc(utc_of_local(2027, 3, 3, h0 + 2, 15)) in task_params(sk)[-1], task_params(sk)[-1]
        assert 'end=' + enc(utc_of_local(2027, 3, 3, h0 + 3, 15)) in task_params(sk)[-1]
        sk.check_clean()
    finally:
        sk.close()


def test_create_event_submit():
    sk = create_skin()
    try:
        m, g = sk.mock, sk.g
        g.CreateAt(2, zone_y(sk, 2, '14:00'))
        title = 'Ripasso "capitolo 3" & esercizi'
        m.vars['CreateTitle'] = title                # !SetVariable of the InputText command
        m.bangs.clear()
        g.CreateSubmit()
        assert task_params(sk) == ['-s -f -L -m 30 ' + SCRIPT_URL + '?action=createevent&cal=&title=' + enc(title)
                                   + '&start=' + enc(utc_of_local(2027, 3, 3, 14))
                                   + '&end=' + enc(utc_of_local(2027, 3, 3, 15))], task_params(sk)
        assert ['!CommandMeasure', 'MeasureTaskAction', 'Run'] in m.bangs
        assert not m.shown('CrCard') and not m.shown('CrDraft')

        def ripasso():
            return [t for t in sk.event_titles() if t.startswith("Ripasso 'capitolo 3'")]
        assert len(ripasso()) == 1, sk.event_titles()
        i = event_meter(sk, 'Ripasso')
        assert 'Saved - waiting for the calendar to sync' in sk.tip('EvBg%d' % i)
        assert 'Fill Color 3,155,229,255' in m.opt('EvBg%d' % i, 'Shape')   # the color of slot 1
        # Saved: still shown until the feed has it, then once
        m.measure_values['MeasureTaskAction'] = 'OK abc999@google.com'
        g.TaskResult()
        assert len(ripasso()) == 1
        add_event(sk, 1, 'BEGIN:VEVENT\nUID:abc999@google.com\nDTSTART:%s\nDTEND:%s\nSUMMARY:%s\nEND:VEVENT\n'
                  % (utc_of_local(2027, 3, 3, 14, compact=True), utc_of_local(2027, 3, 3, 15, compact=True), title))
        g.Reload(1)
        assert len(ripasso()) == 1, sk.event_titles()
        assert 'Saved' not in sk.tip('EvBg%d' % event_meter(sk, 'Ripasso'))

        # Google refuses: the item goes away and the form comes back with the title and the reason
        g.CreateAt(2, zone_y(sk, 2, '16:00'))
        m.vars['CreateTitle'] = 'Seconda "prova"'
        g.CreateSubmit()
        assert any(t.startswith("Seconda 'prova'") for t in sk.event_titles())
        m.measure_values['MeasureTaskAction'] = 'ERROR Calendar usage limits exceeded.'
        m.bangs.clear()
        g.TaskResult()
        assert not any(t.startswith('Seconda') for t in sk.event_titles())
        # (the box opens on a click only: one Rainmeter opens by itself gets no keyboard and
        # keeps the plugin from opening another)
        assert m.shown('CrCard') and ['!CommandMeasure', 'MeasureCreateInput', 'ExecuteBatch 1'] not in m.bangs
        assert 'Not saved: Calendar usage limits exceeded.' in card_texts(sk), card_texts(sk)
        assert m.opt('TbSync', 'Text').endswith('change not saved'), m.opt('TbSync', 'Text')
        run_action(sk, m.opt(card_el(sk, "Seconda 'prova'"), 'LeftMouseUpAction'))
        assert ['!CommandMeasure', 'MeasureCreateInput', 'ExecuteBatch 1'] in m.bangs
        assert m.opt('MeasureCreateInput', 'DefaultValue') == "Seconda 'prova'"
        # Enter on the title as it was saves the real one (with its quotes)
        m.vars['CreateTitle'] = "Seconda 'prova'"
        g.CreateSubmit()
        assert task_params(sk)[-1].split('&title=')[1].startswith(enc('Seconda "prova"') + '&'), task_params(sk)[-1]
        # Enter on an empty title only closes the box
        m.measure_values['MeasureTaskAction'] = 'OK x@google.com'
        g.TaskResult()
        g.CreateAt(2, zone_y(sk, 2, '17:00'))
        n = len(task_params(sk))
        m.vars['CreateTitle'] = '   '
        g.CreateSubmit()
        assert len(task_params(sk)) == n and m.shown('CrCard') and 'Add title' in card_texts(sk)
        sk.check_clean()
    finally:
        sk.close()


def test_create_task_from_all_day_row():
    sk = create_skin(TasksToken='s3cret')
    try:
        m, g = sk.mock, sk.g
        assert m.shown('CrAdZone4') and m.opt('CrAdZone4', 'LeftMouseUpAction') is None  # static in the .ini
        friday = [j for j in sk.all_day().values() if chip_col(sk, j) == 4]
        g.CreateAllDay(4)
        texts = card_texts(sk)
        assert 'Fri 5 Mar' in texts and 'My Tasks' in texts and 'More options' not in texts, texts
        assert m.opt(card_el(sk, 'Task'), 'FontColor') == '4,30,73,255'
        assert m.opt('CrDraft', 'Y') == str(56 + 68 + 3 + len(friday) * 22) and m.opt('CrDraftTx', 'Text') == '○ (no title)'
        assert 'Fill Color 142,36,170,255' in m.opt('CrDraft', 'Shape')     # the tasks' slot color
        m.vars['CreateTitle'] = 'Consegna'
        g.CreateSubmit()
        assert task_params(sk) == ['-s -f -L -m 30 ' + SCRIPT_URL + '?action=createtask&list=%40default'
                                   '&title=Consegna&due=2027-03-05&token=s3cret'], task_params(sk)
        i = sk.all_day()['○ Consegna']
        assert chip_col(sk, i) == 4 and not m.shown('ADChk%d' % i)
        assert m.opt('ADBg%d' % i, 'LeftMouseDownAction') == NO_DRAG    # not draggable before it syncs
        m.bangs.clear()
        m.measure_values['MeasureTaskAction'] = 'OK newtask1'
        g.TaskResult()
        assert ['!CommandMeasure', 'MeasureICS3', 'Update'] in m.bangs
        add_event(sk, 3, 'BEGIN:VEVENT\nUID:newtask1@tasks.google.com\nDTSTART;VALUE=DATE:20270305\n'
                         'SUMMARY:Consegna\nX-WC-TASK:NEEDS-ACTION\nX-WC-TASKLIST:L1\nX-WC-TASKID:newtask1\nEND:VEVENT\n')
        g.Reload(3)
        assert list(sk.all_day()).count('○ Consegna') == 1
        i = sk.all_day()['○ Consegna']
        assert m.shown('ADChk%d' % i)                                 # from the feed: checkable again
        # An all-day event from the all-day row: Event keeps "All day"
        g.CreateAllDay(1)
        g.CreateType('event')
        assert 'Tue 2 Mar' in card_texts(sk) and '09:00' not in card_texts(sk)
        m.vars['CreateTitle'] = 'Gita'
        g.CreateSubmit()
        assert task_params(sk)[-1].endswith('?action=createevent&cal=&title=Gita&date=2027-03-02&days=1&token=s3cret')
        # The day number adds a task too
        assert m.opt('DayNum2', 'LeftMouseUpAction') == '[!CommandMeasure MeasureScript "CreateAllDay(2)"]'
        assert sk.tip('DayNum2') == 'Click: add a task'
        sk.check_clean()
    finally:
        sk.close()


def test_create_without_the_script():
    sk = create_skin(script=False)
    try:
        m, g = sk.mock, sk.g
        assert sk.tip('DayNum2') == 'Click: add an event'
        g.CreateAt(2, zone_y(sk, 2, '10:00'))
        texts = card_texts(sk)
        assert 'Open in Google Calendar' in texts and 'Task' not in texts and 'More options' not in texts, texts
        assert sk.tip('DayNum2') == ''                # under the card: no tooltip of the items
        m.vars['CreateTitle'] = 'Cena'
        m.bangs.clear()
        g.CreateSubmit()
        url = ('https://calendar.google.com/calendar/render?action=TEMPLATE&text=Cena&dates='
               + utc_of_local(2027, 3, 3, 10, compact=True) + '/' + utc_of_local(2027, 3, 3, 11, compact=True)
               + '&authuser=me%40example.com')
        assert ['["%s"]' % url] in m.bangs, m.bangs
        assert not task_params(sk) and not m.shown('CrCard')
        # A task cannot be made without the script: the all-day row makes an all-day event
        g.CreateAllDay(4)
        assert 'Task' not in card_texts(sk)
        m.bangs.clear()
        g.CreateMore()
        assert [['["https://calendar.google.com/calendar/render?action=TEMPLATE&text=&dates=20270305/20270306'
                 '&authuser=me%40example.com"]']] == [b for b in m.bangs if b[0].startswith('["https://')]
        sk.check_clean()
    finally:
        sk.close()


def test_create_zones_are_under_the_items():
    order = ini_order()
    for z in ('CrZone6', 'CrAdZone6'):
        assert order.index('Grid') < order.index(z) < order.index('ADBg1') < order.index('EvBg1'), z
    assert order.index('EvD80') < order.index('CrDraft') < order.index('HidUpBg0')
    assert order.index('DragZone41') < order.index('DragSlot1') < order.index('CrDismiss') < order.index('CrCard')
    assert order.index('CrCard') < order.index('CrTx1') < order.index('ToastBg')
    # the line of the current time goes under an open card
    assert order.index('EvBg80') < order.index('NowLine') < order.index('CrDismiss')
    # Clicks on the hours and on the events: the events keep their own click
    sk = create_skin()
    try:
        i = event_meter(sk, 'Attività')
        # (an event the skin may change is pressed to drag it; its click comes through the drop)
        assert sk.mock.opt('EvBg%d' % i, 'LeftMouseDownAction') ==             '[!CommandMeasure MeasureScript "DragEvent(%d, $MouseY$+0, $MouseX$+0)"]' % i
        assert sk.mock.opt('EvBg%d' % i, 'RightMouseUpAction') == '[!CommandMeasure MeasureScript "ItemCard(\'ev\', %d)"]' % i
        # The month view has no zones
        sk.g.SetView('month')
        assert not any(sk.mock.shown('CrZone%d' % c) or sk.mock.shown('CrAdZone%d' % c) for c in range(7))
        sk.check_clean()
    finally:
        sk.close()


def test_settings_turn_off_creating_and_dragging():
    sk = create_skin()
    try:
        today_x = int(sk.mock.opt('BtnToday', 'X'))
        assert sk.mock.opt('DayNum2', 'LeftMouseUpAction') == '[!CommandMeasure MeasureScript "CreateAllDay(2)"]'
    finally:
        sk.close()
    sk = create_skin(ClickToCreate='0', ShowCreateButton='0', DragToMove='0')
    try:
        m, g = sk.mock, sk.g
        # No "+": the buttons take its place
        assert not m.shown('CrNew') and not m.shown('CrNewTx') and sk.tip('CrNew') == ''
        assert int(m.opt('BtnToday', 'X')) == today_x - 42
        # Empty spots: no click, but the zones stay (a press on the grid must not move the skin)
        for c in range(7):
            assert m.shown('CrZone%d' % c) and m.opt('CrZone%d' % c, 'LeftMouseUpAction') == ''
            assert m.opt('CrAdZone%d' % c, 'LeftMouseUpAction') == ''
        assert m.opt('DayNum2', 'LeftMouseUpAction') is None and sk.tip('DayNum2') == ''
        assert m.opt('DayNum2', 'MouseActionCursor') == '0'
        # Events and tasks keep their click, right-click and the harmless press
        i = event_meter(sk, 'Attività')
        assert m.opt('EvBg%d' % i, 'LeftMouseDownAction') == NO_DRAG
        assert m.opt('EvBg%d' % i, 'LeftMouseUpAction').startswith('["https://')
        assert m.opt('EvBg%d' % i, 'RightMouseUpAction') == '[!CommandMeasure MeasureScript "ItemCard(\'ev\', %d)"]' % i
        assert 'Drag' not in sk.tip('EvBg%d' % i)
        j = task_chip(sk)
        assert m.opt('ADBg%d' % j, 'LeftMouseDownAction') == NO_DRAG and 'Drag' not in sk.tip('ADBg%d' % j)
        assert m.opt('ADBg%d' % j, 'LeftMouseUpAction') != ''
        g.SetView('month')
        assert not any((m.opt('MLn%d' % k, 'LeftMouseDownAction') or NO_DRAG) != NO_DRAG for k in range(1, 211))
        sk.check_clean()
    finally:
        sk.close()
    # RightClickCard=0: the right click shows the skin menu again, and the tooltips do not offer it
    sk = create_skin(RightClickCard='0')
    try:
        m, g = sk.mock, sk.g
        i = event_meter(sk, 'Attività')
        for meter in ('EvBg%d' % i, 'EvT%d' % i):
            assert m.opt(meter, 'RightMouseUpAction') == '', meter
        assert 'Right-click' not in sk.tip('EvBg%d' % i) and 'Drag' in sk.tip('EvBg%d' % i)
        j = task_chip(sk)
        assert m.opt('ADBg%d' % j, 'RightMouseUpAction') == '' and 'Right-click' not in sk.tip('ADBg%d' % j)
        assert not sk.tip('ADBg%d' % j).endswith('#CRLF#')
        g.SetView('month')
        assert not any(m.opt('MLn%d' % k, 'RightMouseUpAction') for k in range(1, 211))
        sk.check_clean()
    finally:
        sk.close()


def test_settings_new_event_length_and_undo_time():
    sk = create_skin(NewEventMinutes='30')
    try:
        sk.g.CreateAt(2, zone_y(sk, 2, '10:20'))
        assert '10:00' in card_texts(sk) and '10:30' in card_texts(sk), card_texts(sk)
        sk.g.CardClose()
    finally:
        sk.close()
    sk = edit_skin(UndoSeconds='3')
    try:
        m, g = sk.mock, sk.g
        open_card(sk, 'EvBg%d' % event_meter(sk, 'Lezione'))
        g.ItemDelete('one')
        sk.at(2027, 3, 3, 8, 0, 2)
        g.Tick()
        assert not task_params(sk) and m.shown('ToastBg')
        sk.at(2027, 3, 3, 8, 0, 4)
        g.Tick()
        assert task_params(sk) and not m.shown('ToastBg')
        sk.check_clean()
    finally:
        sk.close()


# ---------------------------------------------------------------------------
# Details, editing and deleting (cards)
# ---------------------------------------------------------------------------
EDIT_ICS = GOOGLE_ICS.replace('END:VCALENDAR\r\n', (
    "BEGIN:VEVENT\r\nUID:inv@google.com\r\nDTSTART:20270304T130000Z\r\nDTEND:20270304T140000Z\r\n"
    "SUMMARY:Invito\r\nORGANIZER;CN=Other:mailto:Other@Example.com\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nUID:mine@google.com\r\nDTSTART:20270305T130000Z\r\nDTEND:20270305T140000Z\r\n"
    "SUMMARY:Mia riunione\r\nORGANIZER:mailto:me@example.com\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nUID:trip@google.com\r\nDTSTART;VALUE=DATE:20270304\r\nDTEND;VALUE=DATE:20270306\r\n"
    "SUMMARY:Gita\r\nEND:VEVENT\r\n"
    "END:VCALENDAR\r\n"))


def edit_skin(tasks='tasks.ics', **kw):
    kw.setdefault('IcalUrl3', SCRIPT_URL)
    sk = Skin(**kw)
    open(os.path.join(sk.dir, 'DownloadFile', 'calendar1.ics'), 'w', encoding='utf-8', newline='').write(EDIT_ICS)
    shutil.copy(os.path.join(FIXTURES, tasks), os.path.join(sk.dir, 'DownloadFile', 'calendar3.ics'))
    sk.start(2027, 3, 3, 8)
    return sk


GHOST_ICS = EDIT_ICS.replace('END:VCALENDAR\r\n', (
    # Google's iCal address lists the tasks that have a time as free events
    "BEGIN:VEVENT\r\nUID:ghost1@google.com\r\nDTSTART:20270303T140000Z\r\nDTEND:20270303T150000Z\r\n"
    "SUMMARY:Simulazione Tema di Esame\r\nCLASS:PRIVATE\r\nTRANSP:TRANSPARENT\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nUID:ghost2@google.com\r\nDTSTART:20270302T090000Z\r\nDTEND:20270302T093000Z\r\n"
    "SUMMARY:Esercizi\\, parte 2\r\nTRANSP:TRANSPARENT\r\nEND:VEVENT\r\n"
    # a real event with a task's title stays
    "BEGIN:VEVENT\r\nUID:real@google.com\r\nDTSTART:20270301T090000Z\r\nDTEND:20270301T100000Z\r\n"
    "SUMMARY:Ripasso\r\nTRANSP:OPAQUE\r\nEND:VEVENT\r\n"
    "END:VCALENDAR\r\n"))


def test_short_events_show_their_place():
    sk = edit_skin()
    try:
        m, g = sk.mock, sk.g
        extra = (
            "BEGIN:VEVENT\r\nUID:barber@google.com\r\nDTSTART:20270304T163000Z\r\nDTEND:20270304T173000Z\r\n"
            "SUMMARY:Barbiere\r\nLOCATION:Viale Monza\\, 325\r\nEND:VEVENT\r\n"
            "BEGIN:VEVENT\r\nUID:short@google.com\r\nDTSTART:20270305T163000Z\r\nDTEND:20270305T170000Z\r\n"
            "SUMMARY:Breve\r\nLOCATION:Sala 2\r\nEND:VEVENT\r\n"
            "BEGIN:VEVENT\r\nUID:mid@google.com\r\nDTSTART:20270302T163000Z\r\nDTEND:20270302T171500Z\r\n"
            "SUMMARY:Medio\r\nLOCATION:Sala 3\r\nEND:VEVENT\r\n"
            "BEGIN:VEVENT\r\nUID:long@google.com\r\nDTSTART:20270306T090000Z\r\nDTEND:20270306T120000Z\r\n"
            "SUMMARY:Lungo\r\nLOCATION:Aula 5\r\nEND:VEVENT\r\n")
        open(os.path.join(sk.dir, 'DownloadFile', 'calendar1.ics'), 'w', encoding='utf-8', newline='').write(
            EDIT_ICS.replace('END:VCALENDAR\r\n', extra + 'END:VCALENDAR\r\n'))
        g.Reload(1)

        def lines(title):
            i = list(event_meters(sk, title).values())[0]
            text = m.opt('EvT%d' % i, 'Text')
            if m.shown('EvD%d' % i):
                text += '#CRLF#' + m.opt('EvD%d' % i, 'Text')
            return text.split('#CRLF#')
        start = clock_of(utc(2027, 3, 4, 16, 30))
        # one hour: the title, then the start and the place on one line
        assert lines('Barbiere') == ['Barbiere', start + ', Viale Monza, 325'], lines('Barbiere')
        # 45 minutes: still the title on its own line, like Google Calendar (less padding)
        mid = clock_of(utc(2027, 3, 2, 16, 30))
        assert lines('Medio') == ['Medio', mid + ', Sala 3'], lines('Medio')
        i = list(event_meters(sk, 'Medio').values())[0]
        assert int(m.opt('EvD%d' % i, 'Y')) + 16 <= int(m.opt('EvBg%d' % i, 'Y')) + int(m.opt('EvBg%d' % i, 'H')) + 2
        # half an hour: everything on the title's line
        assert lines('Breve') == ['Breve, ' + start + ', Sala 2'], lines('Breve')
        # tall boxes keep the time range and the place on lines of their own
        assert lines('Lungo')[1:3] == ['%s – %s' % (clock_of(utc(2027, 3, 6, 9)), clock_of(utc(2027, 3, 6, 12))), 'Aula 5']
        sk.check_clean()
    finally:
        sk.close()


def test_low_box_keeps_its_line_inside():
    # Every hour visible: a short event gets the smallest box (16 px); its one line is
    # centered in it instead of running past the bottom
    sk = edit_skin(StartHour='0', EndHour='24')
    try:
        m, g = sk.mock, sk.g
        extra = ("BEGIN:VEVENT\r\nUID:tiny@google.com\r\nDTSTART:20270301T163000Z\r\nDTEND:20270301T164500Z\r\n"
                 "SUMMARY:Minimo\r\nEND:VEVENT\r\n")
        open(os.path.join(sk.dir, 'DownloadFile', 'calendar1.ics'), 'w', encoding='utf-8', newline='').write(
            EDIT_ICS.replace('END:VCALENDAR\r\n', extra + 'END:VCALENDAR\r\n'))
        g.Reload(1)
        i = list(event_meters(sk, 'Minimo').values())[0]
        top, h = int(m.opt('EvBg%d' % i, 'Y')), int(m.opt('EvBg%d' % i, 'H'))
        ty, th = int(m.opt('EvT%d' % i, 'Y')), int(m.opt('EvT%d' % i, 'H'))
        assert h < 20 and top <= ty and ty + th <= top + h + 1, (top, h, ty, th)
        sk.check_clean()
    finally:
        sk.close()


def test_task_with_a_time_shows_once():
    sk = edit_skin()
    try:
        m, g = sk.mock, sk.g
        open(os.path.join(sk.dir, 'DownloadFile', 'calendar1.ics'), 'w', encoding='utf-8', newline='').write(GHOST_ICS)
        g.Reload(1)
        chips = sk.all_day()
        assert not any(t.startswith('○ Simulazione') or t.startswith('✓ Esercizi') for t in chips), chips
        assert '○ Ripasso' in chips and list(event_meters(sk, 'Ripasso')) == [0]
        assert list(event_meters(sk, '✓ Eserci')) == [1]
        cols = event_meters(sk, '○ Simulazione')
        assert list(cols) == [2], cols
        i = cols[2]
        assert not event_meters(sk, 'Simulazione')                  # the free event is left out
        h0 = int(clock_of(utc(2027, 3, 3, 14))[:2])
        assert '%02d:00 – %02d:00' % (h0, h0 + 1) in m.opt('EvT%d' % i, 'Text') + m.opt('EvD%d' % i, 'Text')
        assert sk.tip('EvBg%d' % i).split('#CRLF#')[2] == 'Task · Le mie attività'
        assert m.opt('EvBg%d' % i, 'LeftMouseDownAction') == NO_DRAG  # a task is not dragged by its time
        # The card: a task at that time; editing keeps only the date
        texts = open_card(sk, 'EvBg%d' % i)
        assert 'Mark complete' in texts and any('%02d:00' % h0 in t for t in texts), texts
        g.ItemEdit()
        assert not any('%02d:00' % h0 in t for t in card_texts(sk)), card_texts(sk)
        g.CardClose()
        # Completed from the card: it stays at its time, with the check mark
        open_card(sk, 'EvBg%d' % i)
        g.ItemToggle()
        assert list(event_meters(sk, '✓ Simulazione')) == [2]
        # struck through like Google Calendar, title and time (not the check mark)
        assert m.opt('EvT%d' % i, 'InlineSetting') == 'Strikethrough'
        assert m.opt('EvT%d' % i, 'InlinePattern') == '(?s)^\\S+ (.*)$'
        assert m.opt('EvD%d' % i, 'InlineSetting') == 'Strikethrough'
        assert m.opt('EvT%d' % event_meters(sk, 'Ripasso')[0], 'InlineSetting') == ''
        assert 'action=complete' in task_params(sk)[-1]
        m.measure_values['MeasureTaskAction'] = 'OK'
        g.TaskResult()
        # Deleted: the free event does not come back while Google's address still has it
        open_card(sk, 'EvBg%d' % event_meters(sk, '✓ Simulazione')[2])
        g.ItemDelete('one')
        assert not event_meters(sk, '✓ Simulazione') and not event_meters(sk, 'Simulazione')
        g.ItemUndo()
        # Moved to another day: an all-day task there, the free event still hidden
        open_card(sk, 'EvBg%d' % event_meters(sk, '✓ Simulazione')[2])
        g.ItemEdit()
        g.CreateAdjust('date', 1)
        g.ItemSave()
        assert not event_meters(sk, 'Simulazione') and not event_meters(sk, '✓ Simulazione')
        assert chip_col(sk, sk.all_day()['✓ Simulazione Tema di Esame']) == 3
        g.SetView('month')
        assert not any((m.opt('MLn%d' % k, 'Text') or '').endswith(' Simulazione Tema di Esame') and m.shown('MLn%d' % k)
                       and (m.opt('MLn%d' % k, 'Text') or '')[:1].isdigit() for k in range(1, 211))
        sk.check_clean()
    finally:
        sk.close()


def event_meters(sk, title):
    """Shown event meters of a title as {day column: index}."""
    return {int((int(sk.mock.opt('EvBg%d' % i, 'X')) - 64) // DAY_W): i for i in range(1, 81)
            if sk.mock.shown('EvT%d' % i) and sk.mock.opt('EvT%d' % i, 'Text').startswith(title)}


def open_card(sk, meter):
    run_action(sk, sk.mock.opt(meter, 'RightMouseUpAction'))
    assert sk.mock.shown('CrCard')
    return card_texts(sk)


def test_item_card_details_and_read_only():
    sk = edit_skin(IcalUrl2=HOLIDAY_URL)
    try:
        m, g = sk.mock, sk.g
        shutil.copy(os.path.join(FIXTURES, 'holidays.ics'), os.path.join(sk.dir, 'DownloadFile', 'calendar2.ics'))
        g.Reload(2)
        i = event_meter(sk, 'Lezione')
        for meter in ('EvBg%d' % i, 'EvT%d' % i):
            assert m.opt(meter, 'RightMouseUpAction') == '[!CommandMeasure MeasureScript "ItemCard(\'ev\', %d)"]' % i
        assert sk.tip('EvBg%d' % i).endswith('#CRLF#Right-click: details, edit, delete#CRLF#Drag to move this event')
        texts = open_card(sk, 'EvBg%d' % i)
        when = 'Wed 3 Mar · %s – %s' % (clock_of(utc(2027, 3, 3, 10)), clock_of(utc(2027, 3, 3, 11)))
        assert texts[0] == 'Lezione' and when in texts, texts
        assert 'Aula 3.0.3#CRLF#Portare il libro & appunti' in texts, texts
        for t in ('Open in Google', 'Open link', 'Edit', 'Delete'):
            assert t in texts, (t, texts)
        assert m.opt(card_el(sk, 'Delete'), 'FontColor') == '234,67,53,255'
        assert m.opt(card_el(sk, 'Open link'), 'LeftMouseUpAction') == \
            '["https://meet.google.com/abc-defg-hij"][!CommandMeasure MeasureScript "CardClose()"]'
        assert not m.shown('CrDraft')
        # beside the event's column
        assert int(m.opt('CrCard', 'X')) + 12 == int(64 + 3 * DAY_W + 0.5) + 8
        # A click outside closes it; a right click too
        assert m.opt('CrDismiss', 'LeftMouseUpAction') is None    # static in the .ini: CardClose()
        g.CardClose()
        # Recurring: how it repeats
        texts = open_card(sk, 'EvBg%d' % event_meters(sk, 'Daily')[2])
        assert any(t.endswith('#CRLF#Every day') for t in texts) and 'Edit' in texts, texts
        g.CardClose()
        # Read-only: an invitation of someone else, a holiday; my own meeting is not
        texts = open_card(sk, 'EvBg%d' % event_meter(sk, 'Invito'))
        assert 'Organised by other@example.com' in texts and 'Edit' not in texts and 'Delete' not in texts, texts
        assert 'Open in Google' in texts
        g.CardClose()
        assert 'Edit' in open_card(sk, 'EvBg%d' % event_meter(sk, 'Mia riunione'))
        g.CardClose()
        texts = open_card(sk, 'ADBg%d' % sk.all_day()['Festa di prova'])
        assert 'Holiday calendar - read only' in texts and 'Delete' not in texts, texts
        g.CardClose()
        # A task: complete it from the card
        texts = open_card(sk, 'ADBg%d' % task_chip(sk))
        assert texts[:2] == ['Simulazione Tema di Esame', 'Wed 3 Mar#CRLF#Task · Le mie attività'] and 'Mark complete' in texts, texts
        g.ItemToggle()
        assert not m.shown('CrCard') and task_params(sk)[-1].endswith('?action=complete&list=L1&task=t-open')
        # Tasks of an older script: read-only, with what to do
        texts = open_card(sk, 'ADBg%d' % sk.all_day()['○ Ripasso'])
        assert 'Edit' not in texts and any('GoogleTasksFeed.gs' in t for t in texts), texts
        g.CardClose()
        # "+N more" has no card
        more = [v for k, v in sk.all_day().items() if k.startswith('+')]
        assert all(m.opt('ADBg%d' % j, 'RightMouseUpAction') == '' for j in more)
        sk.check_clean()
    finally:
        sk.close()
    # Without the Tasks script events are read-only, with the reason
    sk = edit_skin(IcalUrl3='')
    try:
        texts = open_card(sk, 'EvBg%d' % event_meter(sk, 'Lezione'))
        assert 'Edit' not in texts and any('GoogleTasksFeed.gs' in t for t in texts), texts
        sk.check_clean()
    finally:
        sk.close()


def test_delete_event_with_undo():
    sk = edit_skin(Language='it')
    try:
        m, g = sk.mock, sk.g

        def lezione():
            return any(t.startswith('Lezione') for t in sk.event_titles())
        open_card(sk, 'EvBg%d' % event_meter(sk, 'Lezione'))
        run_action(sk, m.opt(card_el(sk, 'Elimina'), 'LeftMouseUpAction'))
        assert not lezione() and not m.shown('CrCard')
        assert m.shown('ToastBg') and m.opt('ToastTx', 'Text') == 'Evento eliminato' and m.opt('ToastAct', 'Text') == 'Annulla'
        assert m.opt('ToastAct', 'FontColor') == '168,199,250,255'
        assert ['!EnableMeasure', 'MeasureTick'] in m.bangs and not task_params(sk)
        m.bangs.clear()
        g.ItemUndo()
        assert lezione() and not m.shown('ToastBg') and not task_params(sk)
        assert ['!DisableMeasure', 'MeasureTick'] in m.bangs
        # Deleted again: sent 8 s later
        open_card(sk, 'EvBg%d' % event_meter(sk, 'Lezione'))
        g.ItemDelete('one')
        sk.at(2027, 3, 3, 8, 0, 5)
        g.Tick()
        assert not task_params(sk) and m.shown('ToastBg')
        sk.at(2027, 3, 3, 8, 0, 9)
        g.Tick()
        assert task_params(sk) == ['-s -f -L -m 30 ' + SCRIPT_URL
                                   + '?action=deleteevent&cal=me%40example.com&uid=abc123%40google.com&scope=one']
        assert not m.shown('ToastBg') and not lezione()
        # Google refuses: it comes back, and the toolbar says so
        m.measure_values['MeasureTaskAction'] = 'ERROR Forbidden'
        g.TaskResult()
        assert lezione() and m.opt('TbSync', 'Text').endswith('modifica non salvata'), m.opt('TbSync', 'Text')
        assert 'Google: Forbidden' in sk.tip('TbSync')
        # Saved: hidden while the feed still has it, then the feed drops it
        open_card(sk, 'EvBg%d' % event_meter(sk, 'Lezione'))
        g.ItemDelete('one')
        sk.at(2027, 3, 3, 8, 0, 20)
        g.Tick()
        m.measure_values['MeasureTaskAction'] = 'OK'
        g.TaskResult()
        g.Reload(1)
        assert not lezione()
        path = os.path.join(sk.dir, 'DownloadFile', 'calendar1.ics')
        text = open(path, encoding='utf-8', newline='').read()
        start = text.index('BEGIN:VEVENT\r\nUID:abc123')
        without = text[:start] + text[text.index('END:VEVENT\r\n', start) + 12:]
        open(path, 'w', encoding='utf-8', newline='').write(without)
        g.Reload(1)
        assert not lezione()
        # ...the local change is gone: the event shows again if it comes back
        open(path, 'w', encoding='utf-8', newline='').write(text)
        g.Reload(1)
        assert lezione()
        # A second deletion within 8 s sends the first at once
        open_card(sk, 'EvBg%d' % event_meter(sk, 'Lezione'))
        g.ItemDelete('one')
        n = len(task_params(sk))
        open_card(sk, 'EvBg%d' % event_meter(sk, 'Invito'))
        assert 'Elimina' not in card_texts(sk)
        g.CardClose()
        open_card(sk, 'EvBg%d' % event_meter(sk, 'Mia riunione'))
        g.ItemDelete('one')
        assert len(task_params(sk)) == n + 1 and 'uid=abc123' in task_params(sk)[-1]
        # Kept at most a day while the feed still has it
        m.measure_values['MeasureTaskAction'] = 'OK'
        g.TaskResult()
        sk.at(2027, 3, 4, 9)
        g.Reload(1)
        assert lezione()
        sk.check_clean()
    finally:
        sk.close()


def test_delete_recurring_event():
    sk = edit_skin(TasksToken='t')
    try:
        m, g = sk.mock, sk.g
        assert sorted(event_meters(sk, 'Daily')) == [0, 1, 2, 3, 4]
        texts = open_card(sk, 'EvBg%d' % event_meters(sk, 'Daily')[2])
        assert m.opt(card_el(sk, 'Delete'), 'LeftMouseUpAction') == '[!CommandMeasure MeasureScript "ItemDeleteAsk(1)"]'
        g.ItemDeleteAsk(1)
        texts = card_texts(sk)
        assert 'Delete recurring event:' in texts and 'This event' in texts and 'All events' in texts and 'Cancel' in texts
        g.ItemDeleteAsk(0)
        assert 'Edit' in card_texts(sk)
        g.ItemDeleteAsk(1)
        g.ItemDelete('one')
        assert sorted(event_meters(sk, 'Daily')) == [0, 1, 3, 4]
        sk.at(2027, 3, 3, 8, 0, 9)
        g.Tick()
        assert task_params(sk)[-1] == ('-s -f -L -m 30 ' + SCRIPT_URL + '?action=deleteevent&cal=me%40example.com'
                                       '&uid=rec%40google.com&orig=2027-03-03T09%3A00%3A00Z&scope=one&token=t')
        m.measure_values['MeasureTaskAction'] = 'OK'
        g.TaskResult()
        # All events
        open_card(sk, 'EvBg%d' % event_meters(sk, 'Daily')[0])
        g.ItemDelete('all')
        assert event_meters(sk, 'Daily') == {}
        sk.at(2027, 3, 3, 8, 0, 20)
        g.Tick()
        assert task_params(sk)[-1].endswith('&uid=rec%40google.com&orig=2027-03-01T09%3A00%3A00Z&scope=all&token=t')
        g.TaskResult()
        g.ShiftWeek(1)
        g.ShiftWeek(-1)
        assert event_meters(sk, 'Daily') == {}
        sk.check_clean()
    finally:
        sk.close()


def test_edit_task_and_events():
    sk = edit_skin()
    try:
        m, g = sk.mock, sk.g
        # A task: new title and two days later
        open_card(sk, 'ADBg%d' % task_chip(sk))
        g.ItemEdit()
        assert m.opt('MeasureCreateInput', 'DefaultValue') == 'Simulazione Tema di Esame'
        texts = card_texts(sk)
        assert 'Wed 3 Mar' in texts and 'Save' in texts and 'Cancel' in texts and '00:00' not in texts, texts
        g.CreateAdjust('date', 2)
        m.vars['CreateTitle'] = 'Nuovo titolo'
        g.CreateSubmit()                                  # Enter saves
        assert task_params(sk)[-1] == ('-s -f -L -m 30 ' + SCRIPT_URL
                                       + '?action=edittask&list=L1&task=t-open&title=Nuovo%20titolo&due=2027-03-05')
        assert chip_col(sk, sk.all_day()['○ Nuovo titolo']) == 4 and not m.shown('CrCard')
        m.measure_values['MeasureTaskAction'] = 'ERROR Backend Error'
        g.TaskResult()
        assert chip_col(sk, task_chip(sk)) == 2           # back
        # Only the title: the date is not sent again (it could drop a time set in Google)
        open_card(sk, 'ADBg%d' % task_chip(sk))
        g.ItemEdit()
        m.vars['CreateTitle'] = 'Solo titolo'
        g.CreateSubmit()
        assert task_params(sk)[-1].endswith('?action=edittask&list=L1&task=t-open&title=Solo%20titolo'), task_params(sk)[-1]
        m.measure_values['MeasureTaskAction'] = 'ERROR Backend Error'
        g.TaskResult()
        # Saved without changes: nothing is sent
        n = len(task_params(sk))
        open_card(sk, 'ADBg%d' % task_chip(sk))
        g.ItemEdit()
        g.ItemSave()
        assert len(task_params(sk)) == n and not m.shown('CrCard')
        # Delete a task
        open_card(sk, 'ADBg%d' % task_chip(sk))
        g.ItemDelete('one')
        assert not any(k.startswith('○ Simulazione') for k in sk.all_day())
        assert m.opt('ToastTx', 'Text') == 'Task deleted'
        sk.at(2027, 3, 3, 8, 0, 9)
        g.Tick()
        assert task_params(sk)[-1].endswith('?action=deletetask&list=L1&task=t-open')
        m.measure_values['MeasureTaskAction'] = 'OK'
        m.bangs.clear()
        g.TaskResult()
        assert ['!CommandMeasure', 'MeasureICS3', 'Update'] in m.bangs
        assert not any(k.startswith('○ Simulazione') for k in sk.all_day())

        # One occurrence of a recurring event, 30 minutes later; Save with the mouse
        before = {c: int(m.opt('EvBg%d' % i, 'Y')) for c, i in event_meters(sk, 'Daily').items()}
        open_card(sk, 'EvBg%d' % event_meters(sk, 'Daily')[2])
        g.ItemEdit()
        assert 'Only this event will change' in card_texts(sk)
        g.CreateInputClosed()
        g.CreateAdjust('start', 2)
        run_action(sk, m.opt(card_el(sk, 'Save'), 'LeftMouseUpAction'))
        assert task_params(sk)[-1] == ('-s -f -L -m 30 ' + SCRIPT_URL + '?action=editevent&cal=me%40example.com'
                                       '&uid=rec%40google.com&orig=2027-03-03T09%3A00%3A00Z'
                                       '&start=2027-03-03T09%3A30%3A00Z&end=2027-03-03T10%3A00%3A00Z'), task_params(sk)[-1]
        after = {c: int(m.opt('EvBg%d' % i, 'Y')) for c, i in event_meters(sk, 'Daily').items()}
        assert after[2] > before[2] and all(after[c] == before[c] for c in (0, 1, 3, 4)), (before, after)
        m.measure_values['MeasureTaskAction'] = 'OK'
        g.TaskResult()
        # The feed gets the modified occurrence: shown once, where Google has it
        add_event(sk, 1, 'BEGIN:VEVENT\nUID:rec@google.com\nRECURRENCE-ID:20270303T090000Z\n'
                         'DTSTART:20270303T093000Z\nDTEND:20270303T100000Z\nSUMMARY:Daily\nEND:VEVENT\n')
        g.Reload(1)
        assert sorted(event_meters(sk, 'Daily')) == [0, 1, 2, 3, 4]
        assert int(m.opt('EvBg%d' % event_meters(sk, 'Daily')[2], 'Y')) == after[2]
        # An all-day event over two days keeps its length
        open_card(sk, 'ADBg%d' % sk.all_day()['Gita'])
        g.ItemEdit()
        g.CreateAdjust('date', -1)
        g.ItemSave()
        assert task_params(sk)[-1].endswith('?action=editevent&cal=me%40example.com&uid=trip%40google.com'
                                            '&date=2027-03-03&days=2')
        sk.check_clean()
    finally:
        sk.close()


def test_google_script_create_edit_delete():
    node = shutil.which('node')
    if not node:
        print('      (skipped: node not installed)')
        return
    import json
    import subprocess
    script = open(os.path.join(ROOT, 'tools', 'GoogleTasksFeed.gs'), encoding='utf-8').read()
    harness = script + r"""
var TOKEN = null, calls = [];
var PropertiesService = { getScriptProperties: function () { return { getProperty: function () { return TOKEN; } }; } };
var ContentService = { MimeType: { ICAL: 'ical' }, createTextOutput: function (s) {
  return { text: s, setMimeType: function () { return this; } }; } };
var Tasks = { Tasks: {
  insert: function (res, list) { calls.push(['tinsert', res, list]); return { id: 'T1' }; },
  patch: function (res, list, task) { calls.push(['tpatch', res, list, task]); },
  remove: function (list, task) { if (task === 'missing') throw new Error('Not Found'); calls.push(['tremove', list, task]); } } };
var EVENTS = {
  'abc@google.com': [{ id: 'abc', iCalUID: 'abc@google.com', start: { dateTime: '2027-03-03T10:00:00Z' } }],
  'CSVConvert123': [{ id: 'imp1', iCalUID: 'CSVConvert123' }],
  'rec@google.com': [{ id: 'rec_x', recurringEventId: 'rec', iCalUID: 'rec@google.com' },
                     { id: 'rec', iCalUID: 'rec@google.com', recurrence: ['RRULE:FREQ=DAILY'],
                       start: { dateTime: '2027-03-01T10:00:00+01:00', timeZone: 'Europe/Rome' },
                       end: { dateTime: '2027-03-01T10:30:00+01:00', timeZone: 'Europe/Rome' } }],
  'day@google.com': [{ id: 'dayrec', iCalUID: 'day@google.com', recurrence: ['RRULE:FREQ=WEEKLY'] }]
};
var INSTANCES = {
  rec: [{ id: 'rec_20270303T090000Z', originalStartTime: { dateTime: '2027-03-03T10:00:00+01:00' },
         start: { dateTime: '2027-03-03T10:00:00+01:00' } },
        { id: 'rec_20270304T090000Z', originalStartTime: { dateTime: '2027-03-04T10:00:00+01:00' } }],
  dayrec: [{ id: 'dayrec_20270305', originalStartTime: { date: '2027-03-05' }, start: { date: '2027-03-05' } }]
};
var Calendar = { Events: {
  insert: function (res, cal) {
    calls.push(['insert', res, cal]);
    if (cal === 'nope') throw new Error('Not Found');
    return { id: 'new1', iCalUID: 'new1@google.com' }; },
  list: function (cal, a) { calls.push(['list', cal, a]); return { items: EVENTS[a.iCalUID] || [] }; },
  instances: function (cal, id, a) {
    calls.push(['instances', cal, id, a]);
    if (a.originalStart && id === 'rec') throw new Error('Invalid value');
    return { items: INSTANCES[id] || [] }; },
  patch: function (res, cal, id) { calls.push(['patch', res, cal, id]); },
  remove: function (cal, id) { calls.push(['remove', cal, id]); } } };
function w(p) { var n = calls.length; var r = doGet({ parameter: p }).text; return [r, calls.slice(n)]; }
var C = 'me@example.com';
var out = {
  task: w({ action: 'createtask', list: '@default', title: 'Esame', due: '2027-03-05' }),
  taskNoTitle: w({ action: 'createtask', list: '@default', title: '', due: '2027-03-05' }),
  taskBadDate: w({ action: 'createtask', title: 'X', due: '5/3/2027' }),
  ev: w({ action: 'createevent', cal: '', title: 'Cena', start: '2027-03-03T18:00:00Z', end: '2027-03-03T19:00:00Z' }),
  evAllDay: w({ action: 'createevent', cal: C, title: 'Gita', date: '2027-03-04', days: '2' }),
  evBackwards: w({ action: 'createevent', title: 'X', start: '2027-03-03T19:00:00Z', end: '2027-03-03T18:00:00Z' }),
  evNoTime: w({ action: 'createevent', title: 'X' }),
  evNoCal: w({ action: 'createevent', cal: 'nope', title: 'X', start: '2027-03-03T18:00:00Z', end: '2027-03-03T19:00:00Z' }),
  editTask: w({ action: 'edittask', list: 'L1', task: 't1', title: 'Nuovo', due: '2027-03-06' }),
  delTask: w({ action: 'deletetask', list: 'L1', task: 't1' }),
  delTaskMissing: w({ action: 'deletetask', list: 'L1', task: 'missing' }),
  delImported: w({ action: 'deleteevent', cal: C, uid: 'CSVConvert123', scope: 'one' }),
  delOcc: w({ action: 'deleteevent', cal: C, uid: 'rec@google.com', orig: '2027-03-04T09:00:00Z', scope: 'one' }),
  delAll: w({ action: 'deleteevent', cal: C, uid: 'rec@google.com', orig: '2027-03-04T09:00:00Z', scope: 'all' }),
  editOcc: w({ action: 'editevent', cal: C, uid: 'rec@google.com', orig: '2027-03-03T09:00:00Z', title: 'Daily',
               start: '2027-03-03T09:30:00Z', end: '2027-03-03T10:00:00Z' }),
  moveDay: w({ action: 'moveevent', cal: C, uid: 'day@google.com', orig: '2027-03-05', date: '2027-03-06', days: '1' }),
  moveOne: w({ action: 'moveevent', cal: C, uid: 'abc@google.com', start: '2027-03-05T10:00:00Z', end: '2027-03-05T11:00:00Z' }),
  missing: w({ action: 'deleteevent', cal: C, uid: 'gone@google.com', scope: 'one' }),
  noOcc: w({ action: 'deleteevent', cal: C, uid: 'rec@google.com', orig: '2027-03-09T09:00:00Z', scope: 'one' })
};
TOKEN = 's3cret';
out.badToken = w({ action: 'deletetask', list: 'L1', task: 't1', token: 'wrong' });
out.noToken = w({ action: 'complete', list: 'L1', task: 't1' });
out.goodToken = w({ action: 'deletetask', list: 'L1', task: 't1', token: 's3cret' });
process.stdout.write(JSON.stringify(out));
"""
    res = subprocess.run([node, '-e', harness], capture_output=True, encoding='utf-8')
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert out['task'] == ['OK T1', [['tinsert', {'title': 'Esame', 'due': '2027-03-05T00:00:00.000Z'}, '@default']]], out['task']
    assert out['taskNoTitle'] == ['ERROR bad title', []] and out['taskBadDate'] == ['ERROR bad date', []]
    assert out['ev'] == ['OK new1@google.com', [['insert', {'summary': 'Cena', 'start': {'dateTime': '2027-03-03T18:00:00Z'},
                                                            'end': {'dateTime': '2027-03-03T19:00:00Z'}}, 'primary']]], out['ev']
    assert out['evAllDay'][1] == [['insert', {'summary': 'Gita', 'start': {'date': '2027-03-04'},
                                              'end': {'date': '2027-03-06'}}, 'me@example.com']], out['evAllDay']
    assert out['evBackwards'] == ['ERROR end before start', []] and out['evNoTime'] == ['ERROR bad time', []]
    assert out['evNoCal'][0] == 'ERROR calendar not found'
    assert out['editTask'] == ['OK', [['tpatch', {'title': 'Nuovo', 'due': '2027-03-06T00:00:00.000Z'}, 'L1', 't1']]]
    assert out['delTask'] == ['OK', [['tremove', 'L1', 't1']]] and out['delTaskMissing'][0] == 'ERROR Not Found'
    # Found by iCal UID, whatever Google's own id is
    assert out['delImported'][0] == 'OK' and out['delImported'][1][-1] == ['remove', 'me@example.com', 'imp1']
    assert out['delImported'][1][0] == ['list', 'me@example.com', {'iCalUID': 'CSVConvert123', 'showDeleted': False, 'maxResults': 5}]
    # One occurrence: matched by its original start (here the API refuses originalStart: a search)
    assert out['delOcc'][0] == 'OK' and out['delOcc'][1][-1] == ['remove', 'me@example.com', 'rec_20270304T090000Z'], out['delOcc']
    assert out['delAll'][0] == 'OK' and out['delAll'][1][-1] == ['remove', 'me@example.com', 'rec'], out['delAll']
    assert out['editOcc'][0] == 'OK' and out['editOcc'][1][-1] == [
        'patch', {'summary': 'Daily', 'start': {'dateTime': '2027-03-03T09:30:00Z'}, 'end': {'dateTime': '2027-03-03T10:00:00Z'}},
        'me@example.com', 'rec_20270303T090000Z'], out['editOcc']
    assert out['moveDay'][0] == 'OK' and out['moveDay'][1][-1] == [
        'patch', {'start': {'date': '2027-03-06'}, 'end': {'date': '2027-03-07'}}, 'me@example.com', 'dayrec_20270305'], out['moveDay']
    assert out['moveDay'][1][1][3] == {'originalStart': '2027-03-05', 'showDeleted': False}
    assert out['moveOne'][1][-1] == ['patch', {'start': {'dateTime': '2027-03-05T10:00:00Z'},
                                               'end': {'dateTime': '2027-03-05T11:00:00Z'}}, 'me@example.com', 'abc']
    assert out['missing'] == ['ERROR event not found', [['list', 'me@example.com',
                                                         {'iCalUID': 'gone@google.com', 'showDeleted': False, 'maxResults': 5}]]]
    assert out['noOcc'][0] == 'ERROR occurrence not found', out['noOcc']
    assert out['badToken'] == ['ERROR bad token', []] and out['noToken'] == ['ERROR bad token', []]
    assert out['goodToken'] == ['OK', [['tremove', 'L1', 't1']]]


# ---------------------------------------------------------------------------
# Dragging an event to another time or day
# ---------------------------------------------------------------------------
def slot_of(sk, clock):
    """Strip index of a time like '10:45' (08:00 is the first visible hour)."""
    h, mi = (int(x) for x in clock.split(':'))
    return (h * 60 + mi - 8 * 60) // 15 + 1


def test_drag_event_actions_and_click():
    sk = edit_skin(IcalUrl2=HOLIDAY_URL)
    try:
        m, g = sk.mock, sk.g
        i = event_meter(sk, 'Lezione')
        assert m.opt('EvBg%d' % i, 'LeftMouseDownAction') == '[!CommandMeasure MeasureScript "DragEvent(%d, $MouseY$+0, $MouseX$+0)"]' % i
        assert m.opt('EvT%d' % i, 'LeftMouseDownAction') == '[!CommandMeasure MeasureScript "DragEvent(%d, $MouseY$+5, $MouseX$+8)"]' % i
        for meter in ('EvBg%d' % i, 'EvT%d' % i):
            assert m.opt(meter, 'LeftMouseUpAction') == '' and m.opt(meter, 'MouseActionCursorName') == 'SizeAll'
        # Read-only events keep their click and the harmless press
        j = event_meter(sk, 'Invito')
        assert m.opt('EvBg%d' % j, 'LeftMouseDownAction') == NO_DRAG
        assert m.opt('EvBg%d' % j, 'LeftMouseUpAction').startswith('["https://')
        assert m.opt('EvBg%d' % j, 'MouseActionCursorName') == 'Hand'
        assert 'Drag' not in sk.tip('EvBg%d' % j)
        # The strips: one per 15 minutes of the visible hours, placed by the layout
        ys = hour_y(sk)
        assert int(m.opt('DragSlot1', 'Y')) == ys['08:00'] and int(m.opt('DragSlot5', 'Y')) == ys['09:00']
        assert m.opt('DragSlot48', 'H') is not None and m.opt('DragSlot49', 'H') is None
        assert not any(m.shown('DragSlot%d' % k) for k in range(1, 97))
        # A click: pressed and released where it was
        start = slot_of(sk, clock_of(utc(2027, 3, 3, 10)))
        g.DragEvent(i, 10)
        assert m.shown('DragArea') and m.shown('DragSlot1') and m.shown('DragSlot48')
        assert m.opt('DragSlot1', 'X') == str(int(64 + 2 * DAY_W + 0.5))
        m.bangs.clear()
        g.DragSlot(start)
        g.DragSlotDrop(start)
        assert ['["%s"]' % eid_link('abc123')] in m.bangs, m.bangs
        assert not task_params(sk) and not any(m.shown(d) for d in DRAG_METERS + ['DragSlot1'])
        sk.check_clean()
    finally:
        sk.close()


def test_drag_event_to_another_time_and_day():
    sk = edit_skin()
    try:
        m, g = sk.mock, sk.g
        i = event_meter(sk, 'Lezione')                # Wednesday, one hour
        s0 = clock_of(utc(2027, 3, 3, 10))
        h0 = int(s0[:2])
        shape = m.opt('EvBg%d' % i, 'Shape')
        g.DragEvent(i, 0)                             # grabbed at its top
        g.DragOver(4)                                 # Friday: the strips move there
        assert m.opt('DragSlot1', 'X') == str(int(64 + 4 * DAY_W + 0.5))
        k = slot_of(sk, '%02d:45' % (h0 + 1))
        g.DragSlot(k)
        assert m.shown('DragPrev') and m.opt('DragPrev', 'X') == str(int(64 + 4 * DAY_W + 0.5) + 4)
        assert m.opt('DragPrevTx', 'Text').startswith('%02d:45 - %02d:45' % (h0 + 1, h0 + 2)), m.opt('DragPrevTx', 'Text')
        assert m.opt('TbSync', 'Text') == 'Move to Fri 5, %02d:45' % (h0 + 1)
        assert m.opt('EvBg%d' % i, 'Shape') != shape        # the event fades
        ys = hour_y(sk)
        assert abs(int(m.opt('DragPrev', 'Y')) - (ys['%02d:00' % (h0 + 1)] + (ys['%02d:00' % (h0 + 2)] - ys['%02d:00' % (h0 + 1)]) * 3 / 4)) <= 2
        g.DragSlotDrop(k)
        assert task_params(sk) == ['-s -f -L -m 30 ' + SCRIPT_URL + '?action=moveevent&cal=me%40example.com'
                                   '&uid=abc123%40google.com&start=' + enc(utc_of_local(2027, 3, 5, h0 + 1, 45))
                                   + '&end=' + enc(utc_of_local(2027, 3, 5, h0 + 2, 45))], task_params(sk)
        assert list(event_meters(sk, 'Lezione')) == [4] and not m.shown('DragPrev')
        assert 'Move to' not in m.opt('TbSync', 'Text')
        # Saved: it stays there while Google's feed still has the old time
        m.measure_values['MeasureTaskAction'] = 'OK'
        g.TaskResult()
        g.Reload(1)
        assert list(event_meters(sk, 'Lezione')) == [4]
        # Moved again, Google refuses: back to Friday (the saved move)
        i = event_meters(sk, 'Lezione')[4]
        g.DragEvent(i, 0)
        g.DragOver(1)
        g.DragSlot(slot_of(sk, '09:00'))
        g.DragSlotDrop(slot_of(sk, '09:00'))
        assert list(event_meters(sk, 'Lezione')) == [1]
        m.measure_values['MeasureTaskAction'] = 'ERROR Forbidden'
        g.TaskResult()
        assert list(event_meters(sk, 'Lezione')) == [4], event_meters(sk, 'Lezione')
        sk.check_clean()
    finally:
        sk.close()


def test_drag_event_small_slip_is_a_click():
    sk = edit_skin()
    try:
        m, g = sk.mock, sk.g
        i = event_meter(sk, 'Lezione')                # Wednesday, column 2
        top, left = int(m.opt('EvBg%d' % i, 'Y')), int(m.opt('EvBg%d' % i, 'X'))

        def slot_y(k):
            return int(m.opt('DragSlot%d' % k, 'Y'))
        start = slot_of(sk, clock_of(utc(2027, 3, 3, 10)))
        h0 = int(clock_of(utc(2027, 3, 3, 10))[:2])
        # Pressed one pixel above the next strip: slipping over its edge is not a move
        edge = slot_y(start + 1)
        g.DragEvent(i, edge - 1 - top, 20)
        g.DragSlot(start + 1)
        assert not m.shown('DragPrev') and 'Move to' not in m.opt('TbSync', 'Text')
        m.bangs.clear()
        g.DragSlotDrop(start + 1, 20, 2)              # released 3 px lower: a click
        assert ['["%s"]' % eid_link('abc123')] in m.bangs and not task_params(sk)
        # 6 px lower is a move (15 minutes)
        g.DragEvent(i, edge - 1 - top, 20)
        g.DragSlotDrop(start + 1, 20, 5)
        assert 'moveevent' in task_params(sk)[-1] and 'start=' + enc(utc_of_local(2027, 3, 3, h0, 15)) in task_params(sk)[-1]
        m.measure_values['MeasureTaskAction'] = 'OK'
        g.TaskResult()
        # Pressed 3 px from the column's right edge: just across it is still home...
        i = event_meter(sk, 'Lezione')
        top, left = int(m.opt('EvBg%d' % i, 'Y')), int(m.opt('EvBg%d' % i, 'X'))
        k = slot_of(sk, '%02d:15' % h0)
        col_edge = int(m.opt('DragZone3', 'X'))
        g.DragEvent(i, slot_y(k) + 4 - top, col_edge - 3 - left)
        g.DragOver(3)
        g.DragSlot(k)
        assert not m.shown('DragPrev')
        m.bangs.clear()
        g.DragSlotDrop(k, 1, 4)                       # 4 px right: a click
        assert not task_params(sk) and any(b[0].startswith('["https://calendar.google.com') for b in m.bangs)
        # ...7 px across moves it to Thursday at the same time
        g.DragEvent(i, slot_y(k) + 4 - top, col_edge - 3 - left)
        g.DragOver(3)
        g.DragSlotDrop(k, 4, 4)
        assert 'start=' + enc(utc_of_local(2027, 3, 4, h0, 15)) in task_params(sk)[-1], task_params(sk)[-1]
        sk.check_clean()
    finally:
        sk.close()


def test_drag_event_grab_clamp_and_cancel():
    sk = edit_skin()
    try:
        m, g = sk.mock, sk.g
        i = event_meters(sk, 'Daily')[2]              # 30 minutes on Wednesday
        h = int(m.opt('EvBg%d' % i, 'H'))
        hour = (hour_y(sk)['10:00'] - hour_y(sk)['09:00'])
        # Grabbed 15 minutes into it (the lower half): the slot under the cursor is its second quarter
        g.DragEvent(i, round(hour / 4) + 2)
        assert h > 0
        k = slot_of(sk, '14:00')
        g.DragSlot(k)
        assert m.opt('DragPrevTx', 'Text').startswith('13:45 - 14:15'), m.opt('DragPrevTx', 'Text')
        # Never before 00:00 (the first strip, grabbed lower) nor after 24:00
        g.DragSlot(1)
        assert m.opt('DragPrevTx', 'Text').startswith('07:45 - 08:15'), m.opt('DragPrevTx', 'Text')
        # Back home: nothing to save; a right click cancels
        g.DragCancel(1)
        g.DragCancel()
        assert not m.shown('DragPrev') and not any(m.shown('DragSlot%d' % k) for k in range(1, 97))
        assert not task_params(sk) and sorted(event_meters(sk, 'Daily')) == [0, 1, 2, 3, 4]
        # Released on the day header (a zone, not a strip): back where it was
        g.DragEvent(i, 0)
        g.DragSlot(slot_of(sk, '12:00'))
        g.DragDrop(2)
        assert not task_params(sk) and not m.shown('DragArea')
        # One occurrence of a recurring event: only that one moves, with its original start
        g.DragEvent(i, 0)
        g.DragSlot(slot_of(sk, '12:00'))
        g.DragSlotDrop(slot_of(sk, '12:00'))
        assert task_params(sk)[-1] == ('-s -f -L -m 30 ' + SCRIPT_URL + '?action=moveevent&cal=me%40example.com'
                                       '&uid=rec%40google.com&orig=2027-03-03T09%3A00%3A00Z'
                                       '&start=' + enc(utc_of_local(2027, 3, 3, 12)) + '&end=' + enc(utc_of_local(2027, 3, 3, 12, 30)))
        ys = {c: int(m.opt('EvBg%d' % j, 'Y')) for c, j in event_meters(sk, 'Daily').items()}
        assert ys[2] > ys[1] and ys[0] == ys[1] == ys[3] == ys[4], ys
        # Late in the day: the end stops at 24:00
        g.ScrollToHour(12)
        assert int(m.opt('DragSlot1', 'Y')) == hour_y(sk)['12:00']
        g.DragEvent(event_meters(sk, 'Daily')[2], 0)
        g.DragSlot(48)                                # 23:45
        assert m.opt('DragPrevTx', 'Text').startswith('23:30 - 24:00'), m.opt('DragPrevTx', 'Text')
        g.DragCancel()
        sk.check_clean()
    finally:
        sk.close()
    # A DST day: 10:00 local on the last Sunday of March is UTC+2 in Europe
    sk = edit_skin()
    try:
        m, g = sk.mock, sk.g
        g.ShiftWeek(4)                                # 29 Mar - 4 Apr 2027... DST began on 28 Mar
        g.ShiftWeek(-1)                               # 22 - 28 Mar: Sunday 28 is the change
        ics = EDIT_ICS.replace('END:VCALENDAR\r\n', 'BEGIN:VEVENT\r\nUID:dst@google.com\r\nDTSTART:20270327T090000Z\r\n'
                               'DTEND:20270327T100000Z\r\nSUMMARY:Sabato\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')
        open(os.path.join(sk.dir, 'DownloadFile', 'calendar1.ics'), 'w', encoding='utf-8', newline='').write(ics)
        g.Reload(1)
        i = event_meter(sk, 'Sabato')
        h0 = int(clock_of(utc(2027, 3, 27, 9))[:2])
        g.DragEvent(i, 0)
        g.DragOver(6)
        g.DragSlot(slot_of(sk, '%02d:00' % h0))
        g.DragSlotDrop(slot_of(sk, '%02d:00' % h0))
        assert task_params(sk)[-1].endswith('&start=' + enc(utc_of_local(2027, 3, 28, h0)) + '&end='
                                            + enc(utc_of_local(2027, 3, 28, h0 + 1))), task_params(sk)[-1]
        sk.check_clean()
    finally:
        sk.close()


def test_drag_all_day_event_and_month_lines():
    sk = edit_skin()
    try:
        m, g = sk.mock, sk.g
        # An all-day event over two days: a chip per day; dragged by its second day, it moves as much
        chips = [j for j in range(1, 71) if m.shown('ADTx%d' % j) and m.opt('ADTx%d' % j, 'Text') == 'Gita']
        assert [chip_col(sk, j) for j in chips] == [3, 4]
        j = chips[1]
        assert m.opt('ADBg%d' % j, 'LeftMouseDownAction') == '[!CommandMeasure MeasureScript "DragStart(%d)"]' % j
        g.DragStart(j)
        g.DragOver(6)
        g.DragDrop(6)
        assert task_params(sk)[-1].endswith('?action=moveevent&cal=me%40example.com&uid=trip%40google.com&date=2027-03-06&days=2')
        assert sorted(chip_col(sk, k) for k in range(1, 71) if m.shown('ADTx%d' % k) and m.opt('ADTx%d' % k, 'Text') == 'Gita') == [5, 6]
        m.measure_values['MeasureTaskAction'] = 'OK'
        g.TaskResult()
        # Month view: a timed line to another day keeps its time
        g.SetView('month')
        line = [l for l in month_lines(sk) if l[1].endswith('Lezione')][0]
        k = int(line[2][3:])
        assert m.opt(line[2], 'LeftMouseDownAction') == '[!CommandMeasure MeasureScript "DragStart(%d)"]' % k
        assert sk.tip(line[2]).endswith('#CRLF#Drag to another day to move it')
        g.DragStart(k)
        g.DragOver(line[0] - 1 + 7)                   # a week later
        g.DragDrop(line[0] - 1 + 7)
        assert task_params(sk)[-1].endswith('&uid=abc123%40google.com&start=2027-03-10T10%3A00%3A00Z&end=2027-03-10T11%3A00%3A00Z'), task_params(sk)[-1]
        assert [l[0] for l in month_lines(sk) if l[1].endswith('Lezione')] == [line[0] + 7]
        # Read-only events cannot be dragged in the month view either
        inv = [l for l in month_lines(sk) if l[1].endswith('Invito')][0]
        assert m.opt(inv[2], 'LeftMouseDownAction') == NO_DRAG
        sk.check_clean()
    finally:
        sk.close()


def test_google_script_moveevent_errors():
    node = shutil.which('node')
    if not node:
        print('      (skipped: node not installed)')
        return
    import json
    import subprocess
    script = open(os.path.join(ROOT, 'tools', 'GoogleTasksFeed.gs'), encoding='utf-8').read()
    harness = script + r"""
var PropertiesService = { getScriptProperties: function () { return { getProperty: function () { return null; } }; } };
var ContentService = { createTextOutput: function (s) { return { text: s }; } };
var Calendar = { Events: {
  list: function (cal, a) { return { items: a.iCalUID === 'x@google.com' ? [{ id: 'x' }] : [] }; },
  patch: function (res, cal, id) { if (cal === 'ro@example.com') throw new Error('Forbidden'); } } };
function w(p) { p.action = 'moveevent'; return doGet({ parameter: p }).text; }
process.stdout.write(JSON.stringify([
  w({ cal: 'me@example.com', uid: 'x@google.com', start: '2027-03-05T10:00:00Z', end: '2027-03-05T11:00:00Z' }),
  w({ cal: 'ro@example.com', uid: 'x@google.com', start: '2027-03-05T10:00:00Z', end: '2027-03-05T11:00:00Z' }),
  w({ cal: 'me@example.com', uid: 'y@google.com', start: '2027-03-05T10:00:00Z', end: '2027-03-05T11:00:00Z' }),
  w({ cal: 'me@example.com', uid: 'x@google.com', start: '2027-03-05 10:00', end: '2027-03-05T11:00:00Z' }),
  w({ cal: 'me@example.com', uid: 'x@google.com', date: '2027-03-05', days: '0' }),
  w({ cal: 'me@example.com' })
]));
"""
    res = subprocess.run([node, '-e', harness], capture_output=True, encoding='utf-8')
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == ['OK', 'ERROR Forbidden', 'ERROR event not found', 'ERROR bad time',
                                      'ERROR bad date', 'ERROR missing uid'], res.stdout


# ---------------------------------------------------------------------------
# Task lists, details; places, descriptions, repeats, calendars (Tasks script 2)
# ---------------------------------------------------------------------------
ARROW = ' \u25be'  # after the choice of a picker


def set_feed(sk, feed, text):
    # A new download of feed (its .ics text), as WebParser would finish it
    open(os.path.join(sk.dir, 'DownloadFile', 'calendar%d.ics' % feed), 'w', encoding='utf-8', newline='').write(text)
    sk.g.Reload(feed)


def answer(sk, out):
    # The Tasks script answers the request being sent ("OK ...", "ERROR ...")
    sk.mock.measure_values['MeasureTaskAction'] = out
    sk.g.TaskResult()


def test_old_script_hides_the_new_fields():
    sk = edit_skin()
    try:
        m, g = sk.mock, sk.g
        g.CreateAllDay(4)
        texts = card_texts(sk)
        assert 'My Tasks' in texts and 'Add details' not in texts, texts
        assert any(t.startswith('For lists, details, places and repeats, update the') for t in texts), texts
        g.CreateType('event')
        assert 'Add location' not in card_texts(sk) and 'Does not repeat' + ARROW not in card_texts(sk)
        g.CardClose()
        open_card(sk, 'EvBg%d' % event_meter(sk, 'Mia riunione'))
        g.ItemEdit()
        assert 'Add location' not in card_texts(sk) and 'All day' not in card_texts(sk)
        sk.check_clean()
    finally:
        sk.close()


def test_task_lists_details_and_moves():
    sk = edit_skin(tasks='tasks_v2.ics')
    try:
        m, g = sk.mock, sk.g
        v2 = open(os.path.join(FIXTURES, 'tasks_v2.ics'), encoding='utf-8').read()
        # Details: its list and its notes
        texts = open_card(sk, 'ADBg%d' % task_chip(sk))
        assert texts[1] == 'Wed 3 Mar#CRLF#Task · Le mie attività' and 'capitolo 4#CRLF#esercizi' in texts, texts
        g.CardClose()

        # A new task: its list (the default one first) and details
        g.CreateAllDay(4)
        texts = card_texts(sk)
        assert 'Add details' in texts and 'Le mie attività' + ARROW in texts, texts
        assert not any('update the' in t for t in texts)
        el = card_el(sk, 'Le mie attività' + ARROW)
        assert sk.tip(el) == 'Click to choose, scroll to change'
        run_action(sk, m.opt(el, 'LeftMouseUpAction'))
        texts = card_texts(sk)
        assert texts[:4] == ['Task list', 'Le mie attività', 'Analisi Matematica 1 - 1° Parziale', 'Sport, palestra'], texts
        assert 'Cancel' in texts and m.opt(card_el(sk, 'Le mie attività'), 'FontColor') == '4,30,73,255'
        run_action(sk, m.opt(card_el(sk, 'Sport, palestra'), 'LeftMouseUpAction'))
        assert 'Sport, palestra' + ARROW in card_texts(sk)
        assert m.bangs.count(['!CommandMeasure', 'MeasureCreateInput', 'ExecuteBatch 1']) >= 2  # title again
        run_action(sk, m.opt(card_el(sk, 'Sport, palestra' + ARROW), 'MouseScrollUpAction'))  # the wheel
        assert 'Analisi Matematica 1 - 1° Parziale' + ARROW in card_texts(sk)
        # Details: a smaller box, two lines tall; Ctrl+Enter lines arrive as CR LF
        run_action(sk, m.opt(card_el(sk, 'Add details'), 'LeftMouseUpAction'))
        assert m.opt('MeasureCreateInput', 'FontSize') == '9' and m.opt('MeasureCreateInput', 'DefaultValue') == ''
        assert m.opt('MeasureCreateInput', 'H') == '44' and m.opt('MeasureCreateInput', 'InputLimit') == '1500'
        assert 'Enter: done - Ctrl+Enter: new line' in card_texts(sk)
        m.vars['CreateTitle'] = ' riga 1\r\nriga \\"2\\" '      # Rainmeter gives a typed " as \"
        g.CreateSubmit()
        assert "riga 1 riga '2'" in card_texts(sk) and 'Add details' not in card_texts(sk)
        g.CardTitle()
        assert m.opt('MeasureCreateInput', 'FontSize') == '13' and m.opt('MeasureCreateInput', 'InputLimit') == '500'
        m.vars['CreateTitle'] = 'Consegna'
        g.CreateSubmit()
        assert task_params(sk)[-1] == ('-s -f -L -m 30 ' + SCRIPT_URL + '?action=createtask&list=L2&title=Consegna'
                                       '&due=2027-03-05&notes=riga%201%0Ariga%20%222%22'), task_params(sk)[-1]
        assert chip_col(sk, sk.all_day()['○ Consegna']) == 4
        answer(sk, 'OK newtask1')

        # Edit a task: new details and another list; details show the list at once
        open_card(sk, 'ADBg%d' % task_chip(sk))
        g.ItemEdit()
        texts = card_texts(sk)
        assert 'capitolo 4 esercizi' in texts and 'Le mie attività' + ARROW in texts, texts
        g.CardCycle('list', 2)
        assert 'Sport, palestra' + ARROW in card_texts(sk)
        g.CardField('notes')
        assert m.opt('MeasureCreateInput', 'DefaultValue') == 'capitolo 4\r\nesercizi'
        m.vars['CreateTitle'] = 'capitolo 4\r\nesercizi'            # Enter without changes
        g.CreateSubmit()
        g.CardField('notes')
        m.vars['CreateTitle'] = 'capitolo 5'
        g.CreateSubmit()
        n = len(task_params(sk))
        g.ItemSave()
        assert task_params(sk)[n:] == ['-s -f -L -m 30 ' + SCRIPT_URL + '?action=edittask&list=L1&task=t-open'
                                       '&notes=capitolo%205'], task_params(sk)[n:]
        texts = open_card(sk, 'ADBg%d' % task_chip(sk))
        assert texts[1] == 'Wed 3 Mar#CRLF#Task · Sport, palestra' and 'capitolo 5' in texts, texts
        g.CardClose()
        answer(sk, 'OK')
        # then the move to the other list; Google gives it a new id there
        assert task_params(sk)[-1] == '-s -f -L -m 30 ' + SCRIPT_URL + '?action=movetask&list=L1&task=t-open&tolist=L3'
        answer(sk, 'OK t-new')
        # a change after the move goes to the task where it is now
        g.ToggleTask(task_chip(sk))
        assert task_params(sk)[-1] == '-s -f -L -m 30 ' + SCRIPT_URL + '?action=complete&list=L3&task=t-new'
        answer(sk, 'OK')
        assert sk.all_day().get('✓ Simulazione Tema di Esame')
        # A download that started before Google saved it (the old task) does not undo it
        set_feed(sk, 3, v2.replace('DTSTAMP:20270301T080000Z', 'DTSTAMP:20270301T090000Z'))
        assert '✓ Simulazione Tema di Esame' in sk.all_day()
        texts = open_card(sk, 'ADBg%d' % task_chip(sk, '✓ Simulazione'))
        assert texts[1] == 'Wed 3 Mar#CRLF#Task completed · Sport, palestra', texts
        g.CardClose()
        # The feed has it in the new list, with its new id: shown once
        moved = v2.replace('UID:t-open@', 'UID:t-new@').replace('X-WC-TASKID:t-open', 'X-WC-TASKID:t-new') \
                  .replace('X-WC-TASKLIST:L1', 'X-WC-TASKLIST:L3').replace('X-WC-TASK:NEEDS-ACTION\nX-WC-TASKLIST:L3\nX-WC-TASKID:t-new',
                                                                          'X-WC-TASK:COMPLETED\nX-WC-TASKLIST:L3\nX-WC-TASKID:t-new') \
                  .replace('DESCRIPTION:capitolo 4\\nesercizi', 'DESCRIPTION:capitolo 5')
        assert 'X-WC-TASK:COMPLETED' in moved
        set_feed(sk, 3, moved)
        assert [k for k in sk.all_day() if 'Simulazione' in k] == ['✓ Simulazione Tema di Esame'], sk.all_day()
        assert not g._WC.edit.card
        sk.check_clean()

        # Google refuses a move (a repeating task): the list goes back, the toolbar says why
        open_card(sk, 'ADBg%d' % task_chip(sk, '○ Ritirare'))
        g.ItemEdit()
        g.CardCycle('list', -1)
        g.ItemSave()
        assert task_params(sk)[-1].endswith('?action=movetask&list=L3&task=t-sport&tolist=L2')
        answer(sk, 'ERROR Recurrent tasks cannot currently be moved between lists')
        assert m.opt('TbSync', 'Text').endswith('task not saved') and 'Recurrent tasks' in sk.tip('TbSync')
        texts = open_card(sk, 'ADBg%d' % task_chip(sk, '○ Ritirare'))
        assert texts[1] == 'Thu 4 Mar#CRLF#Task · Sport, palestra', texts
        g.CardClose()
        # A change Google saved but the feed never shows ends after 10 minutes
        open_card(sk, 'ADBg%d' % task_chip(sk, '○ Ritirare'))
        g.ItemEdit()
        m.vars['CreateTitle'] = 'Ritirare il pacco'
        g.CreateSubmit()
        answer(sk, 'OK')
        set_feed(sk, 3, moved.replace('DTSTAMP:20270301T080000Z', 'DTSTAMP:20270301T100000Z'))
        assert '○ Ritirare il pacco' in sk.all_day()
        sk.at(2027, 3, 3, 8, 11)
        set_feed(sk, 3, moved)
        assert '○ Ritirare oggetti' in sk.all_day()
        sk.check_clean()
    finally:
        sk.close()


FAMILY_URL = 'https://calendar.google.com/calendar/ical/family123%40group.calendar.google.com/private-y/basic.ics'
FAMILY_ICS = 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nX-WR-CALNAME:Famiglia\r\nEND:VCALENDAR\r\n'


def test_event_place_description_repeat_and_calendar():
    sk = edit_skin(tasks='tasks_v2.ics', IcalUrl2=FAMILY_URL)
    try:
        m, g = sk.mock, sk.g
        set_feed(sk, 2, FAMILY_ICS)
        g.CreateAt(2, zone_y(sk, 2, '16:00'))
        texts = card_texts(sk)
        for t in ('Does not repeat' + ARROW, 'Add location', 'Add description', 'me@example.com' + ARROW, 'More options'):
            assert t in texts, (t, texts)
        g.CardMenu('repeat')
        texts = card_texts(sk)
        assert texts[:7] == ['Repeat', 'Does not repeat', 'Every day', 'Every weekday (Monday to Friday)',
                             'Weekly on Wednesday', 'Monthly on day 3', 'Annually on March 3'], texts
        g.CardPick(4)
        assert 'Weekly on Wednesday' + ARROW in card_texts(sk)
        g.CardField('loc')
        assert m.opt('MeasureCreateInput', 'H') == '24'           # one line for a place
        m.vars['CreateTitle'] = 'Aula 3'
        g.CreateSubmit()
        g.CardField('desc')
        m.vars['CreateTitle'] = 'Portare il libro'
        g.CreateSubmit()
        g.CardMenu('cal')
        assert card_texts(sk)[:3] == ['Calendar', 'me@example.com', 'Famiglia'], card_texts(sk)
        g.CardPick(2)
        assert 'Famiglia' + ARROW in card_texts(sk) and 'Aula 3' in card_texts(sk) and 'Portare il libro' in card_texts(sk)
        assert 'Fill Color 11,128,67,255' in m.opt('CrDraft', 'Shape')        # the color of slot 2
        g.CardTitle()
        m.vars['CreateTitle'] = 'Lezione nuova'
        g.CreateSubmit()
        assert task_params(sk)[-1] == ('-s -f -L -m 30 ' + SCRIPT_URL + '?action=createevent'
                                       '&cal=family123%40group.calendar.google.com&title=Lezione%20nuova'
                                       '&start=' + enc(utc_of_local(2027, 3, 3, 16)) + '&end=' + enc(utc_of_local(2027, 3, 3, 17))
                                       + '&location=Aula%203&desc=Portare%20il%20libro&rrule=FREQ%3DWEEKLY'), task_params(sk)[-1]
        # shown at once, every week, with its place
        assert sorted(event_meters(sk, 'Lezione nuova')) == [2]
        assert 'Aula 3' in sk.tip('EvBg%d' % event_meters(sk, 'Lezione nuova')[2])
        g.ShiftWeek(1)
        assert sorted(event_meters(sk, 'Lezione nuova')) == [2]
        g.ShiftWeek(-1)
        answer(sk, 'OK new1@google.com')
        # "More options" takes them to Google Calendar's editor
        g.CreateAt(3, zone_y(sk, 3, '15:00'))
        g.CardField('loc')
        m.vars['CreateTitle'] = 'Via Roma 1'
        g.CreateSubmit()
        g.CardCycle('repeat', 1)
        m.bangs.clear()
        g.CreateMore()
        url = [b[0] for b in m.bangs if b[0].startswith('["https://')][0]
        assert url.endswith('&location=Via%20Roma%201&recur=RRULE%3AFREQ%3DDAILY"]'), url
        # All day, without a repeat
        g.CreateAllDay(1)
        g.CreateType('event')
        m.vars['CreateTitle'] = 'Gita'
        g.CreateSubmit()
        assert task_params(sk)[-1].endswith('?action=createevent&cal=&title=Gita&date=2027-03-02&days=1'), task_params(sk)[-1]
        sk.check_clean()
    finally:
        sk.close()


def test_edit_event_fields_all_day_and_series():
    sk = edit_skin(tasks='tasks_v2.ics')
    try:
        m, g = sk.mock, sk.g
        # Only the place changes
        open_card(sk, 'EvBg%d' % event_meter(sk, 'Mia riunione'))
        g.ItemEdit()
        texts = card_texts(sk)
        assert 'Add location' in texts and 'Add description' in texts and 'All day' in texts, texts
        g.CardField('loc')
        m.vars['CreateTitle'] = 'Sala B'
        g.CreateSubmit()
        g.ItemSave()
        assert task_params(sk)[-1] == ('-s -f -L -m 30 ' + SCRIPT_URL + '?action=editevent&cal=me%40example.com'
                                       '&uid=mine%40google.com&location=Sala%20B'), task_params(sk)[-1]
        assert 'Sala B' in sk.tip('EvBg%d' % event_meter(sk, 'Mia riunione'))
        answer(sk, 'OK')
        # ...then all day: the place stays shown while the feed catches up
        open_card(sk, 'EvBg%d' % event_meter(sk, 'Mia riunione'))
        g.ItemEdit()
        assert 'Sala B' in card_texts(sk)
        g.CreateToggleAllDay()
        assert not any(re.match(r'\d\d:\d\d$', t) for t in card_texts(sk)), card_texts(sk)
        g.ItemSave()
        assert task_params(sk)[-1].endswith('&uid=mine%40google.com&date=2027-03-05&days=1'), task_params(sk)[-1]
        assert 'Mia riunione' in sk.all_day() and not [t for t in sk.event_titles() if t.startswith('Mia riunione')]
        assert 'Sala B' in sk.tip('ADBg%d' % sk.all_day()['Mia riunione'])
        answer(sk, 'OK')
        # ...and back to a time (9:00 by default)
        open_card(sk, 'ADBg%d' % sk.all_day()['Mia riunione'])
        g.ItemEdit()
        g.CreateToggleAllDay()
        assert '09:00' in card_texts(sk) and '10:00' in card_texts(sk)
        g.ItemSave()
        assert task_params(sk)[-1].endswith('&uid=mine%40google.com&start=' + enc(utc_of_local(2027, 3, 5, 9))
                                            + '&end=' + enc(utc_of_local(2027, 3, 5, 10))), task_params(sk)[-1]
        assert 'Mia riunione' not in sk.all_day()
        answer(sk, 'OK')

        # An event without a title: saved unchanged, nothing is sent (not "(no title)")
        add_event(sk, 1, 'BEGIN:VEVENT\nUID:nt@google.com\nDTSTART:20270305T160000Z\nDTEND:20270305T170000Z\nEND:VEVENT\n')
        g.Reload(1)
        n = len(task_params(sk))
        open_card(sk, 'EvBg%d' % event_meter(sk, '(no title)'))
        g.ItemEdit()
        g.ItemSave()
        assert len(task_params(sk)) == n and not m.shown('CrCard')
        # A rich description (Google Meet block) cannot be edited here
        open_card(sk, 'EvBg%d' % event_meter(sk, 'Lezione'))
        g.ItemEdit()
        el = card_el(sk, [t for t in card_texts(sk) if t.startswith('Aula 3.0.3') or t.startswith("'b'")
                          or t.startswith('(b)') or '<b>' in t or 'Aula' in t][0])
        assert m.opt(el, 'LeftMouseUpAction') in (NO_DRAG, None, '') and sk.tip(el).startswith('Formatted description')
        g.CardClose()

        # A recurring event: this event, or all of them (the same day, a new time)
        before = {c: int(m.opt('EvBg%d' % i, 'Y')) for c, i in event_meters(sk, 'Daily').items()}
        open_card(sk, 'EvBg%d' % event_meters(sk, 'Daily')[2])
        g.ItemEdit()
        assert 'Only this event will change' not in card_texts(sk) and 'All day' not in card_texts(sk)
        g.CreateAdjust('start', 2)
        g.ItemSave()
        texts = card_texts(sk)
        assert 'Save recurring event:' in texts and 'All events' in texts and 'This event' in texts, texts
        g.ItemSaveAsk(0)
        assert 'Save recurring event:' not in card_texts(sk)
        g.ItemSave()
        g.ItemSave('all')
        assert task_params(sk)[-1] == ('-s -f -L -m 30 ' + SCRIPT_URL + '?action=editevent&cal=me%40example.com'
                                       '&uid=rec%40google.com&orig=2027-03-03T09%3A00%3A00Z&scope=all'
                                       '&start=2027-03-03T09%3A30%3A00Z&end=2027-03-03T10%3A00%3A00Z'), task_params(sk)[-1]
        after = {c: int(m.opt('EvBg%d' % i, 'Y')) for c, i in event_meters(sk, 'Daily').items()}
        assert sorted(after) == [0, 1, 2, 3, 4] and all(after[c] > before[c] for c in after), (before, after)
        answer(sk, 'OK')
        # the feed has the series at its new time: shown there once, not moved twice
        path = os.path.join(sk.dir, 'DownloadFile', 'calendar1.ics')
        text = open(path, encoding='utf-8', newline='').read()
        set_feed(sk, 1, text.replace('DTSTART:20270301T090000Z\r\nDTEND:20270301T093000Z',
                                     'DTSTART:20270301T093000Z\r\nDTEND:20270301T100000Z'))
        assert {c: int(m.opt('EvBg%d' % i, 'Y')) for c, i in event_meters(sk, 'Daily').items()} == after
        assert not any(k for k in g._WC.edit.changes.keys() if 'rec@google.com' in k)
        # Another day: only that occurrence can change, and the form says so
        open_card(sk, 'EvBg%d' % event_meters(sk, 'Daily')[1])
        g.ItemEdit()
        g.CreateAdjust('date', 1)
        assert 'Only this event will change' in card_texts(sk)
        g.ItemSave()
        assert task_params(sk)[-1].endswith('&uid=rec%40google.com&orig=2027-03-02T09%3A30%3A00Z'
                                            '&start=2027-03-03T09%3A30%3A00Z&end=2027-03-03T10%3A00%3A00Z'), task_params(sk)[-1]
        sk.check_clean()
    finally:
        sk.close()


def test_google_script_lists_notes_and_events():
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
var PropertiesService = { getScriptProperties: function () { return { getProperty: function () { return null; } }; } };
var ContentService = { MimeType: { ICAL: 'ical' }, createTextOutput: function (s) {
  return { text: s, setMimeType: function () { return this; } }; } };
var Tasks = {
  Tasklists: { list: function () { return { items: [{ id: 'L1', title: 'Le mie attività' }, { id: 'L2', title: 'Sport, palestra' }] }; },
               get: function (id) { return { id: 'L1' }; } },
  Tasks: {
    list: function (id, a) { return { items: id === 'L2' ? [{ id: 's', title: 'Corsa', status: 'needsAction', due: '2027-03-04T00:00:00.000Z' }] : [] }; },
    insert: function (res, list) { calls.push(['tinsert', res, list]); return { id: 'T1' }; },
    patch: function (res, list, task) { calls.push(['tpatch', res, list, task]); },
    move: function (list, task, a) {
      calls.push(['tmove', list, task, a]);
      if (task === 'rep') throw new Error('Recurrent tasks cannot currently be moved between lists');
      return { id: task === 'old' ? 'old' : 'N' + task }; },
    get: function (list, task) {
      calls.push(['tget', list, task]);
      if (task === 'old') throw new Error('Not Found');
      return { id: task }; } } };
var SERIES = { id: 'rec', iCalUID: 'rec@google.com', recurrence: ['RRULE:FREQ=DAILY'],
               start: { dateTime: '2027-03-01T10:00:00+01:00', timeZone: 'Europe/Rome' },
               end: { dateTime: '2027-03-01T10:30:00+01:00', timeZone: 'Europe/Rome' } };
var Calendar = {
  Calendars: { get: function (cal) { calls.push(['calget', cal]); return { timeZone: 'Europe/Rome' }; } },
  Events: {
    insert: function (res, cal) { calls.push(['insert', res, cal]); return { id: 'new1', iCalUID: 'new1@google.com' }; },
    list: function (cal, a) {
      if (a.iCalUID === 'rec@google.com') return { items: [SERIES] };
      if (a.iCalUID === 'one@google.com') return { items: [{ id: 'one', start: { dateTime: '2027-03-03T10:00:00Z' } }] };
      if (a.iCalUID === 'day@google.com') return { items: [{ id: 'day', start: { date: '2027-03-03' } }] };
      return { items: [] }; },
    patch: function (res, cal, id) { calls.push(['patch', res, cal, id]); } } };
function w(p) { var n = calls.length; var r = doGet({ parameter: p }).text; return [r, calls.slice(n)]; }
var C = 'me@example.com';
var long = new Array(4002).join('x');
process.stdout.write(JSON.stringify({
  feed: buildFeed(),
  task: w({ action: 'createtask', list: 'L2', title: 'Esame', due: '2027-03-05', notes: 'riga 1\nriga 2' }),
  taskLong: w({ action: 'createtask', title: 'Esame', due: '2027-03-05', notes: long }),
  notes: w({ action: 'edittask', list: 'L1', task: 't1', notes: '' }),
  move: w({ action: 'movetask', list: 'L1', task: 't1', tolist: 'L2' }),
  moveSame: w({ action: 'movetask', list: 'L1', task: 't1', tolist: 'L1' }),
  moveRep: w({ action: 'movetask', list: 'L1', task: 'rep', tolist: 'L2' }),
  moveIgnored: w({ action: 'movetask', list: 'L1', task: 'old', tolist: 'L2' }),
  moveNoList: w({ action: 'movetask', list: 'L1', task: 't1' }),
  ev: w({ action: 'createevent', cal: '', title: 'Corso', start: '2027-03-03T09:00:00Z', end: '2027-03-03T10:00:00Z',
          location: 'Aula 3', desc: 'Libro', rrule: 'FREQ=WEEKLY;BYDAY=MO,WE' }),
  evDay: w({ action: 'createevent', cal: C, title: 'Ferie', date: '2027-03-03', days: '1', rrule: 'FREQ=YEARLY' }),
  evBadRule: w({ action: 'createevent', title: 'X', start: '2027-03-03T09:00:00Z', end: '2027-03-03T10:00:00Z', rrule: 'FREQ=HOURLY' }),
  place: w({ action: 'editevent', cal: C, uid: 'one@google.com', location: '', desc: 'Nuova' }),
  toAllDay: w({ action: 'editevent', cal: C, uid: 'one@google.com', date: '2027-03-04', days: '1' }),
  toTimed: w({ action: 'editevent', cal: C, uid: 'day@google.com', start: '2027-03-03T09:00:00Z', end: '2027-03-03T10:00:00Z' }),
  all: w({ action: 'editevent', cal: C, uid: 'rec@google.com', orig: '2027-03-03T09:00:00Z', scope: 'all', title: 'Daily 2',
           start: '2027-03-03T09:30:00Z', end: '2027-03-03T10:15:00Z' }),
  allTexts: w({ action: 'editevent', cal: C, uid: 'rec@google.com', orig: '2027-03-03T09:00:00Z', scope: 'all', location: 'Sala' }),
  allOtherDay: w({ action: 'editevent', cal: C, uid: 'rec@google.com', orig: '2027-03-03T09:00:00Z', scope: 'all',
                  start: '2027-03-04T09:30:00Z', end: '2027-03-04T10:00:00Z' }),
  allAllDay: w({ action: 'editevent', cal: C, uid: 'rec@google.com', orig: '2027-03-03T09:00:00Z', scope: 'all', date: '2027-03-03', days: '1' })
}));
"""
    res = subprocess.run([node, '-e', harness], capture_output=True, encoding='utf-8')
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    C = 'me@example.com'
    feed = out['feed']
    assert ('X-WR-CALNAME:Google Tasks\r\nX-WC-VERSION:2\r\nX-WC-LIST;ID=L1;DEFAULT=1:Le mie attività\r\n'
            'X-WC-LIST;ID=L2:Sport\\, palestra\r\nBEGIN:VEVENT') in feed, feed
    lua = new_runtime(MockSkin({}, ini_sections()))
    wc = lua.globals()._WC
    wc.cfg.lang, wc.cfg.showDeclined, wc.cfg.scriptFeed = wc.LANGS.en, True, 3
    wc.parseICS(feed, 3)
    lists = wc.edit.taskLists
    assert wc.edit.scriptV == 2 and [(lists[i].id, lists[i].title, lists[i].default) for i in (1, 2)] == \
        [('L1', 'Le mie attività', True), ('L2', 'Sport, palestra', False)]
    assert out['task'] == ['OK T1', [['tinsert', {'title': 'Esame', 'notes': 'riga 1\nriga 2', 'due': '2027-03-05T00:00:00.000Z'}, 'L2']]]
    assert out['taskLong'] == ['ERROR notes too long', []]
    assert out['notes'] == ['OK', [['tpatch', {'notes': ''}, 'L1', 't1']]]
    assert out['move'] == ['OK Nt1', [['tmove', 'L1', 't1', {'destinationTasklist': 'L2'}], ['tget', 'L2', 'Nt1']]], out['move']
    assert out['moveSame'] == ['OK t1', []]
    assert out['moveRep'][0] == 'ERROR Recurrent tasks cannot currently be moved between lists'
    assert out['moveIgnored'][0] == 'ERROR the task stayed in its list: Not Found' and out['moveNoList'] == ['ERROR missing list or task', []]
    assert out['ev'] == ['OK new1@google.com', [['calget', 'primary'], ['insert', {
        'summary': 'Corso', 'start': {'dateTime': '2027-03-03T09:00:00Z', 'timeZone': 'Europe/Rome'},
        'end': {'dateTime': '2027-03-03T10:00:00Z', 'timeZone': 'Europe/Rome'}, 'location': 'Aula 3', 'description': 'Libro',
        'recurrence': ['RRULE:FREQ=WEEKLY;BYDAY=MO,WE']}, 'primary']]], out['ev']
    assert out['evDay'][1] == [['insert', {'summary': 'Ferie', 'start': {'date': '2027-03-03'}, 'end': {'date': '2027-03-04'},
                                           'recurrence': ['RRULE:FREQ=YEARLY']}, C]], out['evDay']
    assert out['evBadRule'] == ['ERROR bad repeat', []]
    assert out['place'] == ['OK', [['patch', {'location': '', 'description': 'Nuova'}, C, 'one']]], out['place']
    assert out['toAllDay'][1] == [['patch', {'start': {'date': '2027-03-04', 'dateTime': None, 'timeZone': None},
                                             'end': {'date': '2027-03-05', 'dateTime': None, 'timeZone': None}}, C, 'one']], out['toAllDay']
    assert out['toTimed'][1] == [['patch', {'start': {'dateTime': '2027-03-03T09:00:00Z', 'date': None},
                                            'end': {'dateTime': '2027-03-03T10:00:00Z', 'date': None}}, C, 'day']], out['toTimed']
    # the series moves by 30 minutes and lasts 45, in its own time zone
    assert out['all'] == ['OK', [['patch', {'summary': 'Daily 2',
                                            'start': {'dateTime': '2027-03-01T09:30:00.000Z', 'timeZone': 'Europe/Rome'},
                                            'end': {'dateTime': '2027-03-01T10:15:00.000Z', 'timeZone': 'Europe/Rome'}}, C, 'rec']]], out['all']
    assert out['allTexts'] == ['OK', [['patch', {'location': 'Sala'}, C, 'rec']]]
    assert out['allOtherDay'] == ['ERROR bad time', []] and out['allAllDay'][0] == 'ERROR change it in Google Calendar'


def test_lua_main_chunk_has_room_for_locals():
    # Lua 5.1 allows 200 local variables per function, the main chunk included: past it
    # Rainmeter refuses the whole script (and a press on the empty skin then moves it).
    # Keep some room: new helpers go inside a do ... end block or into a table.
    src = read_lua_source()
    room = 0
    while room < 15:
        try:
            LuaRuntime().compile(src + '\nlocal ' + ','.join('_room%d' % i for i in range(room + 1)) + '\n')
        except Exception:
            break
        room += 1
    assert room >= 15, 'only %d more locals fit in the main chunk of Calendar.lua' % room


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
