import { motion } from "framer-motion";
import { LeafGlyph, Sprig } from "@/components/Layout/BotanicalMotif";

/**
 * General query loading UI. Exact pipeline stages are shown separately by the
 * new-plant ingestion modal when the progress API reports an active ingestion.
 * Ordinary queries use an indeterminate bar rather than simulated stage timing.
 */
export function BotanicalLoading({ query }: { query: string }) {
  return (
    <div className="relative mx-auto flex min-h-[78vh] max-w-3xl items-center justify-center px-5 py-16">
      <Sprig className="pointer-events-none absolute -left-16 bottom-4 hidden h-72 w-44 text-moss/25 lg:block" animate={false} />
      <Sprig className="pointer-events-none absolute -right-16 top-0 hidden h-72 w-44 text-moss/20 lg:block" />
      <div className="w-full text-center">
        <div className="relative mx-auto mb-8 flex h-28 w-28 items-center justify-center">
          <span className="absolute inset-0 rounded-full border border-turmeric/50" />
          <span className="absolute inset-3 rounded-full border border-moss/40" />
          <LeafGlyph className="h-14 w-14 text-canopy" />
        </div>
        <p className="specimen-label">Exploring Vana</p>
        <h2 className="mt-2 font-display text-3xl text-canopy2 sm:text-4xl">Following the botanical trail</h2>
        <p className="mx-auto mt-3 max-w-xl truncate text-sm text-ink/55">“{query}”</p>

        <div className="mx-auto mt-10 max-w-md" role="status" aria-live="polite">
          <p className="text-sm font-medium text-canopy2">Vana is working through your question</p>
          <p className="mt-2 text-sm leading-relaxed text-ink/60">
            Checking the knowledge graph and assembling the evidence for your answer.
          </p>
          <div
            className="relative mt-6 h-2 overflow-hidden rounded-full bg-specimen/60"
            role="progressbar"
            aria-label="Processing your query"
            aria-valuetext="Processing your query"
          >
            <motion.div
              className="absolute inset-y-0 left-0 w-1/3 rounded-full bg-canopy"
              animate={{ x: ["-110%", "330%"] }}
              transition={{ duration: 1.6, ease: "easeInOut", repeat: Infinity }}
            />
          </div>
          <p className="mt-3 text-xs text-ink/45">This can take a little longer when Vana is gathering new scientific information.</p>
        </div>
      </div>
    </div>
  );
}
