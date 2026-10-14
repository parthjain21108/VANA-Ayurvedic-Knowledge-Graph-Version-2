import{Search,ArrowUpRight}from"lucide-react";
import{useMemo,useState}from"react";
import type{KnowledgeBasePlant}from"@/services/api";

export function PlantDirectory({plants,onSearch}:{plants:KnowledgeBasePlant[];onSearch:(q:string)=>void}){
  const[q,setQ]=useState("");
  const filtered=useMemo(()=>{
    const term=q.trim().toLowerCase();
    if(!term)return plants;
    return plants.filter(p=>p.scientific_name.toLowerCase().includes(term)||(p.common_name||"").toLowerCase().includes(term));
  },[plants,q]);

  return <section id="plant-directory" className="mx-auto mt-24 max-w-7xl px-5 pb-20 sm:px-8">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="specimen-label">Plant directory</p>
        <h2 className="mt-2 font-display text-3xl text-canopy2 sm:text-4xl">Every plant currently in Vana.</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-ink/55">Pulled directly from the serving Neo4j graph. Common name shows the first stored common name.</p>
      </div>
      <span className="rounded-full border border-specimen bg-parchment2 px-3 py-1.5 text-xs text-moss">{filtered.length.toLocaleString("en-IN")} shown</span>
    </div>

    <div className="mt-6 flex items-center gap-3 rounded-2xl border border-specimen bg-parchment2 px-4 py-3 shadow-specimen">
      <Search size={17} className="text-moss"/>
      <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search scientific or common name…" className="min-w-0 flex-1 bg-transparent text-sm outline-none"/>
      {q&&<button type="button" onClick={()=>setQ("")} className="chip">Clear</button>}
    </div>

    <div className="mt-5 overflow-hidden rounded-3xl border border-specimen bg-parchment2 shadow-specimen">
      <div className="max-h-[620px] overflow-auto">
        <table className="w-full min-w-[620px] text-left">
          <thead className="sticky top-0 z-10 bg-parchment2/95 backdrop-blur">
            <tr className="border-b border-specimen/70 text-[10px] uppercase tracking-[.16em] text-moss">
              <th className="px-5 py-4 font-semibold">#</th>
              <th className="px-5 py-4 font-semibold">Scientific name</th>
              <th className="px-5 py-4 font-semibold">Common name</th>
              <th className="px-5 py-4 text-right font-semibold">Explore</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-specimen/55">
            {filtered.map((plant,i)=><tr key={plant.scientific_name} className="group transition hover:bg-parchment">
              <td className="px-5 py-4 text-xs text-ink/35">{i+1}</td>
              <td className="px-5 py-4 font-display italic text-canopy2">{plant.scientific_name}</td>
              <td className="px-5 py-4 text-sm text-ink/65">{plant.common_name||"—"}</td>
              <td className="px-5 py-4 text-right"><button onClick={()=>onSearch(`Tell me about ${plant.scientific_name}`)} className="inline-flex items-center gap-1 rounded-full border border-specimen bg-parchment2 px-3 py-1.5 text-xs font-semibold text-canopy2 opacity-70 transition hover:border-turmeric hover:bg-turmeric/10 group-hover:opacity-100">Explore <ArrowUpRight size={13}/></button></td>
            </tr>)}
            {filtered.length===0&&<tr><td colSpan={4} className="px-6 py-14 text-center text-sm text-ink/45">No plants match “{q}”.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  </section>;
}
