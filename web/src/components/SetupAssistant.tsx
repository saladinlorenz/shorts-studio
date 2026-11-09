import React from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Plug,
  RefreshCw,
  Sparkles,
  XCircle,
} from "lucide-react";
import {
  api,
  apiErrorMessage,
  type AgentStatus,
  type CheckReport,
  type LlmPayload,
  type LlmPublic,
} from "../api/client";

/**
 * Configuration guidée de l'assistant, affichée par le Cockpit tant que
 * l'assistant n'est pas prêt (premier lancement ou réglage incomplet).
 *
 * Trois étapes dans un seul panneau : fournisseur → connexion → modèle,
 * puis « Activer l'assistant ». Tout passe par les endpoints existants
 * (settings, agent/models, agent/check) ; aucune clé n'est renvoyée par le
 * serveur, un champ vide conserve la clé enregistrée. Une fois activé, le
 * Cockpit recharge le statut et ce panneau disparaît.
 */

const CLOUD_WARNING: Record<string, string> = {
  gemini: "Gemini : vos demandes (texte du projet, noms de fichiers) sont envoyées à l'API de Google.",
  groq: "Groq : vos demandes sont envoyées à l'API de Groq. Aucun relais automatique vers le local.",
};

const LOCAL_PRESETS = [
  { url: "http://127.0.0.1:8900/v1", label: "llama.cpp (moteur)" },
  { url: "http://127.0.0.1:8080/api/agent/v1", label: "Local Chat (relais)" },
];

const FALLBACK_PROVIDERS = [
  { id: "local", label: "Serveur local (llama.cpp / compatible OpenAI)", is_cloud: false },
  { id: "gemini", label: "API Gemini (Google)", is_cloud: true },
  { id: "groq", label: "API Groq", is_cloud: true },
];

type ProviderId = "local" | "gemini" | "groq";

function StepTitle({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/15 text-[11px] font-semibold text-primary">
        {n}
      </span>
      <span className="text-xs font-medium">{children}</span>
    </div>
  );
}

