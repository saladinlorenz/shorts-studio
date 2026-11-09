import React from "react";
import {
  AlertTriangle,
  AudioLines,
  BrainCircuit,
  CheckCircle2,
  Loader2,
  Plug,
  RefreshCw,
  XCircle,
} from "lucide-react";
import {
  api,
  apiErrorMessage,
  type AgentStatus,
  type AsrPayload,
  type AsrPublic,
  type CheckReport,
  type LlmPayload,
  type LlmPublic,
} from "../api/client";

/**
 * Réglages : clé Clips (Groq), Assistant IA et transcription des moments.
 *
 * Les clés ne repartent jamais vers le navigateur : un champ vide laisse la clé
 * enregistrée en place, « effacer » est une demande explicite. L'URL des
 * fournisseurs cloud est fixe côté serveur, seule celle du serveur local est
 * saisissable.
 */

const CLOUD_WARNING: Record<string, string> = {
  gemini: "Gemini : vos demandes (texte du projet, noms de fichiers) sont envoyées à l'API de Google.",
  groq: "Groq : vos demandes sont envoyées à l'API de Groq. Aucun relais automatique vers le local.",
};

const LOCAL_PRESETS = [
  { url: "http://127.0.0.1:8900/v1", label: "llama.cpp (moteur)" },
  { url: "http://127.0.0.1:8080/api/agent/v1", label: "Local Chat (relais)" },
];

interface Report extends CheckReport {
  checked_at: number;
}

