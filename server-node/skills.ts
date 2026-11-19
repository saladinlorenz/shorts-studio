import fs from "node:fs";
import path from "node:path";
import { HttpError, SKILLS_DIR } from "./security.ts";

export interface SkillMeta {
  id: string;
  title: string;
  source: string;
  entry: string;
  description: string;
}

const KNOWN_SKILLS: SkillMeta[] = [
  {
    id: "remotion-best-practices",
    title: "Remotion Best Practices",
    source: "remotion-best-practices/SKILL.md",
    entry: "remotion-best-practices/SKILL.md",
    description: "Regles officielles Remotion : timing par frames, polices, sous-titres, audio et rendu.",
  },
  {
    id: "remotion-captions",
    title: "Remotion Captions",
    source: "remotion-best-practices/remotion-captions/REFERENCE.md",
    entry: "remotion-best-practices/remotion-captions/REFERENCE.md",
    description: "Sous-titres et alignement temporel dans Remotion.",
  },
  {
    id: "remotion-arabic",
    title: "Arabic & RTL Typography",
    source: "remotion-best-practices/remotion-markup/arabic-text.md",
    entry: "remotion-best-practices/remotion-markup/arabic-text.md",
    description: "Bonnes pratiques pour le texte arabe et RTL dans Remotion.",
  },
];

export function listSkills(): SkillMeta[] {
  return KNOWN_SKILLS.filter((s) => fs.existsSync(path.join(SKILLS_DIR, s.entry)));
}

export function provenance(): Record<string, unknown> {
  const p = path.join(SKILLS_DIR, "PROVENANCE.md");
  return {
    exists: fs.existsSync(p),
    excerpt: fs.existsSync(p) ? fs.readFileSync(p, "utf8").slice(0, 1200) : "",
  };
}

export function findSkill(skillId: string): SkillMeta {
  const found = KNOWN_SKILLS.find((s) => s.id === skillId);
  if (!found) throw new HttpError(404, `Competence introuvable : ${skillId}`);
  return found;
}

export function readDocument(relPath: string): { path: string; content: string; truncated: boolean } {
  const clean = path.normalize(String(relPath || "").replace(/^[/\\]+/, ""));
  const resolved = path.resolve(SKILLS_DIR, clean);
  if (!resolved.startsWith(path.resolve(SKILLS_DIR) + path.sep) && resolved !== path.resolve(SKILLS_DIR)) {
    throw new HttpError(400, "Chemin de competence invalide.");
  }
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
    throw new HttpError(404, "Document introuvable.");
  }
  const raw = fs.readFileSync(resolved, "utf8");
  const limit = 80_000;
  return {
    path: clean,
    content: raw.slice(0, limit),
    truncated: raw.length > limit,
  };
}

export function buildContext(wanted?: string[] | null, maxChars = 60_000): string {
  const list = wanted && wanted.length > 0
    ? listSkills().filter((s) => wanted.includes(s.id))
    : listSkills();
  let acc = "";
  for (const sk of list) {
    const doc = readDocument(sk.entry);
    const block = `\n## ${sk.title} (${sk.entry})\n${doc.content}\n`;
    if (acc.length + block.length > maxChars) {
      acc += block.slice(0, Math.max(0, maxChars - acc.length));
      break;
    }
    acc += block;
  }
  return acc;
}
