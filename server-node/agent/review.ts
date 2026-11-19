import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import * as budgets from "../budgets.ts";
import { Job } from "../jobs.ts";
import * as renderMod from "../render.ts";
import { resolveProject } from "../resolve.ts";
import * as schema from "../schema.ts";
import * as settingsMod from "../settings.ts";
import { EXPORTS_DIR } from "../security.ts";

export interface ReviewReport {
  ok: boolean;
  summary: string;
  findings: Array<{ severity: "info" | "warning" | "error"; code: string; message: string }>;
  dom_probes: Array<Record<string, unknown>>;
  vision?: {
    enabled: boolean;
    ran: boolean;
    advisory_notes: string[];
  };
}

/**
 * P4 : Contrôle qualité réel du projet (sonde DOM Remotion + cohérence typographique
 * + passe de vision optionnelle strictement désactivée par défaut).
 */
export async function reviewProject(
  job: Job,
  project: schema.AnyRecord,
  opts: { allowVision?: boolean } = {},
): Promise<ReviewReport> {
  budgets.assertNotStopped();
  const cfg = settingsMod.llmConfig();
  const resolved = resolveProject(project);
  const r = resolved.resolved;
  const totalFrames = Number(r.total_frames || 30);
  const findings: ReviewReport["findings"] = [];

  // Sample 3 key frames: early, middle, late
  const sampleFrames = [...new Set([Math.min(15, totalFrames - 1), Math.floor(totalFrames / 2), Math.max(0, totalFrames - 10)])];
  const tmpDir = path.join(EXPORTS_DIR, `_qc_${crypto.randomBytes(4).toString("hex")}`);
  let domProbes: Array<Record<string, unknown>> = [];
  let framePngs: string[] = [];

  try {
    framePngs = await renderMod.renderProjectFrames(job, project, sampleFrames, tmpDir, true);
    for (const f of sampleFrames) {
      const jf = path.join(tmpDir, `frame-${f}.json`);
      if (fs.existsSync(jf)) {
        const probe = JSON.parse(fs.readFileSync(jf, "utf8")) as Record<string, any>;
        domProbes.push(probe);
        if (Array.isArray(probe.overflows) && probe.overflows.length > 0) {
          for (const ov of probe.overflows) {
            findings.push({
              severity: "warning",
              code: "text_overflow",
              message: `Frame ${f} : debordement possible sur '${ov.layerId || "texte"}'.`,
            });
          }
        }
        if (Array.isArray(probe.overlaps) && probe.overlaps.length > 0) {
          for (const ov of probe.overlaps) {
            findings.push({
              severity: "warning",
              code: "layer_overlap",
              message: `Frame ${f} : chevauchement detecte (${ov.a} / ${ov.b}).`,
            });
          }
        }
      }
    }
  } catch (err) {
    findings.push({
      severity: "info",
      code: "dom_probe_skipped",
      message: `Sonde DOM non executee : ${err instanceof Error ? err.message.slice(0, 140) : String(err)}`,
    });
  } finally {
    // Clean up temporary frames after optional vision check below
  }

  // P4: Optional bounded vision pass — strictly OFF by default unless cfg.vision_review === true
  const visionEnabled = Boolean(cfg.vision_review) && Boolean(opts.allowVision ?? true);
  const visionInfo: { enabled: boolean; ran: boolean; advisory_notes: string[] } = {
    enabled: visionEnabled,
    ran: false,
    advisory_notes: [],
  };

  if (visionEnabled && framePngs.length > 0 && cfg.api_key && cfg.provider === "gemini") {
    try {
      const { GoogleGenAI } = await import("@google/genai");
      budgets.consumeBudget("llm_calls", { purpose: "vision_qc" });
      const ai = new GoogleGenAI({ apiKey: cfg.api_key });
      const firstPng = framePngs.find((p) => fs.existsSync(p));
      if (firstPng) {
        const b64 = fs.readFileSync(firstPng).toString("base64");
        const res = await ai.models.generateContent({
          model: cfg.model || "gemini-2.5-flash",
          contents: [
            { inlineData: { mimeType: "image/png", data: b64 } },
            { text: "Analyse brièvement la lisibilité, le contraste et le cadrage de cette image vidéo en 2 phrases max." },
          ],
          config: { maxOutputTokens: 180, temperature: 0.2 },
        });
        visionInfo.ran = true;
        if (res.text) {
          visionInfo.advisory_notes.push(res.text.trim());
        }
      }
    } catch (err) {
      visionInfo.advisory_notes.push(
        `Passe vision ignoree : ${err instanceof Error ? err.message.slice(0, 120) : String(err)}`,
      );
    }
  }

  try {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  } catch {
    // ignore cleanup failure
  }

  const hasErrors = findings.some((f) => f.severity === "error");
  const warningCount = findings.filter((f) => f.severity === "warning").length;
  return {
    ok: !hasErrors,
    summary:
      warningCount === 0
        ? `Controle QC valide (${r.width}x${r.height}, ${r.duration_seconds}s).`
        : `${warningCount} avertissement(s) de mise en page detecte(s).`,
    findings,
    dom_probes: domProbes,
    vision: visionInfo,
  };
}
