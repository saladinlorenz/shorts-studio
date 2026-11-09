import React from "react";
import { X } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Slider } from "../../components/ui/slider";
import { Switch } from "../../components/ui/switch";
import {
  api,
  apiErrorMessage,
  mediaId,
  mediaUrl,
  type EffectParamSpec,
  type EffectParamValue,
  type EffectSpec,
  type EffectsManifest,
  type EffectValue,
  type ModelInfo,
  type Project,
  type TtsGenerateResult,
  type TtsStatus,
} from "../../api/client";
import { cssFamily, FONT_FAMILIES } from "../../remotion/fonts";
import { cancelJob, useJobPolling } from "../../lib/jobs";
import { ErrorNote, JobStatus } from "../../components/job-status";
import type { TextFit } from "./measure";
import { durations, layerById, sceneById, type Selection } from "./edit";

/** Panneaux de l'espace Design. Ils ne calculent rien de metier : ils lisent
 *  le projet et le bloc ``resolved`` fournis par le serveur, et renvoient des
 *  modifications au state de la page (historique d'annulation a la main). */

const ANIM_IN = ["fade", "slide_up", "slide_left", "scale", "mask_reveal", "none"];
const ANIM_OUT = ["none", "fade"];
const ANIM_UNIT = ["block", "line", "word"];
const EASINGS = ["linear", "ease_out_cubic", "ease_out_quint", "spring"];
const BG_ANIM = ["static", "zoom_slow", "zoom_out"];
const FIT = ["cover", "contain"];
const ALIGN = ["left", "center", "right"];

const labelFor: Record<string, string> = {
  fade: "fondu",
  slide_up: "glissement haut",
  slide_left: "glissement gauche",
  scale: "zoom avant",
  mask_reveal: "révélation par masque",
  none: "aucun",
  block: "bloc",
  line: "ligne",
  word: "mot",
  linear: "linéaire",
  ease_out_cubic: "sortie cubique",
  ease_out_quint: "sortie quintique",
  spring: "ressort",
  static: "fixe",
  zoom_slow: "poussée lente",
  zoom_out: "recul lent",
  cover: "remplir (sans étirement)",
  contain: "contenir (sans étirement)",
  left: "gauche",
  center: "centre",
  right: "droite",
};

function title(value: string): string {
  return labelFor[value] ?? value;
}

export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="mt-0.5 block text-[11px] text-muted-foreground">{hint}</span>}
    </label>
  );
}

export function TextInput({
  value,
  onChange,
  onBlurCommit,
  placeholder,
  multiline,
}: {
  value: string;
  onChange: (v: string) => void;
  onBlurCommit?: () => void;
  placeholder?: string;
  multiline?: boolean;
}) {
  const [local, setLocal] = React.useState(value);
  React.useEffect(() => setLocal(value), [value]);
  const common = {
    className: multiline ? "input-base min-h-[92px] resize-y font-medium" : "input-base",
    value: local,
    placeholder,
    onChange: (e: any) => {
      setLocal(e.target.value);
      onChange(e.target.value);
    },
    onBlur: onBlurCommit,
  };
  return multiline ? <textarea {...common} /> : <input {...common} />;
}

function NumberInput({
  value,
  onChange,
  onCommit,
  step = 1,
  min,
  max,
  suffix,
}: {
  value: number;
  onChange: (v: number) => void;
  onCommit?: () => void;
  step?: number;
  min?: number;
  max?: number;
  suffix?: string;
}) {
  const [local, setLocal] = React.useState(String(value));
  React.useEffect(() => setLocal(String(value)), [value]);
  return (
    <div className="flex items-center gap-1">
      <input
        type="number"
        className="input-base font-mono text-xs"
        value={local}
        step={step}
        min={min}
        max={max}
        onChange={(e) => {
          setLocal(e.target.value);
          const parsed = Number(e.target.value);
          if (!Number.isNaN(parsed)) onChange(parsed);
        }}
        onBlur={() => {
          const parsed = Number(local);
          if (Number.isNaN(parsed)) setLocal(String(value));
          else onCommit?.();
        }}
      />
      {suffix && <span className="text-[11px] text-muted-foreground">{suffix}</span>}
    </div>
  );
}

function SelectOne({
  value,
  options,
  onChange,
}: {
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <select className="input-base" value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((option) => (
        <option key={option} value={option}>
          {title(option)}
        </option>
      ))}
    </select>
  );
}

function ColorInput({ value, onChange, onCommit }: { value: string; onChange: (v: string) => void; onCommit?: () => void }) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="color"
        value={/^#[0-9a-fA-F]{6}$/.test(value) ? value : "#ffffff"}
        onChange={(e) => onChange(e.target.value.toUpperCase())}
        onBlur={onCommit}
        className="h-7 w-9 cursor-pointer rounded border border-input bg-transparent"
        aria-label="couleur"
      />
      <input className="input-base font-mono text-xs" value={value} onChange={(e) => onChange(e.target.value)} onBlur={onCommit} />
    </div>
  );
}

