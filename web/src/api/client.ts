/**
 * Client API local — aucune logique métier ici, uniquement des appels
 * vers FastAPI (qui réutilise le code Python existant).
 */

export type Project = Record<string, any>;

export interface ApiError extends Error {
  status: number;
  detail: unknown;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let detail: unknown = await res.text();
    try {
      detail = JSON.parse(detail as string);
    } catch {
      /* texte brut */
    }
    const err = new Error(apiErrorMessage({ status: res.status, detail })) as ApiError;
    err.status = res.status;
    err.detail = detail;
    throw err;
  }
  return res.json() as Promise<T>;
}

export interface FontWeight {
  weight: number;
  style: string;
  file: string;
  url: string;
  available: boolean;
}

export interface FontFamilyInfo {
  id: string;
  css_family: string;
  label: string;
  role: string;
  license: string;
  source: string;
  retrieved: string;
  weights: FontWeight[];
  complete: boolean;
}

export interface ModelInfo {
  id: string;
  label: string;
  description: string;
  version: number;
  recommended_duration: [number, number];
  aspect_ratios: string[];
  editable: string[];
  limits: string[];
}

export type EffectParamValue = number | boolean | string;

export interface EffectParamSpec {
  key: string;
  label: string;
  type: "number" | "integer" | "bool" | "color" | "select" | "text";
  default: EffectParamValue;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  options?: string[];
  max_chars?: number;
  placeholder?: string;
}

export interface EffectSpec {
  id: string;
  label: string;
  category: string;
  scopes: string[];
  targets: string[];
  needs_audio: boolean;
  description: string;
  note: string;
  params: EffectParamSpec[];
}

/** Ce que le projet stocke : la forme courte (« glitch_slices ») ou réglée. */
export type EffectValue = string | { id: string; params?: Record<string, EffectParamValue> };

export interface EffectsManifest {
  categories: Array<{ id: string; label: string }>;
  scopes: string[];
  scope_labels: Record<string, string>;
  max_per_target: number;
  effects: EffectSpec[];
}

export interface LibraryModel {
  id: string;
  builtin: boolean;
  label: string;
  description: string;
  model_id: string | null;
  model_version: number | null;
  version: number | null;
  scenes: number;
  duration: number;
  width: number | null;
  height: number | null;
  fps: number | null;
  media_count: number;
  modified: number;
  file: string | null;
  unreadable?: boolean;
}

export interface ResolvedBlock {
  model: { id: string; version: number };
  fps: number;
  width: number;
  height: number;
  scale: number;
  total_frames: number;
  duration: number;
  scenes: any[];
  signature: any;
  assets: Array<{ kind: string; ref: string; scene: string }>;
  fonts: Array<{ id: string; known: boolean; weights: number[] }>;
  seed: number;
}

export interface PrepareResponse {
  project: Project;
  resolved: ResolvedBlock;
  errors: string[];
  warnings: string[];
  licences: Array<{ ref: string; kind: string; licence: string; source: string; declared: boolean }>;
  composition: string | null;
}

export interface MediaUploadResult {
  id: string;
  url: string;
  render_url: string;
  filename: string;
  size: number;
  content_type: string;
}

// --- Production par lots -----------------------------------------------------

/** Dossier de médias connecté (fonds vidéo, musiques) : emplacement autorisé. */
export interface ConnectedFolder {
  id: string;
  name: string;
  path: string;
  kind: string;
  licence: string;
  added_at: string;
  present: boolean;
  imported: number;
  files?: Array<{
    rel: string;
    name: string;
    kind: string;
    size: number;
    media_id: string;
    ref: string;
    already_present?: boolean;
  }>;
  last_scan: {
    at: string;
    found: number;
    imported: number;
    new: number;
    existing: number;
    skipped: number;
    interrupted: boolean;
  } | null;
}

export interface FoldersSetup {
  folders: ConnectedFolder[];
  kinds: string[];
  registry_path: string;
  limits: { max_files_per_folder: number; max_depth: number; max_bytes: number };
}

