"use strict";

const $ = (selector) => document.querySelector(selector);
const TEXT = new Proxy({}, {get: (_, key) => IDI18N.tables[IDI18N.lang].text[key]});
const labels = new Proxy({}, {get: (_, key) => IDI18N.tables[IDI18N.lang].status[key]});

function hiddenKey() { return `idradar.hidden.${IDI18N.lang}`; }
function readHidden() {
  try { const saved = localStorage.getItem(hiddenKey()); const value = saved == null ? IDI18N.defaultHidden[IDI18N.lang] : JSON.parse(saved); return new Set(Array.isArray(value) ? value.filter((id) => typeof id === "string") : IDI18N.defaultHidden[IDI18N.lang]); }
  catch { return new Set(IDI18N.defaultHidden[IDI18N.lang]); }
}
const state = {candidates: [], platforms: [], selectedPlatforms: new Set(), selections: {}, hiddenPlatforms: readHidden(), matrix: null, parsing: false, checking: false, rules: null, handlePrompt: "", history: [], demo: false, sample: "", detail: null, pendingRemove: null, logins: {}, verifications: {}, loginEpochs: {}, loginNoticeSkipped: false, controller: null};
const nameKey = (name) => name.normalize("NFKC").replace(/\s/g, "").toLowerCase();

function localURL(path) { return path + (path.includes("?") ? "&" : "?") + "lang=" + IDI18N.lang; }
function localized(value, field) { return value?.[field + "_i18n"]?.[IDI18N.lang] ?? value?.[field] ?? ""; }

function crossIcon() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 12 12"); svg.setAttribute("width", "12"); svg.setAttribute("height", "12"); svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M2 2l8 8M10 2l-8 8"); path.setAttribute("stroke", "currentColor"); path.setAttribute("stroke-width", "1.5"); path.setAttribute("stroke-linecap", "round");
  svg.append(path); return svg;
}

function copyIcon() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 14 14"); svg.setAttribute("width", "13"); svg.setAttribute("height", "13"); svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M5 5h7v7H5zM2 9V2h7"); path.setAttribute("fill", "none"); path.setAttribute("stroke", "currentColor"); path.setAttribute("stroke-width", "1.3"); path.setAttribute("stroke-linejoin", "round");
  svg.append(path); return svg;
}

function platformIcon(platform) {
  const icon = element("span", undefined, "platform-icon"); icon.setAttribute("aria-hidden", "true");
  const names = {bilibili: "bilibili", douyin: "douyin", xiaohongshu: "xiaohongshu", weixin_channels: "weixin", github: "github", x: "x"};
  if (!platform.custom && names[platform.id]) {
    const img = element("img"); img.src = `/static/icons/${names[platform.id]}.png`; img.alt = ""; img.width = 14; img.height = 14; icon.append(img);
  } else { icon.textContent = Array.from(platform.label || platform.id || "")[0] || ""; icon.classList.add("custom-icon"); }
  return icon;
}

function addPlatformIcon(node, platform) {
  const text = node.textContent; node.replaceChildren(platformIcon(platform), element("span", text)); node.classList.add("with-platform"); return node;
}

function renderProgress() {
  const metrics = state.matrix?.metrics;
  $("#overall-progress").hidden = !metrics;
  if (!metrics) return;
  $("#progress-bar").max = Math.max(1, metrics.total);
  $("#progress-bar").value = metrics.total ? metrics.completed : 1;
  $("#check-progress").textContent = state.matrix.stopped ? TEXT.userStopped : TEXT.progress(metrics.completed, metrics.total);
  $("#eta").textContent = state.matrix.stopped ? "" : metrics.paused?.length ? TEXT.etaPaused : TEXT.eta(metrics.eta_seconds);
}

function missingLogins(platforms, selected, hidden) {
  return platforms.filter((p) => ["douyin", "xiaohongshu"].includes(p.id) && selected.has(p.id) && !hidden.has(p.id) && p.logged_in !== true);
}

function renderLoginNotice(force = false) {
  if (force) state.loginNoticeSkipped = false;
  const missing = missingLogins(state.platforms, state.selectedPlatforms, state.hiddenPlatforms);
  const banner = $("#login-notice");
  banner.hidden = state.demo || state.loginNoticeSkipped || !missing.length;
  if (banner.hidden) { banner.dataset.key = ""; return; }
  const key = IDI18N.lang + ":" + missing.map((p) => p.id + ":" + !!state.verifications[p.id]).join(":");
  if (!force && banner.dataset.key === key) return;
  banner.dataset.key = key;
  const content = element("div", undefined, "login-notice-content login-pulse");
  content.append(element("strong", TEXT.loginNotice(missing.map((p) => IDI18N.label(p.id)).join(TEXT.listSeparator), missing.length)));
  const actions = element("div", undefined, "toolbar-buttons");
  for (const platform of missing) {
    const button = element("button", TEXT.loginNoticeAction(IDI18N.label(platform.id)), "notice-login");
    button.disabled = !!state.verifications[platform.id];
    button.addEventListener("click", async () => { await startQr(platform.id); $("#login-cards").scrollIntoView({block: "center"}); });
    actions.append(button);
  }
  const skip = element("button", TEXT.loginSkip, "notice-skip");
  skip.addEventListener("click", () => { state.loginNoticeSkipped = true; renderLoginNotice(); });
  actions.append(skip); content.append(actions); banner.replaceChildren(content);
}

function renderRemoval() {
  const platform = state.pendingRemove;
  if (!platform) return;
  $("#remove-title").textContent = TEXT.removeTitle(IDI18N.label(platform.id, platform.label));
  $("#remove-description").textContent = platform.custom ? TEXT.removeCustom : TEXT.removeBuiltin;
}

function requestRemoval(platform) {
  if (visiblePlatforms().length <= 1) return;
  state.pendingRemove = platform; renderRemoval(); $("#remove-dialog").showModal();
}

async function confirmRemoval() {
  const platform = state.pendingRemove;
  if (!platform || visiblePlatforms().length <= 1) return;
  $("#confirm-remove").disabled = true;
  $("#cancel-remove").disabled = true;
  try {
    if (platform.custom) {
      const data = await api(`/api/custom-platforms/${platform.id}`, undefined, "DELETE");
      state.platforms = data.platforms; state.rules = null;
    } else { state.hiddenPlatforms.add(platform.id); saveHidden(); }
    state.selectedPlatforms.delete(platform.id);
    state.pendingRemove = null; $("#remove-dialog").close(); renderPlatforms(); scheduleValidation();
  } catch (error) { notify(error.message, true); }
  finally { $("#confirm-remove").disabled = false; $("#cancel-remove").disabled = false; }
}

