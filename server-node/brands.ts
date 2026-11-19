import fs from "node:fs";
import path from "node:path";
import * as branding from "./branding.ts";
import * as schema from "./schema.ts";
import { BRANDS_DIR, HttpError, safeName } from "./security.ts";

function slug(name: string): string {
  const clean = name
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  return clean || "marque";
}

export function listBrands() {
  if (!fs.existsSync(BRANDS_DIR)) return [];
  return fs
    .readdirSync(BRANDS_DIR)
    .filter((f) => f.endsWith(".json"))
    .sort()
    .map((f) => {
      const id = path.basename(f, ".json");
      const full = path.join(BRANDS_DIR, f);
      try {
        const pack = JSON.parse(fs.readFileSync(full, "utf8")) as Record<string, any>;
        return {
          id,
          label: pack.label || id,
          notes: pack.notes || "",
          theme: pack.theme || {},
          signature: pack.signature || {},
          models: pack.models || [],
        };
      } catch {
        return { id, label: id, notes: "", theme: {}, signature: {}, models: [] };
      }
    });
}

export function getPack(brandId: string) {
  const clean = safeName(brandId);
  const full = path.join(BRANDS_DIR, `${clean}.json`);
  if (!fs.existsSync(full)) throw new HttpError(404, `Pack introuvable : ${brandId}`);
  return JSON.parse(fs.readFileSync(full, "utf8"));
}

export function saveBrand(rawPack: unknown, brandId?: string | null) {
  const [pack, errors, warnings] = branding.normalizeBrandPack(rawPack);
  if (errors.length > 0) {
    throw new HttpError(400, { message: "Pack de marque invalide.", errors, warnings });
  }
  const id = safeName(brandId ? slug(brandId) : slug(String(pack.label || "marque")));
  fs.mkdirSync(BRANDS_DIR, { recursive: true });
  fs.writeFileSync(path.join(BRANDS_DIR, `${id}.json`), JSON.stringify(pack, null, 2), "utf8");
  return { id, pack, warnings };
}

export function deleteBrand(brandId: string) {
  const clean = safeName(brandId);
  const full = path.join(BRANDS_DIR, `${clean}.json`);
  if (!fs.existsSync(full)) throw new HttpError(404, `Pack introuvable : ${brandId}`);
  fs.unlinkSync(full);
  return { deleted: clean };
}

export function applyToProject(brandId: string, project: schema.AnyRecord) {
  const pack = getPack(brandId);
  const [patched, warnings] = branding.applyBrand(project, pack);
  return { project: patched, warnings, brand_id: brandId };
}

export function captureFromProject(project: schema.AnyRecord, label = "", notes = "") {
  const raw = branding.fromProject(project, label || project.name || "Ma marque", notes);
  return saveBrand(raw);
}