export interface MediaAsset {
  media_id: string;
  ref: string;
  name: string;
  kind: string;
  folder: string;
  size: number;
}

/** Champ d'un modèle que le CSV peut remplir. */
export interface BatchField {
  key: string;
  label: string;
  type: "text" | "number" | "list" | "media";
  kind?: string;
  scene: string;
  required: boolean;
  sample?: string | number;
  min?: number;
  max?: number;
}

export interface CsvUploadResult {
  csv_id: string;
  file: string;
  columns: string[];
  rows: Record<string, string>[];
  preview: Record<string, string>[];
  row_count: number;
  encoding: string;
  delimiter: string;
  warnings: string[];
  fields?: BatchField[];
  suggested_mapping?: Record<string, string>;
}

export interface BatchPlanItem {
  index: number;
  name: string;
  filename: string;
  row_preview: Record<string, string>;
  assets_used: Array<Record<string, any> & { field: string; name?: string; media_id?: string }>;
  background_source: string;
  background_pass: number | null;
  music_source: string;
  music_pass: number | null;
  errors: string[];
  warnings: string[];
  scenes: number;
  duration: number;
  seed: number | null;
}

export interface BatchPlan {
  model: string;
  csv_id: string;
  mapping: Record<string, string>;
  options: Record<string, string>;
  summary: {
    rows: number;
    ready: number;
    invalid_rows: number[];
    video_assets: number;
    audio_assets: number;
    background_passes: number;
    music_passes: number;
    cycled_background: boolean;
    cycled_music: boolean;
    auto_background: boolean;
    auto_music: boolean;
  };
  warnings: string[];
  policy: Record<string, unknown>;
  items: BatchPlanItem[];
}

export interface BatchSetup {
  models: LibraryModel[];
  folders: ConnectedFolder[];
  assets: Record<string, MediaAsset[]>;
  csv_limits: { max_rows: number; max_bytes: number };
  batch_dir: string;
  policy: Record<string, unknown>;
}

export interface BatchItemRow {
  id: number;
  position: number;
  name: string;
  filename: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled" | "blocked";
  error: string;
  output_path: string;
  size_bytes: number | null;
  duration: number | null;
  frames: number | null;
  fps: number | null;
  attempts: number;
  warnings: string[];
  assets: Array<Record<string, any> & { field: string; name?: string }>;
  sources: { background?: string; pass?: number; music?: string; music_pass?: number };
  started_at?: string;
  finished_at?: string;
}

export interface BatchCounters {
  total: number;
  rendered: number;
  progress: number;
  queued: number;
  running: number;
  done: number;
  failed: number;
  cancelled: number;
  blocked: number;
}

export interface Batch {
  id: string;
  name: string;
  model_id: string;
  csv_id: string;
  status: "ready" | "running" | "paused" | "done" | "cancelled";
  overwrite: boolean;
  total: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  message: string;
  counters: BatchCounters;
  job_id: string;
  is_running: boolean;
  items?: BatchItemRow[];
}

export interface BatchPayload {
  model: string;
  csv_id: string;
  mapping: Record<string, string>;
  options: Record<string, string>;
  name: string;
  overwrite: boolean;
}

export interface AgentStatus {
  enabled: boolean;
  ready: boolean;
  reason: string;
  provider: string;
  is_cloud: boolean;
  model: string;
  base_url: string;
  key_configured: boolean;
  pin_configured: boolean;
  temperature: number;
  max_tokens: number;
  context_budget: number;
  timeout: number;
  json_mode: string;
  stream: boolean;
  max_repairs: number;
  max_tool_calls: number;
  knowledge: { built: boolean; engine: string; docs: number; chunks: number; error?: string };
  tools: { read: string[]; propose: string[]; execute_with_user: string[]; forbidden: string[] };
  capabilities: {
    models: string[];
    templates: string[];
    fonts: string[];
    media_count: number;
    animation_in: string[];
    remotion: string;
    remotion_packages: string[];
    not_available: string[];
    knowledge_sources: Array<{ id: string; title: string; version: string }>;
  };
}

