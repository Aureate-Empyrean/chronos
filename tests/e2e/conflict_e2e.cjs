// Edit conflicts between real browser tabs, in a real Nexus shell. Run against a disposable stack
// only: it deletes what it creates. All records are synthetic ("WP02 ...").
//
//   PLAYWRIGHT_PATH=.../node_modules/playwright BROWSER=chromium NEXUS_URL=http://localhost:12396 \
//     OWNER_FILE=owner.json [SHOTS=dir] [RESULTS=file.json] node tests/e2e/conflict_e2e.cjs [filter]
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
const shot = async (page, name) => {
  if (SHOTS) {
    await sleep(350);
    await page.screenshot({ path: `${SHOTS}/${ENGINE}-${name}.png` });
  }
};

let context;
let page;
let frame;
let today;
let calendarId;
let zone;

const addEvent = (title, extra = {}) =>
  call(frame, "/events", "POST", { calendar_id: calendarId, title, description: "original notes", start: `${today}T10:00`, end: `${today}T11:00`, time_zone: zone, ...extra });
const addWeekly = (title) => addEvent(title, { rrule: "FREQ=WEEKLY;COUNT=6", start: `${today}T12:00`, end: `${today}T13:00` });
/** A change made by another client, as a real save through the API. */
async function elsewhere(id, changes) {
  const e = await call(frame, `/events/${id}`);
  return call(frame, `/events/${id}`, "PUT", { expected_revision: e.revision, calendar_id: e.calendar_id, title: e.title, description: e.description, location: e.location, start: e.start_local, end: e.end_local, time_zone: e.time_zone, rrule: e.rrule, status: e.status, ...changes });
}
async function clearAll() {
  for (const offset of [-30, 0, 30, 60]) {
    const a = await frame.evaluate((n) => zonedToUtc(addDays(today(), n)).toISOString().replace(".000", ""), offset);
    const b = await frame.evaluate((n) => zonedToUtc(addDays(today(), n + 40)).toISOString().replace(".000", ""), offset);
    for (const o of (await call(frame, `/occurrences?start=${encodeURIComponent(a)}&end=${encodeURIComponent(b)}`)).occurrences) {
      if (/^(WP02|Seeded)/.test(o.title)) await call(frame, `/events/${o.event_id}?scope=series`, "DELETE").catch(() => {});
    }
  }
  const trash = await call(frame, "/trash");
  await call(frame, "/trash/empty", "POST", { confirmed: true, expected_generation: trash.generation });
}
const drawer = (f) => f.locator(".ae-drawer:not(.is-leaving)");
async function openEditor(target, id) {
  const f = await open(target, `/events/${id}`);
  if (target === page) frame = f; // the previous frame went away with the navigation
  await until(() => drawer(f).isVisible(), "the event opened");
  await f.locator('[data-act="edit"]').click();
  await until(() => f.locator("#ev-title").isVisible(), "the editor opened");
  return f;
}
const banner = (f) => f.locator("#editor-conflict");
async function saveAndConflict(f) {
  await f.locator("#save").click();
  await until(() => banner(f).isVisible(), "the save reports a conflict");
  check((await banner(f).innerText()).includes("changed elsewhere"), "it says the event changed elsewhere");
  check((await banner(f).innerText()).includes("Nothing was saved"), "it says nothing was saved");
}
async function review(f) {
  await f.locator("#conflict-review-open").click();
  await until(() => f.locator("#conflict-keep").isVisible(), "the stored version is shown");
}

const J = {};

J["two-tabs-first-wins-second-reviews-and-keeps"] = async () => {
  const event = await addEvent(`WP02 shared ${RUN}`);
  const tabB = await context.newPage();
  try {
    const a = await openEditor(page, event.id);
    const b = await openEditor(tabB, event.id);
    await a.locator("#ev-title").fill(`WP02 from A ${RUN}`);
    await b.locator("#ev-title").fill(`WP02 from B ${RUN}`);
    await b.locator("#ev-description").fill("notes typed in tab B");
    await a.locator("#save").click();
    await until(() => a.locator(".ae-toast", { hasText: "Event saved" }).isVisible(), "tab A saved first");
    await saveAndConflict(b);
    const stored = await call(a, `/events/${event.id}`);
    check(stored.title === `WP02 from A ${RUN}`, "tab B did not overwrite tab A");
    check((await b.locator("#ev-title").inputValue()) === `WP02 from B ${RUN}`, "tab B keeps its title");
    check((await b.locator("#ev-description").inputValue()) === "notes typed in tab B", "tab B keeps its notes");
    await shot(tabB, "conflict-banner");
    await review(b);
    const table = await b.locator(".conflict-table").innerText();
    check(table.includes(`WP02 from A ${RUN}`) && table.includes(`WP02 from B ${RUN}`), "the review shows stored and edited titles side by side");
    await shot(tabB, "conflict-review");
    check((await call(a, `/events/${event.id}`)).revision === stored.revision, "reviewing changes nothing");
    await b.locator("#conflict-keep").click();
    await until(() => b.locator(".ae-toast", { hasText: "Event saved" }).isVisible(), "keeping my version saves it");
    const final = await call(a, `/events/${event.id}`);
    check(final.title === `WP02 from B ${RUN}` && final.revision === stored.revision + 1, "the deliberate save is one new revision");
  } finally {
    await tabB.close();
  }
};

