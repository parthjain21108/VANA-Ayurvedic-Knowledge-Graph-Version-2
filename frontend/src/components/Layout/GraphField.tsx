import{useEffect,useRef}from"react";

/** Ambient, living knowledge-graph constellation for the landing hero. Pure SVG + one rAF loop that writes
 *  attributes directly (no React re-renders). Nodes drift on slow orbits, edges follow, the pointer gently
 *  pushes nearby nodes, and signal pulses travel along edges. */
const W=1200,H=720;
const COLORS=["#244c38","#5f755f","#b77927","#8a9a6a"];
function rng(seed:number){return()=>{seed|=0;seed=seed+0x6D2B79F5|0;let t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
interface N{x:number;y:number;bx:number;by:number;r:number;c:string;ph:number;sp:number;amp:number;ox:number;oy:number}

export function GraphField({className=""}:{className?:string}){
  const svg=useRef<SVGSVGElement>(null);
  useEffect(()=>{
    const el=svg.current;if(!el)return;
    const R=rng(7);const nodes:N[]=[];
    for(let i=0;i<34;i++){const bx=40+R()*(W-80),by=30+R()*(H-60);nodes.push({x:bx,y:by,bx,by,r:i%7===0?9:3+R()*4,c:COLORS[Math.floor(R()*COLORS.length)],ph:R()*6.28,sp:.00018+R()*.00028,amp:10+R()*26,ox:0,oy:0})}
    const edges:[number,number][]=[];
    nodes.forEach((a,i)=>{const near=nodes.map((b,j)=>({j,d:Math.hypot(a.bx-b.bx,a.by-b.by)})).filter(o=>o.j>i&&o.d<210).sort((p,q)=>p.d-q.d).slice(0,2);near.forEach(o=>edges.push([i,o.j]))});
    const NS="http://www.w3.org/2000/svg";
    const g=document.createElementNS(NS,"g");el.appendChild(g);
    const lines=edges.map(()=>{const l=document.createElementNS(NS,"line");l.setAttribute("stroke","#5f755f");l.setAttribute("stroke-opacity",".22");l.setAttribute("stroke-width","1");g.appendChild(l);return l});
    const pulses=[0,1,2,3,4].map(k=>{const c=document.createElementNS(NS,"circle");c.setAttribute("r","2.6");c.setAttribute("fill","#b77927");g.appendChild(c);return{c,e:Math.floor(R()*edges.length),t:-k*.7}});
    const dots=nodes.map(n=>{const c=document.createElementNS(NS,"circle");c.setAttribute("r",String(n.r));c.setAttribute("fill",n.c);c.setAttribute("fill-opacity",n.r>8?".9":".55");if(n.r>8){c.setAttribute("stroke","#b77927");c.setAttribute("stroke-opacity",".5");c.setAttribute("stroke-width","6");c.setAttribute("stroke-linecap","round")}g.appendChild(c);return c});
    const reduce=window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let mx=-999,my=-999,raf=0,last=performance.now();
    const onMove=(e:PointerEvent)=>{const b=el.getBoundingClientRect();const s=Math.max(b.width/W,b.height/H);mx=(e.clientX-b.left-(b.width-W*s)/2)/s;my=(e.clientY-b.top-(b.height-H*s)/2)/s};
    const onLeave=()=>{mx=my=-999};
    window.addEventListener("pointermove",onMove,{passive:true});window.addEventListener("pointerleave",onLeave);
    const frame=(now:number)=>{
      const dt=Math.min(now-last,50);last=now;
      nodes.forEach((n,i)=>{
        const tx=n.bx+Math.cos(now*n.sp+n.ph)*n.amp,ty=n.by+Math.sin(now*n.sp*1.3+n.ph)*n.amp*.8;
        const dx=tx-mx,dy=ty-my,d=Math.hypot(dx,dy);let px=0,py=0;if(d<170){const f=(1-d/170)*46;px=dx/(d||1)*f;py=dy/(d||1)*f}
        n.ox+=(px-n.ox)*.08;n.oy+=(py-n.oy)*.08;n.x=tx+n.ox;n.y=ty+n.oy;
        dots[i].setAttribute("cx",n.x.toFixed(1));dots[i].setAttribute("cy",n.y.toFixed(1));
      });
      edges.forEach(([a,b],i)=>{const l=lines[i];l.setAttribute("x1",nodes[a].x.toFixed(1));l.setAttribute("y1",nodes[a].y.toFixed(1));l.setAttribute("x2",nodes[b].x.toFixed(1));l.setAttribute("y2",nodes[b].y.toFixed(1))});
      pulses.forEach(p=>{p.t+=dt/1600;if(p.t>1){p.t=0;p.e=Math.floor(Math.random()*edges.length)}const[a,b]=edges[p.e];const t=Math.max(p.t,0);p.c.setAttribute("cx",(nodes[a].x+(nodes[b].x-nodes[a].x)*t).toFixed(1));p.c.setAttribute("cy",(nodes[a].y+(nodes[b].y-nodes[a].y)*t).toFixed(1));p.c.setAttribute("opacity",String(Math.sin(Math.min(t,1)*Math.PI)*.9))});
      if(!reduce)raf=requestAnimationFrame(frame);
    };
    raf=requestAnimationFrame(frame);
    return()=>{cancelAnimationFrame(raf);window.removeEventListener("pointermove",onMove);window.removeEventListener("pointerleave",onLeave);g.remove()};
  },[]);
  return <svg ref={svg} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid slice" className={className} aria-hidden/>}
