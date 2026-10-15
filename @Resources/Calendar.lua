-- WeeklyCalendar.lua (Rainmeter, Lua 5.1)
-- Weekly Google Calendar-style view powered by one or more iCal (.ics) feeds.
-- Reads files downloaded by WebParser (DownloadFile folder), expands recurring
-- events (RRULE/EXDATE/RECURRENCE-ID), converts timezones (VTIMEZONE), and renders
-- the week using a pool of meters defined in WeeklyCalendar.ini.
-- Supports vertical hour scrolling, auto-shift for evening events, and week navigation.

------------------------------------------------------------------------
-- Constants and State
------------------------------------------------------------------------
local EV_POOL, AD_POOL, HL_POOL, GRID_POOL = 80, 21, 25, 50
local WD = { SU = 0, MO = 1, TU = 2, WE = 3, TH = 4, FR = 5, SA = 6 }

local LANGS = {
  en = {
    days = { 'SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT' },
    months = { 'January', 'February', 'March', 'April', 'May', 'June', 'July',
               'August', 'September', 'October', 'November', 'December' },
    today = 'Today', week = 'Week', updated = 'Updated at', offline = 'offline',
    more = 'more',
    noTitle = '(no title)',
    noUrl = { 'No calendar configured.',
              'Right-click the skin > Calendar settings,',
              'paste your secret iCal address into IcalUrl1 and save.' },
    loading = { 'Downloading calendar...' },
  },
  it = {
    days = { 'DOM', 'LUN', 'MAR', 'MER', 'GIO', 'VEN', 'SAB' },
    months = { 'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio',
               'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre' },
    today = 'Oggi', week = 'Settimana', updated = 'Aggiornato alle', offline = 'offline',
    more = 'altri',
    noTitle = '(senza titolo)',
    noUrl = { 'Nessun calendario configurato.',
              'Tasto destro sulla skin > Impostazioni calendario,',
              'incolla l\'indirizzo segreto iCal in IcalUrl1 e salva.' },
    loading = { 'Scarico il calendario...' },
  },
}

local cfg = {}
local events = {}         -- base events (VEVENT) across all feeds
local tzdefs = {}         -- TZID -> VTIMEZONE definition
local weekOffset = 0      -- week offset relative to today (0 = current week)
local userScrollH = nil   -- manual hour scroll offset (nil = auto/default)
local lastAutoShift = nil -- tracks morning/evening auto-scroll state
local needLayout = true
local texts = {}          -- feed -> last raw .ics content
local lastPoll = 0
local lastSync = nil
local finishSeen = false
local lastNow = nil
local netErrs = {}
local lastToday = nil
local started = false
local loadedAny = false
local loadErr = nil
local used = { ev = EV_POOL, ad = AD_POOL, hl = HL_POOL }
local skinPath, sep = '', '\\'

------------------------------------------------------------------------
-- Basic Utilities
------------------------------------------------------------------------
local function V(name, default)
  local v = SKIN:GetVariable(name)
  if v == nil or v == '' then return default end
  return v
end

local function N(name, default)
  return tonumber(V(name, default)) or default
end

local function fmt(n) return string.format('%.1f', n) end

local function set(meter, option, value)
  SKIN:Bang('!SetOption', meter, option, tostring(value))
end

local function hide(meter) SKIN:Bang('!HideMeter', meter) end
local function show(meter) SKIN:Bang('!ShowMeter', meter) end

