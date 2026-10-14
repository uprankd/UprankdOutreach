/* Almo front end - plain JS, no build step. */
(function () {
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => Number(n || 0).toLocaleString("en-GB");
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : v; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
};

const I = {
  overview: '<rect x="2" y="2.5" width="12" height="11" rx="1.5"/><path d="M2 6h12M6 6v7.5"/>',
  sites: '<circle cx="8" cy="8" r="6"/><path d="M2 8h12M8 2c1.8 1.7 2.6 3.7 2.6 6S9.8 12.3 8 14C6.2 12.3 5.4 10.3 5.4 8S6.2 3.7 8 2Z"/>',
  attention: '<path d="M3 10.5V7a5 5 0 0 1 10 0v3.5l1 1.5H2l1-1.5ZM6.5 14h3"/>',
  prices: '<path d="M8.6 2H13a1 1 0 0 1 1 1v4.4a1 1 0 0 1-.3.7l-6 6a1 1 0 0 1-1.4 0L2 9.8a1 1 0 0 1 0-1.4l6-6a1 1 0 0 1 .6-.4Z"/><circle cx="11" cy="5" r="1"/>',
  pitch: '<rect x="2" y="3.5" width="12" height="9" rx="1.5"/><path d="m2.5 4.5 5.5 4 5.5-4"/>',
  settings: '<path d="M2 4.5h7M12 4.5h2M2 11.5h2M7 11.5h7"/><circle cx="10.5" cy="4.5" r="1.5"/><circle cx="5.5" cy="11.5" r="1.5"/>',
  up: '<path d="M8 13V3m0 0L4 7m4-4 4 4"/>',
  down: '<path d="M8 3v10m0 0 4-4m-4 4-4-4"/>',
  info: '<circle cx="8" cy="8" r="6.2"/><path d="M8 7.2V11M8 5h.01"/>',
  close: '<path d="m4 4 8 8M12 4l-8 8"/>',
  ext: '<path d="M9 2.5h4.5V7M13.5 2.5 7 9M11.5 9.5v3a1 1 0 0 1-1 1h-7a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1h3"/>',
  upload: '<path d="M8 11V2.5m0 0L4.8 5.7M8 2.5l3.2 3.2M2.5 10.5v2a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-2"/>',
  download: '<path d="M8 2.5V11m0 0L4.8 7.8M8 11l3.2-3.2M2.5 10.5v2a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-2"/>',
  database: '<ellipse cx="8" cy="3.8" rx="5.5" ry="1.9"/><path d="M2.5 3.8v8.4c0 1 2.5 1.9 5.5 1.9s5.5-.9 5.5-1.9V3.8M2.5 8c0 1 2.5 1.9 5.5 1.9s5.5-.9 5.5-1.9"/>',
  outreach: '<path d="M14 2 7 9M14 2l-4.5 12L7 9 2 6.5 14 2Z"/>',
  copy: '<rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/><path d="M10.5 5.5v-2a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2"/>',
  plus: '<path d="M8 3v10M3 8h10"/>',
  inbox: '<path d="M2 9.5 3.6 3.7a1 1 0 0 1 1-.7h6.8a1 1 0 0 1 1 .7L14 9.5V13H2V9.5Zm0 0h3.5l1 1.5h3l1-1.5H14"/>',
};
const icon = (n, cls = "") => '<svg class="' + cls + '" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' + I[n] + "</svg>";

const PILL = {
  queued: "", reading: "sky busy", sending: "sky busy", not_fit: "", no_email: "", ready: "sky", waiting: "sky",
  followed_up: "sky", replied: "warn busy", needs_you: "warn", complete: "good", declined: "",
  no_reply: "", bounced: "bad", error: "bad",
};
const pill = (s, statuses) => '<span class="pill ' + (PILL[s] || "") + '">' + esc((statuses || S.statuses || {})[s] || s) + "</span>";

const S = {
  campaign: Number(store.get("almo-campaign", "0")) || 0,
  days: Number(store.get("almo-days", "30")) || 30,
  route: "overview", data: null, statuses: {}, filter: "all", q: "", drawer: null,
  settingsDirty: false,
};

async function api(path, opts = {}) {
  const init = { method: opts.method || (opts.body ? "POST" : "GET"), headers: {} };
  if (opts.body instanceof FormData) init.body = opts.body;
  else if (opts.body) { init.body = JSON.stringify(opts.body); init.headers["Content-Type"] = "application/json"; }
  const r = await fetch(path, init);
  let j = {};
  try { j = await r.json(); } catch (e) {}
  if (r.status === 401 && j.login) { location.href = "/login?next=" + encodeURIComponent(location.pathname + location.hash); throw new Error("Please sign in"); }
  if (!r.ok) throw new Error(j.error || "Something went wrong (" + r.status + ")");
  return j;
}
function toast(msg, ms = 3200) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), ms);
}
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return; } catch (e) {}
  const ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); } catch (e) {} ta.remove();
}
const ago = (ts) => {
  if (!ts) return "";
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + "m ago";
  if (s < 86400) return Math.floor(s / 3600) + "h ago";
  if (s < 86400 * 7) return Math.floor(s / 86400) + "d ago";
  return new Date(ts * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
};
const day = (ts) => ts ? new Date(ts * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "–";
const campQ = () => (S.campaign ? "campaign=" + S.campaign : "");

/* ------------------------------------------------------------------ shell */
const NAV0 = [["database", "All websites", "database"]];
const NAV1 = [["overview", "Overview", "overview"], ["websites", "Outreach", "outreach"], ["attention", "Needs you", "attention"]];
const NAV2 = [["pitch", "Pitch email", "pitch"], ["settings", "Settings", "settings"]];
function renderNav() {
  const att = S.data ? S.data.attention : 0;
  const item = ([key, label, ic]) => '<a href="#/' + key + '" title="' + label + '"' + (S.route === key ? ' aria-current="page"' : "") + ">" + icon(ic, "nav-icon") + '<span class="nav-label">' + label + "</span>" + (key === "attention" && att ? '<span class="count">' + att + "</span>" : "") + "</a>";
  $("#nav0").innerHTML = NAV0.map(item).join("");
  $("#nav1").innerHTML = NAV1.map(item).join("");
  $("#nav2").innerHTML = NAV2.map(item).join("");
}
function renderCampaigns() {
  const d = S.data; if (!d) return;
  const camps = d.campaigns;
  const cur = camps.find((c) => c.id === S.campaign);
  if (S.campaign && !cur) { S.campaign = 0; store.set("almo-campaign", "0"); }
  $("#campName").textContent = cur ? cur.name : "All campaigns";
  $("#campMark").textContent = (cur ? cur.name : "A").slice(0, 1).toUpperCase();
  const total = camps.reduce((a, c) => a + c.n, 0);
  $("#campList").innerHTML = '<button data-c="0"' + (!S.campaign ? ' aria-current="true"' : "") + '><span class="client-mark">A</span><span class="cname">All campaigns</span><span class="n">' + fmt(total) + "</span></button>" +
    camps.map((c) => '<button data-c="' + c.id + '"' + (S.campaign === c.id ? ' aria-current="true"' : "") + '><span class="client-mark">' + esc(c.name.slice(0, 1).toUpperCase()) + '</span><span class="cname">' + esc(c.name) + '</span><span class="n">' + fmt(c.n) + "</span></button>").join("");
  $("#addCamp").innerHTML = camps.map((c) => '<option value="' + c.id + '"' + ((S.campaign || camps[0].id) === c.id ? " selected" : "") + ">" + esc(c.name) + "</option>").join("");
  const st = d.settings;
  const u = d.user;
  const box = (st.mailboxes || []).find((b) => b.sender_name);
  const nm = u ? u.name : (box && box.sender_name) || "Uprankd";
  $("#whoName").textContent = nm;
  $("#whoSub").textContent = u ? u.email : "Almo · on this computer";
  const initials = (nm || "U").split(/\s+/).map((x) => x[0]).slice(0, 2).join("").toUpperCase();
  $("#avatar").innerHTML = u && u.picture ? '<img src="' + esc(u.picture) + '" alt="" referrerpolicy="no-referrer">' : esc(initials);
  $("#signOut").hidden = !u;
}
function renderRunchip() {
  const d = S.data; if (!d) return;
  const st = d.settings, w = d.worker;
  let dot = "", text;
  if (!st.running) { text = "Paused"; dot = "warn"; }
  else if (w.send_error || w.inbox_error) { text = "Problem - see Overview"; dot = "bad"; }
  else if (st.send_mode === "off") { text = "Running · sending off"; dot = "on"; }
  else if (w.send_wait === "pacing" && w.next_send_in) { text = "Running · next email " + mmss(w.next_send_in); dot = "on"; }
  else if (w.send_wait) { text = "Running · " + w.send_wait; dot = "on"; }
  else text = "Running", dot = "on";
  if (st.send_mode === "test" && st.running) text += " · test";
  $("#runDot").className = "dot " + dot;
  $("#runText").textContent = text;
}
const mmss = (s) => Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");

/* ------------------------------------------------------------------ data */
async function refresh() {
  try {
    S.data = await api("/api/state?days=" + S.days + "&" + campQ());
    S.statuses = S.data.statuses;
  } catch (e) { return; }
  renderNav(); renderCampaigns(); renderRunchip();
  if (S.route === "overview") renderOverview();
  if (["websites", "attention"].includes(S.route)) loadSites();
  if (S.route === "database" && !S.drawerEditing && Date.now() - (S.dbLoaded || 0) > 15000) loadDB();
  if (S.drawer && !S.drawerEditing) openSite(S.drawer, true);
}

/* ------------------------------------------------------------------ overview */
function deltaHTML(m) {
  if (!m.prev && !m.value) return '<div class="delta">nothing yet</div>';
  if (!m.prev) return '<div class="delta">no earlier data</div>';
  const ch = ((m.value - m.prev) / m.prev) * 100;
  const up = ch >= 0;
  return '<div class="delta"><span class="' + (up ? "good" : "bad") + '">' + icon(up ? "up" : "down") + "</span><b class=\"" + (up ? "good" : "bad") + '">' + Math.abs(ch).toFixed(1) + "%</b>&nbsp;vs. prev " + S.days + "d</div>";
}
function banners(d) {
  const st = d.settings, w = d.worker, out = [];
  const b = (cls, ic, html, btn) => '<div class="banner ' + cls + '">' + icon(ic) + '<div class="grow">' + html + "</div>" + (btn || "") + "</div>";
  if (w.send_error) out.push(b("bad", "info", "<b>Sending stopped:</b> " + esc(w.send_error), '<a class="ctl ctl--tiny" href="#/settings">Fix in Settings</a>'));
  if (w.inbox_error) out.push(b("bad", "info", "<b>Can't read your inbox:</b> " + esc(w.inbox_error), '<a class="ctl ctl--tiny" href="#/settings">Fix in Settings</a>'));
  if (w.ai_error) out.push(b("", "info", "<b>AI problem:</b> " + esc(w.ai_error), '<a class="ctl ctl--tiny" href="#/settings">Settings</a>'));
  if (!st.running) out.push(b("", "info", "Paused. Nothing is checked or sent.", '<button class="ctl ctl--tiny" data-act="resume">Resume</button>'));
  else if (st.send_mode === "off" && d.setup[3].done) out.push(b("sky", "info", "Sending is off. Websites are checked and emails found, but nothing is sent yet.", '<a class="ctl ctl--tiny" href="#/settings#sending">Turn on sending</a>'));
  else if (st.send_mode === "test") out.push(b("sky", "info", "Test mode: each email goes to the mailbox that sends it (<b>" + esc((st.mailboxes || []).filter((b) => b.active).map((b) => b.email).join(", ") || "your mailbox") + "</b>), not to the websites.", '<a class="ctl ctl--tiny" href="#/settings#sending">Change</a>'));
  return out.join("");
}
function renderOverview() {
  const d = S.data, v = $("#view");
  const setupLeft = d.setup.filter((x) => !x.done).length;
  const hints = { account: "Gmail, Fastmail or Zoho", name: "For your signature", ai: "Claude, OpenAI or Gemini", sites: "Paste a list", send: "Test first" };
  const go = { account: "#/settings#account", name: "#/settings#account", ai: "#/settings#ai", sites: "add", send: "#/settings#sending" };
  let html = banners(d);
  if (setupLeft) {
    html += '<section><div class="head"><div><h2 class="sec">Get started</h2><div class="pagesub">' + (5 - setupLeft) + " of 5 done</div></div></div><div class=\"steps\">" +
      d.setup.map((x, i) => '<button class="step' + (x.done ? " done" : "") + '" data-go="' + go[x.key] + '"><span class="tick">' + (x.done ? "✓" : i + 1) + "</span><span><b>" + esc(x.label) + "</b><span>" + hints[x.key] + "</span></span></button>").join("") + "</div></section>";
  }
  html += '<section><div class="metrics">' + d.metrics.map((m) => '<div class="metric"><div class="label">' + esc(m.label) + '</div><div class="fig">' + fmt(m.value) + (m.unit ? '<span class="unit">' + m.unit + "</span>" : "") + "</div>" + deltaHTML(m) + "</div>").join("") + "</div></section>";
  html += '<section><div class="head"><div><h2 class="sec">Emails sent</h2><div class="pagesub">' + rangeLabel(d.series) + '</div></div><div class="legend"><span><i></i>Sent</span><span><i class="r"></i>Replies</span></div></div><div class="plot" id="plot"></div></section>';
  const f = d.funnel;
  html += '<section><div class="head"><div><h2 class="sec">Funnel</h2><div class="pagesub">All time</div></div></div><div class="funnel">' +
    f.map((s, i) => {
      const pct = f[0].value ? (100 * s.value) / f[0].value : 0;
      const next = f[i + 1];
      const conv = next ? (s.value ? Math.round((100 * next.value) / s.value) : 0) : null;
      return '<div class="funnel-step"><div class="funnel-step-head"><span class="label">' + s.label + '</span><span class="funnel-index">' + (i + 1) + '</span></div><div class="funnel-value">' + fmt(s.value) + '</div><div class="funnel-track"><span style="width:' + pct.toFixed(1) + '%"></span></div><div class="funnel-loss">' + (conv != null ? "<span>" + conv + "% continue</span><span>to " + next.label.toLowerCase() + "</span>" : "<span>" + pct.toFixed(0) + "%</span><span>of all added</span>") + "</div></div>";
    }).join("") + "</div></section>";
  // status rows + activity
  const order = ["needs_you", "replied", "complete", "waiting", "followed_up", "ready", "queued", "reading", "no_reply", "declined", "bounced", "no_email", "not_fit", "error"];
  const rows = order.filter((k) => d.by_status[k]).map((k) => [k, d.by_status[k]]);
  const tot = rows.reduce((a, r) => a + r[1], 0) || 1, max = Math.max(1, ...rows.map((r) => r[1]));
  const statusHTML = rows.length ? '<div class="rhd"><span class="label t">Status</span><span class="label v">Sites</span><span class="label p">Share</span></div>' +
    rows.map(([k, n]) => '<div class="row" data-go="#/websites?f=' + k + '"><div class="t"><em>' + esc(d.statuses[k]) + '</em><span class="track"><span class="bar" style="width:' + (100 * n / max).toFixed(1) + '%"></span></span></div><span class="v">' + fmt(n) + '</span><span class="p">' + (100 * n / tot).toFixed(1) + "%</span></div>").join("")
    : '<div class="empty"><strong>No websites yet</strong><button class="ctl ctl--primary" data-go="add">Add websites</button></div>';
  const feed = d.events.length ? '<div class="feed">' + d.events.slice(0, 12).map((e) => '<div class="feed-item"><span class="k k-' + e.kind + '"></span><span class="what">' + (e.domain ? '<b data-site="' + e.site_id + '">' + esc(e.domain) + "</b> · " : "") + esc(e.text) + '</span><span class="when">' + ago(e.ts) + "</span></div>").join("") + "</div>" : '<div class="empty"><p>No activity yet.</p></div>';
  html += '<section class="cols"><div><div class="head"><div><h2 class="sec">Status</h2><div class="pagesub">' + fmt(tot) + ' websites in outreach</div></div><a class="ctl ctl--tiny" href="#/websites">Open Outreach</a></div>' + statusHTML + '</div><div><div class="head"><div><h2 class="sec">Activity</h2><div class="pagesub">Latest ' + Math.min(12, d.events.length) + ' events</div></div><button class="ctl ctl--tiny" data-act="inbox">' + icon("inbox") + 'Check inbox</button></div>' + feed + "</div></section>";
  v.innerHTML = html;
  drawChart($("#plot"), d.series);
}
function rangeLabel(series) {
  if (!series.length) return "";
  const f = (s) => new Date(s + "T00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  return f(series[0].date) + " – " + f(series[series.length - 1].date);
}
function niceMax(v) { if (v <= 4) return 4; const p = Math.pow(10, Math.floor(Math.log10(v))); for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p; return v; }
function drawChart(el, series) {
  if (!el) return;
  const W = el.clientWidth || 900, H = el.clientHeight || 260, L = 34, B = 30, T = 8;
  const max = niceMax(Math.max(1, ...series.map((s) => Math.max(s.sent, s.replies))));
  const n = series.length, x = (i) => L + (n <= 1 ? 0 : (i * (W - L)) / (n - 1)), y = (v) => T + (H - B - T) * (1 - v / max);
  const path = (k) => series.map((s, i) => (i ? "L" : "M") + x(i).toFixed(1) + " " + y(s[k]).toFixed(1)).join(" ");
  let g = "";
  [0, max / 2, max].forEach((t) => { g += '<line x1="' + L + '" x2="' + W + '" y1="' + y(t) + '" y2="' + y(t) + '" stroke="var(' + (t ? "--rule" : "--rule-2") + ')"/><text x="' + (L - 12) + '" y="' + (y(t) + 4) + '" text-anchor="end" fill="var(--ink-3)" font-size="11">' + fmt(t) + "</text>"; });
  const ticks = Math.min(5, n);
  for (let k = 0; k < ticks; k++) {
    const i = Math.round((k * (n - 1)) / Math.max(1, ticks - 1));
    const lbl = new Date(series[i].date + "T00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });
    g += '<text x="' + x(i) + '" y="' + (H - 6) + '" text-anchor="' + (k === 0 ? "start" : k === ticks - 1 ? "end" : "middle") + '" fill="var(--ink-3)" font-size="11.5">' + lbl + "</text>";
  }
  const area = path("sent") + " L" + x(n - 1) + " " + y(0) + " L" + x(0) + " " + y(0) + " Z";
  el.innerHTML = '<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none"><defs><linearGradient id="ga" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--sky)" stop-opacity=".22"/><stop offset="1" stop-color="var(--sky)" stop-opacity="0"/></linearGradient></defs>' + g +
    '<path d="' + area + '" fill="url(#ga)"/><path d="' + path("sent") + '" fill="none" stroke="var(--sky)" stroke-width="2" stroke-linejoin="round"/><path d="' + path("replies") + '" fill="none" stroke="var(--good)" stroke-width="2" stroke-linejoin="round"/>' +
    '<circle cx="' + x(n - 1) + '" cy="' + y(series[n - 1].sent) + '" r="4.5" fill="var(--sky)"/><line id="hl" y1="' + T + '" y2="' + (H - B) + '" stroke="var(--rule-2)" style="display:none"/></svg><div class="tip"></div>';
  const tip = $(".tip", el), hl = $("#hl", el);
  el.onmousemove = (e) => {
    const r = el.getBoundingClientRect(), px = e.clientX - r.left;
    const i = Math.max(0, Math.min(n - 1, Math.round(((px - L) / (r.width - L)) * (n - 1))));
    const s = series[i]; const cx = (x(i) / W) * r.width;
    tip.style.display = "block"; tip.style.left = cx + "px"; tip.style.top = (y(Math.max(s.sent, s.replies)) / H) * r.height + "px";
    tip.innerHTML = "<b>" + new Date(s.date + "T00:00").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }) + "</b><br>" + s.sent + " sent · " + s.replies + " replies";
    hl.style.display = ""; hl.setAttribute("x1", x(i)); hl.setAttribute("x2", x(i));
  };
  el.onmouseleave = () => { tip.style.display = "none"; hl.style.display = "none"; };
}

/* ------------------------------------------------------------------ websites / prices */
const TABS = [["all", "All"], ["progress", "In progress"], ["waiting", "Waiting"], ["attention", "Needs you"], ["done", "Prices collected"], ["closed", "Closed"]];
function sitesShell() {
  const v = $("#view");
  {
    const only = S.route === "attention";
    v.innerHTML = '<section>' + (only ? '' : "") +
      '<div class="toolbar"><input class="search" id="q" placeholder="Search website or email" value="' + esc(S.q) + '">' + (only ? "" : '<div class="filter-tabs" id="tabs"></div><span style="flex:1"></span><button class="ctl" id="retryBtn" data-act="retry_failed" title="Look again for an email on every site that failed or had none" hidden>Retry failed</button>') + '</div><div class="tablewrap" id="tbl"></div></section>';
  }
  $("#q").oninput = (e) => { S.q = e.target.value; clearTimeout(sitesShell._t); sitesShell._t = setTimeout(loadSites, 200); };
}
async function loadSites() {
  if (!$("#tbl")) return;
  const filter = S.route === "attention" ? "attention" : S.filter;
  let d;
  try { d = await api("/api/sites?filter=" + filter + "&q=" + encodeURIComponent(S.q) + "&" + campQ()); } catch (e) { return; }
  if ($("#retryBtn")) $("#retryBtn").hidden = S.filter !== "closed";
  if ($("#tabs")) $("#tabs").innerHTML = TABS.map(([k, l]) => '<button data-f="' + k + '" class="' + (S.filter === k ? "is-on" : "") + '">' + l + ' <span class="n">' + fmt(d.counts[k]) + "</span></button>").join("");
  const rows = d.rows;
  let html;
  if (!rows.length) {
    html = S.route === "attention" ? '<div class="empty"><strong>Nothing needs you</strong><p>Replies Almo couldn\'t handle on its own show up here.</p></div>'
      : '<div class="empty"><strong>' + (S.q || S.filter !== "all" ? "Nothing matches" : "No websites yet") + '</strong><button class="ctl ctl--primary" data-go="add">Add websites</button></div>';
  } else {
    html = '<table class="dbt ot"><thead><tr><th class="l">Website</th><th class="l">Email</th><th class="l">Status</th><th class="l">Details</th><th>Price</th><th>Contacted</th><th>Updated</th></tr></thead><tbody>' +
      rows.map((r) => '<tr data-site="' + r.id + '"><td class="site l"><span class="sn">' + fav(r.domain) + '<span class="dn">' + esc(r.domain) + "</span></span></td>" + emailCell(r.email) + '<td class="l">' + pill(r.status, d.statuses) + '</td><td class="l wrap">' + esc(r.note || (r.status === "not_fit" ? r.fit_reason : "")) + "</td><td class=\"strong\">" + (numv(r.price) ? "€" + fmt(numv(r.price)) : '<span class="unk">–</span>') + '</td><td class="muted">' + day(r.sent_at) + '</td><td class="muted">' + ago(r.updated_at) + "</td></tr>").join("") + "</tbody></table>";
  }
  $("#tbl").innerHTML = html;
}

/* ------------------------------------------------------------------ database */
const fav = (d) => '<img class="fav" alt="" loading="lazy" src="https://icons.duckduckgo.com/ip3/' + encodeURIComponent(d) + '.ico" onerror="this.classList.add(\'gone\')">';
const yn = (v) => { const s = String(v || ""), l = s.toLowerCase(); return l === "yes" ? '<span class="yn y">Yes</span>' : l === "no" ? '<span class="yn n">No</span>' : !s || l === "unknown" ? '<span class="unk">–</span>' : '<span class="yn">' + esc(s) + "</span>"; };
const eur = (v) => (numv(v) ? "€" + fmt(numv(v)) : '<span class="unk">–</span>');
const linkIns = (v) => (numv(v) ? '<span class="tp ok">€' + fmt(numv(v)) + "</span>" : /^yes$/i.test(v || "") ? '<span class="tp ok">Yes</span>' : /^no$/i.test(v || "") ? '<span class="tp no">No</span>' : v ? '<span class="tp" title="' + esc(v) + '">' + esc(String(v).slice(0, 10)) + "</span>" : '<span class="unk">–</span>');
const DB_DEFAULT = { q: "", country: "", stage: "", niches: [], price_min: "", price_max: "", sort: "domain", dir: "asc", page: 0 };
const DBF = JSON.parse(JSON.stringify(DB_DEFAULT));
const DB = { rows: [], total: 0, sel: new Set(), all: false };
const STAGE_TABS = [["", "All"], ["never", "Not contacted"], ["outreach", "In outreach"], ["priced", "With prices"], ["noprice", "No price"], ["closed", "Closed"]];
const NICHES = [["casino", "Casino"], ["crypto", "Crypto"], ["loan", "Loans"], ["adult", "Adult"], ["link", "Link insertion"], ["unmarked", "Not marked sponsored"]];
const COLS = [["domain", "Website", "l site"], ["country", "Country", "l"], ["email", "Email", "l"], ["price", "Price"], ["casino", "Casino", "", "Price for a casino article - its own price, the special-topics price, or the normal price when they just said yes"], ["loan", "Loans"], ["crypto", "Crypto"], ["adult", "Adult"], ["sponsored", "Marked", "", "Are articles marked as sponsored?"], ["link", "Link ins.", "", "Link insertion into an existing article"], ["dr", "DR"], ["traffic", "Traffic"], ["status", "Status", "l"]];
const numv = (v) => { const n = parseFloat(String(v == null ? "" : v).replace(",", ".")); return isFinite(n) && n > 0 && /^\s*\d/.test(String(v)) ? n : null; };
/* What a topic costs: its own price, else the special-topics price, else the normal price when they just said yes. */
function topicPrice(r, k) {
  const v = String(r[k] || "").trim(), l = v.toLowerCase();
  if (l === "no") return { no: true };
  const own = numv(v); if (own) return { p: own, own: true };
  if (l === "yes") { const sp = numv(r.special_price), p = numv(r.price); return sp ? { p: sp } : p ? { p, base: true } : { yes: true }; }
  return v ? { text: v } : {};
}
function topicCell(r, k) {
  const t = topicPrice(r, k), base = numv(r.price);
  if (t.no) return '<span class="tp no">No</span>';
  if (t.p) {
    const x = base && Math.abs(t.p - base) > 0.5 ? (t.p / base) : null;
    return '<span class="tp ok' + (t.base ? " same" : "") + '" title="' + (t.own ? "Own price for this topic" : t.base ? "Same as the normal price" : "Special-topics price") + (x ? " · ×" + x.toFixed(1) + " the normal price" : "") + '">€' + fmt(t.p) + "</span>";
  }
  if (t.yes) return '<span class="tp ok">Yes</span>';
  if (t.text) return '<span class="tp" title="' + esc(t.text) + '">' + esc(t.text.slice(0, 10)) + "</span>";
  return '<span class="unk">–</span>';
}
const emailCell = (e) => e ? '<td class="l email"><span class="addr" title="' + esc(e) + '">' + esc(e) + '</span><button class="copy" data-copy="' + esc(e) + '" title="Copy email" aria-label="Copy ' + esc(e) + '">' + icon("copy") + "</button></td>" : '<td class="l email"><span class="unk">–</span></td>';
const tagCell = (v) => { const l = String(v || "").toLowerCase(); return l === "yes" ? '<span class="tag-s m" title="Articles are marked as sponsored">Marked</span>' : l === "no" ? '<span class="tag-s u" title="Articles are not marked as sponsored">Not marked</span>' : v ? '<span class="tag-s" title="' + esc(v) + '">' + esc(String(v).slice(0, 14)) + "</span>" : '<span class="unk">–</span>'; };
const numCell = (v) => { const n = parseFloat(String(v || "").replace(/,/g, "")); return isFinite(n) && String(v).trim() !== "" ? fmt(Math.round(n * 10) / 10) : '<span class="unk">–</span>'; };
function dbQuery(extra) {
  const p = new URLSearchParams();
  ["q", "country", "stage", "price_min", "price_max", "sort", "dir", "page"].forEach((k) => { if (DBF[k] !== "" && DBF[k] != null) p.set(k, DBF[k]); });
  if (DBF.niches.length) p.set("niches", DBF.niches.join(","));
  p.set("per", 2000);
  Object.entries(extra || {}).forEach(([k, v]) => p.set(k, v));
  return p.toString();
}
function saveDBF() {}
function resetDBF() { Object.assign(DBF, JSON.parse(JSON.stringify(DB_DEFAULT))); DB.sel.clear(); DB.all = false; }
function dbShell() {
  $("#view").innerHTML =
    '<section style="margin-bottom:34px"><div class="metrics" id="dbMetrics"></div></section>' +
    '<section><div class="toolbar"><input class="search" id="dbq" placeholder="Search" value="' + esc(DBF.q) + '">' +
    '<select class="ctl" id="dbCountry"></select><div class="filter-tabs" id="dbStage"></div></div>' +
    '<div class="toolbar chips" id="dbChips"></div><div class="tablewrap" id="dbTbl"></div><div class="pager" id="dbPager"></div></section>' +
    '<div class="bulkbar" id="bulk"></div>';
  $("#dbq").oninput = (e) => { DBF.q = e.target.value; DBF.page = 0; clearTimeout(dbShell._t); dbShell._t = setTimeout(() => { saveDBF(); loadDB(); }, 220); };
  $("#dbTbl").onscroll = edgeHints;
  $("#dbCountry").onchange = (e) => { DBF.country = e.target.value; DBF.page = 0; saveDBF(); loadDB(); };
  renderChips();
}
function renderChips() {
  $("#dbChips").innerHTML = NICHES.map(([k, l]) => '<button class="chip' + (DBF.niches.includes(k) ? " is-on" : "") + '" data-niche="' + k + '">' + l + "</button>").join("") +
    '<span class="chip-sep"></span><span class="label" style="margin:0 2px 0 4px">Price €</span><input class="mini" id="pmin" inputmode="numeric" placeholder="min" value="' + esc(DBF.price_min) + '"><span class="dim">–</span><input class="mini" id="pmax" inputmode="numeric" placeholder="max" value="' + esc(DBF.price_max) + '">' +
    (DBF.niches.length || DBF.price_min || DBF.price_max || DBF.country || DBF.stage || DBF.q ? '<button class="linkbtn" data-dbclear>Clear filters</button>' : "");
  const set = (k) => (e) => { DBF[k] = e.target.value.replace(/[^\d.]/g, ""); DBF.page = 0; clearTimeout(renderChips._t); renderChips._t = setTimeout(() => { saveDBF(); loadDB(); }, 350); };
  $("#pmin").oninput = set("price_min"); $("#pmax").oninput = set("price_max");
}
async function loadDB() {
  if (!$("#dbTbl")) return;
  let d;
  try { d = await api("/api/db?" + dbQuery()); } catch (e) { return; }
  DB.rows = d.rows; DB.total = d.total; S.dbLoaded = Date.now();
  const sm = d.summary;
  $("#dbMetrics").innerHTML = [["Websites", fmt(sm.total), "matching the filters"], ["With prices", fmt(sm.priced), sm.total ? Math.round((100 * sm.priced) / sm.total) + "% of these" : "–"],
    ["Average price", sm.priced ? "€" + fmt(sm.avg) : "–", sm.priced ? "€" + fmt(sm.lo) + " – €" + fmt(sm.hi) : "no prices yet"], ["Accept casino", fmt(sm.casino), "said yes or quoted a price"]]
    .map(([l, v, c]) => '<div class="metric"><div class="label">' + l + '</div><div class="fig">' + v + '</div><div class="metric-context">' + c + "</div></div>").join("");
  const cs = d.countries;
  $("#dbCountry").innerHTML = '<option value="">All countries</option>' + cs.map((c) => '<option value="' + esc(c.country) + '"' + (DBF.country === c.country ? " selected" : "") + ">" + esc(c.country) + " (" + c.n + ")</option>").join("");
  $("#dbStage").innerHTML = STAGE_TABS.map(([k, l]) => '<button data-stage="' + k + '" class="' + (DBF.stage === k ? "is-on" : "") + '">' + l + "</button>").join("");
  DB.exportWhat = fmt(sm.total) + " website" + (sm.total === 1 ? "" : "s") + " matching the filters";
  if (!d.rows.length) {
    $("#dbTbl").innerHTML = d.total || DBF.q || DBF.country || DBF.stage || DBF.niches.length || DBF.price_min || DBF.price_max
      ? '<div class="empty"><strong>Nothing matches</strong><p>Try fewer filters.</p><button class="ctl" data-dbclear>Clear filters</button></div>'
      : '<div class="empty"><strong>Your website database is empty</strong><p>Import the Excel file you use today - every sheet is read, and the columns are found by their names. Websites Almo contacts are added here automatically.</p><label class="ctl ctl--primary" style="margin-top:10px">' + icon("upload") + 'Import Excel or CSV<input type="file" accept=".xlsx,.xlsm,.csv,.txt" hidden onchange="window.__importDB(this)"></label></div>';
    $("#dbPager").innerHTML = ""; renderBulk(); return;
  }
  const SORTABLE = ["domain", "country", "email", "price", "sponsored", "link", "dr", "traffic", "status"];
  const th = ([key, label, cls, tip]) => SORTABLE.includes(key) ? '<th class="sortable ' + (cls || "") + '" data-sort="' + key + '"' + (tip ? ' title="' + esc(tip) + '"' : "") + (DBF.sort === key ? ' aria-sort="' + (DBF.dir === "asc" ? "ascending" : "descending") + '"' : "") + ">" + label + '<span class="arr">' + (DBF.sort === key ? (DBF.dir === "asc" ? "↑" : "↓") : "") + "</span></th>" : '<th class="' + (cls || "") + '"' + (tip ? ' title="' + esc(tip) + '"' : "") + ">" + label + "</th>";
  const allOn = DB.rows.every((r) => DB.sel.has(r.id));
  $("#dbTbl").innerHTML = '<table class="dbt"><thead><tr><th class="cb sticky"><input type="checkbox" id="selAll"' + (allOn ? " checked" : "") + ' aria-label="Select all"></th>' + COLS.map(th).join("") + "</tr></thead><tbody>" +
    d.rows.map((r) => '<tr data-site="' + r.id + '"' + (DB.sel.has(r.id) ? ' class="sel"' : "") + '><td class="cb sticky"><input type="checkbox" data-sel="' + r.id + '"' + (DB.sel.has(r.id) ? " checked" : "") + ' aria-label="Select"></td>' +
      '<td class="site l sticky2"><span class="sn">' + fav(r.domain) + '<span class="dn">' + esc(r.domain) + "</span></span></td>" +
      '<td class="l muted">' + (esc(r.country) || '<span class="unk">–</span>') + "</td>" + emailCell(r.email) +
      '<td class="num strong">' + eur(r.price) + "</td>" + ["casino", "loan", "crypto", "adult"].map((k) => "<td>" + topicCell(r, k) + "</td>").join("") +
      "<td>" + tagCell(r.sponsored_tag) + "</td><td>" + linkIns(r.link_insertion) + '</td><td class="muted">' + numCell(r.dr) + '</td><td class="muted">' + numCell(r.traffic) + '</td><td class="l">' + (r.status === "in_db" ? '<span class="unk">Not contacted</span>' : pill(r.status, d.statuses)) + "</tr>").join("") + "</tbody></table>";
  const from = d.page * d.per + 1, to = Math.min(d.total, from + d.rows.length - 1);
  $("#dbPager").innerHTML = d.total <= d.rows.length ? ('<span class="small">' + fmt(d.total) + " website" + (d.total === 1 ? "" : "s") + "</span>") : ('<span class="small">' + fmt(from) + "–" + fmt(to) + " of " + fmt(d.total) + '</span><span style="flex:1"></span><button class="ctl ctl--tiny" data-page="-1"' + (d.page ? "" : " disabled") + '>Previous</button><button class="ctl ctl--tiny" data-page="1"' + (to < d.total ? "" : " disabled") + ">Next</button>");
  renderBulk(); edgeHints();
}
function edgeHints() {
  const w = $("#dbTbl"); if (!w) return;
  w.classList.toggle("scrolled", w.scrollLeft > 4);
  w.classList.toggle("more", w.scrollLeft + w.clientWidth < w.scrollWidth - 4);
}
window.addEventListener("resize", edgeHints);
function renderBulk() {
  const b = $("#bulk"); if (!b) return;
  const n = DB.all ? DB.total : DB.sel.size;
  if (!n) { b.classList.remove("on"); return; }
  b.innerHTML = "<b>" + fmt(n) + "</b>&nbsp;selected" + (!DB.all && DB.sel.size >= DB.rows.length && DB.total > DB.rows.length ? '<button class="linkbtn" data-bulk="all">Select all ' + fmt(DB.total) + "</button>" : "") +
    '<span class="sep"></span><button class="ctl ctl--tiny ctl--primary" data-bulk="ask" title="Send your pitch to the ones Almo hasn\'t written to yet">Ask for prices</button><button class="ctl ctl--tiny" data-bulk="export">Export</button><button class="ctl ctl--tiny ctl--danger" data-bulk="remove">Remove</button><button class="ctl ctl--tiny ctl--icon" data-bulk="clear" title="Clear selection">' + icon("close") + "</button>";
  b.classList.add("on");
}
async function bulkDB(action) {
  if (action === "clear") { DB.sel.clear(); DB.all = false; loadDB(); return; }
  if (action === "all") { DB.all = true; renderBulk(); return; }
  const body = DB.all ? { all: true, filters: Object.fromEntries(new URLSearchParams(dbQuery())) } : { ids: [...DB.sel] };
  if (action === "export") {
    openExport(DB.all ? "db=1&" + dbQuery() : "ids=" + [...DB.sel].join(","), fmt(DB.all ? DB.total : DB.sel.size) + " selected websites");
    return;
  }
  const n = DB.all ? DB.total : DB.sel.size;
  if (action === "remove" && !confirm("Remove " + n + " website" + (n === 1 ? "" : "s") + " from the database?")) return;
  body.action = action;
  try {
    const r = await api("/api/db/bulk", { body });
    toast(action === "ask" ? (r.count ? r.count + " website" + (r.count === 1 ? "" : "s") + " queued - Almo will write to them" : "All of those were already contacted") : r.count + " removed");
    DB.sel.clear(); DB.all = false; loadDB(); refresh();
  } catch (e) { toast(e.message); }
}
async function importDB(file) {
  const fd = new FormData(); fd.append("file", file);
  toast("Reading " + file.name + "…", 8000);
  try {
    const p = await api("/api/db/import?preview=1", { body: fd });
    const sheets = p.sheets.filter((s) => s.rows).map((s) => (s.name ? s.name + " " : "") + "(" + s.rows + ")").join(", ");
    if (!p.new && !p.updated) { toast("Nothing new in " + file.name + " - all " + fmt(p.unchanged) + " websites are already in the database", 5000); return; }
    if (!confirm("Import " + file.name + "?\n\n" + fmt(p.new) + " new websites\n" + fmt(p.updated) + " existing ones get missing details filled in\n" + fmt(p.unchanged) + " already up to date\n\nSheets: " + sheets + "\n\nNothing Almo collected is overwritten.")) return;
    const fd2 = new FormData(); fd2.append("file", file);
    const r = await api("/api/db/import", { body: fd2 });
    toast("Imported " + fmt(r.new) + " new, updated " + fmt(r.updated), 4000);
    DBF.page = 0; loadDB(); refresh();
  } catch (e) { toast(e.message, 6000); }
}
window.__importDB = (input) => { if (input.files[0]) importDB(input.files[0]); input.value = ""; };

/* ------------------------------------------------------------------ site drawer */
async function openSite(id, quiet) {
  let d;
  try { d = await api("/api/sites/" + id); } catch (e) { if (!quiet) toast(e.message); return; }
  S.drawer = id;
  const s = d.site, dr = $("#drawer"), edit = !!S.drawerEdit;
  const has = (v) => v && !/^unknown$/i.test(v);
  let primary = "";
  if (s.status === "in_db") primary = '<button class="ctl ctl--primary" data-sa="ask">' + icon("outreach") + "Ask for prices</button>";
  else if (["error", "no_email", "bounced"].includes(s.status)) primary = '<button class="ctl ctl--primary" data-sa="retry">Check again</button>';
  else if (s.status === "not_fit") primary = '<button class="ctl ctl--primary" data-sa="send_now">Pitch anyway</button>';
  else if (s.replied_at && !["complete", "declined"].includes(s.status) && !s.draft) primary = '<button class="ctl ctl--primary" data-sa="complete">Mark as done</button><button class="ctl" data-sa="reread">Read reply again</button>';
  const fact = (label, v, cls) => '<div class="fact"><div class="label">' + label + '</div><div class="fv ' + (cls || "") + '">' + v + "</div></div>";
  const TERMS = ["price", "special_price", "link_insertion", "casino", "loan", "crypto", "adult", "sponsored_tag", "dr", "traffic"];
  const anyTerms = TERMS.some((k) => has(s[k]));
  const facts = !anyTerms ? '<p class="small notes-empty">No terms yet - they fill in when the website replies, or add them with Edit.</p>'
    : '<div class="facts">' + fact("Price", eur(s.price)) + fact("Special topics", eur(s.special_price)) + fact("Link insertion", linkIns(s.link_insertion)) + fact("DR", numCell(s.dr)) + fact("Traffic", numCell(s.traffic)) + "</div>" +
      '<div class="facts">' + [["Casino", "casino"], ["Loans", "loan"], ["Crypto", "crypto"], ["Adult", "adult"]].map(([l, k]) => fact(l, topicCell(s, k))).join("") + fact("Sponsored", tagCell(s.sponsored_tag)) + "</div>";
  const topics = "";
  const inp = (label, key, ph) => '<div class="fld"><span class="label">' + label + '</span><input data-f="' + key + '" value="' + esc(has(s[key]) ? s[key] : "") + '" placeholder="' + (ph || "–") + '"></div>';
  const editForm = '<div class="form-grid compact">' + inp("Price €", "price", "€") + inp("Special topics €", "special_price", "€") + inp("Link insertion", "link_insertion", "Yes, No or €") + inp("Sponsored tag", "sponsored_tag", "Yes or No") + inp("Casino", "casino", "Yes, No or €") + inp("Loans", "loan", "Yes, No or €") + inp("Crypto", "crypto", "Yes, No or €") + inp("Adult", "adult", "Yes, No or €") + inp("Country", "country") + inp("DR", "dr") + inp("Traffic", "traffic") +
    '<div class="fld full"><span class="label">Notes</span><textarea data-f="requirements" style="min-height:80px">' + esc(s.requirements) + '</textarea></div></div><div style="display:flex;gap:8px;margin-top:14px"><button class="ctl ctl--primary" data-sa="save">Save</button><button class="ctl" data-sa="cancel_edit">Cancel</button></div>';
  const when = (ts) => new Date(ts * 1000).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const lastIn = d.thread.filter((m) => m.direction === "in" && m.kind === "reply").slice(-1)[0];
  const thread = d.thread.length ? d.thread.slice().reverse().map((m, i) => '<details class="msg ' + m.direction + '"' + (i === 0 || m.direction === "in" ? " open" : "") + '><summary class="mh"><span><b>' + (m.direction === "out" ? "You" : esc(m.from_addr)) + '</b><span class="tag">' + esc({ pitch: "Pitch", reply: "Reply", followup: "Follow-up", nudge: "Reminder", bounce: "Bounce" }[m.kind] || m.kind) + "</span>" + (m.test ? '<span class="tag">Test</span>' : "") + "</span><span>" + new Date(m.ts * 1000).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) + '</span></summary><div class="small" style="margin:8px 0 6px">' + esc(m.subject) + '</div><div class="mb">' + esc(m.body) + "</div></details>").join("") : '<p class="small">Almo hasn\'t written to this website yet.</p>';
  dr.innerHTML = '<div class="drawer-head"><div class="grow"><h2 class="pagetitle dtitle">' + fav(s.domain) + esc(s.domain) + '</h2><div class="dsub">' + pill(s.status, d.statuses) + (s.country ? '<span class="muted">' + esc(s.country) + "</span>" : "") + '<a href="https://' + esc(s.domain) + '" target="_blank" rel="noopener">Open website ↗</a></div></div><button class="ctl ctl--icon" data-close-drawer aria-label="Close">' + icon("close") + "</button></div>" +
    '<div class="drawer-body">' + (s.note ? '<div class="banner' + (["bounced", "error"].includes(s.status) ? " bad" : "") + '">' + icon("info") + '<div class="grow">' + esc(s.note) + "</div></div>" : "") +
    (primary ? '<div class="dactions">' + primary + "</div>" : "") +
    (s.draft ? '<section><div class="head"><h3 class="sec">Follow-up ready to send</h3></div>' + (lastIn ? '<div class="msg in quoted"><div class="mh"><span><b>' + esc(lastIn.from_addr) + '</b><span class="tag">Their reply</span></span><span>' + when(lastIn.ts) + '</span></div><div class="mb">' + esc(lastIn.body) + "</div></div>" : "") +
      '<div class="fld"><textarea id="draftIn" style="min-height:150px">' + esc(s.draft) + '</textarea></div><div style="margin-top:12px"><button class="ctl ctl--primary" data-sa="send_draft">Send follow-up</button></div></section>' : "") +
    '<section><div class="head"><h3 class="sec">Terms</h3>' + (edit ? "" : '<button class="ctl ctl--tiny" data-sa="edit">Edit</button>') + "</div>" + (edit ? editForm : facts + topics + (s.requirements ? '<p class="notes">' + esc(s.requirements) + "</p>" : "")) + "</section>" +
    '<section><div class="head"><h3 class="sec">Contact</h3></div><div class="inline"><div class="fld" style="flex:1"><input id="emailIn" value="' + esc(s.email) + '" placeholder="Add an email address"></div><button class="ctl" data-sa="set_email">Save email</button>' + (s.email ? '<button class="ctl ctl--icon" data-copy="' + esc(s.email) + '" title="Copy email">' + icon("copy") + "</button>" : "") + "</div>" +
    (s.emails.length > 1 ? '<p class="small" style="margin:10px 0 0">Also found: ' + s.emails.slice(1, 6).map(esc).join(", ") + "</p>" : "") + (s.fit_reason ? '<p class="small" style="margin:6px 0 0">Site check: ' + esc(s.fit_reason) + "</p>" : "") + "</section>" +
    '<section><div class="head"><h3 class="sec">Emails' + (d.thread.length ? ' <span class="count-inline">' + d.thread.length + "</span>" : "") + "</h3></div>" + thread + "</section>" +
    '<section class="dfoot"><button class="linkbtn danger" data-sa="remove">Remove from Almo</button></section></div>';
  if (!quiet) { dr.classList.add("open"); $("#scrim").classList.add("open"); dr.setAttribute("aria-hidden", "false"); dr.querySelector(".drawer-body").scrollTop = 0; }
  $$("input,textarea", dr).forEach((el) => { el.onfocus = () => (S.drawerEditing = true); });
}
function closeDrawer() {
  S.drawer = null; S.drawerEditing = false; S.drawerEdit = false;
  $("#drawer").classList.remove("open"); $("#drawer").setAttribute("aria-hidden", "true");
  if (!$("#addModal").classList.contains("open")) $("#scrim").classList.remove("open");
}
async function siteAction(action) {
  const id = S.drawer, dr = $("#drawer");
  if (action === "edit" || action === "cancel_edit") { S.drawerEdit = action === "edit"; S.drawerEditing = S.drawerEdit; openSite(id, true); return; }
  const body = { action };
  if (action === "remove" && !confirm("Remove this website from Almo? Its emails stay in your mailbox.")) return;
  if (action === "save") { body.fields = {}; $$("[data-f]", dr).forEach((el) => (body.fields[el.dataset.f] = el.value.trim())); }
  if (action === "send_draft") body.body = ($("#draftIn") || {}).value;
  if (action === "set_email") body.email = $("#emailIn").value;
  try {
    await api("/api/sites/" + id + "/action", { body });
    toast({ save: "Saved", send_draft: "Follow-up sent", remove: "Removed", retry: "Checking again", complete: "Marked as done", reread: "Reading the reply again…", set_email: "Email updated", send_now: "Queued for sending", ask: "Queued - Almo will write to them" }[action] || "Done");
    S.drawerEditing = false; S.drawerEdit = false;
    if (action === "remove") closeDrawer(); else openSite(id, true);
    if (S.route === "database") loadDB();
    refresh();
  } catch (e) { toast(e.message, 5000); }
}

/* ------------------------------------------------------------------ pitch */
async function renderPitch() {
  const d = S.data, v = $("#view");
  const camp = d.campaigns.find((c) => c.id === S.campaign) || d.campaigns[0];
  let pitches;
  try { pitches = (await api("/api/campaigns/" + camp.id + "/pitches")).pitches; } catch (e) { toast(e.message); return; }
  if (S.route !== "pitch") return;
  let cur = pitches.find((p) => p.id === S.pitch) || pitches[0];
  S.pitch = cur.id;
  const rate = (p) => (p.reply_rate == null ? "–" : p.reply_rate + "%");
  const best = pitches.filter((p) => p.sent >= 20).sort((a, b) => b.reply_rate - a.reply_rate)[0];
  const stats = pitches.length > 1 || cur.sent ? '<div class="card abcard"><div class="head" style="margin-bottom:10px"><h2 class="sec">A/B results</h2><span class="small">' + (pitches.filter((p) => p.active).length > 1 ? "Active pitches take turns, so each gets the same share" : "Add a second pitch to compare") + "</span></div>" +
    '<table class="abt"><thead><tr><th class="l">Pitch</th><th class="l">Subject</th><th>Sent</th><th>Replies</th><th>Reply rate</th><th>Prices</th></tr></thead><tbody>' +
    pitches.map((p) => '<tr data-pv="' + p.id + '" class="' + (p.id === cur.id ? "cur" : "") + '"><td class="l"><span class="vlabel' + (p.active ? "" : " off") + '">' + esc(p.label) + "</span>" + (best && best.id === p.id && pitches.length > 1 ? '<span class="tag good">Best</span>' : "") + (p.active ? "" : '<span class="tag">Off</span>') + '</td><td class="l muted subj">' + esc(p.subject) + "</td><td>" + fmt(p.sent) + "</td><td>" + fmt(p.replies) + "</td><td><b>" + rate(p) + "</b></td><td>" + fmt(p.prices) + "</td></tr>").join("") +
    "</tbody></table>" + (pitches.length > 1 && !best ? '<p class="small" style="margin:10px 0 0">Wait for about 20 sends per pitch before picking a winner.</p>' : "") + "</div>" : "";
  v.innerHTML = (S.campaign ? "" : '<div class="banner sky">' + icon("info") + '<div class="grow">Editing the <b>' + esc(camp.name) + "</b> campaign. Pick a campaign on the left to edit its own pitch.</div></div>") + stats +
    '<div class="pitch-layout"><div>' +
    '<div class="card"><div class="fld full" style="margin-bottom:18px"><span class="label">Campaign name</span><input id="pName" value="' + esc(camp.name) + '"></div>' +
    '<div class="vtabs">' + pitches.map((p) => '<button data-pv="' + p.id + '" class="' + (p.id === cur.id ? "is-on" : "") + (p.active ? "" : " off") + '">Pitch ' + esc(p.label) + "</button>").join("") + '<button class="vadd" id="pAdd" title="Add another version to test against">' + icon("plus") + "A/B version</button></div>" +
    '<div class="form-grid"><div class="fld full"><span class="label">Subject</span><input id="pSubj" value="' + esc(cur.subject) + '"></div>' +
    '<div class="fld full"><span class="label">Message</span><textarea id="pBody" style="min-height:300px">' + esc(cur.body) + '</textarea><span class="hint">Write in English. It\'s translated for each site, and the sending mailbox\'s signature is added.</span><div class="vars"><span class="label">Insert</span><code data-ins="{domain}" title="Replaced with the website, e.g. delfi.lv">{domain}</code></div></div></div>' +
    '<div style="display:flex;gap:10px;margin-top:18px;flex-wrap:wrap"><button class="ctl ctl--primary" id="pSave">Save pitch ' + esc(cur.label) + "</button>" +
    (pitches.length > 1 ? '<button class="ctl" id="pToggle">' + (cur.active ? "Stop sending pitch " + esc(cur.label) : "Start sending pitch " + esc(cur.label)) + "</button>" + (cur.sent ? "" : '<button class="ctl ctl--danger" id="pDelV">Delete pitch ' + esc(cur.label) + "</button>") : "") +
    '<span style="flex:1"></span>' + (d.campaigns.length > 1 ? '<button class="linkbtn danger" id="pDel">Delete campaign</button>' : "") + "</div></div></div>" +
    '<div><div class="head" style="margin-bottom:12px"><div><h2 class="sec">Preview · pitch ' + esc(cur.label) + '</h2></div><div class="inline"><input class="search" style="min-width:150px;padding-left:11px;background-image:none" id="pvDomain" value="delfi.lv" placeholder="Preview for website…" aria-label="Preview for website"><select class="ctl" id="pvLang"><option value="">English</option><option value="lv">Latvian</option><option value="de">German</option><option value="lt">Lithuanian</option><option value="et">Estonian</option><option value="nl">Dutch</option><option value="pl">Polish</option><option value="el">Greek</option></select></div></div><div class="preview"><div class="ph" id="pvSubj">…</div><iframe id="pvFrame" title="Preview"></iframe></div></div></div>';
  const preview = async () => {
    $("#pvSubj").innerHTML = '<span class="spin"></span>';
    try {
      const p = await api("/api/preview/" + camp.id + "?pitch=" + cur.id + "&domain=" + encodeURIComponent($("#pvDomain").value) + "&lang=" + $("#pvLang").value);
      $("#pvSubj").textContent = "Subject: " + p.subject; $("#pvFrame").srcdoc = p.html;
    } catch (e) { $("#pvSubj").textContent = e.message; }
  };
  const dirty = () => $("#pSubj").value !== cur.subject || $("#pBody").value !== cur.body;
  const save = async (quiet) => {
    if ($("#pName").value.trim() !== camp.name) await api("/api/campaigns/" + camp.id, { method: "PUT", body: { name: $("#pName").value } });
    if (dirty()) await api("/api/pitches/" + cur.id, { method: "PUT", body: { subject: $("#pSubj").value, body: $("#pBody").value } });
    if (!quiet) toast("Pitch " + cur.label + " saved");
  };
  $("#pSave").onclick = async () => { try { await save(); await refresh(); renderPitch(); } catch (e) { toast(e.message); } };
  $$("[data-pv]", v).forEach((b) => (b.onclick = async () => {
    const id = Number(b.dataset.pv); if (id === cur.id) return;
    if (dirty() && confirm("Save the changes to pitch " + cur.label + " first?")) { try { await save(true); } catch (e) { toast(e.message); return; } }
    S.pitch = id; renderPitch();
  }));
  $("#pAdd").onclick = async () => {
    try { if (dirty()) await save(true); const r = await api("/api/campaigns/" + camp.id + "/pitches", { body: { copy: cur.id } }); S.pitch = r.id; toast("Pitch " + r.pitches.find((p) => p.id === r.id).label + " added - change it, then save"); renderPitch(); } catch (e) { toast(e.message); }
  };
  if ($("#pToggle")) $("#pToggle").onclick = async () => { try { await api("/api/pitches/" + cur.id, { method: "PUT", body: { active: !cur.active } }); toast(cur.active ? "Pitch " + cur.label + " is off - it won't be sent any more" : "Pitch " + cur.label + " is on"); renderPitch(); } catch (e) { toast(e.message, 5000); } };
  if ($("#pDelV")) $("#pDelV").onclick = async () => { if (!confirm("Delete pitch " + cur.label + "?")) return; try { await api("/api/pitches/" + cur.id, { method: "DELETE" }); S.pitch = null; toast("Pitch deleted"); renderPitch(); } catch (e) { toast(e.message, 5000); } };
  if ($("#pDel")) $("#pDel").onclick = async () => {
    if (!confirm("Delete this campaign? Its websites move to the first campaign.")) return;
    try { await api("/api/campaigns/" + camp.id, { method: "DELETE" }); S.campaign = 0; S.pitch = null; store.set("almo-campaign", "0"); toast("Campaign deleted"); await refresh(); renderPitch(); } catch (e) { toast(e.message); }
  };
  $$("[data-ins]").forEach((c) => (c.onclick = () => { const t = $("#pBody"); const p = t.selectionStart; t.value = t.value.slice(0, p) + c.dataset.ins + t.value.slice(t.selectionEnd); t.focus(); }));
  const grow = () => { const t = $("#pBody"); t.style.height = "auto"; t.style.height = Math.max(300, t.scrollHeight + 2) + "px"; };
  $("#pBody").addEventListener("input", grow); grow();
  $("#pvLang").onchange = preview; $("#pvDomain").onchange = preview;
  preview();
}

/* ------------------------------------------------------------------ settings */
function renderSettings() {
  const st = S.data.settings, v = $("#view");
  const sw = (key, title) => '<div class="switch' + (st[key] ? " on" : "") + '" data-sw="' + key + '"><div class="txt"><b>' + title + '</b></div><span class="toggle"></span></div>';
  const num = (key, label, hint) => '<div class="fld"><span class="label">' + label + '</span><input data-k="' + key + '" value="' + esc(st[key]) + '" inputmode="numeric">' + (hint ? '<span class="hint">' + hint + "</span>" : "") + "</div>";
  const help = { Gmail: "https://myaccount.google.com/apppasswords", Fastmail: "https://app.fastmail.com/settings/security/apppasswords" };
  const card = (id, title, sub, body) => '<div class="card" id="' + id + '"><div class="card-head"><div><h2 class="sec">' + title + "</h2>" + (sub ? "<p>" + sub + "</p>" : "") + "</div></div>" + body + "</div>";
  v.innerHTML = '<div style="max-width:760px">' +
    card("account", "Mailboxes", "Pitches are shared evenly between active mailboxes, each within its own daily limit. Replies and follow-ups always stay in the mailbox that started the conversation.",
      '<div id="boxes">' + boxList(st) + "</div>") +
    card("ai", "AI", "Reads websites and replies, pulls out the prices and writes follow-ups. Pick one.",
      '<div class="seg" id="aiprov" style="margin-bottom:18px">' + [["anthropic", "Claude"], ["openai", "OpenAI"], ["gemini", "Gemini"]].map(([k, l]) => '<button data-aip="' + k + '" class="' + ((st.ai_provider || "anthropic") === k ? "is-on" : "") + '">' + l + "</button>").join("") + "</div>" +
      (() => { const P = { anthropic: ["Anthropic API key", "anthropic_key", "sk-ant-…", "https://console.anthropic.com/settings/keys"], openai: ["OpenAI API key", "openai_key", "sk-…", "https://platform.openai.com/api-keys"], gemini: ["Gemini API key", "gemini_key", "AIza…", "https://aistudio.google.com/apikey"] }[st.ai_provider || "anthropic"];
        return '<div class="fld"><span class="label">' + P[0] + '</span><input data-k="' + P[1] + '" type="password" placeholder="' + (st[P[1] + "_set"] ? "•••••••••••• saved" : P[2]) + '"><span class="hint"><a href="' + P[3] + '" target="_blank" rel="noopener">Get one ↗</a></span></div>'; })() +
      '<div style="margin-top:16px;display:flex;gap:10px;align-items:center"><button class="ctl" data-test="ai">Save and test</button><span class="result" id="r-ai"></span></div>') +
    card("sending", "Sending", "Start with Test: every email goes to the mailbox that sends it, so you can check how it looks.",
      '<div class="modes">' + [["off", "Off", "Nothing is sent."], ["test", "Test", "Everything goes to you."], ["live", "Live", "Sends to the websites."]]
        .map(([k, t, p]) => '<button class="mode' + (st.send_mode === k ? " is-on" : "") + '" data-mode="' + k + '"><b><span class="dot' + (k === "live" ? " on" : k === "test" ? " warn" : "") + '"></span>' + t + "</b><p>" + p + "</p></button>").join("") + "</div>") +
    '<details class="card" id="auto"><summary class="sec" style="cursor:pointer">Advanced</summary><div style="margin-top:14px">' +
      sw("check_sites", "Skip sites that don't publish articles") + sw("translate", "Translate the pitch to the site's language") + sw("auto_followup", "Reply automatically when details are missing") +
      '<div class="form-grid" style="margin-top:18px">' + num("daily_limit", "Default daily limit", "For new mailboxes") + num("nudge_days", "Reminder after (days)", "0 = no reminder") +
      '<div class="fld"><span class="label">Pause between emails (sec)</span><div class="inline"><input data-k="gap_min" value="' + st.gap_min + '"><span class="dim">–</span><input data-k="gap_max" value="' + st.gap_max + '"></div></div>' +
      '<div class="fld"><span class="label">Sending hours</span><div class="inline"><input data-k="work_start" value="' + st.work_start + '"><span class="dim">–</span><input data-k="work_end" value="' + st.work_end + '"></div></div>' +
      num("inbox_every_min", "Check inbox every (min)") + '<div class="fld"><span class="label">Company</span><input data-k="company" value="' + esc(st.company) + '"></div>' +
      '<div class="fld full"><span class="label">Results Excel file</span><input data-k="results_path" value="' + esc(st.results_path) + '" placeholder="~/Desktop/Almo results.xlsx"><span class="hint">Kept up to date automatically. Empty = off.</span></div>' +
      '<div class="fld full"><span class="label">Database</span><div class="dbinfo"><b>' + esc(st.database.kind) + '</b><span class="muted">' + esc(st.database.where) + '</span></div><span class="hint">To use a shared PostgreSQL server, put its address in database_url.txt next to the app and restart. See the README.</span></div>' + '<div class="fld"><span class="label">AI model (replies)</span><input data-k="' + (st.ai_provider || "anthropic") + '_smart" value="' + esc(st[(st.ai_provider || "anthropic") + "_smart"]) + '"></div><div class="fld"><span class="label">AI model (site checks)</span><input data-k="' + (st.ai_provider || "anthropic") + '_fast" value="' + esc(st[(st.ai_provider || "anthropic") + "_fast"]) + '"></div></div></div></details>' +
    '<div class="savebar"><span class="small" id="saveNote"></span><button class="ctl ctl--primary" id="saveAll">Save</button></div></div>';
  const hash = location.hash.split("#")[2];
  if (hash && $("#" + hash)) setTimeout(() => $("#" + hash).scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  $$("[data-k]", v).forEach((el) => (el.oninput = () => { markDirty(); }));
}
/* mailboxes */
const BOX_HELP = { Gmail: "Google account → Security → App passwords", Fastmail: "Settings → Privacy & Security → App passwords", Zoho: "Zoho account → Security → App passwords. Servers: Zoho Mail → Settings → Mail accounts → IMAP" };
function boxList(st) {
  const w = (S.data && S.data.worker && S.data.worker.mailboxes) || [];
  const by = Object.fromEntries(w.map((x) => [x.id, x]));
  const rows = (st.mailboxes || []).map((b) => {
    const ws = by[b.id] || {}, err = ws.send_error || ws.inbox_error;
    if (S.boxEdit === b.id) return boxForm(st, b);
    return '<div class="box' + (b.active ? "" : " off") + '"><span class="dot ' + (err ? "bad" : !b.ready ? "warn" : b.active ? "on" : "") + '"></span>' +
      '<div class="grow"><b>' + esc(b.email) + '</b><span class="muted">' + esc(b.provider) + (b.sender_name ? " · " + esc(b.sender_name) : "") + (b.active ? "" : " · paused") + (!b.ready ? " · needs " + (b.password_set ? "a sender name" : "an app password") : "") + "</span>" +
      (err ? '<span class="bad small">' + esc(err) + "</span>" : "") + "</div>" +
      '<div class="today"><b>' + fmt(ws.sent_today || 0) + "</b><span>/ " + fmt(b.daily_limit) + " today</span></div>" +
      '<span class="result" id="r-box-' + b.id + '"></span>' +
      '<button class="ctl ctl--tiny" data-box="test" data-id="' + b.id + '">Test</button><button class="ctl ctl--tiny" data-box="toggle" data-id="' + b.id + '">' + (b.active ? "Pause" : "Resume") + '</button><button class="ctl ctl--tiny" data-box="edit" data-id="' + b.id + '">Edit</button><button class="ctl ctl--tiny ctl--icon ctl--danger" data-box="remove" data-id="' + b.id + '" title="Remove">' + icon("close") + "</button></div>";
  }).join("");
  const empty = !(st.mailboxes || []).length ? '<p class="small" style="margin:0 0 14px">No mailbox yet. Add the one Almo should send from - you can add more any time.</p>' : "";
  return empty + rows + (S.boxEdit === "new" ? boxForm(st, null) : '<button class="ctl" data-box="new" style="margin-top:' + (rows ? 14 : 0) + 'px">' + icon("plus") + "Add mailbox</button>");
}
function boxForm(st, b) {
  const prov = S.boxProv || (b && b.provider) || "Gmail", P = st.providers[prov];
  const v = (k, d) => esc(b && b[k] != null && b[k] !== "" ? b[k] : d == null ? "" : d);
  const servers = !P || P.editable;
  const def = P ? { smtp_host: P.smtp[0], smtp_port: P.smtp[1], imap_host: P.imap[0], imap_port: P.imap[1] } : { smtp_port: 465, imap_port: 993 };
  const sv = (k) => (b && b.provider === prov && b[k] ? esc(b[k]) : esc(def[k] == null ? "" : def[k]));
  return '<div class="boxform" id="boxForm" data-id="' + (b ? b.id : "") + '"><div class="seg" id="boxProv" style="margin-bottom:16px">' + ["Gmail", "Fastmail", "Zoho", "Other"].map((p) => '<button data-bp="' + p + '" class="' + (prov === p ? "is-on" : "") + '">' + p + "</button>").join("") + "</div>" +
    '<div class="form-grid"><div class="fld"><span class="label">Email address</span><input data-b="email" type="email" value="' + v("email") + '" placeholder="name@uprankd.com"></div>' +
    '<div class="fld"><span class="label">App password</span><input data-b="password" type="password" placeholder="' + (b && b.password_set ? "Saved - leave empty to keep" : "xxxx xxxx xxxx xxxx") + '">' + (P ? '<span class="hint"><a href="' + P.help + '" target="_blank" rel="noopener">Get one ↗</a> ' + esc(BOX_HELP[prov] || "") + "</span>" : '<span class="hint">Not your normal password</span>') + "</div>" +
    '<div class="fld"><span class="label">Sender name</span><input data-b="sender_name" value="' + v("sender_name", st.sender_name) + '" placeholder="Kristiāns Safronovs"></div>' +
    '<div class="fld"><span class="label">Job title</span><input data-b="sender_title" value="' + v("sender_title", st.sender_title || "Outreach Specialist") + '"></div>' +
    '<div class="fld"><span class="label">Max emails per day</span><input data-b="daily_limit" inputmode="numeric" value="' + v("daily_limit", st.daily_limit) + '"><span class="hint">New mailboxes: start at 20–30 and raise slowly</span></div><div></div>' +
    (servers ? '<div class="fld"><span class="label">SMTP server</span><input data-b="smtp_host" value="' + sv("smtp_host") + '"></div><div class="fld"><span class="label">SMTP port</span><input data-b="smtp_port" inputmode="numeric" value="' + sv("smtp_port") + '"></div>' +
      '<div class="fld"><span class="label">IMAP server</span><input data-b="imap_host" value="' + sv("imap_host") + '"></div><div class="fld"><span class="label">IMAP port</span><input data-b="imap_port" inputmode="numeric" value="' + sv("imap_port") + '"></div>' : "") +
    (prov === "Zoho" ? '<div class="fld full"><span class="hint">Paid Zoho accounts on your own domain use smtppro / imappro. For a zoho.com account (not EU), change .eu to .com.</span></div>' : "") +
    '</div><div style="margin-top:16px;display:flex;gap:10px;align-items:center"><button class="ctl ctl--primary" data-box="save">' + (b ? "Save" : "Add and test") + '</button><button class="ctl" data-box="cancel">Cancel</button><span class="result" id="r-boxform"></span></div></div>';
}
function rerenderBoxes() { const el = $("#boxes"); if (el) el.innerHTML = boxList(S.data.settings); }
async function boxAction(a, id, t) {
  if (a === "new") { S.boxEdit = "new"; S.boxProv = "Gmail"; rerenderBoxes(); setTimeout(() => $('[data-b="email"]') && $('[data-b="email"]').focus(), 30); return; }
  if (a === "edit") { S.boxEdit = id; S.boxProv = null; rerenderBoxes(); return; }
  if (a === "cancel") { S.boxEdit = null; S.boxProv = null; rerenderBoxes(); return; }
  const box = (S.data.settings.mailboxes || []).find((b) => b.id === id);
  if (a === "save") {
    const f = $("#boxForm"), body = { provider: S.boxProv || (box && box.provider) || "Gmail" };
    $$("[data-b]", f).forEach((el) => { if (el.dataset.b !== "password" || el.value) body[el.dataset.b] = el.value.trim(); });
    const editId = Number(f.dataset.id) || null;
    $("#r-boxform").innerHTML = '<span class="spin"></span> Saving…';
    try {
      const r = await api(editId ? "/api/mailboxes/" + editId : "/api/mailboxes", { method: editId ? "PUT" : "POST", body });
      S.data.settings.mailboxes = r.mailboxes; S.boxEdit = null; S.boxProv = null; rerenderBoxes();
      const newId = editId || r.id;
      toast(editId ? "Mailbox saved" : "Mailbox added - testing…");
      boxAction("test", newId);
      refresh();
    } catch (e) { $("#r-boxform").innerHTML = '<span class="bad">' + esc(e.message) + "</span>"; }
    return;
  }
  if (a === "test") {
    const out = $("#r-box-" + id); if (out) out.innerHTML = '<span class="spin"></span>';
    try {
      const r = await api("/api/test/email", { body: { id } });
      if (out) out.innerHTML = r.ok ? '<span class="good">✓ Connected</span>' : '<span class="bad">' + esc(r.error) + "</span>";
      if (!r.ok && !out) toast(r.error, 6000);
    } catch (e) { if (out) out.innerHTML = '<span class="bad">' + esc(e.message) + "</span>"; }
    return;
  }
  if (a === "toggle") {
    try { const r = await api("/api/mailboxes/" + id, { method: "PUT", body: { active: !box.active } }); S.data.settings.mailboxes = r.mailboxes; rerenderBoxes(); toast(box.active ? "Paused - it still answers its own conversations" : "Mailbox resumed"); refresh(); } catch (e) { toast(e.message); }
    return;
  }
  if (a === "remove") {
    if (!confirm("Remove " + box.email + " from Almo?\n\nNothing is deleted from the mailbox itself. Conversations it started will continue from another mailbox.")) return;
    try { const r = await api("/api/mailboxes/" + id, { method: "DELETE" }); S.data.settings.mailboxes = r.mailboxes; rerenderBoxes(); toast("Mailbox removed"); refresh(); } catch (e) { toast(e.message); }
  }
}

function markDirty() {
  S.settingsDirty = true;
  if ($("#saveNote")) $("#saveNote").textContent = "Unsaved changes";
  if ($(".savebar")) $(".savebar").classList.add("dirty");
}
function collectSettings() {
  const out = {};
  $$("[data-k]").forEach((el) => {
    let val = el.value;
    if (el.dataset.k === "results_path") val = val.trim();
    if (["email_password", "anthropic_key", "openai_key", "gemini_key"].includes(el.dataset.k) && !val) return;
    out[el.dataset.k] = val;
  });
  const prov = $("#prov .is-on"); if (prov) out.provider = prov.dataset.p;
  const aip = $("#aiprov .is-on"); if (aip) out.ai_provider = aip.dataset.aip;
  $$("[data-sw]").forEach((el) => (out[el.dataset.sw] = el.classList.contains("on")));
  return out;
}
async function saveSettings(quiet) {
  const r = await api("/api/settings", { body: collectSettings() });
  S.settingsDirty = false;
  if ($(".savebar")) $(".savebar").classList.remove("dirty");
  if (r.problems && r.problems.length) { toast("Check: " + r.problems.join(", "), 5000); return false; }
  S.data.settings = r.settings;
  if ($("#saveNote")) $("#saveNote").textContent = "Saved";
  $$('[data-k="email_password"],[data-k="anthropic_key"],[data-k="openai_key"],[data-k="gemini_key"]').forEach((el) => { if (el.value) { el.value = ""; el.placeholder = "•••••••••••• saved"; } });
  if (!quiet) toast("Settings saved");
  refresh();
  return true;
}

/* ------------------------------------------------------------------ export */
const EXP = { q: "", kind: store.get("almo-exp-kind") || "full" };
function openExport(q, what) {
  EXP.q = q || ""; EXP.what = what || "";
  $("#expWhat").textContent = EXP.what || (S.campaign ? "Websites in this campaign" : "All websites in outreach");
  $("#expMarkup").value = store.get("almo-markup") || "30";
  $("#expMargin").value = store.get("almo-margin") || "0";
  $("#expSpecial").checked = store.get("almo-exp-special") === "1";
  renderExport();
  $("#expModal").classList.add("open"); $("#scrim").classList.add("open");
  api("/api/export/count?" + EXP.q).then((c) => { EXP.count = c; renderExport(); }).catch(() => {});
}
function closeExport() { $("#expModal").classList.remove("open"); if (!S.drawer && !$("#addModal").classList.contains("open")) $("#scrim").classList.remove("open"); }
const clientPrice = (p, mu, mg) => Math.ceil(Math.round((p * (1 + mu / 100) + mg) * 1e6) / 1e6);
function renderExport() {
  $$("#expKind button").forEach((b) => b.classList.toggle("is-on", b.dataset.ek === EXP.kind));
  const client = EXP.kind === "client";
  $("#expClient").hidden = !client;
  $("#expFullNote").hidden = client;
  const mu = parseFloat(($("#expMarkup").value || "0").replace(",", ".")) || 0, mg = parseFloat(($("#expMargin").value || "0").replace(",", ".")) || 0;
  const c = EXP.count, ex = c && c.sample.length ? c.sample.slice(0, 3) : [{ domain: "example.lv", price: 100 }];
  $("#expExample").innerHTML = ex.map((r) => '<div class="exrow"><span>' + esc(r.domain) + '</span><span class="muted">€' + fmt(r.price) + '</span><span class="arrow">→</span><b>€' + fmt(clientPrice(Number(r.price), mu, mg)) + "</b></div>").join("");
  $("#expInfo").textContent = !c ? "" : client ? fmt(c.priced) + " of " + fmt(c.total) + " have a price and go in the list" : fmt(c.total) + " website" + (c.total === 1 ? "" : "s");
  $("#expGo").disabled = !!(c && (client ? !c.priced : !c.total));
}
function downloadExport() {
  const client = EXP.kind === "client";
  let url = "/api/export?" + EXP.q;
  if (client) {
    const mu = $("#expMarkup").value.replace(",", ".") || "0", mg = $("#expMargin").value.replace(",", ".") || "0";
    store.set("almo-markup", mu); store.set("almo-margin", mg); store.set("almo-exp-special", $("#expSpecial").checked ? "1" : "0");
    url += "&client=1&markup=" + encodeURIComponent(mu) + "&margin=" + encodeURIComponent(mg) + ($("#expSpecial").checked ? "&special=1" : "");
  }
  store.set("almo-exp-kind", EXP.kind);
  location.href = url; closeExport(); toast(client ? "Price list downloading" : "Export downloading");
}

/* ------------------------------------------------------------------ add websites */
function openAdd() {
  $("#addModal").classList.add("open"); $("#scrim").classList.add("open");
  setTimeout(() => $("#siteText").focus(), 60);
}
function closeAdd() { $("#addModal").classList.remove("open"); if (!S.drawer) $("#scrim").classList.remove("open"); }
async function previewAdd() {
  const text = $("#siteText").value;
  if (!text.trim()) { $("#parseNote").textContent = "Any format works."; $("#addGo").disabled = true; $("#addInfo").textContent = ""; return; }
  try {
    const p = await api("/api/sites", { body: { text, preview: true } });
    $("#parseNote").textContent = p.new.length + " new website" + (p.new.length === 1 ? "" : "s") + (p.known.length ? " · " + p.known.length + " already in the database, skipped" : "");
    $("#addGo").disabled = !p.new.length;
    $("#addGo").textContent = p.new.length ? "Start " + p.new.length + " website" + (p.new.length === 1 ? "" : "s") : "Start";
    const st = S.data.settings;
    const info = !st.running ? ["warn", "Almo is paused: sites are added, nothing happens until you resume."] : st.send_mode === "off" ? ["", "Sending is off: sites will be checked, nothing sent."] : st.send_mode === "test" ? ["", "Test mode: emails go to your own mailbox."] : ["warn", "Live: pitches go out to these websites automatically."];
    $("#addInfo").className = "grow " + info[0]; $("#addInfo").textContent = info[1];
  } catch (e) {}
}
async function loadFile(file) {
  const fd = new FormData(); fd.append("file", file);
  $("#parseNote").innerHTML = '<span class="spin"></span> Reading ' + esc(file.name);
  try {
    const r = await api("/api/upload", { body: fd });
    const cur = $("#siteText").value.trim();
    $("#siteText").value = (cur ? cur + "\n" : "") + r.text;
    previewAdd();
  } catch (e) { $("#parseNote").textContent = e.message; }
}

/* ------------------------------------------------------------------ router */
const TITLES = { overview: "Overview", database: "Website database", websites: "Outreach", attention: "Needs you", pitch: "Pitch email", settings: "Settings" };
function route() {
  if (/^#\/prices/.test(location.hash)) { DBF.stage = "priced"; saveDBF(); location.replace("#/database"); return; }
  if ($("#addModal").classList.contains("open")) closeAdd();
  if ($("#expModal").classList.contains("open")) closeExport();
  if (S.drawer) closeDrawer();
  const h = location.hash.replace(/^#\/?/, "");
  const [path, qs] = h.split("#")[0].split("?");
  S.route = TITLES[path] ? path : "overview";
  if (qs) { const f = new URLSearchParams(qs).get("f"); if (f) S.filter = Object.keys({ all: 1, progress: 1, waiting: 1, attention: 1, done: 1, closed: 1 }).includes(f) ? f : statusToTab(f); }
  $("#title").textContent = S.route === "overview" ? (S.data && S.campaign ? (S.data.campaigns.find((c) => c.id === S.campaign) || {}).name || "Overview" : "Overview") : TITLES[S.route];
  const subs = { overview: S.data ? fmt(S.data.funnel[0].value) + " websites in outreach" : "", database: "Every website we know, across all campaigns", websites: "Websites Almo is working on", attention: "Replies that need a look", pitch: "The email each website gets, with A/B versions", settings: "Mailboxes, AI and sending" };
  $("#subtitle").textContent = subs[S.route];
  $("#range").style.display = S.route === "overview" ? "" : "none";
  $("#exportBtn").hidden = ["pitch", "settings"].includes(S.route);
  $("#importBtn").hidden = S.route !== "database";
  renderNav();
  if (!S.data) return;
  if (S.route === "overview") renderOverview();
  else if (["websites", "attention"].includes(S.route)) { sitesShell(); loadSites(); }
  else if (S.route === "database") { if (S.prevRoute !== "database") resetDBF(); dbShell(); loadDB(); }
  else if (S.route === "pitch") renderPitch();
  else if (S.route === "settings") { S.boxEdit = null; S.boxProv = null; renderSettings(); }
  $(".content").scrollTop = 0;
  S.prevRoute = S.route;
}
function statusToTab(s) { for (const [k, v] of Object.entries({ progress: ["queued", "reading", "ready", "sending"], waiting: ["waiting", "followed_up"], attention: ["needs_you", "replied", "error"], done: ["complete"], closed: ["not_fit", "no_email", "declined", "no_reply", "bounced"] })) if (v.includes(s)) return k; return "all"; }

/* ------------------------------------------------------------------ events */
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-niche],[data-stage],[data-sort],[data-page],[data-sel],#selAll,[data-bulk],[data-dbclear],[data-copy]");
  if (!t || !t.closest("#view, #bulk, #drawer")) return;
  e.stopPropagation();
  if (t.dataset.copy) { copyText(t.dataset.copy).then(() => { toast("Copied " + t.dataset.copy); t.classList.add("done"); setTimeout(() => t.classList.remove("done"), 1200); }); return; }
  if (t.dataset.niche) { const k = t.dataset.niche, i = DBF.niches.indexOf(k); if (i < 0) DBF.niches.push(k); else DBF.niches.splice(i, 1); DBF.page = 0; saveDBF(); renderChips(); loadDB(); }
  else if (t.dataset.stage != null) { DBF.stage = t.dataset.stage; DBF.page = 0; saveDBF(); loadDB(); }
  else if (t.dataset.sort) { DBF.dir = DBF.sort === t.dataset.sort && DBF.dir === "desc" ? "asc" : "desc"; if (DBF.sort !== t.dataset.sort && ["domain", "country", "status", "email"].includes(t.dataset.sort)) DBF.dir = "asc"; DBF.sort = t.dataset.sort; DBF.page = 0; saveDBF(); loadDB(); }
  else if (t.dataset.page) { DBF.page = Math.max(0, DBF.page + Number(t.dataset.page)); loadDB(); window.scrollTo({ top: 0, behavior: "smooth" }); }
  else if (t.dataset.sel) { const id = Number(t.dataset.sel); DB.all = false; if (t.checked) DB.sel.add(id); else DB.sel.delete(id); t.closest("tr").classList.toggle("sel", t.checked); renderBulk(); }
  else if (t.id === "selAll") { DB.all = false; DB.rows.forEach((r) => (t.checked ? DB.sel.add(r.id) : DB.sel.delete(r.id))); loadDB(); }
  else if (t.dataset.bulk) bulkDB(t.dataset.bulk);
  else if (t.hasAttribute("data-dbclear")) { Object.assign(DBF, { q: "", country: "", stage: "", niches: [], price_min: "", price_max: "", page: 0 }); saveDBF(); dbShell(); loadDB(); }
}, true);
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { const q = $("#dbq") || $("#q"); if (q) { e.preventDefault(); q.focus(); } }
});
document.addEventListener("click", async (e) => {
  const t = e.target.closest("[data-go],[data-site],[data-f],[data-act],[data-sa],[data-close],[data-close-drawer],[data-mode],[data-box],[data-bp],[data-aip],[data-sw],[data-test],[data-c]");
  if (!t) { if (!e.target.closest("#campMenu")) $("#campMenu").classList.remove("open"); return; }
  if (t.dataset.go) { if (t.dataset.go === "add") openAdd(); else location.hash = t.dataset.go; return; }
  if (t.dataset.site) { openSite(Number(t.dataset.site)); return; }
  if (t.dataset.f && t.closest("#tabs")) { S.filter = t.dataset.f; loadSites(); return; }
  if (t.dataset.c != null && t.closest("#campList")) {
    S.campaign = Number(t.dataset.c); store.set("almo-campaign", String(S.campaign)); $("#campMenu").classList.remove("open");
    $("#exportBtn").href = "/api/export?" + campQ(); await refresh(); route(); return;
  }
  if (t.hasAttribute("data-close")) { closeAdd(); return; }
  if (t.hasAttribute("data-close-drawer")) { closeDrawer(); return; }
  if (t.dataset.sa) { siteAction(t.dataset.sa); return; }
  if (t.dataset.act) {
    const a = t.dataset.act;
    if (a === "resume") { await api("/api/run", { body: { running: true } }); refresh(); }
    if (a === "inbox") { await api("/api/inbox-now", { body: {} }); toast("Checking your inbox…"); setTimeout(refresh, 4000); }
    if (a === "retry_failed") { await api("/api/bulk", { body: { action: "retry_failed", campaign_id: S.campaign } }); toast("Checking failed websites again"); refresh(); }
    return;
  }
  if (t.dataset.mode) {
    const mode = t.dataset.mode;
    if (mode !== "off" && S.data.missing.length) { toast("First add " + S.data.missing.join(", ") + " below", 5000); return; }
    if (mode === "live" && !confirm("Go live? Pitches will be sent to the websites' real email addresses.")) return;
    if (S.settingsDirty) await saveSettings(true);
    await api("/api/settings", { body: { send_mode: mode } });
    toast({ off: "Sending is off", test: "Test mode on - emails go to you", live: "Live - Almo is sending" }[mode]);
    await refresh(); renderSettings(); return;
  }
  if (t.dataset.aip) { const vals = collectSettings(); vals.ai_provider = t.dataset.aip; await api("/api/settings", { body: vals }); await refresh(); renderSettings(); setTimeout(() => $("#ai") && $("#ai").scrollIntoView({ block: "center" }), 30); return; }
  if (t.dataset.box) { boxAction(t.dataset.box, Number(t.dataset.id) || null, t); return; }
  if (t.dataset.bp) {
    const f = $("#boxForm"), keep = {}; $$("[data-b]", f).forEach((el) => { if (!/host|port/.test(el.dataset.b)) keep[el.dataset.b] = el.value; });
    S.boxProv = t.dataset.bp; rerenderBoxes(); Object.entries(keep).forEach(([k, val]) => { const el = $('[data-b="' + k + '"]'); if (el) el.value = val; }); return;
  }
  if (t.dataset.sw) { t.classList.toggle("on"); markDirty(); return; }
  if (t.dataset.test) {
    const which = t.dataset.test, out = $("#r-" + which);
    out.innerHTML = '<span class="spin"></span> Testing…';
    if (!(await saveSettings(true))) { out.textContent = ""; return; }
    try {
      const r = await api("/api/test/" + which, { body: {} });
      out.innerHTML = r.ok ? '<span class="good">✓ Connected</span>' : '<span class="bad">' + esc(r.error) + "</span>";
    } catch (err) { out.innerHTML = '<span class="bad">' + esc(err.message) + "</span>"; }
    refresh();
  }
});
$("#campBtn").onclick = (e) => {
  e.stopPropagation(); $("#campMenu").classList.toggle("open");
  // With the rail collapsed the list opens beside the button instead of below it.
  $("#campList").style.top = document.documentElement.getAttribute("data-rail") === "collapsed" ? $("#campBtn").getBoundingClientRect().top + "px" : "";
};
$("#addCampaign").onclick = async () => {
  const name = prompt("Name the new campaign (e.g. Latvia, Germany casino):");
  if (!name) return;
  const r = await api("/api/campaigns", { body: { name } });
  S.campaign = r.id; store.set("almo-campaign", String(r.id));
  await refresh(); location.hash = "#/pitch"; route(); toast("Campaign created - write its pitch");
};
$("#addBtn").onclick = openAdd;
$("#exportBtn").onclick = (e) => {
  e.preventDefault();
  if (S.route === "database" && DB.sel.size && !DB.all) openExport("ids=" + [...DB.sel].join(","), fmt(DB.sel.size) + " selected website" + (DB.sel.size === 1 ? "" : "s"));
  else if (S.route === "database") openExport("db=1&" + dbQuery(), DB.exportWhat);
  else openExport(campQ(), S.campaign ? "Websites in this campaign" : "All websites in outreach");
};
$("#importFile").onchange = (e) => { if (e.target.files[0]) importDB(e.target.files[0]); e.target.value = ""; };
$$("#expKind button").forEach((b) => (b.onclick = () => { EXP.kind = b.dataset.ek; renderExport(); }));
["#expMarkup", "#expMargin"].forEach((id) => ($(id).oninput = renderExport));
$("#expGo").onclick = downloadExport;
document.addEventListener("click", (e) => { if (e.target.closest("[data-close-exp]")) closeExport(); });
$("#scrim").onclick = () => { closeAdd(); closeDrawer(); closeExport(); };
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeAdd(); closeDrawer(); closeExport(); } });
$("#siteText").oninput = () => { clearTimeout(previewAdd._t); previewAdd._t = setTimeout(previewAdd, 250); };
$("#fileIn").onchange = (e) => { if (e.target.files[0]) loadFile(e.target.files[0]); e.target.value = ""; };
const drop = $("#drop");
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) loadFile(f); });
$("#addGo").onclick = async () => {
  $("#addGo").disabled = true;
  try {
    const r = await api("/api/sites", { body: { text: $("#siteText").value, campaign_id: Number($("#addCamp").value) } });
    $("#siteText").value = ""; closeAdd();
    toast(r.added + " website" + (r.added === 1 ? "" : "s") + " added");
    await refresh(); if (S.route !== "websites") location.hash = "#/websites";
  } catch (e) { toast(e.message); $("#addGo").disabled = false; }
};
$("#saveAll") && 0;
document.addEventListener("click", (e) => { if (e.target.id === "saveAll") saveSettings(); });
$("#runchip").onclick = async () => {
  const on = !(S.data && S.data.settings.running);
  await api("/api/run", { body: { running: on } }); toast(on ? "Automation resumed" : "Automation paused"); refresh();
};
$("#range").value = String(S.days);
$("#range").onchange = (e) => { S.days = Number(e.target.value); store.set("almo-days", String(S.days)); refresh(); };
const SUN = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="8" r="3"/><path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3 3l1 1M12 12l1 1M3 13l1-1M12 4l1-1"/></svg>';
const MOON = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M13.5 10.2A5.8 5.8 0 0 1 5.8 2.5a5.8 5.8 0 1 0 7.7 7.7Z"/></svg>';
function themeIcon() { const light = document.documentElement.getAttribute("data-theme") === "light"; $("#themeBtn").innerHTML = light ? MOON : SUN; $("#themeBtn").title = light ? "Dark theme" : "Light theme"; }
themeIcon();
$("#themeBtn").onclick = () => {
  const cur = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", cur); store.set("almo-theme", cur); themeIcon();
  if (S.route === "overview" && S.data) drawChart($("#plot"), S.data.series);
};
$("#railToggle").onclick = () => {
  const c = document.documentElement.getAttribute("data-rail") === "collapsed";
  if (c) document.documentElement.removeAttribute("data-rail"); else document.documentElement.setAttribute("data-rail", "collapsed");
  store.set("almo-rail", c ? "" : "collapsed");
  setTimeout(() => S.route === "overview" && S.data && drawChart($("#plot"), S.data.series), 220);
};
window.addEventListener("resize", () => { if (S.route === "overview" && S.data) drawChart($("#plot"), S.data.series); });
window.addEventListener("hashchange", route);

fetch("/web/logo.svg").then((r) => r.text()).then((svg) => ($("#logo").innerHTML = svg));
$("#exportBtn").href = "/api/export?" + campQ();
(async () => { await refresh(); route(); })();
setInterval(() => { if (document.hidden) return; if (S.route === "settings" || S.route === "pitch") { api("/api/state?days=" + S.days + "&" + campQ()).then((d) => { S.data = Object.assign(d, { settings: S.settingsDirty ? S.data.settings : d.settings }); renderNav(); renderRunchip(); }).catch(() => {}); } else refresh(); }, 4000);
})();
