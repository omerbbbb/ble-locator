"""
generate_guide.py — BLE Locator code guide generator.

Run from the project root:
    python docs/generate_guide.py

Outputs:  docs/code_guide.html  (open in any browser, no server needed)

How it works:
  - Walks every .py file in the project (excluding .venv / build / dist)
  - Uses the `ast` module to extract module docstrings, class names +
    docstrings, and top-level function names + docstrings
  - Injects the data into a self-contained HTML page with a searchable
    folder tree and a detail panel

To add explanations: add or improve docstrings in the source files.
The guide re-generates from them automatically.
"""

import ast
import json
import os
import textwrap
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent

SKIP_DIRS = {".venv", "build", "dist", "__pycache__", ".git", "data", "docs"}

FOLDER_DESCRIPTIONS = {
    "core":        "Shared foundation — data shapes, contracts (interfaces), platform detection. Every other layer depends on this; it depends on nothing.",
    "sensor":      "Hardware scanners — BLE (Bluetooth) and WiFi. Run in background threads. Produce SignalReading objects and cache them in a registry.",
    "filtering":   "Signal smoothing — Kalman filters reduce the jitter in raw RSSI readings before they reach the positioning engine.",
    "engine":      "Pure algorithms — converts filtered RSSI to metres, then solves for (x, y) from 3+ distances using Least Squares.",
    "services":    "Business logic — PositioningService orchestrates the full pipeline each tick; AnchorStore is the in-memory anchor database.",
    "storage":     "Persistence — saves and loads anchor calibration to/from ~/Library/Application Support/BLE Locator/calibration.json.",
    "traceability":"Observer / logging — EventBus lets any component emit typed events that listeners can observe without coupling.",
    "ui":          "All PyQt6 widgets — each widget is passive (receives data, draws it). main_window owns the 1-second tick that drives everything.",
}

FOLDER_COLORS = {
    "core":         "#6b7280",
    "sensor":       "#3b82f6",
    "filtering":    "#06b6d4",
    "engine":       "#8b5cf6",
    "services":     "#f59e0b",
    "storage":      "#ef4444",
    "traceability": "#ec4899",
    "ui":           "#10b981",
}

# ── AST helpers ───────────────────────────────────────────────────────────────

