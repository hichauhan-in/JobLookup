// Every call to the backend goes through here, so an error always arrives as a
// sentence rather than as an unhandled rejection somewhere in a view.

async function request(method, path, body, options = {}) {
  const init = { method, headers: {} };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.headers["content-type"] = "application/json";
    init.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    throw new Error(`Could not reach JobLookup: ${error.message}. Is the app still running?`);
  }

  if (options.raw) return response;

  const text = await response.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const detail = payload?.detail || payload?.error || text || `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body ?? {}),
  put: (path, body) => request("PUT", path, body ?? {}),
  del: (path) => request("DELETE", path),
  upload: (path, formData) => request("POST", path, formData),

  state: () => api.get("/api/state"),
  health: () => api.get("/api/health"),
  paths: () => api.get("/api/paths"),

  settings: () => api.get("/api/settings"),
  providers: () => api.get("/api/llm/providers"),
  budget: (options = {}) => api.post("/api/llm/budget", options),
  spend: () => api.get("/api/llm/spend"),
  saveSettings: (patch) => api.post("/api/settings", { patch }),
  setProvider: (choice) => api.post("/api/llm/provider", choice),
  testProvider: () => api.post("/api/llm/test"),
  setSecret: (name, value) => api.post("/api/secrets", { name, value }),

  cvs: () => api.get("/api/cvs"),
  deleteCv: (id) => api.del(`/api/cvs/${id}`),
  primaryCv: (id) => api.post(`/api/cvs/${id}/primary`),
  reextract: (id) => api.post(`/api/cvs/${id}/extract`),

  profile: () => api.get("/api/profile"),
  saveProfile: (patch) => api.put("/api/profile", patch),
  rebuildProfile: () => api.post("/api/profile/rebuild"),

  sources: () => api.get("/api/sources"),
  toggleSource: (key, enabled) => api.post(`/api/sources/${key}/enabled`, { enabled }),
  ackRisk: (key, acknowledged) => api.post(`/api/sources/${key}/risk`, { acknowledged }),
  configureSource: (key, config) => api.post(`/api/sources/${key}/config`, { config }),
  setRegion: (code, apply = false, options = {}) =>
    api.post("/api/sources/region", { code, apply, ...options }),
  clearRegion: () => api.post("/api/sources/region/clear"),
  setRemoteOnly: (value) => api.saveSettings({ search: { remote_only: value } }),
  suggestCompanies: (options = {}) => api.post("/api/sources/suggest", options),
  suggestRoles: () => api.post("/api/profile/roles"),
  signIn: (key) => api.post(`/api/sources/${key}/signin`),
  testSelectors: (key) => api.post(`/api/sources/${key}/test`),
  installPlaywright: () => api.post("/api/sources/playwright/install"),

  search: (options = {}) => api.post("/api/search", options),
  match: (rescore) => api.post("/api/match", { rescore }),
  runs: () => api.get("/api/runs"),

  history: () => api.get("/api/history"),
  historyRun: (id) => api.get(`/api/history/${id}`),
  deleteHistoryRun: (id) => api.del(`/api/history/${id}`),
  clearHistory: () => api.del("/api/history"),

  queryJobs: (filter) => api.post("/api/jobs/query", filter),
  job: (id) => api.get(`/api/jobs/${id}`),
  hideJob: (id, hidden) => api.post(`/api/jobs/${id}/hide?hidden=${hidden}`),
  setApplication: (id, status, notes) => api.post(`/api/jobs/${id}/application`, { status, notes }),
  deleteApplication: (id) => api.del(`/api/jobs/${id}/application`),
  applications: () => api.get("/api/applications"),
  resetMatches: (options = {}) => api.post("/api/matches/reset", options),

  tailor: (id, cvId) => api.post(`/api/jobs/${id}/tailor`, { cv_id: cvId ?? null }),

  tasks: () => api.get("/api/tasks"),
  task: (id) => api.get(`/api/tasks/${id}`),
  cancelTask: (id) => api.post(`/api/tasks/${id}/cancel`),
};
