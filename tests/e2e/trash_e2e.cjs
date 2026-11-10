// Recoverable deletion and Trash, in a real Nexus shell. Run against a disposable stack only:
// it empties Trash and deletes what it creates. All records are synthetic ("WP03 ...").
//
//   PLAYWRIGHT_PATH=.../node_modules/playwright BROWSER=chromium NEXUS_URL=http://localhost:12398 \
//     OWNER_FILE=owner.json [SHOTS=dir] [RESULTS=file.json] node tests/e2e/trash_e2e.cjs [filter]
//
// The sign-in is reused across journeys: Nexus allows 10 sign-ins per client per 5 minutes.
const fs = require("fs");
const playwright = require(process.env.PLAYWRIGHT_PATH || "playwright");

const NEXUS = process.env.NEXUS_URL;
const ENGINE = process.env.BROWSER || "chromium";
const FILTER = process.argv[2] || "";
const SHOTS = process.env.SHOTS || "";
const RUN = Date.now().toString(36);
const owner = JSON.parse(fs.readFileSync(process.env.OWNER_FILE, "utf8"));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
let current = "";
const record = (status, what, detail) => {
  results.push({ journey: current, status, what, ...(detail ? { detail } : {}) });
  console.log(`${status.padEnd(4)} [${current}] ${what}${detail ? ` -- ${detail}` : ""}`);
};
const check = (ok, what, detail) => {
  if (!ok) {
    record("FAIL", what, detail);
    throw new Error(`failed: ${what}`);
  }
  record("ok", what);
};
async function until(fn, what, ms = 15000) {
  const end = Date.now() + ms;
  let last;
  while (Date.now() < end) {
    try {
      last = await fn();
      if (last) {
        record("ok", what);
        return last;
      }
    } catch (error) {
      last = error.message.slice(0, 200);
    }
    await sleep(80);
  }
  check(false, `${what} (timed out)`, typeof last === "string" ? last : undefined);
}
const route = (page) => new URL(page.url()).searchParams.get("route");
const appFrame = async (page) => (await page.locator("#module-application").elementHandle({ timeout: 20000 })).contentFrame();
async function open(page, reference) {
  await page.goto(`${NEXUS}/app/modules/chronos${reference ? `?nav=1&route=${encodeURIComponent(reference)}` : ""}`);
  await page.locator("#username, #module-application").first().waitFor({ timeout: 30000 });
  if (await page.locator("#username").isVisible()) {
    await page.locator("#username").fill(owner.username);
    await page.locator("#password").fill(owner.password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
  }
  const end = Date.now() + 25000;
  while (Date.now() < end) {
    try {
      const frame = await appFrame(page);
      if (frame && (await frame.evaluate(() => globalThis.eval('typeof chronosNavigation !== "undefined" && chronosNavigation.enabled')))) return frame;
    } catch {
      /* the frame is replaced during start-up */
    }
    await sleep(100);
  }
  check(false, "Chronos negotiated navigation");
}
const call = (frame, p, method = "GET", body) =>
  frame.evaluate(([x, m, b]) => (b === null ? api(x, m) : api(x, m, b)), [p, method, body === undefined ? null : body]);
const atRoute = (page, expected) => until(() => route(page) === expected, `address is ${expected}`);
const shot = async (page, name) => {
  if (SHOTS) {
    await sleep(350);
    await page.screenshot({ path: `${SHOTS}/${ENGINE}-${name}.png` });
  }
};

let page;
let frame;
let today;
let calendarId;
let zone;

async function clearAll() {
  for (const offset of [-30, 0, 30, 60]) {
    const a = await frame.evaluate((n) => zonedToUtc(addDays(today(), n)).toISOString().replace(".000", ""), offset);
    const b = await frame.evaluate((n) => zonedToUtc(addDays(today(), n + 40)).toISOString().replace(".000", ""), offset);
    for (const o of (await call(frame, `/occurrences?start=${encodeURIComponent(a)}&end=${encodeURIComponent(b)}`)).occurrences) {
      if (/^(WP03|Seeded)/.test(o.title)) await call(frame, `/events/${o.event_id}?scope=series`, "DELETE").catch(() => {});
    }
  }
  const trash = await call(frame, "/trash");
  await call(frame, "/trash/empty", "POST", { confirmed: true, expected: trash.total });
}
const addEvent = (title, extra = {}) =>
  call(frame, "/events", "POST", { calendar_id: calendarId, title, start: `${today}T10:00`, end: `${today}T11:00`, time_zone: zone, ...extra });
const addWeekly = (title, extra = {}) => addEvent(title, { rrule: "FREQ=WEEKLY;COUNT=6", start: `${today}T12:00`, end: `${today}T13:00`, ...extra });
async function ready(reference) {
  frame = await open(page, reference);
  await until(() => frame.locator("#view .month, #view .trash, #view .ae-empty, #view .agenda, #view .week").first().isVisible(), "the screen rendered");
}
const refreshCalendar = () => frame.evaluate(() => refresh());
const chipFor = (id) => frame.locator(`[data-open^="${id}/"]`).first();
const toastText = () => frame.locator(".ae-toast").last().innerText();
async function openEventFromMonth(id) {
  await refreshCalendar();
  await until(() => chipFor(id).isVisible(), "the event is on the month");
  await chipFor(id).click();
  await until(() => frame.locator(".ae-drawer:not(.is-leaving)").isVisible(), "details opened");
}
async function chooseMenu(label) {
  await frame.locator('[data-act="event-menu"]').click();
  await until(() => frame.locator(".ae-menu").isVisible(), "the menu opened");
  await frame.locator(".ae-menu-item", { hasText: label }).click();
}
async function occurrenceKey(id, offset = 0) {
  const a = await frame.evaluate(() => zonedToUtc(today()).toISOString().replace(".000", ""));
  const b = await frame.evaluate(() => zonedToUtc(addDays(today(), 60)).toISOString().replace(".000", ""));
  const all = (await call(frame, `/occurrences?start=${encodeURIComponent(a)}&end=${encodeURIComponent(b)}`)).occurrences.filter((o) => o.event_id === id);
  return { occurrence: all[offset].occurrence, count: all.length };
}
const active = async (id) => occurrenceKey(id).then((r) => r.count).catch(() => 0);

const J = {};

J["delete-event-then-undo"] = async () => {
  const event = await addEvent(`WP03 undo ${RUN}`);
  await ready(`/month/${today}`);
  await openEventFromMonth(event.id);
  await chooseMenu("Delete event");
  await until(() => frame.locator("#dialog h2").innerText().then((t) => t.includes("Move")), "the confirmation names Trash");
  await shot(page, "confirm-move");
  await frame.locator("#confirm").click();
  await until(() => frame.locator(".ae-toast", { hasText: "Moved to Trash" }).isVisible(), "the toast says it moved to Trash");
  await atRoute(page, `/month/${today}`);
  await until(async () => (await chipFor(event.id).count()) === 0, "the event left the calendar");
  await shot(page, "after-delete-toast");
  await frame.locator(".ae-toast [data-toast-action]").click();
  await until(() => chipFor(event.id).isVisible(), "Undo put it back on the calendar");
  await until(() => frame.locator(".ae-toast", { hasText: "Event restored" }).isVisible(), "the toast confirms the restore");
  const back = await call(frame, `/events/${event.id}`);
  check(back.id === event.id && back.created_at === event.created_at, "the same event came back");
  check((await call(frame, "/trash")).total === 0, "Trash is empty again");
};

J["trash-screen-search-history"] = async () => {
  const a = await addEvent(`WP03 Kaviareň ${RUN}`);
  const b = await addEvent(`WP03 other ${RUN}`);
  await call(frame, `/events/${a.id}`, "DELETE");
  await call(frame, `/events/${b.id}`, "DELETE");
  await ready(`/month/${today}`);
  await frame.locator('[data-act="trash"]').click();
  await atRoute(page, "/trash");
  await until(() => frame.locator(".trash-row").count().then((n) => n === 2), "both deleted events are listed");
  check((await frame.locator(".trash-row .trash-time").first().innerText()).startsWith("Deleted"), "each row says when it was deleted");
  check((await frame.locator(".side-count").innerText()) === "2", "the sidebar counts Trash");
  await shot(page, "trash-list");
  await frame.locator("#search").fill("kaviaren");
  await until(() => frame.locator(".trash-row").count().then((n) => n === 1), "accent-insensitive search narrows the list");
  check(route(page) === "/trash", "search text stays out of the address");
  await frame.locator("#search").fill("no such thing");
  await until(() => frame.locator(".ae-empty h3").innerText().then((t) => t.includes("Nothing in Trash matches")), "no results are explained");
  await frame.locator("#search").fill("");
  await until(() => frame.locator(".trash-row").count().then((n) => n === 2), "clearing the search shows everything");
  await frame.locator(".trash-row .trash-open").first().click();
  await until(() => /^\/trash\/[0-9a-f-]{36}$/.test(route(page) || ""), "details have their own address");
  await until(() => frame.locator(".trash-drawer:not(.is-leaving)").isVisible(), "details opened");
  await shot(page, "trash-details");
  await page.goBack();
  await atRoute(page, "/trash");
  await until(async () => (await frame.locator(".trash-drawer:not(.is-leaving)").count()) === 0, "Back closed the details");
  await page.goBack();
  await atRoute(page, `/month/${today}`);
  await until(() => frame.locator("#view .month").isVisible(), "Back returned to the calendar");
  await page.goForward();
  await atRoute(page, "/trash");
  await until(() => frame.locator(".trash-row").count().then((n) => n === 2), "Forward returned to Trash");
  await frame.locator('[data-act="back-calendar"]').click();
  await atRoute(page, `/month/${today}`);
  await until(() => frame.locator("#view .month").isVisible(), "Back to calendar works");
};

J["restore-from-trash-and-show"] = async () => {
  const event = await addEvent(`WP03 restore ${RUN}`);
  await call(frame, `/events/${event.id}`, "DELETE");
  await ready("/trash");
  await until(() => frame.locator(".trash-row").count().then((n) => n === 1), "listed");
  await frame.locator('.trash-row [data-act="trash-restore"]').click();
  await until(() => frame.locator(".ae-toast", { hasText: "Event restored" }).isVisible(), "restored");
  await until(() => frame.locator(".ae-empty h3").innerText().then((t) => t === "Trash is empty"), "the list is empty");
  await frame.locator('.ae-toast [data-toast-action]').click();
  await until(() => (route(page) || "").startsWith(`/events/${event.id}`), "Show opens the restored event");
  await until(() => frame.locator(".ae-drawer:not(.is-leaving)").isVisible(), "its details open");
};

J["permanent-delete"] = async () => {
  const event = await addEvent(`WP03 purge ${RUN}`);
  await call(frame, `/events/${event.id}`, "DELETE");
  await ready("/trash");
  await until(() => frame.locator(".trash-row").count().then((n) => n === 1), "listed");
  await frame.locator('.trash-row [data-act="trash-purge"]').click();
  await until(() => frame.locator("#dialog h2").innerText().then((t) => t.includes("for good")), "permanent deletion is confirmed separately");
  check(await frame.evaluate(() => document.activeElement?.textContent === "Cancel"), "Cancel has the initial focus");
  await shot(page, "confirm-purge");
  await frame.locator('#dialog [data-act="dialog-cancel"]').click();
  await until(async () => !(await frame.evaluate(() => dialog().open)), "Cancel closes the dialog");
  check((await call(frame, "/trash")).total === 1, "Cancel deleted nothing");
  await frame.locator('.trash-row [data-act="trash-purge"]').click();
  await until(() => frame.locator("#confirm").isVisible(), "asked again");
  await frame.locator("#confirm").click();
  await until(() => frame.locator(".ae-toast", { hasText: "Deleted for good" }).isVisible(), "gone for good");
  await ready(`/events/${event.id}`);
  await until(() => frame.locator(".ae-empty h3").innerText().then((t) => t.includes("could not be found")), "its link now reports it as not found");
};

J["empty-trash-safeguards"] = async () => {
  const keep = await addEvent(`WP03 keep ${RUN}`);
  const one = await addEvent(`WP03 gone one ${RUN}`);
  const two = await addEvent(`WP03 gone two ${RUN}`);
  const late = await addEvent(`WP03 late ${RUN}`);
  await call(frame, `/events/${one.id}`, "DELETE");
  await call(frame, `/events/${two.id}`, "DELETE");
  await ready("/trash");
  await until(() => frame.locator(".trash-row").count().then((n) => n === 2), "listed");
  await frame.locator('[data-act="trash-empty"]').click();
  await until(() => frame.locator("#confirm").isVisible(), "Empty Trash asks first");
  check(await frame.locator("#confirm").isDisabled(), "the button is disabled until the box is ticked");
  await shot(page, "confirm-empty");
  await frame.locator("#confirm-check").check();
  check(await frame.locator("#confirm").isEnabled(), "ticking the box enables it");
  // Something else lands in Trash after the dialog was opened.
  await call(frame, `/events/${late.id}`, "DELETE");
  await frame.locator("#confirm").click();
  await until(() => frame.locator("#confirm-error").innerText().then((t) => t.includes("changed")), "a changed Trash is not emptied");
  check((await call(frame, "/trash")).total === 3, "nothing was deleted");
  await frame.locator('#dialog [data-act="dialog-cancel"]').click();
  await until(async () => !(await frame.evaluate(() => dialog().open)), "the dialog closes");
  await until(() => frame.locator(".trash-row").count().then((n) => n === 3), "the list shows the newcomer");
  await frame.locator('[data-act="trash-empty"]').click();
  await until(() => frame.locator("#confirm-check").isVisible(), "asked again");
  await frame.locator("#confirm-check").check();
  await frame.locator("#confirm").click();
  await until(() => frame.locator(".ae-toast", { hasText: "Trash emptied" }).isVisible(), "emptied");
  check((await call(frame, "/trash")).total === 0, "Trash is empty");
  check((await call(frame, `/events/${keep.id}`)).id === keep.id, "active events are untouched");
};

J["occurrence-versus-series"] = async () => {
  const series = await addWeekly(`WP03 weekly ${RUN}`);
  const { occurrence, count } = await occurrenceKey(series.id);
  await ready(`/month/${today}`);
  await openEventFromMonth(series.id);
  await frame.locator('[data-act="event-menu"]').click();
  await until(() => frame.locator(".ae-menu").isVisible(), "the menu opened");
  check((await frame.locator(".ae-menu-item").allInnerTexts()).join("|").includes("Delete this occurrence"), "one occurrence is offered");
  check((await frame.locator(".ae-menu-item").allInnerTexts()).join("|").includes("Delete all occurrences"), "the whole series is offered separately");
  await frame.locator(".ae-menu-item", { hasText: "Delete this occurrence" }).click();
  await until(() => frame.locator("#dialog p").first().innerText().then((t) => t.includes("other occurrences stay")), "the dialog promises the series stays");
  await frame.locator("#confirm").click();
  await until(() => frame.locator(".ae-toast", { hasText: "Occurrence moved to Trash" }).isVisible(), "the occurrence moved");
  check((await active(series.id)) === count - 1, "only one occurrence left the calendar");
  let trash = await call(frame, "/trash");
  check(trash.items[0].kind === "occurrence" && trash.items[0].occurrence === occurrence, "Trash holds exactly that occurrence");
  await frame.locator('.ae-toast [data-toast-action]').first().click();
  await until(async () => (await active(series.id)) === count, "Undo restored the occurrence");

  await openEventFromMonth(series.id);
  await chooseMenu("Delete all occurrences");
  await until(() => frame.locator("#dialog h2").innerText().then((t) => t.includes("whole series")), "the dialog names the whole series");
  await frame.locator("#confirm").click();
  await until(() => frame.locator(".ae-toast", { hasText: "Series moved to Trash" }).isVisible(), "the series moved");
  check((await active(series.id)) === 0, "every occurrence left the calendar");
  trash = await call(frame, "/trash");
  check(trash.items[0].kind === "series" && trash.items[0].rrule === "FREQ=WEEKLY;COUNT=6", "Trash holds the series with its rule");
  await frame.locator('[data-act="trash"]').click();
  await atRoute(page, "/trash");
  await until(() => frame.locator(".trash-row .ae-pill", { hasText: "Series" }).isVisible(), "the row says Series");
  await shot(page, "trash-series");
  await frame.locator('.trash-row [data-act="trash-restore"]').click();
  await until(() => frame.locator(".ae-toast", { hasText: "Series restored" }).isVisible(), "restored");
  await until(async () => (await active(series.id)) === count, "all occurrences are back");
};

J["occurrence-after-series-changes"] = async () => {
  const series = await addWeekly(`WP03 changing ${RUN}`);
  const { occurrence } = await occurrenceKey(series.id, 1);
  const entry = (await call(frame, `/events/${series.id}?occurrence=${encodeURIComponent(occurrence)}`, "DELETE")).trash;
  await call(frame, `/events/${series.id}`, "PUT", { calendar_id: calendarId, title: series.title, start: `${today}T15:00`, end: `${today}T16:00`, time_zone: zone, rrule: "FREQ=WEEKLY;COUNT=6" });
  await ready("/trash");
  await until(() => frame.locator(".trash-row").count().then((n) => n === 1), "listed");
  await frame.locator('.trash-row .trash-actions [data-act="trash-open"]').click();
  await until(() => frame.locator(".trash-drawer .ae-banner").innerText().then((t) => t.includes("rescheduled")), "the details explain what happened");
  await shot(page, "occurrence-gone");
  await frame.locator('[data-act="trash-restore-separate"]').click();
  await until(() => frame.locator(".ae-toast", { hasText: "separate event" }).isVisible(), "restored as a separate event");
  check((await call(frame, `/events/${entry}`)).rrule === null, "the separate event does not repeat");
  check((await call(frame, `/events/${series.id}`)).rrule === "FREQ=WEEKLY;COUNT=6", "the series is unchanged");
};

J["deep-links-to-deleted-things"] = async () => {
  const event = await addEvent(`WP03 link ${RUN}`);
  await ready(`/month/${today}`);
  await call(frame, `/events/${event.id}`, "DELETE");
  await ready(`/events/${event.id}`);
  await until(() => frame.locator(".trash-notice h3").innerText().then((t) => t === "This event is in Trash"), "a direct link says it is in Trash");
  check((await page.locator("#navigation-status").count()) === 0, "Nexus reports no navigation failure");
  await shot(page, "deep-link-notice");
  await frame.locator('[data-act="trash-open"]').click();
  await until(() => /^\/trash\//.test(route(page) || ""), "View in Trash opens it there");
  await page.goBack();
  await atRoute(page, `/events/${event.id}`);
  await until(() => frame.locator(".trash-notice").isVisible(), "Back returns to the notice");
  await frame.locator('[data-act="notice-restore"]').click();
  await until(() => frame.locator(".ae-drawer:not(.is-leaving)").isVisible(), "Restore opens the event at the same address");
  check(route(page) === `/events/${event.id}`, "the address did not move");

  const series = await addWeekly(`WP03 linked weekly ${RUN}`);
  const { occurrence } = await occurrenceKey(series.id, 1);
  await call(frame, `/events/${series.id}?occurrence=${encodeURIComponent(occurrence)}`, "DELETE");
  await ready(`/events/${series.id}?o=${encodeURIComponent(occurrence)}`);
  await until(() => frame.locator(".trash-notice h3").innerText().then((t) => t === "This occurrence is in Trash"), "a link to one occurrence says that occurrence is in Trash");
};

J["draft-is-protected-through-trash-routes"] = async () => {
  await ready(`/month/${today}`);
  await frame.locator('[data-act="trash"]').click();
  await atRoute(page, "/trash");
  await frame.locator(".new-event").click();
  await until(() => frame.locator("#ev-title").isVisible(), "the editor opened over Trash");
  await frame.locator("#ev-title").fill(`WP03 draft ${RUN}`);
  await page.goBack();
  await until(() => frame.locator("#dialog-hold").isVisible(), "Back holds an unsaved event");
  check((await frame.locator("#ev-title").inputValue()) === `WP03 draft ${RUN}`, "the draft is intact");
  await frame.locator("#dialog-hold-discard").click();
  await until(() => frame.locator("#view .month").isVisible(), "discarding continues to the calendar");
  await sleep(600); // the checkpoint that clears the draft is debounced
};

J["editor-save-after-delete-elsewhere-keeps-the-draft"] = async () => {
  const event = await addEvent(`WP03 raced ${RUN}`);
  await ready(`/month/${today}`);
  await openEventFromMonth(event.id);
  await frame.locator('[data-act="edit"]').click();
  await until(() => frame.locator("#ev-title").isVisible(), "the editor opened");
  await frame.locator("#ev-title").fill(`WP03 edited ${RUN}`);
  await call(frame, `/events/${event.id}`, "DELETE"); // as from another tab
  await frame.locator("#save").click();
  await until(() => frame.locator("#ev-error").innerText().then((t) => t.includes("in Trash")), "saving explains that it is in Trash");
  check((await frame.locator("#ev-title").inputValue()) === `WP03 edited ${RUN}`, "the edit stays in the form");
  await frame.locator('#dialog [data-act="dialog-cancel"]').first().click();
};

J["reduced-motion"] = async () => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const event = await addEvent(`WP03 calm ${RUN}`);
  await call(frame, `/events/${event.id}`, "DELETE");
  await ready("/trash");
  await until(() => frame.locator(".trash-row").count().then((n) => n === 1), "listed");
  check(await frame.evaluate(() => reducedMotion()), "the page sees the preference");
  await frame.locator('.trash-row [data-act="trash-restore"]').click();
  await until(() => frame.locator(".ae-toast", { hasText: "Event restored" }).isVisible(), "restored without motion");
  await frame.locator('.ae-toast [data-toast-dismiss]').first().click();
  await until(async () => (await frame.locator(".ae-toast").count()) === 0, "a toast leaves at once");
  await page.emulateMedia({ reducedMotion: "no-preference" });
};

J["phone-width"] = async () => {
  await page.setViewportSize({ width: 390, height: 780 });
  const event = await addEvent(`WP03 a rather long title that has to shorten on a phone ${RUN}`, { location: "Somewhere with a long name too" });
  await call(frame, `/events/${event.id}`, "DELETE");
  await ready(`/month/${today}`);
  await frame.locator('[data-act="nav"]').click();
  await until(() => frame.locator('[data-act="trash"]').isVisible(), "the sidebar opens");
  await frame.locator('[data-act="trash"]').click();
  await atRoute(page, "/trash");
  await until(() => frame.locator(".trash-row").count().then((n) => n === 1), "listed");
  const overflow = await frame.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  check(overflow <= 0, "no horizontal scroll at phone width", String(overflow));
  await shot(page, "phone-trash");
  await page.setViewportSize({ width: 1440, height: 900 });
};

J["calendar-still-works"] = async () => {
  await ready(`/month/${today}`);
  await frame.locator(".new-event").click();
  await until(() => frame.locator("#ev-title").isVisible(), "the editor opened");
  await frame.locator("#ev-title").fill(`WP03 created ${RUN}`);
  await frame.locator("#save").click();
  await until(() => frame.locator(".ae-toast", { hasText: "Event created" }).isVisible(), "an event can be created");
  await until(() => frame.locator(".chip", { hasText: `WP03 created ${RUN}` }).isVisible(), "it appears on the month");
  await frame.locator('.views [data-view="week"]').click();
  await atRoute(page, `/week/${today}`);
  await until(() => frame.locator("#view .week").isVisible(), "Week still renders");
  await frame.locator('.views [data-view="agenda"]').click();
  await atRoute(page, `/agenda/${today}`);
  await until(() => frame.locator("#view .agenda").isVisible(), "Agenda still renders");
};

(async () => {
  const browser = await playwright[ENGINE].launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  page = await context.newPage();
  frame = await open(page);
  const state = await call(frame, "/state");
  calendarId = state.calendars.find((c) => c.kind === "native").id;
  zone = state.settings.time_zone;
  today = await frame.evaluate(() => today());
  let failed = 0;
  for (const [name, journey] of Object.entries(J)) {
    if (FILTER && !name.includes(FILTER)) continue;
    current = name;
    try {
      frame = await open(page, `/month/${today}`);
      await clearAll();
      await journey();
      record("PASS", "journey");
    } catch (error) {
      failed += 1;
      record("FAIL", "journey", error.message.slice(0, 300));
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/${ENGINE}-FAILED-${name}.png` }).catch(() => {});
    }
  }
  current = "cleanup";
  frame = await open(page, `/month/${today}`);
  await clearAll().catch(() => {});
  await browser.close();
  if (process.env.RESULTS) fs.writeFileSync(process.env.RESULTS, JSON.stringify(results, null, 1));
  const passes = results.filter((r) => r.status === "PASS").length;
  console.log(`\n${ENGINE}: ${passes} journeys passed, ${failed} failed, ${results.filter((r) => r.status === "ok").length} checks`);
  process.exit(failed ? 1 : 0);
})();