def _docstring(node) -> str:
    if (node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
        raw = node.body[0].value.value
        return textwrap.dedent(raw).strip().split("\n\n")[0].replace("\n", " ")
    return ""


def parse_file(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception as e:
        return {"error": str(e), "module_doc": "", "items": []}

    module_doc = _docstring(tree)
    items = []
    seen = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            key = ("function", node.name)
            if key not in seen:
                seen.add(key)
                items.append({"kind": "function", "name": node.name,
                               "doc": _docstring(node), "line": node.lineno})
        elif isinstance(node, ast.ClassDef):
            key = ("class", node.name)
            if key not in seen:
                seen.add(key)
                items.append({"kind": "class", "name": node.name,
                               "doc": _docstring(node), "line": node.lineno})

    return {"module_doc": module_doc, "items": items}


def collect() -> dict:
    result = {}
    for py_file in sorted(ROOT.rglob("*.py")):
        parts = py_file.relative_to(ROOT).parts
        if any(p in SKIP_DIRS for p in parts):
            continue
        if py_file.name == "__init__.py":
            continue
        rel = py_file.relative_to(ROOT).as_posix()
        result[rel] = parse_file(py_file)
    return result


# ── HTML — written as a raw string; use __TOKEN__ for injected values ─────────

def build_html(data: dict, generated: str) -> str:
    data_js        = json.dumps(data, ensure_ascii=False, indent=2)
    folder_desc_js = json.dumps(FOLDER_DESCRIPTIONS, ensure_ascii=False)
    folder_color_js = json.dumps(FOLDER_COLORS, ensure_ascii=False)

    return r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BLE Locator — Code Guide</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#0f172a;color:#cbd5e1;font-size:14px;display:flex;
     flex-direction:column;height:100vh;overflow:hidden;}
header{padding:10px 16px;background:#1e293b;border-bottom:1px solid #334155;
       display:flex;align-items:center;gap:12px;flex-shrink:0;}
header h1{font-size:15px;font-weight:600;color:#f1f5f9;}
header .gen{font-size:12px;color:#64748b;margin-left:auto;}
#search{flex:1;max-width:340px;padding:5px 10px;background:#0f172a;
        border:1px solid #334155;border-radius:6px;color:#f1f5f9;font-size:13px;}
#search::placeholder{color:#64748b;}
.main{display:flex;flex:1;overflow:hidden;}
.tree{width:280px;flex-shrink:0;overflow-y:auto;border-right:1px solid #1e293b;
      padding:8px 4px;background:#0f172a;}
.folder-header{display:flex;align-items:center;gap:6px;padding:5px 8px;
               border-radius:6px;cursor:pointer;user-select:none;}
.folder-header:hover{background:#1e293b;}
.folder-caret{font-size:12px;flex-shrink:0;}
.folder-name{font-size:13px;font-weight:600;}
.folder-hint{font-size:10px;color:#64748b;}
.folder-children{margin-left:16px;border-left:1px solid #1e293b;
                 padding-left:6px;display:none;}
.folder-children.open{display:block;}
.file-row{display:flex;align-items:center;gap:6px;padding:3px 8px;
          border-radius:6px;cursor:pointer;font-size:12px;color:#94a3b8;}
.file-row:hover,.file-row.sel{background:#1e3a5f;color:#60a5fa;}
.detail{flex:1;overflow-y:auto;padding:20px 24px;}
.detail-empty{display:flex;align-items:center;justify-content:center;
              height:80%;color:#475569;font-size:13px;}
.folder-banner{background:#1e293b;border-radius:8px;padding:12px 16px;
               margin-bottom:16px;border-left:3px solid;}
.folder-banner-name{font-size:16px;font-weight:600;margin-bottom:4px;}
.folder-banner-desc{font-size:13px;color:#94a3b8;line-height:1.55;}
.dp-badge{display:inline-block;font-size:10px;font-weight:600;
          padding:2px 8px;border-radius:10px;margin-bottom:8px;}
.dp-title{font-size:15px;font-weight:600;color:#f1f5f9;margin-bottom:4px;}
.dp-path{font-family:ui-monospace,monospace;font-size:11px;color:#60a5fa;
         background:#1e3a5f;padding:2px 8px;border-radius:4px;
         display:inline-block;margin-bottom:10px;cursor:pointer;user-select:all;}
.dp-path:hover{text-decoration:underline;}
.dp-doc{font-size:13px;color:#94a3b8;line-height:1.65;margin-bottom:14px;}
.dp-no-doc{font-size:12px;color:#475569;font-style:italic;margin-bottom:14px;}
.divider{border:none;border-top:1px solid #1e293b;margin:12px 0;}
.items-label{font-size:10px;text-transform:uppercase;letter-spacing:.06em;
             color:#475569;font-weight:600;margin-bottom:8px;}
.item-card{background:#1e293b;border-radius:6px;padding:8px 12px;margin-bottom:5px;}
.item-fn{border-left:3px solid #3b82f6;}
.item-cl{border-left:3px solid #a78bfa;}
.item-sig{font-family:ui-monospace,monospace;font-size:12px;color:#93c5fd;}
.item-doc{font-size:12px;color:#64748b;margin-top:4px;line-height:1.5;}
.item-no-doc{font-size:11px;color:#374151;font-style:italic;margin-top:3px;}
</style>
</head>
<body>

<header>
  <h1>BLE Locator — Code Guide</h1>
  <input id="search" type="text" placeholder="Search files, classes, functions..."
         oninput="onSearch()" autocomplete="off"/>
  <span class="gen">Generated """ + generated + r"""</span>
</header>

<div class="main">
  <div class="tree" id="tree"></div>
  <div class="detail" id="detail">
    <div class="detail-empty">Select a file or folder from the tree.</div>
  </div>
</div>

<script>
const DATA        = """ + data_js        + r""";
const FOLDER_DESC  = """ + folder_desc_js  + r""";
const FOLDER_COLOR = """ + folder_color_js + r""";

const openFolders = new Set(['sensor','ui','core','engine','filtering']);

// ── tree ─────────────────────────────────────────────────────────────────────
function buildTree(filterText) {
  const tree = document.getElementById('tree');
  tree.innerHTML = '';
  const ft = (filterText || '').toLowerCase();

  const folders = {};
  const topFiles = [];

  for (const path of Object.keys(DATA)) {
    const slash = path.indexOf('/');
    if (slash === -1) { topFiles.push(path); continue; }
    const folder = path.slice(0, slash);
    (folders[folder] = folders[folder] || []).push(path);
  }

  for (const [folder, files] of Object.entries(folders)) {
    const matching = ft ? files.filter(f => matchesSearch(f, ft)) : files;
    if (ft && matching.length === 0) continue;

    const color  = FOLDER_COLOR[folder] || '#888';
    const isOpen = openFolders.has(folder) || !!ft;
    const hint   = (FOLDER_DESC[folder] || '').split(' — ')[0];

    const wrap   = document.createElement('div');
    const header = document.createElement('div');
    header.className = 'folder-header';

    const caret = document.createElement('span');
    caret.className = 'folder-caret';
    caret.textContent = isOpen ? '▾' : '▸';
    caret.style.color = color;

    const nameEl = document.createElement('span');
    nameEl.className = 'folder-name';
    nameEl.style.color = color;
    nameEl.textContent = folder + '/';

    const hintEl = document.createElement('span');
    hintEl.className = 'folder-hint';
    hintEl.textContent = hint;

    header.appendChild(caret);
    header.appendChild(nameEl);
    header.appendChild(hintEl);

    const children = document.createElement('div');
    children.className = 'folder-children' + (isOpen ? ' open' : '');

    header.onclick = () => {
      const o = children.classList.toggle('open');
      caret.textContent = o ? '▾' : '▸';
      if (o) openFolders.add(folder); else openFolders.delete(folder);
    };
    header.ondblclick = e => { e.stopPropagation(); showFolder(folder); };

    (ft ? matching : files).forEach(f => children.appendChild(makeFileRow(f, color)));
    wrap.appendChild(header);
    wrap.appendChild(children);
    tree.appendChild(wrap);
  }

  topFiles.forEach(f => {
    if (ft && !matchesSearch(f, ft)) return;
    tree.appendChild(makeFileRow(f, '#f59e0b'));
  });
}

function makeFileRow(path, color) {
  const row = document.createElement('div');
  row.className = 'file-row';
  row.dataset.path = path;
  const dot = document.createElement('span');
  dot.style.color = color;
  dot.textContent = '◆';
  const label = document.createElement('span');
  label.textContent = path.split('/').pop();
  row.appendChild(dot);
  row.appendChild(label);
  row.onclick = () => showFile(path);
  return row;
}

// ── search ───────────────────────────────────────────────────────────────────
function matchesSearch(path, term) {
  if (path.includes(term)) return true;
  const info = DATA[path];
  if (!info) return false;
  if ((info.module_doc || '').toLowerCase().includes(term)) return true;
  return (info.items || []).some(it =>
    it.name.toLowerCase().includes(term) ||
    (it.doc || '').toLowerCase().includes(term)
  );
}

function onSearch() {
  buildTree(document.getElementById('search').value.trim());
}

// ── detail — folder ──────────────────────────────────────────────────────────
function showFolder(folder) {
  const color = FOLDER_COLOR[folder] || '#888';
  const desc  = FOLDER_DESC[folder] || '';
  const files = Object.keys(DATA).filter(p => p.startsWith(folder + '/'));

  let html =
    `<div class="folder-banner" style="border-color:${color}">` +
    `<div class="folder-banner-name" style="color:${color}">${folder}/</div>` +
    `<div class="folder-banner-desc">${desc}</div></div>` +
    `<div class="items-label">Files in ${folder}/</div>`;

  html += files.map(f => {
    const info = DATA[f];
    const fname = f.split('/').pop();
    const doc = info && info.module_doc
      ? info.module_doc
      : '<span class="item-no-doc">No module docstring yet.</span>';
    return `<div class="item-card item-fn" style="cursor:pointer" onclick="showFile('${f}')">` +
      `<div class="item-sig">${fname}</div>` +
      `<div class="item-doc">${doc}</div></div>`;
  }).join('');

  document.getElementById('detail').innerHTML = html;
}

// ── detail — file ────────────────────────────────────────────────────────────
function showFile(path) {
  document.querySelectorAll('.file-row').forEach(r =>
    r.classList.toggle('sel', r.dataset.path === path));

  const info   = DATA[path];
  if (!info) return;
  const folder = path.split('/')[0];
  const color  = FOLDER_COLOR[folder] || '#888';
  const fname  = path.split('/').pop();

  let html =
    `<span class="dp-badge" style="background:${color}22;color:${color}">${folder}</span>` +
    `<div class="dp-title">${fname}</div>` +
    `<div class="dp-path" title="click to copy" onclick="copyPath('${path}')">${path}</div>`;

  if (info.error) {
    html += `<div class="dp-no-doc">Parse error: ${info.error}</div>`;
  } else if (info.module_doc) {
    html += `<div class="dp-doc">${info.module_doc}</div>`;
  } else {
    html += `<div class="dp-no-doc">No module-level docstring — add one to the top of the file to improve this guide.</div>`;
  }

  const classes = (info.items || []).filter(i => i.kind === 'class');
  const fns     = (info.items || []).filter(i => i.kind === 'function');

  if (classes.length) {
    html += `<hr class="divider"><div class="items-label">Classes</div>`;
    html += classes.map(c =>
      `<div class="item-card item-cl">` +
      `<div class="item-sig">class ${c.name} <span style="color:#475569;font-size:10px">line ${c.line}</span></div>` +
      (c.doc
        ? `<div class="item-doc">${c.doc}</div>`
        : `<div class="item-no-doc">No docstring</div>`) +
      `</div>`
    ).join('');
  }

  if (fns.length) {
    html += `<hr class="divider"><div class="items-label">Functions & methods</div>`;
    html += fns.map(f =>
      `<div class="item-card item-fn">` +
      `<div class="item-sig">def ${f.name}() <span style="color:#475569;font-size:10px">line ${f.line}</span></div>` +
      (f.doc
        ? `<div class="item-doc">${f.doc}</div>`
        : `<div class="item-no-doc">No docstring</div>`) +
      `</div>`
    ).join('');
  }

  document.getElementById('detail').innerHTML = html;
}

function copyPath(path) {
  navigator.clipboard && navigator.clipboard.writeText(path);
  const el = document.querySelector('.dp-path');
  if (el) {
    const orig = el.textContent;
    el.textContent = '✓ copied';
    setTimeout(() => { el.textContent = orig; }, 1400);
  }
}

buildTree();
</script>
</body>
</html>"""


def generate():
    data = collect()
    out_path = ROOT / "docs" / "code_guide.html"
    out_path.parent.mkdir(exist_ok=True)

    html = build_html(data, datetime.now().strftime("%Y-%m-%d %H:%M"))
    out_path.write_text(html, encoding="utf-8")

    print(f"Generated: {out_path}")
    print(f"  {len(data)} files indexed")
    print(f"  Open in browser: open \"{out_path}\"")


if __name__ == "__main__":
    generate()
