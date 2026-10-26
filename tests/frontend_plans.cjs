"use strict";
const assert = require("node:assert/strict");
const plans = require("../idradar/static/plans.js");
const matrix = {
  candidates: [{name: "工具人", handle: "toolman"}], platforms: ["bilibili", "github", "custom_1"],
  platform_details: {bilibili: {label: "B站"}, github: {label: "GitHub", target: "handle"}, custom_1: {label: "自定义", custom: true, kind: "profile", url_template: "https://example.test/user/{handle}"}},
  results: {"0:bilibili": {status: "taken"}, "0:github": {status: "available"}, "0:custom_1": {status: "manual"}},
};
const original = {bilibili: "工具人", github: "toolman", custom_1: "toolman"};
assert.deepEqual(plans.finalNames(matrix, 0), original);
assert.equal(plans.adopt(matrix, 0, {ready: false, final: {}}), false);
assert.deepEqual(plans.finalNames(matrix, 0), original);
const partial = {bilibili: "工具人日记", github: "toolman", custom_1: "toolman"};
assert.equal(plans.adopt(matrix, 0, {ready: true, final: partial}), true);
assert.deepEqual(plans.finalNames(matrix, 0), partial);
partial.bilibili = "不能影响已采用的副本";
assert.equal(plans.finalNames(matrix, 0).bilibili, "工具人日记");
assert.equal(plans.planLines(matrix, 0), "B站：工具人日记\nGitHub：toolman\n自定义：toolman");
const text = {name: "名字", finalName: "最终用名", verdict: "结论", pending: "查询中", settled: "已定", conclusion: () => "可用 1/2"};
const rows = plans.exportRows(matrix, {taken: "已被占用", available: "没搜到同名", manual: "需手动查"}, text);
assert.deepEqual(rows[0], ["名字", "handle", "B站", "最终用名", "GitHub", "最终用名", "自定义", "最终用名", "结论"]);
assert.deepEqual(rows[1], ["工具人", "toolman", "已被占用", "工具人日记", "没搜到同名", "toolman", "需手动查", "toolman", "已定"]);
plans.undo(matrix, 0);
assert.deepEqual(plans.finalNames(matrix, 0), original);
assert.equal(plans.exportRows(matrix, {}, text)[1].at(-1), "可用 1/2");
const unified = {bilibili: "工具人001", github: "toolman001", custom_1: "toolman001"};
plans.adopt(matrix, 0, {ready: true, final: unified});
assert.deepEqual(plans.finalNames(matrix, 0), unified);
plans.undo(matrix, 0);
assert.deepEqual(plans.finalNames(matrix, 0), original);
const incoming = Array.from({length: 15}, (_, i) => ({name: "名字" + i}));
assert.deepEqual(plans.selectIncoming([], incoming).map((p) => p.selected), [...Array(10).fill(true), ...Array(5).fill(false)]);
assert.equal(plans.selectIncoming(Array(8).fill({selected: true}), incoming).filter((p) => p.selected).length, 2);
assert.equal(plans.selectIncoming(Array(12).fill({selected: true}), incoming).filter((p) => p.selected).length, 0);
assert.deepEqual(incoming[0], {name: "名字0"});
assert.deepEqual(Object.keys(plans.ENTRY_URLS).sort(), ["bilibili", "douyin", "github", "weixin_channels", "x", "xiaohongshu"].sort());
assert.equal(plans.registrationURL({...matrix.platform_details.custom_1, id: "custom_1"}), "https://example.test/");
console.log("最终用名、两种采用、撤销、导出、前十个勾选与方案卡纯函数通过");
