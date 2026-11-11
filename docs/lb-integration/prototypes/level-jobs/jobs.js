// 「作業」模型 → 引擎狀態的轉換（使用者只看作業與步驟；層／鏈／cub／wcub 由這裡推導）。
const WB_JOBS = (function () {
  const deep = (x) => JSON.parse(JSON.stringify(x));
  // 作業：{ id, name, row, steps:[rowId], sameStation, samePerson, offline, pin, cubLabel?, wcubLabel? }
  // 步驟標記：{ rowId: { cub?, wcub?, segment?, general_role?, merge_lock?, offline?, splittable? } }
  function toEngineState(J, labels) {
    const chains = []; const tags = {}; const used = new Set();
    const take = (prefix, want) => { if (want && !used.has(want)) { used.add(want); return want; } let n = 1; while (used.has(`${prefix}${n}`)) n++; used.add(`${prefix}${n}`); return `${prefix}${n}`; };
    for (const t of Object.values(J.stepTags)) { if (t.cub) used.add(t.cub); if (t.wcub) used.add(t.wcub); }
    for (const job of J.jobs) {
      const members = job.steps.filter((id) => !(J.stepTags[id] && J.stepTags[id].general_role));
      const cubLabel = job.sameStation ? take("cub", job.cubLabel) : null;
      const wcubLabel = job.samePerson ? take("wcub", job.wcubLabel) : null;
      if (members.length) chains.push({ id: job.id, kind: job.sameStation ? "cub" : members.length > 1 ? "sub" : "single", label: job.sameStation ? cubLabel : members.length > 1 ? take("sub", null) : null, lo: job.row, hi: job.rowHi || job.row, members });
      for (const id of job.steps) {
        const st = J.stepTags[id] || {}; const t = {};
        if (job.offline || st.offline) t.offline = true;
        if (wcubLabel) t.wcub = wcubLabel; else if (st.wcub) t.wcub = st.wcub;
        if (!job.sameStation && st.cub) t.cub = st.cub;
        if (job.pin) t.pin = job.pin;
        if (st.general_role) t.general_role = st.general_role;
        if (st.segment) t.segment = st.segment;
        if (st.merge_lock) t.merge_lock = true;
        if (st.splittable) t.splittable = true;
        if (st.action_type) t.action_type = st.action_type;
        tags[id] = t;
      }
    }
    return { chains, tags, labels };
  }
  function normalizeRows(J) { const rs = [...new Set(J.jobs.map((j) => j.row))].sort((a, b) => a - b); const m = {}; rs.forEach((r, i) => (m[r] = i + 1)); for (const j of J.jobs) { const hi = j.rowHi ? m[j.rowHi] || m[j.row] : undefined; j.row = m[j.row]; if (hi !== undefined) j.rowHi = Math.max(hi, j.row); } }
  // 基線：依 WI 語句分組，順序 = 出現順序，每個作業自成一排
  function baseline(rows) {
    const jobs = []; const seen = new Map();
    for (const r of rows.slice().sort((a, b) => a.seq - b.seq)) {
      if (!seen.has(r.wi)) { const j = { id: "j" + (jobs.length + 1), name: r.wi, row: jobs.length + 1, steps: [], sameStation: false, samePerson: false, offline: false, pin: null }; seen.set(r.wi, j); jobs.push(j); }
      seen.get(r.wi).steps.push(r.id);
    }
    return { jobs, stepTags: {} };
  }
  // golden 對應的作業編排（用作業語言表達）
  function example(labels) {
    const jobs = [
      { id: "j-A", name: "把機箱放上輸送帶", row: 1, steps: ["A"], sameStation: false, samePerson: false, offline: false, pin: null },
      { id: "j-B", name: "預備 8 顆螺絲（離線）", row: 1, steps: ["B"], sameStation: false, samePerson: false, offline: true, pin: null },
      { id: "j-C", name: "放主板進機箱", row: 1, steps: ["C"], sameStation: false, samePerson: false, offline: false, pin: null },
      { id: "j-D", name: "掃主板序號", row: 2, steps: ["D"], sameStation: false, samePerson: false, offline: false, pin: null },
      { id: "j-E", name: "裝 CPU 與 DIMM", row: 2, steps: ["E", "F", "G", "H"], sameStation: false, samePerson: false, offline: false, pin: null },
      { id: "j-I", name: "鎖主板 8 顆螺絲", row: 2, steps: ["I"], sameStation: true, cubLabel: "cub40", samePerson: false, offline: false, pin: null },
      { id: "j-J", name: "裝 HDD", row: 2, steps: ["J1", "J2", "J3", "K"], sameStation: false, samePerson: false, offline: false, pin: null },
      { id: "j-L", name: "背板壓合", row: 2, steps: ["L1", "L2", "L3", "M"], sameStation: true, cubLabel: "cub10", samePerson: false, offline: false, pin: null },
      { id: "j-N", name: "I/O 擋板熱熔", row: 2, steps: ["N1", "N2", "N3"], sameStation: true, cubLabel: "cub11", samePerson: true, wcubLabel: "wcub21", offline: false, pin: null },
      { id: "j-O", name: "外觀目檢", row: 3, steps: ["O"], sameStation: false, samePerson: false, offline: false, pin: null },
      { id: "j-P", name: "ICT 測試", row: 4, steps: ["P1", "P2", "P3"], sameStation: false, samePerson: false, offline: false, pin: 6 },
      { id: "j-Q", name: "鎖風扇支架（六角扳手）", row: 2, steps: ["Q1", "Q2", "Q3"], sameStation: false, samePerson: false, offline: false, pin: null },
    ];
    const stepTags = {
      A: { general_role: "take_unit" },
      G: { cub: "cub30", segment: "dimm" }, H: { cub: "cub30", segment: "dimm" }, I: { segment: "screw" },
      J1: { wcub: "wcub20" }, J2: { wcub: "wcub20" }, J3: { wcub: "wcub20" }, K: { merge_lock: true }, M: { merge_lock: true },
      O: { splittable: true },
    };
    return { jobs, stepTags };
  }
  // 使用者語言的訊息
  const MSG = {
    E_TOOL_NOT_RELEASED: (r, m) => `${r}：拿了工具，後面沒有放回。請在同一個作業裡加一步「放回」，或確認最後那一步就是放回。`,
    E_TOOL_CROSS_CHAIN: (r) => `${r}：工具在別的作業放回。拿與放要在同一個作業裡。`,
    E_TOOL_TWO_TOOLS: (r) => `${r}：一步同時用兩把工具，請拆成兩步。`,
    E_TOOL_FREQ_AND_REPEAT: (r) => `${r}：這一步「整個動作重複」又「拿一次做多次」同時設了，二選一。`,
    E_TOOL_FRACTIONAL_FREQUENCY: (r) => `${r}：用工具的步驟，重複次數必須是整數。`,
    E_TOOL_ACQUIRE_REPEAT: (r) => `${r}：拿工具只做一次，重複次數請標在使用那一格。`,
    E_REPEAT_MIXED: (r) => `${r}：使用段各格的重複次數不一樣，請統一。`,
    E_REPEAT_NONCONTIGUOUS: (r) => `${r}：重複的動作中間夾了不重複的動作，請把中間那個拆成獨立一步。`,
    E_ATOMIC_ON_TOOL_MOTION: (r) => `${r}：用工具的步驟不用設「同一個人一口氣做完」——工具動作系統會自動綁同一人。請取消這一步的設定。`,
    E_ATOMIC_QUANTITY: (r) => `${r}：做很多次的步驟不能設「同一個人一口氣做完」，請改用「同一批人接著做」。`,
    E_ATOMIC_CROSS_GROUP: (r) => `${r}：「同一個人一口氣做完」的步驟跨了兩個「同一工站」的作業。`,
    E_OFFLINE_INCONSISTENT: (r) => `${r}：同一組裡有的設離線、有的沒有。整組要一致。`,
    E_GENERAL_IN_GROUP: (r) => `${r}：通用動作不能同時在「同一工站／同一個人」的作業裡。`,
    E_GENERAL_ROLE_MISSING: (r) => `${r}：通用動作要選一種（線頭／每站頭／每站尾）。`,
    E_SEGMENT_CROSS_GROUP: () => `「同一批人接著做」的步驟必須在同一個「同一工站」作業裡。`,
    E_TOOL_ACQUIRE_DURATION_MISMATCH: (r, m) => `同一把工具在不同地方拿的時間不一樣（${m.replace(/^.*?工時不一致/, "")}）。如果是不同放置位置，請把工具取不同名字。`,
    E_TOOL_RELEASE_DURATION_MISMATCH: (r, m) => `同一把工具放回的時間不一樣。如果是不同放置位置，請把工具取不同名字。`,
    E_TOOL_ID_SHARED_ACROSS_LOT: (r, m) => `${m.split(" ")[0]} 同時用在「做很多次」和「做一次」的步驟上，請把批量用的那把另取名字（暫行規則）。`,
    E_LEVEL_INVALID: (r, m) => (r ? `${r}：還沒放進任何作業。` : `作業之間的先後形成循環，請檢查排序。`),
    E_LOT_QUANTITY_MIXED: (r) => `${r}：同一個「同一工站」作業裡，做很多次的步驟次數不一樣。`,
    W_FLOATING_TASK: (r) => `${r}：這一步跟其他作業沒有任何先後關係，確定嗎？`,
    W_TOOL_FREQ_ALL_CYCLIC: (r) => `${r}：整個動作（含拿放工具）重複好幾次。如果其實是「拿一次、做很多次」，請把次數標在使用那一格。`,
    W_FRACTIONAL_FREQUENCY_BAKED: (r) => `${r}：重複次數不是整數，已換算成平均時間。`,
    W_GENERAL_WITH_TOOL: (r) => `${r}：通用動作裡用了工具，會當成單一步驟輸出。`,
  };
  const HIDDEN = new Set(["W_AUTO_GROUP_FOR_LOT", "W_ACTION_TYPE_FALLBACK", "W_NB_UNSUPPORTED", "W_SIMO_COLLAPSED", "W_TOOL_NAME_EN_MISSING"]);
  function humanize(issue, stepLabel) { const f = MSG[issue.code]; const r = issue.rowId ? stepLabel(issue.rowId) : ""; return f ? f(r, issue.message) : `${r}${r ? "：" : ""}${issue.message}`; }
  return { toEngineState, normalizeRows, baseline, example, humanize, HIDDEN, deep };
})();
if (typeof module !== "undefined") module.exports = WB_JOBS;