export interface CheckReport {
  ok: boolean;
  provider?: string;
  base_url?: string;
  model?: string;
  is_cloud?: boolean;
  pin_configured?: boolean;
  hint?: string;
  error?: string;
  error_kind?: string;
  latency_ms?: number;
  reply?: string;
  models?: string[];
  capabilities?: Record<string, string>;
}

export interface ProposalSource {
  id: number;
  path: string;
  source: string;
  version: string;
  title: string;
  score: number;
}

export interface ProposalChange {
  target: string;
  before: string;
  after: string;
}

export interface Proposal {
  id: string;
  type: "question" | "unavailable" | "project_new" | "project_patch" | "library_save" | "batch_plan";
  summary: string;
  status: string;
  expires_at?: number;
  project_name: string;
  base_revision: string;
  has_candidate?: boolean;
  questions?: string[];
  capability?: string;
  alternative?: string;
  changes?: ProposalChange[];
  warnings?: string[];
  errors?: string[];
  validation?: { state: string; errors: string[]; warnings: string[] };
  candidate?: Project;
  library?: { label: string; description: string };
  batch?: {
    model: string;
    mapping: Record<string, string>;
    options: Record<string, string>;
    fields: Array<{ key: string; label: string; type: string }>;
    notes: string;
  };
  sources: ProposalSource[];
}

export interface AgentRun {
  proposal: Proposal;
  meta: {
    model: string;
    provider: string;
    attempts: number;
    tool_calls: number;
    latency_ms: number;
    estimated_input_tokens: number;
    context_budget_tokens: number;
    context_shrunk: boolean;
    prompt_mode: string;
    project_detail: string;
    context_sections: Record<string, number>;
    context_trimmed: string[];
    context_dropped: string[];
    knowledge_engine: string;
    json_mode: string;
    raw_length: number;
    rejected_errors: string[];
    retrieval_error: string;
  };
}

export interface AcceptResult {
  kind: string;
  project?: Project;
  revision?: string;
  rebuilt?: boolean;
  warnings?: string[];
  changes?: ProposalChange[];
  library?: { label: string; description: string };
  batch?: Proposal["batch"];
}

export interface LlmProviderState {
  model: string;
  key_configured: boolean;
  is_cloud: boolean;
  base_url: string;
  pin_configured?: boolean;
}

export interface LlmPublic {
  enabled: boolean;
  provider: string;
  providers: Array<{ id: string; label: string; is_cloud: boolean; base_url: string }>;
  local: LlmProviderState;
  gemini: LlmProviderState;
  groq: LlmProviderState;
  active: LlmProviderState;
  base_url: string;
  model: string;
  key_configured: boolean;
  pin_configured: boolean;
  is_cloud: boolean;
  clips_groq_key_available: boolean;
  temperature: number;
  max_tokens: number;
  context_budget: number;
  timeout: number;
  max_repairs: number;
  max_tool_calls: number;
  stream: boolean;
  json_mode: string;
  ready: boolean;
}

export interface LlmPayload {
  enabled?: boolean;
  provider?: string;
  local_base_url?: string;
  local_model?: string;
  local_api_key?: string;
  local_pin?: string;
  gemini_model?: string;
  gemini_api_key?: string;
  groq_model?: string;
  groq_api_key?: string;
  use_groq_clips_key?: boolean;
  clear_key?: boolean;
  temperature?: number;
  max_tokens?: number;
  context_budget?: number;
  timeout?: number;
  max_repairs?: number;
  max_tool_calls?: number;
  stream?: boolean;
  json_mode?: string;
}

export interface SettingsPublic {
  groq_configured: boolean;
  host: string;
  port: number;
  llm: LlmPublic;
  asr?: AsrPublic;
}

export interface BrandPackData {
  label: string;
  notes: string;
  theme: Record<string, unknown>;
  signature: Record<string, unknown>;
  audio: Record<string, unknown>;
  models: string[];
}

export interface BrandPackSummary {
  id: string;
  label: string;
  notes: string;
  models: string[];
  has_logo: boolean;
  has_music: boolean;
  theme_keys: string[];
  created_at: string;
  updated_at: string;
  file: string | null;
  unreadable?: boolean;
}