function Section({ title: heading, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <section className="panel p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="panel-title">{heading}</h3>
        {right}
      </div>
      <div className="grid gap-2.5">{children}</div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Panneau de gauche : modèle, scènes, calques, médias                 */
/* ------------------------------------------------------------------ */

export function ScenesPanel(props: {
  model: ModelInfo | null;
  project: Project;
  selection: Selection;
  onSelect: (next: Selection) => void;
  onScene: (sceneId: string, patch: Record<string, unknown>, commit?: boolean) => void;
  onLayer: (sceneId: string, layerId: string, patch: Record<string, unknown>, commit?: boolean) => void;
  onAddScene: () => void;
  onDuplicateScene: (sceneId: string) => void;
  onRemoveScene: (sceneId: string) => void;
  onMoveScene: (sceneId: string, delta: number) => void;
  onAddLayer: (sceneId: string, type: "text" | "image") => void;
  onRemoveLayer: (sceneId: string, layerId: string) => void;
  onMoveLayer: (sceneId: string, layerId: string, delta: number) => void;
  onToggleLayer: (sceneId: string, layerId: string, key: "hidden" | "locked") => void;
  onMedia: (target: { sceneId: string; layerId?: string; slot: "background" | "layer" | "signature" }, media: string) => void;
  fontsReady: boolean;
}) {
  const { project, selection } = props;
  const scenes = project?.content?.scenes ?? [];
  const info = durations(project);

  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-y-auto">
      <Section title="Modèle">
        <div className="text-sm font-medium">{props.model?.label ?? "—"}</div>
        <p className="text-[11px] leading-relaxed text-muted-foreground">{props.model?.description}</p>
        {props.model && (
          <div className="flex flex-wrap gap-1">
            <Badge variant="outline">v{props.model.version}</Badge>
            <Badge variant="outline">{props.model.recommended_duration[0]}–{props.model.recommended_duration[1]} s</Badge>
            <Badge variant={props.fontsReady ? "success" : "warning"}>
              {props.fontsReady ? "polices chargées" : "polices en cours"}
            </Badge>
          </div>
        )}
      </Section>

      <Section
        title={`Scènes · ${scenes.length}`}
        right={
          <Button size="sm" variant="secondary" onClick={props.onAddScene}>
            + Scène
          </Button>
        }
      >
        {scenes.map((scene: any, index: number) => {
          const active = scene.id === selection.sceneId;
          const startFrame = scenes.slice(0, index).reduce((sum: number, s: any) => sum + Math.round((Number(s.duration) || 0) * (project.export?.fps ?? 30)), 0);
          return (
            <div key={scene.id} className={`rounded-md border p-2 ${active ? "border-primary bg-accent/40" : "border-border bg-card"}`}>
              <div className="flex items-center gap-1.5">
                <button
                  className="flex-1 truncate text-left text-sm font-medium hover:text-foreground"
                  onClick={() => props.onSelect({ sceneId: scene.id, layerId: scene.layers?.[0]?.id ?? null })}
                >
                  {index + 1}. {scene.label}
                </button>
                <button
                  className="text-[11px] text-muted-foreground hover:text-foreground"
                  title={scene.hidden ? "Masquée" : "Visible"}
                  onClick={() => props.onScene(scene.id, { hidden: !scene.hidden }, true)}
                >
                  {scene.hidden ? "masquée" : "visible"}
                </button>
              </div>
              <div className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <span className="font-mono">
                  f{startFrame} → f{startFrame + Math.round((Number(scene.duration) || 0) * (project.export?.fps ?? 30))}
                </span>
                <span>· {(Number(scene.duration) || 0).toFixed(1)} s</span>
              </div>
              <div className="mt-1.5 flex items-center gap-1">
                <Button size="sm" variant="ghost" onClick={() => props.onMoveScene(scene.id, -1)} disabled={index === 0}>
                  ↑
                </Button>
                <Button size="sm" variant="ghost" onClick={() => props.onMoveScene(scene.id, 1)} disabled={index === scenes.length - 1}>
                  ↓
                </Button>
                <Button size="sm" variant="ghost" onClick={() => props.onDuplicateScene(scene.id)}>
                  Dupliquer
                </Button>
                <Button size="sm" variant="ghost" onClick={() => props.onRemoveScene(scene.id)} disabled={scenes.length <= 1}>
                  Supprimer
                </Button>
              </div>
              <div className="mt-2">
                <Slider
                  label="durée"
                  display={`${(Number(scene.duration) || 0).toFixed(1)} s`}
                  min={0.5}
                  max={20}
                  step={0.1}
                  value={[Number(scene.duration) || 1]}
                  onValueChange={([v]) => props.onScene(scene.id, { duration: v }, false)}
                  onValueCommit={() => undefined}
                />
              </div>

              <div className="mt-2 grid gap-1">
                {(scene.layers ?? []).map((layer: any, layerIndex: number) => {
                  const isSelected = active && layer.id === selection.layerId;
                  return (
                    <div
                      key={layer.id}
                      className={`flex items-center gap-1 rounded px-1.5 py-1 text-xs ${isSelected ? "bg-accent text-foreground" : "hover:bg-accent/50"}`}
                    >
                      <button
                        className="min-w-0 flex-1 truncate text-left"
                        onClick={() => props.onSelect({ sceneId: scene.id, layerId: layer.id })}
                      >
                        <span className="mr-1 font-mono text-[10px] text-muted-foreground">
                          {layer.type === "text" ? "T" : "I"}
                        </span>
                        {layer.type === "text" ? String(layer.text ?? "").slice(0, 34) || layer.id : `image · ${layer.id}`}
                      </button>
                      <button
                        title="masquer"
                        className={layer.hidden ? "text-warning" : "text-muted-foreground"}
                        onClick={() => props.onToggleLayer(scene.id, layer.id, "hidden")}
                      >
                        ○
                      </button>
                      <button
                        title="verrouiller"
                        className={layer.locked ? "text-warning" : "text-muted-foreground"}
                        onClick={() => props.onToggleLayer(scene.id, layer.id, "locked")}
                      >
                        ⌁
                      </button>
                      <button onClick={() => props.onMoveLayer(scene.id, layer.id, -1)} disabled={layerIndex === 0} className="text-muted-foreground">
                        ↑
                      </button>
                      <button onClick={() => props.onMoveLayer(scene.id, layer.id, 1)} disabled={layerIndex === scene.layers.length - 1} className="text-muted-foreground">
                        ↓
                      </button>
                    </div>
                  );
                })}
              </div>
              {active && (
                <div className="mt-1.5 flex gap-1">
                  <Button size="sm" variant="secondary" onClick={() => props.onAddLayer(scene.id, "text")}>
                    + Texte
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => props.onAddLayer(scene.id, "image")}>
                    + Image
                  </Button>
                </div>
              )}
            </div>
          );
        })}
        <div className="text-[11px] text-muted-foreground">
          Total : {info.total.toFixed(1)} s · {Math.round(info.total * (project.export?.fps ?? 30))} frames
        </div>
      </Section>

      <Section title="Médias de la scène">
        {selection.sceneId && (
          <>
            <MediaSlot
              label="Fond (image ou vidéo)"
              value={sceneById(project, selection.sceneId)?.background?.media ?? ""}
              onPicked={(media) => props.onMedia({ sceneId: selection.sceneId!, slot: "background" }, media)}
            />
            {(sceneById(project, selection.sceneId)?.layers ?? [])
              .filter((l: any) => l.type === "image")
              .map((layer: any) => (
                <MediaSlot
                  key={layer.id}
                  label={`Calque image · ${layer.id}`}
                  value={layer.media ?? ""}
                  onPicked={(media) => props.onMedia({ sceneId: selection.sceneId!, layerId: layer.id, slot: "layer" }, media)}
                />
              ))}
            <MediaSlot
              label="Logo de signature"
              value={project?.content?.signature?.media ?? ""}
              onPicked={(media) => props.onMedia({ sceneId: selection.sceneId!, slot: "signature" }, media)}
            />
          </>
        )}
      </Section>
    </div>
  );
}

