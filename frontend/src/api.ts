import { QueryClient, useQuery } from "@tanstack/react-query";
import type { SearchTrack, Workspace } from "./types";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 15_000, retry: 1, refetchOnWindowFocus: false },
  },
});

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const timeout = AbortSignal.timeout(45_000);
  const response = await fetch(`/api${path}`, {
    ...options,
    credentials: "same-origin",
    signal: options.signal
      ? AbortSignal.any([options.signal, timeout])
      : timeout,
    headers: {
      ...(options.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...options.headers,
    },
  });
  if (!response.headers.get("content-type")?.includes("application/json")) {
    throw new ApiError(
      `The server returned HTTP ${response.status}.`,
      response.status,
    );
  }
  const payload = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(payload.detail)
      ? payload.detail.map((item: { msg?: string }) => item.msg).join("; ")
      : payload.detail;
    throw new ApiError(
      detail || "The request could not be completed.",
      response.status,
    );
  }
  return payload as T;
}

export function post<T>(path: string, body: unknown = {}): Promise<T> {
  return request(path, { method: "POST", body: JSON.stringify(body) });
}

export function useWorkspace() {
  return useQuery({
    queryKey: ["workspace"],
    queryFn: ({ signal }) => request<Workspace>("/workspace", { signal }),
  });
}

export function useTracks() {
  return useQuery({
    queryKey: ["tracks"],
    queryFn: ({ signal }) => request<{ items: SearchTrack[] }>("/tracks", { signal }),
  });
}

export async function refreshWorkspace() {
  await Promise.all(
    [
      "workspace",
      "opportunities",
      "opportunity",
      "applications",
      "tasks",
      "agenda",
      "activity",
      "versions",
      "benchmark",
      "digest",
    ].map((key) => queryClient.invalidateQueries({ queryKey: [key] })),
  );
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    if (error.name === "TimeoutError")
      return "The server took too long to respond. Please retry.";
    if (error.message === "Failed to fetch")
      return "Cannot reach JobLookup. Check that the local server is running.";
    return error.message;
  }
  return "Something went wrong. Please retry.";
}

export async function downloadFile(
  path: string,
  filename: string,
): Promise<void> {
  const response = await fetch(`/api${path}`, {
    credentials: "same-origin",
    signal: AbortSignal.timeout(120_000),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new ApiError(
      payload.detail || `Download failed (HTTP ${response.status}).`,
      response.status,
    );
  }
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
