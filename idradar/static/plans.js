"use strict";

// 纯函数供页面与离线单元测试共用；平台注册/改名入口集中维护。
const IDPlans = (() => {
  const ENTRY_URLS = Object.freeze({
    bilibili: "https://account.bilibili.com/account/setting",
    douyin: "https://www.douyin.com/",
    xiaohongshu: "https://www.xiaohongshu.com/explore",
    weixin_channels: "https://channels.weixin.qq.com/",
    github: "https://github.com/settings/admin",
    x: "https://x.com/settings/screen_name",
  });
  function usesHandle(platform) {
    return platform.target === "handle" || (platform.custom && platform.kind === "profile") || ["github", "x"].includes(platform.id);
  }
  function originalName(matrix, row, id) {
    const platform = {...matrix.platform_details?.[id], id};
    return matrix.candidates[row][usesHandle(platform) ? "handle" : "name"];
  }
  function finalNames(matrix, row) {
    return {...Object.fromEntries(matrix.platforms.map((id) => [id, originalName(matrix, row, id)])), ...matrix.adoptions?.[row]?.final};
  }
  function adopt(matrix, row, choice) {
    if (!choice.ready) return false;
    matrix.adoptions ||= {};
    matrix.adoptionSequence = (matrix.adoptionSequence || 0) + 1;
    matrix.adoptions[row] = {final: {...choice.final}, order: matrix.adoptionSequence};
    return true;
  }
  function undo(matrix, row) { if (matrix.adoptions) delete matrix.adoptions[row]; }
  function selectIncoming(existing, incoming) {
    let slots = Math.max(0, 10 - existing.filter((item) => item.selected).length);
    return incoming.map((item) => ({...item, selected: slots-- > 0}));
  }
  function exportRows(matrix, labels, text) {
    if (!matrix) return [];
    return [[text.name, "handle", ...matrix.platforms.flatMap((id) => [text.platformLabel ? text.platformLabel(id) : matrix.platform_details?.[id]?.label || id, text.finalName]), text.verdict],
      ...matrix.candidates.map((candidate, row) => [candidate.name, candidate.handle, ...matrix.platforms.flatMap((id) => [labels[matrix.results[`${row}:${id}`]?.status] || text.pending, finalNames(matrix, row)[id]]), matrix.adoptions?.[row] ? text.settled : text.conclusion(row)])];
  }
  function registrationURL(platform) {
    if (!platform.custom) return ENTRY_URLS[platform.id] || "";
    try { return new URL(platform.url_template).origin + "/"; } catch { return ""; }
  }
  function planLines(matrix, row, labelFor = (id) => matrix.platform_details?.[id]?.label || id, separator = "\uFF1A") {
    const names = finalNames(matrix, row);
    return matrix.platforms.map((id) => `${labelFor(id)}${separator}${names[id]}`).join("\n");
  }
  return {ENTRY_URLS, usesHandle, originalName, finalNames, adopt, undo, selectIncoming, exportRows, registrationURL, planLines};
})();
if (typeof module !== "undefined") module.exports = IDPlans;