function renderVerifications() {
  const container = $("#verification-cards"); container.replaceChildren();
  for (const [id, pause] of Object.entries(state.verifications)) {
    const card = element("article", undefined, "verification-card"); card.dataset.platform = id;
    card.append(element("strong", pause.opened ? TEXT.verificationTitle(IDI18N.label(id)) : TEXT.verificationQueued(IDI18N.label(id)), "card-title"), element("p", TEXT.verificationHelp, "muted small"));
    const action = element("button", TEXT.verificationContinue, "primary verification-action");
    action.disabled = !!pause.busy || !pause.opened;
    action.addEventListener("click", async () => {
      pause.busy = true; renderVerifications();
      try {
        await api(`/api/check/${pause.run_id}/${id}/continue`, {pause_id: pause.pause_id});
        if (state.verifications[id]?.pause_id === pause.pause_id) {
          delete state.verifications[id];
        }
      } catch (error) { notify(error.message, true); }
      finally { pause.busy = false; renderVerifications(); }
    });
    card.append(action); container.append(card);
  }
  renderVerifyNotice();
}

// 验证窗口弹出时，顶部也闪 3 次提示，免得用户没注意到弹出的窗口
function renderVerifyNotice() {
  const opened = Object.keys(state.verifications).filter((id) => state.verifications[id].opened);
  const banner = $("#verify-notice");
  banner.hidden = !opened.length;
  if (banner.hidden) { banner.dataset.key = ""; return; }
  const key = IDI18N.lang + ":" + opened.join(":");
  if (banner.dataset.key === key) return;
  banner.dataset.key = key;
  const content = element("div", undefined, "login-notice-content login-pulse");
  content.append(element("strong", TEXT.verifyNotice(opened.map((id) => IDI18N.label(id)).join(TEXT.listSeparator))));
  banner.replaceChildren(content);
}

function copyButton(text, label) {
  const button = element("button", undefined, "copy-id");
  button.setAttribute("aria-label", label); button.title = label; button.append(copyIcon());
  button.addEventListener("click", () => copyText(text));
  return button;
}

const qrPolls = new Map();
let qrCountdown;
function acceptLogin(id, data) {
  state.logins[id] = {...data, expires_at: Date.now() + data.expires_in * 1000};
  const platform = state.platforms.find((item) => item.id === id);
  if (platform) platform.logged_in = data.logged_in;
  renderPlatforms(); renderLoginCards(); pollLogin();
  if (data.status === "logged_in") {
    setTimeout(() => { if (state.logins[id]?.session_id === data.session_id) { delete state.logins[id]; renderLoginCards(); } }, 1500);
  } else pollQr(id);
}

async function startQr(id) {
  const epoch = state.loginEpochs[id] = (state.loginEpochs[id] || 0) + 1;
  clearTimeout(qrPolls.get(id)); state.logins[id] = {status: "loading"}; renderLoginCards();
  try {
    const data = await api(`/api/login/${id}`, {});
    if (state.loginEpochs[id] === epoch) acceptLogin(id, data);
  } catch (error) { if (state.loginEpochs[id] === epoch) { state.logins[id] = {status: "error"}; renderLoginCards(); notify(error.message, true); } }
}

function pollQr(id) {
  clearTimeout(qrPolls.get(id));
  const session = state.logins[id];
  qrPolls.set(id, setTimeout(async () => {
    if (state.logins[id] !== session) return;
    try { const data = await api(`/api/login/${id}`); if (state.logins[id] === session) acceptLogin(id, data); }
    catch (error) { if (state.logins[id] === session) notify(error.message, true); }
  }, 2000));
}

function renderLoginCards() {
  const container = $("#login-cards"); container.replaceChildren(); clearTimeout(qrCountdown);
  for (const [id, session] of Object.entries(state.logins)) {
    const card = element("article", undefined, "login-card"); card.dataset.platform = id;
    const header = element("div", undefined, "login-card-head");
    header.append(element("strong", session.status === "loading" ? TEXT.qrLoading : TEXT.qrScan(IDI18N.label(id))));
    const close = element("button", undefined, "text-button qr-close"); close.append(crossIcon()); close.setAttribute("aria-label", TEXT.qrClose); close.disabled = session.status === "loading";
    close.addEventListener("click", async () => {
      try { await api(`/api/login/${id}`, undefined, "DELETE"); state.loginEpochs[id]++; clearTimeout(qrPolls.get(id)); delete state.logins[id]; renderLoginCards(); }
      catch (error) { notify(error.message, true); }
    }); header.append(close); card.append(header);
    const remaining = Math.max(0, Math.ceil((session.expires_at - Date.now()) / 1000));
    const expired = session.status === "expired" || (session.status === "qr" && remaining === 0);
    if (session.status === "qr" && !expired) {
      const img = element("img", undefined, "qr-image"); img.src = session.qr_image; img.alt = TEXT.qrImage; card.append(img);
      card.append(element("p", TEXT.qrCountdown(remaining), "muted small"), element("p", TEXT.qrPhone, "muted small qr-phone"));
    } else if (session.status === "fallback") {
      card.append(element("p", TEXT.qrFallback), element("p", localized(session, "note"), "muted small"));
      const open = element("button", TEXT.qrOpenWindow, "secondary qr-window");
      open.addEventListener("click", async () => { try { await api(`/api/login/${id}/window`, {}); } catch (error) { notify(error.message, true); } }); card.append(open);
      const finish = element("button", TEXT.qrContinue, "primary qr-continue");
      finish.addEventListener("click", async () => { try { acceptLogin(id, await api(`/api/login/${id}/continue`, {})); } catch (error) { notify(error.message, true); } }); card.append(finish);
    } else if (session.status === "logged_in") card.append(element("p", TEXT.loggedIn + " ✓", "login-success"));
    if (expired || session.status === "error") {
      if (expired) card.append(element("p", TEXT.qrExpired, "muted"));
      const refresh = element("button", TEXT.qrRefresh, "secondary qr-refresh"); refresh.addEventListener("click", () => startQr(id)); card.append(refresh);
    }
    container.append(card);
  }
  if (Object.values(state.logins).some((session) => session.status === "qr")) qrCountdown = setTimeout(renderLoginCards, 1000);
}

function renderParseFeedback() {
  const data = state.parseFeedback;
  $("#parse-feedback").textContent = data ? data.count > 10 ? TEXT.recognized(data.count, selectedCandidates().length) : TEXT.parseCounts(data.count, data.added, data.updated) : "";
}

