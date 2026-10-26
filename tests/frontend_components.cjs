"use strict";
// 最小 DOM 只检查组件逻辑，不代替浏览器布局和截图验收。
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "..");
const localeSource = fs.readFileSync(path.join(root, "idradar/static/i18n.js"), "utf8");
const htmlSource = fs.readFileSync(path.join(root, "idradar/static/index.html"), "utf8");
for (const [browser, saved, expected] of [["en-US", null, "en"], ["zh-TW", null, "zh"], ["en-GB", "zh", "zh"], ["zh-CN", "en", "en"], ["en-US", "invalid", "en"], ["en-US", "throw", "en"]]) {
  const localeContext = vm.createContext({navigator: {language: browser}, localStorage: {getItem: () => {if (saved === "throw") throw new Error("不可用"); return saved;}}});
  vm.runInContext(localeSource, localeContext);
  assert.equal(vm.runInContext("IDI18N.lang", localeContext), expected);
  assert.deepEqual(JSON.parse(vm.runInContext("JSON.stringify(IDI18N.defaultHidden.en)", localeContext)), ["bilibili", "douyin", "xiaohongshu", "weixin_channels"]);
  for (const match of htmlSource.matchAll(/data-i18n(?:-placeholder|-aria-label|-title)?="([^"]+)"/g)) {
    assert.equal(vm.runInContext(`typeof IDI18N.tables.zh.text[${JSON.stringify(match[1])}]`, localeContext), "string");
    assert.equal(vm.runInContext(`typeof IDI18N.tables.en.text[${JSON.stringify(match[1])}]`, localeContext), "string");
  }
}
class Node {
  constructor(tag) { this.tag = tag; this.children = []; this.events = {}; this.attributes = {}; this.dataset = {}; this.className = ""; this.hidden = false; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = []; this.valueText = ""; this.append(...nodes); }
  set textContent(text) { this.children = []; this.valueText = text ?? ""; }
  get textContent() { return String(this.valueText || "") + this.children.map((node) => typeof node === "string" ? node : node.textContent).join(""); }
  setAttribute(key, value) { this.attributes[key] = value; }
  getAttribute(key) { return this.attributes[key]; }
  removeAttribute(key) { delete this.attributes[key]; }
  addEventListener(type, callback) { this.events[type] = callback; }
  get classList() { return {add: (name) => {this.className += " " + name;}, toggle: (name, on) => { const names = new Set(this.className.split(" ")); on ? names.add(name) : names.delete(name); this.className = [...names].join(" "); }}; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  scrollIntoView() {}
  focus() {}
}
function walk(node) { return [node, ...node.children.filter((value) => value instanceof Node).flatMap(walk)]; }
function findClass(node, name) { return walk(node).filter((item) => item.className.split(" ").includes(name)); }
const ids = new Map([...fs.readFileSync(path.join(root, "idradar/static/index.html"), "utf8").matchAll(/id="([^"]+)"/g)].map((match) => [match[1], new Node("div")]));
const platforms = [
  {id: "bilibili", label: "B站", mode: "auto"}, {id: "github", label: "GitHub", mode: "auto", target: "handle"},
  {id: "x", label: "X", mode: "auto", target: "handle"}, {id: "douyin", label: "抖音", mode: "login"},
  {id: "xiaohongshu", label: "小红书", mode: "login"}, {id: "weixin_channels", label: "视频号", mode: "manual"},
];
let clipboard = "", deletes = 0;
const storage = new Map();
const context = vm.createContext({
  console, URL, AbortController, setTimeout: () => 1, clearTimeout: () => {},
  document: {
    documentElement: {lang: "zh-CN"},
    querySelector: (selector) => { assert(selector.startsWith("#")); const node = ids.get(selector.slice(1)); assert(node, selector); return node; },
    querySelectorAll: (selector) => [...ids.values()].flatMap((node) => findClass(node, selector.slice(1))),
    createElement: (tag) => new Node(tag), createElementNS: (namespace, tag) => new Node(tag), createTextNode: (text) => String(text),
  },
  localStorage: {getItem: (key) => storage.get(key), setItem: (key, value) => storage.set(key, value)},
  navigator: {clipboard: {writeText: async (text) => { clipboard = text; }}},
  confirm: () => {throw new Error("不能使用浏览器原生确认框");},
  fetch: async (url) => {
    url = url.split("?")[0];
    if (url.startsWith("/api/custom-platforms/")) deletes++;
    return {ok: true, json: async () => url === "/api/prompt" ? {prompt: "提示词"} : url === "/api/history" ? {history: []} : {platforms: url.startsWith("/api/custom-platforms/") ? platforms.filter(p => p.id !== "custom_1") : platforms}};
  },
});
vm.runInContext(fs.readFileSync(path.join(root, "idradar/static/i18n.js"), "utf8"), context);
vm.runInContext(fs.readFileSync(path.join(root, "idradar/static/plans.js"), "utf8"), context);
vm.runInContext(fs.readFileSync(path.join(root, "idradar/static/app.js"), "utf8"), context);
const run = (code) => vm.runInContext(code, context);
async function main() {
  await new Promise(setImmediate);
  assert.equal(findClass(ids.get("platforms"), "platform-option").length, 6);
  const remove = (label) => findClass(ids.get("platforms"), "remove-platform").find((node) => node.attributes["aria-label"] === "移除平台 " + label);
  await remove("小红书").events.click();
  assert(remove("小红书"));
  assert.equal(ids.get("remove-dialog").open, true);
  assert.equal(remove("小红书").children[0].tag, "svg");
  await ids.get("cancel-remove").events.click();
  assert(remove("小红书"));
  await remove("小红书").events.click();
  await ids.get("confirm-remove").events.click();
  assert(JSON.parse(storage.get("idradar.hidden.zh")).includes("xiaohongshu"));
  assert(!remove("小红书"));
  assert.equal(ids.has("undo-toast"), false);
  await findClass(ids.get("restore-platforms"), "text-button")[0].events.click();
  assert(remove("小红书"));
  await remove("小红书").events.click();
  await ids.get("confirm-remove").events.click();
  assert.equal(ids.get("restore-platforms").hidden, false);
  await findClass(ids.get("restore-platforms"), "text-button")[0].events.click();
  assert(remove("小红书"));
  run('state.platforms.push({id: "custom_1", label: "示例站", custom: true, mode: "auto", kind: "profile", url_template: "https://example.test/{handle}"}); renderPlatforms()');
  const deleteSite = () => findClass(ids.get("platforms"), "remove-platform").find(node => node.attributes["aria-label"] === "删除网站 示例站");
  await deleteSite().events.click();
  assert.equal(deletes, 0);
  assert(deleteSite());
  await ids.get("cancel-remove").events.click();
  await deleteSite().events.click();
  await ids.get("confirm-remove").events.click();
  assert.equal(deletes, 1);
  assert(!deleteSite());
  run('appendCandidates(Array.from({length: 12}, (_, i) => ({name: "候选" + i, handle: "tool" + i})))');
  assert.equal(run("selectedCandidates().length"), 10);
  run("state.candidates.forEach((candidate) => {candidate.selected = true;}); updateActions()");
  assert.equal(ids.get("start-check").textContent, "先查前 10 个（剩 2 个下一批）");
  assert.equal(ids.get("start-check").disabled, false);
  run(`state.matrix = {
    candidates: [{name: "工具人", handle: "toolman"}], platforms: ["bilibili", "github", "x"],
    platform_details: Object.fromEntries(state.platforms.map(p => [p.id, p])),
    results: {"0:bilibili": {status: "taken"}, "0:github": {status: "taken"}, "0:x": {status: "available"}},
    recommendations: {0: {loading: false, checked: 2, copy_prompt: "同音提示", choices: {
      partial: {ready: true, changed: ["bilibili", "github"], final: {bilibili: "工具人本人", github: "toolman001", x: "toolman"}},
      unified: {ready: true, candidate: {name: "工具人001", handle: "toolman001"}, final: {bilibili: "工具人001", github: "toolman001", x: "toolman001"}}
    }}}, adoptions: {}
  }; renderMatrix()`);
  assert.equal(findClass(ids.get("matrix"), "recommendation-card").length, 2);
  await findClass(ids.get("matrix"), "adopt-partial")[0].events.click();
  assert.equal(findClass(ids.get("matrix"), "recommendation-row").length, 0);
  assert.equal(findClass(ids.get("matrix"), "final-use").length, 3);
  assert.equal(ids.get("id-plan").hidden, false);
  await findClass(ids.get("id-plan"), "copy-plan")[0].events.click();
  assert.equal(clipboard, "B站：工具人本人\nGitHub：toolman001\nX：toolman");
  await findClass(ids.get("matrix"), "undo-adoption")[0].events.click();
  assert.equal(findClass(ids.get("matrix"), "recommendation-row").length, 1);
  assert.equal(ids.get("id-plan").hidden, true);
  await findClass(ids.get("matrix"), "adopt-unified")[0].events.click();
  assert.equal(run("exportRows()[1][3]"), "工具人001");
  await findClass(ids.get("id-plan"), "copy-plan")[0].events.click();
  assert.equal(clipboard, "B站：工具人001\nGitHub：toolman001\nX：toolman001");
  await findClass(ids.get("matrix"), "undo-adoption")[0].events.click();
  run('state.matrix.results["0:bilibili"].status = "available"; state.matrix.results["0:github"].status = "available"; state.matrix.recommendations = {}; renderMatrix()');
  // “就用它”只复制名字，不生成方案卡；名字和 handle 旁各有复制按钮
  const choose = findClass(ids.get("matrix"), "choose-original")[0];
  await choose.events.click();
  assert.equal(clipboard, "工具人");
  assert.equal(choose.textContent, "已复制 ✓");
  assert.equal(run("Object.keys(state.matrix.adoptions).length"), 0);
  const copies = findClass(ids.get("matrix"), "copy-id");
  assert.equal(copies[0].attributes["aria-label"], "复制名字 工具人");
  await copies[1].events.click();
  assert.equal(clipboard, run("state.matrix.candidates[0].handle"));
  // 下面的语言切换要检查方案卡，直接采用一次原名方案
  run("IDPlans.adopt(state.matrix, 0, {ready: true, final: IDPlans.finalNames(state.matrix, 0)}); state.matrix.activePlan = 0; renderMatrix()");
  assert.equal(run("exportRows()[1][3]"), "工具人");
  // 切换后候选、勾选、矩阵、采用状态均保留；英文默认展示 GitHub、X 和所有自定义网站。
  run('state.platforms.push({id: "custom_extra", label: "Example", mode: "manual", custom: true, kind: "search", url_template: "https://example.test/{name}"})');
  const before = run("JSON.stringify({candidates: state.candidates, results: state.matrix.results, adoptions: state.matrix.adoptions})");
  await run('switchLanguage("en")');
  assert.equal(run("document.documentElement.lang"), "en");
  assert.deepEqual(JSON.parse(run("JSON.stringify(visiblePlatforms().map(p => p.id))")), ["github", "x", "custom_extra"]);
  assert(run('state.selectedPlatforms.has("custom_extra")'));
  assert.equal(run("JSON.stringify({candidates: state.candidates, results: state.matrix.results, adoptions: state.matrix.adoptions})"), before);
  assert.equal(run("exportRows()[0][3]"), "Final name");
  assert.equal(ids.get("id-plan").textContent.includes("My ID plan"), true);
  assert.equal(run("localURL('/api/check')"), "/api/check?lang=en");
  await findClass(ids.get("id-plan"), "copy-plan")[0].events.click();
  assert.equal(clipboard, "Bilibili: 工具人\nGitHub: toolman\nX: toolman");
  await run('switchLanguage("zh")');
  run('state.platforms = state.platforms.filter(p => p.id !== "custom_extra"); renderPlatforms()');
  assert.equal(run("document.documentElement.lang"), "zh-CN");
  assert.equal(run("visiblePlatforms().length"), 6);
  // 存储被禁用时移除仍可用，最后一个标签不提供删除按钮。
  run('localStorage.setItem = () => {throw new Error("不可用")}; localStorage.getItem = () => {throw new Error("不可用")};');
  assert.equal(run("readHidden().size"), 0);
  for (const label of ["B站", "抖音", "小红书", "视频号", "X"]) { await remove(label).events.click(); await ids.get("confirm-remove").events.click(); }
  assert.equal(findClass(ids.get("platforms"), "platform-option").length, 1);
  assert.equal(findClass(ids.get("platforms"), "remove-platform").length, 0);
  run(`state.matrix = {
    candidates: Array.from({length:5},(_,i)=>({name:"名字"+i,handle:"toolman"})), platforms:["bilibili"],
    platform_details:{bilibili:{label:"B站"}}, results:Object.fromEntries(Array.from({length:5},(_,i)=>[i+":bilibili",{status:"taken"}])),
    recommendations:{0:{loading:true,checked:0},1:{loading:true,checked:0},2:{loading:true,checked:0}}, recommended_rows:[0,1,2], adoptions:{}
  }; renderMatrix()`);
  assert.equal(findClass(ids.get("matrix"), "recommendation-row").length, 3);
  assert.equal(findClass(ids.get("matrix"), "find-available").length, 2);
  assert.equal(findClass(ids.get("matrix"), "recommended-badge").length, 3);
  assert.equal(findClass(ids.get("matrix"), "platform-icon").length, 5);
  const realStream = run("consumeStream"), originalFetch = context.fetch;
  const abort = new AbortController();
  let cancelledReader = false, requestSignal;
  context.fetch = async (url, options) => {
    requestSignal = options.signal;
    return {ok:true, body:{getReader:()=>({
      read:()=>new Promise((resolve,reject)=>options.signal.addEventListener("abort",()=>reject(Object.assign(new Error("aborted"),{name:"AbortError"})),{once:true})),
      cancel:async()=>{cancelledReader=true;},
    })}};
  };
  context.TextDecoder = TextDecoder;
  const abortedStream = realStream("/api/check", {}, ()=>assert.fail("已中断的流不能推送结果"), abort.signal);
  await new Promise(setImmediate);
  abort.abort();
  await assert.rejects(abortedStream, {name:"AbortError"});
  assert.equal(requestSignal, abort.signal);
  assert.equal(cancelledReader, true);
  context.fetch = originalFetch;
  run('consumeStream = async (path,body,onEvent) => {onEvent("recommendation",{row:0,loading:true,checked:0}); onEvent("done",{blocked:false});}');
  await findClass(ids.get("matrix"), "find-available")[0].events.click();
  assert.equal(findClass(ids.get("matrix"), "recommendation-row").length, 4);
  run('state.verifications.bilibili = {run_id:"run",pause_id:"pause",opened:false}; renderVerifications()');
  assert.equal(findClass(ids.get("verification-cards"), "verification-action")[0].disabled, true);
  run('state.verifications.bilibili.opened = true; renderVerifications()');
  await findClass(ids.get("verification-cards"), "verification-action")[0].events.click();
  assert.equal(findClass(ids.get("verification-cards"), "verification-card").length, 0);
  run('acceptLogin("xiaohongshu",{session_id:"qr",status:"qr",qr_image:"data:image/png;base64,AA==",expires_in:120,logged_in:null})');
  assert.equal(findClass(ids.get("login-cards"), "qr-image").length, 1);
  run('acceptLogin("xiaohongshu",{session_id:"qr",status:"expired",expires_in:0})');
  assert.equal(findClass(ids.get("login-cards"), "qr-refresh").length, 1);
  run('acceptLogin("xiaohongshu",{session_id:"qr",status:"logged_in",expires_in:0,logged_in:true})');
  assert.equal(findClass(ids.get("login-cards"), "login-success").length, 1);
  // 提示只考虑实际查重范围，未知状态也提醒；跳过后开始查重会再次提示。
  run('state.hiddenPlatforms = new Set(); state.selectedPlatforms = new Set(["douyin","xiaohongshu"]); state.platforms.find(p=>p.id==="douyin").logged_in=null; state.platforms.find(p=>p.id==="xiaohongshu").logged_in=false; renderLoginNotice(true)');
  assert.equal(ids.get("login-notice").hidden, false);
  assert.equal(findClass(ids.get("login-notice"), "login-pulse").length, 1);
  assert.equal(findClass(ids.get("login-notice"), "notice-login").length, 2);
  await findClass(ids.get("login-notice"), "notice-skip")[0].events.click();
  run('renderLoginNotice()'); assert.equal(ids.get("login-notice").hidden, true);
  run('renderLoginNotice(true)'); assert.equal(ids.get("login-notice").hidden, false);
  run('state.platforms.find(p=>p.id==="xiaohongshu").logged_in=true; renderLoginNotice()');
  assert.equal(findClass(ids.get("login-notice"), "notice-login").length, 1);
  run('state.selectedPlatforms = new Set(["github","x"]); IDI18N.lang="en"; renderLoginNotice()');
  assert.equal(ids.get("login-notice").hidden, true);
  run('state.selectedPlatforms.add("douyin"); renderLoginNotice()');
  assert.equal(ids.get("login-notice").hidden, false);
  assert(ids.get("login-notice").textContent.includes("not signed in"));
  run('state.hiddenPlatforms.add("douyin"); renderLoginNotice()');
  assert.equal(ids.get("login-notice").hidden, true);
  // 中断流用真实 AbortController，保留完成结果、覆盖验证占位格，按钮可重新开始。
  run('IDI18N.lang="zh"; state.checking=true; state.controller=new AbortController(); state.matrix.recommendations={}; state.matrix.results["0:bilibili"]={status:"available"}; delete state.matrix.results["1:bilibili"]; state.verifications.bilibili={row:2,platform:"bilibili",variant:false}; state.matrix.results["2:bilibili"]={status:"blocked"}; updateActions()');
  assert.equal(ids.get("start-check").textContent, "停止查重");
  assert.equal(ids.get("start-check").disabled, false);
  run('stopCheck()');
  assert.equal(run('state.controller.signal.aborted'), true);
  assert.equal(run('state.matrix.results["0:bilibili"].status'), "available");
  assert.equal(run('state.matrix.results["1:bilibili"].status'), "stopped");
  assert.equal(run('state.matrix.results["2:bilibili"].status'), "stopped");
  run('state.checking=false; updateActions()');
  assert.equal(ids.get("start-check").disabled, false);
  run(`state.demo=true; state.selectedPlatforms=new Set(["bilibili"]); state.candidates.forEach((c,i)=>c.selected=i<2);
    consumeStream=async(path,body,onEvent,signal)=>{
      onEvent("start",{id:"fake-run"}); onEvent("result",{row:0,platform:"bilibili",result:{status:"available"}});
      await new Promise((resolve,reject)=>signal.addEventListener("abort",()=>reject(Object.assign(new Error("aborted"),{name:"AbortError"})),{once:true}));
    };
    globalThis.pendingCheck=startCheck();`);
  await new Promise(setImmediate);
  assert.equal(ids.get("start-check").textContent, "停止查重");
  await ids.get("start-check").events.click();
  await run("pendingCheck");
  assert.equal(run("state.checking"), false);
  assert.equal(run('state.matrix.results["0:bilibili"].status'), "available");
  assert.equal(run('state.matrix.results["1:bilibili"].status'), "stopped");
  run('consumeStream=async(path,body,onEvent)=>{body.candidates.forEach((c,row)=>onEvent("result",{row,platform:"bilibili",result:{status:"available"}})); onEvent("done",{blocked:false});}');
  await ids.get("start-check").events.click();
  assert.equal(run("state.checking"), false);
  assert.equal(run('state.matrix.results["1:bilibili"].status'), "available");
  for (const section of ["text", "status", "confidence", "characters"]) {
    assert.deepEqual(JSON.parse(run(`JSON.stringify(Object.keys(IDI18N.tables.zh.${section}).sort())`)), JSON.parse(run(`JSON.stringify(Object.keys(IDI18N.tables.en.${section}).sort())`)));
  }
  console.log("实际组件：推荐、采用、撤销、方案卡、前十个、移除、撤销提示与恢复逻辑通过");
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
