"""
cad-mcp – ein MCP-Server, mit dem ein LLM parametrische 3D-Modelle baut.

Prinzip:
  1. Das LLM schreibt build123d-Code (Python, parametrisches CAD).
  2. Der Server führt ihn isoliert in einem Subprozess aus.
  3. Das Ergebnis wird als STEP + STL gespeichert und als Vorschaubild
     (4 Ansichten) zurückgegeben – so "sieht" das LLM, was es gebaut hat.

Start:  python server.py            (stdio, z. B. für Claude Desktop)
Test:   npx @modelcontextprotocol/inspector python server.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer

from render import render_views

# --------------------------------------------------------------------------
# Konfiguration
# --------------------------------------------------------------------------
WORKSPACE = Path(os.environ.get("CAD_MCP_WORKSPACE", Path.home() / "cad-mcp-output"))
TIMEOUT_S = int(os.environ.get("CAD_MCP_TIMEOUT", "60"))
RUNNER = Path(__file__).with_name("runner.py")

WORKSPACE.mkdir(parents=True, exist_ok=True)

mcp = MCPServer(
    "cad-mcp",
    instructions=(
        "Baue 3D-Modelle mit build123d (Python). Ablauf: run_cad_code mit Code, "
        "der das Endergebnis der Variable `result` zuweist. Prüfe danach das "
        "Vorschaubild und korrigiere bei Bedarf. Einheiten sind Millimeter. "
        "`from build123d import *` ist bereits importiert. "
        "Mit export_model lassen sich weitere Formate erzeugen."
    ),
)


def _safe_name(name: str) -> str:
    """Nur einfache Dateinamen zulassen (kein Path-Traversal)."""
    clean = re.sub(r"[^A-Za-z0-9_-]", "_", name.strip())[:60]
    return clean or "modell"


def _model_dir(name: str) -> Path:
    return WORKSPACE / _safe_name(name)


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------
@mcp.tool()
def run_cad_code(code: str, name: str = "modell") -> list:
    """Führt build123d-Code aus und speichert das Modell.

    Der Code muss das fertige Teil der Variable `result` zuweisen.
    `from build123d import *` ist schon importiert, Einheiten in mm.

    Beispiel (Pyramide 100x100 mm, Höhe 80 mm):
        with BuildPart() as p:
            with BuildSketch():
                Rectangle(100, 100)
            with BuildSketch(Plane.XY.offset(80)):
                Rectangle(0.01, 0.01)
            loft()
        result = p.part

    Gibt Kennzahlen (Volumen, Abmessungen) und ein Vorschaubild zurück.
    """
    out_dir = _model_dir(name)
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        script = f.name

    try:
        proc = subprocess.run(
            [sys.executable, "-I", str(RUNNER), script, str(out_dir)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return [f"Abbruch: Ausführung dauerte länger als {TIMEOUT_S} s."]
    finally:
        os.unlink(script)

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).strip()[-3000:]
        return [f"Fehler beim Ausführen des CAD-Codes:\n{err}"]

    info = json.loads(proc.stdout.strip().splitlines()[-1])
    (out_dir / "source.py").write_text(code, encoding="utf-8")

    png = render_views(out_dir / "model.stl", out_dir / "preview.png")

    bb = info["bbox"]
    summary = (
        f"Modell '{_safe_name(name)}' erstellt.\n"
        f"Abmessungen (X×Y×Z): {bb[0]:.2f} × {bb[1]:.2f} × {bb[2]:.2f} mm\n"
        f"Volumen: {info['volume']:.2f} mm³ | Oberfläche: {info['area']:.2f} mm²\n"
        f"Solids: {info['solids']} | Gültig: {info['valid']}\n"
        f"Dateien: {out_dir / 'model.step'}, {out_dir / 'model.stl'}"
    )
    return [summary, Image(path=str(png))]


@mcp.tool()
def render_preview(name: str = "modell") -> list:
    """Rendert das gespeicherte Modell erneut aus vier Ansichten
    (isometrisch, vorne, oben, rechts)."""
    stl = _model_dir(name) / "model.stl"
    if not stl.exists():
        return [f"Kein Modell '{_safe_name(name)}' gefunden. Erst run_cad_code ausführen."]
    png = render_views(stl, stl.with_name("preview.png"))
    return [Image(path=str(png))]


@mcp.tool()
def export_model(name: str = "modell", fmt: str = "step", target_dir: str | None = None) -> str:
    """Exportiert ein Modell. Formate: step, stl, 3mf, glb, obj.

    Ohne target_dir landet die Datei im Modellordner des Workspace.
    """
    fmt = fmt.lower().lstrip(".")
    src_dir = _model_dir(name)
    if not (src_dir / "model.stl").exists():
        return f"Kein Modell '{_safe_name(name)}' gefunden."

    dest_dir = Path(target_dir).expanduser() if target_dir else src_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{_safe_name(name)}.{fmt}"

    if fmt in ("step", "stl"):
        shutil.copyfile(src_dir / f"model.{fmt}", dest)
    elif fmt in ("3mf", "glb", "obj"):
        import trimesh

        trimesh.load(src_dir / "model.stl").export(dest)
    else:
        return f"Format '{fmt}' wird nicht unterstützt (step, stl, 3mf, glb, obj)."
    return f"Exportiert: {dest}"


@mcp.tool()
def list_models() -> str:
    """Listet alle gespeicherten Modelle im Workspace."""
    names = sorted(p.name for p in WORKSPACE.iterdir() if (p / "model.stl").exists())
    return "\n".join(names) if names else "Noch keine Modelle vorhanden."


@mcp.tool()
def get_source(name: str = "modell") -> str:
    """Liefert den build123d-Code eines Modells – zum Weiterbearbeiten."""
    src = _model_dir(name) / "source.py"
    return src.read_text(encoding="utf-8") if src.exists() else "Kein Quellcode gefunden."


if __name__ == "__main__":
    mcp.run()