function applyStaticText() {
  document.documentElement.lang = IDI18N.lang === "zh" ? "zh-CN" : "en";
  document.title = TEXT.pageTitle;
  if (!$("#cell-details").open) $("#cell-title").textContent = TEXT.details;
  for (const attribute of ["text", "placeholder", "aria-label", "title"]) {
    const name = attribute === "text" ? "data-i18n" : "data-i18n-" + attribute;
    document.querySelectorAll(`[${name}]`).forEach((node) => {
      const value = TEXT[node.getAttribute(name)];
      if (attribute === "text") node.textContent = value;
      else node.setAttribute(attribute, value);
    });
  }
  $("#lang-zh").setAttribute("aria-pressed", String(IDI18N.lang === "zh"));
  $("#lang-en").setAttribute("aria-pressed", String(IDI18N.lang === "en"));
  $("#demo-badge").hidden = !state.demo;
  $("#paste-sample").hidden = !state.demo;
  $("#batch-hint").textContent = TEXT.batchHint;
  if (state.handleNames) $("#handle-summary").textContent = TEXT.handleSummary(state.handleNames.length);
  document.querySelectorAll("[data-status]").forEach((node) => { node.textContent = labels[node.dataset.status]; });
  renderParseFeedback();
  renderHistory();
  renderRemoval(); renderLoginCards(); renderVerifications(); renderProgress(); renderLoginNotice();
  updateActions();
  if (state.matrix && !state.matrix.metrics) $("#check-progress").textContent = TEXT.progress(Object.keys(state.matrix.results).length, state.matrix.candidates.length * state.matrix.platforms.length);
}

async function loadPrompt() {
  const lang = IDI18N.lang;
  $("#copy-prompt").disabled = true;
  $("#paste-sample").disabled = true;
  const data = await api("/api/prompt");
  if (lang !== IDI18N.lang) return;
  $("#naming-prompt").value = data.prompt;
  $("#copy-prompt").disabled = false;
  $("#paste-sample").disabled = false;
  state.demo = !!data.demo; state.sample = data.sample || "";
  applyStaticText();
}

async function switchLanguage(lang) {
  if (lang === IDI18N.lang) return;
  state.selections[IDI18N.lang] = new Set(state.selectedPlatforms);
  IDI18N.lang = lang;
  try { localStorage.setItem("idradar.lang", lang); } catch {}
  state.hiddenPlatforms = readHidden();
  state.selectedPlatforms = state.selections[lang] ? new Set(state.selections[lang]) : new Set(visiblePlatforms().filter((p) => defaultSelected(p, lang)).map((p) => p.id));
  state.rules = null;
  state.handlePrompt = state.handlePrompts?.[lang] || "";
  $("#site-feedback").textContent = "";
  notify("");
  applyStaticText(); renderCandidates(); renderPlatforms(); renderMatrix(); renderHistory();
  if ($("#cell-details").open && state.detail) showDetails(state.detail.candidate, state.detail.id, state.detail.result);
  if ($("#rules-dialog").open) openRules();
  try { await loadPrompt(); } catch (error) { notify(error.message, true); }
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function notify(text, error = false) {
  const message = $("#message");
  message.textContent = text;
  message.className = "message" + (error ? " error" : "");
  message.hidden = !text;
}

async function api(path, body, method) {
  const response = await fetch(localURL(path), {method: method || (body === undefined ? "GET" : "POST"), ...(body === undefined ? {} : {headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)})});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : TEXT.apiError);
  return data;
}

function selectedCandidates() { return state.candidates.filter((candidate) => candidate.selected); }

function updateActions() {
  const count = selectedCandidates().length;
  $("#selection-count").textContent = TEXT.selected(count);
  $("#start-check").textContent = state.checking ? TEXT.stopChecking : TEXT.start(count, state.selectedPlatforms.size);
  $("#start-check").className = state.checking ? "secondary stop-check" : "primary";
  $("#start-check").setAttribute("aria-busy", String(state.checking));
  $("#start-check").disabled = !state.checking && (!count || !state.selectedPlatforms.size);
  $("#parse-names").disabled = state.parsing;
  $("#parse-names").textContent = state.parsing ? TEXT.parsing : TEXT.parseNames;
  document.querySelectorAll(".more-variants").forEach((button) => { button.disabled = state.checking || state.matrix?.blocked || state.matrix?.stopped || button.dataset.exhausted === "true"; });
  document.querySelectorAll(".find-available").forEach((button) => { button.disabled = state.checking || state.matrix?.blocked || state.matrix?.stopped; });
}

function renderCandidates() {
  const grid = $("#candidates");
  grid.replaceChildren();
  if (!state.candidates.length) grid.append(element("p", TEXT.emptyCandidates, "empty"));
  state.candidates.forEach((candidate) => {
    const card = element("article", undefined, "candidate" + (candidate.selected ? " selected" : ""));
    const name = element("label", candidate.name, "candidate-name");
    const checkbox = element("input", undefined, "candidate-checkbox");
    checkbox.type = "checkbox";
    checkbox.checked = candidate.selected;
    checkbox.setAttribute("aria-label", TEXT.selectName(candidate.name));
    name.append(checkbox);
    checkbox.addEventListener("change", () => { candidate.selected = checkbox.checked; card.classList.toggle("selected", checkbox.checked); updateActions(); });
    const handle = element("input", undefined, "handle");
    handle.value = candidate.handle;
    handle.placeholder = TEXT.missingHandle;
    handle.maxLength = 80;
    handle.spellcheck = false;
    handle.setAttribute("aria-label", TEXT.handleLabel(candidate.name));
    handle.addEventListener("input", () => { candidate.handle = handle.value.trim(); scheduleValidation(); });
    const meaning = element("p", candidate.meaning, "meaning");
    meaning.title = candidate.meaning;
    const tags = element("div", undefined, "tags");
    (candidate.tags || []).forEach((tag) => tags.append(element("span", tag, "tag")));
    const warning = element("p", undefined, "candidate-warning");
    warning.hidden = true;
    card.append(name, handle, meaning, warning, tags);
    grid.append(card);
  });
  updateActions();
  scheduleValidation();
}

function appendCandidates(candidates) {
  const seen = new Set(state.candidates.map((candidate) => nameKey(candidate.name)));
  let added = 0;
  for (const candidate of candidates) {
    const key = nameKey(candidate.name);
    if (!seen.has(key)) {
      state.candidates.push(...IDPlans.selectIncoming(state.candidates, [candidate]));
      seen.add(key);
      added++;
    }
  }
  renderCandidates();
  return added;
}

async function recognizeNames() {
  state.parsing = true;
  $("#parse-feedback").textContent = "";
  $("#parse-names").textContent = TEXT.parsing;
  updateActions();
  try {
    const data = await api("/api/parse-names", {text: $("#names-input").value, existing: state.candidates.map(({name, handle}) => ({name, handle}))});
    for (const update of data.updates) state.candidates[update.index].handle = update.handle;
    appendCandidates(data.candidates);
    state.parseFeedback = data;
    renderParseFeedback();
    if (data.count) notify(TEXT.parsed);
  } catch (error) { notify(error.message, true); }
  finally { state.parsing = false; $("#parse-names").textContent = TEXT.parseNames; updateActions(); }
}

