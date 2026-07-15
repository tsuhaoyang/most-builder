// ADistanceSelector — 工位伸手範圍圖（俯視）互動選檔（v3 ADistanceSelector.vue React 移植；ADR-022 批次 C）
// 左＝SVG 俯視圖（人形＋同心弧距離區，點擊選檔）；右＝目前選取＋距離對照表＋實際距離 cm 輸入（自動落檔）。
// 檔位動態來自後端 options 的 a_bands.reach（DISC-06 不寫死）；band.index 即該檔 TMU（前端不算，僅呈現）。
// value 慣例沿用 ASlot.reach：檔位值 = band.max_value（最末開放檔 null → 999；0 = 未選）。
import { useMemo, useState } from 'react'
import type { ABand } from '../wi-workbench/cycle'

export interface ADistanceSelectorProps {
  /** 目前 reach 檔位值（band.max_value ?? 999；0 = 未選） */
  value: number
  onChange: (cm: number) => void
  /** opts.a_bands.reach（後端 options） */
  bands: ABand[]
}

interface Zone {
  value: number      // ASlot.reach 檔位值
  maxCm: number      // Infinity = 開放檔（>最末有限檔）
  tmu: number        // band.index（MiniMOST index 即 TMU 級數）
  shortLabel: string // ≤N / >N
  color: string
  radius: number
}

// v3 配色：由近到遠 藍→綠→黃→橙→紅
const ZONE_COLORS = ['#1565c0', '#1976d2', '#2e7d32', '#558b2f', '#f9a825', '#ef6c00', '#c62828']

// viewBox 幾何（照 v3：400×340，肩關節中心 (200,280)）
const VB_W = 400
const VB_H = 340
const CX = 200
const CY = 280
const MIN_R = 18
const MAX_R = 220
const NATURAL_CM = 35
const MAX_REACH_CM = 60
const SCALE_CM = 70

const cmToRadius = (cm: number) => MIN_R + (cm / SCALE_CM) * (MAX_R - MIN_R)
const NATURAL_R = cmToRadius(NATURAL_CM)
const MAXREACH_R = cmToRadius(MAX_REACH_CM)

const arcPath = (r: number) => `M ${CX - r} ${CY} A ${r} ${r} 0 0 1 ${CX + r} ${CY}`
const bandPath = (outerR: number, innerR: number) =>
  `M ${CX - outerR} ${CY} A ${outerR} ${outerR} 0 0 1 ${CX + outerR} ${CY} ` +
  `L ${CX + innerR} ${CY} A ${innerR} ${innerR} 0 0 0 ${CX - innerR} ${CY} Z`

