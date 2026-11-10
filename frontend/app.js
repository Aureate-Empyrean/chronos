const catalogs = /*CATALOGS*/ {};

/* ───────────────────────── Localization ───────────────────────── */

let activeLocale = "en";
function t(key, vars) {
  let text =
    catalogs[activeLocale]?.[key] ??
    catalogs[activeLocale.split("-")[0]]?.[key] ??
    catalogs.en?.[key] ??
    key;
  if (vars)
    text = text.replace(/\{(\w+)\}/g, (match, name) =>
      name in vars ? vars[name] : match,
    );
  return text;
}
function plural(count, one, other, vars = {}) {
  let rule = "other";
  try {
    rule = new Intl.PluralRules(activeLocale).select(count);
  } catch {
    rule = count === 1 ? "one" : "other";
  }
  return t(rule === "one" ? one : other, { count, ...vars });
}
function safeLocale(value) {
  try {
    return Intl.getCanonicalLocales(value || "en")[0] || "en";
  } catch {
    return "en";
  }
}

/* ───────────────────────── Utilities ───────────────────────── */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
const reducedMotion = () =>
  !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
function animate(el, frames, options) {
  if (!el?.animate || reducedMotion()) return Promise.resolve();
  try {
    return el
      .animate(frames, { easing: "cubic-bezier(.2,.8,.2,1)", ...options })
      .finished.catch(() => {});
  } catch {
    return Promise.resolve();
  }
}

/* The motion scale Meridian uses, so a Trash action feels like the rest of Aureate Empyrean. */
const MOTION = { fast: 120, page: 220, panel: 260, exit: 160, ease: "cubic-bezier(.22,1,.36,1)", exitEase: "cubic-bezier(.4,0,1,1)" };

const ICONS = {
  // Same glyph as frontend/icon.svg, the application icon Nexus shows.
  mark: '<path d="M11.5 4.5a6.5 6.5 0 0 0 8 8 8 8 0 1 1-8-8Z"/><path d="M18.6 2.2c.3 1.7 1.1 2.5 2.8 2.8-1.7.3-2.5 1.1-2.8 2.8-.3-1.7-1.1-2.5-2.8-2.8 1.7-.3 2.5-1.1 2.8-2.8z" fill="currentColor" stroke="none"/>',
  plus: '<path d="M10 4v12M4 10h12"/>',
  left: '<path d="m12 4.5-5.5 5.5 5.5 5.5"/>',
  right: '<path d="m8 4.5 5.5 5.5L8 15.5"/>',
  search: '<circle cx="9" cy="9" r="5.5"/><path d="m13 13 3.5 3.5"/>',
  gear: '<path d="M4 6h7M15 6h1M4 10h2M10 10h6M4 14h8M16 14h0"/><circle cx="13" cy="6" r="1.8"/><circle cx="8" cy="10" r="1.8"/><circle cx="14" cy="14" r="1.8"/>',
  menu: '<path d="M3.5 6h13M3.5 10h13M3.5 14h13"/>',
  more: '<circle cx="5" cy="10" r="1.2" fill="currentColor"/><circle cx="10" cy="10" r="1.2" fill="currentColor"/><circle cx="15" cy="10" r="1.2" fill="currentColor"/>',
  upload: '<path d="M10 13V4M6.5 7.5 10 4l3.5 3.5M4 16h12"/>',
  feed: '<path d="M4.5 15.5a1 1 0 1 0 0 .01M4 9.5a6.5 6.5 0 0 1 6.5 6.5M4 4a12 12 0 0 1 12 12"/>',
  refresh: '<path d="M15.5 8A6 6 0 0 0 4.7 6.3M4.5 12a6 6 0 0 0 10.8 1.7"/><path d="M15.7 3.6V8h-4.4M4.3 16.4V12h4.4"/>',
  x: '<path d="m5 5 10 10M15 5 5 15"/>',
  trash: '<path d="M4.5 6h11M8 6V4.5h4V6M6 6l.7 10h6.6L14 6"/>',
  edit: '<path d="M12.8 4.2 15.8 7.2 7.5 15.5H4.5v-3z"/>',
  copy: '<rect x="7" y="7" width="9" height="9" rx="1.5"/><path d="M13 7V5.5A1.5 1.5 0 0 0 11.5 4h-6A1.5 1.5 0 0 0 4 5.5v6A1.5 1.5 0 0 0 5.5 13H7"/>',
  clock: '<circle cx="10" cy="10" r="7"/><path d="M10 6.2V10l2.6 1.7"/>',
  pin: '<path d="M10 17s5-4.6 5-8.5a5 5 0 0 0-10 0C5 12.4 10 17 10 17z"/><circle cx="10" cy="8.5" r="1.8"/>',
  repeat: '<path d="M4 9V8a3 3 0 0 1 3-3h8l-2.5-2.5M16 11v1a3 3 0 0 1-3 3H5l2.5 2.5"/>',
  calendar: '<rect x="3.5" y="4.5" width="13" height="12" rx="2"/><path d="M3.5 8.5h13M7 3v3M13 3v3"/>',
  link: '<path d="M8.5 11.5a3 3 0 0 0 4.2 0l2.5-2.5a3 3 0 0 0-4.2-4.2l-.9.9M11.5 8.5a3 3 0 0 0-4.2 0L4.8 11a3 3 0 0 0 4.2 4.2l.9-.9"/>',
  open: '<path d="M11 4h5v5M16 4l-7 7M14 11.5V15a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h3.5"/>',
  alert: '<path d="M10 3.5 17 16H3z"/><path d="M10 8.5v3.5M10 14h.01"/>',
  layers: '<path d="m10 3 7 3.8-7 3.8-7-3.8z"/><path d="m3 10.5 7 3.8 7-3.8"/>',
  text: '<path d="M4 5.5h12M4 10h12M4 14.5h8"/>',
  tag: '<path d="M3.5 10.2V4.5a1 1 0 0 1 1-1h5.7l6.3 6.3-6.7 6.7z"/><circle cx="7" cy="7" r="1.1"/>',
  person: '<circle cx="10" cy="7" r="3"/><path d="M4 17c.8-3.2 3.1-5 6-5s5.2 1.8 6 5"/>',
  film: '<rect x="3.5" y="4" width="13" height="12" rx="2"/><path d="M7 4v12M13 4v12M3.5 8h3.5M3.5 12h3.5M13 8h3.5M13 12h3.5"/>',
  task: '<rect x="4" y="4" width="12" height="12" rx="3"/><path d="m7.3 10.2 1.9 1.9 3.6-3.9"/>',
  info: '<circle cx="10" cy="10" r="7"/><path d="M10 9v4.5M10 6.5h.01"/>',
};
function icon(name, className = "") {
  const box = name === "mark" ? "0 0 24 24" : "0 0 20 20";
  return `<svg class="i ${className}" viewBox="${box}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${ICONS[name] || ""}</svg>`;
}

/* ───────────────────────── Nexus bridge ───────────────────────── */

let serial = 0;
const pending = new Map();
window.addEventListener("message", (event) => {
  if (event.source !== parent || event.data?.channel !== "empyrean-v1") return;
  const request = pending.get(event.data.id);
  if (!request) return;
  clearTimeout(request.timer);
  pending.delete(event.data.id);
  event.data.error
    ? request.reject(Error(event.data.error))
    : request.resolve(event.data.result);
});
function bridge(action, data = {}) {
  return new Promise((resolve, reject) => {
    const id = String(++serial);
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(Error(t("Nexus did not respond. Try again in a moment.")));
    }, 15000);
    pending.set(id, { resolve, reject, timer });
    parent.postMessage({ channel: "empyrean-v1", id, action, ...data }, "*");
  });
}
const api = (path, method = "GET", body) =>
  bridge("request", { path: "/api" + path, method, ...(body === undefined ? {} : { body }) });

/* ───────────────────────── Time ───────────────────────── */

const PALETTE = ["#7AA7EB", "#8B7CF6", "#C98BE0", "#E58FC7", "#EF8A8A", "#E8956A", "#E3B26B", "#7CC47F", "#4FB8B0", "#A7A9AF"];
const PROVIDERS = {
  lyra: { name: "Lyra", icon: "film", what: "Release dates from your media library" },
  mnemosyne: { name: "Mnemosyne", icon: "task", what: "Task deadlines" },
  meridian: { name: "Meridian", icon: "person", what: "Birthdays and anniversaries" },
};

const tz = () => state.settings.time_zone || "UTC";
const pad = (n) => String(n).padStart(2, "0");
function toDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}
const isoOf = (date) => date.toISOString().slice(0, 10);
function addDays(iso, n) {
  const d = toDate(iso);
  d.setUTCDate(d.getUTCDate() + n);
  return isoOf(d);
}
function addMonths(iso, n) {
  const d = toDate(iso.slice(0, 8) + "01");
  d.setUTCMonth(d.getUTCMonth() + n);
  return isoOf(d);
}
const weekday = (iso) => toDate(iso).getUTCDay();
const daysBetween = (a, b) => Math.round((toDate(b) - toDate(a)) / 86400000);
function startOfWeek(iso) {
  return addDays(iso, -((weekday(iso) - state.settings.week_start + 7) % 7));
}
const partsFormatter = new Map();
function zoneParts(date, zone = tz()) {
  if (!partsFormatter.has(zone))
    partsFormatter.set(
      zone,
      new Intl.DateTimeFormat("en-US", {
        timeZone: zone,
        hourCycle: "h23",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }),
    );
  const v = Object.fromEntries(
    partsFormatter.get(zone).formatToParts(date).map((p) => [p.type, p.value]),
  );
  return {
    day: `${v.year}-${v.month}-${v.day}`,
    minutes: Number(v.hour) * 60 + Number(v.minute),
    utc: Date.UTC(+v.year, v.month - 1, +v.day, +v.hour, +v.minute, +v.second),
  };
}
function offsetMinutes(date, zone) {
  return (zoneParts(date, zone).utc - Math.floor(date.getTime() / 1000) * 1000) / 60000;
}
/** UTC Date for a wall-clock time in a zone. */
function zonedToUtc(iso, minutes = 0, zone = tz()) {
  const [y, m, d] = iso.split("-").map(Number);
  const guess = Date.UTC(y, m - 1, d, Math.floor(minutes / 60), minutes % 60);
  let result = guess - offsetMinutes(new Date(guess), zone) * 60000;
  const second = offsetMinutes(new Date(result), zone);
  result = guess - second * 60000;
  return new Date(result);
}
const today = () => zoneParts(new Date()).day;
const hourOptions = () =>
  state.settings.time_format === "12"
    ? { hour12: true }
    : state.settings.time_format === "24"
      ? { hourCycle: "h23" }
      : {};
function fmtDay(iso, options) {
  return new Intl.DateTimeFormat(activeLocale, { timeZone: "UTC", ...options }).format(toDate(iso));
}
function fmtTime(instant, zone = tz()) {
  return new Intl.DateTimeFormat(activeLocale, {
    timeZone: zone,
    hour: "numeric",
    minute: "2-digit",
    ...hourOptions(),
  }).format(new Date(instant));
}
function fmtHour(hour) {
  const date = new Date(Date.UTC(2020, 0, 1, hour));
  return new Intl.DateTimeFormat(activeLocale, { timeZone: "UTC", hour: "numeric", ...hourOptions() }).format(date);
}
function relative(instant) {
  if (!instant) return t("never");
  const seconds = (new Date(instant) - Date.now()) / 1000;
  const units = [
    ["year", 31536000],
    ["month", 2592000],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  const rtf = new Intl.RelativeTimeFormat(activeLocale, { numeric: "auto" });
  for (const [unit, size] of units)
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit);
  return rtf.format(0, "minute");
}
function weekdayNames(style = "short") {
  const base = toDate("2023-01-01"); // a Sunday
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(base);
    d.setUTCDate(1 + ((i + state.settings.week_start) % 7));
    return new Intl.DateTimeFormat(activeLocale, { timeZone: "UTC", weekday: style }).format(d);
  });
}
function zoneLabel(zone) {
  try {
    const name = new Intl.DateTimeFormat(activeLocale, { timeZone: zone, timeZoneName: "longGeneric" })
      .formatToParts(new Date())
      .find((p) => p.type === "timeZoneName")?.value;
    return name || zone;
  } catch {
    return zone;
  }
}

/* ───────────────────────── State ───────────────────────── */

const state = {
  context: { applications: [], locale: "en" },
  settings: { time_zone: "UTC", week_start: 1, time_format: "auto" },
  calendars: [],
  categories: [],
  sources: [],
  zones: [],
  view: "month",
  cursor: null,
  miniCursor: null,
  occurrences: [],
  range: null,
  loading: true,
  error: null,
  query: "",
  results: null,
  categoryFilter: new Set(),
  agendaPast: false,
  agendaDays: 60,
  selected: null,
  pollTimer: null,
  screen: "calendar",
  notice: null,
  trashCount: 0,
  trash: { items: [], matched: 0, total: 0, next: null, loading: true, error: null, enter: false },
};
const viewsKey = ["month", "week", "day", "agenda"];

function toast(message, tone = "", action = null) {
  const box = $("#toasts");
  const el = document.createElement("div");
  el.className = `ae-toast ae-glass ${tone === "danger" ? "ae-toast--danger" : ""}`;
  el.innerHTML = `<span>${esc(message)}</span>${action ? `<button class="ae-btn ae-btn--sm toast-action" data-toast-action>${esc(action.label)}</button>` : ""}<button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-toast-dismiss aria-label="${esc(t("Dismiss"))}">${icon("x")}</button>`;
  let leaving = false;
  const leave = async () => {
    if (leaving) return;
    leaving = true;
    await animate(el, [{ opacity: 1, transform: "none" }, { opacity: 0, transform: "translateY(6px)" }], { duration: MOTION.exit, easing: MOTION.exitEase, fill: "forwards" });
    el.remove();
  };
  el.querySelector("[data-toast-dismiss]").onclick = leave;
  if (action)
    el.querySelector("[data-toast-action]").onclick = () => {
      leave();
      action.run();
    };
  box.append(el);
  setTimeout(leave, action ? 10000 : tone === "danger" ? 9000 : 4500);
}
/** The backend's answer to a write based on a version that is no longer the stored one. */
const isConflict = (error) => /changed elsewhere/i.test(error?.message || "");
async function attempt(work, success) {
  try {
    const result = await work();
    if (success) toast(success);
    return result;
  } catch (error) {
    toast(error.message || t("Something went wrong."), "danger");
    return undefined;
  }
}

/* ───────────────────────── Data ───────────────────────── */

async function loadState() {
  const data = await api("/state");
  state.settings = data.settings;
  state.calendars = data.calendars;
  state.categories = data.categories;
  state.sources = data.sources;
  state.pendingSync = data.pending_sync;
  state.trashCount = data.trash_count;
}
function viewRange() {
  const c = state.cursor;
  if (state.view === "month") {
    const start = startOfWeek(c.slice(0, 8) + "01");
    return { start, days: 42 };
  }
  if (state.view === "week") return { start: startOfWeek(c), days: 7 };
  if (state.view === "day") return { start: c, days: 1 };
  return state.agendaPast
    ? { start: addDays(today(), -state.agendaDays), days: state.agendaDays }
    : { start: c < today() ? c : today(), days: state.agendaDays };
}
let loadSerial = 0;
async function loadOccurrences() {
  const range = viewRange();
  const token = ++loadSerial;
  state.loading = !state.occurrences.length || state.range?.start !== range.start;
  if (state.loading) renderView();
  const start = zonedToUtc(range.start).toISOString().replace(".000", "");
  const end = zonedToUtc(addDays(range.start, range.days)).toISOString().replace(".000", "");
  try {
    const data = await api(`/occurrences?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`);
    if (token !== loadSerial) return;
    state.occurrences = data.occurrences;
    state.range = range;
    state.error = null;
  } catch (error) {
    if (token !== loadSerial) return;
    state.error = error.message;
  }
  state.loading = false;
  renderView();
}
function visible(o) {
  if (!state.categoryFilter.size) return true;
  return o.origin !== "projection" && state.categoryFilter.has(o.category_id);
}
/** Occurrences laid out in the display zone: timed ones get day keys and minutes. */
function placed() {
  return state.occurrences.filter(visible).map((o) => {
    if (o.all_day) return { ...o, sDay: o.start, eDay: addDays(o.end, -1) };
    const s = zoneParts(new Date(o.start));
    const e = zoneParts(new Date(o.end));
    let eDay = e.day;
    let eMin = e.minutes;
    if (eDay > s.day && eMin === 0) {
      eDay = addDays(eDay, -1);
      eMin = 1440;
    }
    return { ...o, sDay: s.day, sMin: s.minutes, eDay, eMin };
  });
}
function onDay(list, day) {
  return list.filter((o) => o.sDay <= day && o.eDay >= day);
}
function schedulePoll() {
  clearTimeout(state.pollTimer);
  const busy =
    state.calendars.some((c) => c.subscription?.running) ||
    state.sources.some((s) => s.enabled && !s.last_attempt_at);
  state.pollTimer = setTimeout(async () => {
    if (document.hidden) return schedulePoll();
    try {
      const before = JSON.stringify([state.calendars.map((c) => [c.event_count, c.subscription?.last_success_at]), state.sources.map((s) => s.last_success_at)]);
      const trashBefore = state.trashCount;
      await loadState();
      const after = JSON.stringify([state.calendars.map((c) => [c.event_count, c.subscription?.last_success_at]), state.sources.map((s) => s.last_success_at)]);
      renderSidebar();
      if (before !== after) await loadOccurrences();
      if (state.screen === "trash" && trashBefore !== state.trashCount) await loadTrash({ quiet: true });
    } catch {
      /* the next poll retries */
    }
    schedulePoll();
  }, busy ? 2500 : 60000);
}
const nativeCalendars = () => state.calendars.filter((c) => c.kind === "native");
const calendarById = (id) => state.calendars.find((c) => c.id === id);

/* ───────────────────────── Shell ───────────────────────── */

