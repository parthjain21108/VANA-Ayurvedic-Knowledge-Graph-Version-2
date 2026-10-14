export class ApiError extends Error {
  status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface QueryProgress {
  request_id: string;
  status: string;
  active: boolean;
  phase_index: number;
  stage?: string;
  mode?: "new" | "repair";
  plant_name?: string;
  complete: boolean;
  message?: string;
}

export async function postQuery(query: string, signal?: AbortSignal, requestId?: string) {
  let res: Response;
  try {
    res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, ...(requestId ? { request_id: requestId } : {}) }),
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError("Could not reach the Vana API.");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(data?.detail?.message || data?.error?.message || `API request failed (${res.status}).`, res.status);
  }
  return data;
}

export async function getQueryProgress(requestId: string, signal?: AbortSignal): Promise<QueryProgress | null> {
  try {
    const response = await fetch(`/api/query-progress/${encodeURIComponent(requestId)}`, {
      signal,
      cache: "no-store",
      headers: { "Cache-Control": "no-cache" },
    });
    if (!response.ok) return null;
    return await response.json() as QueryProgress;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    return null;
  }
}

export interface KbStats {
  nodes: Record<string, number>;
  relationships: Record<string, number>;
  total_nodes?: number;
  total_relationships?: number;
  checked_at?: string;
}
export interface KbPlant { scientific_name: string; common_names?: string | null }

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T | null> {
  try {
    const response = await fetch(`/api${path}`, {
      signal,
      cache: "no-store",
      headers: { "Cache-Control": "no-cache" },
    });
    if (!response.ok) return null;
    return await response.json() as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    return null;
  }
}

export const getKbStats = (signal?: AbortSignal) => getJson<KbStats>("/knowledge-base/stats", signal);
export const getKbPlants = (signal?: AbortSignal) => getJson<KbPlant[]>("/knowledge-base/plants", signal);