export function ADistanceSelector({ value, onChange, bands }: ADistanceSelectorProps) {
  const [manualCm, setManualCm] = useState('')

  const zones = useMemo<Zone[]>(() => bands.map((b, i) => {
    const maxCm = b.max_value == null ? Infinity : b.max_value
    const prevMax = i > 0 ? (bands[i - 1].max_value ?? 0) : 0
    return {
      value: b.max_value == null ? 999 : b.max_value,
      maxCm,
      tmu: b.index,
      shortLabel: maxCm === Infinity ? `>${prevMax}` : `≤${maxCm}`,
      color: ZONE_COLORS[i % ZONE_COLORS.length],
      radius: cmToRadius(maxCm === Infinity ? SCALE_CM : maxCm),
    }
  }), [bands])

  const selected = zones.find(z => z.value === value) ?? null
  const selectedIdx = selected ? zones.indexOf(selected) : -1

  const pickZone = (z: Zone) => { onChange(z.value); setManualCm('') }

  // 實際距離輸入 → 自動落檔（找第一個 cm ≤ maxCm 的檔；超過全部 → 最末開放檔）
  const manualZone = useMemo<Zone | null>(() => {
    const n = parseFloat(manualCm)
    if (manualCm === '' || isNaN(n) || n < 0) return null
    return zones.find(z => n <= z.maxCm) ?? zones[zones.length - 1] ?? null
  }, [manualCm, zones])

  const onCmInput = (s: string) => {
    setManualCm(s)
    const n = parseFloat(s)
    if (s === '' || isNaN(n) || n < 0) return
    const z = zones.find(zz => n <= zz.maxCm) ?? zones[zones.length - 1]
    if (z && z.value !== value) onChange(z.value)
  }

  // 圖面任意點點擊：換算 viewBox 座標 → 與肩心距離 → 對映檔位（v3 onDiagramClick）
  const onDiagramClick = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const svgX = ((e.clientX - rect.left) / rect.width) * VB_W
    const svgY = ((e.clientY - rect.top) / rect.height) * VB_H
    if (svgY > CY + 5) return
    const dist = Math.sqrt((svgX - CX) ** 2 + (svgY - CY) ** 2)
    for (const z of zones) {
      if (dist <= z.radius) { pickZone(z); return }
    }
    if (zones.length) pickZone(zones[zones.length - 1])
  }

  return (
    <div className="flex gap-3 items-start w-full" data-testid="a-distance-selector">
      {/* 左：SVG 俯視工位圖 */}
      <div className="flex-[7] min-w-0 border rounded-lg p-1" style={{ background: '#f8f9fb', borderColor: '#e0e0e0' }}>
        <svg
          viewBox={`0 0 ${VB_W} ${VB_H}`}
          className="w-full h-auto block cursor-crosshair select-none"
          onClick={onDiagramClick}
          data-testid="a-distance-svg"
        >
          <defs>
            <filter id="adist-glow-green" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
            <filter id="adist-glow-orange" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>

          {/* 背景 */}
          <rect x="0" y="0" width={VB_W} height={VB_H} fill="#f8f9fb" rx="4" />

          {/* 距離區帶（點擊直接選該檔；選中 0.4、未選 0.06） */}
          {zones.map((z, i) => (
            <path
              key={`fill-${z.value}`}
              d={bandPath(z.radius, i > 0 ? zones[i - 1].radius : 0)}
              fill={z.color}
              opacity={z.value === value || z === manualZone ? 0.4 : 0.06}
              className="cursor-pointer"
              onClick={e => { e.stopPropagation(); pickZone(z) }}
              data-testid={`a-distance-zone-${z.tmu}`}
            />
          ))}

          {/* 選中區虛線外框 */}
          {selected && (
            <path
              d={bandPath(selected.radius, zones[selectedIdx - 1]?.radius ?? 0)}
              fill="none" stroke={selected.color} strokeWidth="2.5"
              strokeDasharray="6 3" opacity="0.9" pointerEvents="none"
            />
          )}

          {/* 自然伸手界線（綠實線＋光暈） */}
          <path d={arcPath(NATURAL_R)} fill="none" stroke="#1b5e20" strokeWidth="4.5" opacity="0.9" filter="url(#adist-glow-green)" />
          <path d={arcPath(NATURAL_R)} fill="none" stroke="#fff" strokeWidth="1.5" strokeDasharray="8 4" opacity="0.5" />

          {/* 最大伸手界線（橙紅虛線＋光暈） */}
          <path d={arcPath(MAXREACH_R)} fill="none" stroke="#bf360c" strokeWidth="4.5" strokeDasharray="14 6" opacity="0.9" filter="url(#adist-glow-orange)" />
          <path d={arcPath(MAXREACH_R)} fill="none" stroke="#fff" strokeWidth="1.5" strokeDasharray="3 10" opacity="0.4" />

          {/* 界線標籤 */}
          <g>
            <rect x={CX - NATURAL_R - 4} y={CY - 26} width="72" height="16" rx="3" fill="#e8f5e9" stroke="#1b5e20" strokeWidth="1" />
            <text x={CX - NATURAL_R + 32} y={CY - 14} textAnchor="middle" fontSize="9" fill="#1b5e20" fontWeight="bold">自然伸手 {NATURAL_CM}cm</text>
          </g>
          <g>
            <rect x={CX - MAXREACH_R - 4} y={CY - 26} width="72" height="16" rx="3" fill="#fbe9e7" stroke="#bf360c" strokeWidth="1" />
            <text x={CX - MAXREACH_R + 32} y={CY - 14} textAnchor="middle" fontSize="9" fill="#bf360c" fontWeight="bold">最大伸手 {MAX_REACH_CM}cm</text>
          </g>

          {/* 前向軸刻度 */}
          {zones.filter(z => z.maxCm !== Infinity).map(z => (
            <g key={`tick-${z.value}`}>
              <line x1={CX + 3} y1={CY - z.radius} x2={CX + 7} y2={CY - z.radius} stroke="#999" strokeWidth="0.7" />
              <text x={CX + 10} y={CY - z.radius + 3} fontSize="7.5" fill="#777" fontWeight={z.value === value ? 'bold' : 'normal'}>{z.maxCm}</text>
            </g>
          ))}

          {/* ===== 人形（俯視） ===== */}
          <ellipse cx={CX + 1} cy={CY + 18} rx="20" ry="26" fill="#000" opacity="0.05" />
          {/* 軀幹 */}
          <path d={`M ${CX - 18} ${CY + 4} C ${CX - 20} ${CY + 14} ${CX - 16} ${CY + 38} ${CX - 9} ${CY + 42} L ${CX + 9} ${CY + 42} C ${CX + 16} ${CY + 38} ${CX + 20} ${CY + 14} ${CX + 18} ${CY + 4} Z`} fill="#546e7a" stroke="#37474f" strokeWidth="1.2" />
          {/* 肩線 */}
          <path d={`M ${CX - 26} ${CY + 1} L ${CX - 18} ${CY + 7} L ${CX + 18} ${CY + 7} L ${CX + 26} ${CY + 1} L ${CX + 20} ${CY - 3} L ${CX - 20} ${CY - 3} Z`} fill="#607d8b" stroke="#455a64" strokeWidth="1.2" />
          {/* 頸/頭 */}
          <ellipse cx={CX} cy={CY - 5} rx="6" ry="4.5" fill="#8d6e63" stroke="#5d4037" strokeWidth="0.8" />
          <ellipse cx={CX} cy={CY - 16} rx="12" ry="14" fill="#a1887f" stroke="#5d4037" strokeWidth="1.2" />
          <ellipse cx={CX} cy={CY - 20} rx="11" ry="9" fill="#4e342e" opacity="0.65" />
          <line x1={CX - 4} y1={CY - 18} x2={CX + 4} y2={CY - 18} stroke="#3e2723" strokeWidth="1.5" strokeLinecap="round" opacity="0.45" />
          <circle cx={CX} cy={CY - 26} r="1.5" fill="#5d4037" opacity="0.5" />
          {/* 左臂：自然姿勢（~35cm） */}
          <path d={`M ${CX - 26} ${CY} Q ${CX - 36} ${CY - 12} ${CX - 40} ${CY - 28}`} fill="none" stroke="#607d8b" strokeWidth="7" strokeLinecap="round" />
          <path d={`M ${CX - 40} ${CY - 28} Q ${CX - 42} ${CY - 42} ${CX - 38} ${CY - 55}`} fill="none" stroke="#6d8fa0" strokeWidth="5.5" strokeLinecap="round" />
          <circle cx={CX - 38} cy={CY - 55} r="3.5" fill="#a1887f" stroke="#795548" strokeWidth="0.8" />
          <ellipse cx={CX - 37} cy={CY - 60} rx="4.5" ry="6" fill="#bcaaa4" stroke="#795548" strokeWidth="0.7" />
          <line x1={CX - 40} y1={CY - 64} x2={CX - 42} y2={CY - 68} stroke="#a1887f" strokeWidth="1.3" strokeLinecap="round" />
          <line x1={CX - 37} y1={CY - 65} x2={CX - 37} y2={CY - 70} stroke="#a1887f" strokeWidth="1.3" strokeLinecap="round" />
          <line x1={CX - 34} y1={CY - 64} x2={CX - 32} y2={CY - 68} stroke="#a1887f" strokeWidth="1.3" strokeLinecap="round" />
          {/* 右臂：極限伸展（~60cm） */}
          <path d={`M ${CX + 26} ${CY} Q ${CX + 40} ${CY - 18} ${CX + 48} ${CY - 38}`} fill="none" stroke="#607d8b" strokeWidth="7" strokeLinecap="round" />
          <path d={`M ${CX + 48} ${CY - 38} Q ${CX + 52} ${CY - 56} ${CX + 46} ${CY - 74}`} fill="none" stroke="#6d8fa0" strokeWidth="5.5" strokeLinecap="round" />
          <circle cx={CX + 46} cy={CY - 74} r="3.5" fill="#a1887f" stroke="#795548" strokeWidth="0.8" />
          <ellipse cx={CX + 45} cy={CY - 80} rx="4.5" ry="6" fill="#bcaaa4" stroke="#795548" strokeWidth="0.7" />
          <line x1={CX + 42} y1={CY - 84} x2={CX + 41} y2={CY - 88} stroke="#a1887f" strokeWidth="1.3" strokeLinecap="round" />
          <line x1={CX + 45} y1={CY - 85} x2={CX + 45} y2={CY - 90} stroke="#a1887f" strokeWidth="1.3" strokeLinecap="round" />
          <line x1={CX + 48} y1={CY - 84} x2={CX + 49} y2={CY - 88} stroke="#a1887f" strokeWidth="1.3" strokeLinecap="round" />
          {/* 手臂姿勢註記 */}
          <text x={CX - 58} y={CY - 66} fontSize="7.5" fill="#1b5e20" fontWeight="700">自然姿勢</text>
          <text x={CX + 54} y={CY - 86} fontSize="7.5" fill="#bf360c" fontWeight="700">極限伸展</text>
          {/* 原點十字（肩關節中心） */}
          <circle cx={CX} cy={CY} r="4" fill="#fff" stroke="#212121" strokeWidth="2" />
          <line x1={CX - 7} y1={CY} x2={CX + 7} y2={CY} stroke="#212121" strokeWidth="1" />
          <line x1={CX} y1={CY - 7} x2={CX} y2={CY + 7} stroke="#212121" strokeWidth="1" />

          {/* 選中檔位標記（前向軸上） */}
          {selected && (
            <circle cx={CX} cy={CY - selected.radius} r="6" fill={selected.color} stroke="#fff" strokeWidth="2.5" pointerEvents="none" />
          )}

          {/* 標題／說明 */}
          <text x={VB_W / 2} y="16" textAnchor="middle" fontSize="11" fill="#333" fontWeight="700">工位伸手範圍圖 (俯視)</text>
          <text x={VB_W / 2} y="332" textAnchor="middle" fontSize="8" fill="#999">量測基準：以肩關節中心向前量測｜點擊對應區域直接選取</text>
        </svg>
      </div>

      {/* 右：資訊面板 */}
      <div className="flex-[3] min-w-[170px] flex flex-col gap-2.5">
        {/* 目前選取 */}
        <div className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2" data-testid="a-distance-current">
          {selected ? (
            <div className="flex flex-col gap-1.5">
              <div className="flex flex-col">
                <span className="text-[10px] text-slate-400 tracking-wide">目前距離區間</span>
                <span className="text-sm font-bold" style={{ color: selected.color }}>{selected.shortLabel} cm</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[10px] text-slate-400 tracking-wide">距離 TMU</span>
                <span className="text-[22px] leading-tight font-extrabold text-blue-800">{selected.tmu}</span>
              </div>
            </div>
          ) : (
            <div className="text-xs text-slate-400 text-center py-2">請選擇距離區間</div>
          )}
        </div>

        {/* 距離對照表 */}
        <div className="rounded-md border border-slate-200 bg-white px-2 py-1.5">
          <div className="text-[10px] font-semibold text-slate-500 mb-1">距離對照表</div>
          <div className="flex flex-col gap-px">
            {zones.map(z => (
              <button
                key={`row-${z.value}`}
                type="button"
                onClick={() => pickZone(z)}
                className={`flex items-center gap-1.5 px-1.5 py-1 rounded text-[11px] text-left transition-colors
                  ${z.value === value ? 'bg-blue-50 font-bold' : 'hover:bg-slate-100'}`}
                data-testid={`a-distance-row-${z.tmu}`}
              >
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: z.color }} />
                <span className="flex-1 text-slate-700">{z.shortLabel} cm</span>
                <span className="text-slate-300 text-[10px]">→</span>
                <span className={`font-semibold min-w-[42px] text-right ${z.value === value ? 'text-blue-900' : 'text-blue-700'}`}>
                  {z.tmu} TMU
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* 實際距離輸入（自動落檔） */}
        <div className="rounded-md border border-slate-200 bg-white px-2.5 py-2">
          <div className="text-[10px] font-semibold text-slate-500 mb-1">實際距離 (cm)</div>
          <input
            type="number" min={0} max={200} step={5}
            className="w-full border rounded px-2 py-1 text-sm"
            value={manualCm}
            onChange={e => onCmInput(e.target.value)}
            placeholder="輸入 cm 自動落檔"
            data-testid="a-distance-cm-input"
          />
          {manualZone && (
            <div className="text-[11px] font-semibold text-blue-700 mt-1">
              → {manualZone.shortLabel} cm（{manualZone.tmu} TMU）
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