async function copyWithFeedback(text, button) {
  const original = button.textContent;
  const lang = IDI18N.lang;
  try {
    await navigator.clipboard.writeText(text);
    button.textContent = TEXT.copyDone;
    button.disabled = true;
    setTimeout(() => { button.textContent = lang === IDI18N.lang ? original : TEXT[button.getAttribute("data-i18n")] || original; button.disabled = false; }, 1500);
  } catch { notify(TEXT.copyError, true); }
}

let validationTimer = null;
let validationEpoch = 0;
function scheduleValidation() {
  clearTimeout(validationTimer);
  const epoch = ++validationEpoch;
  validationTimer = setTimeout(async () => {
    const candidates = state.candidates.map(({name, handle}) => ({name, handle}));
    const platforms = [...state.selectedPlatforms];
    if (!candidates.length) { $("#handle-help").hidden = true; state.handlePrompt = ""; return; }
    try {
      const data = await api("/api/rules/check", {candidates, platforms});
      if (epoch !== validationEpoch) return;
      state.handlePrompt = data.handle_prompt;
      state.handlePrompts = data.handle_prompt_i18n;
      state.handleNames = data.handle_names;
      $("#handle-summary").textContent = TEXT.handleSummary(data.handle_names.length);
      $("#handle-help").hidden = !data.handle_names.length;
      document.querySelectorAll(".candidate-warning").forEach((warning, index) => {
        const validations = data.validations[index] || {};
        warning.textContent = platforms.filter((id) => validations[id]?.verdict === "bad").map((id) => `${IDI18N.label(id, state.platforms.find((p) => p.id === id)?.label)}${TEXT.colon}${validations[id].reasons.join(TEXT.sentenceSeparator)}`).join(" · ");
        warning.hidden = !warning.textContent;
      });
    } catch (error) { if (epoch === validationEpoch) notify(TEXT.validationFailed(error.message), true); }
  }, 150);
}

function platformLabel(matrix, id) { return IDI18N.label(id, matrix.platform_details?.[id]?.label || id); }

function renderRecommendation(matrix, row, panel) {
  const content = element("div", undefined, "recommendation");
  content.append(element("p", panel.loading ? TEXT.finding(panel.checked) : TEXT.found(panel.checked), "muted small"));
  if (panel.loading) return content;
  if (panel.error) content.append(element("p", panel.error, "failure"));
  const cards = element("div", undefined, "recommendation-cards");
  const partial = panel.choices.partial, unified = panel.choices.unified;
  for (const kind of ["partial", "unified"]) {
    const choice = panel.choices[kind];
    const card = element("article", undefined, "recommendation-card " + kind);
    card.append(element("h3", TEXT[kind]));
    let summary;
    if (kind === "partial") {
      summary = partial.ready ? TEXT.partialSummary(partial.changed.map((id) => TEXT.useFor(platformLabel(matrix, id), partial.final[id])), matrix.platforms.length - partial.changed.length) : TEXT.missing(partial.missing.map((id) => platformLabel(matrix, id)));
    } else summary = unified.ready ? TEXT.unifiedSummary(unified.candidate, matrix.platforms.length) : TEXT.noUnified(panel.checked);
    card.append(element("p", summary, "muted small"));
    const use = element("button", TEXT[kind === "partial" ? "adoptPartial" : "adoptUnified"], kind === "partial" ? "primary adopt-partial" : "secondary adopt-unified");
    use.disabled = !choice.ready;
    use.addEventListener("click", () => { IDPlans.adopt(matrix, row, choice); matrix.activePlan = row; renderMatrix(); });
    card.append(use);
    cards.append(card);
  }
  content.append(cards);
  const actions = element("div", undefined, "recommendation-actions muted small");
  actions.append(element("span", TEXT.dissatisfied));
  const more = element("button", TEXT.more, "text-button more-variants");
  more.dataset.exhausted = String(panel.exhausted);
  more.disabled = state.checking || matrix.blocked || panel.blocked || panel.exhausted;
  more.addEventListener("click", () => checkMoreVariants(row));
  const copy = element("button", TEXT.copyHomophone, "text-button");
  copy.addEventListener("click", () => copyWithFeedback(localized(panel, "copy_prompt"), copy));
  actions.append(more, document.createTextNode(" · "), copy);
  content.append(actions);
  if (panel.exhausted) content.append(element("p", TEXT.exhausted, "muted small"));
  if (panel.blocked) content.append(element("p", TEXT.stopped, "muted small"));
  return content;
}

function renderPlan() {
  const card = $("#id-plan"), matrix = state.matrix;
  card.replaceChildren();
  const rows = Object.keys(matrix?.adoptions || {}).sort((a, b) => matrix.adoptions[a].order - matrix.adoptions[b].order);
  card.hidden = !rows.length;
  if (!rows.length) return;
  const row = matrix.adoptions[matrix.activePlan] ? matrix.activePlan : Number(rows.at(-1));
  matrix.activePlan = row;
  card.append(element("h3", TEXT.plan));
  const select = element("div", undefined, "plan-choices");
  for (const value of rows) {
    const button = element("button", matrix.candidates[value].name, "pill");
    button.setAttribute("aria-pressed", String(Number(value) === Number(row)));
    button.addEventListener("click", () => { matrix.activePlan = Number(value); renderPlan(); });
    select.append(button);
  }
  if (rows.length > 1) card.append(select);
  card.append(element("p", TEXT.planFor(matrix.candidates[row].name), "muted small"));
  const names = IDPlans.finalNames(matrix, row);
  for (const id of matrix.platforms) {
    const line = element("div", undefined, "plan-line");
    line.append(element("span", platformLabel(matrix, id)), element("strong", names[id], "plan-name"));
    const copy = element("button", TEXT.copy, "secondary");
    copy.addEventListener("click", () => copyWithFeedback(names[id], copy));
    line.append(copy, safeLink(IDPlans.registrationURL({...matrix.platform_details[id], id}), TEXT.register));
    card.append(line);
  }
  const copyAll = element("button", TEXT.copyAll, "secondary copy-plan");
  copyAll.addEventListener("click", () => copyWithFeedback(IDPlans.planLines(matrix, row, (id) => platformLabel(matrix, id), TEXT.colon), copyAll));
  card.append(copyAll);
}

const confidenceLabels = new Proxy({}, {get: (_, key) => IDI18N.tables[IDI18N.lang].confidence[key]});
const characterLabels = new Proxy({}, {get: (_, key) => IDI18N.tables[IDI18N.lang].characters[key]});


function confidenceBadge(level) { return element("span", confidenceLabels[level] || confidenceLabels.conflict, `confidence ${level || "conflict"}`); }

