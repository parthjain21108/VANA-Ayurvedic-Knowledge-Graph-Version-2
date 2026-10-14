import { useCallback, useRef, useState } from "react";
import { ApiError, getQueryProgress, postQuery, type QueryProgress } from "@/services/api";
import { buildViewModel, type ViewModel } from "@/utils/adapter";

type QueryStatus = "idle" | "loading" | "success" | "error";
const pause = (milliseconds: number) => new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));

function newRequestId(): string {
  // Keep working over the HTTP public IP address where crypto.randomUUID may be unavailable.
  return `vana-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

export function useQueryFlow() {
  const [status, setStatus] = useState<QueryStatus>("idle");
  const [vm, setVm] = useState<ViewModel | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [ingestionProgress, setIngestionProgress] = useState<QueryProgress | null>(null);
  const queryAbort = useRef<AbortController | null>(null);
  const progressAbort = useRef<AbortController | null>(null);

  const clearIngestionProgress = useCallback(() => setIngestionProgress(null), []);

  const runQuery = useCallback(async (value: string) => {
    const query = value.trim();
    if (!query) return;

    queryAbort.current?.abort();
    progressAbort.current?.abort();
    const queryController = new AbortController();
    const progressController = new AbortController();
    const requestId = newRequestId();
    queryAbort.current = queryController;
    progressAbort.current = progressController;

    setStatus("loading");
    setVm(null);
    setErrorMessage(null);
    setIngestionProgress(null);

    // Poll in parallel with the synchronous /query request. Existing complete
    // plants never set active=true, so they continue to use the ordinary loader.
    const pollProgress = async () => {
      while (!progressController.signal.aborted) {
        try {
          const progress = await getQueryProgress(requestId, progressController.signal);
          if (progressController.signal.aborted) return;
          // The product requirement is to show the 12-step modal only for a
          // genuinely new plant. Existing incomplete records may be repaired
          // by the backend, but use the normal loader rather than "new plant" UI.
          if (progress?.active && progress.mode === "new") {
            setIngestionProgress(progress);
          }
          if (progress && (progress.status === "complete" || progress.status === "failed")) return;
        } catch (error) {
          if ((error as any)?.name === "AbortError") return;
        }
        await pause(450);
      }
    };
    void pollProgress();

    try {
      const raw = await postQuery(query, queryController.signal, requestId);
      const confirmedNewPlantIngestion =
        raw?.ingestion?.required === true &&
        raw?.ingestion?.started === true &&
        raw?.ingestion?.router?.status === "ingested";
      if (confirmedNewPlantIngestion) {
        const finalProgress = await getQueryProgress(requestId).catch(() => null);
        // The API response itself only marks ingestion as required after the
        // router has verified the serving graph. This fallback handles a very
        // fast run whose polling event was missed; it does not invent stage timing.
        setIngestionProgress({
          request_id: requestId,
          status: "complete",
          active: true,
          phase_index: 11,
          stage: finalProgress?.stage || "Plant relationships verified in Neo4j",
          mode: finalProgress?.mode || (raw?.ingestion?.router?.status === "repaired" ? "repair" : "new"),
          plant_name: finalProgress?.plant_name || raw?.ingestion?.router?.scientific_name || undefined,
          complete: true,
          message: finalProgress?.message || "The plant and its required plant-part relationships were verified.",
        });
      } else {
        // Never show new-plant UI for a healthy existing plant or an in-place
        // repair of an incomplete record. Those requests use the normal loader.
        setIngestionProgress(null);
      }

      const next = buildViewModel(raw);
      if (raw.status === "error" && !raw.graph && !raw.evidence) {
        setVm(null);
        setStatus("error");
        setErrorMessage(raw.error?.message || "No answer could be generated.");
      } else {
        setVm(next);
        setStatus("success");
      }
      setHistory((items) => [query, ...items.filter((item) => item !== query)].slice(0, 8));
    } catch (error) {
      if ((error as any)?.name === "AbortError") return;
      // A query can fail after ingestion already began. Fetch the final progress
      // event once before stopping polling so failure is visible in the modal.
      const finalProgress = await getQueryProgress(requestId).catch(() => null);
      if (finalProgress?.active && finalProgress.mode === "new") setIngestionProgress(finalProgress);
      setStatus("error");
      setErrorMessage(error instanceof ApiError ? error.message : "We could not reach the knowledge graph service. Check that the API is running.");
    } finally {
      progressController.abort();
    }
  }, []);

  const reset = useCallback(() => {
    queryAbort.current?.abort();
    progressAbort.current?.abort();
    setStatus("idle");
    setVm(null);
    setErrorMessage(null);
    setIngestionProgress(null);
  }, []);

  return { status, vm, errorMessage, history, runQuery, reset, ingestionProgress, clearIngestionProgress };
}