export interface DeliveryStatus {
  batch: { id: string; name: string; model_id: string; status: string; counters: Record<string, number> };
  total: number;
  rendered: number;
  is_packaging: boolean;
  package: {
    file: string;
    bytes: number;
    modified_at: string;
    prepared_at?: string;
    videos?: number;
    subtitles?: number;
    thumbnails?: number;
    metadata?: number;
    warnings?: string[];
  } | null;
  items: Array<{
    position: number;
    nom: string;
    fichier: string;
    statut: string;
    duree_s: number;
    octets: number;
    rendered: boolean;
  }>;
}

// --- Moments forts : transcription, détection, génération ---------------------

/** Un fournisseur de transcription, avec la raison écrite quand il est hors service. */
export interface AsrProviderState {
  id: string;
  label: string;
  cloud: boolean;
  available: boolean;
  kind?: string;
  models: string[];
  reason: string;
}

export interface AsrLocalBackend {
  kind: string;
  available: boolean;
  cli: string;
  model: string;
  reason: string;
}

/** Bloc « transcription » de /api/settings : états et raisons, jamais une clé. */
export interface AsrPublic {
  provider: string;
  groq_models: string[];
  model: string;
  language: string;
  key_configured: boolean;
  clips_key_available: boolean;
  providers: AsrProviderState[];
  local_backend: AsrLocalBackend;
}

export interface AsrPayload {
  provider?: string;
  groq_api_key?: string;
  clear_key?: boolean;
  groq_model?: string;
  language?: string;
}

/** /api/moments/providers : les choix réels plus les presets de la page. */
export interface MomentsSetup {
  providers: AsrProviderState[];
  local_backend: AsrLocalBackend;
  asr_key_configured: boolean;
  clips_key_configured: boolean;
  default_provider: string;
  default_model: string;
  language: string;
  duration_presets: Record<string, { label: string; min_seconds: number; max_seconds: number }>;
  top_default: number;
}

/** Un sous-titre du moment, en secondes relatives à la fenêtre. */
export interface MomentCue {
  start: number;
  end: number;
  text: string;
  words: number;
  raw_start: number;
  raw_end: number;
}

export interface MomentItem {
  id: string;
  position: number;
  start: number;
  end: number;
  duration: number;
  score: number;
  reasons: string[];
  text: string;
  cues: MomentCue[];
  keywords: string[];
}

export interface AnalysisSummary {
  id: string;
  source_ref: string;
  source_media_id: string;
  source_title: string;
  duration: number;
  provider: string;
  model: string;
  language: string;
  segments: number;
  moment_count: number;
  best_score: number;
  created_at: string;
  updated_at: string;
  unreadable?: boolean;
}

export interface MomentTimelineSpec {
  scene_start: number;
  scene_end: number;
  cue_start: number;
  cue_end: number;
  text: string;
  raw_start: number;
  raw_end: number;
}

/** L'analyse complète telle qu'elle est stockée dans moments/<id>.json. */
export interface AnalysisRecord {
  id: string;
  source_ref: string;
  source_media_id: string;
  source_title: string;
  created_at: string;
  updated_at: string;
  energy_file?: string;
  transcript?: {
    duration?: number;
    provider?: string;
    model?: string;
    language?: string;
    source?: string;
    warnings?: string[];
    segments?: Array<{ start: number; end: number; text: string }>;
  };
  detect?: { min_seconds: number; max_seconds: number; top: number; algorithm: string };
  moments?: MomentItem[];
  summary?: AnalysisSummary;
}

/** Ce que le projet porte déjà pour la publication : le paquet ne rédige rien. */
export interface MomentPublishBlock {
  title?: string;
  description?: string;
  hashtags?: string[];
  [key: string]: unknown;
}

export interface MomentGenerateResult {
  name: string;
  project: Project;
  project_path: string;
  voice_ref: string;
  thumbnail_ref: string;
  srt_available: boolean;
  srt_path: string;
  start: number;
  end: number;
  duration: number;
  cues: number;
  timeline: MomentTimelineSpec[];
  publish: MomentPublishBlock;
  warnings: string[];
}

