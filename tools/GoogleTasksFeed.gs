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
 */

var DAYS_BACK = 60;    // completed/overdue tasks older than this are left out
var DAYS_AHEAD = 400;  // and so are tasks due further ahead than this

function doGet(e) {
  var p = (e && e.parameter) || {};
  if (p.action === 'complete' || p.action === 'reopen') {
    return ContentService.createTextOutput(setCompleted(p.list, p.task, p.action === 'complete'));
  }
  if (p.action === 'move') {
    return ContentService.createTextOutput(moveTask(p.list, p.task, p.due));
  }
  return ContentService.createTextOutput(buildFeed()).setMimeType(ContentService.MimeType.ICAL);
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
    return;
  }
  Tasks.Tasks.patch({ status: tasks[0].status }, lists[0].id, tasks[0].id);
  Logger.log('OK: the skin can now mark tasks completed. Deploy a new version if you have not yet.');
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