function renderRules(rules) {
  const content = $("#rules-content");
  content.replaceChildren();
  const scroll = element("div", undefined, "rules-scroll");
  scroll.tabIndex = 0;
  scroll.setAttribute("role", "region");
  scroll.setAttribute("aria-label", TEXT.rulesScroll);
  const table = element("table", undefined, "rules-table"), head = element("thead"), header = element("tr");
  for (const title of TEXT.ruleHeaders) { const cell = element("th", title); cell.scope = "col"; header.append(cell); }
  head.append(header);
  const body = element("tbody");
  const order = state.platforms.map((platform) => platform.id);
  for (const id of order) {
    const rule = rules[id];
    if (!rule) continue;
    const row = element("tr");
    if (rule.custom) {
      row.append(element("td", rule.label));
      const unknown = element("td", TEXT.unknownRules);
      unknown.colSpan = 5;
      row.append(unknown);
      body.append(row);
      continue;
    }
    row.append(element("td", rule.label + (rule.target === "handle" ? "（handle）" : "")));
    const counts = rule.cjk_width === null ? TEXT.unknown : rule.allowed.cjk === "no" ? TEXT.ascii : TEXT.cjkCount(rule.cjk_width);
    const allowed = [["yes", TEXT.allowedYes], ["no", TEXT.allowedNo], ["unknown", TEXT.allowedUnknown]].map(([value, label]) => {
      const names = Object.entries(rule.allowed).filter(([, flag]) => flag === value).map(([key]) => characterLabels[key]);
      return names.length ? `${label}${TEXT.colon}${names.join(TEXT.listSeparator)}` : "";
    }).filter(Boolean).join(TEXT.sentenceSeparator);
    const extra = rule.extra_rules.includes("hyphen_not_at_edges") ? TEXT.hyphenRules : "";
    const values = [
      [TEXT.lengthRange(rule.min_len ?? TEXT.allowedUnknown, rule.max_len ?? TEXT.allowedUnknown), rule.field_confidence.length],
      [counts, rule.field_confidence.cjk_width],
      [allowed + extra, rule.field_confidence.allowed],
      [{yes: TEXT.uniqueYes, no: TEXT.uniqueNo, unknown: TEXT.unknown}[rule.unique.value], rule.unique.confidence],
      [rule.rename_limit, rule.field_confidence.rename_limit],
    ];
    for (const [text, level] of values) { const cell = element("td", text); cell.append(confidenceBadge(level || rule.confidence)); row.append(cell); }
    body.append(row);
  }
  table.append(head, body);
  scroll.append(table);
  content.append(scroll);
  content.append(element("h3", TEXT.sourceNotes, "rules-section-title"));
  for (const id of order) {
    const rule = rules[id];
    if (rule) content.append(element("p", `${rule.label}${TEXT.colon}${rule.notes.join(" ")}`, "rule-platform-note"));
  }
  content.append(element("h3", TEXT.sources, "rules-section-title"));
  const seen = new Set();
  for (const rule of Object.values(rules)) {
    for (const source of rule.sources) {
      const key = source.url + source.date + source.level;
      if (seen.has(key)) continue;
      seen.add(key);
      const line = element("p", undefined, "rule-source");
      line.append(safeLink(new URL(source.url.startsWith("/api/") ? localURL(source.url) : source.url, location.origin).href, source.title), document.createTextNode(` · ${source.date} `), confidenceBadge(source.level));
      content.append(line);
    }
  }
}

async function openRules() {
  if (!$("#rules-dialog").open) $("#rules-dialog").showModal();
  $("#rules-content").textContent = TEXT.readingRules;
  const lang = IDI18N.lang;
  try { const rules = state.rules || (await api("/api/rules")).platforms; if (lang === IDI18N.lang) { state.rules = rules; renderRules(rules); } }
  catch (error) { $("#rules-content").textContent = error.message; }
}

// 中文模式默认勾上自动查和要登录的平台（抖音、小红书），只有手动平台（视频号）不勾。
const defaultSelected = (platform, lang) => lang === "en" || platform.mode !== "manual";
function visiblePlatforms() {
  return state.platforms.filter((platform) => platform.custom || !state.hiddenPlatforms.has(platform.id));
}
function saveHidden() {
  try { localStorage.setItem(hiddenKey(), JSON.stringify([...state.hiddenPlatforms])); } catch {}
}
function restorePlatform(id) {
  state.hiddenPlatforms.delete(id);
  state.selectedPlatforms.add(id);
  saveHidden(); renderPlatforms(); scheduleValidation();
}
function renderPlatforms() {
  // 损坏或陈旧的本机存储不能把所有平台都藏起来。
  if (state.platforms.length && !visiblePlatforms().length) { state.hiddenPlatforms.delete(state.platforms[0].id); saveHidden(); }
  const visible = visiblePlatforms();
  const active = new Set(visible.map((platform) => platform.id));
  for (const id of state.selectedPlatforms) if (!active.has(id)) state.selectedPlatforms.delete(id);
  const container = $("#platforms"); container.replaceChildren();
  visible.forEach((platform) => {
    const label = IDI18N.label(platform.id, platform.label);
    const group = element("div", undefined, "platform-option");
    const button = addPlatformIcon(element("button", label, "pill"), platform);
    button.setAttribute("aria-pressed", String(state.selectedPlatforms.has(platform.id)));
    button.addEventListener("click", () => {
      state.selectedPlatforms.has(platform.id) ? state.selectedPlatforms.delete(platform.id) : state.selectedPlatforms.add(platform.id);
      button.setAttribute("aria-pressed", String(state.selectedPlatforms.has(platform.id)));
      updateActions(); scheduleValidation(); renderLoginNotice();
    });
    group.append(button);
    if (platform.mode === "manual") group.append(element("small", TEXT.manual));
    if (platform.mode === "login") {
      const status = platform.logged_in === true ? TEXT.loggedIn : platform.logged_in === false ? TEXT.loggedOut : TEXT.unconfirmed;
      group.append(element("small", status));
      const login = element("button", platform.logged_in === true ? TEXT.relogin : TEXT.login, "login-button");
      login.disabled = !!state.verifications[platform.id];
      login.addEventListener("click", () => startQr(platform.id));
      group.append(login);
    }
    if (visible.length > 1) {
      const remove = element("button", undefined, "remove-platform"); remove.append(crossIcon());
      remove.setAttribute("aria-label", (platform.custom ? TEXT.delete : TEXT.remove)(label));
      remove.addEventListener("click", () => requestRemoval(platform));
      group.append(remove);
    }
    container.append(group);
  });
  const add = element("button", TEXT.addSite, "secondary add-site");
  add.addEventListener("click", () => { $("#custom-site-form").hidden = false; $("#site-feedback").textContent = ""; $("#site-label").focus(); });
  container.append(add);
  const restore = $("#restore-platforms");
  restore.replaceChildren(document.createTextNode(TEXT.restore));
  const hidden = state.platforms.filter((platform) => !platform.custom && state.hiddenPlatforms.has(platform.id));
  restore.hidden = !hidden.length;
  for (const platform of hidden) {
    const button = element("button", IDI18N.label(platform.id, platform.label), "text-button");
    button.addEventListener("click", () => restorePlatform(platform.id));
    restore.append(button);
  }
  updateActions();
  renderLoginNotice();
}

