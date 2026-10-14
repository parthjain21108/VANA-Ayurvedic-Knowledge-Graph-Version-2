import { motion } from "framer-motion";
import { CheckCircle2, CircleAlert, Leaf } from "lucide-react";
import { LeafGlyph } from "@/components/Layout/BotanicalMotif";
import { IngestionProgress } from "@/components/Ingestion/IngestionProgress";

type Status = "started" | "running" | "complete" | "failed" | string;
type Mode = "new" | "repair" | string | undefined;

export function NewPlantModal({
  plantName,
  status,
  mode,
  message,
  activeStep,
  onComplete,
  resultsReady,
}: {
  plantName: string;
  status: Status;
  mode?: Mode;
  message?: string;
  activeStep: number;
  onComplete: () => void;
  resultsReady: boolean;
}) {
  const complete = status === "complete";
  const failed = status === "failed";
  const repairing = mode === "repair";

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-canopy2/55 px-4 py-6 backdrop-blur-md"
      role="dialog"
      aria-modal="true"
      aria-labelledby="new-plant-title"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 18 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-xl max-h-[calc(100vh_-_3rem)] overflow-y-auto rounded-[30px] border border-parchment2/60 bg-parchment2 shadow-[0_30px_90px_rgba(0,0,0,.28)]"
      >
        <div className="border-b border-specimen px-6 py-6 sm:px-8">
          <div className="flex items-start gap-4">
            <div className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl ${failed ? "bg-red-100 text-red-700" : "bg-sage/30 text-canopy"}`}>
              {failed ? <CircleAlert className="h-8 w-8" /> : complete ? <CheckCircle2 className="h-8 w-8" /> : <LeafGlyph className="h-8 w-8" />}
            </div>
            <div className="min-w-0 flex-1">
              <p className="specimen-label">
                {failed ? "Ingestion needs attention" : complete ? "Knowledge graph verified" : repairing ? "Completing an incomplete plant record" : "NEW PLANT DISCOVERED"}
              </p>
              <h2 id="new-plant-title" className="mt-1 font-display text-2xl text-canopy2 sm:text-3xl">
                {failed ? "We couldn't finish this plant yet." : complete ? "Thank you for helping Vana grow." : "Thank you for expanding our database."}
              </h2>
              <p className="mt-2 truncate text-sm text-ink/55"><span className="italic">{plantName || "Requested plant"}</span></p>
            </div>
          </div>
        </div>

        <div className="px-6 py-7 sm:px-8 sm:py-8">
          {failed ? (
            <div className="rounded-2xl border border-red-300/70 bg-red-50 p-5 text-sm leading-7 text-red-900">
              <p className="font-semibold">Vana could not verify a usable graph result.</p>
              <p className="mt-2">{message || "The plant and its required relationships were not confirmed. Vana has not marked this as a successful addition. Please check the server logs before trying again."}</p>
              <button onClick={onComplete} className="mt-5 rounded-full bg-canopy px-5 py-3 text-sm font-semibold text-parchment2">Close</button>
            </div>
          ) : complete ? (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
              <div className="flex items-center gap-3 rounded-2xl border border-canopy/20 bg-sage/20 p-5 text-sm leading-7 text-ink/70">
                <CheckCircle2 className="h-6 w-6 shrink-0 text-canopy" />
                <div>
                  <p className="font-semibold text-canopy2">The plant record and its graph relationships were verified.</p>
                  <p className="mt-1">{resultsReady ? "Your results are ready." : "The query finished successfully."}</p>
                </div>
              </div>
              <div className="mt-6 flex justify-end">
                <button onClick={onComplete} className="inline-flex items-center gap-2 rounded-full bg-canopy px-6 py-3 text-sm font-semibold text-parchment2 transition hover:bg-canopy2">
                  <Leaf size={16} /> {resultsReady ? "Continue to results" : "Close"}
                </button>
              </div>
            </motion.div>
          ) : (
            <div className="text-left">
              <p className="text-sm leading-6 text-ink/65">
                {repairing
                  ? "This plant has an incomplete graph record. Vana is checking its scientific details and verifying its relationships before showing the result."
                  : "This plant is not in Vana's database yet. Vana is collecting and cross-checking scientific details, then validating the plant's relationships."}
              </p>
              <IngestionProgress activeStep={activeStep} />
              <p className="mt-4 text-xs leading-5 text-ink/45">
                Please keep this tab open and don't submit the same plant again while it is being processed. Some stages take longer than others.
              </p>
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
}
