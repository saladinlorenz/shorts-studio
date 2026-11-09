"""Entree de rendu unique, partagee par l'export unitaire et la production.

Un projet -> un MP4. L'export d'une video isolee comme le rendu d'un lot de
100 lignes passent par ``render_project_to_mp4()`` : il n'existe qu'une seule
chaine d'execution, donc un correctif de rendu profite aux deux usages.

Etapes :
1. resolution du projet (frames absolues, modele, graine) ;
2. references media -> URLs locales du cache de rendu ;
3. sous-processus ``remotion render`` dans ``web/`` (jamais dans le thread de
   requete) avec l'identifiant de composition vient du projet, pas du code ;
4. progression reellement lue dans la sortie du rendu ;
5. annulation = terminaison du sous-processus.
"""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
from pathlib import Path

from shortvideos import resolve as resolve_mod
from shortvideos import schema

from . import mediacache
from .jobs import Job, JobCancelled
from .security import ROOT

WEB_DIR = ROOT / "web"
ENTRY = "src/remotion/index.tsx"

_PROGRESS_RE = re.compile(r"(?:Rendered|Rendering|Encoded)\s+(\d+)\s*/\s*(\d+)", re.IGNORECASE)


def node_command() -> Path:
    """Node.js portable du projet, sinon celui du PATH."""
    portable = ROOT.parent / "_tools" / "node" / "node.exe"
    if portable.exists():
        return portable
    raise RuntimeError(
        "Node.js introuvable dans _tools/node. Relancez start_web.bat "
        "ou installez Node.js 18+."
    )


def _env() -> dict:
    env = dict(os.environ)
    node_dir = ROOT.parent / "_tools" / "node"
    if (node_dir / "node.exe").exists():
        env["PATH"] = str(node_dir) + os.pathsep + env.get("PATH", "")
    return env


def prepare_for_render(project: dict) -> dict:
    """Projet edite -> objet de props du rendu (resollu + URLs medias)."""
    if project.get("version") == schema.SCHEMA_VERSION_V2:
        prepared = resolve_mod.resolve(project)
    else:
        prepared = copy.deepcopy(project)
    return mediacache.to_render_urls(prepared)


def composition_id_of(project: dict) -> str:
    """Identifiant de la composition passe a Remotion.

    Les ids de modele du projet sont en snake_case (format JSON, tests,
    presets) alors que Remotion n'accepte que ``[a-zA-Z0-9-]`` : le registre
    frontend applique la meme correspondance (``quote_cinematic`` ->
    ``quote-cinematic``), donc l'aperçu et le rendu visent la meme entree.
    """
    if project.get("version") == schema.SCHEMA_VERSION_V2:
        return _remotion_id(resolve_mod.composition_id(project))
    template = str(project.get("template", ""))
    if template not in schema.MODELS:
        raise RuntimeError(f"Modele inconnu pour le rendu : {template!r}.")
    return _remotion_id(template)


def _remotion_id(model_id: str) -> str:
    return model_id.replace("_", "-")


def remotion_cli() -> Path:
    cli = WEB_DIR / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    if not cli.exists():
        raise RuntimeError("Remotion CLI introuvable : lancez 'npm install' dans web/.")
    if not (WEB_DIR / "package.json").exists():
        raise RuntimeError("Frontend absent : dossier web/ introuvable.")
    return cli


def render_project_to_mp4(job: Job, project: dict, out_path: Path) -> dict:
    """Rendu reel d'UN projet. Utilise par l'export unitaire et par la file."""
    prepared = prepare_for_render(project)
    composition = composition_id_of(project)

    props_path = mediacache.write_props(prepared, job.id)
    try:
        cmd = [
            str(node_command()),
            str(remotion_cli()),
            "render",
            ENTRY,
            composition,
            str(out_path),
            f"--props={props_path}",
            "--codec=h264",
            "--log=info",
        ]
        proc = subprocess.Popen(
            cmd,
            cwd=str(WEB_DIR),
            env=_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        job.result_process = proc  # type: ignore[attr-defined]

        tail: list[str] = []
        total_seen = 0
        for line in proc.stdout:  # type: ignore[union-attr]
            tail.append(line.rstrip())
            if len(tail) > 200:
                tail.pop(0)
            match = _PROGRESS_RE.search(line)
            if match:
                current, total = int(match.group(1)), int(match.group(2))
                total_seen = max(total_seen, total)
                job.set_progress(current, total or 1, f"Rendu {current}/{total}")
            if job.cancel_event.is_set():
                _terminate(proc)
                raise JobCancelled()
            if proc.poll() is not None:
                break

        returncode = proc.wait(timeout=30)
        if job.cancel_event.is_set():
            raise JobCancelled()
        if returncode != 0:
            raise RuntimeError(
                f"Le rendu Remotion a echoue (code {returncode}) :\n"
                + ("\n".join(tail[-25:]) or "aucune sortie")
            )
        if not out_path.exists() or out_path.stat().st_size == 0:
            raise RuntimeError("Le rendu n'a produit aucun fichier.")

        from shortvideos.probe import probe_mp4

        info = probe_mp4(str(out_path))
        info["path"] = str(out_path)
        info["size_bytes"] = out_path.stat().st_size
        info["composition"] = composition
        info["frames_expected"] = total_seen
        return info
    finally:
        props_path.unlink(missing_ok=True)


def _terminate(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        try:
            proc.kill()
        except OSError:
            pass


def render_props_preview(project: dict) -> dict:
    """Props telles que les verrait le Player (pour inspection dans l'UI)."""
    return json.loads(json.dumps(prepare_for_render(project)))