local function uchars(s)
  local t = {}
  for c in s:gmatch('[%z\1-\127\194-\244][\128-\191]*') do t[#t + 1] = c end
  return t
end

local function ulen(s) return #uchars(s) end

local function usub(s, i, j)
  local t = uchars(s)
  return table.concat(t, '', i, j or #t)
end

-- Strips characters interpreted by Rainmeter (variables, sections, quotes)
local function safe(s)
  s = s or ''
  s = s:gsub('#', ' '):gsub('%[', '('):gsub('%]', ')'):gsub('"', "'")
  s = s:gsub('%s+', ' ')
  return s
end

------------------------------------------------------------------------
-- Dates (proleptic Gregorian calendar, days since 1970-01-01)
------------------------------------------------------------------------
local function daysFromCivil(y, m, d)
  if m <= 2 then y = y - 1 end
  local era = math.floor(y / 400)
  local yoe = y - era * 400
  local mp = (m + 9) % 12
  local doy = math.floor((153 * mp + 2) / 5) + d - 1
  local doe = yoe * 365 + math.floor(yoe / 4) - math.floor(yoe / 100) + doy
  return era * 146097 + doe - 719468
end

local function civilFromDays(z)
  z = z + 719468
  local era = math.floor(z / 146097)
  local doe = z - era * 146097
  local yoe = math.floor((doe - math.floor(doe / 1460) + math.floor(doe / 36524)
                          - math.floor(doe / 146096)) / 365)
  local y = yoe + era * 400
  local doy = doe - (365 * yoe + math.floor(yoe / 4) - math.floor(yoe / 100))
  local mp = math.floor((5 * doy + 2) / 153)
  local d = doy - math.floor((153 * mp + 2) / 5) + 1
  local m = mp + 3
  if m > 12 then m = m - 12 end
  if m <= 2 then y = y + 1 end
  return y, m, d
end

local function weekdayOf(day) return (day + 4) % 7 end -- 0 = Sunday

local function daysInMonth(y, m)
  local dm = { 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31 }
  if m == 2 and ((y % 4 == 0 and y % 100 ~= 0) or y % 400 == 0) then return 29 end
  return dm[m]
end

local function nthWeekday(y, m, wd, n)
  local dim = daysInMonth(y, m)
  local first = daysFromCivil(y, m, 1)
  if n > 0 then
    local off = (wd - weekdayOf(first) + 7) % 7
    local d = 1 + off + (n - 1) * 7
    if d > dim then return nil end
    return first + d - 1
  else
    local last = first + dim - 1
    local off = (weekdayOf(last) - wd + 7) % 7
    local d = last - off - (-n - 1) * 7
    if d < first then return nil end
    return d
  end
end

-- Local PC timezone (via C runtime)
local function localMidnight(day)
  local y, m, d = civilFromDays(day)
  return os.time({ year = y, month = m, day = d, hour = 0, min = 0, sec = 0 })
end

local function localDayOf(e)
  local t = os.date('*t', e)
  return daysFromCivil(t.year, t.month, t.day), t.hour * 60 + t.min
end

local function localOffset(e)
  local t = os.date('*t', e)
  local asUtc = daysFromCivil(t.year, t.month, t.day) * 86400 + t.hour * 3600 + t.min * 60 + t.sec
  return asUtc - e
end

------------------------------------------------------------------------
-- iCalendar Parser
------------------------------------------------------------------------
local function readFile(path)
  local f = io.open(path, 'rb')
  if not f then return nil end
  local s = f:read('*a')
  f:close()
  return s
end

local function parseProp(line)
  local first = line:find('[;:]')
  if not first then return nil end
  local name = line:sub(1, first - 1):upper()
  local params = {}
  local pos = first
  local n = #line
  while line:sub(pos, pos) == ';' do
    local eq = line:find('=', pos + 1, true)
    if not eq then break end
    local pname = line:sub(pos + 1, eq - 1):upper()
    local vstart = eq + 1
    local val, nextpos
    if line:sub(vstart, vstart) == '"' then
      local q = line:find('"', vstart + 1, true) or n
      val = line:sub(vstart + 1, q - 1)
      nextpos = q + 1
    else
      local e = line:find('[;:]', vstart) or (n + 1)
      val = line:sub(vstart, e - 1)
      nextpos = e
    end
    params[pname] = val
    pos = nextpos
  end
  if line:sub(pos, pos) ~= ':' then return nil end
  return name, params, line:sub(pos + 1)
end

local function unescape(s)
  return (s:gsub('\\(.)', function(c)
    if c == 'n' or c == 'N' then return ' ' end
    return c
  end))
end

local function parseDT(value, params)
  if not value then return nil end
  local y, m, d = value:match('^(%d%d%d%d)(%d%d)(%d%d)')
  if not y then return nil end
  local r = { y = tonumber(y), m = tonumber(m), d = tonumber(d), H = 0, M = 0, S = 0 }
  local H, M, S = value:match('T(%d%d)(%d%d)(%d%d)')
  if (params and params.VALUE == 'DATE') or not H then
    r.allday = true
    return r
  end
  r.H, r.M, r.S = tonumber(H), tonumber(M), tonumber(S)
  if value:sub(-1) == 'Z' then r.zone = 'utc'
  elseif params and params.TZID then r.zone = params.TZID
  else r.zone = 'float' end
  return r
end

local function parseOffset(v)
  local sign, hh, mm, ss = v:match('^([+-])(%d%d)(%d%d)(%d?%d?)')
  if not sign then return 0 end
  local s = tonumber(hh) * 3600 + tonumber(mm) * 60 + (tonumber(ss) or 0)
  if sign == '-' then s = -s end
  return s
end

local function parseRRule(str)
  local rr = {}
  for k, v in str:gmatch('([^=;]+)=([^;]*)') do rr[k:upper()] = v end
  rr.INTERVAL = tonumber(rr.INTERVAL) or 1
  if rr.INTERVAL < 1 then rr.INTERVAL = 1 end
  rr.COUNT = tonumber(rr.COUNT)
  rr.FREQ = rr.FREQ and rr.FREQ:upper() or nil
  if rr.BYDAY then
    local list = {}
    for tok in rr.BYDAY:gmatch('[^,]+') do
      local n, wd = tok:match('^([+-]?%d*)(%a%a)$')
      if wd and WD[wd:upper()] then
        local num = nil
        if n ~= '' then num = tonumber(n) end
        list[#list + 1] = { n = num, wd = WD[wd:upper()] }
      end
    end
    rr.byday = list
  end
  local function nums(s)
    local t = {}
    for x in s:gmatch('[+-]?%d+') do t[#t + 1] = tonumber(x) end
    return t
  end
  if rr.BYMONTHDAY then rr.bymonthday = nums(rr.BYMONTHDAY) end
  if rr.BYMONTH then rr.bymonth = nums(rr.BYMONTH) end
  rr.wkst = WD[(rr.WKST or 'MO'):upper()] or 1
  return rr
end

local function parseDuration(v)
  local sign, rest = v:match('^([+-]?)P(.*)$')
  if not rest then return nil end
  local datePart = rest:match('^([^T]*)') or ''
  local timePart = rest:match('T(.*)$') or ''
  local secs = 0
  local w = datePart:match('(%d+)W'); if w then secs = secs + tonumber(w) * 604800 end
  local d = datePart:match('(%d+)D'); if d then secs = secs + tonumber(d) * 86400 end
  local h = timePart:match('(%d+)H'); if h then secs = secs + tonumber(h) * 3600 end
  local mi = timePart:match('(%d+)M'); if mi then secs = secs + tonumber(mi) * 60 end
  local s = timePart:match('(%d+)S'); if s then secs = secs + tonumber(s) end
  if sign == '-' then secs = -secs end
  return secs
end

local function parseICS(text, feed)
  text = text:gsub('\r\n', '\n'):gsub('\r', '\n'):gsub('\n[ \t]', '')
  local cur, curtz, curcomp
  local inAlarm = false
  for line in text:gmatch('[^\n]+') do
    local name, params, value = parseProp(line)
    if name == 'BEGIN' then
      local v = value:upper()
      if v == 'VEVENT' then cur = { feed = feed, exdates = {}, props = {} }
      elseif v == 'VTIMEZONE' then curtz = { comps = {} }
      elseif (v == 'STANDARD' or v == 'DAYLIGHT') and curtz then curcomp = { kind = v, rdates = {} }
      elseif v == 'VALARM' then inAlarm = true end
    elseif name == 'END' then
      local v = value:upper()
      if v == 'VEVENT' then
        if cur then events[#events + 1] = cur end
        cur = nil
      elseif v == 'VTIMEZONE' then
        if curtz and curtz.id then tzdefs[curtz.id] = curtz end
        curtz = nil
      elseif v == 'STANDARD' or v == 'DAYLIGHT' then
        if curtz and curcomp then curtz.comps[#curtz.comps + 1] = curcomp end
        curcomp = nil
      elseif v == 'VALARM' then inAlarm = false end
    elseif name and curcomp then
      if name == 'DTSTART' then curcomp.dt = parseDT(value, params)
      elseif name == 'TZOFFSETFROM' then curcomp.from = parseOffset(value)
      elseif name == 'TZOFFSETTO' then curcomp.to = parseOffset(value)
      elseif name == 'RRULE' then curcomp.rr = parseRRule(value)
      elseif name == 'RDATE' then
        for v in value:gmatch('[^,]+') do
          local dt = parseDT(v, params)
          if dt then
            curcomp.rdates[#curcomp.rdates + 1] =
              daysFromCivil(dt.y, dt.m, dt.d) * 86400 + dt.H * 3600 + dt.M * 60 + dt.S
          end
        end
      end
    elseif name and curtz then
      if name == 'TZID' then curtz.id = value end
    elseif name and cur and not inAlarm then
      if name == 'DTSTART' then cur.dtstart = parseDT(value, params)
      elseif name == 'DTEND' then cur.dtend = parseDT(value, params)
      elseif name == 'DURATION' then cur.duration = parseDuration(value)
      elseif name == 'SUMMARY' then cur.summary = unescape(value)
      elseif name == 'LOCATION' then cur.location = unescape(value)
      elseif name == 'UID' then cur.uid = value
      elseif name == 'STATUS' then cur.status = value:upper()
      elseif name == 'RRULE' then cur.rrule = parseRRule(value)
      elseif name == 'RECURRENCE-ID' then cur.recid = parseDT(value, params)
      elseif name == 'EXDATE' then
        for v in value:gmatch('[^,]+') do
          local dt = parseDT(v, params)
          if dt then cur.exdates[#cur.exdates + 1] = dt end
        end
      end
    end
  end
end

------------------------------------------------------------------------
-- Timezones
------------------------------------------------------------------------
local function tzRuleDay(rr, y)
  local m = rr.bymonth and rr.bymonth[1]
  if not m then return nil end
  if rr.byday and rr.byday[1] then
    local b = rr.byday[1]
    return nthWeekday(y, m, b.wd, b.n or 1)
  elseif rr.bymonthday and rr.bymonthday[1] then
    local d = rr.bymonthday[1]
    if d < 0 then d = daysInMonth(y, m) + d + 1 end
    return daysFromCivil(y, m, d)
  end
  return nil
end

local function compOnsetBefore(c, X)
  if not c.dt or not c.from then return nil end
  local best
  local tod = c.dt.H * 3600 + c.dt.M * 60 + c.dt.S
  local function try(e)
    if e <= X and (not best or e > best) then best = e end
  end
  local d0 = daysFromCivil(c.dt.y, c.dt.m, c.dt.d)
  if c.rr and c.rr.FREQ == 'YEARLY' then
    local untilE
    if c.rr.UNTIL then
      local u = parseDT(c.rr.UNTIL, {})
      if u then untilE = daysFromCivil(u.y, u.m, u.d) * 86400 + u.H * 3600 + u.M * 60 + u.S end
    end
    local y0 = civilFromDays(math.floor(X / 86400))
    for y = y0 - 1, y0 do
      local day = tzRuleDay(c.rr, y)
      if day and day >= d0 then
        local e = day * 86400 + tod - c.from
        if not untilE or e <= untilE then try(e) end
      end
    end
  else
    try(d0 * 86400 + tod - c.from)
  end
  for _, rd in ipairs(c.rdates or {}) do try(rd - c.from) end
  return best
end

local function tzOffsetAt(tz, X)
  local bestE, bestC
  for _, c in ipairs(tz.comps) do
    local e = compOnsetBefore(c, X)
    if e and (not bestE or e > bestE) then bestE, bestC = e, c end
  end
  if bestC then return bestC.to end
  local c = tz.comps[1]
  if c and c.from then return c.from end
  return 0
end

-- (day, seconds since day start) in timezone 'zone' -> UTC epoch
local function wallToEpoch(zone, day, secs)
  if zone == 'utc' then return day * 86400 + secs end
  local tz = tzdefs[zone]
  if tz and #tz.comps > 0 then
    local wall = day * 86400 + secs
    local off = tzOffsetAt(tz, wall)
    local e = wall - off
    local off2 = tzOffsetAt(tz, e)
    return wall - off2
  end
  -- "floating" time or unknown timezone: local PC time
  local y, m, d = civilFromDays(day)
  return os.time({ year = y, month = m, day = d,
                   hour = math.floor(secs / 3600), min = math.floor(secs % 3600 / 60), sec = secs % 60 })
end

------------------------------------------------------------------------
-- Recurring Event Expansion
------------------------------------------------------------------------
local function monthDays(rr, y, m, sd)
  local out = {}
  local dim = daysInMonth(y, m)
  local first = daysFromCivil(y, m, 1)
  if rr.bymonthday then
    for _, d in ipairs(rr.bymonthday) do
      local dd = d
      if d < 0 then dd = dim + d + 1 end
      if dd >= 1 and dd <= dim then out[#out + 1] = first + dd - 1 end
    end
  elseif rr.byday then
    for _, b in ipairs(rr.byday) do
      if b.n then
        local day = nthWeekday(y, m, b.wd, b.n)
        if day then out[#out + 1] = day end
      else
        for d = 1, dim do
          if weekdayOf(first + d - 1) == b.wd then out[#out + 1] = first + d - 1 end
        end
      end
    end
  elseif sd <= dim then
    out[#out + 1] = first + sd - 1
  end
  table.sort(out)
  return out
end

local function dailyMatch(rr, day)
  if rr.byday then
    local ok = false
    for _, b in ipairs(rr.byday) do if b.wd == weekdayOf(day) then ok = true end end
    if not ok then return false end
  end
  if rr.bymonth or rr.bymonthday then
    local _, m, d = civilFromDays(day)
    if rr.bymonth then
      local ok = false
      for _, x in ipairs(rr.bymonth) do if x == m then ok = true end end
      if not ok then return false end
    end
    if rr.bymonthday then
      local ok = false
      for _, x in ipairs(rr.bymonthday) do
        local dd = x
        if x < 0 then
          local y2 = civilFromDays(day)
          dd = daysInMonth(y2, m) + x + 1
        end
        if dd == d then ok = true end
      end
      if not ok then return false end
    end
  end
  return true
end

-- Calls fn(day) for each occurrence in chronological order (>= startDay).
-- fn returns true to stop.
local function eachOccurrence(rr, startDay, fromDay, toDay, fn)
  local freq, iv = rr.FREQ, rr.INTERVAL
  local skip = not rr.COUNT
  local guard = 0
  if freq == 'DAILY' then
    local k = 0
    if skip and fromDay > startDay then
      k = math.max(0, math.floor((fromDay - startDay) / iv) - 1)
    end
    while true do
      local day = startDay + k * iv
      if day > toDay then return end
      if dailyMatch(rr, day) and fn(day) then return end
      k = k + 1
      guard = guard + 1
      if guard > 40000 then return end
    end
  elseif freq == 'WEEKLY' then
    local wk = rr.wkst
    local ws0 = startDay - ((weekdayOf(startDay) - wk + 7) % 7)
    local offs = {}
    if rr.byday then
      for _, b in ipairs(rr.byday) do offs[#offs + 1] = (b.wd - wk + 7) % 7 end
    else
      offs[1] = (weekdayOf(startDay) - wk + 7) % 7
    end
    table.sort(offs)
    local p = 0
    if skip and fromDay > ws0 then
      p = math.max(0, math.floor((fromDay - ws0) / (7 * iv)) - 1)
    end
    while true do
      local ws = ws0 + p * 7 * iv
      if ws > toDay then return end
      for _, o in ipairs(offs) do
        local day = ws + o
        if day >= startDay then
          if day > toDay then return end
          if fn(day) then return end
        end
      end
      p = p + 1
      guard = guard + 1
      if guard > 8000 then return end
    end
  elseif freq == 'MONTHLY' or freq == 'YEARLY' then
    local sy, sm, sd = civilFromDays(startDay)
    local p = 0
    if freq == 'MONTHLY' then
      local m0 = sy * 12 + (sm - 1)
      if skip and fromDay > startDay then
        local fy, fm = civilFromDays(fromDay)
        p = math.max(0, math.floor((fy * 12 + fm - 1 - m0) / iv) - 1)
      end
      while true do
        local mm = m0 + p * iv
        local y, m = math.floor(mm / 12), mm % 12 + 1
        if daysFromCivil(y, m, 1) > toDay then return end
        for _, day in ipairs(monthDays(rr, y, m, sd)) do
          if day >= startDay then
            if day > toDay then return end
            if fn(day) then return end
          end
        end
        p = p + 1
        guard = guard + 1
        if guard > 3000 then return end
      end
    else
      if skip and fromDay > startDay then
        local fy = civilFromDays(fromDay)
        p = math.max(0, math.floor((fy - sy) / iv) - 1)
      end
      local months = {}
      if rr.bymonth then for _, m in ipairs(rr.bymonth) do months[#months + 1] = m end
      else months[1] = sm end
      table.sort(months)
      while true do
        local y = sy + p * iv
        if daysFromCivil(y, 1, 1) > toDay then return end
        for _, m in ipairs(months) do
          for _, day in ipairs(monthDays(rr, y, m, sd)) do
            if day >= startDay then
              if day > toDay then return end
              if fn(day) then return end
            end
          end
        end
        p = p + 1
        guard = guard + 1
        if guard > 500 then return end
      end
    end
  else
    -- unsupported frequencies (HOURLY, etc.): first occurrence only
    fn(startDay)
  end
end

local function dtDay(dt) return daysFromCivil(dt.y, dt.m, dt.d) end
local function dtSecs(dt) return dt.H * 3600 + dt.M * 60 + dt.S end

-- Exclusion sets (EXDATE + occurrences replaced by RECURRENCE-ID)
local overrides = {}   -- uid -> { epochs = {}, days = {} }

local function buildOverrides()
  overrides = {}
  for _, ev in ipairs(events) do
    if ev.recid and ev.uid and ev.recid.y then
      local o = overrides[ev.uid]
      if not o then o = { epochs = {}, days = {} }; overrides[ev.uid] = o end
      if ev.recid.allday then
        o.days[dtDay(ev.recid)] = true
      else
        local zone = ev.recid.zone
        if zone == 'float' and ev.dtstart and ev.dtstart.zone then zone = ev.dtstart.zone end
        o.epochs[wallToEpoch(zone, dtDay(ev.recid), dtSecs(ev.recid))] = true
      end
    end
  end
end

-- Produces instances of an event that intersect the [fromDay, toDay) local day window
local function expandEvent(ev, fromDay, toDay, out)
  local st = ev.dtstart
  if not st or ev.status == 'CANCELLED' then return end
  local winS, winE = localMidnight(fromDay), localMidnight(toDay)
  local title = (ev.summary and ev.summary ~= '') and ev.summary or cfg.lang.noTitle
  local loc = ev.location or ''

  if st.allday then
    local sDay = dtDay(st)
    local durDays = 1
    if ev.dtend and ev.dtend.y then durDays = math.max(1, dtDay(ev.dtend) - sDay)
    elseif ev.duration then durDays = math.max(1, math.ceil(ev.duration / 86400)) end
    local function emit(day)
      if day < toDay and day + durDays > fromDay then
        out[#out + 1] = { kind = 'allday', sDay = day, eDay = day + durDays,
                          title = title, loc = loc, feed = ev.feed }
      end
    end
    if not ev.rrule then
      emit(sDay)
    else
      local rr = ev.rrule
      local ex = {}
      for _, x in ipairs(ev.exdates) do ex[dtDay(x)] = true end
      local ov = ev.uid and overrides[ev.uid]
      local count = 0
      local untilDay
      if rr.UNTIL then local u = parseDT(rr.UNTIL, {}); if u then untilDay = dtDay(u) end end
      eachOccurrence(rr, sDay, fromDay - durDays - 2, toDay + 1, function(day)
        count = count + 1
        if rr.COUNT and count > rr.COUNT then return true end
        if untilDay and day > untilDay then return true end
        if not ex[day] and not (ov and ov.days[day]) then emit(day) end
        return false
      end)
    end
    return
  end

  local zone = st.zone
  local sDay, sSecs = dtDay(st), dtSecs(st)
  local baseS = wallToEpoch(zone, sDay, sSecs)
  local dur = 0
  if ev.dtend and ev.dtend.y and not ev.dtend.allday then
    local ez = ev.dtend.zone
    dur = wallToEpoch(ez, dtDay(ev.dtend), dtSecs(ev.dtend)) - baseS
  elseif ev.duration then
    dur = ev.duration
  end
  if dur < 0 then dur = 0 end

  local function emit(s)
    local e = s + dur
    if s < winE and (e > winS or (dur == 0 and s >= winS)) then
      out[#out + 1] = { kind = 'timed', s = s, e = e, title = title, loc = loc, feed = ev.feed }
    end
  end

  if not ev.rrule then
    emit(baseS)
    return
  end

  local rr = ev.rrule
  local ex = {}
  for _, x in ipairs(ev.exdates) do
    if x.allday then
      ex['d' .. dtDay(x)] = true
    else
      local z = x.zone
      if z == 'float' then z = zone end
      ex[wallToEpoch(z, dtDay(x), dtSecs(x))] = true
    end
  end
  local ov = ev.uid and overrides[ev.uid]
  local untilE, untilDay
  if rr.UNTIL then
    local u = parseDT(rr.UNTIL, {})
    if u then
      if u.allday then untilDay = dtDay(u)
      else
        local z = u.zone
        if z == 'float' then z = zone end
        untilE = wallToEpoch(z, dtDay(u), dtSecs(u))
      end
    end
  end
  local count = 0
  local margin = math.ceil(dur / 86400) + 3
  eachOccurrence(rr, sDay, fromDay - margin, toDay + 2, function(day)
    count = count + 1
    if rr.COUNT and count > rr.COUNT then return true end
    local s = wallToEpoch(zone, day, sSecs)
    if untilE and s > untilE then return true end
    if untilDay and day > untilDay then return true end
    if not ex[s] and not ex['d' .. day] and not (ov and ov.epochs[s]) then emit(s) end
    return false
  end)
end

local function buildInstances(fromDay, toDay)
  local out = {}
  for _, ev in ipairs(events) do
    local ok, err = pcall(expandEvent, ev, fromDay, toDay, out)
    if not ok then loadErr = 'Event error: ' .. tostring(err) end
  end
  return out
end

------------------------------------------------------------------------
-- Colors
------------------------------------------------------------------------
local function parseColor(s, default)
  s = (s or ''):gsub('%s', '')
  local r, g, b, a = s:match('^(%d+),(%d+),(%d+),?(%d*)$')
  if r then return { tonumber(r), tonumber(g), tonumber(b), tonumber(a) or 255 } end
  local hex = s:gsub('^#', '')
  if hex:match('^%x%x%x%x%x%x$') or hex:match('^%x%x%x%x%x%x%x%x$') then
    return { tonumber(hex:sub(1, 2), 16), tonumber(hex:sub(3, 4), 16), tonumber(hex:sub(5, 6), 16),
             tonumber(hex:sub(7, 8), 16) or 255 }
  end
  return default or { 0, 0, 0, 255 }
end

local function colStr(c)
  return string.format('%d,%d,%d,%d', c[1], c[2], c[3], c[4] or 255)
end

local function blend(c, bg, t) -- t = background color weight
  return { math.floor(c[1] + (bg[1] - c[1]) * t + 0.5),
           math.floor(c[2] + (bg[2] - c[2]) * t + 0.5),
           math.floor(c[3] + (bg[3] - c[3]) * t + 0.5), 255 }
end

------------------------------------------------------------------------
-- Settings
------------------------------------------------------------------------
local function validUrl(u) return u and u:match('^https?://') ~= nil end

local function readSettings()
  cfg.lang = LANGS[V('Language', 'en'):lower()] or LANGS.en
  cfg.W, cfg.H = N('Width', 1400), N('Height', 860)
  cfg.startHour, cfg.endHour = N('StartHour', 8), N('EndHour', 20)
  cfg.autoRange = N('AutoRange', 1) == 1
  cfg.autoScroll = N('AutoScroll', 1) == 1
  cfg.autoScrollHour = N('AutoScrollHour', 14)
  cfg.firstDay = N('FirstDay', 1) % 7
  cfg.toolbar = N('ShowToolbar', 1) == 1
  cfg.pt = N('FontSize', 9)
  cfg.px = cfg.pt * 4 / 3
  cfg.radius = N('EventRadius', 8)
  cfg.fade = N('PastFade', 0.35)
  cfg.bg = parseColor(V('BgColor', '255,255,255,255'))
  cfg.grid = colStr(parseColor(V('GridColor', '224,227,231,255')))
  cfg.evText = colStr(parseColor(V('EventTextColor', '255,255,255,255')))
  cfg.pastText = colStr(parseColor(V('PastTextColor', '255,255,255,230')))
  cfg.now = colStr(parseColor(V('NowColor', '234,67,53,255')))
  cfg.today = colStr(parseColor(V('TodayColor', '11,87,208,255')))
  cfg.todayText = colStr(parseColor(V('TodayTextColor', '255,255,255,255')))
  cfg.dayNum = colStr(parseColor(V('DayNumColor', '31,31,31,255')))
  cfg.muted = colStr(parseColor(V('MutedColor', '116,119,117,255')))
  cfg.badgeBg = colStr(parseColor(V('BadgeBgColor', '239,241,241,255')))
  cfg.badgeText = colStr(parseColor(V('BadgeTextColor', '68,71,70,255')))
  cfg.border = colStr(parseColor(V('BorderColor', '218,220,224,255')))
  cfg.urls, cfg.colors, cfg.pastColors = {}, {}, {}
  for i = 1, 3 do
    cfg.urls[i] = V('IcalUrl' .. i, '')
    local c = parseColor(V('EventColor' .. i, i == 1 and '3,155,229,255' or (i == 2 and '11,128,67,255' or '142,36,170,255')))
    cfg.colors[i] = c
    cfg.pastColors[i] = blend(c, cfg.bg, cfg.fade)
  end
  skinPath = SKIN:GetVariable('CURRENTPATH') or ''
  sep = skinPath:find('/', 1, true) and '/' or '\\'
end

------------------------------------------------------------------------
-- Data Loading
------------------------------------------------------------------------
local function rebuild()
  events, tzdefs = {}, {}
  loadedAny, loadErr = false, nil
  for i = 1, 3 do
    local txt = texts[i]
    if txt then
      if txt:find('BEGIN:VCALENDAR', 1, true) then
        local ok, err = pcall(parseICS, txt, i)
        if ok then loadedAny = true else loadErr = 'ICS file error: ' .. tostring(err) end
      else
        loadErr = 'Downloaded file (calendar ' .. i .. ') is not a valid iCal feed: check the URL.'
      end
    end
  end
  buildOverrides()
  if loadErr then SKIN:Bang('!Log', 'WeeklyCalendar: ' .. loadErr, 'Warning') end
end

local function pollFiles()
  lastPoll = os.time()
  local changed = false
  for i = 1, 3 do
    if validUrl(cfg.urls[i]) then
      local txt = readFile(skinPath .. 'DownloadFile' .. sep .. 'calendar' .. i .. '.ics')
      if txt and #txt > 0 and txt ~= texts[i] then
        texts[i] = txt
        changed = true
      end
    end
  end
  if changed then rebuild() end
  return changed
end

------------------------------------------------------------------------
-- Text Wrapping by Code Point
------------------------------------------------------------------------
local function wrapText(s, maxChars, maxLines)
  maxChars = math.max(1, math.floor(maxChars))
  local lines, cur = {}, ''
  for w in s:gmatch('%S+') do
    local wc = uchars(w)
    while #wc > maxChars do
      if cur ~= '' then lines[#lines + 1] = cur; cur = '' end
      lines[#lines + 1] = table.concat(wc, '', 1, maxChars)
      local rest = {}
      for i = maxChars + 1, #wc do rest[#rest + 1] = wc[i] end
      wc = rest
      w = table.concat(wc)
    end
    if #wc > 0 then
      if cur == '' then cur = w
      elseif ulen(cur) + 1 + #wc <= maxChars then cur = cur .. ' ' .. w
      else lines[#lines + 1] = cur; cur = w end
    end
  end
  if cur ~= '' then lines[#lines + 1] = cur end
  if #lines > maxLines then
    local t = {}
    for i = 1, maxLines do t[i] = lines[i] end
    lines = t
    local last = lines[maxLines]
    if ulen(last) >= maxChars then last = usub(last, 1, math.max(1, maxChars - 3)) end
    lines[maxLines] = last .. '...'
  end
  return lines
end

local function hhmm(e) return os.date('%H:%M', e) end

------------------------------------------------------------------------
-- Layout Calculations
------------------------------------------------------------------------
local function weekStartOf(day)
  return day - ((weekdayOf(day) - cfg.firstDay + 7) % 7)
end

local function isoWeek(day)
  local wdMon = (weekdayOf(day) + 6) % 7
  local thu = day - wdMon + 3
  local y = civilFromDays(thu)
  return math.floor((thu - daysFromCivil(y, 1, 1)) / 7) + 1
end

local function packDay(segs)
  table.sort(segs, function(a, b)
    if a.s ~= b.s then return a.s < b.s end
    return a.eEff > b.eEff
  end)
  local cur, curEnd
  local clusters = {}
  for _, sg in ipairs(segs) do
    if not cur or sg.s >= curEnd then
      cur = { cols = {}, items = {} }
      clusters[#clusters + 1] = cur
      curEnd = -1
    end
    local placed = false
    for ci, colEnd in ipairs(cur.cols) do
      if colEnd <= sg.s then
        sg.col = ci
        cur.cols[ci] = sg.eEff
        placed = true
        break
      end
    end
    if not placed then
      cur.cols[#cur.cols + 1] = sg.eEff
      sg.col = #cur.cols
    end
    cur.items[#cur.items + 1] = sg
    if sg.eEff > curEnd then curEnd = sg.eEff end
  end
  for _, c in ipairs(clusters) do
    for _, sg in ipairs(c.items) do sg.ncols = #c.cols end
  end
end

local function tzLabel(now)
  local off = localOffset(now)
  local sign = off < 0 and '-' or '+'
  off = math.abs(off)
  local h, m = math.floor(off / 3600), math.floor(off % 3600 / 60)
  if m == 0 then return string.format('GMT%s%02d', sign, h) end
  return string.format('GMT%s%02d:%02d', sign, h, m)
end

local function setStatus(lines)
  if lines and #lines > 0 then
    set('Status', 'Text', table.concat(lines, '#CRLF#'))
    show('Status')
  else
    hide('Status')
  end
end

-- Determines the start hour, end hour, and scroll limits for the visible grid
local function getVisibleHours(nowMin)
  local span = math.max(4, math.min(24, cfg.endHour - cfg.startHour))
  local maxStartH = math.max(0, 24 - span)
  local baseStartH = math.max(0, math.min(maxStartH, cfg.startHour))

  -- User manual scroll override takes precedence
  if userScrollH ~= nil then
    local sH = math.max(0, math.min(maxStartH, userScrollH))
    return sH, sH + span, span, maxStartH
  end

  -- Auto-scroll for current week in the afternoon/evening
  if weekOffset == 0 and cfg.autoScroll then
    local nowH = math.floor(nowMin / 60)
    if nowH >= cfg.autoScrollHour then
      -- Shift down so the evening through midnight is visible
      local eveningStart = math.max(baseStartH, math.min(maxStartH, baseStartH + (24 - cfg.endHour)))
      if eveningStart == baseStartH and maxStartH > baseStartH then
        eveningStart = math.min(maxStartH, baseStartH + 4)
      end
      return eveningStart, eveningStart + span, span, maxStartH
    end
  end

  return baseStartH, baseStartH + span, span, maxStartH
end

local function layout()
  local lang = cfg.lang
  local now = os.time()
  local todayDay, nowMin = localDayOf(now)
  local ws = weekStartOf(todayDay + weekOffset * 7)
  local we = ws + 7
  local inst = buildInstances(ws, we)

  local dS, dE = {}, {}
  for i = 0, 7 do dS[i] = localMidnight(ws + i) end
  for i = 0, 6 do dE[i] = dS[i + 1] end

  local days = {}
  for i = 0, 6 do days[i] = { segs = {}, allday = {} } end

  for _, it in ipairs(inst) do
    if it.kind == 'allday' then
      for d = math.max(it.sDay, ws), math.min(it.eDay, we) - 1 do
        local list = days[d - ws].allday
        list[#list + 1] = it
      end
    else
      for i = 0, 6 do
        if it.s < dE[i] and (it.e > dS[i] or (it.e == it.s and it.s >= dS[i])) then
          local sMin, eMin = 0, 1440
          if it.s > dS[i] then local _, mm = localDayOf(it.s); sMin = mm end
          if it.e < dE[i] then local _, mm = localDayOf(it.e); eMin = mm end
          if eMin < sMin then eMin = sMin end
          local sg = { it = it, day = i, s = sMin, e = eMin, eEff = math.min(1440, math.max(eMin, sMin + 30)) }
          local list = days[i].segs
          list[#list + 1] = sg
        end
      end
    end
  end

  local startH, endH, hours, maxStartH = getVisibleHours(nowMin)

  -- Geometry
  local W, H = cfg.W, cfg.H
  local tb = cfg.toolbar and 56 or 0
  local hdr = 68
  local maxAD = 0
  for i = 0, 6 do maxAD = math.max(maxAD, math.min(3, #days[i].allday)) end
  local adH = maxAD > 0 and (maxAD * 22 + 8) or 0
  local gridTop = tb + hdr + adH
  local pad = 0
  local gridBottom = H - 10
  local timeW = 64
  local dayW = (W - timeW - 14) / 7
  local hourH = (gridBottom - gridTop - pad) / hours
  local px = cfg.px
  local lh = px * 1.25 + 1

  -- Grid (single Shape meter with multiple lines)
  local g = 0
  local function gline(x1, y1, x2, y2)
    g = g + 1
    local key = (g == 1) and 'Shape' or ('Shape' .. g)
    set('Grid', key, 'Line ' .. fmt(x1) .. ',' .. fmt(y1) .. ',' .. fmt(x2) .. ',' .. fmt(y2)
      .. ' | StrokeWidth 1 | Stroke Color ' .. cfg.grid)
  end
  -- Horizontal separator line under day numbers
  gline(timeW, tb + 60 + 0.5, W - 14, tb + 60 + 0.5)
  if adH > 0 then
    gline(timeW, gridTop + 0.5, W - 14, gridTop + 0.5)
  end
  -- Vertical lines between days
  for i = 0, 7 do
    gline(timeW + i * dayW + 0.5, tb + 6, timeW + i * dayW + 0.5, gridBottom)
  end
  -- Horizontal lines for each hour
  for h = 0, hours do
    local y = gridTop + pad + h * hourH
    gline(timeW, y + 0.5, W - 14, y + 0.5)
  end
  for k = g + 1, GRID_POOL do
    local key = (k == 1) and 'Shape' or ('Shape' .. k)
    set('Grid', key, 'Rectangle 0,0,1,1 | Fill Color 0,0,0,0 | StrokeWidth 0')
  end

  -- Toolbar
  local tbItems = { 'CalLogo', 'CalLogoTxt', 'CalAppTitle', 'BtnToday', 'BtnTodayTxt', 'BtnPrev', 'BtnPrevTxt', 'BtnNext', 'BtnNextTxt',
                    'TbTitle', 'TbWeekBg', 'TbWeek', 'TbSync' }
  if cfg.toolbar then
    local cy = tb / 2
    local _, _, todayD = civilFromDays(todayDay)
    set('CalLogo', 'X', 20); set('CalLogo', 'Y', fmt(cy - 16))
    set('CalLogo', 'W', 32); set('CalLogo', 'H', 32)
    set('CalLogo', 'Shape', 'Rectangle 0,0,32,32,8 | Fill Color ' .. cfg.today .. ' | StrokeWidth 0')
    set('CalLogoTxt', 'X', 36); set('CalLogoTxt', 'Y', fmt(cy)); set('CalLogoTxt', 'Text', todayD)
    set('CalAppTitle', 'X', 62); set('CalAppTitle', 'Y', fmt(cy)); set('CalAppTitle', 'Text', 'Calendar')
    set('CalAppTitle', 'FontColor', cfg.dayNum)

    set('BtnToday', 'X', 142); set('BtnToday', 'Y', fmt(cy - 16))
    set('BtnToday', 'W', 72); set('BtnToday', 'H', 32)
    set('BtnToday', 'Shape', 'Rectangle 0,0,72,32,16 | Fill Color 0,0,0,1 | StrokeWidth 1 | Stroke Color ' .. cfg.border)
    set('BtnTodayTxt', 'X', 178); set('BtnTodayTxt', 'Y', fmt(cy)); set('BtnTodayTxt', 'Text', lang.today)
    set('BtnTodayTxt', 'FontColor', cfg.dayNum)

    set('BtnPrev', 'X', 217); set('BtnPrev', 'Y', fmt(cy - 15))
    set('BtnPrev', 'W', 30); set('BtnPrev', 'H', 30)
    set('BtnPrev', 'Shape', 'Ellipse 15,15,15 | Fill Color 0,0,0,1 | StrokeWidth 0')
    set('BtnPrevTxt', 'X', 232); set('BtnPrevTxt', 'Y', fmt(cy - 1)); set('BtnPrevTxt', 'Text', '<')
    set('BtnPrevTxt', 'FontColor', cfg.muted)

    set('BtnNext', 'X', 249); set('BtnNext', 'Y', fmt(cy - 15))
    set('BtnNext', 'W', 30); set('BtnNext', 'H', 30)
    set('BtnNext', 'Shape', 'Ellipse 15,15,15 | Fill Color 0,0,0,1 | StrokeWidth 0')
    set('BtnNextTxt', 'X', 264); set('BtnNextTxt', 'Y', fmt(cy - 1)); set('BtnNextTxt', 'Text', '>')
    set('BtnNextTxt', 'FontColor', cfg.muted)

    local y1, m1 = civilFromDays(ws)
    local y2, m2 = civilFromDays(ws + 6)
    local title
    if y1 == y2 and m1 == m2 then
      title = lang.months[m1] .. ' ' .. y1
    elseif y1 == y2 then
      title = usub(lang.months[m1], 1, 3) .. ' - ' .. usub(lang.months[m2], 1, 3) .. ' ' .. y1
    else
      title = usub(lang.months[m1], 1, 3) .. ' ' .. y1 .. ' - ' .. usub(lang.months[m2], 1, 3) .. ' ' .. y2
    end
    set('TbTitle', 'X', 296); set('TbTitle', 'Y', fmt(cy)); set('TbTitle', 'Text', title)
    set('TbTitle', 'FontColor', cfg.dayNum)
    local titlePx = N('TitleFontSize', 16) * 4 / 3
    local wkX = 296 + ulen(title) * titlePx * 0.52 + 18
    local wk = lang.week .. ' ' .. isoWeek(ws + 3)
    local wkW = math.max(68, ulen(wk) * 7.5 + 20)
    set('TbWeekBg', 'X', fmt(wkX)); set('TbWeekBg', 'Y', fmt(cy - 11))
    set('TbWeekBg', 'W', fmt(wkW)); set('TbWeekBg', 'H', 22)
    set('TbWeekBg', 'Shape', 'Rectangle 0,0,' .. fmt(wkW) .. ',22,11 | Fill Color ' .. cfg.badgeBg .. ' | StrokeWidth 0')
    set('TbWeek', 'X', fmt(wkX + wkW / 2)); set('TbWeek', 'Y', fmt(cy)); set('TbWeek', 'Text', wk)
    set('TbWeek', 'FontColor', cfg.badgeText)

    local sync = ''
    if finishSeen and lastSync then sync = lang.updated .. ' ' .. hhmm(lastSync) end
    local hasErr = false
    for i = 1, 3 do if netErrs[i] then hasErr = true end end
    if hasErr then sync = sync .. ((sync ~= '') and ' - ' or '') .. lang.offline end
    set('TbSync', 'X', fmt(W - 20)); set('TbSync', 'Y', fmt(cy)); set('TbSync', 'Text', sync)
    for _, m in ipairs(tbItems) do show(m) end
  else
    for _, m in ipairs(tbItems) do hide(m) end
  end

  set('TzLabel', 'X', timeW - 12); set('TzLabel', 'Y', fmt(tb + 20))
  set('TzLabel', 'Text', tzLabel(now))

  -- Vertical hour scroll buttons in the time gutter
  if startH > 0 then
    set('BtnUpHour', 'X', fmt(timeW / 2 - 12)); set('BtnUpHour', 'Y', fmt(gridTop - 27))
    set('BtnUpHour', 'W', 24); set('BtnUpHour', 'H', 18)
    set('BtnUpHour', 'Shape', 'Rectangle 0,0,24,18,4 | Fill Color 0,0,0,1 | StrokeWidth 0')
    set('BtnUpHourTxt', 'X', fmt(timeW / 2)); set('BtnUpHourTxt', 'Y', fmt(gridTop - 18))
    show('BtnUpHour'); show('BtnUpHourTxt')
  else
    hide('BtnUpHour'); hide('BtnUpHourTxt')
  end

  if startH < maxStartH then
    set('BtnDownHour', 'X', fmt(timeW / 2 - 12)); set('BtnDownHour', 'Y', fmt(gridBottom - 20))
    set('BtnDownHour', 'W', 24); set('BtnDownHour', 'H', 18)
    set('BtnDownHour', 'Shape', 'Rectangle 0,0,24,18,4 | Fill Color 0,0,0,1 | StrokeWidth 0')
    set('BtnDownHourTxt', 'X', fmt(timeW / 2)); set('BtnDownHourTxt', 'Y', fmt(gridBottom - 11))
    show('BtnDownHour'); show('BtnDownHourTxt')
  else
    hide('BtnDownHour'); hide('BtnDownHourTxt')
  end

  -- Day headers
  local todayIdx = todayDay - ws
  for i = 0, 6 do
    local wd = (cfg.firstDay + i) % 7
    local cx = timeW + i * dayW + dayW / 2
    local _, _, dnum = civilFromDays(ws + i)
    set('DayName' .. i, 'X', fmt(cx)); set('DayName' .. i, 'Y', fmt(tb + 14))
    set('DayName' .. i, 'Text', lang.days[wd + 1])
    set('DayName' .. i, 'FontColor', (i == todayIdx) and cfg.today or cfg.muted)
    set('DayNum' .. i, 'X', fmt(cx)); set('DayNum' .. i, 'Y', fmt(tb + 38))
    set('DayNum' .. i, 'Text', dnum)
    set('DayNum' .. i, 'FontColor', (i == todayIdx) and cfg.todayText or cfg.dayNum)
  end
  if todayIdx >= 0 and todayIdx <= 6 then
    local cx = timeW + todayIdx * dayW + dayW / 2
    set('TodayCircle', 'Shape', 'Ellipse ' .. fmt(cx) .. ',' .. fmt(tb + 38) .. ',18 | Fill Color ' .. cfg.today .. ' | StrokeWidth 0')
    show('TodayCircle')
  else
    hide('TodayCircle')
  end

  -- Hour labels
  for h = 0, hours do
    local idx = h + 1
    local y = gridTop + pad + h * hourH
    local hr = startH + h
    local label = (hr == 24) and '24:00' or string.format('%02d:00', hr % 24)
    set('HL' .. idx, 'X', timeW - 12); set('HL' .. idx, 'Y', fmt(y))
    set('HL' .. idx, 'Text', label)
    show('HL' .. idx)
  end
  for idx = hours + 2, used.hl do hide('HL' .. idx) end
  used.hl = hours + 1

  -- All-day events
  local adUsed = 0
  for i = 0, 6 do
    local list = days[i].allday
    local n = #list
    for r = 1, math.min(3, n) do
      adUsed = adUsed + 1
      if adUsed > AD_POOL then break end
      local it = list[r]
      local x = timeW + i * dayW + 3
      local y = tb + hdr + 3 + (r - 1) * 22
      local w = dayW - 12
      local label = it.title
      if r == 3 and n > 3 then label = '+' .. (n - 2) .. ' ' .. lang.more end
      set('ADBg' .. adUsed, 'X', fmt(x)); set('ADBg' .. adUsed, 'Y', fmt(y))
      set('ADBg' .. adUsed, 'W', fmt(w)); set('ADBg' .. adUsed, 'H', 20)
      set('ADBg' .. adUsed, 'Shape', 'Rectangle 0,0,' .. fmt(w) .. ',20,' .. cfg.radius
        .. ' | Fill Color ' .. colStr(cfg.colors[it.feed]) .. ' | StrokeWidth 0')
      local adTip = safe(it.title)
      if it.loc ~= '' then adTip = adTip .. '#CRLF#' .. safe(it.loc) end
      set('ADBg' .. adUsed, 'ToolTipText', adTip)
      show('ADBg' .. adUsed)
      local lines = wrapText(safe(label), (w - 16) / (px * 0.5), 1)
      set('ADTx' .. adUsed, 'X', fmt(x + 8)); set('ADTx' .. adUsed, 'Y', fmt(y + 10))
      set('ADTx' .. adUsed, 'W', fmt(w - 16)); set('ADTx' .. adUsed, 'H', 18)
      set('ADTx' .. adUsed, 'Text', lines[1] or '')
      set('ADTx' .. adUsed, 'ToolTipText', adTip)
      show('ADTx' .. adUsed)
    end
  end
  for idx = adUsed + 1, used.ad do
    set('ADBg' .. idx, 'ToolTipText', '')
    set('ADTx' .. idx, 'ToolTipText', '')
    hide('ADBg' .. idx); hide('ADTx' .. idx)
  end
  used.ad = adUsed

  -- Timed events
  local evUsed = 0
  local overflow = 0
  local colPad = 4
  local dayInnerW = dayW - colPad * 2
  for i = 0, 6 do
    local segs = days[i].segs
    packDay(segs)
    for _, sg in ipairs(segs) do
      if evUsed >= EV_POOL then
        overflow = overflow + 1
      else
        local it = sg.it
        local topMin, botMin = startH * 60, endH * 60
        local s, e = math.max(sg.s, topMin), math.min(sg.eEff, botMin)
        if e > s then
          evUsed = evUsed + 1
          local idx = evUsed
          local avail = (dayInnerW - (sg.ncols - 1) * 3) / sg.ncols
          local x = timeW + i * dayW + colPad + (sg.col - 1) * (avail + 3)
          local w = avail
          local y = gridTop + pad + (s - topMin) / 60 * hourH + 1
          local rawH = (e - s) / 60 * hourH - 2
          local maxAvailH = gridBottom - 1 - y
          local h = math.min(maxAvailH, math.max(16, rawH))
          if h < 10 then h = 10 end
          local past = it.e < now
          local fill = past and colStr(cfg.pastColors[it.feed]) or colStr(cfg.colors[it.feed])
          local tcol = past and cfg.pastText or cfg.evText

          set('EvBg' .. idx, 'X', fmt(x)); set('EvBg' .. idx, 'Y', fmt(y))
          set('EvBg' .. idx, 'W', fmt(w)); set('EvBg' .. idx, 'H', fmt(h))
          set('EvBg' .. idx, 'Shape', 'Rectangle 0,0,' .. fmt(w) .. ',' .. fmt(h) .. ','
            .. cfg.radius .. ' | Fill Color ' .. fill .. ' | StrokeWidth 0')
          local tip = safe(it.title) .. '#CRLF#' .. hhmm(it.s) .. ' - ' .. hhmm(it.e)
          if it.loc ~= '' then tip = tip .. '#CRLF#' .. safe(it.loc) end
          set('EvBg' .. idx, 'ToolTipText', tip)
          show('EvBg' .. idx)

          local padX, padY = 8, 5
          local tw = w - padX * 2
          local avl = math.floor((h - padY * 2 + 2) / lh)
          if avl < 1 then avl = 1 end
          local title = safe(it.title)
          local cpl = tw / (px * 0.54)
          local range = hhmm(it.s) .. ' - ' .. hhmm(it.e)
          local tl
          if avl == 1 then
            tl = wrapText(title .. ', ' .. hhmm(it.s), cpl, 1)
          else
            tl = wrapText(title, cpl, avl > 2 and 2 or 1)
          end
          local detail = {}
          local remain = avl - #tl
          if remain >= 1 and avl > 1 then
            if ulen(range) * px * 0.5 > tw then range = hhmm(it.s) end
            detail[#detail + 1] = range
          end
          if remain >= 2 and it.loc ~= '' then detail[#detail + 1] = safe(it.loc) end

          set('EvT' .. idx, 'X', fmt(x + padX)); set('EvT' .. idx, 'Y', fmt(y + padY))
          set('EvT' .. idx, 'W', fmt(tw)); set('EvT' .. idx, 'H', fmt(#tl * lh + 1))
          set('EvT' .. idx, 'FontColor', tcol)
          set('EvT' .. idx, 'Text', table.concat(tl, '#CRLF#'))
          set('EvT' .. idx, 'ToolTipText', tip)
          show('EvT' .. idx)
          if #detail > 0 then
            set('EvD' .. idx, 'X', fmt(x + padX)); set('EvD' .. idx, 'Y', fmt(y + padY + #tl * lh))
            set('EvD' .. idx, 'W', fmt(tw)); set('EvD' .. idx, 'H', fmt(#detail * lh + 1))
            set('EvD' .. idx, 'FontColor', tcol)
            set('EvD' .. idx, 'Text', table.concat(detail, '#CRLF#'))
            set('EvD' .. idx, 'ToolTipText', tip)
            show('EvD' .. idx)
          else
            set('EvD' .. idx, 'ToolTipText', '')
            hide('EvD' .. idx)
          end
        end
      end
    end
  end
  for idx = evUsed + 1, used.ev do
    set('EvBg' .. idx, 'ToolTipText', '')
    set('EvT' .. idx, 'ToolTipText', '')
    set('EvD' .. idx, 'ToolTipText', '')
    hide('EvBg' .. idx); hide('EvT' .. idx); hide('EvD' .. idx)
  end
  used.ev = evUsed

  -- Status messages
  local anyUrl = false
  for k = 1, 3 do if validUrl(cfg.urls[k]) then anyUrl = true end end
  if not anyUrl then setStatus(lang.noUrl)
  elseif not loadedAny then setStatus(loadErr and { loadErr } or lang.loading)
  else setStatus(nil) end
  if overflow > 0 then
    SKIN:Bang('!Log', 'WeeklyCalendar: ' .. overflow .. ' events omitted (maximum ' .. EV_POOL .. ' per week)', 'Warning')
  end

  -- Geometry cache for now line
  cfg.geo = { timeW = timeW, dayW = dayW, gridTop = gridTop, pad = pad, hourH = hourH,
              startH = startH, endH = endH, ws = ws }
  lastNow = nil
  SKIN:Bang('!UpdateMeterGroup', 'Cal')
  SKIN:Bang('!Redraw')
  needLayout = false
end

local function updateNowLine()
  local g = cfg.geo
  if not g then return end
  local now = os.time()
  local todayDay, nowMin = localDayOf(now)
  local idx = todayDay - g.ws
  local key
  local y, x
  if idx < 0 or idx > 6 or nowMin < g.startH * 60 or nowMin > g.endH * 60 then
    key = 'hidden'
  else
    y = g.gridTop + g.pad + (nowMin - g.startH * 60) / 60 * g.hourH
    x = g.timeW + idx * g.dayW
    key = fmt(x) .. ',' .. fmt(y)
  end
  if key == lastNow then return end
  lastNow = key
  if y then
    set('NowLine', 'Shape', 'Line ' .. fmt(x) .. ',' .. fmt(y) .. ',' .. fmt(x + g.dayW) .. ',' .. fmt(y)
      .. ' | StrokeWidth 2 | Stroke Color ' .. cfg.now)
    set('NowLine', 'Shape2', 'Ellipse ' .. fmt(x) .. ',' .. fmt(y) .. ',5 | Fill Color ' .. cfg.now .. ' | StrokeWidth 0')
    show('NowLine')
    SKIN:Bang('!UpdateMeter', 'NowLine')
  else
    hide('NowLine')
  end
  SKIN:Bang('!Redraw')
end

------------------------------------------------------------------------
-- Rainmeter Entry Points
------------------------------------------------------------------------
function Initialize()
  readSettings()
  for i = 1, 3 do
    if not validUrl(cfg.urls[i]) then
      SKIN:Bang('!DisableMeasure', 'MeasureICS' .. i)
    else
      SKIN:Bang('!EnableMeasure', 'MeasureICS' .. i)
    end
  end
end

local function safeLayout()
  local ok, err = pcall(layout)
  if not ok then
    SKIN:Bang('!Log', 'WeeklyCalendar: ' .. tostring(err), 'Error')
    setStatus({ 'Error: ' .. safe(tostring(err)) })
    SKIN:Bang('!UpdateMeterGroup', 'Cal')
    SKIN:Bang('!Redraw')
  end
end

function Update()
  local now = os.time()
  if not started then
    started = true
    pollFiles()
    needLayout = true
  elseif now - lastPoll >= (loadedAny and 30 or 10) then
    if pollFiles() then needLayout = true end
  end

  local today, nowMin = localDayOf(now)
  if today ~= lastToday then
    lastToday = today
    userScrollH = nil
    needLayout = true
  end

  -- Auto-scroll transition check for evening hours
  if weekOffset == 0 and cfg.autoScroll and userScrollH == nil then
    local nowH = math.floor(nowMin / 60)
    local autoShift = (nowH >= cfg.autoScrollHour) and 1 or 0
    if autoShift ~= lastAutoShift then
      lastAutoShift = autoShift
      needLayout = true
    end
  end

  if needLayout then safeLayout() end
  updateNowLine()
  return 0
end

-- Called when WebParser download finishes
function Reload()
  finishSeen = true
  lastSync = os.time()
  netErrs = {}
  pollFiles()
  safeLayout()
  updateNowLine()
end

function NetError(i)
  if validUrl(cfg.urls[i]) then
    netErrs[i] = true
    needLayout = true
  end
end

function ShiftWeek(n)
  weekOffset = weekOffset + n
  userScrollH = nil
  safeLayout()
  updateNowLine()
end

function GoToday()
  weekOffset = 0
  userScrollH = nil
  safeLayout()
  updateNowLine()
end

function ScrollHours(delta)
  local now = os.time()
  local _, nowMin = localDayOf(now)
  local curStartH, _, _, maxStartH = getVisibleHours(nowMin)
  local target = math.max(0, math.min(maxStartH, curStartH + delta))
  userScrollH = target
  safeLayout()
  updateNowLine()
end

function ResetScroll()
  userScrollH = nil
  safeLayout()
  updateNowLine()
end

function Refresh()
  for i = 1, 3 do
    if validUrl(cfg.urls[i]) then SKIN:Bang('!CommandMeasure', 'MeasureICS' .. i, 'Update') end
  end
end
