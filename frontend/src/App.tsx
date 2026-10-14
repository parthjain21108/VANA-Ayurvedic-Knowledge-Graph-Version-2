import { useState } from "react";
import { LeafGlyph } from "@/components/Layout/BotanicalMotif";
import { BotanicalLoading } from "@/components/Layout/BotanicalLoading";
import { NewPlantModal } from "@/components/Ingestion/NewPlantModal";
import { Landing } from "@/pages/Landing";
import { Results } from "@/pages/Results";
import { useQueryFlow } from "@/hooks/useQueryFlow";

export default function App() {
  const { status, vm, errorMessage, runQuery, reset, history, ingestionProgress, clearIngestionProgress } = useQueryFlow();
  const [query, setQuery] = useState("");

  const search = (value: string) => {
    const nextQuery = value.trim();
    if (!nextQuery) return;
    setQuery(nextQuery);
    runQuery(nextQuery);
  };

  const showLoading = status === "loading";
  const progressVisible = Boolean(ingestionProgress?.active);
  const ingestedPlantName = ingestionProgress?.plant_name || vm?.subject || "The requested plant";

  return <div className="min-h-screen bg-parchment text-ink">
    {status === "idle" && <Landing onSearch={search}/>}

    {showLoading && <>
      <div className="flex items-center gap-2 px-5 py-4 text-canopy2"><LeafGlyph className="h-7 w-7"/><span className="font-display text-xl">Vana</span></div>
      <BotanicalLoading query={query}/>
    </>}

    {status === "error" && <div className="mx-auto flex min-h-screen max-w-xl items-center px-6">
      <div className="w-full rounded-[28px] border border-specimen bg-parchment2 p-8 text-center shadow-specimen">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-turmeric/10 text-turmeric">!</div>
        <h1 className="mt-5 font-display text-3xl text-canopy2">We lost the trail</h1>
        <p className="mt-3 leading-7 text-ink/60">{errorMessage}</p>
        <div className="mt-7 flex justify-center gap-2">
          <button onClick={() => query && search(query)} className="rounded-full bg-canopy px-5 py-3 text-sm font-semibold text-parchment2">Try again</button>
          <button onClick={reset} className="rounded-full border border-specimen px-5 py-3 text-sm font-semibold text-canopy2">Back home</button>
        </div>
        {history.length > 0 && <div className="mt-8 border-t border-specimen/60 pt-5 text-left"><p className="specimen-label">Recent questions</p><div className="mt-2 flex flex-wrap gap-2">{history.map((item) => <button key={item} className="chip" onClick={() => search(item)}>{item}</button>)}</div></div>}
      </div>
    </div>}

    {status === "success" && !showLoading && vm && <Results vm={vm} onSearch={search} onHome={reset}/>}

    {progressVisible && ingestionProgress && <NewPlantModal
      plantName={ingestedPlantName}
      status={ingestionProgress.status}
      mode={ingestionProgress.mode}
      message={ingestionProgress.message}
      activeStep={ingestionProgress.phase_index}
      resultsReady={status === "success" && Boolean(vm)}
      onComplete={clearIngestionProgress}
    />}
  </div>;
}
