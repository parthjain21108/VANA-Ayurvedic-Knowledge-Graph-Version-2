import{useEffect,useMemo,useRef,useState}from"react";import{animate,AnimatePresence,motion,useInView,useScroll,useTransform}from"framer-motion";import{ArrowUpRight,Leaf,Search,Sprout,Waypoints,FileCheck2}from"lucide-react";
import{LeafGlyph,Sprig}from"@/components/Layout/BotanicalMotif";import{GraphField}from"@/components/Layout/GraphField";import{getKbPlants,getKbStats,type KbPlant,type KbStats}from"@/services/api";

const SUG=["Tell me the uses of neem","What are the phytochemicals in turmeric?","Which phytochemicals in Acacia leucophloea have IC50 activity against EGFR?","Explore Moringa oleifera"];
const PLACEHOLDERS=["Tell me the uses of neem…","What are the phytochemicals in turmeric?","Explore Moringa oleifera…","Which compounds in holy basil target EGFR?"];
const STAT_LABELS:[string,string][]=[["plants","Plants"],["plant_parts","Plant parts"],["phytochemicals","Phytochemicals"],["bioactivities","Bioactivities"],["targets","Protein targets"],["therapeutic_uses","Therapeutic uses"],["documents","Source documents"]];
const EASE=[0.22,1,0.36,1] as const;

function CountUp({to}:{to:number}){const ref=useRef<HTMLSpanElement>(null);const inView=useInView(ref,{once:true,margin:"-60px"});const[v,setV]=useState(0);useEffect(()=>{if(!inView)return;const c=animate(0,to,{duration:1.8,ease:EASE,onUpdate:x=>setV(Math.round(x))});return()=>c.stop()},[inView,to]);return <span ref={ref} className="tabular-nums">{v.toLocaleString()}</span>}
function Reveal({children,delay=0,className=""}:{children:React.ReactNode;delay?:number;className?:string}){return <motion.div className={className} initial={{opacity:0,y:28}} whileInView={{opacity:1,y:0}} viewport={{once:true,margin:"-70px"}} transition={{duration:.8,delay,ease:EASE}}>{children}</motion.div>}
function Words({text,className="",delay=0}:{text:string;className?:string;delay?:number}){return <span className={className}>{text.split(" ").map((w,i)=><span key={i} className="inline-block overflow-hidden pb-[.12em] align-bottom"><motion.span className="inline-block" initial={{y:"110%",rotate:4}} animate={{y:0,rotate:0}} transition={{duration:.9,delay:delay+i*.07,ease:EASE}}>{w}&nbsp;</motion.span></span>)}</span>}

