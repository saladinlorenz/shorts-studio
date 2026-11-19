import fs from "node:fs";
import path from "node:path";
import * as asrMod from "../asr.ts";
import * as brandsMod from "../brands.ts";
import * as effectsMod from "../effects.ts";
import * as foldersMod from "../folders.ts";
import * as fontsMod from "../fonts.ts";
import * as libraryMod from "../library.ts";
import * as renderMod from "../render.ts";
import * as retrievalMod from "../retrieval.ts";
import * as schema from "../schema.ts";
import * as settingsMod from "../settings.ts";
import * as stockMod from "../stock.ts";
import * as ttsMod from "../tts.ts";
import { EXPORTS_DIR, MEDIA_DIR, PROJECTS_DIR } from "../security.ts";

export interface ToolResult {
  tool: string;
  ok: boolean;
  data: unknown;
}

export const READ_TOOLS = [
  "list_fonts",
  "list_effects",
  "list_models",
  "list_projects",
  "list_media",
  "list_brands",
  "list_folders",
  "search_skills",
  "search_stock",
  "tts_status",
  "asr_status",
  "check_render", // P8
] as const;

export const TOOL_DESCRIPTION =
  "Outils en lecture seule : list_fonts, list_effects, list_models, list_projects, list_media, list_brands, list_folders, search_skills, search_stock, tts_status, asr_status, check_render.";

export async function runReadTool(
  name: string,
  args: Record<string, unknown> = {},
  activeProject?: schema.AnyRecord | null,
): Promise<ToolResult> {
  if (name === "list_fonts") {
    return { tool: name, ok: true, data: { families: fontsMod.families() } };
  }
  if (name === "list_effects") {
    return { tool: name, ok: true, data: effectsMod.manifest() };
  }
  if (name === "list_models") {
    return { tool: name, ok: true, data: { models: libraryMod.listLibrary() } };
  }
  if (name === "list_projects") {
    const names = fs.existsSync(PROJECTS_DIR)
      ? fs.readdirSync(PROJECTS_DIR).filter((f) => f.endsWith(".json")).map((f) => path.basename(f, ".json"))
      : [];
    return { tool: name, ok: true, data: { projects: names } };
  }
  if (name === "list_media") {
    const files = fs.existsSync(MEDIA_DIR)
      ? fs.readdirSync(MEDIA_DIR).filter((f) => f !== "provenance" && !f.endsWith(".part"))
      : [];
    return { tool: name, ok: true, data: { count: files.length, media: files.slice(0, 40) } };
  }
  if (name === "list_brands") {
    return { tool: name, ok: true, data: { brands: brandsMod.listBrands() } };
  }
  if (name === "list_folders") {
    return { tool: name, ok: true, data: { folders: foldersMod.listRoots() } };
  }
  if (name === "search_skills") {
    const q = String(args.query || "").trim();
    return { tool: name, ok: true, data: { passages: retrievalMod.search(q, 4, 3000) } };
  }
  if (name === "search_stock") {
    const items = await stockMod.searchStock(String(args.query || ""), {
      source: args.source ? String(args.source) : undefined,
      kind: args.kind ? String(args.kind) : "video",
      limit: Number(args.limit || 5),
    });
    return { tool: name, ok: true, data: { items } };
  }
  if (name === "tts_status") {
    const cfg = ttsMod.status(path.join(EXPORTS_DIR, "..", "tts_models"));
    return { tool: name, ok: true, data: cfg };
  }
  if (name === "asr_status") {
    const s = settingsMod.loadSettings();
    return {
      tool: name,
      ok: true,
      data: {
        provider: s.asr_provider,
        providers: asrMod.providers({ groqKeyPresent: Boolean(s.asr_groq_api_key || s.groq_api_key) }),
      },
    };
  }
  if (name === "check_render") {
    // P8: verify rendered MP4 &/or active project DOM layout
    const exportName = args.export_name ? String(args.export_name) : undefined;
    const report = await renderMod.checkRender({
      exportName,
      project: activeProject || undefined,
    });
    return { tool: name, ok: Boolean(report.ok), data: report };
  }
  return { tool: name, ok: false, data: { error: `Outil inconnu : ${name}` } };
}