let loginTimer = null;
function pollLogin() {
  clearTimeout(loginTimer);
  loginTimer = setTimeout(async () => {
    try {
      const data = await api("/api/platforms");
      state.platforms = data.platforms;
      renderPlatforms();
      if (data.browser_open) pollLogin();
    } catch (error) { notify(error.message, true); }
  }, 2000);
}

function verdict(matrix, row) {
  const auto = matrix.platforms.filter((id) => (matrix.platform_details?.[id] || state.platforms.find((platform) => platform.id === id))?.mode !== "manual");
  if (!auto.length) return {text: labels.manual, all: false};
  const results = auto.map((id) => matrix.results[`${row}:${id}`]);
  if (results.some((result) => result?.status === "stopped")) return {text: labels.stopped, all: false};
  if (results.some((result) => !result)) return {text: TEXT.checking, all: false};
  const count = results.filter((result) => result.status === "available").length;
  return {text: count === auto.length ? TEXT.allAvailable : TEXT.availableCount(count, auto.length), all: count === auto.length};
}

function renderMatrix(changedCell = null) {
  const matrix = state.matrix;
  if (!matrix) return;
  $("#matrix-scroll").hidden = false; $("#results-footer").hidden = false;
  const table = $("#matrix"); table.replaceChildren();
  const head = element("thead"), headRow = element("tr");
  const titles = [TEXT.name, ...matrix.platforms.map((id) => platformLabel(matrix, id)), TEXT.verdict];
  titles.forEach((title) => { const th = element("th", title); th.scope = "col"; headRow.append(th); });
  head.append(headRow);
  const body = element("tbody");
  matrix.candidates.forEach((candidate, row) => {
    const conclusion = verdict(matrix, row), adopted = matrix.adoptions?.[row];
    const tr = element("tr", undefined, "result-row" + (conclusion.all ? " all-available" : ""));
    tr.dataset.row = row;
    const name = element("td");
    const nameLine = element("div", undefined, "copy-line");
    nameLine.append(element("strong", candidate.name), copyButton(candidate.name, TEXT.copyNameOf(candidate.name)));
    name.append(nameLine);
    if (candidate.handle) {
      const handleLine = element("div", undefined, "copy-line");
      handleLine.append(element("span", candidate.handle, "handle"), copyButton(candidate.handle, TEXT.copyHandleOf(candidate.handle)));
      name.append(handleLine);
    }
    tr.append(name);
    matrix.platforms.forEach((id) => {
      const td = element("td"); td.dataset.cell = `${row}:${id}`;
      const result = matrix.results[`${row}:${id}`];
      if (!result) {
        const loading = element("span", undefined, "pending");
        loading.append(element("span", undefined, "spinner"), document.createTextNode(" " + TEXT.pending)); td.append(loading);
      } else {
        const platform = matrix.platform_details?.[id];
        if (platform?.custom && platform.kind === "search" && result.status === "manual") td.append(addPlatformIcon(safeLink(result.search_url, labels.manual, "status manual status-link"), {...platform, id}));
        else {
          const button = element("button", labels[result.status] || labels.error, `status ${result.status}` + (changedCell === `${row}:${id}` ? " new-result" : ""));
          button.addEventListener("click", () => showDetails(candidate, id, result)); td.append(addPlatformIcon(button, {...platform, id}));
        }
      }
      if (adopted) {
        const oldName = IDPlans.originalName(matrix, row, id), newName = adopted.final[id];
        const line = element("div", undefined, "final-use" + (oldName === newName ? " muted" : " changed"));
        if (oldName === newName) line.textContent = TEXT.useOriginal;
        else line.append(element("s", oldName), document.createTextNode(` → ${newName} ✓`));
        td.append(line);
      }
      tr.append(td);
    });
    const conclusionCell = element("td", undefined, "verdict" + (conclusion.all ? " all-available" : ""));
    conclusionCell.append(element("span", adopted ? TEXT.settled : conclusion.text));
    if (matrix.recommended_rows?.includes(row)) conclusionCell.append(element("small", TEXT.recommended, "recommended-badge"));
    if (adopted) {
      const changed = matrix.platforms.filter((id) => IDPlans.originalName(matrix, row, id) !== adopted.final[id]);
      const changedNames = changed.filter((id) => !IDPlans.usesHandle({...matrix.platform_details[id], id})).map((id) => platformLabel(matrix, id));
      const changedHandles = changed.filter((id) => IDPlans.usesHandle({...matrix.platform_details[id], id})).map((id) => platformLabel(matrix, id));
      conclusionCell.append(element("small", TEXT.changed(changedNames, changedHandles), "settled-note"));
      const undo = element("button", TEXT.undo, "text-button undo-adoption");
      undo.addEventListener("click", () => { IDPlans.undo(matrix, row); renderMatrix(); }); conclusionCell.append(undo);
    } else if (matrix.platforms.every((id) => matrix.results[`${row}:${id}`]) && !matrix.platforms.some((id) => ["taken", "similar", "stopped"].includes(matrix.results[`${row}:${id}`].status))) {
      const choose = element("button", TEXT.choose, "secondary choose-original");
      // 全部可用时点“就用它”直接复制名字就完事，不再生成 ID 方案卡
      choose.addEventListener("click", async () => { await copyText(candidate.name); choose.textContent = TEXT.copyDone; });
      conclusionCell.append(choose);
    }
    if (!adopted && !matrix.recommendations?.[row] && matrix.platforms.every((id) => matrix.results[`${row}:${id}`]) && matrix.platforms.some((id) => ["taken", "similar"].includes(matrix.results[`${row}:${id}`].status))) {
      const find = element("button", TEXT.findAvailable, "secondary find-available"); find.disabled = state.checking || matrix.blocked || matrix.stopped;
      find.addEventListener("click", () => checkMoreVariants(row)); conclusionCell.append(find);
    }
    tr.append(conclusionCell); body.append(tr);
    const panel = matrix.recommendations?.[row];
    if (panel && !adopted) {
      const panelRow = element("tr", undefined, "recommendation-row"); panelRow.dataset.row = row;
      const cell = element("td", undefined, "recommendation-cell"); cell.colSpan = matrix.platforms.length + 2;
      cell.append(renderRecommendation(matrix, row, panel)); panelRow.append(cell); body.append(panelRow);
    }
  });
  table.append(head, body); renderPlan(); renderProgress();
}

function safeLink(url, text, className) {
  const link = element("a", text, className);
  try {
    const parsed = new URL(url);
    if (!["https:", "http:"].includes(parsed.protocol)) throw new Error();
    link.href = parsed.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  } catch { link.removeAttribute("href"); }
  return link;
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); notify(TEXT.copied); }
  catch { notify(TEXT.copyError, true); }
}

