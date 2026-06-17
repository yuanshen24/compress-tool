#!/usr/bin/env python3
"""
压缩排除工具 — Web UI
在浏览器中运行，界面现代清晰，解决 tkinter 高 DPI 模糊问题。
依赖: python3, tar/gzip/zip (均为系统自带)
"""

import os
import sys
import json
import subprocess
import threading
import webbrowser
import socket
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

# ── 压缩状态（线程安全） ──────────────────────────────────
_lock = threading.Lock()
_state = {"running": False, "success": None, "message": "就绪", "output_file": ""}


def set_state(**kw):
    with _lock:
        _state.update(kw)


def get_state():
    with _lock:
        return dict(_state)


# ── HTML 页面 ─────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>压缩排除工具</title>
<style>
  :root {
    --bg: #f1f5f9;
    --card: #ffffff;
    --border: #e2e8f0;
    --text: #0f172a;
    --text2: #64748b;
    --primary: #6366f1;
    --primary-hover: #4f46e5;
    --success: #16a34a;
    --danger: #dc2626;
    --radius: 10px;
    --shadow: 0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei",
                 "Noto Sans", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
    min-height: 100vh;
  }
  .container { max-width: 1100px; margin: 0 auto; padding: 24px 20px 40px; }

  /* Header */
  header {
    display: flex; align-items: center; gap: 12px;
    margin-bottom: 24px;
  }
  header h1 { font-size: 22px; font-weight: 700; letter-spacing: -.01em; }
  header .badge {
    font-size: 12px; padding: 3px 10px; border-radius: 20px;
    background: #e0e7ff; color: var(--primary); font-weight: 600;
  }

  /* Cards */
  .card {
    background: var(--card); border-radius: var(--radius);
    box-shadow: var(--shadow); border: 1px solid var(--border);
    padding: 18px 20px; margin-bottom: 14px;
  }
  .card-sm { padding: 12px 20px; }

  /* Directory row */
  .dir-row {
    display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
  }
  .dir-row label { font-weight: 600; font-size: 14px; white-space: nowrap; }
  .dir-row input[type="text"] {
    flex: 1; min-width: 260px; padding: 9px 12px;
    border: 1.5px solid var(--border); border-radius: 7px;
    font-size: 13px; font-family: inherit;
    transition: border-color .15s;
    background: #fafbfc;
  }
  .dir-row input[type="text"]:focus {
    outline: none; border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(99,102,241,.12);
  }
  .btn {
    padding: 9px 16px; border: none; border-radius: 7px;
    font-size: 13px; font-weight: 600; cursor: pointer;
    font-family: inherit; white-space: nowrap;
    transition: all .15s; display: inline-flex; align-items: center; gap: 5px;
  }
  .btn-ghost {
    background: #fff; color: var(--text); border: 1.5px solid var(--border);
  }
  .btn-ghost:hover { background: #f8fafc; border-color: #cbd5e1; }
  .btn-primary { background: var(--primary); color: #fff; }
  .btn-primary:hover { background: var(--primary-hover); }
  .btn-danger { background: var(--danger); color: #fff; }
  .btn-danger:hover { background: #b91c1c; }
  .btn-sm { padding: 5px 10px; font-size: 12px; border-radius: 5px; }
  .btn-xs { padding: 3px 8px; font-size: 11px; border-radius: 4px; }

  /* Toolbar */
  .toolbar {
    display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
  }
  .toolbar .sep { width: 1px; height: 22px; background: var(--border); margin: 0 6px; }
  .toolbar select {
    padding: 7px 10px; border: 1.5px solid var(--border); border-radius: 6px;
    font-size: 13px; font-family: inherit; background: #fff; cursor: pointer;
  }
  .toolbar select:focus { outline: none; border-color: var(--primary); }

  /* Breadcrumb navigation */
  .nav-bar {
    display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  }
  .nav-back {
    padding: 6px 12px; border: 1.5px solid var(--border); border-radius: 6px;
    background: #fff; color: var(--primary); font-size: 12px; font-weight: 600;
    cursor: pointer; font-family: inherit; transition: all .15s;
    white-space: nowrap;
  }
  .nav-back:hover { background: #eef2ff; border-color: var(--primary); }
  .nav-back:disabled { opacity: .35; cursor: default; }
  .nav-back:disabled:hover { background: #fff; border-color: var(--border); }

  .breadcrumb { display: flex; align-items: center; gap: 2px; font-size: 13px; flex-wrap: wrap; }
  .breadcrumb .bc-item {
    padding: 3px 8px; border-radius: 5px; cursor: pointer; color: var(--primary);
    font-weight: 500; transition: all .1s; white-space: nowrap;
  }
  .breadcrumb .bc-item:hover { background: #eef2ff; }
  .breadcrumb .bc-sep { color: #cbd5e1; font-weight: 300; margin: 0 1px; user-select: none; }
  .breadcrumb .bc-current { font-weight: 700; color: var(--text); padding: 3px 8px; white-space: nowrap; }

  /* Table */
  .table-wrap {
    max-height: 420px; overflow-y: auto; border-radius: var(--radius);
    border: 1px solid var(--border);
  }
  table {
    width: 100%; border-collapse: collapse; font-size: 13px;
    table-layout: fixed;
  }
  thead { position: sticky; top: 0; z-index: 1; }
  thead th {
    background: #f8fafc; padding: 10px 14px;
    font-weight: 600; font-size: 12px; color: var(--text2);
    text-transform: uppercase; letter-spacing: .03em;
    border-bottom: 1.5px solid var(--border); user-select: none;
    white-space: nowrap;
  }
  tbody td { padding: 8px 14px; border-bottom: 1px solid #f1f5f9; }
  tbody tr { transition: background .1s; }
  tbody tr:hover { background: #f8fafc; }
  tbody tr.row-dir { cursor: pointer; }

  /* Custom checkbox */
  .cbx { display: flex; align-items: center; justify-content: center; }
  .cbx input { display: none; }
  .cbx label {
    width: 20px; height: 20px; border-radius: 5px;
    border: 2px solid #cbd5e1; cursor: pointer; display: block;
    transition: all .15s; position: relative; flex-shrink: 0;
  }
  .cbx label:hover { border-color: var(--primary); }
  .cbx input:checked + label {
    background: var(--primary); border-color: var(--primary);
  }
  .cbx input:checked + label::after {
    content: ""; position: absolute; left: 5px; top: 2px;
    width: 6px; height: 10px; border: solid #fff;
    border-width: 0 2px 2px 0; transform: rotate(45deg);
  }

  /* 各列对齐: th 和 td 统一 text-align */
  .col-check { width: 58px; text-align: center; }
  .col-type  { width: 105px; text-align: center; }
  .col-size  { width: 120px; text-align: right; }
  .col-name  { text-align: left; }

  .type-badge {
    font-size: 12px; padding: 3px 10px; border-radius: 4px; font-weight: 600;
    display: inline-block; white-space: nowrap;
  }
  .type-dir { background: #dbeafe; color: #1d4ed8; }
  .type-file { background: #f1f5f9; color: #475569; }

  /* Sortable column headers */
  th.sortable { cursor: pointer; user-select: none; transition: background .12s; }
  th.sortable:hover { color: var(--text); background: #eef2ff; }
  th.sortable .sort-arrow { font-size: 10px; margin-left: 3px; opacity: .25; }
  th.sortable.active .sort-arrow { opacity: 1; color: var(--primary); }

  /* Clickable directory type-badge */
  .type-dir-clickable { cursor: pointer; transition: all .12s; }
  .type-dir-clickable:hover { background: #bfdbfe; color: #1e40af; transform: scale(1.06); }

  .size-col { color: var(--text2); font-variant-numeric: tabular-nums; font-size: 12px; }
  .name-col { font-weight: 500; word-break: break-all; }

  /* Footer row */
  .footer-row {
    display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
  }
  .footer-row label { font-weight: 600; font-size: 14px; }
  .footer-row input[type="text"] {
    padding: 9px 12px; border: 1.5px solid var(--border); border-radius: 7px;
    font-size: 13px; font-family: inherit; width: 220px;
    background: #fafbfc;
  }
  .footer-row input[type="text"]:focus {
    outline: none; border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(99,102,241,.12);
  }
  .output-path {
    font-size: 12px; color: var(--text2); margin-left: 4px;
    max-width: 360px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }

  /* Status */
  .status {
    display: flex; align-items: center; gap: 8px; padding: 10px 0 0;
    font-size: 13px; color: var(--text2);
  }
  .status .dot {
    width: 8px; height: 8px; border-radius: 99px; flex-shrink: 0;
  }
  .dot-ok { background: var(--success); }
  .dot-busy { background: #f59e0b; animation: pulse 1s infinite; }
  .dot-err { background: var(--danger); }
  @keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:.4 } }

  /* Toast */
  .toasts { position: fixed; top: 20px; right: 20px; z-index: 999; display: flex; flex-direction: column; gap: 8px; }
  .toast {
    padding: 12px 20px; border-radius: 8px; font-size: 13px; font-weight: 600;
    color: #fff; box-shadow: 0 4px 12px rgba(0,0,0,.15);
    animation: slideIn .25s ease; max-width: 400px;
  }
  .toast-success { background: var(--success); }
  .toast-error { background: var(--danger); }
  @keyframes slideIn { from { transform: translateX(100%); opacity: 0 } to { transform: translateX(0); opacity: 1 } }

  /* Empty state */
  .empty {
    text-align: center; padding: 40px 20px; color: var(--text2);
  }
  .empty .icon { font-size: 40px; margin-bottom: 8px; }

  /* Loading spinner */
  .spinner {
    display: inline-block; width: 16px; height: 16px; border: 2px solid #e2e8f0;
    border-top-color: var(--primary); border-radius: 50%; animation: spin .6s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg) } }

  /* indeterminate: 目录部分选中 — 白色底 + 居中蓝色正方形 */
  .cbx input:indeterminate + label {
    background: #fff; border-color: var(--primary);
  }
  .cbx input:indeterminate + label::after {
    content: ""; position: absolute; left: 50%; top: 50%;
    transform: translate(-50%, -50%);
    width: 9px; height: 9px; background: var(--primary); border-radius: 2px;
  }

  .exclude-count {
    font-size: 12px; color: var(--text2); background: #f1f5f9;
    padding: 3px 10px; border-radius: 20px; font-weight: 600;
  }
</style>
</head>
<body>
<div class="container">

  <header>
    <h1>压缩排除工具</h1>
    <span class="badge">v2</span>
  </header>

  <!-- 目录选择 -->
  <div class="card">
    <div class="dir-row">
      <label>根目录</label>
      <input type="text" id="dirPath" placeholder="输入要压缩的目录路径 …" spellcheck="false">
      <button class="btn btn-ghost" onclick="browseDir()">浏览…</button>
	      <button class="btn btn-ghost" onclick="resetAndScan()">刷新</button>
    </div>
  </div>

  <!-- 导航栏 -->
  <div class="card card-sm" id="navCard" style="display:none;">
    <div class="nav-bar">
      <button class="nav-back" id="backBtn" onclick="goBack()" disabled>← 返回上级</button>
      <span style="color:var(--text2);font-size:12px;margin:0 4px;">|</span>
      <div class="breadcrumb" id="breadcrumb"></div>
      <span style="flex:1;"></span>
      <span class="exclude-count" id="excludeCount">排除 0 项</span>
    </div>
  </div>

  <!-- 工具栏 -->
  <div class="card card-sm">
    <div class="toolbar">
      <button class="btn btn-ghost btn-sm" onclick="setAll(true)">全选（排除）</button>
      <button class="btn btn-ghost btn-sm" onclick="setAll(false)">全不选（包含）</button>
      <button class="btn btn-ghost btn-sm" onclick="invert()">反选</button>
      <span class="sep"></span>
      <label style="font-size:13px;font-weight:600;">格式</label>
      <select id="fmt" onchange="updateOutputPath()">
        <option value="tar.gz">tar.gz</option>
        <option value="tar.bz2">tar.bz2</option>
        <option value="tar.xz">tar.xz</option>
        <option value="zip">zip</option>
      </select>
    </div>
  </div>

  <!-- 文件列表 -->
  <div class="card" style="padding:0; overflow:hidden;">
    <div class="table-wrap" id="tableWrap">
      <table>
        <thead>
          <tr>
            <th class="col-check">排除</th>
            <th class="col-type">类型</th>
            <th class="col-size sortable active" id="sortSize" onclick="setSort('size')">大小 <span class="sort-arrow">▼</span></th>
            <th class="col-name sortable" id="sortName" onclick="setSort('name')">文件名 <span class="sort-arrow">▲</span></th>
          </tr>
        </thead>
        <tbody id="fileList"></tbody>
      </table>
    </div>
    <div class="empty" id="emptyState">
      <div class="icon">📂</div>
      <div>输入根目录路径后点击「刷新」扫描文件</div>
    </div>
  </div>

  <!-- 操作栏 -->
  <div class="card">
    <div class="footer-row">
      <label>输出文件名</label>
      <input type="text" id="outputName" oninput="updateOutputPath()" placeholder="archive">
      <span style="font-size:12px;color:var(--text2);">.<span id="extLabel">tar.gz</span></span>
      <span class="output-path" id="outputPathHint"></span>
      <span style="flex:1;"></span>
      <button class="btn btn-primary" id="compressBtn" onclick="startCompress()">
        开始压缩
      </button>
    </div>
    <div class="status" id="statusRow">
      <span class="dot dot-ok"></span>
      <span id="statusText">就绪</span>
    </div>
  </div>

</div>

<div class="toasts" id="toasts"></div>

<script>
// ── 状态 ──────────────────────────────────────────────
let rootPath = "";       // 压缩目标根目录
let navPath = "";        // 当前浏览目录（可能是 rootPath 的子目录）
let items = [];          // navPath 下的条目列表
let checked = {};        // 相对根目录的路径 → true(排除)
let sortField = "name";  // 当前排序列: "name" | "size"
let sortAsc = true;      // true = 升序

// ── DOM 引用 ──────────────────────────────────────────
const dirPathEl   = document.getElementById("dirPath");
const navCardEl   = document.getElementById("navCard");
const backBtnEl   = document.getElementById("backBtn");
const breadcrumbEl = document.getElementById("breadcrumb");
const excludeCountEl = document.getElementById("excludeCount");
const fileListEl  = document.getElementById("fileList");
const emptyStateEl = document.getElementById("emptyState");
const tableWrapEl = document.getElementById("tableWrap");
const outputNameEl = document.getElementById("outputName");
const compressBtnEl = document.getElementById("compressBtn");
const statusTextEl = document.getElementById("statusText");
const statusDot   = document.querySelector("#statusRow .dot");
const fmtEl       = document.getElementById("fmt");
const extLabelEl  = document.getElementById("extLabel");
const outputPathHintEl = document.getElementById("outputPathHint");

dirPathEl.addEventListener("keydown", e => { if (e.key === "Enter") resetAndScan(); });

// 文件夹 type-badge 点击 → 进入子目录
fileListEl.addEventListener("click", e => {
  const badge = e.target.closest(".type-dir-clickable");
  if (badge && badge.dataset.dir) {
    e.stopPropagation();
    navigateInto(badge.dataset.dir);
  }
});

// 面包屑点击 → 跳转层级
breadcrumbEl.addEventListener("click", e => {
  const item = e.target.closest(".bc-item");
  if (item && item.dataset.rel !== undefined) {
    goToBreadcrumb(item.dataset.rel);
  }
});

// 初始获取当前工作目录
fetch("/api/pwd").then(r => r.json()).then(d => {
  dirPathEl.value = d.path;
  resetAndScan();
});

// 浏览目录按钮：调用系统原生文件选择器
async function browseDir() {
  try {
    const resp = await fetch("/api/browse-dir");
    const data = await resp.json();
    if (data.path) {
      dirPathEl.value = data.path;
      resetAndScan();
    }
  } catch (e) {
    showToast("无法打开文件选择器: " + e.message, "error");
  }
}

// ── 路径工具 ──────────────────────────────────────────

function relPath(itemName) {
  // 当前条目相对于根目录的路径
  if (navPath === rootPath) return itemName;
  return navPath.substring(rootPath.length + 1) + "/" + itemName;
}

function parentDir(p) {
  p = p.replace(/\/+$/, "");
  const i = p.lastIndexOf("/");
  return i > 0 ? p.substring(0, i) : "/";
}

// ── 排序 ──────────────────────────────────────────────

function applySort() {
  if (sortField === "name") {
    items.sort((a, b) => {
      if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
      const cmp = a.name.localeCompare(b.name);
      return sortAsc ? cmp : -cmp;
    });
  } else {
    items.sort((a, b) => sortAsc ? a.size_bytes - b.size_bytes : b.size_bytes - a.size_bytes);
  }
}

function setSort(field) {
  if (sortField === field) {
    sortAsc = !sortAsc;
  } else {
    sortField = field;
    sortAsc = field === "name";
  }
  applySort();
  renderList();
  updateSortHeaders();
}

function updateSortHeaders() {
  const nh = document.getElementById("sortName");
  const sh = document.getElementById("sortSize");
  if (!nh || !sh) return;
  nh.classList.toggle("active", sortField === "name");
  sh.classList.toggle("active", sortField === "size");
  nh.querySelector(".sort-arrow").textContent = sortField === "name" ? (sortAsc ? "▲" : "▼") : "▼";
  sh.querySelector(".sort-arrow").textContent = sortField === "size" ? (sortAsc ? "▲" : "▼") : "▼";
}

// ── 扫描 ──────────────────────────────────────────────

// 重置到根目录并扫描
async function resetAndScan() {
  const path = dirPathEl.value.trim();
  if (!path) return;
  rootPath = path;
  navPath = path;
  checked = {};
  await doScan(path);
  renderNav();
}

// 导航进入子目录
async function navigateInto(dirName) {
  navPath = navPath + "/" + dirName;
  await doScan(navPath);
  renderNav();
}

// 返回上级目录（不超出 rootPath）
async function goBack() {
  if (navPath === rootPath) return;
  const parent = parentDir(navPath);
  navPath = parent.length >= rootPath.length ? parent : rootPath;
  await doScan(navPath);
  renderNav();
}

// 面包屑跳转到指定层级
async function goToBreadcrumb(rel) {
  navPath = rootPath + (rel ? "/" + rel : "");
  await doScan(navPath);
  renderNav();
}

async function doScan(path) {
  fileListEl.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:30px;">
    <span class="spinner"></span> 正在扫描 …</td></tr>`;
  emptyStateEl.style.display = "none";
  tableWrapEl.style.display = "block";

  try {
    const resp = await fetch("/api/scan?path=" + encodeURIComponent(path));
    const data = await resp.json();
    if (!data.success) {
      showToast(data.error || "扫描失败", "error");
      fileListEl.innerHTML = "";
      emptyStateEl.style.display = "block";
      tableWrapEl.style.display = "none";
      return;
    }
    items = data.items || [];
    applySort();

    // 如果是根目录扫描且没有设置输出名，自动填充
    if (path === rootPath && !outputNameEl.value) {
      outputNameEl.value = data.dir_name || "archive";
    }

    renderList();
    updateSortHeaders();
    updateOutputPath();
    updateExcludeCount();
    setStatus("ok", `已扫描 ${items.length} 个项目`);
  } catch (e) {
    fileListEl.innerHTML = "";
    emptyStateEl.style.display = "block";
    tableWrapEl.style.display = "none";
    showToast("无法连接到服务: " + e.message, "error");
  }
}

// ── 导航 UI ───────────────────────────────────────────

function renderNav() {
  const inSubdir = navPath !== rootPath;
  navCardEl.style.display = "block";
  backBtnEl.disabled = !inSubdir;

  // 面包屑
  if (!inSubdir) {
    breadcrumbEl.innerHTML = `<span class="bc-current">📂 ${escapeHtml(relPathName("")) || "根目录"}</span>`;
  } else {
    const rel = navPath.substring(rootPath.length + 1);
    const parts = rel.split("/");
    let html = `<span class="bc-item" data-rel="">📂 根目录</span>`;
    for (let i = 0; i < parts.length; i++) {
      html += ` <span class="bc-sep">›</span> `;
      if (i === parts.length - 1) {
        html += `<span class="bc-current">${escapeHtml(parts[i])}</span>`;
      } else {
        const accum = parts.slice(0, i + 1).join("/");
        html += `<span class="bc-item" data-rel="${escapeHtml(accum)}">${escapeHtml(parts[i])}</span>`;
      }
    }
    breadcrumbEl.innerHTML = html;
  }
  updateExcludeCount();
}

function relPathName(p) {
  // 返回 navPath 中某个条目的文件名，供面包屑用
  return p || (navPath === rootPath ? "" : navPath.split("/").pop());
}

// ── 渲染文件列表 ──────────────────────────────────────

// 目录复选框的视觉状态: "checked" | "indeterminate" | "unchecked"
// 优先看显式设置，再看祖先覆盖，最后看子孙状态
function getDirVisualState(dirRelPath) {
  const prefix = dirRelPath + "/";

  // 统计显式偏离默认值的子孙（同时存在 true 和 false 即可提前退出）
  let hasExplicitTrue = false;
  let hasExplicitFalse = false;
  for (const [key, val] of Object.entries(checked)) {
    if (key.startsWith(prefix)) {
      if (val) hasExplicitTrue = true;
      else hasExplicitFalse = true;
      if (hasExplicitTrue && hasExplicitFalse) break;
    }
  }

  // 目录自身的默认状态：显式设置优先，否则看祖先
  let baseChecked;
  if (dirRelPath in checked) {
    baseChecked = checked[dirRelPath] === true;
  } else {
    baseChecked = hasCheckedAncestor(dirRelPath);
  }

  if (baseChecked) {
    // 默认排除，但有子孙被显式取消 → indeterminate
    if (hasExplicitFalse) return "indeterminate";
    return "checked";
  } else {
    // 默认不排除，但有子孙被显式勾选 → indeterminate
    if (hasExplicitTrue) return "indeterminate";
    return "unchecked";
  }
}

// 条目是否在任何显式勾选的祖先目录下
function hasCheckedAncestor(rp) {
  const parts = rp.split("/");
  for (let i = 0; i < parts.length - 1; i++) {
    if (checked[parts.slice(0, i + 1).join("/")] === true) return true;
  }
  return false;
}

// 条目的有效勾选状态（考虑祖先覆盖）
function isEffectivelyChecked(rp) {
  if (rp in checked) return checked[rp] === true;
  return hasCheckedAncestor(rp);
}

// 级联设置目录自身 + 所有已知子孙
function toggleDirTree(dirRelPath, val) {
  checked[dirRelPath] = val;
  const prefix = dirRelPath + "/";
  for (const key of Object.keys(checked)) {
    if (key.startsWith(prefix)) checked[key] = val;
  }
}

function renderList() {
  if (items.length === 0) {
    fileListEl.innerHTML = "";
    emptyStateEl.style.display = "block";
    tableWrapEl.style.display = "none";
    return;
  }
  emptyStateEl.style.display = "none";
  tableWrapEl.style.display = "block";

  fileListEl.innerHTML = items.map((it, i) => {
    const rp = relPath(it.name);
    const isDir = it.type === "dir";
    const typeCls = isDir ? "type-dir type-dir-clickable" : "type-file";
    const typeLabel = isDir ? "目录" : "文件";
    const icon = isDir ? "📁" : "📄";

    // 目录用视觉状态（checked/indeterminate/unchecked），文件考虑祖先覆盖
    let chk, indeterminate = false;
    if (isDir) {
      const vs = getDirVisualState(rp);
      chk = vs === "checked";
      indeterminate = vs === "indeterminate";
    } else {
      chk = isEffectivelyChecked(rp);
    }

    // 文件夹的 type-badge 可点击进入，带 tooltip
    const typeHtml = isDir
      ? `<span class="type-badge ${typeCls}" data-dir="${escapeHtml(it.name)}" title="点击进入此文件夹">${icon} ${typeLabel}</span>`
      : `<span class="type-badge ${typeCls}">${icon} ${typeLabel}</span>`;

    return `<tr>
      <td class="col-check" onclick="event.stopPropagation()">
        <div class="cbx">
          <input type="checkbox" id="cb${i}" ${chk ? "checked" : ""}
                 ${indeterminate ? 'data-indeterminate="1"' : ""}
                 onchange="toggleCheck(${i})">
          <label for="cb${i}"></label>
        </div>
      </td>
      <td class="col-type">${typeHtml}</td>
      <td class="col-size">${escapeHtml(it.size_str)}</td>
      <td class="col-name">${escapeHtml(it.name)}</td>
    </tr>`;
  }).join("");

  // 为目录复选框设置 indeterminate 视觉状态
  fileListEl.querySelectorAll("input[data-indeterminate]").forEach(cb => {
    cb.indeterminate = true;
  });
}

function toggleCheck(i) {
  const it = items[i];
  const rp = relPath(it.name);
  if (it.type === "dir") {
    const cur = getDirVisualState(rp);
    toggleDirTree(rp, cur !== "checked");
  } else {
    checked[rp] = !isEffectivelyChecked(rp);
  }
  renderList();
  updateExcludeCount();
}

function setAll(val) {
  items.forEach(it => {
    const rp = relPath(it.name);
    if (it.type === "dir") toggleDirTree(rp, val);
    else checked[rp] = val;
  });
  renderList();
  updateExcludeCount();
  const label = val ? "排除全部" : "包含全部";
  setStatus("ok", `已设置: ${label} (当前目录 ${items.length} 项)`);
}

function invert() {
  items.forEach(it => {
    const rp = relPath(it.name);
    if (it.type === "dir") {
      const cur = getDirVisualState(rp);
      toggleDirTree(rp, cur !== "checked");
    } else {
      checked[rp] = !isEffectivelyChecked(rp);
    }
  });
  renderList();
  updateExcludeCount();
  setStatus("ok", "已反选当前目录");
}

function updateExcludeCount() {
  const total = Object.values(checked).filter(v => v).length;
  excludeCountEl.textContent = `排除 ${total} 项`;
}

// ── 压缩 ──────────────────────────────────────────────

async function startCompress() {
  const excludeNames = Object.entries(checked)
    .filter(([_, v]) => v)
    .map(([n]) => n);
  const outputName = outputNameEl.value.trim();

  if (!outputName) { showToast("请输入输出文件名", "error"); return; }
  if (!rootPath) { showToast("请先扫描根目录", "error"); return; }

  if (excludeNames.length === 0) {
    if (!confirm("没有勾选任何排除项，将压缩目录内全部内容。\n\n确定继续？")) return;
  }

  const fmt = fmtEl.value;
  const outputFile = parentDir(rootPath) + "/" + outputName + "." + fmt;

  try {
    const check = await fetch("/api/exists?path=" + encodeURIComponent(outputFile));
    const cd = await check.json();
    if (cd.exists) {
      if (!confirm("文件已存在:\n" + outputFile + "\n\n是否覆盖？")) return;
    }
  } catch (_) {}

  compressBtnEl.disabled = true;
  compressBtnEl.textContent = "压缩中 …";
  setStatus("busy", "正在压缩 …");

  try {
    await fetch("/api/compress", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: rootPath,
        format: fmt,
        output_name: outputName,
        exclude: excludeNames,
      }),
    });
    await pollStatus();
  } catch (e) {
    showToast("请求失败: " + e.message, "error");
    resetCompressUI();
  }
}

async function pollStatus() {
  try {
    const resp = await fetch("/api/status");
    const st = await resp.json();
    if (st.running) {
      setStatus("busy", st.message || "压缩中 …");
      setTimeout(pollStatus, 600);
    } else if (st.success) {
      setStatus("ok", st.message);
      showToast(st.message, "success");
      resetCompressUI();
    } else {
      setStatus("err", st.message || "压缩失败");
      showToast(st.message || "压缩失败", "error");
      resetCompressUI();
    }
  } catch (e) {
    setStatus("err", "状态查询失败");
    resetCompressUI();
  }
}

function resetCompressUI() {
  compressBtnEl.disabled = false;
  compressBtnEl.textContent = "开始压缩";
}

// ── 输出路径 ──────────────────────────────────────────

function updateOutputPath() {
  extLabelEl.textContent = fmtEl.value;
  if (!rootPath || !outputNameEl.value) {
    outputPathHintEl.textContent = "";
    return;
  }
  const outFile = parentDir(rootPath) + "/" + outputNameEl.value + "." + fmtEl.value;
  outputPathHintEl.textContent = "→ " + outFile;
}

// ── 状态与提示 ────────────────────────────────────────

function setStatus(type, msg) {
  statusTextEl.textContent = msg;
  statusDot.className = "dot dot-" + type;
}

function showToast(msg, type) {
  const toast = document.createElement("div");
  toast.className = "toast toast-" + type;
  toast.textContent = msg;
  document.getElementById("toasts").appendChild(toast);
  setTimeout(() => { toast.remove(); }, 3500);
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

</script>
</body>
</html>"""

# ── 工具函数 ────────────────────────────────────────────


def format_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def get_dir_size(path: str) -> int:
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat().st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total += get_dir_size(entry.path)
                except (PermissionError, OSError):
                    pass
    except (PermissionError, OSError):
        pass
    return total


def run_compress(target_dir: str, fmt: str, output_file: str, exclude_items: list):
    """在后台线程中运行压缩命令"""
    set_state(running=True, success=None, message="正在压缩 …", output_file="")

    try:
        if fmt == "zip":
            cmd = ["zip", "-r", output_file, "."]
            for item in exclude_items:
                # zip: -x 'dirname' 不递归，但 'dirname/*' 递归排除该目录下所有内容
                full = os.path.join(target_dir, item)
                if os.path.isdir(full):
                    cmd.extend(["-x", f"./{item}/*"])
                else:
                    cmd.extend(["-x", f"./{item}"])
        else:
            # tar: --exclude='./dirname' 默认递归排除目录内所有内容
            compress_flag = {"tar.gz": "z", "tar.bz2": "j", "tar.xz": "J"}
            flag = compress_flag.get(fmt, "z")
            cmd = ["tar", f"-c{flag}f", output_file]
            for item in exclude_items:
                cmd.append(f"--exclude=./{item}")
            cmd.append(".")

        proc = subprocess.run(
            cmd,
            cwd=target_dir,
            capture_output=True,
            text=True,
        )

        if proc.returncode == 0:
            size = os.path.getsize(output_file)
            msg = f"压缩完成: {os.path.basename(output_file)} ({format_size(size)})"
            set_state(running=False, success=True, message=msg, output_file=output_file)
        else:
            err = proc.stderr.strip() or "未知错误"
            set_state(running=False, success=False, message=f"压缩失败: {err}", output_file="")

    except Exception as e:
        set_state(running=False, success=False, message=f"压缩异常: {e}", output_file="")


# ── HTTP 处理器 ─────────────────────────────────────────


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # 关闭访问日志

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode("utf-8") if length else ""

    # ── 路由 ──────────────────────────────────────────

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._send_html(HTML)

        elif path == "/api/pwd":
            self._send_json({"path": os.getcwd()})

        elif path == "/api/scan":
            target = unquote(qs.get("path", [""])[0])
            if not target or not os.path.isdir(target):
                self._send_json({"success": False, "error": "无效的目录路径"}, 400)
                return

            items = []
            try:
                for name in sorted(os.listdir(target), key=lambda x: (not os.path.isdir(os.path.join(target, x)), x.lower())):
                    full = os.path.join(target, name)
                    try:
                        is_dir = os.path.isdir(full)
                        if is_dir:
                            size = get_dir_size(full)
                        else:
                            size = os.path.getsize(full)
                        items.append({
                            "name": name,
                            "type": "dir" if is_dir else "file",
                            "size_bytes": size,
                            "size_str": format_size(size),
                        })
                    except (PermissionError, OSError):
                        pass
            except PermissionError:
                self._send_json({"success": False, "error": "没有权限访问该目录"}, 403)
                return

            self._send_json({
                "success": True,
                "path": target,
                "dir_name": os.path.basename(target) or "archive",
                "items": items,
            })

        elif path == "/api/status":
            self._send_json(get_state())

        elif path == "/api/exists":
            target = unquote(qs.get("path", [""])[0])
            self._send_json({"exists": os.path.exists(target) if target else False})

        elif path == "/api/browse-dir":
            selected = None
            for picker in ["zenity", "kdialog"]:
                try:
                    flag = "--directory" if picker == "zenity" else "--getexistingdirectory"
                    result = subprocess.run(
                        [picker, flag],
                        capture_output=True, text=True, timeout=60,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        selected = result.stdout.strip()
                        break
                except Exception:
                    continue
            if selected:
                self._send_json({"path": selected})
            else:
                self._send_json({"error": "未选择任何目录"}, 200)

        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/compress":
            try:
                data = json.loads(self._read_body())
            except json.JSONDecodeError:
                self._send_json({"success": False, "error": "无效的 JSON"}, 400)
                return

            target_dir = data.get("path", "")
            fmt = data.get("format", "tar.gz")
            output_name = data.get("output_name", "archive")
            exclude_items = data.get("exclude", [])

            if not target_dir or not os.path.isdir(target_dir):
                self._send_json({"success": False, "error": "无效的目录路径"}, 400)
                return

            if fmt not in ("tar.gz", "tar.bz2", "tar.xz", "zip"):
                self._send_json({"success": False, "error": "不支持的压缩格式"}, 400)
                return

            output_dir = os.path.dirname(os.path.abspath(target_dir))
            output_file = os.path.join(output_dir, f"{output_name}.{fmt}")

            if get_state()["running"]:
                self._send_json({"success": False, "error": "已有压缩任务正在运行"}, 409)
                return

            thread = threading.Thread(
                target=run_compress,
                args=(target_dir, fmt, output_file, exclude_items),
                daemon=True,
            )
            thread.start()

            self._send_json({"success": True, "message": "压缩已开始"})

        else:
            self._send_json({"error": "Not found"}, 404)


# ── 入口 ────────────────────────────────────────────────


def find_free_port(start=8765):
    """找一个空闲端口"""
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


def main():
    port = find_free_port()
    server = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"

    print(f"  压缩排除工具已启动")
    print(f"  打开浏览器: {url}")
    print(f"  按 Ctrl+C 退出")
    print()

    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已退出")
        server.shutdown()


if __name__ == "__main__":
    main()
