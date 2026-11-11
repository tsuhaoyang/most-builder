// 即時提示 ⓘ（hover 顯示）
export function Hint({ tip }: { tip: string }) {
  return (
    <span title={tip}
      className="inline-flex items-center justify-center w-[15px] h-[15px] rounded-full bg-slate-400 text-white text-[10px] font-bold cursor-help align-middle mx-0.5">
      i
    </span>
  )
}
