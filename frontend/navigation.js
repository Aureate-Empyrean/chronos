/* Chronos adapter for the Nexus navigation contract (`empyrean-navigation-v1`, SDK in
   vendor/nexus-navigation.js, kept in sync by empyrean-nexus/scripts/sync-navigation.mjs).
   Nexus owns the browser URL and history; Chronos owns its routes.

     /month|week|day|agenda/<YYYY-MM-DD>        a calendar view on a date
     /events/<id>[?o=<occurrence>&view=&date=]  a native event, one exact occurrence of it
     /projected/<provider>?item=<id>&view=&date= a date another module owns

   Search text, category filters and agenda range are private per-entry view state, and an
   unsaved event editor is a draft. None of them enter the URL. Without a supporting host,
   Chronos keeps its old in-memory navigation. */

const CHRONOS_VIEWS = ["month", "week", "day", "agenda"];
function validDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}
const ChronosRoutes = {
  parse(value) {
    const url = new URL(String(value || "/"), "http://chronos.invalid");
    const path = url.pathname.replace(/\/+$/, "") || "/";
    const context = () => {
      const view = url.searchParams.get("view");
      const date = url.searchParams.get("date");
      return { view: CHRONOS_VIEWS.includes(view) ? view : null, date: validDate(date) ? date : null };
    };
    if (path === "/") return { view: "month", date: null };
    const calendar = path.match(/^\/(month|week|day|agenda)\/(\d{4}-\d{2}-\d{2})$/);
    if (calendar && validDate(calendar[2])) return { view: calendar[1], date: calendar[2] };
    const event = path.match(/^\/events\/([0-9a-f-]{36})$/);
    if (event) return { event: { id: event[1], occurrence: url.searchParams.get("o") || "" }, ...context() };
    const projected = path.match(/^\/projected\/([a-z][a-z0-9-]{0,47})$/);
    if (projected && url.searchParams.get("item")) return { projected: { provider: projected[1], item: url.searchParams.get("item") }, ...context() };
    return { notFound: true, path: String(value || "/") };
  },
  serialize(route) {
    if (route.notFound) return route.path;
    const context = () => {
      const q = new URLSearchParams();
      if (route.view) q.set("view", route.view);
      if (route.date) q.set("date", route.date);
      return q;
    };
    if (route.event) {
      const q = context();
      if (route.event.occurrence) q.set("o", route.event.occurrence);
      const text = q.toString();
      return `/events/${route.event.id}${text ? `?${text}` : ""}`;
    }
    if (route.projected) {
      const q = context();
      q.set("item", route.projected.item);
      return `/projected/${route.projected.provider}?${q}`;
    }
    return route.date ? `/${route.view}/${route.date}` : "/";
  },
};

let shownRoute = null;
let shownParsed = null;
let heldRoute = null;
let pendingTrigger = null;
let queuedRoute = null;
let clearSearchOnApply = false;
const retainedDrafts = new Map();
let lastCheckpointDirty = false;

const calendarRoute = () => ({ view: state.view, date: state.cursor });
function routeForOccurrence(o) {
  const context = { view: state.view, date: state.cursor };
  if (o.origin === "projection") return { projected: { provider: o.provider, item: o.item_id }, ...context };
  return { event: { id: o.event_id, occurrence: o.occurrence || "" }, ...context };
}
function routeHasDetail() {
  return !heldRoute && !!(shownParsed?.event || shownParsed?.projected);
}
function commitRoute(route, mode = "push") {
  queuedRoute = route;
  return queueNavigation(ChronosRoutes.serialize(route), mode)
    .catch((error) => {
      if (!/superseded/i.test(error.message)) toast(error.message, "danger");
    })
    .finally(() => {
      if (queuedRoute === route) queuedRoute = null;
    });
}