J["use-the-stored-version-instead"] = async () => {
  const event = await addEvent(`WP02 discard ${RUN}`);
  const f = await openEditor(page, event.id);
  await f.locator("#ev-title").fill(`WP02 mine ${RUN}`);
  await elsewhere(event.id, { title: `WP02 theirs ${RUN}` });
  await saveAndConflict(f);
  await review(f);
  await f.locator("#conflict-use").click();
  await until(() => f.locator("#ev-title").inputValue().then((v) => v === `WP02 theirs ${RUN}`), "the form now holds the stored version");
  check((await banner(f).count()) === 0, "the conflict is resolved");
  await f.locator("#save").click();
  await until(() => f.locator(".ae-toast", { hasText: "Event saved" }).isVisible(), "saving from the stored version works");
};

J["keeping-my-version-conflicts-again-if-it-changed-again"] = async () => {
  const event = await addEvent(`WP02 twice ${RUN}`);
  const f = await openEditor(page, event.id);
  await f.locator("#ev-title").fill(`WP02 patient ${RUN}`);
  await elsewhere(event.id, { title: `WP02 second ${RUN}` });
  await saveAndConflict(f);
  await review(f);
  await elsewhere(event.id, { title: `WP02 third ${RUN}` }); // changes after the review was read
  await f.locator("#conflict-keep").click();
  await until(() => f.locator("#conflict-review-open").isVisible(), "a newer change needs a new review");
  check((await call(f, `/events/${event.id}`)).title === `WP02 third ${RUN}`, "the newest version was not overwritten");
  check((await f.locator("#ev-title").inputValue()) === `WP02 patient ${RUN}`, "the edit is still in the form");
};

J["rapid-double-save-writes-once"] = async () => {
  const event = await addEvent(`WP02 double ${RUN}`);
  let puts = 0;
  const count = (r) => {
    if (r.method() === "PUT" && r.url().includes(`/api/events/${event.id}`)) puts += 1;
  };
  page.on("request", count);
  try {
    const f = await openEditor(page, event.id);
    await f.locator("#ev-title").fill(`WP02 once ${RUN}`);
    await f.locator("#save").evaluate((button) => {
      button.click();
      button.click();
      button.click();
    });
    await until(() => f.locator(".ae-toast", { hasText: "Event saved" }).isVisible(), "the save completed");
    check(puts === 1, "three quick clicks send one save", String(puts));
    check((await call(f, `/events/${event.id}`)).revision === event.revision + 1, "one new revision");
  } finally {
    page.off("request", count);
  }
};

J["a-draft-keeps-its-base-version-through-reload"] = async () => {
  const event = await addEvent(`WP02 draft ${RUN}`);
  let f = await openEditor(page, event.id);
  await f.locator("#ev-title").fill(`WP02 drafted ${RUN}`);
  await sleep(700); // the checkpoint is debounced
  await elsewhere(event.id, { title: `WP02 newer ${RUN}` });
  await page.reload();
  await page.locator("#module-application").waitFor();
  await until(async () => {
    f = await appFrame(page);
    return f.locator('[data-draft="resume"]').isVisible();
  }, "after a refresh the draft is offered");
  await f.locator('[data-draft="resume"]').click();
  await until(() => f.locator("#ev-title").inputValue().then((v) => v === `WP02 drafted ${RUN}`), "the draft text is back");
  await f.locator("#save").click();
  await until(() => banner(f).isVisible(), "the draft is still judged against the version it was written on");
  check((await call(f, `/events/${event.id}`)).title === `WP02 newer ${RUN}`, "the newer change survived");
  await f.locator('#dialog [data-act="dialog-cancel"]').first().click();
  await sleep(600);
};

