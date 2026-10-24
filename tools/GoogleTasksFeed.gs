/**
 * WeeklyCalendar - publishes your Google Tasks as an iCal (.ics) feed.
 *
 * Google Calendar's iCal addresses never include tasks, so this small Google Apps
 * Script reads them with your account and serves them at a private web address that
 * the skin downloads like any other calendar. Setup: README, "Showing Google Tasks".
 *
 * Tasks with a due date become all-day entries (the Tasks API only stores the date,
 * not the time). Completed tasks are marked with X-WC-TASK:COMPLETED.
 *
 * The same address also marks a task completed or not completed when the skin's
 * circle / check mark is clicked: ?action=complete|reopen&list=<list id>&task=<task id>,
 * and moves it to another day when it is dragged there:
 * ?action=move&list=<list id>&task=<task id>&due=YYYY-MM-DD (README, "Completing tasks").
 *
 * It also creates, edits and deletes tasks and Google Calendar events for the skin's
 * cards (README, "Creating and editing"); events need the advanced "Google Calendar API"
 * service:
 *   ?action=createtask&list=..&title=..&due=YYYY-MM-DD           -> OK <task id>
 *   ?action=edittask&list=..&task=..[&title=..][&due=YYYY-MM-DD] -> OK
 *   ?action=deletetask&list=..&task=..                           -> OK
 *   ?action=createevent&cal=..&title=..&start=<UTC>&end=<UTC>    -> OK <iCal UID>
 *                      (or &date=YYYY-MM-DD&days=N for an all-day event)
 *   ?action=editevent|moveevent&cal=..&uid=<iCal UID>[&orig=..][&title=..][&start=..&end=..|&date=..&days=..]
 *   ?action=deleteevent&cal=..&uid=..[&orig=..]&scope=one|all
 * "orig" is the original start of one occurrence of a recurring event (UTC, or the date
 * of an all-day event). Every answer is "OK ..." or "ERROR <reason>".
 *
 * The same address with ?feed=birthdays publishes the birthdays of your contacts, which
 * Google Calendar's iCal address leaves out (README, "Birthdays").
 *
 * Optional protection: with the script property WRITE_TOKEN set (Project Settings >
 * Script properties), every change needs &token=<that value> (TasksToken in the skin's
 * Private.inc). Reading the feed does not.
 */

var DAYS_BACK = 60;    // completed/overdue tasks older than this are left out
var DAYS_AHEAD = 400;  // and so are tasks due further ahead than this

var WRITE_ACTIONS = {
  complete: 1, reopen: 1, move: 1, createtask: 1, edittask: 1, deletetask: 1,
  createevent: 1, editevent: 1, moveevent: 1, deleteevent: 1
};

function doGet(e) {
  var p = (e && e.parameter) || {};
  if (WRITE_ACTIONS[p.action]) {
    return ContentService.createTextOutput(write(p));
  }
  var feed = p.feed === 'birthdays' ? buildBirthdays() : buildFeed();
  return ContentService.createTextOutput(feed).setMimeType(ContentService.MimeType.ICAL);
}

// A change asked by the skin: "OK [id]" or "ERROR <reason>"
function write(p) {
  var token = PropertiesService.getScriptProperties().getProperty('WRITE_TOKEN');
  if (token && p.token !== token) return 'ERROR bad token';
  switch (p.action) {
    case 'complete': case 'reopen': return setCompleted(p.list, p.task, p.action === 'complete');
    case 'move': return moveTask(p.list, p.task, p.due);
    case 'createtask': return createTask(p);
    case 'edittask': return editTask(p);
    case 'deletetask': return deleteTask(p);
    case 'createevent': return createEvent(p);
    case 'editevent': case 'moveevent': return editEvent(p);
    case 'deleteevent': return deleteEvent(p);
  }
  return 'ERROR unknown action';
}

// Answers "OK", or "ERROR <reason>" (the skin then shows the task as it was)
function setCompleted(listId, taskId, done) {
  if (!listId || !taskId) return 'ERROR missing list or task';
  try {
    // "completed" holds the completion time: it must be cleared to reopen a task
    Tasks.Tasks.patch(done ? { status: 'completed' } : { status: 'needsAction', completed: null },
                      listId, taskId);
    return 'OK';
  } catch (err) {
    return 'ERROR ' + err.message;
  }
}