function showDetails(candidate, id, result) {
  state.detail = {candidate, id, result};
  $("#cell-title").textContent = `${candidate.name} · ${platformLabel(state.matrix, id)}`;
  const content = $("#cell-content");
  content.replaceChildren(addPlatformIcon(element("span", labels[result.status], `status ${result.status}`), {...state.matrix.platform_details?.[id], id}));
  for (const match of (result.matches || []).slice(0, 5)) {
    const item = element("div", undefined, "match-item");
    item.append(safeLink(match.url, match.name));
    if (match.extra) item.append(element("small", localized(match, "extra")));
    content.append(item);
  }
  if (result.search_url) content.append(safeLink(result.search_url, TEXT.searchPage, "detail-search platform-address"));
  content.append(element("p", localized(result, "note"), "detail-note"));
  if (result.status === "manual") {
    const actions = element("div", undefined, "export-buttons");
    const copy = element("button", TEXT.copyName, "secondary");
    copy.addEventListener("click", () => copyText(candidate.name));
    actions.append(copy);
    if (result.search_url) actions.append(safeLink(result.search_url, TEXT.openPlatform));
    content.append(actions);
  }
  if (!$("#cell-details").open) $("#cell-details").showModal();
}

async function consumeStream(path, body, onEvent, signal) {
  const response = await fetch(localURL(path), {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body), signal});
  if (!response.ok) { const data = await response.json(); throw new Error(data.detail || TEXT.requestFailed); }
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let buffer = "", done = false;
  function consume() {
    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const chunk = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
      const type = chunk.match(/^event: (.+)$/m)?.[1], payload = chunk.match(/^data: (.+)$/m)?.[1];
      if (!payload) continue;
      const data = JSON.parse(payload);
      if (type === "done") done = true;
      if (!signal?.aborted) onEvent(type, data);
    }
  }
  try {
    while (true) {
      const {value, done: ended} = await reader.read();
      if (ended) { buffer += decoder.decode(); consume(); break; }
      buffer += decoder.decode(value, {stream: true}); consume();
    }
    if (!done) throw new Error(TEXT.disconnected);
  } finally { try { await reader.cancel(); } catch (error) { if (!signal?.aborted) throw error; } }
}

function stopCheck() {
  if (!state.checking || !state.controller || state.controller.signal.aborted) return;
  state.controller.abort();
  const matrix = state.matrix;
  matrix.stopped = true;
  for (const pause of Object.values(state.verifications)) if (!pause.variant) delete matrix.results[`${pause.row}:${pause.platform}`];
  matrix.candidates.forEach((candidate, row) => matrix.platforms.forEach((id) => {
    const key = `${row}:${id}`;
    matrix.results[key] ||= {status: "stopped", matches: [], search_url: "", note: TEXT.userStopped,
      note_i18n: Object.fromEntries(["zh", "en"].map((lang) => [lang, IDI18N.tables[lang].text.userStopped]))};
  }));
  for (const panel of Object.values(matrix.recommendations)) panel.loading = false;
  state.verifications = {}; renderVerifications(); renderMatrix();
  $("#check-progress").textContent = TEXT.userStopped;
  $("#start-check").disabled = true;
}

