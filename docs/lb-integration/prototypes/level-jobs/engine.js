// Level Workbench 投影引擎（原型）：與 MOST_LB_DATA_CONTRACT_SPEC v1.1 同構的簡化實作，純函式、無 DOM。
const WB_ENGINE = (function () {
  const COLUMNS = ["task_id","action","part_id","group","atomic_group","duration","predecessors","station_name","action_type",
    "complexity_level","adjustable","fixed_station","offline_flag","tool_id","tool_action","divisible","p2","quantity","segment",
    "qty_scope","duration_basis","source_wi_row_id","role_type","general_role"];
  const ROLE_ACTION = { take_unit: "take", scanner: "scan", transport: "transport" };
  const uuid = (seq) => "00000000-0000-4000-8000-" + String(seq).padStart(12, "0");
  const ms = (tmu) => Math.round(tmu * 36);
  const isInt = (x) => Number.isInteger(x);
  const numOf = (label) => parseInt(String(label).replace(/\D/g, ""), 10);

  function tagsOf(state, id) { return state.tags[id] || {}; }
  function isGeneral(state, id) { return !!tagsOf(state, id).general_role || !!tagsOf(state, id).is_general; }
  function isToolHeld(row) { return !!(row.tool || row.objTool); }
  function chainOf(state, id) { return state.chains.find((c) => c.members.includes(id)) || null; }
  function cubLabelOf(state, id) { const c = chainOf(state, id); if (!c) return null; if (c.kind === "cub") return c.label; return tagsOf(state, id).cub || null; }

  // ── §3.3 分桶 ────────────────────────────────────────────────────────────
  function decompose(row, errs) {
    const s = row.slots, rep = row.rep || {};
    if ((rep[2] || 1) > 1) errs.push(["E_TOOL_ACQUIRE_REPEAT", row.id, "取得段（G）不得 repeat"]);
    const U = [3, 4, 5].filter((i) => s[i] > 0);
    const R = U.filter((i) => (rep[i] || 1) > 1);
    let N = 1;
    if (R.length) {
      const ns = new Set(R.map((i) => rep[i]));
      if (ns.size > 1) errs.push(["E_REPEAT_MIXED", row.id, "重複區塊 R 內 repeat 值不一致"]);
      N = rep[R[0]];
      const first = U.indexOf(R[0]), last = U.indexOf(R[R.length - 1]);
      if (last - first + 1 !== R.length) errs.push(["E_REPEAT_NONCONTIGUOUS", row.id, "use 段重複格之間夾著不重複的動作"]);
    }
    const pre = R.length ? U.filter((i) => !R.includes(i) && i < R[0]) : [];
    const post = R.length ? U.filter((i) => !R.includes(i) && i > R[R.length - 1]) : [];
    const setup_pre = s[0] + s[1] + s[2] + pre.reduce((a, i) => a + s[i], 0);
    const use_once = R.length ? R.reduce((a, i) => a + s[i] / N, 0) : (s[3] + s[4] + s[5]);
    const setup_post = post.reduce((a, i) => a + s[i], 0) + s[6];
    if (Math.abs(setup_pre + N * use_once + setup_post - row.tmu) > 1e-6) errs.push(["E_TMU_DECOMPOSITION", row.id, "分桶守恆失敗"]);
    return { setup_pre, use_once, setup_post, N, R };
  }

  // ── §4 工具生命週期（每個 chain 一台狀態機）────────────────────────────
  function resolveTools(rows, state, errs) {
    const byId = Object.fromEntries(rows.map((r) => [r.id, r]));
    const plans = {}; const episodes = [];
    for (const ch of state.chains) {
      const held = new Map(); // tool -> episode
      const seq = ch.members.map((id) => byId[id]);
      seq.forEach((row, idx) => {
        const T = row.tool || row.objTool;
        if (!T || isGeneral(state, row.id)) { plans[row.id] = { parts: ["single"], tool: null }; return; }
        const holding = held.has(T);
        if (row.tool && !holding) {                       // IMPLICIT_ACQUIRE（Pattern B）
          const later = seq.slice(idx + 1).findIndex((r) => (r.objTool === T && r.kind === "GM") || r.tool === T || r.objTool === T);
          const laterRow = later >= 0 ? seq[idx + 1 + later] : null;
          const releasedLater = laterRow && laterRow.objTool === T && laterRow.kind === "GM";
          const ep = { tool: T, acquire: [row.id, 0], uses: [[row.id, 1]], release: null };
          episodes.push(ep);
          if (releasedLater) { plans[row.id] = { parts: ["acquire", "use"], tool: T, ep }; held.set(T, ep); }
          else { plans[row.id] = { parts: ["acquire", "use", "release"], tool: T, ep }; ep.release = [row.id, 2]; }
        } else if (row.tool && holding) {                 // USE
          const ep = held.get(T); ep.uses.push([row.id, 0]);
          plans[row.id] = { parts: ["use"], tool: T, ep };
        } else if (row.objTool && !holding) {             // ACQUIRE（Pattern A）
          if (row.kind !== "GM") { plans[row.id] = { parts: ["single"], tool: null }; return; }
          const ep = { tool: T, acquire: [row.id, 0], uses: [], release: null };
          episodes.push(ep); held.set(T, ep);
          plans[row.id] = { parts: ["acquire"], tool: T, ep };
        } else if (row.objTool && holding) {              // RELEASE（GM）／USE（CM）
          const ep = held.get(T);
          if (row.kind === "GM") { ep.release = [row.id, 0]; held.delete(T); plans[row.id] = { parts: ["release"], tool: T, ep }; }
          else { ep.uses.push([row.id, 0]); plans[row.id] = { parts: ["use"], tool: T, ep }; }
        }
      });
      for (const [T, ep] of held) {
        const last = ep.uses.length ? ep.uses[ep.uses.length - 1][0] : ep.acquire[0];
        errs.push(["E_TOOL_NOT_RELEASED", last, `工具 ${T} 在 chain 結束時仍持有（拿了沒放）`]);
      }
    }
    return { plans, episodes };
  }

  // ── 主投影 ───────────────────────────────────────────────────────────────
  function project(rows, state) {
    const errs = [], warns = [];
    const byId = Object.fromEntries(rows.map((r) => [r.id, r]));
    const placed = new Set(state.chains.flatMap((c) => c.members));
    const labelsMap = state.labels || {};
    for (const r of rows) {
      if (!placed.has(r.id) && !isGeneral(state, r.id)) errs.push(["E_LEVEL_INVALID", r.id, "尚未編排（R3_ORPHAN：無歸屬、無層）"]);
      if (isGeneral(state, r.id)) {
        const t = tagsOf(state, r.id);
        if (chainOf(state, r.id) && chainOf(state, r.id).kind !== "single") errs.push(["E_GENERAL_IN_GROUP", r.id, "general 列不得在 sub/cub 內"]);
        if (t.wcub) errs.push(["E_GENERAL_IN_GROUP", r.id, "general 列不得在 wcub 內"]);
        if (!t.general_role) errs.push(["E_GENERAL_ROLE_MISSING", r.id, "general 列缺 general_role"]);
        if (isToolHeld(r)) warns.push(["W_GENERAL_WITH_TOOL", r.id, "general 列持工具：以單列輸出，工具欄丟棄"]);
      }
    }
    const { plans, episodes } = resolveTools(rows, state, errs);

    // 建 node（task 雛形）
    const nodes = []; const nodeKey = (id, i) => `${id}#${i}`;
    const nodeByKey = {};
    const autoGroupOf = (r) => 9000 + r.seq;
    for (const r of rows) {
      if (!placed.has(r.id) && !isGeneral(state, r.id)) continue;
      const t = tagsOf(state, r.id);
      const general = isGeneral(state, r.id);
      const plan = general ? { parts: ["single"], tool: null } : (plans[r.id] || { parts: ["single"], tool: null });
      const toolHeld = !general && isToolHeld(r);
      const dec = toolHeld ? decompose(r, errs) : null;
      const freqInt = isInt(r.freq);
      const cubLabel = general ? null : cubLabelOf(state, r.id);
      let groupId = cubLabel ? numOf(cubLabel) : null;
      const wcub = t.wcub ? numOf(t.wcub) : null;
      const base = {
        row: r, wi: r.wi, part: general ? "General" : r.part, offline: !!t.offline, pin: t.pin || null,
        role_type: r.kind === "CM" && r.xsec >= 1 ? "machine" : "human", general_role: t.general_role || "", atomic: wcub,
        segment: t.segment || "", divisible: !!t.splittable, action_label: t.action_type || labelsMap[r.id] || "",
      };
      const mk = (idx, partName, extra) => { const n = Object.assign({ key: nodeKey(r.id, idx), rowId: r.id, seq: r.seq, idx, partName }, base, extra); nodes.push(n); nodeByKey[n.key] = n; return n; };
      if (!toolHeld) {
        let q = 1, scope = "", basis = "", dur = r.tmu;
        if (!general && r.freq > 1 && freqInt) { q = r.freq; scope = "cyclic"; basis = "once"; if (!groupId) { groupId = autoGroupOf(r); warns.push(["W_AUTO_GROUP_FOR_LOT", r.id, `Q>1 無 cub，合成 group ${groupId}`]); } }
        else if (!general && !freqInt) { dur = r.tmu * r.freq; warns.push(["W_FRACTIONAL_FREQUENCY_BAKED", r.id, "非整數 frequency 燙進 duration"]); }
        else if (general) { dur = r.tmu * (freqInt ? r.freq : 1); }
        mk(0, "single", { tmu: dur, group: groupId, quantity: q, scope, basis, tool: null, tool_action: "", adjustable: 0, action_type: general ? ROLE_ACTION[t.general_role] || "take" : base.action_label });
        continue;
      }
      // 持工具
      const parts = plan.parts, N = dec.N;
      let q = 1, allCyclic = false;
      if (!freqInt) errs.push(["E_TOOL_FRACTIONAL_FREQUENCY", r.id, "持工具 motion 的 frequency 非整數"]);
      if (r.freq > 1 && N > 1) errs.push(["E_TOOL_FREQ_AND_REPEAT", r.id, "持工具 motion 同時 frequency>1 與 repeat>1"]);
      else if (r.freq > 1 && freqInt) { q = r.freq; allCyclic = true; warns.push(["W_TOOL_FREQ_ALL_CYCLIC", r.id, "持工具 motion frequency>1：三列全 cyclic（要「拿一次做 N 次」請用 repeat）"]); }
      else if (N > 1) q = N;
      if (q > 1 && !groupId) { groupId = autoGroupOf(r); warns.push(["W_AUTO_GROUP_FOR_LOT", r.id, `Q>1 無 cub，合成 group ${groupId}`]); }
      if (wcub) errs.push(["E_ATOMIC_ON_TOOL_MOTION", r.id, "wcub 不得標在持工具 motion（工具 episode 由 segment 綁同人）"]);
      const lock = !!t.merge_lock, tool = plan.tool;
      const scopeOf = (p) => (q > 1 ? (allCyclic ? "cyclic" : (p === "use" ? "cyclic" : "setup")) : "");
      const basis = q > 1 ? "once" : "";
      let pre = dec.setup_pre, useT = dec.use_once, post = dec.setup_post;
      if (parts.length === 2) { if (N > 1) pre += post; else useT += post; }        // §4.3
      if (parts.length === 1) { useT = r.tmu; pre = r.tmu; post = r.tmu; }         // Pattern A 單列：整個 motion
      const seqParts = parts.map((p) => p);
      seqParts.forEach((p, i) => {
        const tmu = p === "acquire" ? pre : p === "release" ? post : useT;
        mk(i, p, { tmu, group: groupId, quantity: q, scope: scopeOf(p), basis, tool, tool_action: p,
          adjustable: (p === "acquire" || p === "release") ? (lock ? 0 : 1) : 0,
          action_type: p === "acquire" ? "pick" : p === "release" ? "put" : base.action_label });
      });
    }
    for (const n of nodes) if (!n.action_type) { n.action_type = "op"; warns.push(["W_ACTION_TYPE_FALLBACK", n.rowId, "無 action_type 標籤，以 op 輸出"]); }

    // 邊：chain 內鏈 + 層間傳遞縮減
    const preds = {}; nodes.forEach((n) => (preds[n.key] = new Set()));
    const nodesOfRow = (id) => nodes.filter((n) => n.rowId === id).sort((a, b) => a.idx - b.idx);
    const chainSeq = (ch) => ch.members.flatMap((id) => nodesOfRow(id));
    const chains = state.chains.filter((c) => c.members.some((id) => placed.has(id) && !isGeneral(state, id)));
    for (const ch of chains) {
      const s = chainSeq(ch);
      for (let i = 1; i < s.length; i++) preds[s[i].key].add(s[i - 1].key);
    }
    const lt = (Y, X) => Y.hi < X.lo;
    for (const X of chains) for (const Y of chains) {
      if (!lt(Y, X)) continue;
      if (chains.some((Z) => Z !== X && Z !== Y && lt(Y, Z) && lt(Z, X))) continue;
      const src = chainSeq(X)[0], sink = chainSeq(Y).slice(-1)[0];
      if (src && sink) preds[src.key].add(sink.key);
    }
    // 編號（Kahn，(seq, idx) 最小優先）
    const indeg = {}; const succ = {};
    nodes.forEach((n) => { indeg[n.key] = preds[n.key].size; succ[n.key] = []; });
    nodes.forEach((n) => preds[n.key].forEach((p) => succ[p].push(n.key)));
    const ready = nodes.filter((n) => indeg[n.key] === 0);
    const order = []; const idOf = {};
    const pick = () => { ready.sort((a, b) => a.seq - b.seq || a.idx - b.idx); return ready.shift(); };
    while (ready.length) { const n = pick(); idOf[n.key] = order.length + 1; order.push(n); for (const s of succ[n.key]) if (--indeg[s] === 0) ready.push(nodeByKey[s]); }
    if (order.length !== nodes.length) errs.push(["E_LEVEL_INVALID", null, "層／鏈形成循環"]);

    // 跨列驗證
    const nodesByRow = {}; nodes.forEach((n) => (nodesByRow[n.rowId] = nodesByRow[n.rowId] || []).push(n));
    const groupsW = {}, atomicW = {};
    for (const n of nodes) { if (n.group) (groupsW[n.group] = groupsW[n.group] || []).push(n); if (n.atomic) (atomicW[n.atomic] = atomicW[n.atomic] || []).push(n); }
    for (const [g, ns] of Object.entries(groupsW)) {
      if (new Set(ns.map((n) => n.offline)).size > 1) errs.push(["E_OFFLINE_INCONSISTENT", ns[0].rowId, `cub ${g} 內 offline 不一致`]);
      const qs = new Set(ns.filter((n) => n.quantity > 1).map((n) => n.quantity)); if (qs.size > 1) errs.push(["E_LOT_QUANTITY_MIXED", ns[0].rowId, `cub ${g} 內 quantity 不一致`]);
    }
    for (const [a, ns] of Object.entries(atomicW)) {
      if (new Set(ns.map((n) => n.offline)).size > 1) errs.push(["E_OFFLINE_INCONSISTENT", ns[0].rowId, `wcub ${a} 內 offline 不一致`]);
      if (ns.some((n) => n.quantity > 1)) errs.push(["E_ATOMIC_QUANTITY", ns.find((n) => n.quantity > 1).rowId, `wcub ${a} 成員 Q>1`]);
      if (new Set(ns.map((n) => n.group || 0)).size > 1 && new Set(ns.map((n) => n.group)).size > 1 && ns.filter((n) => n.group).length && new Set(ns.filter((n) => n.group).map((n) => n.group)).size > 1) errs.push(["E_ATOMIC_CROSS_GROUP", ns[0].rowId, `wcub ${a} 跨多個 cub`]);
    }
    const segCub = {};
    for (const n of nodes) if (n.segment) { const k = n.segment; segCub[k] = segCub[k] || new Set(); segCub[k].add(n.group || "none"); }
    for (const [k, gs] of Object.entries(segCub)) if (gs.size > 1) errs.push(["E_SEGMENT_CROSS_GROUP", null, `segment ${k} 跨不同 cub`]);
    const acqDur = {}, relDur = {}, lotTools = new Set(), q1Tools = new Set();
    for (const n of nodes) {
      if (!n.tool) continue;
      (n.quantity > 1 ? lotTools : q1Tools).add(n.tool);
      const m = n.tool_action === "acquire" ? acqDur : n.tool_action === "release" ? relDur : null;
      if (m) { (m[n.tool] = m[n.tool] || new Set()).add(ms(n.tmu)); }
    }
    for (const [tl, ds] of Object.entries(acqDur)) if (ds.size > 1) errs.push(["E_TOOL_ACQUIRE_DURATION_MISMATCH", null, `${tl} 取用工時不一致 ${[...ds].join("/")}ms：不同拿取位置請用不同 tool_id`]);
    for (const [tl, ds] of Object.entries(relDur)) if (ds.size > 1) errs.push(["E_TOOL_RELEASE_DURATION_MISMATCH", null, `${tl} 放回工時不一致 ${[...ds].join("/")}ms`]);
    for (const tl of lotTools) if (q1Tools.has(tl)) errs.push(["E_TOOL_ID_SHARED_ACROSS_LOT", null, `${tl} 同時出現在批量與單件 episode（過渡守衛）`]);
    for (const n of nodes) if (!isGeneral(state, n.rowId) && preds[n.key].size === 0 && succ[n.key].length === 0) warns.push(["W_FLOATING_TASK", n.rowId, "無前置也無後繼"]);

    const tasks = order.map((n) => ({
      task_id: idOf[n.key], action: n.partName === "acquire" ? `pick up ${n.tool.replace(/_/g, " ")}` : n.partName === "release" ? `put down ${n.tool.replace(/_/g, " ")}` : n.row.narr,
      part_id: n.part, group: n.group || "", atomic_group: n.atomic || "", duration: ms(n.tmu),
      predecessors: [...preds[n.key]].map((k) => idOf[k]).sort((a, b) => a - b).join(","), station_name: n.wi, action_type: n.action_type,
      complexity_level: "", adjustable: n.adjustable, fixed_station: n.pin || "", offline_flag: n.offline ? 1 : 0,
      tool_id: n.tool || "", tool_action: n.tool ? n.tool_action : "", divisible: n.divisible ? 1 : 0, p2: "",
      quantity: n.quantity, segment: n.segment, qty_scope: n.scope, duration_basis: n.basis, source_wi_row_id: uuid(n.seq),
      role_type: n.tool ? "human" : n.role_type, general_role: n.general_role, _rowId: n.rowId, _part: n.partName, _key: n.key,
    }));
    const dedupe = (xs) => { const s = new Set(); return xs.filter((x) => { const k = x.join("|"); if (s.has(k)) return false; s.add(k); return true; }); };
    const E = dedupe(errs).map(([code, rowId, message]) => ({ code, rowId, message }));
    const W = dedupe(warns).map(([code, rowId, message]) => ({ code, rowId, message }));
    return { tasks, errors: E, warnings: W, plans, episodes, tmuTotal: +tasks.reduce((a, t) => a + (t.duration * (t.qty_scope === "cyclic" ? t.quantity : 1)), 0).toFixed(0) };
  }

  function toCsv(tasks) {
    const esc = (v) => { const s = String(v ?? ""); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    return [COLUMNS.join(","), ...tasks.map((t) => COLUMNS.map((c) => esc(t[c])).join(","))].join("\n") + "\n";
  }

  // ── 自動化 ───────────────────────────────────────────────────────────────
  function autoChainByWI(rows, state) {
    const chains = []; let layer = 0; const seen = new Map();
    for (const r of rows.slice().sort((a, b) => a.seq - b.seq)) {
      if (isGeneral(state, r.id)) continue;
      if (!seen.has(r.wi)) { layer += 1; const c = { id: `auto-${layer}`, kind: "sub", label: null, lo: layer, hi: layer, members: [] }; seen.set(r.wi, c); chains.push(c); }
      seen.get(r.wi).members.push(r.id);
    }
    for (const c of chains) if (c.members.length === 1) { c.kind = "single"; c.label = null; }
    let n = 1; for (const c of chains) if (c.kind === "sub") c.label = `sub${n++}`;
    return Object.assign({}, state, { chains });
  }
  function suggestions(rows, state, proj) {
    const out = [];
    const byId = Object.fromEntries(rows.map((r) => [r.id, r]));
    // (a) Pattern A episode 跨多個 motion 且未同站 → 建議 cub
    for (const ep of proj.episodes) {
      const ids = [...new Set([ep.acquire[0], ...ep.uses.map((u) => u[0]), ep.release ? ep.release[0] : null].filter(Boolean))];
      if (ids.length >= 2 && !ids.every((id) => cubLabelOf(state, id))) out.push({ kind: "cub", rowIds: ids, text: `工具 ${ep.tool} 的 episode 跨 ${ids.length} 個 motion（拿／用／放）——工具在一個地方，建議設為同站 cub` });
    }
    // (b) 同 chain 連續 Q>1、同 frequency、無 segment → 建議 segment
    for (const ch of state.chains) {
      let run = [];
      const flush = () => { if (run.length >= 2 && run.some((id) => !tagsOf(state, id).segment)) out.push({ kind: "segment", rowIds: run.slice(), text: `${run.join("、")} 連續批量 ×${byId[run[0]].freq}，建議綁同一 segment（同一批人、每人件數對齊）` }); run = []; };
      for (const id of ch.members) { const r = byId[id]; if (r.freq > 1 && isInt(r.freq) && (run.length === 0 || byId[run[0]].freq === r.freq)) run.push(id); else flush(); }
      flush();
    }
    // (c) 未編排
    const placed = new Set(state.chains.flatMap((c) => c.members));
    const un = rows.filter((r) => !placed.has(r.id) && !isGeneral(state, r.id)).map((r) => r.id);
    if (un.length) out.push({ kind: "autochain", rowIds: un, text: `${un.length} 列尚未編排——「依 WI 語句自動成鏈」可一鍵得到全序列基線` });
    return out;
  }
  function nextLabel(state, prefix) {
    const used = new Set(); for (const c of state.chains) if (c.label) used.add(c.label);
    for (const t of Object.values(state.tags)) { if (t.cub) used.add(t.cub); if (t.wcub) used.add(t.wcub); }
    let n = 1; while (used.has(`${prefix}${n}`)) n++; return `${prefix}${n}`;
  }
  return { COLUMNS, project, toCsv, autoChainByWI, suggestions, nextLabel, chainOf, cubLabelOf, tagsOf, isGeneral, isToolHeld, decompose };
})();
if (typeof module !== "undefined") module.exports = WB_ENGINE;