// New due date (YYYY-MM-DD). The Tasks API stores only the date: it is midnight UTC
// of that day, as in the feed above.
function moveTask(listId, taskId, due) {
  if (!listId || !taskId) return 'ERROR missing list or task';
  if (!/^\d{4}-\d{2}-\d{2}$/.test(due || '')) return 'ERROR bad date';
  try {
    Tasks.Tasks.patch({ due: due + 'T00:00:00.000Z' }, listId, taskId);
    return 'OK';
  } catch (err) {
    return 'ERROR ' + err.message;
  }
}

var DATE = /^\d{4}-\d{2}-\d{2}$/;
var UTC_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?Z$/;

function badTitle(title) {
  return !title || title.length > 500;
}

// Day after date (YYYY-MM-DD) plus n - 1 days: the exclusive end of an all-day event
function addDays(date, n) {
  return new Date(Date.parse(date + 'T00:00:00Z') + n * 86400000).toISOString().substring(0, 10);
}

function createTask(p) {
  if (badTitle(p.title)) return 'ERROR bad title';
  if (!DATE.test(p.due || '')) return 'ERROR bad date';
  try {
    var t = Tasks.Tasks.insert({ title: p.title, notes: p.notes || undefined, due: p.due + 'T00:00:00.000Z' },
                               p.list || '@default');
    return 'OK ' + t.id;
  } catch (err) {
    return 'ERROR ' + err.message;
  }
}

// New title and / or due date; omitted fields stay as they are
function editTask(p) {
  if (!p.list || !p.task) return 'ERROR missing list or task';
  var patch = {};
  if (p.title !== undefined) {
    if (badTitle(p.title)) return 'ERROR bad title';
    patch.title = p.title;
  }
  if (p.due !== undefined) {
    if (!DATE.test(p.due)) return 'ERROR bad date';
    patch.due = p.due + 'T00:00:00.000Z';
  }
  try {
    Tasks.Tasks.patch(patch, p.list, p.task);
    return 'OK';
  } catch (err) {
    return 'ERROR ' + err.message;
  }
}

function deleteTask(p) {
  if (!p.list || !p.task) return 'ERROR missing list or task';
  try {
    Tasks.Tasks.remove(p.list, p.task);
    return 'OK';
  } catch (err) {
    return 'ERROR ' + err.message;
  }
}

// Start and end of an event from the request: { start, end } in the Calendar API format,
// null when the request has no times, or a string with the error
function eventTimes(p) {
  if (p.date !== undefined) {
    var days = parseInt(p.days || '1', 10);
    if (!DATE.test(p.date) || !(days >= 1 && days <= 366)) return 'ERROR bad date';
    return { start: { date: p.date }, end: { date: addDays(p.date, days) } };
  }
  if (p.start === undefined && p.end === undefined) return null;
  if (!UTC_TIME.test(p.start || '') || !UTC_TIME.test(p.end || '')) return 'ERROR bad time';
  if (Date.parse(p.end) <= Date.parse(p.start)) return 'ERROR end before start';
  return { start: { dateTime: p.start }, end: { dateTime: p.end } };
}

function createEvent(p) {
  if (badTitle(p.title)) return 'ERROR bad title';
  var times = eventTimes(p);
  if (!times) return 'ERROR bad time';
  if (typeof times === 'string') return times;
  try {
    var ev = Calendar.Events.insert({ summary: p.title, start: times.start, end: times.end }, p.cal || 'primary');
    return 'OK ' + ev.iCalUID;
  } catch (err) {
    if (/not ?found/i.test(err.message)) return 'ERROR calendar not found';
    return 'ERROR ' + err.message;
  }
}