export default function SettingsPage() {
  const [llm, setLlm] = React.useState<LlmPublic | null>(null);
  const [agent, setAgent] = React.useState<AgentStatus | null>(null);
  const [groqConfigured, setGroqConfigured] = React.useState(false);
  const [clipsKey, setClipsKey] = React.useState("");
  const [draft, setDraft] = React.useState<LlmPayload>({});
  const [asr, setAsr] = React.useState<AsrPublic | null>(null);
  const [asrDraft, setAsrDraft] = React.useState<AsrPayload>({});
  const [models, setModels] = React.useState<string[]>([]);
  const [report, setReport] = React.useState<Report | null>(null);
  const [status, setStatus] = React.useState<{ kind: "idle" | "busy" | "ok" | "error"; msg: string }>({
    kind: "idle",
    msg: "",
  });

  const load = React.useCallback(async () => {
    try {
      const s = await api.getSettings();
      setLlm(s.llm);
      setGroqConfigured(s.groq_configured);
      setAsr(s.asr ?? null);
      setAsrDraft((prev) => ({
        provider: s.asr?.provider ?? "auto",
        groq_model: s.asr?.model ?? "",
        language: s.asr?.language ?? "",
        ...prev,
      }));
      setDraft((prev) => ({
        provider: s.llm.provider,
        local_base_url: s.llm.local.base_url,
        local_model: s.llm.local.model,
        gemini_model: s.llm.gemini.model,
        groq_model: s.llm.groq.model,
        ...prev,
      }));
    } catch (e) {
      setStatus({ kind: "error", msg: apiErrorMessage(e) });
    }
    try {
      setAgent(await api.agentStatus());
    } catch {
      /* le manifeste est optionnel : le reste de la page reste utilisable */
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const provider = draft.provider || llm?.provider || "local";
  const isCloud = provider !== "local";
  const state = llm?.[provider as "local" | "gemini" | "groq"];

  const set = (patch: Partial<LlmPayload>) => setDraft((prev) => ({ ...prev, ...patch }));

  const fieldModel =
    provider === "local" ? draft.local_model : provider === "gemini" ? draft.gemini_model : draft.groq_model;
  const fieldKey =
    provider === "local" ? draft.local_api_key : provider === "gemini" ? draft.gemini_api_key : draft.groq_api_key;
  const fieldPin = draft.local_pin;

  const saveClipsKey = async () => {
    setStatus({ kind: "busy", msg: "Enregistrement…" });
    try {
      const r = await api.setGroqKey(clipsKey.trim());
      setGroqConfigured(r.groq_configured);
      setClipsKey("");
      setLlm(r.llm);
      // la clé Clips peut aussi servir la transcription, si on le lui demande :
      // son disponibilité change l'état affiché du fournisseur Groq
      const fresh = await api.getSettings();
      setAsr(fresh.asr ?? null);
      setStatus({ kind: "ok", msg: "Clé Clips enregistrée (serveur uniquement)." });
    } catch (e) {
      setStatus({ kind: "error", msg: apiErrorMessage(e) });
    }
  };

  const save = async () => {
    setStatus({ kind: "busy", msg: "Enregistrement des réglages…" });
    try {
      const r = await api.setSettings({ llm: draft });
      setLlm(r.llm);
      setDraft((prev) => ({
        ...prev,
        local_api_key: undefined,
        gemini_api_key: undefined,
        groq_api_key: undefined,
        local_pin: undefined,
        clear_key: undefined,
        use_groq_clips_key: undefined,
      }));
      setStatus({ kind: "ok", msg: `Réglages enregistrés — fournisseur ${r.llm.provider}.` });
    } catch (e) {
      setStatus({ kind: "error", msg: apiErrorMessage(e) });
    }
  };

  const setAsrPatch = (patch: Partial<AsrPayload>) => setAsrDraft((prev) => ({ ...prev, ...patch }));

  const saveAsr = async () => {
    setStatus({ kind: "busy", msg: "Enregistrement de la transcription…" });
    try {
      const r = await api.setSettings({ asr: asrDraft });
      setAsr(r.asr ?? null);
      setAsrDraft((prev) => ({ ...prev, groq_api_key: undefined, clear_key: undefined }));
      setStatus({ kind: "ok", msg: `Transcription enregistrée — fournisseur ${r.asr?.provider ?? "auto"}.` });
    } catch (e) {
      setStatus({ kind: "error", msg: apiErrorMessage(e) });
    }
  };

  const refreshModels = async () => {
    setStatus({ kind: "busy", msg: "Lecture des modèles du fournisseur…" });
    try {
      const r = await api.agentModels({
        provider,
        base_url: provider === "local" ? draft.local_base_url || undefined : undefined,
        api_key: fieldKey || undefined,
        pin: provider === "local" ? fieldPin || undefined : undefined,
      });
      setModels(r.models);
      setStatus({
        kind: r.models.length ? "ok" : "error",
        msg: r.models.length
          ? `${r.models.length} modèle(s) réellement accessible(s).`
          : "Le fournisseur ne renvoie pas de liste de modèles : saisissez le nom à la main.",
      });
    } catch (e) {
      setModels([]);
      setStatus({ kind: "error", msg: apiErrorMessage(e) });
    }
  };

  const check = async () => {
    setStatus({ kind: "busy", msg: "Test du fournisseur…" });
    try {
      const r = await api.agentCheck({
        provider,
        base_url: provider === "local" ? draft.local_base_url || undefined : undefined,
        model: fieldModel || undefined,
        api_key: fieldKey || undefined,
        pin: provider === "local" ? fieldPin || undefined : undefined,
      });
      setReport({ ...r, checked_at: Date.now() });
      setStatus({ kind: r.ok ? "ok" : "error", msg: r.ok ? "Connexion vérifiée." : String(r.error || "Échec.") });
    } catch (e) {
      setReport(null);
      setStatus({ kind: "error", msg: apiErrorMessage(e) });
    }
  };

  return (
    <div className="flex-1 overflow-auto p-6">
      <h1 className="text-lg font-semibold">Réglages</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Configuration locale du serveur. Les clés d'API restent dans{" "}
        <code className="text-xs">server/settings.json</code> et ne sont jamais renvoyées au
        navigateur ni écrites dans les logs.
      </p>

      <div className="panel mt-4 max-w-2xl p-4">
        <div className="panel-title">Clé API Groq (analyse Clips)</div>
        <p className="mt-2 text-sm text-muted-foreground">
          État actuel :{" "}
          {groqConfigured ? (
            <span className="text-success">configurée</span>
          ) : (
            <span className="text-warning">non configurée</span>
          )}
          . Cette clé sert uniquement à l'analyse de la page Clips ; l'assistant ne la réutilise
          que si vous le demandez explicitement ci-dessous.
        </p>
        <div className="mt-3 flex gap-2">
          <input
            type="password"
            className="input-base flex-1"
            placeholder="gsk_…"
            value={clipsKey}
            onChange={(e) => setClipsKey(e.target.value)}
            autoComplete="off"
          />
          <button
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            onClick={saveClipsKey}
            disabled={status.kind === "busy" || !clipsKey.trim()}
          >
            {status.kind === "busy" ? "…" : "Enregistrer"}
          </button>
        </div>
      </div>

      <div className="panel mt-4 max-w-2xl p-4">
        <div className="panel-title flex items-center gap-2">
          <AudioLines size={14} /> Transcription des moments forts
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          La page Moments transcrit le son d'une source déjà importée, puis y cherche les moments
          forts. Un Whisper local n'est utilisé que s'il est déjà installé sur ce poste :
          l'application n'installe rien.
        </p>

        <div className="mt-3">
          <span className="text-xs font-medium text-muted-foreground">Fournisseur</span>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {[{ id: "auto", label: "Auto (local d'abord)", cloud: false }, ...(asr?.providers ?? []).map((item) => ({ id: item.id, label: item.label, cloud: item.cloud }))].map(
              (item) => {
                const detail = (asr?.providers ?? []).find((p) => p.id === item.id);
                return (
                  <button
                    key={item.id}
                    onClick={() => setAsrPatch({ provider: item.id })}
                    className={
                      "rounded-md border px-2.5 py-1 text-xs " +
                      ((asrDraft.provider ?? asr?.provider ?? "auto") === item.id
                        ? "border-primary bg-primary/10 font-medium"
                        : "border-border hover:bg-muted")
                    }
                    title={detail?.reason || ""}
                  >
                    {item.label}
                    {item.cloud && <span className="ml-1 text-[10px] text-warning">cloud</span>}
                    {detail && !detail.available && (
                      <span className="ml-1 text-[10px] text-muted-foreground">indisponible</span>
                    )}
                  </button>
                );
              },
            )}
          </div>
          {(asr?.providers ?? [])
            .filter((p) => p.reason)
            .map((p) => (
              <p key={p.id} className="mt-1 text-[11px] text-muted-foreground">
                {p.label} : {p.reason}
              </p>
            ))}
        </div>

        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <label className="block text-xs">
            <span className="font-medium text-muted-foreground">
              Clé dédiée à la transcription{" "}
              {asr?.key_configured && <span className="text-success">(enregistrée)</span>}
            </span>
            <input
              type="password"
              className="input-base mt-1 w-full font-mono text-xs"
              placeholder={asr?.key_configured ? "•••••• (inchangée si vide)" : "gsk_…"}
              value={asrDraft.groq_api_key ?? ""}
              onChange={(e) => setAsrPatch({ groq_api_key: e.target.value })}
              autoComplete="off"
            />
            <span className="text-[10px] text-muted-foreground">
              Ne sert qu'à la transcription. La clé de Clips reste à Clips : la page Moments ne la
              reprend que si vous le cochez, et elle ne sort jamais du serveur.
            </span>
          </label>
          <div className="space-y-2">
            <label className="block text-xs">
              <span className="font-medium text-muted-foreground">Modèle Groq</span>
              <select
                className="input-base mt-1 w-full text-xs"
                value={asrDraft.groq_model ?? asr?.model ?? ""}
                onChange={(e) => setAsrPatch({ groq_model: e.target.value })}
              >
                {(asr?.groq_models ?? []).map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-xs">
              <span className="font-medium text-muted-foreground">
                Langue (vide = détection)
              </span>
              <input
                className="input-base mt-1 w-full font-mono text-xs"
                placeholder="fr"
                maxLength={8}
                value={asrDraft.language ?? ""}
                onChange={(e) => setAsrPatch({ language: e.target.value })}
              />
            </label>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            onClick={saveAsr}
            disabled={status.kind === "busy"}
          >
            {status.kind === "busy" ? "…" : "Enregistrer la transcription"}
          </button>
          {asr?.key_configured && (
            <button
              className="rounded-md border border-destructive/50 px-2.5 py-1 text-xs text-destructive hover:bg-destructive/10"
              onClick={() => setAsrPatch({ clear_key: true })}
            >
              Effacer la clé
            </button>
          )}
          {asrDraft.clear_key && <span className="text-[11px] text-destructive">effacement demandé</span>}
          {!asr?.key_configured && asr?.clips_key_available && (
            <span className="text-[11px] text-muted-foreground">
              aucune clé dédiée : seule la clé de Clips est disponible, réutilisation à cocher page Moments.
            </span>
          )}
        </div>
      </div>

      <div className="panel mt-4 max-w-2xl p-4">
        <div className="panel-title flex items-center gap-2">
          <BrainCircuit size={14} /> Assistant IA du studio
        </div>

        <label className="mt-3 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={draft.enabled ?? llm?.enabled ?? false}
            onChange={(e) => set({ enabled: e.target.checked })}
          />
          Activer l'assistant (panneau Assistant du Design et aide de Production)
        </label>

        <div className="mt-3">
          <span className="text-xs font-medium text-muted-foreground">Fournisseur</span>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {(llm?.providers || [
              { id: "local", label: "Serveur local", is_cloud: false, base_url: "" },
              { id: "gemini", label: "API Gemini", is_cloud: true, base_url: "" },
              { id: "groq", label: "API Groq", is_cloud: true, base_url: "" },
            ]).map((item) => (
              <button
                key={item.id}
                onClick={() => set({ provider: item.id })}
                className={
                  "rounded-md border px-2.5 py-1 text-xs " +
                  (provider === item.id
                    ? "border-primary bg-primary/10 font-medium"
                    : "border-border hover:bg-muted")
                }
              >
                {item.label}
                {item.is_cloud && <span className="ml-1 text-[10px] text-warning">cloud</span>}
              </button>
            ))}
          </div>
          <p className="mt-1 text-[11px] text-muted-foreground">
            Changer de fournisseur est explicite : aucun basculement automatique entre local et
            cloud, et les réglages déjà saisis pour chaque fournisseur sont conservés séparément.
          </p>
        </div>

        {isCloud && (
          <p className="mt-2 flex items-start gap-1.5 rounded border border-warning/40 bg-warning/10 p-2 text-[11px] text-warning">
            <AlertTriangle size={12} className="mt-0.5 shrink-0" />
            {CLOUD_WARNING[provider]}
          </p>
        )}

        {provider === "local" && (
          <div className="mt-3 space-y-2">
            <label className="block text-xs">
              <span className="font-medium text-muted-foreground">URL du serveur (base OpenAI)</span>
              <input
                className="input-base mt-1 w-full font-mono text-xs"
                placeholder="http://127.0.0.1:8080/v1"
                value={draft.local_base_url ?? ""}
                onChange={(e) => set({ local_base_url: e.target.value })}
              />
            </label>
            <div className="flex flex-wrap gap-1.5">
              {LOCAL_PRESETS.map((preset) => (
                <button
                  key={preset.url}
                  className="rounded-md border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-muted"
                  onClick={() => set({ local_base_url: preset.url })}
                >
                  {preset.label} · {preset.url}
                </button>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">
              Aucune hypothèse sur le port : le serveur doit exposer une route de type{" "}
              <code className="text-[10px]">/chat/completions</code>. Le PIN, si votre serveur
              l'exige, est envoyé en en-tête <code className="text-[10px]">X-PIN</code>.
            </p>
            <label className="block text-xs">
              <span className="font-medium text-muted-foreground">
                PIN du serveur {state?.pin_configured && <span className="text-success">(déjà enregistré)</span>}
              </span>
              <input
                type="password"
                className="input-base mt-1 w-full font-mono text-xs"
                placeholder={state?.pin_configured ? "•••••• (inchangé si vide)" : ""}
                value={draft.local_pin ?? ""}
                onChange={(e) => set({ local_pin: e.target.value })}
                autoComplete="off"
              />
            </label>
          </div>
        )}

        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <label className="block text-xs">
            <span className="font-medium text-muted-foreground">
              Clé d'API {state?.key_configured && <span className="text-success">(enregistrée)</span>}
            </span>
            <input
              type="password"
              className="input-base mt-1 w-full font-mono text-xs"
              placeholder={state?.key_configured ? "•••••• (inchangée si vide)" : provider === "local" ? "souvent inutile en local" : "clé du fournisseur"}
              value={draftKey(draft, provider)}
              onChange={(e) => setKeyDraft(set, provider, e.target.value)}
              autoComplete="off"
            />
          </label>
          <label className="block text-xs">
            <span className="font-medium text-muted-foreground">Modèle</span>
            <input
              className="input-base mt-1 w-full font-mono text-xs"
              list="agent-models"
              placeholder={state?.model ? state.model : "nom exact du modèle"}
              value={fieldModel ?? ""}
              onChange={(e) =>
                set(
                  provider === "local"
                    ? { local_model: e.target.value }
                    : provider === "gemini"
                      ? { gemini_model: e.target.value }
                      : { groq_model: e.target.value },
                )
              }
            />
            <datalist id="agent-models">
              {models.map((id) => (
                <option key={id} value={id} />
              ))}
            </datalist>
          </label>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button
            className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs hover:bg-muted"
            onClick={refreshModels}
            disabled={status.kind === "busy"}
          >
            <RefreshCw size={11} /> Actualiser les modèles
          </button>
          <button
            className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs hover:bg-muted"
            onClick={check}
            disabled={status.kind === "busy"}
          >
            <Plug size={11} /> Vérifier la connexion
          </button>
          {provider === "groq" && llm?.clips_groq_key_available && (
            <button
              className="rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted"
              onClick={() => set({ use_groq_clips_key: true })}
              title="Copie la clé Clips déjà présente côté serveur vers l'assistant — rien n'est envoyé au navigateur"
            >
              Réutiliser la clé Clips
            </button>
          )}
          {(state?.key_configured || state?.pin_configured) && (
            <button
              className="rounded-md border border-destructive/50 px-2.5 py-1 text-xs text-destructive hover:bg-destructive/10"
              onClick={() => set({ clear_key: true })}
            >
              Effacer la clé{state?.pin_configured ? " et le PIN" : ""}
            </button>
          )}
          {draft.clear_key && <span className="text-[11px] text-destructive">effacement demandé</span>}
          {draft.use_groq_clips_key && <span className="text-[11px] text-success">reprise de la clé Clips demandée</span>}
        </div>

        {models.length > 0 && (
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            Modèles déclarés par ce fournisseur : {models.slice(0, 8).join(", ")}
            {models.length > 8 ? ` … (+${models.length - 8})` : ""}
          </p>
        )}

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <NumberField label="Température" step="0.1" value={draft.temperature ?? llm?.temperature} onChange={(v) => set({ temperature: v })} />
          <NumberField label="Tokens de sortie" step="1" value={draft.max_tokens ?? llm?.max_tokens} onChange={(v) => set({ max_tokens: v })} />
          <NumberField
            label="Budget de contexte (tokens estimés)"
            step="100"
            value={draft.context_budget ?? llm?.context_budget}
            onChange={(v) => set({ context_budget: v })}
            hint="La fenêtre du serveur doit couvrir budget + sortie."
          />
          <NumberField label="Timeout (s)" step="5" value={draft.timeout ?? llm?.timeout} onChange={(v) => set({ timeout: v })} />
          <NumberField label="Réparations auto" step="1" value={draft.max_repairs ?? llm?.max_repairs} onChange={(v) => set({ max_repairs: v })} />
          <NumberField label="Outils de lecture / demande" step="1" value={draft.max_tool_calls ?? llm?.max_tool_calls} onChange={(v) => set({ max_tool_calls: v })} />
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-4 text-xs">
          <label className="flex items-center gap-1.5">
            sortie JSON (response_format)
            <select
              className="input-base h-7"
              value={draft.json_mode ?? llm?.json_mode ?? "auto"}
              onChange={(e) => set({ json_mode: e.target.value })}
            >
              <option value="auto">auto</option>
              <option value="on">toujours demander</option>
              <option value="off">jamais</option>
            </select>
          </label>
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={draft.stream ?? llm?.stream ?? true}
              onChange={(e) => set({ stream: e.target.checked })}
            />
            streaming (permet l'arrêt en cours de génération)
          </label>
        </div>

        <div className="mt-4 flex items-center gap-2">
          <button
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            onClick={save}
            disabled={status.kind === "busy"}
          >
            {status.kind === "busy" ? "…" : "Enregistrer les réglages"}
          </button>
          <button
            className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted"
            onClick={() => {
              void load();
              setDraft({});
              setModels([]);
              setReport(null);
            }}
          >
            Recharger
          </button>
          {llm && (
            <span className="ml-auto text-[11px]">
              {llm.ready ? (
                <span className="flex items-center gap-1 text-success">
                  <CheckCircle2 size={12} /> prêt : {llm.active.base_url || "—"} · {llm.model || "aucun modèle"}
                </span>
              ) : (
                <span className="flex items-center gap-1 text-warning">
                  <XCircle size={12} /> non configuré
                </span>
              )}
            </span>
          )}
        </div>

        {status.msg && (
          <p
            className={
              "mt-2 text-xs " +
              (status.kind === "error" ? "text-destructive" : status.kind === "ok" ? "text-success" : "text-muted-foreground")
            }
          >
            {status.msg}
          </p>
        )}

        {report && <CheckReportCard report={report} />}
      </div>

      {agent && (
        <div className="panel mt-4 max-w-2xl p-4">
          <div className="panel-title">Ce que l'assistant peut toucher</div>
          <p className="mt-2 text-xs text-muted-foreground">
            Manifeste lu côté serveur :{" "}
            <code className="text-[10px]">GET /api/agent/capabilities</code>. Les capacités listées
            viennent du registre de compositions, de la bibliothèque, du schéma v2, du catalogue de
            polices et de <code className="text-[10px]">web/package.json</code> — pas de la
            documentation seule.
          </p>
          <div className="mt-2 grid gap-2 text-[11px] sm:grid-cols-2">
            <Manifest label="modèles" items={agent.capabilities.models} />
            <Manifest label="modèles de bibliothèque" items={agent.capabilities.templates} />
            <Manifest label="polices" items={agent.capabilities.fonts} />
            <Manifest label="animations d'entrée" items={agent.capabilities.animation_in} />
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">
            Médias importés : {agent.capabilities.media_count}.
          </p>
          <p className="mt-2 text-[11px] text-warning">
            Non proposé par l'assistant :{" "}
            {agent.capabilities.not_available.map((item) => item.split(" : ")[0]).join(" · ")}
          </p>
        </div>
      )}
    </div>
  );
}

function draftKey(draft: LlmPayload, provider: string): string {
  if (provider === "local") return draft.local_api_key ?? "";
  if (provider === "gemini") return draft.gemini_api_key ?? "";
  return draft.groq_api_key ?? "";
}

function setKeyDraft(
  set: (patch: Partial<LlmPayload>) => void,
  provider: string,
  value: string,
) {
  if (provider === "local") set({ local_api_key: value });
  else if (provider === "gemini") set({ gemini_api_key: value });
  else set({ groq_api_key: value });
}

function NumberField({
  label,
  value,
  step,
  hint,
  onChange,
}: {
  label: string;
  value: number | undefined;
  step: string;
  hint?: string;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block text-xs">
      <span className="font-medium text-muted-foreground">{label}</span>
      <input
        type="number"
        step={step}
        className="input-base mt-1 w-full"
        value={value ?? ""}
        onChange={(e) => {
          const parsed = Number.parseFloat(e.target.value);
          if (!Number.isNaN(parsed)) onChange(parsed);
        }}
      />
      {hint && <span className="text-[10px] text-muted-foreground">{hint}</span>}
    </label>
  );
}

function Manifest({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="rounded border border-border/60 px-2 py-1">
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <p className="mt-0.5 font-mono text-[11px]">{items?.length ? items.join(", ") : "aucun"}</p>
    </div>
  );
}

function CheckReportCard({ report }: { report: Report }) {
  const caps = report.capabilities || {};
  return (
    <div className="mt-3 rounded-md border border-border/70 bg-muted/20 p-2.5 text-[11px]">
      <div className="flex items-center gap-1.5 font-medium">
        {report.ok ? (
          <CheckCircle2 size={12} className="text-success" />
        ) : (
          <XCircle size={12} className="text-destructive" />
        )}
        Test réel du fournisseur {report.provider || ""} —{" "}
        {report.latency_ms !== undefined ? `${report.latency_ms} ms` : "latence inconnue"}
      </div>
      {report.error && <p className="mt-1 text-destructive">{report.error}</p>}
      {report.hint && <p className="mt-1 text-warning">{report.hint}</p>}
      <ul className="mt-1.5 grid gap-0.5 sm:grid-cols-2">
        {Object.entries(caps).map(([key, value]) => (
          <li key={key} className="flex justify-between gap-2">
            <span className="text-muted-foreground">{key}</span>
            <span className="font-mono">{String(value)}</span>
          </li>
        ))}
      </ul>
      {report.reply && (
        <p className="mt-1 truncate rounded bg-background/60 px-1.5 py-1 font-mono text-[10px]">
          réponse : {report.reply}
        </p>
      )}
      <p className="mt-1.5 flex items-center gap-1 text-[10px] text-muted-foreground">
        <Loader2 size={10} className="hidden" />
        Résultats observés sur les réponses du serveur, jamais déduits du nom du modèle.
      </p>
    </div>
  );
}
