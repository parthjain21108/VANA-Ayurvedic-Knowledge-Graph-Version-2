import{motion}from"framer-motion";
import{useEffect,useState}from"react";
import type{KnowledgeBaseStats}from"@/services/api";

function AnimatedNumber({value}:{value:number}){
  const[display,setDisplay]=useState(0);
  useEffect(()=>{
    const start=performance.now();
    const from=display;
    const duration=900;
    let frame=0;
    const tick=(now:number)=>{
      const progress=Math.min(1,(now-start)/duration);
      const eased=1-Math.pow(1-progress,3);
      setDisplay(Math.round(from+(value-from)*eased));
      if(progress<1) frame=requestAnimationFrame(tick);
    };
    frame=requestAnimationFrame(tick);
    return()=>cancelAnimationFrame(frame);
    // A count changing on the server should animate from the current value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[value]);
  return <>{display.toLocaleString("en-IN")}</>;
}

const CARDS=[
  ["plants","Plants","living plant records"],
  ["plant_parts","Plant parts","named graph components"],
  ["phytochemicals","Phytochemicals","mapped compounds"],
  ["bioactivities","Bioactivities","measured activities"],
  ["documents","Documents","literature records"],
  ["targets","Targets","resolved targets"],
  ["therapeutic_uses","Therapeutic uses","MeSH-linked uses"],
] as const;

export function GraphStats({stats,loading}:{stats:KnowledgeBaseStats|null;loading:boolean}){
  return <section className="mx-auto mt-20 max-w-7xl px-5 sm:px-8">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="specimen-label">Live knowledge base</p>
        <h2 className="mt-2 font-display text-3xl text-canopy2 sm:text-4xl">The graph, right now.</h2>
      </div>
      <div className="rounded-full border border-specimen bg-parchment2 px-3 py-1.5 text-xs text-moss">
        {stats?.checked_at?`Checked ${new Date(stats.checked_at).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"})}`:"Connecting to Neo4j…"}
      </div>
    </div>

    <div className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {CARDS.map(([key,label,detail],i)=><motion.div
        key={key}
        initial={{opacity:0,y:12}}
        whileInView={{opacity:1,y:0}}
        viewport={{once:true,amount:.25}}
        transition={{delay:i*.04}}
        className="lift-card rounded-2xl border border-specimen bg-parchment2 p-5"
      >
        <div className="flex items-start justify-between gap-3">
          <p className="specimen-label">{label}</p>
          <span className="h-2 w-2 rounded-full bg-canopy/70"/>
        </div>
        <p className="mt-3 font-display text-3xl text-canopy2">
          {loading||!stats?<span className="inline-block h-9 w-24 animate-pulse rounded bg-sage/30"/>:<AnimatedNumber value={stats.nodes[key]}/>}</p>
        <p className="mt-1 text-xs text-ink/45">{detail}</p>
      </motion.div>)}
      <motion.div
        initial={{opacity:0,y:12}}
        whileInView={{opacity:1,y:0}}
        viewport={{once:true,amount:.25}}
        className="lift-card rounded-2xl border border-canopy/20 bg-canopy p-5 text-parchment2 sm:col-span-2 lg:col-span-4"
      >
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[.16em] text-parchment2/60">Relationships</p>
            <p className="mt-1 font-display text-3xl">{loading||!stats?<span className="inline-block h-9 w-28 animate-pulse rounded bg-parchment2/15"/>:<AnimatedNumber value={stats.relationships}/>}</p>
          </div>
          <p className="max-w-md text-sm leading-6 text-parchment2/70">Edges connecting plants, parts, compounds, therapeutic uses, measured activity, targets and documents.</p>
        </div>
      </motion.div>
    </div>
  </section>;
}