export function Landing({onSearch}:{onSearch:(q:string)=>void}){
  const[v,setV]=useState("");const[focus,setFocus]=useState(false);const[ph,setPh]=useState(0);
  const[stats,setStats]=useState<KbStats|null>(null);const[live,setLive]=useState(false);const[plants,setPlants]=useState<KbPlant[]>([]);const[filter,setFilter]=useState("");
  const hero=useRef<HTMLElement>(null);const{scrollYProgress}=useScroll({target:hero,offset:["start start","end start"]});const fieldY=useTransform(scrollYProgress,[0,1],[0,120]);const heroOp=useTransform(scrollYProgress,[0,.8],[1,0]);
  useEffect(()=>{const id=setInterval(()=>setPh(p=>(p+1)%PLACEHOLDERS.length),3200);return()=>clearInterval(id)},[]);
  useEffect(()=>{
    let stopped=false;
    let timer:number|undefined;
    let failures=0;
    const refresh=async()=>{
      const [nextStats,nextPlants]=await Promise.all([getKbStats(),getKbPlants()]);
      if(stopped)return;
      const statsOk=Boolean(nextStats?.nodes && typeof nextStats.total_relationships==="number");
      const plantsOk=Array.isArray(nextPlants);
      if(statsOk){setStats(nextStats);setLive(true)}else{setLive(false)}
      if(Array.isArray(nextPlants))setPlants(nextPlants);
      if(statsOk&&plantsOk)failures=0;else failures=Math.min(failures+1,4);
      // Retry a cold/transient endpoint quickly, then refresh the live counts every minute.
      const delay=statsOk&&plantsOk?60000:Math.min(1000*(2**failures),15000);
      timer=window.setTimeout(refresh,delay);
    };
    void refresh();
    return()=>{stopped=true;if(timer!==undefined)window.clearTimeout(timer)};
  },[]);
  const shown=useMemo(()=>{const f=filter.trim().toLowerCase();return(f?plants.filter(p=>p.scientific_name.toLowerCase().includes(f)||(p.common_names||"").toLowerCase().includes(f)):plants)},[plants,filter]);
  const go=(q:string)=>{const t=q.trim();if(t)onSearch(t)};

  return <div className="relative overflow-x-clip">
    {/* HERO */}
    <section ref={hero} className="relative isolate min-h-screen overflow-hidden">
      <div className="aurora" aria-hidden><span className="aurora-a"/><span className="aurora-b"/><span className="aurora-c"/></div>
      <motion.div style={{y:fieldY}} className="absolute inset-0 -z-10"><GraphField className="h-full w-full opacity-80 [mask-image:radial-gradient(ellipse_70%_65%_at_50%_45%,transparent_30%,#000_85%)]"/></motion.div>
      <Sprig className="pointer-events-none absolute -right-10 bottom-[-40px] -z-10 hidden h-[460px] w-[280px] text-moss/20 lg:block"/><Sprig className="pointer-events-none absolute -left-12 bottom-[-30px] -z-10 hidden h-[340px] w-[200px] -scale-x-100 text-moss/15 md:block" animate={false}/>

      <motion.header initial={{opacity:0,y:-12}} animate={{opacity:1,y:0}} transition={{duration:.8,ease:EASE}} className="mx-auto flex max-w-7xl items-center justify-between px-5 py-5 sm:px-8"><div className="flex items-center gap-2 text-canopy2"><LeafGlyph className="h-8 w-8"/><span className="font-display text-2xl">Vana</span></div><nav className="hidden items-center gap-7 text-sm text-ink/60 sm:flex"><a href="#how" className="transition hover:text-canopy">How it works</a><a href="#graph" className="transition hover:text-canopy">The graph</a>{plants.length>0&&<a href="#plants" className="transition hover:text-canopy">Plants</a>}</nav></motion.header>

      <motion.div style={{opacity:heroOp}} className="mx-auto flex min-h-[calc(100vh-76px)] max-w-5xl flex-col items-center justify-center px-5 pb-24 text-center sm:px-8">
        <motion.div initial={{opacity:0,scale:.92}} animate={{opacity:1,scale:1}} transition={{duration:.7,delay:.1,ease:EASE}} className="inline-flex items-center gap-2 rounded-full border border-specimen bg-parchment2/80 px-4 py-2 text-xs text-moss shadow-sm backdrop-blur"><span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-turmeric/60"/><span className="relative inline-flex h-2 w-2 rounded-full bg-turmeric"/></span><Leaf size={13}/> Grounded in a botanical knowledge graph</motion.div>
        <h1 className="mt-8 text-balance font-display text-[2.9rem] leading-[1.02] tracking-tight text-canopy2 sm:text-7xl lg:text-[5.6rem]"><Words text="Ask the plant." delay={.2}/><br/><Words text="Follow the evidence." delay={.55} className="shimmer-text italic"/></h1>
        <motion.p initial={{opacity:0,y:18}} animate={{opacity:1,y:0}} transition={{duration:.9,delay:1,ease:EASE}} className="mx-auto mt-7 max-w-2xl text-base leading-8 text-ink/65 sm:text-lg">Vana turns natural-language questions into a traceable journey across plants, plant parts, phytochemicals, uses, bioactivity, targets and documents.</motion.p>

        <motion.form initial={{opacity:0,y:22}} animate={{opacity:1,y:0}} transition={{duration:.9,delay:1.15,ease:EASE}} onSubmit={e=>{e.preventDefault();go(v)}} className={`search-shell relative mt-10 flex w-full max-w-2xl items-center gap-2 rounded-[26px] border bg-parchment2/90 p-2 pl-5 backdrop-blur-md transition-all duration-500 ${focus?"border-canopy shadow-[0_0_0_5px_rgba(36,76,56,.1),0_24px_60px_rgba(36,76,56,.18)] -translate-y-0.5":"border-specimen shadow-specimen"}`}>
          <Search size={18} className={`shrink-0 transition-colors ${focus?"text-canopy":"text-moss"}`}/>
          <div className="relative min-w-0 flex-1"><input value={v} onChange={e=>setV(e.target.value)} onFocus={()=>setFocus(true)} onBlur={()=>setFocus(false)} aria-label="Ask a question" className="relative z-10 w-full bg-transparent py-3.5 text-left text-sm outline-none sm:text-base"/>
            <AnimatePresence>{!v&&<motion.span key={ph} initial={{opacity:0,y:8}} animate={{opacity:1,y:0}} exit={{opacity:0,y:-8}} transition={{duration:.4}} className="pointer-events-none absolute inset-y-0 left-0 flex items-center truncate text-sm text-ink/40 sm:text-base">{PLACEHOLDERS[ph]}</motion.span>}</AnimatePresence></div>
          <button className="press group flex shrink-0 items-center gap-2 rounded-[19px] bg-canopy px-5 py-3.5 text-sm font-semibold text-parchment2 transition hover:bg-canopy2">Explore <ArrowUpRight size={16} className="transition-transform duration-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5"/></button>
        </motion.form>

        <div className="mt-6 flex max-w-3xl flex-wrap justify-center gap-2">{SUG.map((s,i)=><motion.button key={s} type="button" onClick={()=>go(s)} initial={{opacity:0,y:12}} animate={{opacity:1,y:0}} transition={{duration:.6,delay:1.4+i*.08,ease:EASE}} className="chip bg-parchment2/80 backdrop-blur">{s}</motion.button>)}</div>
      </motion.div>
      <motion.a href="#how" initial={{opacity:0}} animate={{opacity:1}} transition={{delay:2.2}} className="absolute bottom-6 left-1/2 hidden -translate-x-1/2 flex-col items-center gap-2 text-[10px] uppercase tracking-[.2em] text-moss/70 sm:flex" aria-label="Scroll"><span>Scroll</span><span className="relative h-9 w-px overflow-hidden bg-specimen"><span className="scroll-dot absolute left-0 top-0 h-3 w-px bg-canopy"/></span></motion.a>
    </section>

    {/* HOW IT WORKS */}
    <section id="how" className="relative mx-auto max-w-6xl px-5 py-28 sm:px-8">
      <Reveal className="mx-auto max-w-2xl text-center"><p className="specimen-label">How Vana thinks</p><h2 className="mt-3 text-balance font-display text-4xl text-canopy2 sm:text-5xl">From a question to a <span className="italic text-canopy">traceable</span> answer</h2></Reveal>
      <div className="relative mt-16 grid gap-5 md:grid-cols-3">
        <div className="pointer-events-none absolute left-[16%] right-[16%] top-[54px] hidden h-px bg-gradient-to-r from-transparent via-specimen to-transparent md:block"/>
        {([[Sprout,"01 · Resolve","Understand the question","Natural language is resolved to the exact plants, compounds and targets your graph understands."],[Waypoints,"02 · Trace","Follow graph relationships","Every returned relationship can be explored, highlighted and inspected node by node."],[FileCheck2,"03 · Explain","Read a grounded answer","The explanation is tied back to evidence facts, measurements and document provenance."]] as const).map(([Icon,k,t,d],i)=>
          <Reveal key={k} delay={i*.12}><div className="lift-card group relative h-full rounded-3xl border border-specimen bg-parchment2 p-7 text-left shadow-specimen"><div className="relative z-10 flex h-14 w-14 items-center justify-center rounded-2xl bg-canopy text-parchment2 shadow-lg shadow-canopy/20 transition-transform duration-500 group-hover:-rotate-6 group-hover:scale-110"><Icon size={24}/></div><p className="specimen-label mt-6">{k}</p><p className="mt-2 font-display text-2xl text-canopy2">{t}</p><p className="mt-3 text-sm leading-7 text-ink/60">{d}</p></div></Reveal>)}
      </div>
    </section>

    {/* LIVE GRAPH STATS */}
    <section id="graph" className="relative overflow-hidden bg-canopy2 py-28 text-parchment2">
      <div className="pointer-events-none absolute inset-0 opacity-40 [background-image:radial-gradient(rgba(251,248,241,.14)_1px,transparent_1px)] [background-size:22px_22px]"/><div className="pointer-events-none absolute -left-32 top-0 h-96 w-96 rounded-full bg-turmeric/20 blur-[110px]"/><div className="pointer-events-none absolute -right-24 bottom-0 h-96 w-96 rounded-full bg-moss/40 blur-[110px]"/>
      <div className="relative mx-auto max-w-6xl px-5 sm:px-8">
        <Reveal className="mx-auto max-w-2xl text-center"><p className="flex items-center justify-center gap-2 text-[10px] font-semibold uppercase tracking-[.16em] text-sage"><span className={`h-1.5 w-1.5 rounded-full ${live?"bg-emerald-400 animate-pulse":"bg-sage/60"}`}/>{live?"Live from the knowledge graph":"The knowledge graph"}</p><h2 className="mt-3 text-balance font-display text-4xl sm:text-5xl">A living map of botanical evidence</h2></Reveal>
        <div className="mt-14 grid grid-cols-2 gap-px overflow-hidden rounded-3xl border border-white/10 bg-white/10 sm:grid-cols-4">
          {([...STAT_LABELS, ["total_relationships", "Relationships"]] as [string, string][]).map(([k, label], i) => {
            const value = k === "total_relationships" ? stats?.total_relationships : stats?.nodes?.[k];
            return <Reveal key={k} delay={i * .06} className="bg-canopy2/90"><div className="p-7 text-left"><div className="font-display text-4xl sm:text-5xl">{typeof value === "number" ? <CountUp to={value}/> : <span aria-label="Loading live count">—</span>}</div><p className="mt-2 text-xs uppercase tracking-[.14em] text-sage">{label}</p></div></Reveal>;
          })}
        </div>
      </div>
    </section>

    {/* PLANT DIRECTORY (live; hidden when API has no list) */}
    {plants.length>0&&<section id="plants" className="mx-auto max-w-5xl px-5 py-28 sm:px-8">
      <Reveal className="text-center"><p className="specimen-label">Plant directory</p><h2 className="mt-3 font-display text-4xl text-canopy2 sm:text-5xl">{plants.length} plants, ready to explore</h2><p className="mx-auto mt-4 max-w-xl text-sm leading-7 text-ink/60">Pick any plant to open its graph. Not listed? Ask about it above and Vana will build it for you.</p></Reveal>
      <Reveal delay={.1}><div className="mx-auto mt-9 max-w-md"><div className="flex items-center gap-2 rounded-full border border-specimen bg-parchment2 px-4 py-2.5 transition focus-within:border-canopy focus-within:shadow-[0_0_0_4px_rgba(36,76,56,.1)]"><Search size={15} className="text-moss"/><input value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Filter by scientific or common name" className="w-full bg-transparent text-sm outline-none"/></div></div>
      <div className="mt-6 max-h-[28rem] overflow-y-auto rounded-3xl border border-specimen bg-parchment2 shadow-specimen"><table className="w-full text-left text-sm"><thead className="sticky top-0 bg-parchment2/95 backdrop-blur"><tr className="border-b border-specimen"><th className="specimen-label px-5 py-3.5">Plant</th><th className="specimen-label hidden px-5 py-3.5 sm:table-cell">Common name</th><th className="w-10"/></tr></thead><tbody>{shown.map(p=><tr key={p.scientific_name} onClick={()=>go(`Explore ${p.scientific_name}`)} className="group cursor-pointer border-b border-specimen/50 transition-colors last:border-0 hover:bg-turmeric/10"><td className="px-5 py-3 italic text-canopy2">{p.scientific_name}</td><td className="hidden px-5 py-3 text-ink/55 sm:table-cell">{p.common_names||"—"}</td><td className="pr-4 text-moss opacity-0 transition group-hover:opacity-100"><ArrowUpRight size={15}/></td></tr>)}{shown.length===0&&<tr><td colSpan={3} className="px-5 py-10 text-center text-ink/45">No plants match “{filter}”.</td></tr>}</tbody></table></div></Reveal>
    </section>}

    <footer className="border-t border-specimen/70 py-10 text-center text-xs text-ink/40">Vana renders the backend response as returned. Graph evidence is authoritative for what is shown.</footer>
  </div>}
