/**
 * WeeklyCalendar - publishes your Google Tasks as an iCal (.ics) feed.
 *
 * Google Calendar's iCal addresses never include tasks, so this small Google Apps
 * Script reads them with your account and serves them at a private web address that
 * the skin downloads like any other calendar. Setup: README, "Showing Google Tasks".
 *
 * Tasks with a due date become all-day entries (the Tasks API only stores the date,
 * not the time). Completed tasks are marked with X-WC-TASK:COMPLETED.
 */

var DAYS_BACK = 60;    // completed/overdue tasks older than this are left out
var DAYS_AHEAD = 400;  // and so are tasks due further ahead than this

function doGet() {
  return ContentService.createTextOutput(buildFeed()).setMimeType(ContentService.MimeType.ICAL);
}

// Run this once from the editor (Run > test) to grant access and preview the feed.
function test() {
  Logger.log(buildFeed().slice(0, 2000));
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
               'X-WC-TASK:' + (t.status === 'completed' ? 'COMPLETED' : 'NEEDS-ACTION'));
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