function renderShell() {
  $("#app").innerHTML = `
    <aside class="sidebar ae-surface" aria-label="${esc(t("Calendars"))}">
      <div class="brand"><span class="brand-mark">${icon("mark")}</span><span class="brand-name">Chronos</span></div>
      <button class="ae-btn ae-btn--primary new-event" data-act="new">${icon("plus")}<span>${esc(t("New event"))}</span></button>
      <div class="sidebar-scroll" id="sidebar"></div>
      <div class="side-trash" id="side-trash"></div>
      <div class="side-foot">
        <button class="ae-btn ae-btn--quiet ae-btn--sm" data-act="import">${icon("upload")}<span>${esc(t("Import"))}</span></button>
        <button class="ae-btn ae-btn--quiet ae-btn--sm" data-act="subscribe">${icon("feed")}<span>${esc(t("Subscribe"))}</span></button>
      </div>
    </aside>
    <main class="main">
      <header class="topbar ae-surface">
        <button class="ae-btn ae-btn--quiet ae-btn--icon menu-toggle" data-act="nav" aria-label="${esc(t("Show calendars"))}">${icon("menu")}</button>
        <button class="ae-btn ae-btn--sm" data-act="today" data-tip="T">${esc(t("Today"))}</button>
        <button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="prev" aria-label="${esc(t("Previous"))}">${icon("left")}</button>
        <button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="next" aria-label="${esc(t("Next"))}">${icon("right")}</button>
        <h1 id="title"></h1>
        <span class="spacer"></span>
        <label class="search">${icon("search")}<span class="ae-visually-hidden">${esc(t("Search events"))}</span><input class="ae-input" id="search" type="search" placeholder="${esc(t("Search events"))}" autocomplete="off"></label>
        <div class="ae-seg views" role="group" aria-label="${esc(t("View"))}">
          ${viewsKey.map((v) => `<button data-view="${v}" aria-pressed="false">${esc(t({ month: "Month", week: "Week", day: "Day", agenda: "Agenda" }[v]))}</button>`).join("")}
        </div>
        <button class="ae-btn ae-btn--quiet ae-btn--icon" data-act="settings" aria-label="${esc(t("Settings"))}" data-tip="${esc(t("Settings"))}">${icon("gear")}</button>
      </header>
      <div class="view ae-surface" id="view" tabindex="-1"></div>
    </main>`;
  $("#search").addEventListener("input", onSearch);
}

function renderSidebar() {
  const range = state.range || viewRange();
  const mini = state.miniCursor || state.cursor;
  const first = mini.slice(0, 8) + "01";
  const gridStart = startOfWeek(first);
  const now = today();
  const days = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i));
  const rangeEnd = addDays(range.start, range.days - 1);
  const calendarRow = (c) => {
    const sub = c.subscription;
    let status = "";
    if (sub?.running) status = `<span class="state is-busy" data-tip="${esc(t("Synchronizing"))}">${icon("refresh")}</span>`;
    else if (sub?.last_error) status = `<span class="state is-error" data-tip="${esc(sub.last_error)}">${icon("alert")}</span>`;
    else if (sub && !sub.enabled) status = `<span class="state" data-tip="${esc(t("Paused"))}">${icon("clock")}</span>`;
    else if (c.kind === "subscription") status = `<span class="state" data-tip="${esc(t("Read-only subscription"))}">${icon("feed")}</span>`;
    else if (c.kind === "import") status = `<span class="state" data-tip="${esc(t("Read-only import"))}">${icon("upload")}</span>`;
    return `<div class="cal-row" style="--c:${esc(c.color)}">
      <input type="checkbox" class="swatch" data-act="toggle-calendar" data-id="${esc(c.id)}" ${c.visible ? "checked" : ""} aria-label="${esc(t("Show {name}", { name: c.name }))}">
      <span class="name" title="${esc(c.name)}">${esc(c.name)}</span>${status}
      <button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="calendar-menu" data-id="${esc(c.id)}" aria-label="${esc(t("Options for {name}", { name: c.name }))}" aria-haspopup="menu">${icon("more")}</button>
    </div>`;
  };
  const sourceRow = (s) => {
    const p = PROVIDERS[s.provider];
    const note = !s.enabled
      ? t("Off")
      : s.availability && s.availability !== "available"
        ? sourceProblem(s)
        : s.last_success_at
          ? plural(s.item_count, "{count} date", "{count} dates")
          : t("Connecting…");
    return `<div class="cal-row" style="--c:${esc(s.color)}">
      <input type="checkbox" class="swatch" data-act="toggle-source" data-provider="${esc(s.provider)}" ${s.enabled ? "checked" : ""} aria-label="${esc(t("Show dates from {name}", { name: p.name }))}">
      <span class="name">${esc(p.name)} <span class="provider-note">· ${esc(note)}</span></span>
    </div>`;
  };
  const groups = [
    [t("My calendars"), state.calendars.filter((c) => c.kind === "native")],
    [t("Imported"), state.calendars.filter((c) => c.kind === "import")],
    [t("Subscriptions"), state.calendars.filter((c) => c.kind === "subscription")],
  ];
  $("#sidebar").innerHTML = `
    <section class="mini" aria-label="${esc(t("Month overview"))}">
      <div class="mini-head"><span>${esc(fmtDay(first, { month: "long", year: "numeric" }))}</span>
        <span><button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="mini-prev" aria-label="${esc(t("Previous month"))}">${icon("left")}</button><button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="mini-next" aria-label="${esc(t("Next month"))}">${icon("right")}</button></span></div>
      <div class="mini-grid">${weekdayNames("narrow").map((w) => `<span class="wd">${esc(w)}</span>`).join("")}
        ${days.map((d) => `<button data-act="goto" data-day="${d}" class="${[d.slice(0, 7) !== first.slice(0, 7) ? "out" : "", d === now ? "today" : "", d === state.cursor ? "selected" : d >= range.start && d <= rangeEnd && state.view !== "month" ? "in-range" : ""].join(" ")}" aria-label="${esc(fmtDay(d, { dateStyle: "full" }))}">${Number(d.slice(8))}</button>`).join("")}
      </div>
    </section>
    ${groups
      .filter(([, list], i) => i === 0 || list.length)
      .map(
        ([label, list], i) => `<section class="side-section">
          <div class="side-head"><span class="ae-eyebrow">${esc(label)}</span>${i === 0 ? `<button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="new-calendar" aria-label="${esc(t("New calendar"))}" data-tip="${esc(t("New calendar"))}">${icon("plus")}</button>` : ""}</div>
          ${list.map(calendarRow).join("")}
        </section>`,
      )
      .join("")}
    <section class="side-section">
      <div class="side-head"><span class="ae-eyebrow">${esc(t("Shared with Chronos"))}</span><button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="settings" aria-label="${esc(t("Sharing settings"))}">${icon("gear")}</button></div>
      ${state.sources.map(sourceRow).join("")}
    </section>
    <section class="side-section">
      <div class="side-head"><span class="ae-eyebrow">${esc(t("Categories"))}</span><button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="new-category" aria-label="${esc(t("New category"))}" data-tip="${esc(t("New category"))}">${icon("plus")}</button></div>
      ${
        state.categories.length
          ? `<div class="chips">${state.categories.map((c) => `<button class="ae-chip" data-act="filter-category" data-id="${esc(c.id)}" aria-pressed="${state.categoryFilter.has(c.id)}" style="color:${esc(c.color)}"><span class="ae-dot"></span><span style="color:var(--text-2)">${esc(c.name)}</span></button>`).join("")}${state.categoryFilter.size ? `<button class="ae-chip" data-act="clear-filter">${esc(t("Show all"))}</button>` : ""}</div>`
          : `<p class="ae-meta" style="padding:0 var(--space-2);margin:0">${esc(t("Group events by what they are about."))}</p>`
      }
    </section>`;
  $("#side-trash").innerHTML = `<button class="side-link" data-act="trash" ${state.screen === "trash" ? 'aria-current="page"' : ""}>${icon("trash")}<span class="grow">${esc(t("Trash"))}</span>${state.trashCount ? `<span class="side-count">${state.trashCount}</span>` : ""}</button>`;
}
function sourceProblem(source) {
  return (
    {
      module_uninstalled: t("not installed"),
      module_disabled: t("stopped"),
      not_provided: t("does not share dates"),
      forbidden: t("declined to share"),
      not_granted: t("not permitted"),
      nexus_unreachable: t("Nexus unreachable"),
    }[source.availability] || t("unavailable")
  );
}

function titleText() {
  const c = state.cursor;
  if (state.screen === "trash") return `<span class="t-main">${esc(t("Trash"))}</span>`;
  if (state.results) return esc(t("Search"));
  if (state.view === "month")
    return `<span class="t-main">${esc(fmtDay(c, { month: "long" }))}</span> <span class="sub">${esc(fmtDay(c, { year: "numeric" }))}</span>`;
  if (state.view === "week") {
    const s = startOfWeek(c);
    const e = addDays(s, 6);
    const sameMonth = s.slice(0, 7) === e.slice(0, 7);
    return `<span class="t-main">${esc(fmtDay(s, sameMonth ? { day: "numeric" } : { day: "numeric", month: "short" }))} – ${esc(fmtDay(e, { day: "numeric", month: "short" }))}</span> <span class="sub">${esc(fmtDay(e, { year: "numeric" }))}</span>`;
  }
  if (state.view === "day")
    return `<span class="t-main">${esc(fmtDay(c, { weekday: "long" }))}</span> <span class="sub">${esc(fmtDay(c, { day: "numeric", month: "long", year: "numeric" }))}</span>`;
  return `<span class="t-main">${esc(state.agendaPast ? t("Past events") : t("Upcoming"))}</span>`;
}

