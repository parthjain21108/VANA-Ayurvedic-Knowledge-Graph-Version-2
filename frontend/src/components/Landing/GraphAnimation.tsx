import{motion}from"framer-motion";
import{LeafGlyph}from"@/components/Layout/BotanicalMotif";

const DOTS=[
  {x:22,y:24,r:5,d:.1},{x:68,y:18,r:4,d:.25},{x:81,y:46,r:6,d:.4},
  {x:73,y:76,r:4,d:.55},{x:31,y:79,r:6,d:.7},{x:14,y:56,r:4,d:.85},
];

export function GraphAnimation(){
  return <div className="relative mx-auto aspect-square w-full max-w-[390px] overflow-hidden rounded-[34px] border border-specimen bg-parchment2 shadow-specimen">
    <div className="absolute inset-0 bg-grain opacity-30"/>
    <div className="absolute left-1/2 top-1/2 h-32 w-32 -translate-x-1/2 -translate-y-1/2 rounded-full border border-canopy/20 bg-sage/25 blur-[1px]"/>
    <motion.div
      className="absolute left-1/2 top-1/2 flex h-24 w-24 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-canopy/40 bg-parchment"
      animate={{scale:[1,1.04,1]}}
      transition={{duration:3,ease:"easeInOut",repeat:Infinity}}
    >
      <LeafGlyph className="h-12 w-12 text-canopy"/>
    </motion.div>
    <svg viewBox="0 0 100 100" className="absolute inset-0 h-full w-full" aria-hidden>
      {DOTS.map((dot,i)=><motion.line key={`l-${i}`} x1="50" y1="50" x2={dot.x} y2={dot.y} stroke="currentColor" className="text-canopy/20" strokeWidth=".55"/>) }
      {DOTS.map((dot,i)=><motion.circle
        key={`c-${i}`}
        cx={dot.x}
        cy={dot.y}
        r={dot.r/2}
        className="fill-turmeric"
        animate={{opacity:[.35,1,.35],scale:[.85,1.1,.85]}}
        transition={{duration:2.6,delay:dot.d,repeat:Infinity,ease:"easeInOut"}}
      />)}
      <motion.circle cx="50" cy="50" r="30" fill="none" stroke="currentColor" className="text-canopy/10" strokeDasharray="1.8 2.8" animate={{rotate:360}} transition={{duration:22,repeat:Infinity,ease:"linear"}} transform="rotate(-20 50 50)"/>
    </svg>
    <div className="absolute inset-x-5 bottom-5 rounded-2xl border border-specimen/80 bg-parchment2/90 px-4 py-3 backdrop-blur">
      <p className="specimen-label">Live graph</p>
      <p className="mt-1 font-display text-lg text-canopy2">Plants → compounds → uses → evidence</p>
    </div>
  </div>;
}