export default function SetupAssistant({
  status,
  onReady,
}: {
  status: AgentStatus;
  onReady: () => void;
}) {
  const navigate = useNavigate();
  const [provider, setProvider] = React.useState<ProviderId>(
    (status.provider as ProviderId) || "local",
  );
  const [stored, setStored] = React.useState<LlmPublic | null>(null);
  const [baseUrl, setBaseUrl] = React.useState("");
  const [apiKey, setApiKey] = React.useState("");
  const [pin, setPin] = React.useState("");
  const [model, setModel] = React.useState("");
  const [models, setModels] = React.useState<string[]>([]);
  const [report, setReport] = React.useState<CheckReport | null>(null);
  const [busy, setBusy] = React.useState<"" | "models" | "check" | "save">("");
  const [error, setError] = React.useState("");

  // Reprise de l'existant : ce qui est déjà enregistré est pré-rempli, les
  // clés ne reviennent jamais du serveur (seul leur état booléen sort).
  React.useEffect(() => {
    let stopped = false;
    api
      .getSettings()
      .then((s) => {
        if (stopped) return;
        setStored(s.llm);
        const p = (s.llm.provider as ProviderId) || "local";
        setProvider(p);
        setBaseUrl(s.llm.local.base_url);
        setModel(s.llm[p].model);
      })
      .catch((e) => {
        if (!stopped) setError(apiErrorMessage(e));
      });
    return () => {
      stopped = true;
    };
  }, []);

  const isCloud = provider !== "local";
  const providerState = stored?.[provider];
  const keyStored = providerState?.key_configured ?? false;
  const pinStored = provider === "local" && (providerState?.pin_configured ?? false);
  const connectionOk = isCloud ? keyStored || !!apiKey.trim() : !!baseUrl.trim();
  const canActivate = connectionOk && !!model.trim();

  const chooseProvider = (p: ProviderId) => {
    setProvider(p);
    setApiKey("");
    setPin("");
    setModels([]);
    setReport(null);
    setError("");
    setModel(stored ? stored[p].model : "");
  };

  const listModels = async () => {
    setBusy("models");
    setError("");
    try {
      const r = await api.agentModels({
        provider,
        base_url: provider === "local" ? baseUrl.trim() : undefined,
        api_key: apiKey.trim() || undefined,
        pin: provider === "local" ? pin.trim() || undefined : undefined,
      });
      setModels(r.models);
      if (r.models.length && !model.trim()) setModel(r.models[0]);
      if (!r.models.length) {
        setError("Le fournisseur ne renvoie pas de liste de modèles : saisissez le nom exact à la main.");
      }
    } catch (e) {
      setModels([]);
      setError(apiErrorMessage(e));
    } finally {
      setBusy("");
    }
  };

  const check = async () => {
    setBusy("check");
    setError("");
    setReport(null);
    try {
      const r = await api.agentCheck({
        provider,
        base_url: provider === "local" ? baseUrl.trim() : undefined,
        model: model.trim(),
        api_key: apiKey.trim() || undefined,
        pin: provider === "local" ? pin.trim() || undefined : undefined,
      });
      setReport(r);
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setBusy("");
    }
  };

  const activate = async () => {
    setBusy("save");
    setError("");
    const llm: LlmPayload = { enabled: true, provider };
    if (provider === "local") {
      llm.local_base_url = baseUrl.trim();
      llm.local_model = model.trim();
      if (apiKey.trim()) llm.local_api_key = apiKey.trim();
      if (pin.trim()) llm.local_pin = pin.trim();
    } else if (provider === "gemini") {
      llm.gemini_model = model.trim();
      if (apiKey.trim()) llm.gemini_api_key = apiKey.trim();
    } else {
      llm.groq_model = model.trim();
      if (apiKey.trim()) llm.groq_api_key = apiKey.trim();
    }
    try {
      await api.setSettings({ llm });
      onReady();
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setBusy("");
    }
  };

  return (
    <section className="panel mt-4 border-primary/40 p-4" aria-label="Configuration guidée de l'assistant">
      <div className="flex items-center gap-2">
        <Sparkles size={14} className="text-primary" />
        <h2 className="text-sm font-medium">Activer l'assistant en trois étapes</h2>
        <button
          className="ml-auto text-[11px] text-muted-foreground hover:text-foreground"
          onClick={() => navigate("/settings")}
        >
          Réglages avancés
        </button>
      </div>
      <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
        {status.reason || "L'assistant n'est pas configuré."} Une fois activé, vous décrivez ce que
        vous voulez et il prépare le projet ; rien ne s'applique ni ne se rend sans votre clic.
      </p>

      <div className="mt-3 space-y-3">
        <div>
          <StepTitle n={1}>Choisissez le moteur</StepTitle>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {(stored?.providers ?? FALLBACK_PROVIDERS).map((item) => (
              <button
                key={item.id}
                onClick={() => chooseProvider(item.id as ProviderId)}
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
          {isCloud && (
            <p className="mt-1.5 flex items-start gap-1.5 rounded border border-warning/40 bg-warning/10 p-2 text-[11px] text-warning">
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              {CLOUD_WARNING[provider]}
            </p>
          )}
        </div>

        <div>
          <StepTitle n={2}>Connectez-le</StepTitle>
          {provider === "local" ? (
            <div className="mt-1.5 space-y-2">
              <label className="block text-xs">
                <span className="font-medium text-muted-foreground">URL du serveur (base OpenAI)</span>
                <input
                  className="input-base mt-1 w-full font-mono text-xs"
                  placeholder="http://127.0.0.1:8080/v1"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                />
              </label>
              <div className="flex flex-wrap gap-1.5">
                {LOCAL_PRESETS.map((preset) => (
                  <button
                    key={preset.url}
                    className="rounded-md border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-muted"
                    onClick={() => setBaseUrl(preset.url)}
                  >
                    {preset.label} · {preset.url}
                  </button>
                ))}
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <label className="block text-xs">
                  <span className="font-medium text-muted-foreground">
                    Clé d'API {keyStored && <span className="text-success">(enregistrée)</span>}
                  </span>
                  <input
                    type="password"
                    className="input-base mt-1 w-full font-mono text-xs"
                    placeholder={keyStored ? "•••••• (inchangée si vide)" : "souvent inutile en local"}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    autoComplete="off"
                  />
                </label>
                <label className="block text-xs">
                  <span className="font-medium text-muted-foreground">
                    PIN du serveur {pinStored && <span className="text-success">(enregistré)</span>}
                  </span>
                  <input
                    type="password"
                    className="input-base mt-1 w-full font-mono text-xs"
                    placeholder={pinStored ? "•••••• (inchangé si vide)" : "si votre serveur l'exige"}
                    value={pin}
                    onChange={(e) => setPin(e.target.value)}
                    autoComplete="off"
                  />
                </label>
              </div>
            </div>
          ) : (
            <label className="mt-1.5 block text-xs">
              <span className="font-medium text-muted-foreground">
                Clé d'API {keyStored && <span className="text-success">(enregistrée)</span>}
              </span>
              <input
                type="password"
                className="input-base mt-1 w-full font-mono text-xs"
                placeholder={keyStored ? "•••••• (inchangée si vide)" : "clé du fournisseur"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                autoComplete="off"
              />
              <span className="text-[10px] text-muted-foreground">
                La clé reste dans server/settings.json, elle n'est jamais renvoyée au navigateur.
              </span>
            </label>
          )}
        </div>

        <div>
          <StepTitle n={3}>Choisissez le modèle, puis activez</StepTitle>
          <div className="mt-1.5 flex flex-wrap items-end gap-2">
            <label className="block min-w-[220px] flex-1 text-xs">
              <span className="font-medium text-muted-foreground">Modèle</span>
              <input
                className="input-base mt-1 w-full font-mono text-xs"
                list="setup-models"
                placeholder="nom exact du modèle"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              />
              <datalist id="setup-models">
                {models.map((id) => (
                  <option key={id} value={id} />
                ))}
              </datalist>
            </label>
            <button
              className="flex h-8 items-center gap-1 rounded-md border border-border px-2.5 text-xs hover:bg-muted disabled:opacity-50"
              onClick={listModels}
              disabled={!connectionOk || busy !== ""}
            >
              {busy === "models" ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
              Lister les modèles
            </button>
            <button
              className="flex h-8 items-center gap-1 rounded-md border border-border px-2.5 text-xs hover:bg-muted disabled:opacity-50"
              onClick={check}
              disabled={!canActivate || busy !== ""}
            >
              {busy === "check" ? <Loader2 size={11} className="animate-spin" /> : <Plug size={11} />}
              Tester la connexion
            </button>
          </div>
          {models.length > 0 && (
            <p className="mt-1 text-[11px] text-muted-foreground">
              {models.length} modèle(s) réellement accessible(s) : {models.slice(0, 6).join(", ")}
              {models.length > 6 ? " …" : ""}
            </p>
          )}
          {report && (
            <p
              className={
                "mt-1.5 flex items-start gap-1.5 rounded border p-2 text-[11px] " +
                (report.ok
                  ? "border-success/40 bg-success/10 text-success"
                  : "border-destructive/40 bg-destructive/10 text-destructive")
              }
            >
              {report.ok ? <CheckCircle2 size={12} className="mt-0.5 shrink-0" /> : <XCircle size={12} className="mt-0.5 shrink-0" />}
              <span>
                {report.ok
                  ? `Connexion vérifiée${report.latency_ms !== undefined ? ` — ${report.latency_ms} ms` : ""}. Vous pouvez activer.`
                  : report.error || "Échec de la connexion."}
                {report.hint && <span className="block text-warning">{report.hint}</span>}
              </span>
            </p>
          )}
          <div className="mt-2 flex items-center gap-2">
            <button
              className="flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              onClick={activate}
              disabled={!canActivate || busy !== ""}
            >
              {busy === "save" ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
              Activer l'assistant
            </button>
            {!canActivate && (
              <span className="text-[11px] text-muted-foreground">
                {!connectionOk
                  ? isCloud
                    ? "Saisissez la clé d'API pour continuer."
                    : "Saisissez l'URL du serveur pour continuer."
                  : "Renseignez le modèle pour continuer."}
              </span>
            )}
          </div>
        </div>
      </div>

      {error && <p className="mt-2 text-[11px] leading-snug text-destructive">{error}</p>}
    </section>
  );
}