J["back-and-forward-during-a-conflict"] = async () => {
  const event = await addEvent(`WP02 history ${RUN}`);
  frame = await open(page, `/month/${today}`);
  await frame.evaluate(() => refresh());
  await until(() => frame.locator(`[data-open^="${event.id}/"]`).first().isVisible(), "the event is on the month");
  await frame.locator(`[data-open^="${event.id}/"]`).first().click();
  await until(() => drawer(frame).isVisible(), "the event opened");
  await frame.locator('[data-act="edit"]').click();
  await until(() => frame.locator("#ev-title").isVisible(), "the editor opened");
  await frame.locator("#ev-title").fill(`WP02 held ${RUN}`);
  await elsewhere(event.id, { title: `WP02 moved on ${RUN}` });
  await saveAndConflict(frame);
  await page.goBack();
  await until(() => frame.locator("#dialog-hold").isVisible(), "Back holds the editor");
  check((await frame.locator("#ev-title").inputValue()) === `WP02 held ${RUN}`, "the edit survives Back");
  check(await banner(frame).isVisible(), "the conflict is still shown");
  await page.goForward();
  await until(async () => (await frame.locator("#dialog-hold").count()) === 0, "Forward returns to the event");
  check((await frame.locator("#ev-title").inputValue()) === `WP02 held ${RUN}`, "the edit survives Forward");
  await review(frame);
  await frame.locator("#conflict-keep").click();
  await until(() => frame.locator(".ae-toast", { hasText: "Event saved" }).isVisible(), "the save completes after traversal");
};

J["series-conflict-keeps-the-deleted-occurrence"] = async () => {
  const series = await addWeekly(`WP02 series ${RUN}`);
  const f = await openEditor(page, series.id);
  const a = await f.evaluate(() => zonedToUtc(today()).toISOString().replace(".000", ""));
  const b = await f.evaluate(() => zonedToUtc(addDays(today(), 60)).toISOString().replace(".000", ""));
  const all = (await call(f, `/occurrences?start=${encodeURIComponent(a)}&end=${encodeURIComponent(b)}`)).occurrences.filter((o) => o.event_id === series.id);
  const key = all[1].occurrence;
  await call(f, `/events/${series.id}?occurrence=${encodeURIComponent(key)}`, "DELETE");
  await f.locator("#ev-title").fill(`WP02 renamed series ${RUN}`);
  await saveAndConflict(f);
  await review(f);
  check((await f.locator(".conflict-table").innerText()).includes("Deleted or skipped occurrences"), "the review names the deleted occurrence");
  await f.locator("#conflict-keep").click();
  await until(() => f.locator(".ae-toast", { hasText: "Event saved" }).isVisible(), "saved after review");
  const final = await call(f, `/events/${series.id}`);
  check(final.title === `WP02 renamed series ${RUN}` && final.exdates.includes(key), "the rename kept the occurrence deleted");
};

J["stale-details-cannot-delete-a-newer-version"] = async () => {
  const event = await addEvent(`WP02 stale view ${RUN}`);
  const f = await open(page, `/events/${event.id}`);
  frame = f;
  await until(() => drawer(f).isVisible(), "the event opened");
  await elsewhere(event.id, { title: `WP02 changed view ${RUN}` });
  await f.locator('[data-act="event-menu"]').click();
  await until(() => f.locator(".ae-menu").isVisible(), "the menu opened");
  await f.locator(".ae-menu-item", { hasText: "Delete event" }).click();
  await until(() => f.locator("#confirm").isVisible(), "asked to confirm");
  await f.locator("#confirm").click();
  await until(() => f.locator(".ae-toast", { hasText: "nothing was deleted" }).isVisible(), "the stale delete is refused");
  await until(() => f.locator("#details-title").innerText().then((t) => t === `WP02 changed view ${RUN}`), "the details now show the current version");
  check((await call(f, "/trash")).total === 0, "nothing went to Trash");
  await f.locator('[data-act="event-menu"]').click();
  await f.locator(".ae-menu-item", { hasText: "Delete event" }).click();
  await until(() => f.locator("#confirm").isVisible(), "asked again");
  await f.locator("#confirm").click();
  await until(() => f.locator(".ae-toast", { hasText: "Moved to Trash" }).isVisible(), "deleting the current version works");
  await f.locator(".ae-toast [data-toast-action]").last().click();
  await until(async () => (await call(f, `/events/${event.id}`)).trashed_at === null, "Undo still works");
};

J["trash-and-restore-while-editing"] = async () => {
  const event = await addEvent(`WP02 trashed ${RUN}`);
  const f = await openEditor(page, event.id);
  await f.locator("#ev-title").fill(`WP02 kept typing ${RUN}`);
  const entry = (await call(f, `/events/${event.id}`, "DELETE")).trash;
  await f.locator("#save").click();
  await until(() => f.locator("#ev-error").innerText().then((t) => t.includes("in Trash")), "saving says it is in Trash");
  check((await f.locator("#ev-title").inputValue()) === `WP02 kept typing ${RUN}`, "the edit stays in the form");
  await call(f, `/trash/${entry}/restore`, "POST", {});
  await saveAndConflict(f);
  await review(f);
  await f.locator("#conflict-keep").click();
  await until(() => f.locator(".ae-toast", { hasText: "Event saved" }).isVisible(), "after a restore the edit can be saved knowingly");
  check((await call(f, `/events/${event.id}`)).title === `WP02 kept typing ${RUN}`, "the event has the edit");
};