function MediaSlot({ label, value, onPicked }: { label: string; value: string; onPicked: (media: string) => void }) {
  const [busy, setBusy] = React.useState<string | null>(null);
  const [licence, setLicence] = React.useState<string>("");
  const input = React.useRef<HTMLInputElement>(null);
  const url = mediaUrl(value);
  const id = mediaId(value);

  React.useEffect(() => {
    let cancelled = false;
    if (!id) return;
    api
      .studioProvenance(id)
      .then((prov) => !cancelled && setLicence(String(prov.licence ?? "inconnue")))
      .catch(() => !cancelled && setLicence("inconnue"));
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function pick(file: File) {
    setBusy("import…");
    try {
      const result = await api.uploadMedia(file, { source: file.name, licence: licence === "inconnue" ? "" : licence });
      onPicked(`media://${result.id}`);
      setLicence("inconnue");
      setBusy(null);
    } catch (error) {
      setBusy(`échec : ${(error as Error).message.slice(0, 80)}`);
    }
  }

  return (
    <div className="rounded-md border border-border p-2">
      <div className="flex items-center justify-between">
        <span className="field-label">{label}</span>
        <Badge variant={licence && licence !== "inconnue" ? "success" : "warning"}>licence : {licence || "inconnue"}</Badge>
      </div>
      <div className="mt-1.5 flex items-center gap-2">
        {url ? <img src={url} alt="" className="h-12 w-12 rounded border border-border object-cover" /> : <div className="h-12 w-12 rounded border border-dashed border-border" />}
        <div className="flex flex-col gap-1">
          <Button size="sm" variant="secondary" onClick={() => input.current?.click()}>
            Importer
          </Button>
          {value && (
            <Button size="sm" variant="ghost" onClick={() => onPicked("")}>
              Retirer
            </Button>
          )}
        </div>
        <input
          ref={input}
          type="file"
          accept="image/*,video/mp4,video/webm,video/quicktime"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void pick(file);
            e.target.value = "";
          }}
        />
      </div>
      {busy && busy !== "import…" && <p className="mt-1 text-[11px] text-destructive">{busy}</p>}
      {busy === "import…" && <p className="mt-1 text-[11px] text-muted-foreground">import en cours…</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Panneau de droite : propriétés                                      */
/* ------------------------------------------------------------------ */

/* ------------------------------------------------------------------ */
/* Effets : le catalogue du serveur dicte la liste, les bornes, les    */
/* reglages. Rien n'est propose ici qui ne soit reellement rendu.       */
/* ------------------------------------------------------------------ */

function effectIdOf(raw: EffectValue): string {
  return typeof raw === "string" ? raw : String(raw.id ?? "");
}

function storedParams(raw: EffectValue): Record<string, EffectParamValue> {
  return typeof raw === "string" ? {} : { ...(raw.params ?? {}) };
}

/** La forme courte (« glitch_slices ») est gardee tant qu'aucun reglage ne
 *  depasse les valeurs du catalogue : le projet reste lisible. */
function toStoredValue(spec: EffectSpec, params: Record<string, EffectParamValue>): EffectValue {
  const changed: Record<string, EffectParamValue> = {};
  for (const item of spec.params) {
    const value = params[item.key];
    if (value !== undefined && value !== item.default) changed[item.key] = value;
  }
  return Object.keys(changed).length ? { id: spec.id, params: changed } : spec.id;
}

function paramDisplay(spec: EffectParamSpec, value: EffectParamValue): string {
  const unit = spec.unit ? ` ${spec.unit}` : "";
  if (typeof value === "boolean") return value ? "oui" : "non";
  if (typeof value === "number") return `${spec.type === "integer" ? Math.round(value) : value}${unit}`;
  return String(value);
}

function EffectParamRow({
  spec,
  value,
  onChange,
}: {
  spec: EffectParamSpec;
  value: EffectParamValue;
  onChange: (value: EffectParamValue, commit: boolean) => void;
}) {
  if (spec.type === "bool") {
    return (
      <div className="flex items-center justify-between">
        <span className="field-label">{spec.label}</span>
        <Switch checked={Boolean(value)} onCheckedChange={(v) => onChange(v, true)} />
      </div>
    );
  }
  if (spec.type === "color") {
    return (
      <Field label={spec.label}>
        <ColorInput value={String(value)} onChange={(v) => onChange(v, false)} onCommit={() => onChange(String(value), true)} />
      </Field>
    );
  }
  if (spec.type === "select") {
    return (
      <Field label={spec.label}>
        <SelectOne value={String(value)} options={spec.options ?? []} onChange={(v) => onChange(v, true)} />
      </Field>
    );
  }
  if (spec.type === "text") {
    return (
      <Field label={spec.label} hint={spec.placeholder || undefined}>
        <TextInput
          multiline
          value={String(value)}
          onChange={(v) => onChange(v, false)}
          onBlurCommit={() => onChange(String(value), true)}
        />
      </Field>
    );
  }
  const min = Number(spec.min ?? 0);
  const max = Number(spec.max ?? 1);
  const step = Number(spec.step ?? (spec.type === "integer" ? 1 : 0.01));
  const numeric = Number(value);
  return (
    <Slider
      label={spec.label}
      display={paramDisplay(spec, Number.isFinite(numeric) ? numeric : min)}
      min={min}
      max={max}
      step={step}
      value={[Number.isFinite(numeric) ? numeric : min]}
      onValueChange={([v]) => onChange(spec.type === "integer" ? Math.round(v) : v, false)}
      onValueCommit={() => onChange(spec.type === "integer" ? Math.round(Number(value)) : Number(value), true)}
    />
  );
}

function EffectsSection(props: {
  catalog: EffectsManifest | null;
  host: "layer" | "scene";
  target: "text" | "image" | "scene";
  value: EffectValue[];
  audioReady: boolean;
  onChange: (next: EffectValue[], commit?: boolean) => void;
  onApplyToAll?: (next: EffectValue[]) => void;
}) {
  const { catalog, host, target, value, audioReady } = props;
  const [expanded, setExpanded] = React.useState<string | null>(null);

  if (!catalog) {
    return (
      <Section title="Effets">
        <p className="text-[11px] text-muted-foreground">Cataloge en attente du serveur.</p>
      </Section>
    );
  }

  const byId: Record<string, EffectSpec> = {};
  for (const spec of catalog.effects) byId[spec.id] = spec;

  const usable = catalog.effects.filter((spec) =>
    host === "layer"
      ? spec.scopes.includes("layer") && spec.targets.includes(target)
      : spec.scopes.includes("scene") || spec.scopes.includes("overlay"),
  );
  const chosen = value.map(effectIdOf);
  const remaining = usable.filter((spec) => !chosen.includes(spec.id));
  const full = value.length >= catalog.max_per_target;

  const write = (index: number, next: EffectValue, commit = true) => {
    const list = value.slice();
    list[index] = next;
    props.onChange(list, commit);
  };

  return (
    <Section
      title="Effets"
      right={
        <span className="font-mono text-[11px] text-muted-foreground">
          {value.length}/{catalog.max_per_target}
        </span>
      }
    >
      <select
        className="input-base"
        value=""
        disabled={full || remaining.length === 0}
        onChange={(e) => {
          const spec = byId[e.target.value];
          if (!spec) return;
          props.onChange([...value, spec.id], true);
        }}
      >
        <option value="">
          {full
            ? `maximum ${catalog.max_per_target} effets par ${host === "layer" ? "calque" : "scene"}`
            : "+ ajouter un effet…"}
        </option>
        {catalog.categories.map((category) => {
          const options = remaining.filter((spec) => spec.category === category.id);
          if (!options.length) return null;
          return (
            <optgroup key={category.id} label={category.label}>
              {options.map((spec) => (
                <option key={spec.id} value={spec.id}>
                  {spec.label}
                </option>
              ))}
            </optgroup>
          );
        })}
      </select>

      {value.map((raw, index) => {
        const id = effectIdOf(raw);
        const spec = byId[id];
        if (!spec) {
          return (
            <p key={`${id}-${index}`} className="text-[11px] text-destructive">
              ✗ Effet « {id || "—" } » inconnu du catalogue : retirez-le ou choisissez-en un autre.
            </p>
          );
        }
        const stored = storedParams(raw);
        const shown = (item: EffectParamSpec) => (stored[item.key] === undefined ? item.default : stored[item.key]);
        const key = `${host}-${id}`;
        const isOpen = expanded === key;
        return (
          <div key={key} className="rounded-md border border-border p-2">
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="flex-1 text-left text-xs font-medium"
                onClick={() => setExpanded(isOpen ? null : key)}
              >
                {spec.label} <span className="font-mono text-[10px] text-muted-foreground">{spec.id}</span>
              </button>
              {spec.needs_audio && !audioReady && <Badge variant="warning">audio requis</Badge>}
              {spec.needs_audio && audioReady && <Badge variant="secondary">audio réel</Badge>}
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground"
                aria-label={`retirer ${spec.label}`}
                onClick={() => props.onChange(value.filter((_, i) => i !== index), true)}
              >
                <X size={14} />
              </button>
            </div>
            <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{spec.description}</p>
            {spec.note && <p className="mt-1 text-[11px] leading-snug text-warning">{spec.note}</p>}
            {isOpen && (
              <div className="mt-2 grid gap-2.5 border-t border-border pt-2">
                {spec.params.map((item) => (
                  <EffectParamRow
                    key={item.key}
                    spec={item}
                    value={shown(item)}
                    onChange={(v, commit) => write(index, toStoredValue(spec, { ...stored, [item.key]: v }), commit)}
                  />
                ))}
              </div>
            )}
          </div>
        );
      })}

      {host === "scene" && value.length > 0 && props.onApplyToAll && (
        <Button variant="outline" size="sm" onClick={() => props.onApplyToAll?.(value.slice())}>
          Appliquer a toutes les scenes
        </Button>
      )}
    </Section>
  );
}

function VoiceOverSection({
  project,
  onAudio,
}: {
  project: Project;
  onAudio: (patch: Record<string, unknown>, commit?: boolean) => void;
}) {
  const [status, setStatus] = React.useState<TtsStatus | null>(null);
  const [statusError, setStatusError] = React.useState("");
  const [text, setText] = React.useState("");
  const [voiceId, setVoiceId] = React.useState("piper-fr-siwis");
  const [speed, setSpeed] = React.useState(1.0);
  const [downloadJobId, setDownloadJobId] = React.useState<string | null>(null);
  const [generateJobId, setGenerateJobId] = React.useState<string | null>(null);
  const [actionError, setActionError] = React.useState("");

  const refreshStatus = React.useCallback(() => {
    api
      .ttsStatus()
      .then((s) => {
        setStatus(s);
        setStatusError("");
      })
      .catch((e) => setStatusError(apiErrorMessage(e)));
  }, []);
  React.useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  const downloadPoll = useJobPolling(downloadJobId);
  const generatePoll = useJobPolling(generateJobId);

  const dlDoneRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    const job = downloadPoll.job;
    if (job && job.status === "done" && dlDoneRef.current !== job.id) {
      dlDoneRef.current = job.id;
      refreshStatus();
    }
  }, [downloadPoll.job, refreshStatus]);

  // La voix generee n'est assignee au projet qu'a la fin du job, par un geste
  // unique dans l'historique (annulable). Aucun chemin disque : une ref media://.
  const genAppliedRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    const job = generatePoll.job;
    if (job && job.status === "done" && job.result && genAppliedRef.current !== job.id) {
      genAppliedRef.current = job.id;
      const result = job.result as TtsGenerateResult;
      onAudio({ voice: result.ref, enabled: true }, true);
    }
  }, [generatePoll.job, onAudio]);

  const voices = status?.voices ?? [];
  const voice = voices.find((v) => v.id === voiceId) ?? null;
  const engine = voice ? status?.engines[voice.engine] : null;
  const engineAvailable = Boolean(engine?.available);
  const busy =
    downloadPoll.job?.status === "running" || generatePoll.job?.status === "running";

  const startDownload = () => {
    setActionError("");
    api
      .ttsDownload(voiceId)
      .then((r) => setDownloadJobId(r.job_id))
      .catch((e) => setActionError(apiErrorMessage(e)));
  };
  const startGenerate = () => {
    setActionError("");
    api
      .ttsGenerate({ text, voice_id: voiceId, speed })
      .then((r) => setGenerateJobId(r.job_id))
      .catch((e) => setActionError(apiErrorMessage(e)));
  };

  const voiceRef = String(project.audio?.voice ?? "");
  const previewUrl = mediaUrl(voiceRef);

  return (
    <Section
      title="Voix off"
      right={voiceRef ? <span className="text-[11px] text-success">assignée</span> : undefined}
    >
      <p className="text-[11px] text-muted-foreground">
        Synthèse vocale locale (Piper / Kokoro). Aucun envoi cloud : le texte reste sur ce poste.
        La voix générée est assignée au projet, annulable via Annuler.
      </p>
      {statusError && <ErrorNote>{statusError}</ErrorNote>}
      <Field label="texte à lire" hint={`${text.length}/5000 caractères`}>
        <TextInput multiline value={text} onChange={setText} placeholder="Bonjour, voici une voix off…" />
      </Field>
      <Field label="voix">
        <select className="input-base" value={voiceId} onChange={(e) => setVoiceId(e.target.value)}>
          {voices.map((v) => (
            <option key={v.id} value={v.id}>
              {v.label}
              {v.downloaded ? "" : ` · à télécharger (~${v.approx_mb} Mo)`}
            </option>
          ))}
        </select>
      </Field>
      <Slider
        label="vitesse"
        display={`${speed.toFixed(2)}×`}
        min={0.5}
        max={2}
        step={0.05}
        value={[speed]}
        onValueChange={([v]) => setSpeed(v)}
      />

      {voice && !engineAvailable && (
        <ErrorNote>{engine?.reason || "Moteur indisponible : installez requirements.txt."}</ErrorNote>
      )}

      {voice && engineAvailable && !voice.downloaded && (
        <Button size="sm" variant="secondary" onClick={startDownload} disabled={busy}>
          Télécharger la voix (~{voice.approx_mb} Mo)
        </Button>
      )}

      <Button size="sm" onClick={startGenerate} disabled={busy || !text.trim() || !voice?.ready}>
        Générer la voix off
      </Button>

      <JobStatus
        job={downloadPoll.job}
        pollError={downloadPoll.pollError}
        runningLabel="Téléchargement de la voix…"
        onCancel={
          downloadJobId && downloadPoll.job?.status === "running"
            ? () => void cancelJob(downloadJobId)
            : undefined
        }
      />
      <JobStatus
        job={generatePoll.job}
        pollError={generatePoll.pollError}
        runningLabel="Synthèse vocale…"
        onCancel={
          generateJobId && generatePoll.job?.status === "running"
            ? () => void cancelJob(generateJobId)
            : undefined
        }
        doneMessage={generatePoll.job?.status === "done" ? "Voix off assignée au projet." : undefined}
      />

      {actionError && <ErrorNote>{actionError}</ErrorNote>}

      {previewUrl && (
        <Field label="aperçu de la voix off">
          <audio controls src={previewUrl} className="w-full" />
        </Field>
      )}
      {voiceRef && (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onAudio({ voice: "", enabled: Boolean(project.audio?.music) }, true)}
        >
          Retirer la voix off
        </Button>
      )}
    </Section>
  );
}