async function refreshStoppedHistory(runId) {
  if (state.demo || !runId) return;
  // 断流清理在服务端完成，历史可能比浏览器的 AbortError 晚一点落盘。
  for (let i = 0; i < 20; i++) {
    await loadHistory();
    if (state.history.some((record) => record.id === runId)) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}

function handleRunEvent(matrix, type, data, rowOverride) {
  if (type === "start") { matrix.run_id = data.id; matrix.metrics = data.progress; renderProgress(); }
  else if (type === "result") {
    matrix.results[`${data.row}:${data.platform}`] = data.result;
    if (data.result.status === "blocked") matrix.blocked = true;
    renderMatrix(`${data.row}:${data.platform}`);
  } else if (type === "recommendation") {
    const row = rowOverride ?? data.row;
    matrix.recommendations[row] = {...data, row}; matrix.blocked ||= data.blocked; renderMatrix();
  } else if (type === "ranking") { matrix.recommended_rows = data.recommended_rows; renderMatrix(); }
  else if (type === "progress") { matrix.metrics = data; renderProgress(); }
  else if (type === "verification") {
    const row = rowOverride ?? data.row;
    state.verifications[data.platform] = {...data, row};
    if (!data.variant) matrix.results[`${row}:${data.platform}`] = data.result;
    renderVerifications(); renderPlatforms(); renderMatrix();
  } else if (type === "verification_resumed") {
    const pause = state.verifications[data.platform];
    if (pause?.pause_id === data.pause_id) {
      if (!pause.variant) delete matrix.results[`${pause.row}:${data.platform}`];
      delete state.verifications[data.platform];
    }
    renderVerifications(); renderPlatforms(); renderMatrix();
  } else if (type === "batch") $("#check-progress").textContent = TEXT.batch(data.number, data.total);
  else if (type === "warning") notify(localized(data, "message"), true);
  else if (type === "done") { matrix.blocked ||= data.blocked; if (matrix.blocked) notify(TEXT.stopped); }
}

async function startCheck() {
  if (state.checking) { stopCheck(); return; }
  const candidates = selectedCandidates().map(({name, handle}) => ({name, handle}));
  const platforms = [...state.selectedPlatforms];
  if (!candidates.length || !platforms.length) { notify(TEXT.emptySelection, true); return; }
  renderLoginNotice(true);
  state.matrix = {candidates, platforms, results: {}, recommendations: {}, adoptions: {}, blocked: false,
    platform_details: Object.fromEntries(state.platforms.map((platform) => [platform.id, {...platform}]))};
  state.verifications = {}; renderVerifications(); $("#overall-progress").hidden = true;
  const matrix = state.matrix;
  const controller = state.controller = new AbortController();
  state.checking = true; updateActions(); renderMatrix();
  pollLogin();
  $("#check-progress").textContent = TEXT.progress(0, candidates.length * platforms.length);
  try {
    await consumeStream("/api/check", {candidates, platforms}, (type, data) => handleRunEvent(matrix, type, data), controller.signal);
    try { await loadHistory(); } catch (error) { notify(TEXT.historyFailed(error.message), true); }
  } catch (error) {
    if (controller.signal.aborted) return;
    notify(error.message, true);
    candidates.forEach((candidate, row) => platforms.forEach((id) => {
      const key = `${row}:${id}`;
      if (!matrix.results[key]) matrix.results[key] = {status: "error", matches: [], search_url: "", note: error.message};
    }));
    for (const panel of Object.values(matrix.recommendations)) { panel.loading = false; panel.error = error.message; }
    renderMatrix(); $("#check-progress").textContent = TEXT.failed;
  } finally {
    state.controller = null; state.checking = false; state.verifications = {}; renderVerifications(); renderPlatforms(); pollLogin();
    if (controller.signal.aborted) { try { await refreshStoppedHistory(matrix.run_id); } catch (error) { notify(TEXT.historyFailed(error.message), true); } }
  }
}

async function checkMoreVariants(row) {
  const matrix = state.matrix;
  const panel = matrix.recommendations[row] ||= {next_offset: 0, checked: 0, copy_prompt: "", choices: {
    partial: {ready: false, missing: matrix.platforms.filter((id) => ["taken", "similar"].includes(matrix.results[`${row}:${id}`]?.status))}, unified: {ready: false}}};
  if (state.checking || matrix.blocked || panel.exhausted) return;
  if (matrix.platforms.some((id) => matrix.results[`${row}:${id}`]?.status === "stopped")) return;
  const controller = state.controller = new AbortController();
  matrix.stopped = false;
  state.checking = true; panel.loading = true; updateActions(); renderMatrix();
  try {
    await consumeStream("/api/variants/check", {candidate: matrix.candidates[row], platforms: matrix.platforms,
      original: Object.fromEntries(matrix.platforms.map((id) => [id, matrix.results[`${row}:${id}`]])), offset: panel.next_offset}, (type, data) => {
      handleRunEvent(matrix, type, data, row);
    }, controller.signal);
  } catch (error) { if (!controller.signal.aborted) { const current = matrix.recommendations[row]; current.loading = false; current.error = error.message; renderMatrix(); } }
  finally {
    state.controller = null; state.checking = false; state.verifications = {}; renderVerifications(); renderPlatforms(); pollLogin();
    if (controller.signal.aborted) { try { await refreshStoppedHistory(matrix.run_id); } catch (error) { notify(TEXT.historyFailed(error.message), true); } }
  }
}

async function loadHistory() {
  const data = await api("/api/history");
  state.history = data.history;
  renderHistory();
}

function renderHistory() {
  const data = {history: state.history};
  const list = $("#history-list");
  list.replaceChildren();
  if (!data.history.length) list.textContent = TEXT.noHistory;
  data.history.forEach((record) => {
    const button = element("button", `${new Date(record.created_at).toLocaleString(TEXT.dateLocale)} · ${record.candidates.map((candidate) => candidate.name).join(TEXT.listSeparator)}`, "history-item secondary");
    button.addEventListener("click", () => {
      if (state.checking) { notify(TEXT.historyWait, true); return; }
      state.matrix = {candidates: record.candidates, platforms: record.platforms, results: {}, platform_details: record.platform_details || {}, recommendations: record.recommendations || {}, recommended_rows: record.recommended_rows || [], adoptions: {}, stopped: !!record.stopped, blocked: record.results.some((cell) => cell.result.status === "blocked")};
      record.results.forEach((cell) => { state.matrix.results[`${cell.row}:${cell.platform}`] = cell.result; });
      renderMatrix();
      $("#check-progress").textContent = TEXT.viewingHistory + new Date(record.created_at).toLocaleString(TEXT.dateLocale);
      $("#history-menu").open = false;
      $("#matrix-scroll").scrollIntoView({block: "nearest"});
    });
    list.append(button);
  });
}

function exportRows() {
  return IDPlans.exportRows(state.matrix, labels, {...IDI18N.tables[IDI18N.lang].text, platformLabel: (id) => platformLabel(state.matrix, id), conclusion: (row) => verdict(state.matrix, row).text});
}

$("#lang-zh").addEventListener("click", () => switchLanguage("zh"));
$("#lang-en").addEventListener("click", () => switchLanguage("en"));
$("#paste-sample").addEventListener("click", () => { if (state.demo) $("#names-input").value = state.sample; });
$("#confirm-remove").addEventListener("click", confirmRemoval);
$("#cancel-remove").addEventListener("click", () => { state.pendingRemove = null; $("#remove-dialog").close(); });
$("#remove-dialog").addEventListener("cancel", () => { state.pendingRemove = null; });
$("#parse-names").addEventListener("click", recognizeNames);
$("#copy-prompt").addEventListener("click", () => copyWithFeedback($("#naming-prompt").value, $("#copy-prompt")));
$("#copy-handle-prompt").addEventListener("click", () => copyWithFeedback(state.handlePrompt, $("#copy-handle-prompt")));
$("#cancel-site").addEventListener("click", () => { $("#custom-site-form").hidden = true; });
$("#custom-site-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#save-site").disabled = true;
  $("#site-feedback").textContent = "";
  try {
    const data = await api("/api/custom-platforms", Object.fromEntries(new FormData(event.target)));
    state.platforms = data.platforms;
    state.selectedPlatforms.add(data.site.id);
    state.rules = null;
    event.target.reset();
    event.target.hidden = true;
    renderPlatforms();
    scheduleValidation();
  } catch (error) { $("#site-feedback").textContent = error.message; }
  finally { $("#save-site").disabled = false; }
});
$("#select-all").addEventListener("click", () => { state.candidates.forEach((candidate) => { candidate.selected = true; }); renderCandidates(); });
$("#select-none").addEventListener("click", () => { state.candidates.forEach((candidate) => { candidate.selected = false; }); renderCandidates(); });
$("#start-check").addEventListener("click", startCheck);
$("#open-rules").addEventListener("click", openRules);
$("#close-rules").addEventListener("click", () => $("#rules-dialog").close());
$("#close-details").addEventListener("click", () => $("#cell-details").close());
$("#copy-markdown").addEventListener("click", () => {
  const rows = exportRows().map((row) => row.map((value) => String(value).replace(/\|/g, "\\|").replace(/[\r\n]/g, " ")));
  if (!rows.length) return;
  const line = (row) => "| " + row.join(" | ") + " |";
  copyText([line(rows[0]), line(rows[0].map(() => "---")), ...rows.slice(1).map(line)].join("\n"));
});
$("#export-csv").addEventListener("click", () => {
  const rows = exportRows();
  const csv = rows.map((row) => row.map((value) => { let text = String(value); if (/^[\s]*[=+\-@]/.test(text)) text = "'" + text; return '"' + text.replace(/"/g, '""') + '"'; }).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob(["\uFEFF" + csv], {type: "text/csv;charset=utf-8"}));
  const link = element("a"); link.href = url; link.download = TEXT.csvFilename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});

async function init() {
  applyStaticText();
  const results = await Promise.allSettled([loadPrompt(), api("/api/platforms"), loadHistory()]);
  if (results[0].status === "rejected") notify(results[0].reason.message, true);
  if (results[1].status === "fulfilled") {
    state.platforms = results[1].value.platforms;
    visiblePlatforms().filter((platform) => defaultSelected(platform, IDI18N.lang)).forEach((platform) => state.selectedPlatforms.add(platform.id));
    renderPlatforms();
    if (results[1].value.browser_open) pollLogin();
  } else notify(results[1].reason.message, true);
  if (results[2].status === "rejected") notify(results[2].reason.message, true);
  updateActions();
}

init();