// The event the skin means: found by its iCal UID (Google may give imported events
// another id), then, for one occurrence of a recurring event, the instance whose original
// start is p.orig. Returns { series, target } or a string with the error.
function findEvent(p) {
  if (!p.uid) return 'ERROR missing uid';
  var cal = p.cal || 'primary';
  var items = Calendar.Events.list(cal, { iCalUID: p.uid, showDeleted: false, maxResults: 5 }).items || [];
  var series = items.filter(function (x) { return !x.recurringEventId; })[0];
  if (!series) return 'ERROR event not found';
  if (!p.orig || !series.recurrence) return { series: series, target: series };
  var allDay = DATE.test(p.orig);
  var origMs = allDay ? null : Date.parse(p.orig);
  function matches(x) {
    var o = x.originalStartTime || {};
    return allDay ? o.date === p.orig : (o.dateTime !== undefined && Date.parse(o.dateTime) === origMs);
  }
  // The instance may have been moved anywhere: ask for it by its original start, then
  // look around that day
  var found = null;
  try {
    found = (Calendar.Events.instances(cal, series.id, { originalStart: p.orig, showDeleted: false }).items || [])
      .filter(matches)[0];
  } catch (err) {
    found = null; // e.g. a format of originalStart the API does not take: search instead
  }
  if (!found) {
    var at = allDay ? Date.parse(p.orig + 'T00:00:00Z') : origMs;
    found = (Calendar.Events.instances(cal, series.id, {
      timeMin: new Date(at - 8 * 86400000).toISOString(),
      timeMax: new Date(at + 9 * 86400000).toISOString(),
      showDeleted: false, maxResults: 250 }).items || []).filter(matches)[0];
  }
  if (!found) return 'ERROR occurrence not found';
  return { series: series, target: found };
}

// New title and / or times of an event, or of one occurrence (orig)
function editEvent(p) {
  var patch = {};
  if (p.title !== undefined) {
    if (badTitle(p.title)) return 'ERROR bad title';
    patch.summary = p.title;
  }
  var times = eventTimes(p);
  if (typeof times === 'string') return times;
  if (times) {
    patch.start = times.start;
    patch.end = times.end;
  }
  try {
    var ev = findEvent(p);
    if (typeof ev === 'string') return ev;
    Calendar.Events.patch(patch, p.cal || 'primary', ev.target.id);
    return 'OK';
  } catch (err) {
    return 'ERROR ' + err.message;
  }
}

// scope=one: the event, or only occurrence orig of a recurring one; scope=all: the series
function deleteEvent(p) {
  try {
    var ev = findEvent(p.scope === 'all' ? { cal: p.cal, uid: p.uid } : p);
    if (typeof ev === 'string') return ev;
    Calendar.Events.remove(p.cal || 'primary', ev.target.id);
    return 'OK';
  } catch (err) {
    return 'ERROR ' + err.message;
  }
}

// Run this once from the editor (Run > test) to grant access and preview the feed.
function test() {
  Logger.log(buildFeed().slice(0, 2000));
}

// Run this from the editor (Run > authorize) if the skin says "allow editing tasks":
// Google asks again for access to your tasks, then a change that leaves a task as it
// is checks that the script may now edit them.
function authorize() {
  var lists = Tasks.Tasklists.list({ maxResults: 1 }).items || [];
  var tasks = lists.length ? (Tasks.Tasks.list(lists[0].id, { maxResults: 1 }).items || []) : [];
  if (!tasks.length) {
    Logger.log('No task to check with: create one, then run authorize again.');
  } else {
    Tasks.Tasks.patch({ status: tasks[0].status }, lists[0].id, tasks[0].id);
    Logger.log('OK: the skin can now mark tasks completed. Deploy a new version if you have not yet.');
  }
  // Creating and changing events from the skin needs the Google Calendar API service
  if (typeof Calendar === 'undefined') {
    Logger.log('To create and change events from the skin, add the Google Calendar API service ' +
               '(+ next to Services), then run authorize again.');
    return;
  }
  Calendar.Calendars.get('primary');
  Logger.log('OK: the skin can now change your calendar too.');
}