export function InspectorPanel(props: {
  project: Project;
  selection: Selection;
  fits: TextFit[];
  errors: string[];
  warnings: string[];
  resolved: any;
  effects: EffectsManifest | null;
  audioReady: boolean;
  onScene: (sceneId: string, patch: Record<string, unknown>, commit?: boolean) => void;
  onLayer: (sceneId: string, layerId: string, patch: Record<string, unknown>, commit?: boolean) => void;
  onAllScenes?: (patch: Record<string, unknown>) => void;
  onStyle: (part: "style" | "position" | "animation", patch: Record<string, unknown>, commit?: boolean) => void;
  onTheme: (patch: Record<string, unknown>, commit?: boolean) => void;
  onSignature: (patch: Record<string, unknown>, commit?: boolean) => void;
  onExport: (patch: Record<string, unknown>, commit?: boolean) => void;
  onVariation: (patch: Record<string, unknown>, commit?: boolean) => void;
  onAudio: (patch: Record<string, unknown>, commit?: boolean) => void;
}) {
  const { project, selection } = props;
  const scene = sceneById(project, selection.sceneId);
  const layer = layerById(project, selection.sceneId, selection.layerId);
  const resolvedLayer = props.resolved?.scenes?.find((s: any) => s.id === scene?.id)?.layers?.find((l: any) => l.id === selection.layerId);
  const theme = project.theme ?? {};
  const signature = project.content?.signature ?? {};
  const exported = project.export ?? {};
  const fit = props.fits.find((f) => f.sceneId === scene?.id && f.layerId === selection.layerId);

  if (!scene) {
    return <div className="p-3 text-sm text-muted-foreground">Sélectionnez une scène.</div>;
  }
  const sceneId = scene.id as string;

  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-y-auto pr-1">
      <VoiceOverSection project={project} onAudio={props.onAudio} />

      {layer && (
        <Section title="Contenu du calque">
          <Field label="rôle">
            <TextInput value={String(layer.role ?? "")} onChange={(v) => props.onLayer(sceneId, layer.id, { role: v }, false)} />
          </Field>
          {layer.type === "text" ? (
            <>
              <Field label="texte" hint={`${String(layer.text ?? "").length} caractères`}>
                <TextInput multiline value={String(layer.text ?? "")} onChange={(v) => props.onLayer(sceneId, layer.id, { text: v }, false)} />
              </Field>
              <Field label="mots mis en valeur" hint="séparés par des virgules — peints en couleur d'accent">
                <TextInput
                  value={(layer.emphasis ?? []).join(", ")}
                  onChange={(v) => props.onLayer(sceneId, layer.id, { emphasis: v.split(",").map((w) => w.trim()).filter(Boolean) }, false)}
                />
              </Field>
            </>
          ) : (
            <p className="text-[11px] text-muted-foreground">Calque image : importez le fichier dans le panneau de gauche.</p>
          )}
        </Section>
      )}

      {layer && layer.type === "text" && (
        <Section title="Typographie">
          <Field label="police (licence affichée)">
            <select
              className="input-base"
              value={String(resolvedLayer?.font_family ?? theme.font_family ?? "")}
              onChange={(e) => props.onStyle("style", { font_family: e.target.value }, true)}
            >
              <option value="">— hériter du thème —</option>
              {FONT_FAMILIES.map((family) => (
                <option key={family.id} value={family.id}>
                  {family.label} · {family.license}
                </option>
              ))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="poids">
              <NumberInput value={Number(layer.style?.font_weight ?? theme.font_weight ?? 700)} onChange={(v) => props.onStyle("style", { font_weight: v }, false)} onCommit={() => undefined} />
            </Field>
            <Field label="taille (px)" hint={`≠ ${resolvedLayer ? Math.round(resolvedLayer.font_size_px) : "—"} px rendus`}>
              <NumberInput value={Number(layer.style?.font_size ?? theme.font_size ?? 84)} onChange={(v) => props.onStyle("style", { font_size: v }, false)} onCommit={() => undefined} min={8} max={400} />
            </Field>
            <Field label="interligne">
              <NumberInput value={Number(layer.style?.line_height ?? theme.line_height ?? 1.2)} step={0.01} onChange={(v) => props.onStyle("style", { line_height: v }, false)} onCommit={() => undefined} />
            </Field>
            <Field label=" chasse (em)">
              <NumberInput value={Number(layer.style?.letter_spacing ?? theme.letter_spacing ?? 0)} step={0.005} onChange={(v) => props.onStyle("style", { letter_spacing: v }, false)} onCommit={() => undefined} />
            </Field>
          </div>
          <Field label="alignement">
            <SelectOne value={String(layer.position?.align ?? "center")} options={ALIGN} onChange={(v) => props.onStyle("position", { align: v }, true)} />
          </Field>
          <Field label="couleur du texte">
            <ColorInput value={String(layer.style?.color ?? theme.text_color ?? "#FFFFFF")} onChange={(v) => props.onStyle("style", { color: v }, false)} onCommit={() => undefined} />
          </Field>
          <Field label="couleur d'accent (mots en valeur)">
            <ColorInput value={String(layer.style?.accent_color ?? theme.accent_color ?? "#E2B458")} onChange={(v) => props.onStyle("style", { accent_color: v }, false)} onCommit={() => undefined} />
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="contour (px)">
              <NumberInput value={Number(layer.style?.stroke_width ?? 0)} onChange={(v) => props.onStyle("style", { stroke_width: v }, false)} onCommit={() => undefined} min={0} max={40} />
            </Field>
            <Field label="couleur du contour">
              <ColorInput value={String(layer.style?.stroke_color ?? "#000000")} onChange={(v) => props.onStyle("style", { stroke_color: v }, false)} onCommit={() => undefined} />
            </Field>
          </div>
          <div className="flex items-center justify-between">
            <span className="field-label">ombre portée</span>
            <Switch checked={Boolean(layer.style?.shadow ?? theme.shadow ?? true)} onCheckedChange={(v) => props.onStyle("style", { shadow: v }, true)} />
          </div>
          <Field label="sens d'écriture" hint="rtl : architecture prévue, non encore validée visuellement">
            <SelectOne value={String(layer.position?.direction ?? "ltr")} options={["ltr", "rtl"]} onChange={(v) => props.onStyle("position", { direction: v }, true)} />
          </Field>
          {fit && (
            <div className={`rounded-md border p-2 text-[11px] ${fit.overflow ? "border-warning bg-warning/10" : "border-border"}`}>
              {fit.overflow ? (
                <>
                  <strong className="text-warning">Débordement détecté</strong>
                  <p className="mt-0.5">
                    bloc mesuré {fit.textHeightPx} px pour {fit.boxHeightPx} px utiles ({fit.lines} lignes).
                    Réduisez la taille, le texte ou la largeur, ou allongez la scène.
                  </p>
                </>
              ) : (
                <span className="text-muted-foreground">
                  Mise en page dans le cadre : {fit.lines} lignes, {fit.textHeightPx} px.
                </span>
              )}
            </div>
          )}
        </Section>
      )}

      {layer && (
        <Section title="Position">
          <div className="grid grid-cols-3 gap-2">
            <Field label="x">
              <NumberInput value={Number(layer.position?.x ?? 0.5)} step={0.01} min={0} max={1} onChange={(v) => props.onStyle("position", { x: v }, false)} onCommit={() => undefined} />
            </Field>
            <Field label="y">
              <NumberInput value={Number(layer.position?.y ?? 0.5)} step={0.01} min={0} max={1} onChange={(v) => props.onStyle("position", { y: v }, false)} onCommit={() => undefined} />
            </Field>
            <Field label="largeur">
              <NumberInput value={Number(layer.position?.width ?? 0.8)} step={0.01} min={0.05} max={1} onChange={(v) => props.onStyle("position", { width: v }, false)} onCommit={() => undefined} />
            </Field>
          </div>
          {layer.type === "image" && (
            <Field label="opacité">
              <NumberInput value={Number(layer.opacity ?? 1)} step={0.05} min={0} max={1} onChange={(v) => props.onStyle("style", { opacity: v }, false)} onCommit={() => undefined} />
            </Field>
          )}
        </Section>
      )}

      {layer && (
        <Section title="Animation & temporisation">
          <div className="grid grid-cols-2 gap-2">
            <Field label="entrée">
              <SelectOne value={String(layer.animation?.in ?? "fade")} options={ANIM_IN} onChange={(v) => props.onStyle("animation", { in: v }, true)} />
            </Field>
            <Field label="sortie">
              <SelectOne value={String(layer.animation?.out ?? "fade")} options={ANIM_OUT} onChange={(v) => props.onStyle("animation", { out: v }, true)} />
            </Field>
            <Field label="unité animée">
              <SelectOne value={String(layer.animation?.unit ?? "block")} options={ANIM_UNIT} onChange={(v) => props.onStyle("animation", { unit: v }, true)} />
            </Field>
            <Field label="courbe">
              <SelectOne value={String(layer.animation?.easing ?? "ease_out_cubic")} options={EASINGS} onChange={(v) => props.onStyle("animation", { easing: v }, true)} />
            </Field>
          </div>
          <Slider
            label="début (frame de la scène)"
            display={`f${Math.round(Number(layer.animation?.start_frames ?? 0))}`}
            min={0}
            max={Math.max(1, Math.round((Number(scene.duration) || 1) * (project.export?.fps ?? 30)))}
            step={1}
            value={[Number(layer.animation?.start_frames ?? 0)]}
            onValueChange={([v]) => props.onStyle("animation", { start_frames: v }, false)}
          />
          <div className="grid grid-cols-3 gap-2">
            <Field label="entrée (frames)">
              <NumberInput value={Number(layer.animation?.in_frames ?? 18)} min={0} onChange={(v) => props.onStyle("animation", { in_frames: v }, false)} onCommit={() => undefined} />
            </Field>
            <Field label="maintien">
              <span className="font-mono text-xs text-muted-foreground">
                f{resolvedLayer ? resolvedLayer.hold_frames : "—"}
              </span>
            </Field>
            <Field label="sortie (frames)">
              <NumberInput value={Number(layer.animation?.out_frames ?? 12)} min={0} onChange={(v) => props.onStyle("animation", { out_frames: v }, false)} onCommit={() => undefined} />
            </Field>
          </div>
          <Slider
            label="décalage entre unités"
            display={`${Math.round(Number(layer.animation?.stagger_frames ?? 0))} f`}
            min={0}
            max={20}
            step={1}
            value={[Number(layer.animation?.stagger_frames ?? 0)]}
            onValueChange={([v]) => props.onStyle("animation", { stagger_frames: v }, false)}
          />
          <Slider
            label="distance du mouvement"
            display={`${(Number(layer.animation?.distance ?? 0.06) * 100).toFixed(1)} %`}
            min={0}
            max={0.4}
            step={0.005}
            value={[Number(layer.animation?.distance ?? 0.06)]}
            onValueChange={([v]) => props.onStyle("animation", { distance: v }, false)}
          />
          {layer.animation?.easing === "spring" && (
            <div className="grid grid-cols-3 gap-2">
              <Field label="amorti.">
                <NumberInput value={Number(layer.animation?.spring?.damping ?? 16)} onChange={(v) => props.onStyle("animation", { spring: { ...layer.animation.spring, damping: v } }, false)} onCommit={() => undefined} />
              </Field>
              <Field label="raideur">
                <NumberInput value={Number(layer.animation?.spring?.stiffness ?? 140)} onChange={(v) => props.onStyle("animation", { spring: { ...layer.animation.spring, stiffness: v } }, false)} onCommit={() => undefined} />
              </Field>
              <Field label="masse">
                <NumberInput value={Number(layer.animation?.spring?.mass ?? 1)} step={0.1} onChange={(v) => props.onStyle("animation", { spring: { ...layer.animation.spring, mass: v } }, false)} onCommit={() => undefined} />
              </Field>
            </div>
          )}
          <p className="text-[11px] text-muted-foreground">
            Frames de début : f{resolvedLayer ? resolvedLayer.start_frame : "—"} · fin f{resolvedLayer ? resolvedLayer.end_frame : "—"}
          </p>
        </Section>
      )}

      {layer && (
        <EffectsSection
          catalog={props.effects}
          host="layer"
          target={layer.type === "image" ? "image" : "text"}
          value={(layer.effects as EffectValue[]) ?? []}
          audioReady={props.audioReady}
          onChange={(next, commit = true) => props.onLayer(sceneId, layer.id, { effects: next }, commit)}
        />
      )}

      <Section title="Fond de scène">
        <div className="grid grid-cols-2 gap-2">
          <Field label="cadrage">
            <SelectOne value={String(scene.background?.fit ?? "cover")} options={FIT} onChange={(v) => props.onScene(scene.id, { background: { ...scene.background, fit: v } }, true)} />
          </Field>
          <Field label="mouvement">
            <SelectOne value={String(scene.background?.animation ?? "static")} options={BG_ANIM} onChange={(v) => props.onScene(scene.id, { background: { ...scene.background, animation: v } }, true)} />
          </Field>
        </div>
      </Section>

      <EffectsSection
        catalog={props.effects}
        host="scene"
        target="scene"
        value={(scene.effects as EffectValue[]) ?? []}
        audioReady={props.audioReady}
        onChange={(next, commit = true) => props.onScene(scene.id, { effects: next }, commit)}
        onApplyToAll={
          props.onAllScenes
            ? (next) => props.onAllScenes?.({ effects: next })
            : undefined
        }
      />

      <Section title="Thème (valeurs par défaut)">
        <div className="grid grid-cols-2 gap-2">
          <Field label="fond">
            <ColorInput value={String(theme.background_color ?? "#0B0B10")} onChange={(v) => props.onTheme({ background_color: v }, false)} onCommit={() => undefined} />
          </Field>
          <Field label="surface">
            <ColorInput value={String(theme.surface_color ?? "#15151F")} onChange={(v) => props.onTheme({ surface_color: v }, false)} onCommit={() => undefined} />
          </Field>
          <Field label="accent">
            <ColorInput value={String(theme.accent_color ?? "#E2B458")} onChange={(v) => props.onTheme({ accent_color: v }, false)} onCommit={() => undefined} />
          </Field>
          <Field label="police par défaut">
            <select className="input-base" value={String(theme.font_family ?? "")} onChange={(e) => props.onTheme({ font_family: e.target.value }, true)}>
              {FONT_FAMILIES.map((family) => (
                <option key={family.id} value={family.id}>
                  {family.css_family}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <Field label="palette enregistrée">
          <TextInput value={String(theme.palette_id ?? "")} onChange={(v) => props.onTheme({ palette_id: v }, false)} />
        </Field>
      </Section>

      <Section title="Signature de marque">
        <div className="flex items-center justify-between">
          <span className="field-label">afficher la signature</span>
          <Switch checked={Boolean(signature.enabled)} onCheckedChange={(v) => props.onSignature({ enabled: v }, true)} />
        </div>
        <Field label="nom de marque">
          <TextInput value={String(signature.handle ?? "")} onChange={(v) => props.onSignature({ handle: v }, false)} />
        </Field>
        <div className="grid grid-cols-3 gap-2">
          <Field label="taille">
            <NumberInput value={Number(signature.font_size ?? 34)} onChange={(v) => props.onSignature({ font_size: v }, false)} onCommit={() => undefined} />
          </Field>
          <Field label="logo (larg.)">
            <NumberInput value={Number(signature.logo_width ?? 0.14)} step={0.01} min={0} max={0.6} onChange={(v) => props.onSignature({ logo_width: v }, false)} onCommit={() => undefined} />
          </Field>
          <Field label="y">
            <NumberInput value={Number(signature.position?.y ?? 0.945)} step={0.005} min={0} max={1} onChange={(v) => props.onSignature({ position: { ...(signature.position ?? {}), y: v } }, false)} onCommit={() => undefined} />
          </Field>
        </div>
        <Slider
          label="apparition (frames)"
          display={`f${Math.round(Number(signature.start_frames ?? 0))}`}
          min={0}
          max={Math.max(1, Number(props.resolved?.total_frames ?? 1))}
          step={1}
          value={[Number(signature.start_frames ?? 0)]}
          onValueChange={([v]) => props.onSignature({ start_frames: v }, false)}
        />
      </Section>

      <Section title="Export">
        <div className="grid grid-cols-3 gap-2">
          <Field label="largeur">
            <NumberInput value={Number(exported.width ?? 1080)} onChange={(v) => props.onExport({ width: Math.round(v / 2) * 2 }, false)} onCommit={() => undefined} />
          </Field>
          <Field label="hauteur">
            <NumberInput value={Number(exported.height ?? 1920)} onChange={(v) => props.onExport({ height: Math.round(v / 2) * 2 }, false)} onCommit={() => undefined} />
          </Field>
          <Field label="fps">
            <NumberInput value={Number(exported.fps ?? 30)} onChange={(v) => props.onExport({ fps: Math.round(v) }, false)} onCommit={() => undefined} min={1} max={120} />
          </Field>
        </div>
        <Field label="graine de variation" hint="enregistrée dans le projet résolu — aucune valeur aléatoire au rendu">
          <NumberInput
            value={Number(project.variation?.seed ?? 1)}
            onChange={(v) => props.onVariation({ seed: Math.round(v) }, false)}
          />
        </Field>
      </Section>

      <Section title="Validation (serveur)">
        {props.errors.length === 0 && props.warnings.length === 0 && (
          <p className="text-[11px] text-success">Aucune erreur ni avertissement.</p>
        )}
        {props.errors.map((error, index) => (
          <p key={`e${index}`} className="text-[11px] text-destructive">
            ✗ {error}
          </p>
        ))}
        {props.warnings.map((warning, index) => (
          <p key={`w${index}`} className="text-[11px] text-warning">
            ⚠ {warning}
          </p>
        ))}
      </Section>

      <Section title="Projet résolu">
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Modèle {props.resolved?.model?.id} v{props.resolved?.model?.version} · {props.resolved?.total_frames ?? "—"} frames ·
          graine {props.resolved?.seed ?? "—"} · {props.resolved?.assets?.length ?? 0} média(s) ·{" "}
          {props.resolved?.fonts?.length ?? 0} police(s)
        </p>
        <p className="text-[11px] text-muted-foreground" style={{ fontFamily: cssFamily(String(theme.font_family ?? "inter")) }}>
          Aperçu typographique : é à ç ù “bonjour” 0123456789
        </p>
      </Section>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Barre du bas : transport + chronologie simple                       */
/* ------------------------------------------------------------------ */

export function TimelineBar(props: {
  project: Project;
  resolved: any;
  frame: number;
  playing: boolean;
  errors: string[];
  onSeek: (frame: number) => void;
  onTogglePlay: () => void;
  onToggleLoop: () => void;
  loop: boolean;
  sceneMarks: Array<{ id: string; label: string; startFrame: number; durationFrames: number }>;
}) {
  const fps = props.resolved?.fps ?? props.project?.export?.fps ?? 30;
  const total = props.resolved?.total_frames ?? 1;
  const seconds = props.frame / fps;
  const blocked = props.errors.length > 0;

  return (
    <div className="flex items-center gap-3 border-t border-border bg-card/60 px-3 py-2">
      <Button size="sm" variant="secondary" onClick={props.onTogglePlay}>
        {props.playing ? "Pause" : "Lecture"}
      </Button>
      <Button size="sm" variant="ghost" onClick={props.onToggleLoop}>
        boucle {props.loop ? "on" : "off"}
      </Button>
      <div className="flex min-w-0 flex-1 items-center gap-2">
        {props.sceneMarks.map((mark, index) => (
          <button
            key={mark.id}
            onClick={() => props.onSeek(mark.startFrame)}
            title={`${mark.label} · f${mark.startFrame} → f${mark.startFrame + mark.durationFrames}`}
            className={`h-8 overflow-hidden rounded border text-left text-[10px] ${
              props.frame >= mark.startFrame && props.frame < mark.startFrame + mark.durationFrames
                ? "border-primary bg-accent text-foreground"
                : "border-border bg-background text-muted-foreground"
            }`}
            style={{ flexGrow: Math.max(1, mark.durationFrames), flexBasis: 0, order: index }}
          >
            <span className="px-1.5 leading-8">{mark.label}</span>
          </button>
        ))}
      </div>
      <input
        type="range"
        min={0}
        max={Math.max(1, total - 1)}
        value={Math.min(props.frame, total - 1)}
        onChange={(e) => props.onSeek(Number(e.target.value))}
        className="w-48 accent-primary"
        aria-label="position"
      />
      <div className="w-40 shrink-0 text-right font-mono text-[11px] text-muted-foreground">
        f{props.frame}/{total} · {seconds.toFixed(2)} s
      </div>
      <Badge variant={blocked ? "destructive" : "success"}>{blocked ? "Export bloqué" : "Prêt à exporter"}</Badge>
    </div>
  );
}
