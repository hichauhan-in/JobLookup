export type Skill = {
  name: string;
  level?: string;
  years?: number;
  core?: boolean;
  evidence?: string;
};
export type Profile = {
  full_name?: string;
  headline?: string;
  summary?: string;
  seniority?: string;
  total_years_experience?: number;
  skills?: Skill[];
  target_titles?: string[];
  locations?: string[];
  work_modes?: string[];
  employment_types?: string[];
  recency_days?: number;
  exclusions?: string[];
  work_authorization?: string;
  links?: string[];
  email?: string;
  notes?: string;
};
export type Resume = {
  id: number;
  label: string;
  filename: string;
  extract_state: string;
  extract_error?: string;
  is_primary: number;
  raw_text_chars: number;
};
export type Task = {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  label: string;
  stage: string;
  message: string;
  error: string;
  fraction: number | null;
  elapsed: number;
  created_at: number;
  meta: Record<string, unknown>;
};
export type Run = {
  id: number;
  started_at: string;
  status: string;
  sources: string[];
  result_count: number;
  new_count: number;
  stats: {
    fetched?: number;
    kept?: number;
    new?: number;
    duplicates?: number;
    too_old?: number;
    by_source?: Record<string, number>;
    failures?: Record<string, string>;
  };
};
export type Workspace = {
  profile: { data: Profile; version: number; updated_at?: string };
  counts: {
    jobs: number;
    tracked: number;
    cvs: number;
    sources_enabled: number;
  };
  cvs: Resume[];
  runs: Run[];
  tasks: Task[];
  defaults: { days: number; region: string };
  matching: { engine: string; available: boolean; requires_ai: boolean };
};
export type Fit = {
  score: number;
  band: "strong" | "good" | "review" | "excluded";
  eligible: boolean;
  summary: string;
  engine: string;
  target_role: string;
  method: string;
  matched_skills: { skill: string; quote: string }[];
  other_skills: string[];
  criteria: {
    key: string;
    label: string;
    state: string;
    detail: string;
    points: number;
    maximum: number;
  }[];
  blockers: string[];
  warnings: string[];
};
export type Opportunity = {
  id: number;
  title: string;
  company: string;
  location: string;
  country: string;
  description?: string;
  work_mode: string;
  employment: string;
  seniority: string;
  posted_at: string | null;
  first_seen_at: string;
  last_seen_at: string;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  url: string;
  apply_url: string;
  hidden: number;
  fit: Fit;
  source_keys: string[];
  sources?: { source_key: string; url: string; seen_at: string }[];
  application_status: string | null;
  application_notes?: string;
};
export type Opportunities = {
  items: Opportunity[];
  total: number;
  scanned: number;
  page: number;
  page_size: number;
  buckets: {
    recommended: number;
    review: number;
    excluded: number;
    hidden: number;
    all: number;
  };
  has_profile: boolean;
  profile_version: number;
  engine: string;
};
export type Review = {
  summary: string;
  evidence: { skill: string; quote: string }[];
  questions: string[];
  provider: string;
  profile_version: number;
};
export type Application = {
  job_id: number;
  title: string;
  company: string;
  status: string;
  notes: string;
  updated_at: string;
  applied_at?: string;
  url: string;
  band?: string;
  composite?: number;
};
export type SourceField = {
  key: string;
  label: string;
  kind: string;
  placeholder: string;
  required: boolean;
  help: string;
};
export type Source = {
  key: string;
  name: string;
  tier: string;
  enabled: boolean;
  ready: boolean;
  requires_key: boolean;
  blocked_reason: string;
  homepage: string;
  description: string;
  last_status: string;
  last_error: string;
  last_count: number;
  last_run_at: string;
  config: Record<string, unknown>;
  fields: SourceField[];
  guide: {
    links?: { label: string; url: string }[];
    examples?: { seen: string; enter: string }[];
  };
};
export type Sources = {
  sources: Source[];
  regions: { code: string; name: string }[];
  region: { code: string; name: string };
};

export type Portal = Source & {
  risk_ack: boolean;
  access_mode: "session" | "public";
  public_supported: boolean;
  login_url: string;
  search_url: string;
  session: { authenticated: boolean; checked_at?: string };
};

export type Portals = {
  portals: Portal[];
  enabled: boolean;
  local_only: boolean;
  browser: { installed: boolean; browser_ready: boolean; detail: string };
  risk_notice: string;
};
export type Preset = {
  key: string;
  label: string;
  provider: string;
  base_url: string;
  suggested_models: string[];
  needs_paid_key: boolean;
  needs_base_url: boolean;
};
export type Connection = {
  provider: string;
  preset: string;
  base_url: string;
  model: string;
  key_set: boolean;
  presets: Preset[];
  local_matching: boolean;
};

export type BridgeModels = {
  models: string[];
  default_model: string;
  available: boolean;
  detail: string;
};
