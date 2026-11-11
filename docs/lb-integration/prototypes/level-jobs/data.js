// Level Workbench 原型資料：server node 範例（24 motions，= MOST golden fixture）＋ 3 個 Pattern A 示範 motion（WI-Q）。
// 欄位：seq、wi（WI 語句／sub_activity）、part（key_parts）、narr（narrative_en）、kind、slots（7 格 TMU，已含 repeat）、
// rep（slot→repeat）、xsec（X 秒數）、freq、tool（tool_vocab，持工具）、objTool（object 本身是工具，Pattern A）。
const WB_DATA = (function () {
  const M = [
    ["A", 1,"General","General","take chassis from cart onto conveyor","GM",[24,0,6,24,0,6,0],{},0,1,null,false],
    ["B", 2,"Pre-kit","SCREW","pre-kit 8 screws into tray","GM",[10,0,24,10,0,6,0],{},0,1,null,false],
    ["C", 3,"MB sub-assy","MB","take motherboard from rack and place into chassis","GM",[16,32,6,16,0,24,0],{},0,1,null,false],
    ["D", 4,"MB sub-assy","MB","scan motherboard SN with scanner","CM",[10,0,6,6,6,10,10],{},0,1,"scanner",false],
    ["E", 5,"MB sub-assy","CPU","insert CPU into socket","GM",[10,0,10,10,0,40,0],{},0,1,null,false],
    ["F", 6,"MB sub-assy","CPU","scan CPU label with scanner","CM",[10,0,6,6,6,10,10],{},0,1,"scanner",false],
    ["G", 7,"MB sub-assy","DIMM","insert DIMM into slot","GM",[10,0,10,6,0,40,0],{},0,8,null,false],
    ["H", 8,"MB sub-assy","DIMM","close DIMM retainer latch","GM",[3,0,3,0,0,22,0],{},0,8,null,false],
    ["I", 9,"MB sub-assy","SCREW","fasten motherboard screw","CM",[16,0,6,24,48,80,16],{3:8,4:8,5:8},0.216,1,"electric_driver",false],
    ["J1",10,"HDD sub-assy","HDD","pick up HDD from rack","GM",[16,0,6,10,0,3,0],{},0,1,null,false],
    ["J2",11,"HDD sub-assy","HDD","align and slide HDD into bay","CM",[0,0,0,10,0,16,0],{},0,1,null,false],
    ["J3",12,"HDD sub-assy","HDD","press HDD to seat","CM",[0,0,0,3,0,6,0],{},0,1,null,false],
    ["K",13,"HDD sub-assy","HDD","fasten HDD bracket screw to torque","CM",[16,0,6,3,6,10,16],{},0.216,1,"torque_driver",false],
    ["L1",14,"Backplane","BACKPLANE","place backplane into press fixture","GM",[16,0,6,16,0,24,0],{},0,1,null,false],
    ["L2",15,"Backplane","BACKPLANE","start press cycle (3 s machine time)","CM",[6,0,3,3,83.333,0,6],{},3,1,null,false],
    ["L3",16,"Backplane","BACKPLANE","remove backplane from press fixture","GM",[16,0,6,16,0,6,0],{},0,1,null,false],
    ["M",17,"Backplane","BACKPLANE","fasten backplane bracket screw to torque","CM",[16,0,6,3,6,10,16],{},0.216,1,"torque_driver",false],
    ["N1",18,"IO shield","IO_SHIELD","place I/O shield into heat-stake fixture and hold","GM",[16,0,6,10,0,24,0],{},0,1,null,false],
    ["N2",19,"IO shield","IO_SHIELD","start heat stake while holding shield (2 s)","CM",[0,0,0,3,55.556,0,0],{},2,1,null,false],
    ["N3",20,"IO shield","IO_SHIELD","withdraw hands from heat-stake fixture","GM",[0,0,0,6,0,6,6],{},0,1,null,false],
    ["O",21,"Final","MB","visual inspection of assembled board (12 check points)","CM",[6,10,0,0,0,72,0],{5:12},0,1,null,false],
    ["P1",22,"Final","MB","place board into ICT fixture and close lid","GM",[16,0,6,16,0,24,0],{},0,1,null,false],
    ["P2",23,"Final","MB","start ICT test (20 s machine time)","CM",[6,0,3,3,555.556,0,6],{},20,1,null,false],
    ["P3",24,"Final","MB","remove board from ICT fixture","GM",[16,0,6,16,0,6,0],{},0,1,null,false],
    // WI-Q：Pattern A 示範（拿工具 / 用工具 / 放工具 三個 motion）——不在 golden 內
    ["Q1",25,"Fan","FAN","pick up hex key from dock","GM",[16,0,6,10,0,3,0],{},0,1,null,true],
    ["Q2",26,"Fan","FAN","fasten fan bracket with hex key","CM",[0,0,0,3,6,10,0],{},0.216,1,"hex_key",false],
    ["Q3",27,"Fan","FAN","put hex key back on dock","GM",[0,0,0,10,0,6,16],{},0,1,null,true],
  ];
  const TOOL_OF_OBJ = { Q1: "hex_key", Q3: "hex_key" };
  const rows = M.map(([id, seq, wi, part, narr, kind, slots, rep, xsec, freq, tool, objTool]) => ({
    id, seq, wi, part, narr, kind, slots, rep, xsec, freq, tool, objTool: objTool ? TOOL_OF_OBJ[id] : null,
    tmu: +slots.reduce((a, b) => a + b, 0).toFixed(3),
  }));
  const LABELS = {A:"take",B:"collect",C:"place",D:"scan",E:"insert",F:"scan",G:"insert",H:"latch",I:"fasten",
    J1:"pick",J2:"insert",J3:"press",K:"fasten",L1:"place",L2:"press",L3:"remove",M:"fasten",
    N1:"place",N2:"press",N3:"remove",O:"inspect",P1:"place",P2:"test",P3:"remove",Q1:"pick",Q2:"fasten",Q3:"put"};
  // golden 編排（= MOST fixture 的 Level System 編碼）
  const example = {
    chains: [
      { id: "c-B", kind: "single", label: null, lo: 1, hi: 1, members: ["B"] },
      { id: "c-C", kind: "single", label: null, lo: 1, hi: 1, members: ["C"] },
      { id: "c-D", kind: "single", label: null, lo: 2, hi: 2, members: ["D"] },
      { id: "sub2", kind: "sub", label: "sub2", lo: 2, hi: 2, members: ["E","F","G","H"] },
      { id: "cub40", kind: "cub", label: "cub40", lo: 2, hi: 2, members: ["I"] },
      { id: "sub3", kind: "sub", label: "sub3", lo: 2, hi: 2, members: ["J1","J2","J3","K"] },
      { id: "cub10", kind: "cub", label: "cub10", lo: 2, hi: 2, members: ["L1","L2","L3","M"] },
      { id: "cub11", kind: "cub", label: "cub11", lo: 2, hi: 2, members: ["N1","N2","N3"] },
      { id: "c-O", kind: "single", label: null, lo: 3, hi: 3, members: ["O"] },
      { id: "sub5", kind: "sub", label: "sub5", lo: 4, hi: 4, members: ["P1","P2","P3"] },
    ],
    tags: {
      A: { general_role: "take_unit" }, B: { offline: true },
      G: { cub: "cub30", segment: "dimm" }, H: { cub: "cub30", segment: "dimm" },
      I: { segment: "screw" },
      J1: { wcub: "wcub20" }, J2: { wcub: "wcub20" }, J3: { wcub: "wcub20" },
      K: { merge_lock: true }, M: { merge_lock: true },
      N1: { wcub: "wcub21" }, N2: { wcub: "wcub21" }, N3: { wcub: "wcub21" },
      O: { splittable: true },
      P1: { pin: 6 }, P2: { pin: 6 }, P3: { pin: 6 },
    },
    labels: LABELS,
  };
  return { rows, example, LABELS };
})();
if (typeof module !== "undefined") module.exports = WB_DATA;