export const api = {
  health: () => request<{ status: string; groq_configured: boolean; web_dist: boolean }>("/api/health"),

  // Projets
  listProjects: () =>
    request<Array<{ name: string; version: number | null; size: number; modified: number }>>(
      "/api/projects",
    ),
  loadProject: (name: string) =>
    request<{
      name: string;
      project: Project;
      errors: string[];
      warnings: string[];
      migrated_media: string[];
    }>(`/api/projects/${encodeURIComponent(name)}`),
  saveProject: (name: string, project: Project) =>
    request<{ name: string }>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ name, project }),
    }),
  deleteProject: (name: string) =>
    request<{ deleted: string }>(`/api/projects/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),
  validateProject: (project: Project) =>
    request<{ errors: string[]; warnings: string[] }>("/api/projects/validate", {
      method: "POST",
      body: JSON.stringify({ project }),
    }),

  // Studio : modèles, polices sous licence, préparation du rendu
  studioModels: () => request<{ models: ModelInfo[]; default: string }>("/api/studio/models"),
  studioEffects: () => request<EffectsManifest>("/api/studio/effects"),
  studioFonts: () =>
    request<{ families: FontFamilyInfo[]; missing_files: string[]; catalog: string }>("/api/studio/fonts"),
  studioDefault: (model = "quote_cinematic") =>
    request<{ project: Project }>(`/api/studio/default?model=${encodeURIComponent(model)}`),
  studioPrepare: (project: Project) =>
    request<PrepareResponse>("/api/studio/prepare", {
      method: "POST",
      body: JSON.stringify({ project }),
    }),
  studioUpgrade: (project: Project) =>
    request<{ project: Project; notes: string[]; errors: string[]; warnings: string[] }>(
      "/api/studio/upgrade",
      { method: "POST", body: JSON.stringify({ project }) },
    ),
  studioInspect: (project: Project) =>
    request<{ resolved: ResolvedBlock }>("/api/studio/inspect", {
      method: "POST",
      body: JSON.stringify({ project }),
    }),
  studioProvenance: (mediaId: string) =>
    request<{ id?: string; licence: string; declared: boolean; source?: string; imported_at?: string }>(
      `/api/studio/provenance/${encodeURIComponent(mediaId)}`,
    ),
  setProvenance: (media_id: string, source: string, licence: string) =>
    request<{ media_id: string; source: string; licence: string }>("/api/studio/provenance", {
      method: "POST",
      body: JSON.stringify({ media_id, source, licence }),
    }),

  // Bibliothèque de modèles (dossier models/, éditable à la main)
  libraryModels: () =>
    request<{ models: LibraryModel[]; folder: string; folder_path: string }>("/api/library"),
  libraryModel: (id: string) =>
    request<{ id: string; project: Project }>(`/api/library/${encodeURIComponent(id)}`),
  saveLibraryModel: (project: Project, label: string, description: string, modelId?: string) =>
    request<{ model: LibraryModel; warnings: string[] }>("/api/library", {
      method: "POST",
      body: JSON.stringify({ project, label, description, model_id: modelId ?? null }),
    }),
  deleteLibraryModel: (id: string) =>
    request<{ deleted: string }>(`/api/library/${encodeURIComponent(id)}`, { method: "DELETE" }),

  // Dossiers de médias connectés (fonds vidéo / musiques de fond)
  folders: () => request<FoldersSetup>("/api/folders"),
  folderAssets: (kind: string) =>
    request<{ kind: string; assets: MediaAsset[] }>(`/api/folders/assets?kind=${encodeURIComponent(kind)}`),
  addFolder: (path: string, kind: string, name: string, licence: string) =>
    request<ConnectedFolder>("/api/folders", {
      method: "POST",
      body: JSON.stringify({ path, kind, name, licence }),
    }),
  scanFolder: (id: string) =>
    request<{ job_id: string; folder_id: string; status: string }>(
      `/api/folders/${encodeURIComponent(id)}/scan`,
      { method: "POST" },
    ),
  removeFolder: (id: string) =>
    request<{ id: string; removed: boolean; note: string }>(`/api/folders/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  // Production par lots
  batchSetup: () => request<BatchSetup>("/api/batch/setup"),
  batchFields: (model: string) =>
    request<{ model: string; fields: BatchField[] }>(`/api/batch/fields?model=${encodeURIComponent(model)}`),
  uploadCsv: async (file: File, model: string): Promise<CsvUploadResult> => {
    const form = new FormData();
    form.append("file", file);
    form.append("model", model);
    const res = await fetch("/api/batch/csv", { method: "POST", body: form });
    if (!res.ok) {
      let detail: unknown = await res.text();
      try {
        detail = JSON.parse(detail as string);
      } catch {
        /* texte brut */
      }
      throw new Error(apiErrorMessage({ status: res.status, detail }));
    }
    return res.json() as Promise<CsvUploadResult>;
  },
  batchPlan: (payload: BatchPayload) =>
    request<BatchPlan>("/api/batch/plan", { method: "POST", body: JSON.stringify(payload) }),
  batchLine: (payload: BatchPayload, position: number) =>
    request<{ item: BatchPlanItem; project: Project }>(
      `/api/batch/line?position=${position}`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  batchStart: (payload: BatchPayload) =>
    request<{ batch: Batch; job_id: string; plan_summary: BatchPlan["summary"]; plan_warnings: string[] }>(
      "/api/batch/start",
      { method: "POST", body: JSON.stringify(payload) },
    ),
  batchList: () => request<{ batches: Batch[] }>("/api/batch"),
  batchDetail: (id: string, items = false) =>
    request<Batch>(`/api/batch/${encodeURIComponent(id)}?items=${items ? "true" : "false"}`),
  batchRun: (id: string) =>
    request<{ batch: Batch; job_id: string; status: string }>(
      `/api/batch/${encodeURIComponent(id)}/start`,
      { method: "POST" },
    ),
  batchCancel: (id: string) =>
    request<{ batch: Batch; message: string }>(`/api/batch/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
    }),
  batchRetry: (id: string) =>
    request<{ batch: Batch; requeued: number; started: string }>(
      `/api/batch/${encodeURIComponent(id)}/retry`,
      { method: "POST" },
    ),
  batchManifestUrl: (id: string, format: "json" | "csv") =>
    `/api/batch/${encodeURIComponent(id)}/manifest/file?format=${format}`,
  batchFileUrl: (id: string, position: number) =>
    `/api/batch/${encodeURIComponent(id)}/file?position=${position}`,
  batchForget: (id: string) =>
    request<{ deleted: string }>(`/api/batch/${encodeURIComponent(id)}`, { method: "DELETE" }),

  // Médias
  uploadMedia: async (
    file: File,
    provenance?: { source?: string; licence?: string },
  ): Promise<MediaUploadResult> => {
    const form = new FormData();
    form.append("file", file);
    form.append("source", provenance?.source ?? "");
    form.append("licence", provenance?.licence ?? "");
    const res = await fetch("/api/media/upload", { method: "POST", body: form });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(detail);
    }
    return res.json();
  },

  // Exports
  startExport: (name: string, project: Project, overwrite: boolean) =>
    request<{ job_id: string }>("/api/exports", {
      method: "POST",
      body: JSON.stringify({ name, project, overwrite }),
    }),
  exportStatus: (jobId: string) => request<JobSnapshot>(`/api/exports/${jobId}`),
  cancelExport: (jobId: string) =>
    request<JobSnapshot>(`/api/exports/${jobId}/cancel`, { method: "POST" }),
  /** URL de relecture d'un export terminé (pour contrôle visuel du rendu). */
  exportFileUrl: (jobId: string) => `/api/exports/${encodeURIComponent(jobId)}/file`,

  // Réglages
  getSettings: () => request<SettingsPublic>("/api/settings"),
  setGroqKey: (groq_api_key: string) =>
    request<{ groq_configured: boolean; llm: LlmPublic }>("/api/settings", {
      method: "POST",
      body: JSON.stringify({ groq_api_key }),
    }),
  setSettings: (payload: { groq_api_key?: string; llm?: LlmPayload; asr?: AsrPayload }) =>
    request<{ groq_configured: boolean; llm: LlmPublic; asr?: AsrPublic }>("/api/settings", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // Assistant IA (orchestration côté serveur, aucune exécution automatique)
  agentStatus: () => request<AgentStatus>("/api/agent/status"),
  agentCapabilities: () => request<Record<string, any>>("/api/agent/capabilities"),
  agentIndex: (force = false) =>
    request<Record<string, any>>(`/api/agent/index?force=${force ? "true" : "false"}`, { method: "POST" }),
  agentCheck: (payload: {
    provider?: string;
    base_url?: string;
    model?: string;
    api_key?: string;
    pin?: string;
  }) => request<CheckReport>("/api/agent/check", { method: "POST", body: JSON.stringify(payload) }),
  agentModels: (payload: { provider?: string; base_url?: string; api_key?: string; pin?: string }) =>
    request<{ models: string[]; provider: string }>("/api/agent/models", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  agentSearch: (query: string, limit = 5) =>
    request<{ query: string; engine: string; passages: Array<Record<string, any>> }>(
      "/api/agent/search",
      { method: "POST", body: JSON.stringify({ query, limit }) },
    ),
  agentAsk: (payload: {
    message: string;
    project?: Project | null;
    project_name?: string;
    revision?: string;
    selection?: Record<string, any> | null;
    history?: Array<{ role: string; content: string }>;
    csv_columns?: string[];
    mode?: string;
  }) => request<{ job_id: string; status: string }>("/api/agent/ask", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  agentProposal: (id: string, preview = false) =>
    request<{ proposal: Proposal }>(
      `/api/agent/proposals/${encodeURIComponent(id)}?preview=${preview ? "true" : "false"}`,
    ),
  agentAccept: (id: string, project: Project | null, rebase = false) =>
    request<AcceptResult>(`/api/agent/proposals/${encodeURIComponent(id)}/accept`, {
      method: "POST",
      body: JSON.stringify({ project, rebase }),
    }),
  agentReject: (id: string) =>
    request<{ rejected: string; project_unchanged?: boolean; note?: string }>(
      `/api/agent/proposals/${encodeURIComponent(id)}/reject`,
      { method: "POST" },
    ),

  deliveryStatus: (batchId: string) =>
    request<DeliveryStatus>(`/api/delivery/${encodeURIComponent(batchId)}`),
  deliveryPackage: (batchId: string) =>
    request<{ job_id: string; items: number }>(`/api/delivery/${encodeURIComponent(batchId)}/package`, {
      method: "POST",
    }),
  deliveryPackageUrl: (batchId: string) => `/api/delivery/${encodeURIComponent(batchId)}/package/file`,

  brandList: () =>
    request<{ brands: BrandPackSummary[]; folder: string; folder_path: string }>("/api/brands"),
  brandGet: (id: string) =>
    request<{ id: string; pack: BrandPackData }>(`/api/brands/${encodeURIComponent(id)}`),
  brandSave: (pack: Partial<BrandPackData>, brandId?: string | null) =>
    request<{ brand: BrandPackSummary; warnings: string[] }>("/api/brands", {
      method: "POST",
      body: JSON.stringify({ pack, brand_id: brandId ?? null }),
    }),
  brandDelete: (id: string) =>
    request<{ deleted: string }>(`/api/brands/${encodeURIComponent(id)}`, { method: "DELETE" }),
  brandApply: (id: string, project: Project) =>
    request<{ project: Project; warnings: string[] }>(`/api/brands/${encodeURIComponent(id)}/apply`, {
      method: "POST",
      body: JSON.stringify({ project }),
    }),
  brandCapture: (project: Project, label: string, notes: string) =>
    request<{ brand: BrandPackSummary; warnings: string[] }>("/api/brands/capture", {
      method: "POST",
      body: JSON.stringify({ project, label, notes }),
    }),

  // Moments forts : l'analyse propose, seul le clic sur « générer » applique
  momentsSetup: () => request<MomentsSetup>("/api/moments/providers"),
  momentsList: () => request<{ analyses: AnalysisSummary[] }>("/api/moments"),
  momentsAnalysis: (id: string) => request<AnalysisRecord>(`/api/moments/${encodeURIComponent(id)}`),
  momentsAnalyze: (payload: {
    source: string;
    provider?: string;
    api_key_source?: "asr" | "clips";
    model?: string;
    language?: string;
    min_seconds?: number;
    max_seconds?: number;
    top?: number;
  }) => request<{ job_id: string; status: string }>("/api/moments/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  momentsRecompute: (
    id: string,
    payload: { min_seconds?: number; max_seconds?: number; top?: number },
  ) =>
    request<{ analysis: AnalysisSummary; moments: MomentItem[]; energy_used: boolean }>(
      `/api/moments/${encodeURIComponent(id)}/recompute`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  momentsGenerate: (
    id: string,
    payload: {
      moment_id: string;
      brand_id?: string;
      handle?: string;
      source_title?: string;
      use_source_thumbnail?: boolean;
      overwrite?: boolean;
    },
  ) =>
    request<MomentGenerateResult>(`/api/moments/${encodeURIComponent(id)}/generate`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  momentsDelete: (id: string) =>
    request<{ deleted: string }>(`/api/moments/${encodeURIComponent(id)}`, { method: "DELETE" }),

  ttsStatus: () => request<TtsStatus>("/api/tts/status"),
  ttsDownload: (voice_id: string) =>
    request<{ job_id: string; status: string }>("/api/tts/download", {
      method: "POST",
      body: JSON.stringify({ voice_id }),
    }),
  ttsGenerate: (payload: { text: string; voice_id: string; speed: number }) =>
    request<{ job_id: string; status: string }>("/api/tts/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

/** Message lisible d'une erreur serveur, y compris quand le détail porte une
 *  liste d'erreurs de validation ({detail: {message, errors}}). */
export function apiErrorMessage(error: unknown): string {
  const anyError = error as any;
  const inner = anyError?.detail?.detail ?? anyError?.detail;
  if (inner && typeof inner === "object") {
    const errors = Array.isArray(inner.errors) ? inner.errors.map(String) : [];
    const text = inner.message ? String(inner.message) : "";
    return [text, ...errors].filter(Boolean).join(" — ") || String(anyError?.message ?? error);
  }
  // HTTPException(detail="texte") : le message utile est dans le détail, pas
  // dans l'objet Error construit à partir de la réponse.
  if (typeof inner === "string" && inner.trim()) return inner;
  return String(anyError?.message ?? error);
}

export interface JobSnapshot {
  id: string;
  kind: string;
  status: "running" | "done" | "error" | "cancelled";
  progress: number;
  message: string;
  result: any;
  error: string;
  cancelable: boolean;
  started_at: number;
  finished_at: number | null;
}

export interface TtsEngineState {
  available: boolean;
  reason: string;
}

export interface TtsVoice {
  id: string;
  engine: "piper" | "kokoro";
  label: string;
  language: string;
  gender: string;
  downloaded: boolean;
  ready: boolean;
  approx_mb: number;
}

export interface TtsStatus {
  engines: Record<string, TtsEngineState>;
  voices: TtsVoice[];
}

export interface TtsGenerateResult {
  media_id: string;
  ref: string;
  url: string;
  duration: number;
  sample_rate: number;
  voice: string;
  engine: string;
}

/** Convertit une référence de projet en URL serveur. */
export function mediaUrl(value: string | undefined): string | null {
  if (!value) return null;
  if (value.startsWith("media://")) return `/api/media/${value.slice("media://".length)}`;
  if (value.startsWith("/media-cache/")) return value;
  return null; // chemin absolu v1 : non servable en web (réimport requis)
}

/** Identifiant d'un média depuis une référence de projet. */
export function mediaId(value: string | undefined): string | null {
  if (!value || !value.startsWith("media://")) return null;
  return value.slice("media://".length) || null;
}
