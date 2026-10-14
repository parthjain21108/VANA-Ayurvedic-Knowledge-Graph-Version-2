import { motion } from "framer-motion";
import { Check, LoaderCircle } from "lucide-react";
import { INGESTION_PHASES } from "./ingestionPhases";

export function IngestionProgress({ activeStep, complete = false }: { activeStep: number; complete?: boolean }) {
  // The API phase_index is zero-based: 0 is step 1 and 11 is step 12.
  // A value below zero means the run has started but the first stage is not known yet.
  const reportedStep = Number.isFinite(activeStep) ? Math.trunc(activeStep) : -1;
  const boundedStep = Math.max(-1, Math.min(reportedStep, INGESTION_PHASES.length - 1));
  const displayCount = complete ? INGESTION_PHASES.length : boundedStep + 1;
  const currentPhase = boundedStep >= 0 ? INGESTION_PHASES[boundedStep] : null;

  return (
    <section className="mt-6" aria-label="Plant ingestion progress">
      <div className="flex items-center justify-between gap-3 text-xs text-ink/50">
        <span className="specimen-label">Plant knowledge pipeline</span>
        <span className="shrink-0 font-semibold tabular-nums text-canopy2" aria-live="polite">
          {complete ? "12/12 complete" : displayCount > 0 ? `Step ${displayCount} of 12` : "Preparing ···"}
        </span>
      </div>

      <div
        className="mt-3 grid grid-cols-12 gap-1.5"
        role="progressbar"
        aria-label="Plant knowledge pipeline stages"
        aria-valuemin={0}
        aria-valuemax={INGESTION_PHASES.length}
        aria-valuenow={displayCount}
        aria-valuetext={complete ? "All 12 stages complete" : displayCount > 0 ? `Step ${displayCount} of 12` : "Preparing pipeline"}
      >
        {INGESTION_PHASES.map((phase, index) => {
          const done = complete || index < boundedStep;
          const current = !complete && index === boundedStep;
          return (
            <motion.span
              key={phase.number}
              className={`h-2 rounded-full ${done ? "bg-canopy" : current ? "bg-turmeric" : "bg-specimen/70"}`}
              animate={current ? { opacity: [0.55, 1, 0.55] } : { opacity: 1 }}
              transition={current ? { duration: 1.25, repeat: Infinity, ease: "easeInOut" } : { duration: 0.2 }}
              aria-hidden="true"
            />
          );
        })}
      </div>

      <div className="mt-4 rounded-2xl border border-canopy/15 bg-sage/20 px-4 py-3">
        <p className="specimen-label">Current step</p>
        <p className="mt-1 text-sm font-semibold text-canopy2">
          {complete ? "All pipeline stages completed" : currentPhase?.title || "Preparing to collect plant information"}
        </p>
        <p className="mt-1 text-xs leading-5 text-ink/55">
          {complete
            ? "The plant and its required graph relationships have been verified."
            : currentPhase
              ? "Vana is processing this stage before moving on to the next one."
              : "The progress tracker will update when the first pipeline stage is reported."}
        </p>
      </div>

      <div className="mt-4 max-h-44 space-y-1 overflow-y-auto pr-1" aria-label="All pipeline stages">
        {INGESTION_PHASES.map((phase, index) => {
          const done = complete || index < boundedStep;
          const current = !complete && index === boundedStep;
          return (
            <div
              key={phase.number}
              aria-current={current ? "step" : undefined}
              className={`flex items-center gap-3 rounded-xl border px-3 py-2 ${current ? "border-canopy/25 bg-sage/25" : "border-transparent"}`}
            >
              <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border ${done ? "border-canopy bg-canopy text-parchment2" : current ? "border-turmeric bg-turmeric/10 text-turmeric" : "border-specimen text-moss"}`}>
                {done ? <Check size={13} aria-hidden="true" /> : current ? <LoaderCircle size={13} className="animate-spin" aria-hidden="true" /> : <span className="text-[10px]">{phase.number}</span>}
              </span>
              <span className={`min-w-0 flex-1 text-xs ${current ? "font-semibold text-canopy2" : done ? "text-ink/55" : "text-ink/60"}`}>
                {phase.title}
              </span>
              {current && <span className="text-[9px] font-semibold uppercase tracking-[.1em] text-canopy">Now</span>}
            </div>
          );
        })}
      </div>
    </section>
  );
}