function buildFeed() {
  var now = new Date();
  var stamp = Utilities.formatDate(now, 'UTC', "yyyyMMdd'T'HHmmss'Z'");
  var dueMin = new Date(now.getTime() - DAYS_BACK * 86400000).toISOString();
  var dueMax = new Date(now.getTime() + DAYS_AHEAD * 86400000).toISOString();
  var out = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//WeeklyCalendar//Google Tasks//EN',
             'CALSCALE:GREGORIAN', 'X-WR-CALNAME:Google Tasks'];

  var lists = allPages(function (args) {
    args.maxResults = 100;
    return Tasks.Tasklists.list(args);
  });
  lists.forEach(function (list) {
    var tasks = allPages(function (args) {
      args.showCompleted = true;
      args.showHidden = true;    // tasks completed in the Google apps are "hidden"
      args.showDeleted = false;
      args.dueMin = dueMin;
      args.dueMax = dueMax;
      args.maxResults = 100;
      return Tasks.Tasks.list(list.id, args);
    });
    tasks.forEach(function (t) {
      if (!t.due || t.deleted) return;
      out.push('BEGIN:VEVENT',
               'UID:' + t.id + '@tasks.google.com',
               'DTSTAMP:' + stamp,
               // "due" is midnight UTC of the chosen day: its date part is the day itself
               'DTSTART;VALUE=DATE:' + t.due.substring(0, 10).replace(/-/g, ''),
               'SUMMARY:' + esc(t.title || ''),
               'CATEGORIES:' + esc(list.title || 'Tasks'),
               'X-WC-TASK:' + (t.status === 'completed' ? 'COMPLETED' : 'NEEDS-ACTION'),
               // used by the skin to mark the task (un)completed
               'X-WC-TASKLIST:' + list.id,
               'X-WC-TASKID:' + t.id);
      if (t.notes) out.push('DESCRIPTION:' + esc(t.notes));
      out.push('END:VEVENT');
    });
  });

  out.push('END:VCALENDAR');
  return out.join('\r\n') + '\r\n';
}

// The birthdays of your contacts (?feed=birthdays): Google Calendar keeps them as
// "birthday" events of your primary calendar but leaves them out of its iCal address.
// Needs the Google Calendar API service (README, "Birthdays").
function buildBirthdays() {
  if (typeof Calendar === 'undefined') {
    return 'ERROR add the Google Calendar API service to the Tasks script (README, "Birthdays")';
  }
  var now = new Date();
  var stamp = Utilities.formatDate(now, 'UTC', "yyyyMMdd'T'HHmmss'Z'");
  var items;
  try {
    items = allPages(function (args) {
      args.eventTypes = ['birthday'];
      args.singleEvents = true;  // one entry per year, as the skin shows them
      args.timeMin = new Date(now.getTime() - DAYS_BACK * 86400000).toISOString();
      args.timeMax = new Date(now.getTime() + DAYS_AHEAD * 86400000).toISOString();
      args.maxResults = 2500;
      return Calendar.Events.list('primary', args);
    });
  } catch (err) {
    return 'ERROR ' + err.message;
  }
  var out = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//WeeklyCalendar//Birthdays//EN',
             'CALSCALE:GREGORIAN', 'X-WR-CALNAME:Birthdays'];
  items.forEach(function (ev) {
    if (ev.status === 'cancelled' || !ev.start || !ev.start.date) return;
    out.push('BEGIN:VEVENT',
             'UID:' + ev.id + '@birthdays.google.com',
             'DTSTAMP:' + stamp,
             'DTSTART;VALUE=DATE:' + ev.start.date.replace(/-/g, ''));
    if (ev.end && ev.end.date) out.push('DTEND;VALUE=DATE:' + ev.end.date.replace(/-/g, ''));
    out.push('SUMMARY:' + esc(ev.summary || ''));
    if (ev.htmlLink) out.push('URL:' + ev.htmlLink);  // a click opens it in Google Calendar
    out.push('END:VEVENT');
  });
  out.push('END:VCALENDAR');
  return out.join('\r\n') + '\r\n';
}

// Collects every page of a Tasks API list call
function allPages(fetch) {
  var items = [], token = null;
  do {
    var args = {};
    if (token) args.pageToken = token;
    var page = fetch(args);
    items = items.concat(page.items || []);
    token = page.nextPageToken;
  } while (token);
  return items;
}

// iCalendar TEXT escaping (RFC 5545 3.3.11)
function esc(s) {
  return String(s).replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,')
                  .replace(/\r?\n/g, '\\n');
}
