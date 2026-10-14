import{AnimatePresence,motion}from"framer-motion";
import{useEffect,useState}from"react";

const QUOTES=[
  "The graph is where the evidence meets the plant.",
  "A botanical name is the beginning of a trail, not the end.",
  "Follow the relationship. Inspect the evidence. Then decide what it means.",
];

export function QuoteRotator(){
  const[index,setIndex]=useState(0);
  useEffect(()=>{
    const timer=window.setInterval(()=>setIndex(i=>(i+1)%QUOTES.length),5200);
    return()=>window.clearInterval(timer);
  },[]);

  return <div className="mt-8 flex min-h-14 items-center justify-center text-center">
    <AnimatePresence mode="wait">
      <motion.p
        key={index}
        initial={{opacity:0,y:8}}
        animate={{opacity:1,y:0}}
        exit={{opacity:0,y:-8}}
        transition={{duration:.45}}
        className="max-w-2xl font-display text-lg italic text-canopy2 sm:text-xl"
      >
        “{QUOTES[index]}”
      </motion.p>
    </AnimatePresence>
  </div>;
}