/* ── The event editor ── */
const editorFields = () => {
  const root = dialog();
  return { fields: $$("input, select, textarea", root).map((el) => (el.type === "checkbox" || el.type === "radio" ? el.checked : el.value)), days: $$("#ev-days [aria-pressed=true]", root).map((b) => b.dataset.day) };
};
let editorSession = null;
function eventEditorOpened(existing, defaults) {
  editorSession = { existing, defaults, baseline: JSON.stringify(editorFields()) };
}
const editorOpen = () => dialog().open && !!$("#editor", dialog());
const editorDirty = () => !!editorSession && editorOpen() && JSON.stringify(editorFields()) !== editorSession.baseline;
function captureDraft() {
  if (!editorDirty()) return null;
  const { existing, defaults } = editorSession;
  return { key: existing ? `event:${existing.id}` : "event:new", eventId: existing?.id || null, defaults, label: $("#ev-title", dialog()).value || t("New event"), route: shownRoute, ...editorFields() };
}
async function reopenDraft(draft) {
  const existing = draft.eventId ? await api(`/events/${draft.eventId}`) : null;
  await eventEditor(existing, draft.defaults || {});
  const root = dialog();
  $$("input, select, textarea", root).forEach((el, i) => {
    if (draft.fields[i] === undefined) return;
    if (el.type === "checkbox" || el.type === "radio") el.checked = !!draft.fields[i];
    else el.value = draft.fields[i];
  });
  $$("#ev-days button", root).forEach((b) => b.setAttribute("aria-pressed", String(draft.days.includes(b.dataset.day))));
  root.dispatchEvent(new Event("change"));
}
function checkpointValue() {
  const live = captureDraft();
  const drafts = [...retainedDrafts.values()].filter((d) => d.key !== live?.key);
  if (live) drafts.push(live);
  return { version: 1, dirty: drafts.length > 0, drafts };
}
function checkpointNow() {
  if (!chronosNavigation.enabled) return Promise.resolve();
  const value = checkpointValue();
  if (!value.dirty && !lastCheckpointDirty) return Promise.resolve();
  return chronosNavigation.checkpoint(value).then(() => {
    lastCheckpointDirty = value.dirty;
  });
}
let checkpointTimer;
function scheduleCheckpoint() {
  clearTimeout(checkpointTimer);
  checkpointTimer = setTimeout(() => checkpointNow().catch((error) => toast(error.message, "danger")), 400);
}
for (const kind of ["input", "change"]) document.addEventListener(kind, (event) => event.target.closest("#editor") && scheduleCheckpoint());
function renderDraftTray() {
  let tray = $("#draft-tray");
  if (!retainedDrafts.size) return tray?.remove();
  if (!tray) {
    tray = document.createElement("div");
    tray.id = "draft-tray";
    tray.className = "draft-tray ae-glass";
    tray.setAttribute("role", "status");
    document.body.append(tray);
  }
  tray.replaceChildren(
    ...[...retainedDrafts.values()].map((draft) => {
      const row = document.createElement("div");
      row.className = "draft-tray-row";
      row.innerHTML = `<span class="grow">${esc(t("An unsaved event is kept in this tab: {label}", { label: draft.label }))}</span><button class="ae-btn ae-btn--sm ae-btn--primary" data-draft="resume">${esc(t("Resume editing"))}</button><button class="ae-btn ae-btn--sm ae-btn--quiet" data-draft="discard">${esc(t("Discard"))}</button>`;
      $('[data-draft="resume"]', row).onclick = async () => {
        try {
          await reopenDraft(draft);
          retainedDrafts.delete(draft.key);
          renderDraftTray();
          scheduleCheckpoint();
        } catch {
          toast(t("This draft could not be reopened. It stays available here."), "danger");
        }
      };
      $('[data-draft="discard"]', row).onclick = () => {
        retainedDrafts.delete(draft.key);
        renderDraftTray();
        checkpointNow().catch(() => {});
      };
      return row;
    }),
  );
}
function renderHoldNotice() {
  const root = $("#editor", dialog());
  if (!root) return;
  let notice = $("#dialog-hold", root);
  if (!heldRoute) return notice?.remove();
  if (notice) return;
  notice = document.createElement("div");
  notice.id = "dialog-hold";
  notice.className = "ae-banner ae-banner--warn dialog-hold";
  notice.setAttribute("role", "status");
  notice.innerHTML = `<div>${esc(t("The browser moved to another page. Your unsaved event stays here until you save or discard it, or use Back and Forward to return."))}</div><button class="ae-btn ae-btn--sm" id="dialog-hold-discard">${esc(t("Discard and continue"))}</button>`;
  root.prepend(notice);
  $("#dialog-hold-discard", notice).onclick = () => closeDialog();
}
document.addEventListener(
  "close",
  (event) => {
    if (event.target !== dialog()) return;
    editorSession = null;
    scheduleCheckpoint();
    if (!heldRoute) return;
    const { reference, route } = heldRoute;
    heldRoute = null;
    shownRoute = reference;
    shownParsed = route;
    showRoute(route, null);
  },
  true,
);