function renderView() {
  $("#title").innerHTML = titleText();
  const inTrash = state.screen === "trash";
  $$(".views button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === state.view && !state.results && !inTrash && !state.notice)));
  $("#app").classList.toggle("in-trash", inTrash);
  const search = $("#search");
  if (search) search.placeholder = inTrash ? t("Search Trash") : t("Search events");
  const view = $("#view");
  if (state.notFound) return (view.innerHTML = `<div class="ae-empty">${icon("alert")}<h3>${esc(t("This page could not be found"))}</h3><p>${esc(t("The address may be wrong, or the event may have been removed."))}</p><button class="ae-btn" data-act="today">${esc(t("Today"))}</button></div>`);
  if (state.notice) return renderTrashNotice(view);
  if (inTrash) return renderTrash(view);
  if (state.results) return renderResults(view);
  if (state.error)
    return (view.innerHTML = `<div class="ae-banner ae-banner--danger view-error">${icon("alert")}<div><strong>${esc(t("Events could not be loaded."))}</strong><br>${esc(state.error)}</div><button class="ae-btn ae-btn--sm" data-act="reload">${esc(t("Try again"))}</button></div>`);
  if (state.loading) return (view.innerHTML = skeleton());
  ({ month: renderMonth, week: renderWeek, day: renderWeek, agenda: renderAgenda })[state.view](view);
  renderSidebar();
}
function skeleton() {
  return `<div style="padding:var(--space-5);display:grid;gap:10px">${Array.from({ length: 6 }, (_, i) => `<div class="ae-skeleton" style="height:${i ? 52 : 28}px;width:${i ? 100 : 30}%"></div>`).join("")}</div>`;
}

/* ───────────────────────── Month ───────────────────────── */

function chip(o, day) {
  const classes = ["chip", o.all_day || o.sDay !== o.eDay ? "allday" : "", o.origin === "projection" ? "projection" : "", o.status];
  const time = !o.all_day && o.sDay === day ? `<span class="t">${esc(fmtTime(o.start))}</span>` : "";
  return `<button class="${classes.join(" ")}" style="--c:${esc(o.color)}" data-open="${esc(o.key)}" title="${esc(o.title)}"><span class="dot"></span>${time}<span class="label">${esc(o.title)}</span></button>`;
}
function sortForDay(list) {
  return list.sort(
    (a, b) =>
      (b.all_day || b.sDay !== b.eDay) - (a.all_day || a.sDay !== a.eDay) ||
      (a.sMin ?? 0) - (b.sMin ?? 0) ||
      a.title.localeCompare(b.title),
  );
}
function renderMonth(view) {
  const { start } = viewRange();
  const list = placed();
  const month = state.cursor.slice(0, 7);
  const now = today();
  const limit = window.innerHeight > 900 ? 4 : 3;
  const cells = Array.from({ length: 42 }, (_, i) => {
    const day = addDays(start, i);
    const items = sortForDay(onDay(list, day));
    const shown = items.slice(0, items.length > limit ? limit - 1 : limit);
    const w = weekday(day);
    return `<div class="cell ${day.slice(0, 7) !== month ? "out" : ""} ${day === now ? "today" : ""} ${w === 0 || w === 6 ? "weekend" : ""}" data-day="${day}">
      <button class="num" data-act="open-day" data-day="${day}" aria-label="${esc(fmtDay(day, { dateStyle: "full" }))}">${Number(day.slice(8))}</button>
      ${shown.map((o) => chip(o, day)).join("")}
      ${items.length > shown.length ? `<button class="more" data-act="open-day" data-day="${day}">${esc(t("{count} more", { count: items.length - shown.length }))}</button>` : ""}
    </div>`;
  });
  view.innerHTML = `<div class="month" role="grid" aria-label="${esc(fmtDay(state.cursor, { month: "long", year: "numeric" }))}">
    <div class="month-head">${weekdayNames().map((w) => `<div>${esc(w)}</div>`).join("")}</div>
    ${Array.from({ length: 6 }, (_, r) => `<div class="month-row">${cells.slice(r * 7, r * 7 + 7).join("")}</div>`).join("")}
  </div>`;
}

/* ───────────────────────── Week / Day ───────────────────────── */

function layoutDay(items) {
  // Greedy columns within clusters of overlapping events.
  const sorted = items.slice().sort((a, b) => a.top - b.top || b.bottom - a.bottom);
  let cluster = [];
  let clusterEnd = -1;
  const flush = () => {
    const columns = [];
    for (const item of cluster) {
      let index = columns.findIndex((end) => end <= item.top);
      if (index === -1) index = columns.push(0) - 1;
      columns[index] = item.bottom;
      item.col = index;
    }
    cluster.forEach((item) => (item.cols = columns.length));
    cluster = [];
  };
  for (const item of sorted) {
    if (item.top >= clusterEnd && cluster.length) flush();
    cluster.push(item);
    clusterEnd = Math.max(clusterEnd, item.bottom);
  }
  if (cluster.length) flush();
  return sorted;
}
function renderWeek(view) {
  const { start, days } = viewRange();
  const dayKeys = Array.from({ length: days }, (_, i) => addDays(start, i));
  const list = placed();
  const now = today();
  const names = weekdayNames();
  const nowParts = zoneParts(new Date());
  const allDay = (day) =>
    sortForDay(onDay(list.filter((o) => o.all_day || o.sDay !== o.eDay), day))
      .map((o) => chip(o, day))
      .join("");
  const column = (day) => {
    const blocks = layoutDay(
      onDay(list.filter((o) => !o.all_day && o.sDay === o.eDay), day).map((o) => ({
        o,
        top: o.sMin,
        bottom: Math.max(o.eMin, o.sMin + 20),
      })),
    )
      .map(({ o, top, bottom, col, cols }) => {
        const height = ((bottom - top) / 60) * 100;
        const short = bottom - top < 45;
        return `<button class="block ${o.origin === "projection" ? "projection" : ""} ${o.status} ${short ? "short" : ""}" style="--c:${esc(o.color)};top:calc(${top / 60} * var(--hour));height:calc(${height / 100} * var(--hour) - 2px);left:calc(${(col / cols) * 100}% + 2px);width:calc(${100 / cols}% - 4px)" data-open="${esc(o.key)}"><span class="title">${esc(o.title)}</span><span class="when">${esc(fmtTime(o.start))} – ${esc(fmtTime(o.end))}</span></button>`;
      })
      .join("");
    const w = weekday(day);
    const line = day === now ? `<div class="now-line" style="top:calc(${nowParts.minutes / 60} * var(--hour))"></div>` : "";
    return `<div class="col ${day === now ? "today" : ""} ${w === 0 || w === 6 ? "weekend" : ""}" data-slot="${day}">${blocks}${line}</div>`;
  };
  view.innerHTML = `<div class="week" style="--days:${days}">
    <div class="week-head"><div></div>${dayKeys.map((d) => `<div class="day-h ${d === now ? "today" : ""}"><span>${esc(days === 1 ? fmtDay(d, { weekday: "long" }) : names[(weekday(d) - state.settings.week_start + 7) % 7])}</span><button data-act="open-day" data-day="${d}" aria-label="${esc(fmtDay(d, { dateStyle: "full" }))}">${Number(d.slice(8))}</button></div>`).join("")}</div>
    <div class="allday-lane"><div class="gutter-label">${esc(t("all-day"))}</div>${dayKeys.map((d) => `<div class="lane" data-allday="${d}">${allDay(d)}</div>`).join("")}</div>
    <div class="grid-scroll" id="grid-scroll"><div class="grid-body">
      <div class="hours">${Array.from({ length: 23 }, (_, h) => `<span style="top:calc(${h + 1} * var(--hour))">${esc(fmtHour(h + 1))}</span>`).join("")}</div>
      ${dayKeys.map(column).join("")}
    </div></div>
  </div>`;
  const scroller = $("#grid-scroll");
  const firstEvent = Math.min(...list.filter((o) => !o.all_day && dayKeys.includes(o.sDay)).map((o) => o.sMin), 7 * 60);
  const hour = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--hour")) || 52;
  scroller.scrollTop = Math.max(0, (Math.min(firstEvent, 8 * 60) / 60) * hour - hour / 2);
}

/* ───────────────────────── Agenda / search ───────────────────────── */

function rowHtml(o, day) {
  let time;
  if (o.all_day) time = t("All day");
  else if (o.sDay !== o.eDay) time = o.sDay === day ? `${fmtTime(o.start)} →` : o.eDay === day ? `→ ${fmtTime(o.end)}` : t("All day");
  else time = o.start === o.end ? fmtTime(o.start) : `${fmtTime(o.start)} – ${fmtTime(o.end)}`;
  const tags = [];
  if (o.origin === "projection") {
    tags.push(`<span class="ae-pill">${esc(PROVIDERS[o.provider]?.name || o.provider)}</span>`);
    if (o.certainty !== "confirmed") tags.push(`<span class="ae-pill ae-pill--warn">${esc(o.certainty === "estimated" ? t("Estimated") : t("May change"))}</span>`);
  }
  if (o.status === "tentative") tags.push(`<span class="ae-pill">${esc(t("Tentative"))}</span>`);
  if (o.status === "cancelled") tags.push(`<span class="ae-pill ae-pill--danger">${esc(t("Cancelled"))}</span>`);
  const meta = [o.origin === "projection" ? o.context || o.group_label || PROVIDERS[o.provider]?.name : o.calendar_name, o.location].filter(Boolean).join(" · ");
  return `<button class="row ${o.origin === "projection" ? "projection" : ""} ${o.status}" style="--c:${esc(o.color)}" data-open="${esc(o.key)}">
    <span class="time">${esc(time)}</span><span class="bar"></span>
    <span class="main-text"><span class="title">${esc(o.title)}</span>${meta ? `<span class="meta">${esc(meta)}</span>` : ""}</span>
    <span class="tags">${tags.join("")}</span></button>`;
}
function renderAgenda(view) {
  const { start, days } = viewRange();
  const list = placed();
  const now = today();
  let keys = Array.from({ length: days }, (_, i) => addDays(start, i));
  if (state.agendaPast) keys = keys.reverse();
  const sections = keys
    .map((day) => {
      const items = sortForDay(onDay(list, day));
      if (!items.length) return "";
      return `<section class="agenda-day ${day === now ? "today" : ""}"><div class="date"><span class="d">${Number(day.slice(8))}</span><span class="w">${esc(fmtDay(day, { weekday: "long" }))}</span><span class="m">${esc(day === now ? t("Today") : fmtDay(day, { month: "long" }))}</span></div><div class="day-items">${items.map((o) => rowHtml(o, day)).join("")}</div></section>`;
    })
    .join("");
  view.innerHTML = `<div class="agenda">
    <div class="agenda-tools"><div class="ae-seg" role="group"><button data-act="agenda-upcoming" aria-pressed="${!state.agendaPast}">${esc(t("Upcoming"))}</button><button data-act="agenda-past" aria-pressed="${state.agendaPast}">${esc(t("Past"))}</button></div><span class="ae-meta">${esc(state.agendaPast ? plural(state.agendaDays, "Last {count} day", "Last {count} days") : plural(state.agendaDays, "Next {count} day", "Next {count} days"))}</span></div>
    ${sections || `<div class="ae-empty">${icon("calendar")}<h3>${esc(state.agendaPast ? t("Nothing in the past {count} days", { count: days }) : t("Nothing scheduled"))}</h3><p>${esc(state.agendaPast ? t("Earlier events are still in Month and Week views.") : t("Your next {count} days are clear.", { count: days }))}</p></div>`}
    ${state.agendaDays < 120 ? `<div style="text-align:center;margin-top:var(--space-5)"><button class="ae-btn ae-btn--quiet" data-act="agenda-more">${esc(t("Show more"))}</button></div>` : ""}
  </div>`;
}
let searchTimer;
function onSearch(event) {
  state.query = event.target.value;
  clearTimeout(searchTimer);
  if (state.screen === "trash") {
    searchTimer = setTimeout(() => loadTrash({ quiet: true }), 220);
    return;
  }
  searchTimer = setTimeout(async () => {
    if (state.query.trim().length < 2) {
      state.results = null;
      return renderView();
    }
    const query = state.query;
    try {
      const data = await api("/search?q=" + encodeURIComponent(query.trim()));
      if (query === state.query) {
        state.results = data;
        renderView();
      }
    } catch (error) {
      toast(error.message, "danger");
    }
  }, 220);
}
function renderResults(view) {
  const { events, projected } = state.results;
  const now = new Date().toISOString();
  const asOccurrence = (e) => ({ ...e, key: `${e.id}/`, event_id: e.id, sDay: e.all_day ? e.start : zoneParts(new Date(e.start)).day, eDay: e.all_day ? addDays(e.end, -1) : zoneParts(new Date(e.end)).day, status: "confirmed" });
  const all = [...events.map(asOccurrence), ...projected.map((p) => ({ ...p, sDay: p.all_day ? p.start : zoneParts(new Date(p.start)).day, eDay: p.all_day ? addDays(p.end, -1) : zoneParts(new Date(p.end)).day }))];
  state.searchIndex = new Map(all.map((o) => [o.key, o]));
  const upcoming = all.filter((o) => (o.all_day ? o.end > today() : o.end >= now) || o.recurring).sort((a, b) => a.start.localeCompare(b.start));
  const past = all.filter((o) => !upcoming.includes(o)).sort((a, b) => b.start.localeCompare(a.start));
  const group = (label, items) =>
    items.length
      ? `<h2 class="ae-eyebrow search-head">${esc(label)}</h2>${items.map((o) => `<div class="agenda-day"><div class="date"><span class="w">${esc(fmtDay(o.sDay, { day: "numeric", month: "short", year: "numeric" }))}</span></div><div>${rowHtml(o, o.sDay)}</div></div>`).join("")}`
      : "";
  view.innerHTML = `<div class="agenda">${upcoming.length || past.length ? group(t("Upcoming"), upcoming) + group(t("Past"), past) : `<div class="ae-empty">${icon("search")}<h3>${esc(t("No events match “{query}”", { query: state.query.trim() }))}</h3><p>${esc(t("Search covers titles, places and descriptions in every calendar."))}</p></div>`}</div>`;
}

/* ───────────────────────── Details drawer ───────────────────────── */

function findOccurrence(key) {
  return state.occurrences.find((o) => o.key === key) || state.searchIndex?.get(key);
}
/** Close the details drawer. Its address goes with it: a push when the owner closes it, a
 * replace when an action made the record go away. */
function closeLayer({ mode = "push" } = {}) {
  closeLayerUI();
  if (chronosNavigation.enabled && routeHasDetail()) commitRoute(shownParsed?.trash ? { trash: {} } : calendarRoute(), mode);
}
let detailSerial = 0;
function closeLayerUI() {
  ++detailSerial;
  const drawer = $(".ae-drawer");
  if (!drawer) return;
  drawer.classList.add("is-leaving");
  $(".ae-scrim")?.remove();
  // Only the drawer that was closing: another may have opened in the meantime.
  setTimeout(() => {
    if ($(".ae-drawer")?.classList.contains("is-leaving")) $("#layer").innerHTML = "";
  }, reducedMotion() ? 0 : 170);
  state.selected?.returnFocus?.focus?.();
  state.selected = null;
}
function whenText(o) {
  if (o.all_day) {
    const last = addDays(o.end, -1);
    return last === o.start
      ? fmtDay(o.start, { weekday: "long", day: "numeric", month: "long", year: "numeric" })
      : `${fmtDay(o.start, { day: "numeric", month: "short" })} – ${fmtDay(last, { day: "numeric", month: "short", year: "numeric" })}`;
  }
  const s = zoneParts(new Date(o.start));
  const e = zoneParts(new Date(o.end));
  const day = fmtDay(s.day, { weekday: "long", day: "numeric", month: "long" });
  if (o.start === o.end) return `${day}, ${fmtTime(o.start)}`;
  return s.day === e.day
    ? `${day}, ${fmtTime(o.start)} – ${fmtTime(o.end)}`
    : `${day}, ${fmtTime(o.start)} – ${fmtDay(e.day, { day: "numeric", month: "short" })}, ${fmtTime(o.end)}`;
}
function ruleText(rrule, start) {
  if (!rrule) return "";
  const parts = Object.fromEntries(rrule.replace(/^RRULE:/i, "").split(";").map((p) => p.split("=")));
  const n = Number(parts.INTERVAL || 1);
  const unit = { DAILY: ["Every day", "Every {count} days"], WEEKLY: ["Every week", "Every {count} weeks"], MONTHLY: ["Every month", "Every {count} months"], YEARLY: ["Every year", "Every {count} years"] }[parts.FREQ];
  let text = unit ? plural(n, unit[0], unit[1]) : t("Repeats");
  if (parts.BYDAY) {
    const map = { SU: 0, MO: 1, TU: 2, WE: 3, TH: 4, FR: 5, SA: 6 };
    const names = parts.BYDAY.split(",").map((d) => new Intl.DateTimeFormat(activeLocale, { weekday: "short", timeZone: "UTC" }).format(toDate(addDays("2023-01-01", map[d.slice(-2)] ?? 0))));
    text += " · " + names.join(", ");
  }
  if (parts.COUNT) text += " · " + plural(Number(parts.COUNT), "{count} time", "{count} times");
  if (parts.UNTIL) text += " · " + t("until {date}", { date: fmtDay(`${parts.UNTIL.slice(0, 4)}-${parts.UNTIL.slice(4, 6)}-${parts.UNTIL.slice(6, 8)}`, { day: "numeric", month: "short", year: "numeric" }) });
  return text;
}
async function openDetails(key, trigger) {
  const o = findOccurrence(key);
  if (!o) return;
  const serial = ++detailSerial;
  state.selected = { key, returnFocus: trigger };
  const isProjection = o.origin === "projection";
  let event = null;
  if (!isProjection) {
    event = await attempt(() => api(`/events/${o.event_id}`));
    // Superseded while loading: the late response must not open over the newer screen.
    if (serial !== detailSerial) return;
    if (!event) return;
  }
  const facts = [];
  facts.push(`<div class="fact">${icon("clock")}<div><span class="primary">${esc(whenText(o))}</span>${!o.all_day && o.time_zone && o.time_zone !== tz() ? `<span class="secondary">${esc(t("Scheduled in {zone}", { zone: zoneLabel(o.time_zone) }))} · ${esc(fmtTime(o.start, o.time_zone))}</span>` : ""}${event?.rrule ? `<span class="secondary">${esc(ruleText(event.rrule, event.start))}</span>` : ""}</div></div>`);
  if (isProjection) {
    const p = PROVIDERS[o.provider] || { name: o.provider, icon: "layers" };
    const pills = [];
    if (o.certainty === "tentative") pills.push(`<span class="ae-pill ae-pill--warn">${esc(t("Date may change"))}</span>`);
    if (o.certainty === "estimated") pills.push(`<span class="ae-pill ae-pill--warn">${esc(t("Estimated date"))}</span>`);
    if (o.certainty === "confirmed") pills.push(`<span class="ae-pill ae-pill--good">${esc(t("Confirmed"))}</span>`);
    if (o.status === "completed") pills.push(`<span class="ae-pill ae-pill--good">${esc(t("Completed"))}</span>`);
    if (o.status === "cancelled" || o.status === "postponed") pills.push(`<span class="ae-pill ae-pill--danger">${esc(o.status === "cancelled" ? t("Cancelled") : t("Postponed"))}</span>`);
    facts.push(`<div class="fact">${icon(p.icon)}<div><span class="primary">${esc(t("From {name}", { name: p.name }))}${o.group_label ? ` · ${esc(o.group_label)}` : ""}${o.context ? ` · ${esc(o.context)}` : ""}</span><span class="secondary">${esc(t("{name} owns this date. Chronos shows a copy that updates when {name} changes it.", { name: p.name }))}</span><span class="pills">${pills.join("")}</span></div></div>`);
    if (o.summary) facts.push(`<div class="fact">${icon("text")}<div><span class="primary">${esc(o.summary)}</span></div></div>`);
  } else {
    const prov = event.provenance;
    const where =
      prov.kind === "subscription"
        ? t("Subscribed calendar “{name}”, updated {when}", { name: prov.name, when: relative(prov.synced_at) })
        : prov.kind === "import"
          ? t("Imported from {file} into “{name}”", { file: prov.filename || t("a file"), name: prov.name })
          : prov.name;
    facts.push(`<div class="fact">${icon(prov.kind === "subscription" ? "feed" : prov.kind === "import" ? "upload" : "calendar")}<div><span class="primary">${esc(where)}</span>${event.readonly ? `<span class="secondary">${esc(t("Read-only here. The calendar it came from stays authoritative."))}</span>` : ""}</div></div>`);
    const category = state.categories.find((c) => c.id === event.category_id);
    if (category) facts.push(`<div class="fact">${icon("tag")}<div><span class="primary" style="color:${esc(category.color)}">${esc(category.name)}</span></div></div>`);
    if (event.location) facts.push(`<div class="fact">${icon("pin")}<div><span class="primary">${esc(event.location)}</span></div></div>`);
    if (event.status !== "confirmed") facts.push(`<div class="fact">${icon("info")}<div><span class="primary">${esc(event.status === "tentative" ? t("Tentative") : t("Cancelled"))}</span></div></div>`);
    const about = event.links.filter((l) => !["chronos.involves", "chronos.at"].includes(l.relation));
    const people = event.links.filter((l) => l.relation === "chronos.involves");
    const places = event.links.filter((l) => l.relation === "chronos.at");
    if (about.length) facts.push(`<div class="fact">${icon("link")}<div id="links">${about.map((l) => `<span class="primary">${esc(l.label || l.target)}</span>`).join("")}<span class="secondary">${esc(t("Checking…"))}</span></div></div>`);
    if (people.length || !event.readonly) facts.push(peopleFact(event, people));
    if (places.length || !event.readonly) facts.push(placesFact(event, places));
    facts.push(`<div class="fact" id="linked-fact" hidden>${icon("link")}<div id="linked-from"></div></div>`);
  }
  const actions = [];
  if (isProjection) {
    actions.push(`<button class="ae-btn ae-btn--primary" data-act="plan" data-key="${esc(o.key)}">${icon("plus")}<span>${esc(t("Plan in my calendar"))}</span></button>`);
    if (state.context.applications.some((a) => a.id === o.provider)) actions.push(`<button class="ae-btn" data-act="open-projected" data-key="${esc(o.key)}">${icon("open")}<span>${esc(t("Open {name}", { name: PROVIDERS[o.provider]?.name || o.provider }))}</span></button>`);
  } else if (event.readonly) {
    actions.push(`<button class="ae-btn" data-act="copy" data-id="${esc(event.id)}">${icon("copy")}<span>${esc(t("Copy to my calendar"))}</span></button>`);
  } else {
    actions.push(`<button class="ae-btn ae-btn--primary" data-act="edit" data-id="${esc(event.id)}">${icon("edit")}<span>${esc(t("Edit"))}</span></button>`);
    actions.push(`<span class="grow"></span><button class="ae-btn ae-btn--quiet ae-btn--icon" data-act="event-menu" data-id="${esc(event.id)}" data-occurrence="${esc(o.occurrence || "")}" data-revision="${esc(event.revision)}" aria-label="${esc(t("More actions"))}" aria-haspopup="menu">${icon("more")}</button>`);
  }
  $("#layer").innerHTML = `<div class="ae-scrim" data-act="close"></div>
    <aside class="ae-drawer ae-glass ${isProjection ? "is-projection" : ""}" style="--c:${esc(o.color)}" role="dialog" aria-modal="true" aria-labelledby="details-title">
      <div class="details">
        <div class="details-head"><span class="swatch ${isProjection ? "projection" : ""}" style="--c:${esc(o.color)}"></span><h2 id="details-title" class="${o.status === "cancelled" ? "cancelled" : ""}">${esc(o.title)}</h2><button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="close" aria-label="${esc(t("Close"))}">${icon("x")}</button></div>
        <div class="details-body"><div class="facts">${facts.join("")}</div>${event?.description ? `<p class="description">${esc(event.description)}</p>` : ""}</div>
        <div class="details-foot">${actions.join("")}</div>
      </div>
    </aside>`;
  $(".ae-drawer [data-act=close]").focus();
  if (event) loadLinkedFrom(event.id);
  if (event?.links.length) {
    const result = await api(`/events/${event.id}/links`).catch(() => null);
    const box = $("#links");
    if (box && result)
      box.innerHTML = result.links
        .filter((l) => !["chronos.involves", "chronos.at"].includes(l.relation))
        .map((l) => `<span class="primary">${esc(l.label || l.target)}</span><span class="secondary">${esc(l.availability === "available" ? t("Linked item") : l.availability === "deleted" ? t("The linked item was deleted") : t("The linked item is not available right now"))}</span>`)
        .join("");
    if (result) renderPeople(event, result.links.filter((l) => l.relation === "chronos.involves"));
    if (result) renderPlaces(event, result.links.filter((l) => l.relation === "chronos.at"));
  }
}
/* People on an event: Meridian People linked by reference. Meridian owns them; Chronos keeps
   only the link (and a last-known name), and shows the current name when Meridian answers. */
function personRow(event, l, live) {
  const gone = live && live.availability !== "available";
  const state = !live ? "" : live.availability === "deleted" ? t("No longer in Meridian") : gone ? t("Meridian is not available right now") : "";
  const remove = event.readonly ? "" : `<button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="remove-person" data-event="${esc(event.id)}" data-id="${esc(l.id)}" aria-label="${esc(t("Remove {name}", { name: (live && live.label) || l.label || t("this person") }))}">${icon("x")}</button>`;
  return `<div class="person-row${gone ? " is-gone" : ""}"><span class="grow"><span class="primary">${esc((live && live.label) || l.label || t("A person in Meridian"))}</span>${state ? `<span class="secondary">${esc(state)}</span>` : ""}</span>${remove}</div>`;
}
function peopleFact(event, people) {
  const add = event.readonly ? "" : `<div class="person-add"><button class="ae-btn ae-btn--sm" data-act="add-person" data-event="${esc(event.id)}" aria-expanded="false">${icon("plus")}<span>${esc(t("Add a person"))}</span></button>
    <div class="person-search" hidden><input class="ae-input" type="search" role="combobox" aria-expanded="false" aria-autocomplete="list" aria-controls="person-results" aria-label="${esc(t("Search people in Meridian"))}" placeholder="${esc(t("Search people in Meridian"))}" maxlength="100" autocomplete="off"><div class="person-results" id="person-results" role="listbox"></div></div></div>`;
  return `<div class="fact">${icon("person")}<div class="people" id="people"><div id="people-rows">${people.map((l) => personRow(event, l)).join("")}</div>${!people.length && event.readonly ? "" : add}</div></div>`;
}
function renderPeople(event, links) {
  const box = $("#people-rows");
  if (box) box.innerHTML = links.map((l) => personRow(event, l, l)).join("");
}
async function personSearch(event, input) {
  const box = $("#person-results");
  const q = input.value.trim();
  const mine = (personSearch.seq = (personSearch.seq || 0) + 1);
  const result = await api("/people" + (q ? `?q=${encodeURIComponent(q)}` : "")).catch(() => ({ availability: "nexus_unreachable", items: [] }));
  if (mine !== personSearch.seq || !box) return;
  const linked = new Set(event.links.filter((l) => l.relation === "chronos.involves").map((l) => l.target));
  const items = result.items.filter((p) => !linked.has(p.resource));
  personSearch.items = items;
  const why = { not_granted: t("Chronos is not allowed to search Meridian. Review its permissions in Nexus."), module_uninstalled: t("Meridian is not installed."), module_disabled: t("Meridian is stopped."), not_provided: t("This version of Meridian cannot share names yet.") }[result.availability] || t("Meridian is not available right now.");
  box.innerHTML = result.availability !== "available"
    ? `<p class="person-empty">${esc(why)}</p>`
    : items.length
      ? items.map((p, i) => `<button type="button" class="person-option" role="option" id="person-o${i}" data-act="pick-person" data-index="${i}" data-event="${esc(event.id)}">${icon("person")}<span>${esc(p.label)}</span>${p.self ? `<span class="ae-pill">${esc(t("Me"))}</span>` : ""}</button>`).join("")
      : `<p class="person-empty">${esc(q ? t("No one in Meridian matches “{q}”.", { q }) : t("No people to add."))}</p>`;
  input.setAttribute("aria-expanded", "true");
}

/* Places on an event (0.3.0): Atlas owns the Place; Chronos keeps the link and a last-known name. */
function placeRow(event, l, live) {
  const gone = live && live.availability !== "available";
  const note = !live ? "" : live.availability === "deleted" ? t("No longer in Atlas") : gone ? t("Atlas is not available right now") : "";
  const remove = event.readonly ? "" : `<button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="remove-person" data-event="${esc(event.id)}" data-id="${esc(l.id)}" aria-label="${esc(t("Remove {name}", { name: (live && live.label) || l.label || t("this place") }))}">${icon("x")}</button>`;
  return `<div class="person-row${gone ? " is-gone" : ""}"><span class="grow"><span class="primary">${esc((live && live.label) || l.label || t("A place in Atlas"))}</span>${note ? `<span class="secondary">${esc(note)}</span>` : ""}</span>${remove}</div>`;
}
function placesFact(event, places) {
  const add = event.readonly ? "" : `<div class="person-add"><button class="ae-btn ae-btn--sm" data-act="add-place" data-event="${esc(event.id)}" aria-expanded="false">${icon("plus")}<span>${esc(t("Add a place"))}</span></button>
    <div class="person-search place-search" hidden><input class="ae-input" type="search" aria-label="${esc(t("Search places in Atlas"))}" placeholder="${esc(t("Search places in Atlas"))}" maxlength="100" autocomplete="off"><div class="person-results" id="place-results"></div></div></div>`;
  return `<div class="fact">${icon("pin")}<div class="people"><div id="place-rows">${places.map((l) => placeRow(event, l)).join("")}</div>${!places.length && event.readonly ? "" : add}</div></div>`;
}
function renderPlaces(event, links) {
  const box = $("#place-rows");
  if (box) box.innerHTML = links.map((l) => placeRow(event, l, l)).join("");
}
async function placeSearch(event, input) {
  const box = $("#place-results");
  const q = input.value.trim();
  const mine = (placeSearch.seq = (placeSearch.seq || 0) + 1);
  const result = await api("/places" + (q ? `?q=${encodeURIComponent(q)}` : "")).catch(() => ({ availability: "nexus_unreachable", items: [] }));
  if (mine !== placeSearch.seq || !box) return;
  const linked = new Set(event.links.filter((l) => l.relation === "chronos.at").map((l) => l.target));
  placeSearch.items = result.items.filter((p) => !linked.has(p.resource));
  box.innerHTML = result.availability !== "available"
    ? `<p class="person-empty">${esc(t("Atlas cannot be reached right now."))}</p>`
    : placeSearch.items.length
      ? placeSearch.items.map((p, i) => `<button type="button" class="person-option" data-act="pick-place" data-index="${i}" data-event="${esc(event.id)}">${icon("pin")}<span>${esc(p.label)}</span></button>`).join("")
      : `<p class="person-empty">${esc(q ? t("No place in Atlas matches “{q}”.", { q }) : t("No places to add."))}</p>`;
}
/* Backlinks standard (concepts/backlinks.md). */
const LINKED_KIND = { "meridian:interaction": "Interaction in Meridian", "atlas:place": "Place in Atlas", "mnemosyne:note": "Note in Mnemosyne", "mnemosyne:task": "Task in Mnemosyne", "lyra:movie": "Film in Lyra", "lyra:series": "Series in Lyra" };
async function loadLinkedFrom(id) {
  const result = await api(`/events/${id}/linked-from`).catch(() => null);
  const box = $("#linked-from");
  if (!box || !result || result.availability !== "available" || !result.items.length) return;
  box.innerHTML = `<span class="secondary">${esc(t("Linked from other modules"))}</span>` + result.items.map((x) => {
    const gone = x.availability !== "available";
    const note = x.availability === "deleted" ? t("deleted there") : ["forbidden", "not_found", "not_resolvable"].includes(x.availability) ? t("not available") : gone ? t("not available right now") : "";
    const open = !gone && state.context.applications.some((a) => a.id === x.module) ? `<button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="open-module" data-module="${esc(x.module)}" data-path="${esc(x.open_path || "")}" aria-label="${esc(t("Open {name}", { name: x.module }))}">${icon("open")}</button>` : "";
    return `<div class="person-row${gone ? " is-gone" : ""}"><span class="grow"><span class="primary">${esc(gone ? t("Something linked here") : x.label)}</span><span class="secondary">${esc([t(LINKED_KIND[`${x.module}:${x.type}`] || "Linked from another module"), note].filter(Boolean).join(" · "))}</span></span>${open}</div>`;
  }).join("") + `<span class="secondary">${esc(t("These items belong to their modules."))}</span>`;
  $("#linked-fact").hidden = false;
}

/* ───────────────────────── Trash ───────────────────────── */

const fmtMoment = (instant) =>
  new Intl.DateTimeFormat(activeLocale, { timeZone: tz(), year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", ...hourOptions() }).format(new Date(instant));

async function rerunSearch() {
  if (!state.results || state.query.trim().length < 2) return;
  state.results = await api("/search?q=" + encodeURIComponent(state.query.trim())).catch(() => state.results);
}
async function afterTrashChange() {
  if (state.screen === "trash") await loadTrash({ quiet: true });
  await rerunSearch();
  await refresh();
}

/* A confirmation for moving to Trash or deleting for good. `check` must be ticked first. */
function trashConfirm({ title, text, notes = [], label, check, safeFocus = false, run }) {
  openDialog(`<div class="ae-dialog-head"><h2>${esc(title)}</h2></div>
    <div class="ae-dialog-body confirm-body"><p>${esc(text)}</p>${notes.map((n) => `<div class="ae-banner ae-banner--warn">${icon("alert")}<div>${esc(n)}</div></div>`).join("")}${check ? `<label class="confirm-check"><input type="checkbox" id="confirm-check"><span>${esc(check)}</span></label>` : ""}<p class="ae-error-text" id="confirm-error" hidden></p></div>
    <div class="ae-dialog-foot"><button class="ae-btn" data-act="dialog-cancel" ${safeFocus ? "autofocus" : ""}>${esc(t("Cancel"))}</button><button class="ae-btn ae-btn--danger" id="confirm" ${check ? "disabled" : ""} ${safeFocus ? "" : "autofocus"}>${esc(label)}</button></div>`);
  const d = dialog();
  d.classList.add("trash-dialog");
  if (check) $("#confirm-check", d).onchange = (event) => ($("#confirm", d).disabled = !event.target.checked);
  $("#confirm", d).onclick = async (event) => {
    const button = event.currentTarget;
    button.classList.add("is-busy");
    button.disabled = true;
    try {
      await run();
    } catch (error) {
      button.classList.remove("is-busy");
      button.disabled = false;
      const box = $("#confirm-error", d);
      if (box) {
        box.textContent = error.message;
        box.hidden = false;
      }
    }
  };
}

let trashSerial = 0;
async function loadTrash({ more = false, quiet = false } = {}) {
  const token = ++trashSerial;
  const box = state.trash;
  if (!more && !quiet && !box.items.length) {
    box.loading = true;
    renderView();
  }
  const params = new URLSearchParams({ q: state.query.trim() });
  if (more && box.next) params.set("cursor", box.next);
  try {
    const data = await api(`/trash?${params}`);
    if (token !== trashSerial) return;
    box.items = more ? [...box.items, ...data.items] : data.items;
    box.matched = data.matched;
    box.total = data.total;
    box.generation = data.generation;
    box.next = data.next_cursor;
    box.error = null;
    state.trashCount = data.total;
  } catch (error) {
    if (token !== trashSerial) return;
    box.error = error.message;
  }
  box.loading = false;
  renderView();
}
function openTrash() {
  state.trash.enter = state.screen !== "trash";
  if (chronosNavigation.enabled) {
    if (state.screen !== "trash") clearSearchOnApply = true;
    return commitRoute({ trash: {} });
  }
  state.screen = "trash";
  state.results = null;
  state.notice = null;
  state.query = "";
  if ($("#search")) $("#search").value = "";
  return loadTrash();
}
function openTrashEntry(id, trigger) {
  if (!chronosNavigation.enabled) return openTrashDetails(id, trigger);
  pendingTrigger = trigger;
  return commitRoute({ trash: { id } });
}
function trashPills(entry) {
  const pills = [];
  if (entry.kind === "series") pills.push(`<span class="ae-pill">${esc(t("Series"))}</span>`);
  if (entry.kind === "occurrence") pills.push(`<span class="ae-pill">${esc(t("One occurrence"))}</span>`);
  if (entry.cause === "calendar") pills.push(`<span class="ae-pill ae-pill--warn">${esc(t("Calendar deleted"))}</span>`);
  return pills.join("");
}
function trashRow(entry) {
  const restoreButton =
    entry.blocked === "series_in_trash"
      ? `<button class="ae-btn ae-btn--sm" disabled data-tip="${esc(t("Restore the series first"))}">${esc(t("Restore"))}</button>`
      : entry.blocked === "occurrence_gone"
        ? `<button class="ae-btn ae-btn--sm" data-act="trash-open" data-id="${esc(entry.id)}">${esc(t("Options"))}</button>`
        : `<button class="ae-btn ae-btn--sm" data-act="trash-restore" data-id="${esc(entry.id)}" aria-label="${esc(t("Restore {name}", { name: entry.title }))}">${esc(t("Restore"))}</button>`;
  return `<li class="trash-row" data-row="${esc(entry.id)}" style="--c:${esc(entry.color)}">
    <button class="trash-open" data-act="trash-open" data-id="${esc(entry.id)}">
      <span class="bar"></span>
      <span class="main-text"><span class="title">${esc(entry.title)}</span><span class="meta">${esc([whenText(entry), entry.calendar.name].join(" · "))}</span></span>
      <span class="tags">${trashPills(entry)}</span>
      <span class="trash-time" title="${esc(fmtMoment(entry.deleted_at))}">${esc(t("Deleted {when}", { when: relative(entry.deleted_at) }))}</span>
    </button>
    <span class="trash-actions">${restoreButton}<button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="trash-purge" data-id="${esc(entry.id)}" aria-label="${esc(t("Delete {name} for good", { name: entry.title }))}" data-tip="${esc(t("Delete for good"))}">${icon("trash")}</button></span>
  </li>`;
}
function renderTrash(view) {
  renderSidebar();
  const box = state.trash;
  if (box.error && !box.items.length) {
    view.innerHTML = `<div class="ae-banner ae-banner--danger view-error">${icon("alert")}<div><strong>${esc(t("Trash could not be loaded."))}</strong><br>${esc(box.error)}</div><button class="ae-btn ae-btn--sm" data-act="trash-retry">${esc(t("Try again"))}</button></div>`;
    return;
  }
  if (box.loading && !box.items.length) {
    view.innerHTML = skeleton();
    return;
  }
  const query = state.query.trim();
  const summary = query
    ? plural(box.matched, "{count} match in Trash", "{count} matches in Trash")
    : box.total
      ? `${plural(box.total, "{count} deleted item", "{count} deleted items")} · ${t("Kept until you restore or delete them.")}`
      : "";
  const body = !box.total
    ? `<div class="ae-empty">${icon("trash")}<h3>${esc(t("Trash is empty"))}</h3><p>${esc(t("Events you delete stay here until you restore them or delete them for good."))}</p></div>`
    : !box.items.length
      ? `<div class="ae-empty">${icon("search")}<h3>${esc(t("Nothing in Trash matches “{query}”", { query }))}</h3><p>${esc(t("Search covers titles, places, descriptions and calendar names."))}</p></div>`
      : `<ul class="trash-list">${box.items.map(trashRow).join("")}</ul>${box.next ? `<div class="trash-more"><button class="ae-btn ae-btn--quiet" data-act="trash-more">${esc(t("Show more"))}</button></div>` : ""}`;
  view.innerHTML = `<div class="trash">
    <div class="trash-head"><p class="trash-lead" role="status">${esc(summary)}</p><span class="spacer"></span>
      <button class="ae-btn ae-btn--quiet ae-btn--sm" data-act="back-calendar">${icon("left")}<span>${esc(t("Back to calendar"))}</span></button>
      ${box.total ? `<button class="ae-btn ae-btn--sm ae-btn--danger" data-act="trash-empty">${esc(t("Empty Trash"))}</button>` : ""}</div>
    ${body}
  </div>`;
  if (box.enter) {
    box.enter = false;
    animate($(".trash", view), [{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }], { duration: MOTION.page, easing: MOTION.ease });
  }
}
/** The screen for a link to something that is in Trash: say so, and offer the way back. */
function renderTrashNotice(view) {
  renderSidebar();
  const entry = state.notice;
  view.innerHTML = `<div class="ae-empty trash-notice">${icon("trash")}
    <h3>${esc(entry.kind === "occurrence" ? t("This occurrence is in Trash") : t("This event is in Trash"))}</h3>
    <p>${esc(t("“{name}” was deleted {when}. It stays recoverable until it is deleted for good.", { name: entry.title, when: relative(entry.deleted_at) }))}</p>
    <div class="trash-notice-actions">
      ${entry.blocked ? "" : `<button class="ae-btn ae-btn--primary" data-act="notice-restore" data-id="${esc(entry.id)}">${esc(t("Restore"))}</button>`}
      <button class="ae-btn" data-act="trash-open" data-id="${esc(entry.id)}">${esc(t("View in Trash"))}</button>
      <button class="ae-btn ae-btn--quiet" data-act="back-calendar">${esc(t("Back to calendar"))}</button>
    </div>
  </div>`;
  animate($(".trash-notice", view), [{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }], { duration: MOTION.page, easing: MOTION.ease });
}
async function noticeRestore(id) {
  const result = await restoreEntry(id);
  if (!result) return;
  state.notice = null;
  if (chronosNavigation.enabled && shownParsed) return showRoute(shownParsed, null);
  renderView();
}
function restoredMessage(result) {
  if (result.separate) return t("Restored as a separate event");
  if (result.calendar_restored) return t("Restored, together with its calendar");
  return { occurrence: t("Occurrence restored"), series: t("Series restored") }[result.restored] || t("Event restored");
}
function showRestored(result) {
  const day = result.all_day ? result.start : zoneParts(new Date(result.start)).day;
  if (chronosNavigation.enabled) return commitRoute({ event: { id: result.event_id, occurrence: result.occurrence || "" }, view: state.view, date: day });
  state.screen = "calendar";
  state.cursor = day;
  return loadOccurrences();
}
/** The same restore serves Undo, the Trash list, its details and a link to a deleted event. */
async function restoreEntry(id, body = {}, leave = null) {
  try {
    const result = await api(`/trash/${id}/restore`, "POST", body);
    await leave?.();
    toast(restoredMessage(result), "", { label: t("Show"), run: () => showRestored(result) });
    await afterTrashChange();
    return result;
  } catch (error) {
    toast(error.message, "danger");
    await afterTrashChange();
    return null;
  }
}
async function restoreBatch(batch) {
  try {
    const result = await api(`/trash/batches/${batch}/restore`, "POST");
    if ($(".ae-drawer") && state.screen === "trash") closeLayer({ mode: "replace" });
    toast(plural(result.restored, "{count} event restored", "{count} events restored"));
    await afterTrashChange();
  } catch (error) {
    toast(error.message, "danger");
  }
}
/** Collapse a row out of the list, then hand focus to what took its place. */
function rowLeaves(row) {
  if (!row) return Promise.resolve();
  const height = row.offsetHeight;
  return animate(row, [{ opacity: 1, height: `${height}px` }, { opacity: 0, height: "0px" }], { duration: MOTION.exit, easing: MOTION.exitEase, fill: "forwards" });
}
function focusAfterRemoval(index) {
  const rows = $$(".trash-open");
  (rows[Math.min(index, rows.length - 1)] || $(".trash-head .ae-btn") || $("#view"))?.focus?.();
}
async function trashRestoreRow(id, target, body = {}) {
  const row = $(`.trash-row[data-row="${CSS.escape(id)}"]`);
  const index = $$(".trash-row").indexOf(row);
  target.classList.add("is-busy");
  target.disabled = true;
  const inDrawer = !!target.closest(".ae-drawer");
  const result = await restoreEntry(id, body, async () => {
    if (inDrawer) closeLayer({ mode: "replace" });
    await rowLeaves(row);
  });
  if (!result) {
    target.classList.remove("is-busy");
    target.disabled = false;
    return;
  }
  if (state.screen === "trash") focusAfterRemoval(index);
}
async function trashPurge(id) {
  const entry = await attempt(() => api(`/trash/${id}`));
  if (!entry) return;
  const notes = [];
  if (entry.occurrences_in_trash) notes.push(plural(entry.occurrences_in_trash, "Its {count} deleted occurrence goes with it.", "Its {count} deleted occurrences go with it."));
  if (entry.kind !== "occurrence") {
    const linked = await api(`/events/${entry.event_id}/linked-from`).catch(() => null);
    if (!linked || linked.availability !== "available") notes.push(t("Chronos could not check whether other modules link to this event."));
    else if (linked.items.length) notes.push(plural(linked.items.length, "{count} item in another module links to this event. It will show as deleted there.", "{count} items in other modules link to this event. It will show as deleted there."));
  }
  trashConfirm({
    title: t("Delete “{name}” for good?", { name: entry.title }),
    text: entry.kind === "occurrence" ? t("This occurrence can no longer be restored and stays off the series. The rest of the series is not affected.") : t("This cannot be undone. Everything about this event is removed from Chronos."),
    notes,
    label: t("Delete for good"),
    safeFocus: true,
    run: async () => {
      const row = $(`.trash-row[data-row="${CSS.escape(id)}"]`);
      const index = $$(".trash-row").indexOf(row);
      await api(`/trash/${id}?confirmed=true`, "DELETE");
      await leaveDialog();
      if ($(".ae-drawer") && state.screen === "trash") closeLayer({ mode: "replace" });
      await rowLeaves(row);
      toast(t("Deleted for good"));
      await afterTrashChange();
      if (state.screen === "trash") focusAfterRemoval(index);
    },
  });
}
function trashEmpty() {
  const count = state.trash.total;
  const generation = state.trash.generation;
  trashConfirm({
    title: t("Empty Trash?"),
    text: plural(count, "{count} deleted item is removed for good. This cannot be undone.", "All {count} deleted items are removed for good. This cannot be undone."),
    check: t("I understand that these items cannot be recovered."),
    label: t("Empty Trash"),
    safeFocus: true,
    run: async () => {
      try {
        await api("/trash/empty", "POST", { confirmed: true, expected_generation: generation });
      } catch (error) {
        await loadTrash({ quiet: true });
        throw error;
      }
      await leaveDialog();
      toast(t("Trash emptied"));
      await afterTrashChange();
    },
  });
}
async function openTrashDetails(id, trigger) {
  const serial = ++detailSerial;
  state.selected = { key: `trash:${id}`, returnFocus: trigger };
  let entry;
  try {
    entry = await api(`/trash/${id}`);
  } catch (error) {
    if (serial !== detailSerial) return "stale";
    state.selected = null;
    toast(error.message, "danger");
    return "missing";
  }
  if (serial !== detailSerial) return "stale";
  const facts = [];
  facts.push(`<div class="fact">${icon("clock")}<div><span class="primary">${esc(whenText(entry))}</span>${entry.rrule ? `<span class="secondary">${esc(ruleText(entry.rrule, entry.start))}</span>` : ""}${entry.kind === "occurrence" ? `<span class="secondary">${esc(t("One occurrence of a repeating event"))}</span>` : ""}</div></div>`);
  facts.push(`<div class="fact">${icon("trash")}<div><span class="primary">${esc(t("Deleted {when}", { when: relative(entry.deleted_at) }))}</span><span class="secondary">${esc(fmtMoment(entry.deleted_at))}</span></div></div>`);
  facts.push(`<div class="fact">${icon("calendar")}<div><span class="primary">${esc(entry.calendar.name)}</span>${entry.calendar.deleted ? `<span class="secondary">${esc(t("This calendar was deleted too. Restoring brings it back."))}</span>` : ""}</div></div>`);
  if (entry.category_name) facts.push(`<div class="fact">${icon("tag")}<div><span class="primary">${esc(entry.category_name)}</span></div></div>`);
  if (entry.location) facts.push(`<div class="fact">${icon("pin")}<div><span class="primary">${esc(entry.location)}</span></div></div>`);
  if (entry.links.length) facts.push(`<div class="fact">${icon("link")}<div>${entry.links.map((l) => `<span class="primary">${esc(l.label || l.target)}</span>`).join("")}<span class="secondary">${esc(t("These links come back when it is restored."))}</span></div></div>`);
  facts.push(`<div class="fact">${icon("info")}<div><span class="secondary">${esc(t("Created {created} · last changed {changed}", { created: fmtMoment(entry.created_at), changed: fmtMoment(entry.updated_at) }))}</span></div></div>`);
  const banner =
    entry.blocked === "series_in_trash"
      ? `<div class="ae-banner ae-banner--warn">${icon("info")}<div>${esc(t("The series this belongs to is in Trash. Restore the series first."))}</div></div>`
      : entry.blocked === "occurrence_gone"
        ? `<div class="ae-banner ae-banner--warn">${icon("info")}<div>${esc(t("The series was rescheduled after this was deleted, so this occurrence no longer exists in it. You can bring it back as a separate event."))}</div></div>`
        : "";
  const primary =
    entry.blocked === "series_in_trash"
      ? `<button class="ae-btn ae-btn--primary" disabled>${esc(t("Restore"))}</button>`
      : entry.blocked === "occurrence_gone"
        ? `<button class="ae-btn ae-btn--primary" data-act="trash-restore-separate" data-id="${esc(entry.id)}">${esc(t("Restore as separate event"))}</button>`
        : `<button class="ae-btn ae-btn--primary" data-act="trash-restore" data-id="${esc(entry.id)}">${esc(t("Restore"))}</button>`;
  const batch = entry.cause === "calendar" && entry.batch_size > 1 ? `<button class="ae-btn" data-act="trash-restore-batch" data-batch="${esc(entry.batch)}">${esc(plural(entry.batch_size, "Restore {count} from this calendar", "Restore all {count} from this calendar"))}</button>` : "";
  $("#layer").innerHTML = `<div class="ae-scrim" data-act="close"></div>
    <aside class="ae-drawer ae-glass trash-drawer" style="--c:${esc(entry.color)}" role="dialog" aria-modal="true" aria-labelledby="details-title">
      <div class="details">
        <div class="details-head"><span class="swatch" style="--c:${esc(entry.color)}"></span><h2 id="details-title">${esc(entry.title)}</h2><button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="close" aria-label="${esc(t("Close"))}">${icon("x")}</button></div>
        <div class="details-body">${banner}<div class="facts">${facts.join("")}</div>${entry.description ? `<p class="description">${esc(entry.description)}</p>` : ""}</div>
        <div class="details-foot">${primary}${batch}<span class="grow"></span><button class="ae-btn ae-btn--quiet trash-danger" data-act="trash-purge" data-id="${esc(entry.id)}">${esc(t("Delete for good"))}</button></div>
      </div>
    </aside>`;
  $(".ae-drawer [data-act=close]").focus();
  return "open";
}

/* ───────────────────────── Menus and dialogs ───────────────────────── */

function openMenu(anchor, items) {
  closeMenu();
  const menu = document.createElement("div");
  menu.className = "ae-menu ae-glass";
  menu.setAttribute("role", "menu");
  menu.innerHTML = items
    .map((item) =>
      item === "-"
        ? '<div class="ae-menu-sep" role="separator"></div>'
        : `<button class="ae-menu-item ${item.danger ? "ae-menu-item--danger" : ""}" role="menuitem" data-index="${items.indexOf(item)}">${item.icon ? icon(item.icon) : ""}<span>${esc(item.label)}</span></button>`,
    )
    .join("");
  document.body.append(menu);
  const box = anchor.getBoundingClientRect();
  const width = menu.offsetWidth;
  menu.style.left = Math.max(8, Math.min(box.right - width, innerWidth - width - 8)) + "px";
  const top = box.bottom + 6;
  menu.style.top = (top + menu.offsetHeight > innerHeight - 8 ? box.top - menu.offsetHeight - 6 : top) + "px";
  anchor.setAttribute("aria-expanded", "true");
  menu.addEventListener("click", (event) => {
    const button = event.target.closest("[data-index]");
    if (!button) return;
    closeMenu();
    items[Number(button.dataset.index)].run();
  });
  menu.addEventListener("keydown", (event) => {
    const buttons = $$(".ae-menu-item", menu);
    const index = buttons.indexOf(document.activeElement);
    if (event.key === "ArrowDown") buttons[(index + 1) % buttons.length].focus();
    else if (event.key === "ArrowUp") buttons[(index - 1 + buttons.length) % buttons.length].focus();
    else return;
    event.preventDefault();
  });
  menu.anchor = anchor;
  $(".ae-menu-item", menu)?.focus();
}
function closeMenu() {
  const menu = $(".ae-menu");
  if (!menu) return false;
  menu.anchor?.setAttribute("aria-expanded", "false");
  menu.anchor?.focus?.();
  menu.remove();
  return true;
}
document.addEventListener("pointerdown", (event) => {
  if (!event.target.closest(".ae-menu") && !event.target.closest("[aria-haspopup]")) closeMenu();
});

const dialog = () => $("#dialog");
function openDialog(html, { wide = false, onOpen } = {}) {
  const d = dialog();
  d.className = `ae-dialog ae-glass ${wide ? "ae-dialog--wide" : ""}`;
  d.innerHTML = html;
  if (!d.open) d.showModal();
  onOpen?.(d);
  ($("[autofocus]", d) || $("input,select,textarea,button", d))?.focus();
  return d;
}
function closeDialog() {
  if (dialog().open) dialog().close();
}
/** Close a Trash dialog with its exit motion; any other dialog closes at once, as before. */
async function leaveDialog() {
  const d = dialog();
  if (!d.open) return;
  if (!d.classList.contains("trash-dialog") || reducedMotion()) return closeDialog();
  d.classList.add("is-closing");
  await new Promise((resolve) => setTimeout(resolve, MOTION.exit));
  d.classList.remove("is-closing");
  closeDialog();
}
dialog().addEventListener("cancel", (event) => {
  if (!dialog().classList.contains("trash-dialog")) return;
  event.preventDefault();
  leaveDialog();
});
function confirmAction(title, text, label, run) {
  openDialog(`<div class="ae-dialog-head"><h2>${esc(title)}</h2></div><div class="ae-dialog-body"><p style="margin:0;color:var(--text-2)">${esc(text)}</p></div>
    <div class="ae-dialog-foot"><button class="ae-btn" data-act="dialog-cancel">${esc(t("Cancel"))}</button><button class="ae-btn ae-btn--danger" id="confirm">${esc(label)}</button></div>`);
  $("#confirm").onclick = async (event) => {
    event.currentTarget.classList.add("is-busy");
    await run();
    closeDialog();
  };
}
const swatchPicker = (name, current, { inherit } = {}) =>
  `<div class="swatches" role="radiogroup" data-swatches="${name}">${inherit ? `<button type="button" class="inherit" style="--c:${esc(inherit)}" data-color="" aria-pressed="${!current}" aria-label="${esc(t("Calendar color"))}" data-tip="${esc(t("Calendar color"))}"></button>` : ""}${PALETTE.map((c) => `<button type="button" style="--c:${c}" data-color="${c}" aria-pressed="${current?.toLowerCase() === c.toLowerCase()}" aria-label="${esc(c)}"></button>`).join("")}</div>`;
function pickedColor(root, name) {
  return $(`[data-swatches=${name}] [aria-pressed=true]`, root)?.dataset.color ?? "";
}
document.addEventListener("click", (event) => {
  const swatch = event.target.closest("[data-swatches] button");
  if (!swatch) return;
  $$("button", swatch.parentElement).forEach((b) => b.setAttribute("aria-pressed", String(b === swatch)));
});

/* Calendar and category dialogs */

/** Run a save from a form. On a conflict the form stays open, with its contents, and says what
 * is stored now; saving again is then a decision made with that knowledge. */
async function saveGuarded(work, reload) {
  try {
    return await work();
  } catch (error) {
    if (!isConflict(error)) {
      toast(error.message || t("Something went wrong."), "danger");
      return undefined;
    }
    const note = await reload();
    if (note === null) {
      toast(t("This no longer exists."), "danger");
      closeDialog();
      await refresh();
      return undefined;
    }
    showDialogConflict(note);
    renderSidebar();
    return undefined;
  }
}
function showDialogConflict(text) {
  const body = $(".ae-dialog-body", dialog());
  let box = $("#dialog-conflict", body);
  if (!box) {
    box = document.createElement("div");
    box.id = "dialog-conflict";
    box.className = "ae-banner ae-banner--warn dialog-conflict";
    box.setAttribute("role", "alert");
    body.prepend(box);
  }
  box.innerHTML = `${icon("alert")}<div>${esc(text)}</div>`;
}

function calendarDialog(existing) {
  openDialog(`<div class="ae-dialog-head"><h2>${esc(existing ? t("Calendar settings") : t("New calendar"))}</h2></div>
    <div class="ae-dialog-body form">
      <div class="ae-field"><label for="cal-name">${esc(t("Name"))}</label><input class="ae-input" id="cal-name" maxlength="100" value="${esc(existing?.name || "")}" autofocus></div>
      <div class="ae-field"><span class="ae-label">${esc(t("Color"))}</span>${swatchPicker("cal", existing?.color || PALETTE[0])}</div>
    </div>
    <div class="ae-dialog-foot"><button class="ae-btn" data-act="dialog-cancel">${esc(t("Cancel"))}</button><button class="ae-btn ae-btn--primary" id="save">${esc(existing ? t("Save") : t("Create"))}</button></div>`);
  $("#save").onclick = async () => {
    const body = { name: $("#cal-name").value.trim(), color: pickedColor(dialog(), "cal") || PALETTE[0] };
    if (!body.name) return $("#cal-name").setAttribute("aria-invalid", "true");
    const ok = existing
      ? await saveGuarded(
          () => api(`/calendars/${existing.id}`, "PUT", { ...body, expected_revision: existing.revision }),
          async () => {
            await loadState();
            const latest = calendarById(existing.id);
            if (!latest) return null;
            existing = latest;
            return t("This calendar changed elsewhere. It is now named “{name}”. Your changes are still here; save again to replace it.", { name: latest.name });
          },
        )
      : await attempt(() => api("/calendars", "POST", body));
    if (ok) {
      closeDialog();
      await refresh();
    }
  };
}
function categoryDialog(existing) {
  openDialog(`<div class="ae-dialog-head"><h2>${esc(existing ? t("Edit category") : t("New category"))}</h2></div>
    <div class="ae-dialog-body form">
      <div class="ae-field"><label for="cat-name">${esc(t("Name"))}</label><input class="ae-input" id="cat-name" maxlength="60" value="${esc(existing?.name || "")}" autofocus></div>
      <div class="ae-field"><span class="ae-label">${esc(t("Color"))}</span>${swatchPicker("cat", existing?.color || PALETTE[7])}</div>
    </div>
    <div class="ae-dialog-foot">${existing ? `<button class="ae-btn ae-btn--quiet" id="delete-cat" style="margin-right:auto">${esc(t("Delete"))}</button>` : ""}<button class="ae-btn" data-act="dialog-cancel">${esc(t("Cancel"))}</button><button class="ae-btn ae-btn--primary" id="save">${esc(t("Save"))}</button></div>`);
  $("#save").onclick = async () => {
    const body = { name: $("#cat-name").value.trim(), color: pickedColor(dialog(), "cat") || PALETTE[7] };
    if (!body.name) return $("#cat-name").setAttribute("aria-invalid", "true");
    const saved = existing
      ? await saveGuarded(
          () => api(`/categories/${existing.id}`, "PUT", { ...body, expected_revision: existing.revision }),
          async () => {
            await loadState();
            const latest = state.categories.find((c) => c.id === existing.id);
            if (!latest) return null;
            existing = latest;
            return t("This category changed elsewhere. It is now named “{name}”. Your changes are still here; save again to replace it.", { name: latest.name });
          },
        )
      : await attempt(() => api("/categories", "POST", body));
    if (saved) {
      closeDialog();
      await refresh();
    }
  };
  if (existing)
    $("#delete-cat").onclick = async () => {
      await attempt(() => api(`/categories/${existing.id}?expected_revision=${existing.revision}`, "DELETE"));
      state.categoryFilter.delete(existing.id);
      closeDialog();
      await refresh();
    };
}

/* Event editor */

const WEEKDAYS = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"];
function parseRule(rrule) {
  const parts = Object.fromEntries((rrule || "").replace(/^RRULE:/i, "").split(";").filter(Boolean).map((p) => p.split("=")));
  return parts;
}
function zoneOptions(selected) {
  const zones = state.zones.length ? state.zones : [selected];
  return zones.map((z) => `<option value="${esc(z)}" ${z === selected ? "selected" : ""}>${esc(z.replace(/_/g, " "))}</option>`).join("");
}
/** What differs between the stored event and the form, as rows of field, stored and yours. */
function conflictRows(stored, mine, opened) {
  const when = (e) => {
    if (e.all_day) return e.start === addDays(e.end, -1) ? e.start : `${e.start} – ${addDays(e.end, -1)}`;
    return `${String(e.startLocal).replace("T", " ")} – ${String(e.endLocal).replace("T", " ")} · ${e.time_zone}`;
  };
  const storedWhen = { ...stored, startLocal: stored.start_local, endLocal: stored.end_local };
  const mineWhen = { ...mine, startLocal: mine.start, endLocal: mine.end };
  const statusName = (s) => ({ confirmed: t("Confirmed"), tentative: t("Tentative"), cancelled: t("Cancelled") })[s] || s;
  const categoryName = (id) => state.categories.find((c) => c.id === id)?.name || t("None");
  const pairs = [
    [t("Title"), stored.title, mine.title],
    [t("When"), when(storedWhen), when(mineWhen)],
    [t("Repeat"), ruleText(stored.rrule) || t("Does not repeat"), ruleText(mine.rrule) || t("Does not repeat")],
    [t("Calendar"), stored.calendar.name, calendarById(mine.calendar_id)?.name || mine.calendar_id],
    [t("Category"), categoryName(stored.category_id), categoryName(mine.category_id)],
    [t("Location"), stored.location || "—", mine.location || "—"],
    [t("Description"), stored.description || "—", mine.description || "—"],
    [t("Status"), statusName(stored.status), statusName(mine.status)],
  ];
  const rows = pairs.filter(([, a, b]) => a !== b);
  if (opened && stored.exdates.length !== opened.exdates.length)
    rows.push([t("Deleted or skipped occurrences"), String(stored.exdates.length), t("{count} when you opened it", { count: opened.exdates.length })]);
  return rows;
}
async function eventEditor(existing, defaults = {}, baseRevision) {
  if (!state.zones.length) state.zones = (await api("/timezones").catch(() => ({ zones: [] }))).zones;
  const calendars = nativeCalendars();
  const now = zoneParts(new Date());
  const startDay = existing ? (existing.all_day ? existing.start : existing.start_local.slice(0, 10)) : defaults.day || (state.cursor === today() ? today() : state.cursor);
  const startMin = existing && !existing.all_day ? Number(existing.start_local.slice(11, 13)) * 60 + Number(existing.start_local.slice(14, 16)) : defaults.minutes ?? Math.min(23 * 60, (Math.floor(now.minutes / 60) + 1) * 60);
  const endDay = existing ? (existing.all_day ? addDays(existing.end, -1) : existing.end_local.slice(0, 10)) : startDay;
  const endMin = existing && !existing.all_day ? Number(existing.end_local.slice(11, 13)) * 60 + Number(existing.end_local.slice(14, 16)) : Math.min(startMin + 60, 23 * 60 + 59);
  const hm = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
  const allDay = existing ? existing.all_day : !!defaults.all_day;
  const zone = existing?.time_zone || tz();
  const rule = parseRule(existing?.rrule);
  const preset = !existing?.rrule ? "none" : rule.FREQ === "WEEKLY" && rule.BYDAY === "MO,TU,WE,TH,FR" && !rule.INTERVAL ? "weekdays" : rule.INTERVAL || rule.COUNT || rule.UNTIL || (rule.FREQ === "WEEKLY" && rule.BYDAY?.includes(",")) ? "custom" : rule.FREQ.toLowerCase();
  const calendarId = existing?.calendar_id || defaults.calendar_id || calendars[0]?.id;
  const repeatLabel = (key) =>
    ({
      none: t("Does not repeat"),
      daily: t("Every day"),
      weekly: t("Every week on {day}", { day: fmtDay(startDay, { weekday: "long" }) }),
      weekdays: t("Every weekday (Monday to Friday)"),
      monthly: t("Every month on day {day}", { day: Number(startDay.slice(8)) }),
      yearly: t("Every year on {date}", { date: fmtDay(startDay, { day: "numeric", month: "long" }) }),
      custom: t("Custom…"),
    })[key];
  const byday = new Set((rule.BYDAY || WEEKDAYS[weekday(startDay)]).split(","));
  openDialog(
    `<div class="ae-dialog-head"><h2>${esc(existing ? t("Edit event") : t("New event"))}</h2><button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="dialog-cancel" aria-label="${esc(t("Close"))}">${icon("x")}</button></div>
    <div class="ae-dialog-body form" id="editor">
      <input class="ae-input title-input" id="ev-title" maxlength="300" placeholder="${esc(t("Add a title"))}" value="${esc(existing?.title || "")}" autofocus aria-label="${esc(t("Title"))}">
      <div class="inline"><input type="checkbox" role="switch" class="ae-switch" id="ev-allday" ${allDay ? "checked" : ""}><label for="ev-allday">${esc(t("All day"))}</label></div>
      <div class="form-row"><div class="ae-field"><label for="ev-start">${esc(t("Starts"))}</label><div class="inline"><input class="ae-input" type="date" id="ev-start" value="${startDay}"><input class="ae-input timed" type="time" id="ev-start-time" value="${hm(startMin)}" ${allDay ? "hidden" : ""} aria-label="${esc(t("Start time"))}"></div></div>
      <div class="ae-field"><label for="ev-end">${esc(t("Ends"))}</label><div class="inline"><input class="ae-input" type="date" id="ev-end" value="${endDay}"><input class="ae-input timed" type="time" id="ev-end-time" value="${hm(endMin)}" ${allDay ? "hidden" : ""} aria-label="${esc(t("End time"))}"></div></div></div>
      <div class="ae-field timed" ${allDay ? "hidden" : ""}><label for="ev-zone">${esc(t("Time zone"))}</label><select class="ae-select" id="ev-zone">${zoneOptions(zone)}</select></div>
      <div class="ae-field"><label for="ev-repeat">${esc(t("Repeat"))}</label><select class="ae-select" id="ev-repeat">${["none", "daily", "weekly", "weekdays", "monthly", "yearly", "custom"].map((k) => `<option value="${k}" ${k === preset ? "selected" : ""}>${esc(repeatLabel(k))}</option>`).join("")}</select></div>
      <div class="form" id="custom-rule" ${preset === "custom" ? "" : "hidden"}>
        <div class="form-row three"><div class="ae-field"><label for="ev-interval">${esc(t("Every"))}</label><input class="ae-input" type="number" min="1" max="99" id="ev-interval" value="${esc(rule.INTERVAL || 1)}"></div>
          <div class="ae-field"><label for="ev-unit">${esc(t("Unit"))}</label><select class="ae-select" id="ev-unit">${[["DAILY", t("days")], ["WEEKLY", t("weeks")], ["MONTHLY", t("months")], ["YEARLY", t("years")]].map(([v, l]) => `<option value="${v}" ${(rule.FREQ || "WEEKLY") === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>
          <div class="ae-field"><label for="ev-ends">${esc(t("Ends"))}</label><select class="ae-select" id="ev-ends"><option value="never">${esc(t("Never"))}</option><option value="until" ${rule.UNTIL ? "selected" : ""}>${esc(t("On a date"))}</option><option value="count" ${rule.COUNT ? "selected" : ""}>${esc(t("After a number of times"))}</option></select></div></div>
        <div class="weekday-toggles" id="ev-days" ${(rule.FREQ || "WEEKLY") === "WEEKLY" ? "" : "hidden"}>${weekdayNames("narrow").map((n, i) => { const code = WEEKDAYS[(i + state.settings.week_start) % 7]; return `<button type="button" data-day="${code}" aria-pressed="${byday.has(code)}">${esc(n)}</button>`; }).join("")}</div>
        <div class="form-row"><input class="ae-input" type="date" id="ev-until" value="${rule.UNTIL ? `${rule.UNTIL.slice(0, 4)}-${rule.UNTIL.slice(4, 6)}-${rule.UNTIL.slice(6, 8)}` : addDays(startDay, 90)}" ${rule.UNTIL ? "" : "hidden"} aria-label="${esc(t("Last date"))}"><input class="ae-input" type="number" min="1" max="1000" id="ev-count" value="${esc(rule.COUNT || 10)}" ${rule.COUNT ? "" : "hidden"} aria-label="${esc(t("Number of times"))}"></div>
      </div>
      <div class="form-row"><div class="ae-field"><label for="ev-calendar">${esc(t("Calendar"))}</label><select class="ae-select" id="ev-calendar">${calendars.map((c) => `<option value="${esc(c.id)}" ${c.id === calendarId ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></div>
      <div class="ae-field"><label for="ev-category">${esc(t("Category"))}</label><select class="ae-select" id="ev-category"><option value="">${esc(t("None"))}</option>${state.categories.map((c) => `<option value="${esc(c.id)}" ${existing?.category_id === c.id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></div></div>
      <div class="ae-field"><label for="ev-location">${esc(t("Location"))}</label><input class="ae-input" id="ev-location" maxlength="500" value="${esc(existing?.location || "")}"></div>
      <div class="ae-field"><label for="ev-description">${esc(t("Description"))}</label><textarea class="ae-textarea" id="ev-description" maxlength="20000">${esc(existing?.description || "")}</textarea></div>
      <details class="disclosure"><summary>${esc(t("Color and status"))}</summary><div class="form">
        <div class="ae-field"><span class="ae-label">${esc(t("Color"))}</span>${swatchPicker("ev", existing?.color || "", { inherit: calendarById(calendarId)?.color || PALETTE[0] })}</div>
        <div class="ae-field"><label for="ev-status">${esc(t("Status"))}</label><select class="ae-select" id="ev-status">${[["confirmed", t("Confirmed")], ["tentative", t("Tentative")], ["cancelled", t("Cancelled")]].map(([v, l]) => `<option value="${v}" ${(existing?.status || "confirmed") === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>
      </div></details>
      <p class="ae-error-text" id="ev-error" hidden></p>
    </div>
    <div class="ae-dialog-foot"><button class="ae-btn" data-act="dialog-cancel">${esc(t("Cancel"))}</button><button class="ae-btn ae-btn--primary" id="save">${esc(existing ? t("Save") : t("Create event"))}</button></div>`,
    { wide: true },
  );
  const root = dialog();
  const sync = () => {
    const isAllDay = $("#ev-allday", root).checked;
    $$(".timed", root).forEach((el) => (el.hidden = isAllDay));
    const custom = $("#ev-repeat", root).value === "custom";
    $("#custom-rule", root).hidden = !custom;
    $("#ev-days", root).hidden = $("#ev-unit", root).value !== "WEEKLY";
    $("#ev-until", root).hidden = $("#ev-ends", root).value !== "until";
    $("#ev-count", root).hidden = $("#ev-ends", root).value !== "count";
  };
  root.addEventListener("change", (event) => {
    if (event.target.id === "ev-start" && $("#ev-end", root).value < event.target.value) $("#ev-end", root).value = event.target.value;
    sync();
  });
  $("#ev-days", root).addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (button) button.setAttribute("aria-pressed", String(button.getAttribute("aria-pressed") !== "true"));
  });
  const fail = (message) => {
    const box = $("#ev-error", root);
    box.textContent = message;
    box.hidden = false;
  };
  const collect = () => {
    const title = $("#ev-title", root).value.trim();
    if (!title) return { error: t("Add a title."), invalid: "#ev-title" };
    const isAllDay = $("#ev-allday", root).checked;
    const start = $("#ev-start", root).value;
    const end = $("#ev-end", root).value;
    if (!start || !end) return { error: t("Choose a start and an end.") };
    const startDayValue = start;
    const repeat = $("#ev-repeat", root).value;
    let rrule = null;
    const dayCode = WEEKDAYS[weekday(startDayValue)];
    if (repeat === "daily") rrule = "FREQ=DAILY";
    if (repeat === "weekly") rrule = `FREQ=WEEKLY;BYDAY=${dayCode}`;
    if (repeat === "weekdays") rrule = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR";
    if (repeat === "monthly") rrule = `FREQ=MONTHLY;BYMONTHDAY=${Number(startDayValue.slice(8))}`;
    if (repeat === "yearly") rrule = "FREQ=YEARLY";
    if (repeat === "custom") {
      const unit = $("#ev-unit", root).value;
      const parts = [`FREQ=${unit}`];
      const interval = Number($("#ev-interval", root).value || 1);
      if (interval > 1) parts.push(`INTERVAL=${interval}`);
      if (unit === "WEEKLY") {
        const days = $$("#ev-days [aria-pressed=true]", root).map((b) => b.dataset.day);
        parts.push(`BYDAY=${(days.length ? days : [dayCode]).join(",")}`);
      }
      const ends = $("#ev-ends", root).value;
      if (ends === "until") parts.push(`UNTIL=${$("#ev-until", root).value.replaceAll("-", "")}`);
      if (ends === "count") parts.push(`COUNT=${Number($("#ev-count", root).value || 1)}`);
      rrule = parts.join(";");
    }
    const body = {
      calendar_id: $("#ev-calendar", root).value,
      title,
      description: $("#ev-description", root).value,
      location: $("#ev-location", root).value.trim(),
      all_day: isAllDay,
      start: isAllDay ? start : `${start}T${$("#ev-start-time", root).value || "09:00"}`,
      end: isAllDay ? addDays(end, 1) : `${end}T${$("#ev-end-time", root).value || "10:00"}`,
      time_zone: isAllDay ? null : $("#ev-zone", root).value,
      rrule,
      status: $("#ev-status", root).value,
      category_id: $("#ev-category", root).value || null,
      color: pickedColor(root, "ev"),
    };
    if (isAllDay ? body.end <= body.start : body.end < body.start) return { error: t("The end must be after the start.") };
    return { body };
  };
  /* A conflict never changes the form and never saves anything by itself. The owner reads what
     is stored now, then keeps their version against that exact revision or takes the stored one. */
  const reviewConflict = async (box) => {
    const slot = $("#conflict-review", box);
    let stored;
    try {
      stored = await api(`/events/${existing.id}`);
    } catch (error) {
      slot.innerHTML = `<p class="conflict-note">${esc(error.message)}</p>`;
      return;
    }
    const { body } = collect();
    const rows = body ? conflictRows(stored, body, existing) : [];
    slot.innerHTML = `${
      rows.length
        ? `<table class="conflict-table"><thead><tr><th></th><th>${esc(t("Stored now"))}</th><th>${esc(t("Your edit"))}</th></tr></thead><tbody>${rows.map(([field, a, b]) => `<tr><th scope="row">${esc(field)}</th><td>${esc(a)}</td><td>${esc(b)}</td></tr>`).join("")}</tbody></table>`
        : `<p class="conflict-note">${esc(t("The stored version now has the same details as your form."))}</p>`
    }<div class="conflict-actions"><button type="button" class="ae-btn ae-btn--sm ae-btn--primary" id="conflict-keep">${esc(t("Save my version"))}</button><button type="button" class="ae-btn ae-btn--sm" id="conflict-use">${esc(t("Discard my edits and use the stored version"))}</button></div>`;
    $("#conflict-keep", slot).onclick = (event) => {
      editorSession.revision = stored.revision;
      scheduleCheckpoint();
      save(event.currentTarget);
    };
    $("#conflict-use", slot).onclick = () => eventEditor(stored);
    animate(slot, [{ opacity: 0, transform: "translateY(4px)" }, { opacity: 1, transform: "none" }], { duration: MOTION.page, easing: MOTION.ease });
  };
  const showConflict = () => {
    $("#ev-error", root).hidden = true;
    let box = $("#editor-conflict", root);
    if (!box) {
      box = document.createElement("div");
      box.id = "editor-conflict";
      box.className = "ae-banner ae-banner--warn editor-conflict";
      box.setAttribute("role", "alert");
      $("#editor", root).prepend(box);
      animate(box, [{ opacity: 0, transform: "translateY(-4px)" }, { opacity: 1, transform: "none" }], { duration: MOTION.page, easing: MOTION.ease });
    }
    box.innerHTML = `${icon("alert")}<div class="conflict-body"><strong>${esc(t("This event changed elsewhere"))}</strong><p>${esc(t("Nothing was saved, and your edits are still here. Review the stored version before you decide."))}</p><div class="conflict-actions"><button type="button" class="ae-btn ae-btn--sm" id="conflict-review-open">${esc(t("Review stored version"))}</button></div><div id="conflict-review"></div></div>`;
    $("#conflict-review-open", box).onclick = (event) => {
      event.currentTarget.closest(".conflict-actions").remove();
      reviewConflict(box);
    };
    box.scrollIntoView({ block: "nearest" });
    $("#conflict-review-open", box).focus();
  };
  let saving = false;
  const save = async (button) => {
    if (saving) return;
    const { body, error: problem, invalid } = collect();
    if (problem) {
      if (invalid) $(invalid, root).setAttribute("aria-invalid", "true");
      return fail(problem);
    }
    saving = true;
    button.classList.add("is-busy");
    try {
      const saved = existing ? await api(`/events/${existing.id}`, "PUT", { ...body, expected_revision: editorSession.revision }) : await api("/events", "POST", body);
      closeDialog();
      closeLayer({ mode: "replace" });
      toast(existing ? t("Event saved") : t("Event created"));
      if (!existing) state.cursor = saved.all_day ? saved.start : zoneParts(new Date(saved.start)).day;
      await refresh();
    } catch (error) {
      button.classList.remove("is-busy");
      if (isConflict(error)) showConflict();
      else fail(error.message);
    } finally {
      saving = false;
    }
  };
  $("#save", root).onclick = (event) => save(event.currentTarget);
  sync();
  eventEditorOpened(existing, defaults, baseRevision ?? existing?.revision);
}

/* Import */

function importDialog() {
  const imports = state.calendars.filter((c) => c.kind === "import");
  let content = null;
  let filename = "calendar.ics";
  openDialog(
    `<div class="ae-dialog-head"><h2>${esc(t("Import an iCalendar file"))}</h2><button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="dialog-cancel" aria-label="${esc(t("Close"))}">${icon("x")}</button></div>
    <div class="ae-dialog-body form" id="import">
      <label class="dropzone" id="drop">${icon("upload")}<strong>${esc(t("Choose an .ics file"))}</strong><span class="ae-meta">${esc(t("or drop it here · up to 2 MiB"))}</span><input type="file" id="file" accept=".ics,.ical,.ifb,.icalendar,text/calendar" hidden></label>
      <div id="preview"></div>
      <p class="ae-hint">${esc(t("Imported events are read-only copies. Importing the same file again updates changed events and never creates duplicates. Your own calendars are never changed."))}</p>
    </div>
    <div class="ae-dialog-foot"><button class="ae-btn" data-act="dialog-cancel">${esc(t("Cancel"))}</button><button class="ae-btn ae-btn--primary" id="do-import" disabled>${esc(t("Import"))}</button></div>`,
    { wide: true },
  );
  const root = dialog();
  const target = () => $("#imp-target", root)?.value || "";
  const preview = async () => {
    const box = $("#preview", root);
    box.innerHTML = `<div class="inline"><span class="ae-spinner"></span><span class="ae-meta">${esc(t("Reading {file}…", { file: filename }))}</span></div>`;
    try {
      const p = await api("/import/preview", "POST", { content, filename, calendar_id: target() || null });
      const dupes = p.already_in_target + p.duplicates_in_file;
      box.innerHTML = `<div class="form">
        <dl class="stats"><div><dt>${esc(t("Events"))}</dt><dd>${p.total}</dd></div><div><dt>${esc(t("Repeating"))}</dt><dd>${p.recurring}</dd></div><div><dt>${esc(t("All-day"))}</dt><dd>${p.all_day}</dd></div><div><dt>${esc(t("Already present"))}</dt><dd>${dupes}</dd></div></dl>
        <div class="form-row"><div class="ae-field"><label for="imp-target">${esc(t("Import into"))}</label><select class="ae-select" id="imp-target"><option value="">${esc(t("A new calendar"))}</option>${imports.map((c) => `<option value="${esc(c.id)}" ${target() === c.id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></div>
        <div class="ae-field" id="imp-new" ${target() ? "hidden" : ""}><label for="imp-name">${esc(t("Calendar name"))}</label><input class="ae-input" id="imp-name" maxlength="100" value="${esc(p.name)}"></div></div>
        <div class="ae-field" id="imp-color" ${target() ? "hidden" : ""}><span class="ae-label">${esc(t("Color"))}</span>${swatchPicker("imp", PALETTE[7])}</div>
        ${p.in_other_calendars.length ? `<div class="ae-banner ae-banner--warn">${icon("alert")}<div>${esc(t("Some events already exist in other calendars: {list}. Importing into a new calendar would show them twice.", { list: p.in_other_calendars.map((c) => `${c.name} (${c.count})`).join(", ") }))}</div></div>` : ""}
        ${p.error_count ? `<div class="ae-banner ae-banner--danger">${icon("alert")}<div><strong>${esc(plural(p.error_count, "{count} event cannot be imported", "{count} events cannot be imported"))}</strong><ul class="issues">${p.errors.slice(0, 5).map((e) => `<li>${esc(e.title)}: ${esc(e.error)}</li>`).join("")}</ul></div></div>` : ""}
        ${p.warnings.length ? `<div class="ae-banner">${icon("info")}<div><ul class="issues">${p.warnings.slice(0, 5).map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div></div>` : ""}
        ${p.ignored && Object.keys(p.ignored).length ? `<p class="ae-hint">${esc(t("Tasks and journal entries in the file are not imported."))}</p>` : ""}
        ${p.sample.length ? `<div><span class="ae-eyebrow">${esc(t("First events"))}</span><ul class="sample">${p.sample.map((e) => `<li><span class="when">${esc(e.all_day ? fmtDay(e.start, { day: "numeric", month: "short", year: "numeric" }) : `${fmtDay(zoneParts(new Date(e.start)).day, { day: "numeric", month: "short", year: "numeric" })} ${fmtTime(e.start)}`)}</span><span>${esc(e.title)}${e.rrule ? ` <span class="ae-pill">${esc(t("repeats"))}</span>` : ""}</span></li>`).join("")}</ul></div>` : ""}
      </div>`;
      $("#do-import", root).disabled = !p.total;
      $("#imp-target", root).onchange = () => preview();
    } catch (error) {
      box.innerHTML = `<div class="ae-banner ae-banner--danger">${icon("alert")}<div><strong>${esc(t("This file cannot be imported."))}</strong><br>${esc(error.message)}</div></div>`;
      $("#do-import", root).disabled = true;
    }
  };
  const read = (file) => {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) return toast(t("The file is larger than 2 MiB."), "danger");
    filename = file.name;
    const reader = new FileReader();
    reader.onload = () => {
      content = String(reader.result);
      $("#drop strong", root).textContent = file.name;
      preview();
    };
    reader.readAsText(file);
  };
  $("#file", root).onchange = (e) => read(e.target.files[0]);
  const drop = $("#drop", root);
  drop.addEventListener("dragover", (e) => {
    e.preventDefault();
    drop.classList.add("over");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("over");
    read(e.dataTransfer.files[0]);
  });
  $("#do-import", root).onclick = async (event) => {
    event.currentTarget.classList.add("is-busy");
    const id = target();
    try {
      const result = await api("/import", "POST", {
        content,
        filename,
        calendar_id: id || null,
        name: id ? null : $("#imp-name", root)?.value.trim() || null,
        color: id ? null : pickedColor(root, "imp") || null,
      });
      closeDialog();
      toast(t("Imported: {created} new, {updated} updated, {unchanged} unchanged", result));
      await refresh();
    } catch (error) {
      $("#do-import", root).classList.remove("is-busy");
      toast(error.message, "danger");
    }
  };
}

/* Subscriptions */

const REFRESH = [15, 60, 180, 360, 720, 1440];
function refreshLabel(minutes) {
  return minutes < 60 ? t("Every {count} minutes", { count: minutes }) : plural(minutes / 60, "Every hour", "Every {count} hours");
}
function subscribeDialog(existing) {
  openDialog(
    `<div class="ae-dialog-head"><h2>${esc(existing ? t("Change calendar address") : t("Subscribe to a calendar"))}</h2></div>
    <div class="ae-dialog-body form">
      ${existing ? "" : `<div class="ae-field"><label for="sub-name">${esc(t("Name"))}</label><input class="ae-input" id="sub-name" maxlength="100" placeholder="${esc(t("For example: Formula 1"))}" autofocus></div>`}
      <div class="ae-field"><label for="sub-url">${esc(t("Calendar address"))}</label><input class="ae-input" id="sub-url" type="url" inputmode="url" maxlength="2048" placeholder="https://… or webcal://…" ${existing ? "autofocus" : ""}><span class="ae-hint">${esc(t("Public iCalendar (.ics) feeds only. Addresses on your local network are refused."))}</span></div>
      ${existing ? "" : `<div class="form-row"><div class="ae-field"><label for="sub-refresh">${esc(t("Refresh"))}</label><select class="ae-select" id="sub-refresh">${REFRESH.map((m) => `<option value="${m}" ${m === 360 ? "selected" : ""}>${esc(refreshLabel(m))}</option>`).join("")}</select></div></div>
      <div class="ae-field"><span class="ae-label">${esc(t("Color"))}</span>${swatchPicker("sub", PALETTE[5])}</div>`}
      <div class="ae-banner">${icon("info")}<div>${esc(t("Subscriptions are read-only and follow the feed: new events appear, changed ones update and removed ones disappear. Chronos contacts only this address; the address is never shown in logs."))}</div></div>
      <p class="ae-error-text" id="sub-error" hidden></p>
    </div>
    <div class="ae-dialog-foot"><button class="ae-btn" data-act="dialog-cancel">${esc(t("Cancel"))}</button><button class="ae-btn ae-btn--primary" id="save">${esc(existing ? t("Save") : t("Subscribe"))}</button></div>`,
  );
  const root = dialog();
  $("#save", root).onclick = async (event) => {
    const url = $("#sub-url", root).value.trim();
    const name = existing ? null : $("#sub-name", root).value.trim();
    const error = $("#sub-error", root);
    if (!existing && !name) return $("#sub-name", root).setAttribute("aria-invalid", "true");
    if (!url) return $("#sub-url", root).setAttribute("aria-invalid", "true");
    event.currentTarget.classList.add("is-busy");
    try {
      if (existing) await api(`/subscriptions/${existing.id}`, "PUT", { url, expected_revision: existing.revision });
      else await api("/subscriptions", "POST", { name, url, color: pickedColor(root, "sub") || PALETTE[5], refresh_minutes: Number($("#sub-refresh", root).value) });
      closeDialog();
      toast(existing ? t("Address changed. Synchronizing…") : t("Subscribed. The first synchronization is running."));
      await refresh();
    } catch (failure) {
      $("#save", root).classList.remove("is-busy");
      if (existing && isConflict(failure)) {
        await loadState();
        existing = calendarById(existing.id) || existing;
      }
      error.textContent = failure.message;
      error.hidden = false;
    }
  };
}
function subscriptionDetails(c) {
  const sub = c.subscription;
  openDialog(
    `<div class="ae-dialog-head"><h2>${esc(c.name)}</h2></div>
    <div class="ae-dialog-body">
      <div class="setting"><div><strong>${esc(t("Address"))}</strong><span class="ae-mono">${esc(sub.url_display)}</span></div><button class="ae-btn ae-btn--sm" id="change-url">${esc(t("Change"))}</button></div>
      <div class="setting"><div><strong>${esc(t("Last synchronized"))}</strong><span>${esc(sub.last_success_at ? relative(sub.last_success_at) : t("not yet"))} · ${esc(plural(c.event_count, "{count} event", "{count} events"))}</span></div><button class="ae-btn ae-btn--sm" id="sync-now" ${sub.running ? "disabled" : ""}>${icon("refresh")}<span>${esc(t("Sync now"))}</span></button></div>
      ${sub.last_error ? `<div class="ae-banner ae-banner--danger" style="margin:var(--space-3) 0">${icon("alert")}<div><strong>${esc(t("The last attempt failed"))}</strong> · ${esc(relative(sub.last_attempt_at))}<br>${esc(sub.last_error)}</div></div>` : ""}
      ${sub.last_warning ? `<div class="ae-banner ae-banner--warn" style="margin:var(--space-3) 0">${icon("info")}<div>${esc(sub.last_warning)}</div></div>` : ""}
      <div class="setting"><div><strong>${esc(t("Refresh"))}</strong></div><select class="ae-select" id="refresh" style="width:auto">${REFRESH.map((m) => `<option value="${m}" ${m === sub.refresh_minutes ? "selected" : ""}>${esc(refreshLabel(m))}</option>`).join("")}</select></div>
      <div class="setting"><div><strong>${esc(t("Automatic updates"))}</strong><span>${esc(t("Paused subscriptions keep their events but stop contacting the feed."))}</span></div><input type="checkbox" role="switch" class="ae-switch" id="enabled" ${sub.enabled ? "checked" : ""} aria-label="${esc(t("Automatic updates"))}"></div>
    </div>
    <div class="ae-dialog-foot"><button class="ae-btn ae-btn--primary" data-act="dialog-cancel">${esc(t("Done"))}</button></div>`,
  );
  const root = dialog();
  $("#change-url", root).onclick = () => subscribeDialog(c);
  $("#sync-now", root).onclick = async () => {
    await attempt(() => api(`/subscriptions/${c.id}/sync`, "POST"), t("Synchronizing…"));
    closeDialog();
    await refresh();
  };
  $("#refresh", root).onchange = (e) => attempt(() => api(`/subscriptions/${c.id}`, "PUT", { refresh_minutes: Number(e.target.value) }));
  $("#enabled", root).onchange = async (e) => {
    await attempt(() => api(`/subscriptions/${c.id}`, "PUT", { enabled: e.target.checked }));
    await refresh();
  };
}

/* Settings */

async function settingsDialog() {
  if (!state.zones.length) state.zones = (await api("/timezones").catch(() => ({ zones: [] }))).zones;
  const source = (provider) => state.sources.find((s) => s.provider === provider);
  const lyra = source("lyra");
  const mnemosyne = source("mnemosyne");
  const meridian = source("meridian") || { enabled: 0 };
  const status = (s) =>
    !s.enabled ? t("Off") : s.availability && s.availability !== "available" ? sourceProblem(s) : s.last_success_at ? `${plural(s.item_count, "{count} date", "{count} dates")} · ${t("updated {when}", { when: relative(s.last_success_at) })}` : t("Connecting…");
  openDialog(
    `<div class="ae-dialog-head"><h2>${esc(t("Settings"))}</h2><button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="dialog-cancel" aria-label="${esc(t("Close"))}">${icon("x")}</button></div>
    <div class="ae-dialog-body">
      <section class="settings-group"><span class="ae-eyebrow">${esc(t("Time"))}</span>
        <div class="setting"><div><strong>${esc(t("Time zone"))}</strong><span>${esc(t("Calendar times are shown in this zone."))}</span></div><select class="ae-select" id="set-zone" style="width:220px">${zoneOptions(tz())}${tz() === "UTC" ? '<option value="UTC" selected>UTC</option>' : ""}</select></div>
        <div class="setting"><div><strong>${esc(t("Week starts on"))}</strong></div><select class="ae-select" id="set-week" style="width:auto">${[1, 0, 6].map((d) => `<option value="${d}" ${state.settings.week_start === d ? "selected" : ""}>${esc(fmtDay(addDays("2023-01-01", d), { weekday: "long" }))}</option>`).join("")}</select></div>
        <div class="setting"><div><strong>${esc(t("Time format"))}</strong></div><select class="ae-select" id="set-format" style="width:auto">${[["auto", t("From language")], ["24", "13:00"], ["12", "1:00 PM"]].map(([v, l]) => `<option value="${v}" ${state.settings.time_format === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>
      </section>
      <section class="settings-group"><span class="ae-eyebrow">${esc(t("Dates shared by other modules"))}</span>
        <div class="setting"><div><strong>${esc(t("Lyra release dates"))}</strong><span>${esc(t("Episodes and releases from your media library. Choose which ones in Lyra."))} · ${esc(status(lyra))}</span></div><input type="checkbox" role="switch" class="ae-switch" data-source="lyra" ${lyra.enabled ? "checked" : ""} aria-label="${esc(t("Lyra release dates"))}"></div>
        <div class="setting"><div><strong>${esc(t("Mnemosyne task deadlines"))}</strong><span>${esc(t("Off by default. Shows deadlines of your Tasks as read-only entries; they stay Tasks in Mnemosyne and never become events."))} · ${esc(status(mnemosyne))}</span></div><input type="checkbox" role="switch" class="ae-switch" data-source="mnemosyne" ${mnemosyne.enabled ? "checked" : ""} aria-label="${esc(t("Mnemosyne task deadlines"))}"></div>
        <div class="setting"><div><strong>${esc(t("Meridian birthdays and anniversaries"))}</strong><span>${esc(t("Off by default. Shows the birthdays and anniversaries recorded in Meridian as read-only yearly dates; Meridian stays their owner."))} · ${esc(status(meridian))}</span></div><input type="checkbox" role="switch" class="ae-switch" data-source="meridian" ${meridian.enabled ? "checked" : ""} aria-label="${esc(t("Meridian birthdays and anniversaries"))}"></div>
        <div class="setting" ${mnemosyne.enabled ? "" : "hidden"} id="completed-row"><div><strong>${esc(t("Show completed tasks"))}</strong></div><input type="checkbox" role="switch" class="ae-switch" id="show-completed" ${mnemosyne.show_completed ? "checked" : ""} aria-label="${esc(t("Show completed tasks"))}"></div>
        <div class="setting"><div><span>${esc(t("Shared dates refresh every 15 minutes and soon after a change is announced."))}</span></div><button class="ae-btn ae-btn--sm" id="refresh-sources">${icon("refresh")}<span>${esc(t("Refresh now"))}</span></button></div>
      </section>
      <section class="settings-group"><span class="ae-eyebrow">${esc(t("About"))}</span>
        <p class="ae-meta" style="margin:var(--space-2) 0 0">${esc(t("Chronos {version}. Imported and subscribed calendars are read-only; there is no two-way synchronization or CalDAV yet.", { version: state.version || "" }))}</p>
      </section>
    </div>
    <div class="ae-dialog-foot"><button class="ae-btn ae-btn--primary" data-act="dialog-cancel">${esc(t("Done"))}</button></div>`,
    { wide: true },
  );
  const root = dialog();
  const save = async (body) => {
    await attempt(async () => {
      state.settings = await api("/settings", "PUT", body);
      partsFormatter.clear();
    });
    await refresh();
  };
  $("#set-zone", root).onchange = (e) => save({ time_zone: e.target.value });
  $("#set-week", root).onchange = (e) => save({ week_start: Number(e.target.value) });
  $("#set-format", root).onchange = (e) => save({ time_format: e.target.value });
  $$("[data-source]", root).forEach((input) => {
    input.onchange = async () => {
      await attempt(() => api(`/sources/${input.dataset.source}`, "PUT", { enabled: input.checked }));
      if (input.dataset.source === "mnemosyne") $("#completed-row", root).hidden = !input.checked;
      await refresh();
    };
  });
  $("#show-completed", root).onchange = async (e) => {
    await attempt(() => api("/sources/mnemosyne", "PUT", { show_completed: e.target.checked }));
    await refresh();
  };
  $("#refresh-sources", root).onclick = async () => {
    for (const s of state.sources.filter((s) => s.enabled)) await attempt(() => api(`/sources/${s.provider}/refresh`, "POST"));
    toast(t("Refreshing shared dates…"));
    schedulePoll();
  };
}

/* ───────────────────────── Actions ───────────────────────── */

async function refresh() {
  await attempt(loadState);
  renderSidebar();
  await loadOccurrences();
  schedulePoll();
}
/** Inside a Nexus with the navigation contract every move is a browser history entry and is
 * shown when Nexus confirms it (frontend/navigation.js); otherwise it is shown directly. */
function go(view, cursor = state.cursor) {
  state.miniCursor = null;
  // Via Nexus the search is cleared once this entry's view state has been recorded with it.
  if (chronosNavigation.enabled && ChronosRoutes.serialize({ view, date: cursor }) !== shownRoute) {
    clearSearchOnApply = true;
    return commitRoute({ view, date: cursor });
  }
  state.results = null;
  state.notice = null;
  state.screen = "calendar";
  if ($("#search")) $("#search").value = state.query = "";
  state.view = view;
  state.cursor = cursor;
  loadOccurrences();
}
function step(direction) {
  if (state.screen === "trash") return;
  // A step still on its way to Nexus counts, so repeated presses do not collapse into one.
  const c = chronosNavigation.enabled ? queuedRoute?.date || state.cursor : state.cursor;
  let cursor = c;
  if (state.view === "month") cursor = addMonths(c, direction);
  else if (state.view === "week") cursor = addDays(c, 7 * direction);
  else if (state.view === "day") cursor = addDays(c, direction);
  else cursor = addDays(c, state.agendaDays * direction);
  state.miniCursor = null;
  if (chronosNavigation.enabled) commitRoute({ view: state.view, date: cursor });
  else {
    state.cursor = cursor;
    loadOccurrences();
  }
  animate($("#view"), [{ opacity: 0.4, transform: `translateX(${direction * 10}px)` }, { opacity: 1, transform: "none" }], { duration: 200 });
}
function calendarMenu(anchor, c) {
  const items = [];
  if (c.kind === "native") items.push({ label: t("Rename or recolor"), icon: "edit", run: () => calendarDialog(c) });
  if (c.kind === "subscription") {
    items.push({ label: t("Subscription details"), icon: "feed", run: () => subscriptionDetails(c) });
    items.push({ label: t("Sync now"), icon: "refresh", run: async () => { await attempt(() => api(`/subscriptions/${c.id}/sync`, "POST"), t("Synchronizing…")); await refresh(); } });
  }
  if (c.kind !== "native") items.push({ label: t("Rename or recolor"), icon: "edit", run: () => calendarDialog(c) });
  items.push({ label: c.visible ? t("Hide") : t("Show"), icon: "layers", run: async () => { await attempt(() => api(`/calendars/${c.id}`, "PUT", { visible: !c.visible })); await refresh(); } });
  items.push("-");
  items.push({
    label: c.kind === "subscription" ? t("Unsubscribe") : t("Delete calendar"),
    icon: "trash",
    danger: true,
    run: () =>
      c.kind === "native"
        ? trashConfirm({
            title: t("Delete “{name}”?", { name: c.name }),
            text: c.event_count ? plural(c.event_count, "Its {count} event moves to Trash, and the calendar goes with it. You can restore them from Trash.", "Its {count} events move to Trash, and the calendar goes with them. You can restore them from Trash.") : t("This calendar has no events and will be removed."),
            label: t("Move to Trash"),
            run: async () => {
              let result;
              try {
                result = await api(`/calendars/${c.id}?confirmed=true&expected_revision=${c.revision}`, "DELETE");
              } catch (error) {
                if (isConflict(error)) await refresh();
                throw error;
              }
              await leaveDialog();
              const batch = result.trash?.batch;
              toast(t("Removed “{name}”", { name: c.name }), "", batch ? { label: t("Undo"), run: () => restoreBatch(batch) } : null);
              await refresh();
            },
          })
        : confirmAction(
            c.kind === "subscription" ? t("Unsubscribe from “{name}”?", { name: c.name }) : t("Delete “{name}”?", { name: c.name }),
            plural(c.event_count, "Its {count} event is removed from Chronos. This cannot be undone.", "Its {count} events are removed from Chronos. This cannot be undone."),
            c.kind === "subscription" ? t("Unsubscribe") : t("Delete"),
            async () => {
              await attempt(() => api(`/calendars/${c.id}?confirmed=true&expected_revision=${c.revision}`, "DELETE"), t("Removed “{name}”", { name: c.name }));
              await refresh();
            },
          ),
  });
  openMenu(anchor, items);
}
function eventMenu(anchor, id, occurrence, revision) {
  const o = findOccurrence(state.selected?.key);
  const items = [{ label: t("Duplicate"), icon: "copy", run: async () => { await attempt(() => api(`/events/${id}/copy`, "POST", { calendar_id: o?.calendar_id || nativeCalendars()[0].id }), t("Event duplicated")); closeLayer({ mode: "replace" }); await refresh(); } }];
  items.push("-");
  const recurring = !!(o?.recurring || o?.rrule);
  if (recurring && occurrence) items.push({ label: t("Delete this occurrence"), icon: "trash", danger: true, run: () => moveToTrashDialog(id, occurrence, o, revision) });
  items.push({ label: recurring ? t("Delete all occurrences") : t("Delete event"), icon: "trash", danger: true, run: () => moveToTrashDialog(id, "", o, revision) });
  openMenu(anchor, items);
}
/** Show the current version in the open details, after finding out that it is no longer this one. */
async function reloadDrawer() {
  const selected = state.selected;
  await refresh();
  if (!selected) return;
  if (findOccurrence(selected.key)) return openDetails(selected.key, selected.returnFocus);
  closeLayer({ mode: "replace" });
}
/** Deleting is one explicit choice: one occurrence, the whole series, or a single event. The
 * backend also refuses a repeating event without one, so losing the choice cannot widen it. */
function moveToTrashDialog(id, occurrence, o, revision) {
  const name = o?.title || "";
  const recurring = !!(o?.recurring || o?.rrule);
  const copy = occurrence
    ? { title: t("Delete only this occurrence?"), text: t("“{name}” on {when} moves to Trash. The other occurrences stay on your calendar.", { name, when: whenText(o) }), label: t("Delete this occurrence"), done: t("Occurrence moved to Trash") }
    : recurring
      ? { title: t("Delete the whole series?"), text: t("Every occurrence of “{name}” moves to Trash. Restoring it brings the whole series back.", { name }), label: t("Delete all occurrences"), done: t("Series moved to Trash") }
      : { title: t("Move “{name}” to Trash?", { name }), text: t("You can restore it from Trash at any time."), label: t("Move to Trash"), done: t("Moved to Trash") };
  const query = new URLSearchParams({ expected_revision: revision });
  if (occurrence) query.set("occurrence", occurrence);
  else if (recurring) query.set("scope", "series");
  trashConfirm({
    ...copy,
    run: async () => {
      let result;
      try {
        result = await api(`/events/${id}?${query}`, "DELETE");
      } catch (error) {
        if (!isConflict(error)) throw error;
        await leaveDialog();
        toast(t("This event changed elsewhere, so nothing was deleted. Here is the current version."), "danger");
        return reloadDrawer();
      }
      await leaveDialog();
      closeLayer({ mode: "replace" });
      toast(copy.done, "", result.trash ? { label: t("Undo"), run: () => restoreEntry(result.trash) } : null);
      await afterTrashChange();
    },
  });
}
function choosePlanCalendar(run) {
  const calendars = nativeCalendars();
  if (calendars.length === 1) return run(calendars[0].id);
  openDialog(`<div class="ae-dialog-head"><h2>${esc(t("Plan in which calendar?"))}</h2></div><div class="ae-dialog-body"><select class="ae-select" id="plan-cal">${calendars.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join("")}</select></div><div class="ae-dialog-foot"><button class="ae-btn" data-act="dialog-cancel">${esc(t("Cancel"))}</button><button class="ae-btn ae-btn--primary" id="plan-go">${esc(t("Plan"))}</button></div>`);
  $("#plan-go").onclick = () => {
    const id = $("#plan-cal").value;
    closeDialog();
    run(id);
  };
}

document.addEventListener("click", async (event) => {
  const opener = event.target.closest("[data-open]");
  if (opener) {
    const o = chronosNavigation.enabled ? findOccurrence(opener.dataset.open) : null;
    if (!o) return openDetails(opener.dataset.open, opener);
    pendingTrigger = opener;
    return commitRoute(routeForOccurrence(o));
  }
  const viewButton = event.target.closest("[data-view]");
  if (viewButton) return go(viewButton.dataset.view);
  const target = event.target.closest("[data-act]");
  if (!target) {
    const slot = event.target.closest("[data-slot]");
    if (slot && !event.target.closest(".block")) {
      const box = slot.getBoundingClientRect();
      const hour = box.height / 24;
      const minutes = Math.max(0, Math.min(23 * 60, Math.floor(((event.clientY - box.top) / hour) * 2) * 30));
      return eventEditor(null, { day: slot.dataset.slot, minutes });
    }
    const cell = event.target.closest(".cell[data-day]");
    if (cell && !event.target.closest("button")) return eventEditor(null, { day: cell.dataset.day });
    const lane = event.target.closest("[data-allday]");
    if (lane && !event.target.closest("button")) return eventEditor(null, { day: lane.dataset.allday, all_day: true });
    return;
  }
  const act = target.dataset.act;
  const id = target.dataset.id;
  if (act === "nav") return $("#app").classList.toggle("nav-open");
  if (act === "new") return eventEditor(null);
  if (act === "today") return go(state.view === "agenda" ? "agenda" : state.view, today());
  if (act === "prev") return step(-1);
  if (act === "next") return step(1);
  if (act === "goto") {
    $("#app").classList.remove("nav-open");
    return go(state.view === "agenda" ? "day" : state.view, target.dataset.day);
  }
  if (act === "open-day") return go("day", target.dataset.day);
  if (act === "mini-prev" || act === "mini-next") {
    state.miniCursor = addMonths(state.miniCursor || state.cursor, act === "mini-prev" ? -1 : 1);
    return renderSidebar();
  }
  if (act === "settings") return settingsDialog();
  if (act === "import") return importDialog();
  if (act === "subscribe") return subscribeDialog();
  if (act === "new-calendar") return calendarDialog();
  if (act === "new-category") return categoryDialog();
  if (act === "calendar-menu") return calendarMenu(target, calendarById(id));
  if (act === "event-menu") return eventMenu(target, id, target.dataset.occurrence, target.dataset.revision);
  if (act === "filter-category") {
    if (event.detail === 2 || event.altKey) return categoryDialog(state.categories.find((c) => c.id === id));
    state.categoryFilter.has(id) ? state.categoryFilter.delete(id) : state.categoryFilter.add(id);
    renderSidebar();
    return renderView();
  }
  if (act === "clear-filter") {
    state.categoryFilter.clear();
    renderSidebar();
    return renderView();
  }
  if (act === "trash") {
    $("#app").classList.remove("nav-open");
    return openTrash();
  }
  if (act === "back-calendar") return go(state.view, state.cursor);
  if (act === "trash-open") return openTrashEntry(id, target);
  if (act === "trash-restore") return trashRestoreRow(id, target);
  if (act === "trash-restore-separate") return trashRestoreRow(id, target, { as_separate: true });
  if (act === "trash-restore-batch") return restoreBatch(target.dataset.batch);
  if (act === "trash-purge") return trashPurge(id);
  if (act === "trash-empty") return trashEmpty();
  if (act === "trash-more") return loadTrash({ more: true });
  if (act === "trash-retry") return loadTrash();
  if (act === "notice-restore") return noticeRestore(id);
  if (act === "close") return closeLayer();
  if (act === "dialog-cancel") return leaveDialog();
  if (act === "reload") return refresh();
  if (act === "edit") {
    const existing = await attempt(() => api(`/events/${id}`));
    if (existing) eventEditor(existing);
    return;
  }
  if (act === "copy")
    return choosePlanCalendar(async (calendar) => {
      if (await attempt(() => api(`/events/${id}/copy`, "POST", { calendar_id: calendar }), t("Copied to your calendar"))) {
        closeLayer({ mode: "replace" });
        await refresh();
      }
    });
  if (act === "plan") {
    const o = findOccurrence(target.dataset.key);
    return choosePlanCalendar(async (calendar) => {
      if (await attempt(() => api("/projected/plan", "POST", { provider: o.provider, item_id: o.item_id, calendar_id: calendar }), t("Added to your calendar, linked to {name}", { name: PROVIDERS[o.provider]?.name || o.provider }))) {
        closeLayer({ mode: "replace" });
        await refresh();
      }
    });
  }
  if (act === "open-projected") {
    const o = findOccurrence(target.dataset.key);
    if (!o) return;
    const found = await attempt(() => api(`/projected/open?provider=${encodeURIComponent(o.provider)}&item_id=${encodeURIComponent(o.item_id)}`));
    if (!found) return;
    if (["deleted", "not_found"].includes(found.availability)) return toast(t("This is no longer available in {name}.", { name: PROVIDERS[o.provider]?.name || o.provider }), "danger");
    return bridge("navigate", { module: o.provider, ...(found.open_path ? { path: found.open_path } : {}) }).catch((e) => toast(e.message, "danger"));
  }
  if (act === "open-module") return bridge("navigate", { module: target.dataset.module, ...(target.dataset.path ? { path: target.dataset.path } : {}) }).catch((e) => toast(e.message, "danger"));
  if (act === "add-person") {
    const wrap = target.closest(".person-add");
    const search = $(".person-search", wrap);
    search.hidden = !search.hidden;
    target.setAttribute("aria-expanded", String(!search.hidden));
    if (search.hidden) return;
    const input = $("input", search);
    const event = await attempt(() => api(`/events/${target.dataset.event}`));
    if (!event) return;
    let timer;
    input.oninput = () => {
      clearTimeout(timer);
      timer = setTimeout(() => personSearch(event, input), 160);
    };
    input.onkeydown = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        search.hidden = true;
        target.setAttribute("aria-expanded", "false");
        target.focus();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        $(".person-option", search)?.focus();
      }
    };
    input.focus();
    return personSearch(event, input);
  }
  if (act === "add-place") {
    const search = $(".place-search", target.closest(".person-add"));
    search.hidden = !search.hidden;
    target.setAttribute("aria-expanded", String(!search.hidden));
    if (search.hidden) return;
    const input = $("input", search);
    const event = await attempt(() => api(`/events/${target.dataset.event}`));
    if (!event) return;
    let timer;
    input.oninput = () => {
      clearTimeout(timer);
      timer = setTimeout(() => placeSearch(event, input), 160);
    };
    input.focus();
    return placeSearch(event, input);
  }
  if (act === "pick-place") {
    const p = (placeSearch.items || [])[Number(target.dataset.index)];
    if (!p) return;
    const updated = await attempt(() => api(`/events/${target.dataset.event}/places`, "POST", { resource: p.resource, label: p.label }), t("{name} added", { name: p.label }));
    if (updated && state.selected) return openDetails(state.selected.key, state.selected.returnFocus);
    return;
  }
  if (act === "pick-person") {
    const p = (personSearch.items || [])[Number(target.dataset.index)];
    if (!p) return;
    const updated = await attempt(() => api(`/events/${target.dataset.event}/people`, "POST", { resource: p.resource, label: p.label }), t("{name} added", { name: p.label }));
    if (updated && state.selected) return openDetails(state.selected.key, state.selected.returnFocus);
    return;
  }
  if (act === "remove-person") {
    if (await attempt(() => api(`/events/${target.dataset.event}/links/${target.dataset.id}`, "DELETE"), t("Removed from this event")) && state.selected)
      return openDetails(state.selected.key, state.selected.returnFocus);
    return;
  }
  if (act === "agenda-past" || act === "agenda-upcoming") {
    state.agendaPast = act === "agenda-past";
    state.agendaDays = 60;
    return loadOccurrences();
  }
  if (act === "agenda-more") {
    state.agendaDays = Math.min(120, state.agendaDays + 30);
    return loadOccurrences();
  }
});
document.addEventListener("change", async (event) => {
  const target = event.target.closest("[data-act]");
  if (!target) return;
  if (target.dataset.act === "toggle-calendar") {
    await attempt(() => api(`/calendars/${target.dataset.id}`, "PUT", { visible: target.checked }));
    await refresh();
  }
  if (target.dataset.act === "toggle-source") {
    if (target.dataset.provider === "mnemosyne" && target.checked) {
      target.checked = false;
      return settingsDialog();
    }
    await attempt(() => api(`/sources/${target.dataset.provider}`, "PUT", { enabled: target.checked }));
    await refresh();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (closeMenu()) return;
    if (dialog().open) return;
    if ($(".ae-drawer")) return closeLayer();
    if ($("#app").classList.contains("nav-open")) return $("#app").classList.remove("nav-open");
    if (state.results) {
      $("#search").value = "";
      state.query = "";
      state.results = null;
      return renderView();
    }
    if (state.screen === "trash" && state.query) {
      $("#search").value = "";
      state.query = "";
      return loadTrash({ quiet: true });
    }
    return;
  }
  if (event.target.closest("input,textarea,select,[contenteditable]") || dialog().open || event.metaKey || event.ctrlKey || event.altKey) return;
  const keys = { t: () => go(state.view, today()), m: () => go("month"), w: () => go("week"), d: () => go("day"), a: () => go("agenda"), n: () => eventEditor(null), ArrowLeft: () => step(-1), ArrowRight: () => step(1), j: () => step(1), k: () => step(-1), "/": () => $("#search").focus() };
  if (keys[event.key]) {
    event.preventDefault();
    keys[event.key]();
  }
});
window.addEventListener("resize", () => {
  if (state.view === "month" && state.cursor) renderView();
});

/* ───────────────────────── Start ───────────────────────── */

async function start() {
  try {
    state.context = await bridge("context");
  } catch {
    /* standalone preview: keep defaults */
  }
  activeLocale = safeLocale(state.context.locale);
  document.documentElement.lang = activeLocale;
  try {
    const data = await api("/state");
    Object.assign(state, { settings: data.settings, calendars: data.calendars, categories: data.categories, sources: data.sources, version: data.version, trashCount: data.trash_count });
    if (!state.settings.time_zone_set) {
      const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (zone) state.settings = await api("/settings", "PUT", { time_zone: zone }).catch(() => state.settings);
    }
  } catch (error) {
    $("#app").innerHTML = `<div class="ae-empty">${icon("alert")}<h3>${esc(t("Chronos could not start"))}</h3><p>${esc(error.message)}</p></div>`;
    return;
  }
  state.cursor = today();
  renderShell();
  renderSidebar();
  setInterval(() => {
    if (state.view === "week" || state.view === "day") {
      const line = $(".now-line");
      if (line) line.style.top = `calc(${zoneParts(new Date()).minutes / 60} * var(--hour))`;
    }
  }, 60000);
  // Inside a Nexus that supports it, the browser URL and Back/Forward follow Chronos's screens.
  if (state.context.navigation?.versions?.includes(1)) {
    try {
      if (await chronosNavigation.start(state.context)) {
        schedulePoll();
        // The first screen gets its exact address (view and date) without a new history entry.
        const initial = shownParsed && !shownParsed.notFound && !shownParsed.date && !shownParsed.event && !shownParsed.projected && !shownParsed.trash ? ChronosRoutes.serialize(calendarRoute()) : shownRoute;
        if (initial) {
          if (initial !== shownRoute) shownRoute = initial;
          await queueNavigation(initial, "replace").catch(() => {});
        }
        return;
      }
    } catch {
      /* the host did not answer the handshake: keep the in-memory navigation below */
    }
  }
  await loadOccurrences();
  schedulePoll();
  // A link to one event, from another module (open_path of the resolver).
  const deep = location.pathname.match(/\/events\/([0-9a-f-]{36})$/);
  if (deep) {
    const event = await api(`/events/${deep[1]}`).catch(() => null);
    if (event) {
      state.cursor = String(event.start).slice(0, 10);
      await loadOccurrences();
      const found = state.occurrences.find((o) => o.event_id === deep[1]);
      if (found) openDetails(found.key);
    }
  }
}
start();