J["permanent-delete-while-editing"] = async () => {
  const event = await addEvent(`WP02 gone ${RUN}`);
  const f = await openEditor(page, event.id);
  await f.locator("#ev-title").fill(`WP02 orphaned ${RUN}`);
  const entry = (await call(f, `/events/${event.id}`, "DELETE")).trash;
  await call(f, `/trash/${entry}?confirmed=true`, "DELETE");
  await f.locator("#save").click();
  await until(() => f.locator("#ev-error").isVisible(), "saving reports the event is gone");
  check((await f.locator("#ev-title").inputValue()) === `WP02 orphaned ${RUN}`, "the text stays available to copy");
  await f.locator('#dialog [data-act="dialog-cancel"]').first().click();
  await sleep(600);
};

J["stale-calendar-rename"] = async () => {
  const created = await call(frame, "/calendars", "POST", { name: `WP02 cal ${RUN}`, color: "#7AA7EB" });
  try {
    const f = await open(page, `/month/${today}`);
    frame = f;
    await f.locator(`[data-act="calendar-menu"][data-id="${created.id}"]`).click();
    await f.locator(".ae-menu-item", { hasText: "Rename or recolor" }).click();
    await until(() => f.locator("#cal-name").isVisible(), "the dialog opened");
    await f.locator("#cal-name").fill(`WP02 mine ${RUN}`);
    await call(f, `/calendars/${created.id}`, "PUT", { name: `WP02 theirs ${RUN}`, expected_revision: created.revision });
    await f.locator("#save").click();
    await until(() => f.locator("#dialog-conflict").isVisible(), "the rename reports a conflict");
    check((await f.locator("#dialog-conflict").innerText()).includes(`WP02 theirs ${RUN}`), "it says what the calendar is called now");
    check((await f.locator("#cal-name").inputValue()) === `WP02 mine ${RUN}`, "the typed name stays");
    await shot(page, "calendar-conflict");
    await f.locator("#save").click();
    await until(async () => (await call(f, "/state")).calendars.some((c) => c.name === `WP02 mine ${RUN}`), "saving again applies it knowingly");
  } finally {
    const state = await call(frame, "/state").catch(() => null);
    const row = state?.calendars.find((c) => c.id === created.id);
    if (row) await call(frame, `/calendars/${created.id}?confirmed=true&expected_revision=${row.revision}`, "DELETE").catch(() => {});
  }
};

J["phone-width-conflict"] = async () => {
  await page.setViewportSize({ width: 390, height: 780 });
  try {
    const event = await addEvent(`WP02 phone ${RUN}`);
    const f = await openEditor(page, event.id);
    await f.locator("#ev-title").fill(`WP02 a long edited title that must wrap on a phone ${RUN}`);
    await elsewhere(event.id, { title: `WP02 a long stored title that must also wrap on a phone ${RUN}` });
    await saveAndConflict(f);
    await review(f);
    const overflow = await f.evaluate(() => {
      const body = dialog().querySelector(".ae-dialog-body");
      return body.scrollWidth - body.clientWidth;
    });
    check(overflow <= 0, "the review fits at phone width", String(overflow));
    await shot(page, "phone-conflict");
    await f.locator('#dialog [data-act="dialog-cancel"]').first().click();
    await sleep(600);
  } finally {
    await page.setViewportSize({ width: 1440, height: 900 });
  }
};

J["reduced-motion-conflict"] = async () => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  try {
    const event = await addEvent(`WP02 calm ${RUN}`);
    const f = await openEditor(page, event.id);
    await f.locator("#ev-title").fill(`WP02 calm edit ${RUN}`);
    await elsewhere(event.id, { title: `WP02 calm stored ${RUN}` });
    await saveAndConflict(f);
    await review(f);
    await f.locator("#conflict-keep").click();
    await until(() => f.locator(".ae-toast", { hasText: "Event saved" }).isVisible(), "the flow works without motion");
  } finally {
    await page.emulateMedia({ reducedMotion: "no-preference" });
  }
};

(async () => {
  const browser = await playwright[ENGINE].launch();
  context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
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
    // A fresh tab each time: an editor left open by one journey must not become the next one's draft.
    await page.close();
    page = await context.newPage();
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
  await page.close();
  page = await context.newPage();
  current = "cleanup";
  frame = await open(page, `/month/${today}`);
  await clearAll().catch(() => {});
  await browser.close();
  if (process.env.RESULTS) fs.writeFileSync(process.env.RESULTS, JSON.stringify(results, null, 1));
  console.log(`\n${ENGINE}: ${results.filter((r) => r.status === "PASS").length} journeys passed, ${failed} failed, ${results.filter((r) => r.status === "ok").length} checks`);
  process.exit(failed ? 1 : 0);
})();