/* ── Showing a route ── */
function dayOfEvent(event) {
  return event.all_day ? event.start : zoneParts(new Date(event.start)).day;
}
async function fetchEvent(id) {
  try {
    return await api(`/events/${id}`);
  } catch (error) {
    if (/not found/i.test(error.message)) return null;
    throw error;
  }
}
function showNotFound() {
  state.notFound = true;
  state.results = null;
  renderView();
  return "not-found";
}
async function showRoute(next, message) {
  const isCurrent = message?.isCurrent || (() => true);
  const view = message?.viewState;
  closeLayerUI();
  state.notFound = false;
  if (clearSearchOnApply) {
    clearSearchOnApply = false;
    state.results = null;
    state.query = "";
    if ($("#search")) $("#search").value = "";
  }
  if (next.notFound) return showNotFound();
  if (view) {
    state.categoryFilter = new Set(view.category || []);
    state.agendaPast = !!view.agendaPast;
    state.agendaDays = view.agendaDays || 60;
  }
  let date = next.date;
  let event = null;
  if (next.event && !date) {
    event = await fetchEvent(next.event.id);
    if (!isCurrent()) return;
    if (!event) return showNotFound();
    date = dayOfEvent(event);
  }
  state.view = next.view || state.view;
  state.cursor = date || state.cursor || today();
  state.miniCursor = null;
  const range = viewRange();
  if (state.range?.start !== range.start || state.range?.days !== range.days || !state.occurrences.length) await loadOccurrences();
  else renderView();
  if (!isCurrent()) return;
  renderSidebar();
  if (view?.query?.trim().length >= 2) {
    state.query = view.query;
    if ($("#search")) $("#search").value = view.query;
    state.results = await api("/search?q=" + encodeURIComponent(view.query.trim())).catch(() => null);
    if (!isCurrent()) return;
    renderView();
  } else if (view) {
    state.query = "";
    state.results = null;
    if ($("#search")) $("#search").value = "";
    renderView();
  }
  if (next.event) {
    const ref = next.event;
    let o = state.occurrences.find((x) => x.event_id === ref.id && (!ref.occurrence || x.occurrence === ref.occurrence)) || (ref.occurrence ? state.searchIndex?.get(`${ref.id}/${ref.occurrence}`) : null);
    if (!o && !ref.occurrence) {
      event ??= await fetchEvent(ref.id);
      if (!isCurrent()) return;
      if (!event) return showNotFound();
      const placedDay = dayOfEvent(event);
      o = { ...event, key: `${event.id}/`, event_id: event.id, sDay: placedDay, eDay: event.all_day ? addDays(event.end, -1) : zoneParts(new Date(event.end)).day, status: event.status };
      state.searchIndex = new Map([...(state.searchIndex || []), [o.key, o]]);
    }
    if (!o) return showNotFound(); // That exact occurrence no longer exists on this date.
    await openDetails(o.key, takeTrigger());
  } else if (next.projected) {
    const key = `${next.projected.provider}:${next.projected.item}`;
    if (!findOccurrence(key)) return showNotFound();
    await openDetails(key, takeTrigger());
  }
  if (view?.scroll && $("#view")) $("#view").scrollTop = view.scroll;
}
function takeTrigger() {
  const trigger = pendingTrigger;
  pendingTrigger = null;
  return trigger;
}

const chronosNavigation = EmpyreanNavigation.createClient({
  async apply(value, message) {
    if (message.checkpoint?.version === 1) {
      for (const draft of message.checkpoint.drafts || []) retainedDrafts.set(draft.key, draft);
      lastCheckpointDirty = !!message.checkpoint.dirty;
      renderDraftTray();
    }
    const next = ChronosRoutes.parse(value);
    const reference = ChronosRoutes.serialize(next);
    if (reference === shownRoute) {
      if (heldRoute) {
        heldRoute = null;
        renderHoldNotice();
      }
      return;
    }
    if (shownRoute && editorDirty()) {
      heldRoute = { reference, route: next };
      renderHoldNotice();
      return;
    }
    if (!message.isCurrent()) return;
    heldRoute = null;
    const previous = { route: shownRoute, parsed: shownParsed };
    shownRoute = reference;
    shownParsed = next;
    const outcome = await showRoute(next, message);
    // Superseded while loading: the next restore must show its page. An editor opened meanwhile
    // still belongs to the page that was on screen.
    if (!message.isCurrent() && shownRoute === reference) {
      shownRoute = editorDirty() ? previous.route : null;
      if (editorDirty()) shownParsed = previous.parsed;
    }
    return outcome;
  },
  beforeLeave: checkpointNow,
  captureView() {
    if (heldRoute || state.notFound || !state.cursor) return null;
    return { scroll: $("#view")?.scrollTop || 0, query: state.query, category: [...state.categoryFilter], agendaPast: state.agendaPast, agendaDays: state.agendaDays };
  },
  onError(error) {
    toast(error.message, "danger");
  },
});

let navigationQueue = Promise.resolve();
function queueNavigation(reference, mode) {
  const next = navigationQueue.catch(() => {}).then(() => chronosNavigation.navigate(reference, mode));
  navigationQueue = next;
  return next;
}
