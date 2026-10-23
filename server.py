"""
cad-mcp – ein MCP-Server, mit dem ein LLM parametrische 3D-Modelle baut.

Prinzip:
  1. Das LLM schreibt build123d-Code (Python, parametrisches CAD).
  2. Der Server führt ihn isoliert in einem Subprozess aus.
  3. Das Ergebnis wird als STEP + STL gespeichert und als Vorschaubild
     (4 Ansichten) zurückgegeben – so "sieht" das LLM, was es gebaut hat.

Zusätzlich: image_to_extrusion / image_to_relief machen aus Bildern Modelle.

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

import image3d
from render import render_heightmap, render_views

# --------------------------------------------------------------------------
# Konfiguration
# --------------------------------------------------------------------------
WORKSPACE = Path(os.environ.get("CAD_MCP_WORKSPACE", Path.home() / "cad-mcp-output"))
TIMEOUT_S = int(os.environ.get("CAD_MCP_TIMEOUT", "60"))
IMAGES = Path(os.environ.get("CAD_MCP_IMAGES", Path.home() / "cad-bilder"))
RUNNER = Path(__file__).with_name("runner.py")

WORKSPACE.mkdir(parents=True, exist_ok=True)
IMAGES.mkdir(parents=True, exist_ok=True)

mcp = MCPServer(
    "cad-mcp",
    instructions=(
        "Baue 3D-Modelle mit build123d (Python). Ablauf: run_cad_code mit Code, "
        "der das Endergebnis der Variable `result` zuweist. Prüfe danach das "
        "Vorschaubild und korrigiere bei Bedarf. Einheiten sind Millimeter. "
        "`from build123d import *` ist bereits importiert. "
        "Mit export_model lassen sich weitere Formate erzeugen. "
        f"Bilder liegen in {IMAGES}: image_to_extrusion macht aus Logos, "
        "Schriftzügen und Silhouetten einen extrudierten Körper, image_to_relief "
        "macht aus Fotos ein Relief oder eine Lithophane."
    ),
)


def _safe_name(name: str) -> str:
    """Nur einfache Dateinamen zulassen (kein Path-Traversal)."""
    clean = re.sub(r"[^A-Za-z0-9_-]", "_", name.strip())[:60]
    return clean or "modell"


def _model_dir(name: str) -> Path:
    return WORKSPACE / _safe_name(name)


def _image_path(image: str) -> Path:
    """Dateiname im Bilderordner oder absoluter Pfad zu einer Bilddatei."""
    p = Path(image).expanduser()
    if not p.is_absolute():
        p = IMAGES / p
    if p.suffix.lower() not in image3d.IMAGE_SUFFIXES:
        raise ValueError(f"'{p.name}' ist kein unterstütztes Bildformat.")
    if not p.is_file():
        found = sorted(f.name for f in IMAGES.iterdir() if f.suffix.lower() in image3d.IMAGE_SUFFIXES)
        hint = ", ".join(found[:20]) or "keine"
        raise ValueError(f"Bild '{image}' nicht gefunden. Bilder in {IMAGES}: {hint}")
    return p


def _build(code: str, name: str) -> list:
    """Führt build123d-Code im Subprozess aus, speichert STEP + STL + Vorschau."""
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
    return _build(code, name)


@mcp.tool()
def image_to_extrusion(
    image: str,
    name: str = "",
    width_mm: float = 80.0,
    height_mm: float = 5.0,
    base_mm: float = 0.0,
    threshold: int | None = None,
    invert: bool = False,
    simplify_mm: float = 0.2,
    min_area_mm2: float = 1.0,
) -> list:
    """Macht aus einem Logo, Schriftzug oder einer Silhouette einen 3D-Körper.

    Die Umrisse im Bild werden gefunden und um height_mm extrudiert. Gut für
    Ausstechformen, Schilder, Stempel, Schlüsselanhänger.

    image:        Dateiname im Bilderordner (CAD_MCP_IMAGES) oder absoluter Pfad
    width_mm:     Breite des Bildes im Modell; die Höhe ergibt sich proportional
    height_mm:    Extrusionshöhe der Form
    base_mm:      > 0 legt eine Grundplatte (mit 3 mm Rand) darunter
    threshold:    Helligkeitsschwelle 0–255; leer = automatisch (Otsu)
    invert:       Standard ist "dunkel = Form"; True für helle Form auf dunklem Grund
    simplify_mm:  Glättung der Kontur; größer = weniger Punkte, gröber
    min_area_mm2: kleinere Flecken (Staub, Bildrauschen) werden ignoriert

    Ergebnis ist build123d-Code (get_source), also weiter bearbeitbar.
    Stimmt das Ergebnis nicht, threshold, invert oder simplify_mm anpassen.
    """
    try:
        path = _image_path(image)
    except ValueError as e:
        return [str(e)]
    shapes, stats = image3d.trace_shapes(
        image3d.load_gray(path), width_mm, threshold, invert, simplify_mm, min_area_mm2
    )
    if not shapes:
        return [
            f"Keine Formen gefunden (Schwelle {stats['threshold']}). "
            "Probiere invert=True oder einen anderen threshold."
        ]
    result = _build(image3d.extrusion_code(shapes, height_mm, base_mm), name or path.stem)
    result[0] = (
        f"Bild: {path.name} | Schwelle: {stats['threshold']} | Formen: {stats['shapes']} | "
        f"Löcher: {stats['holes']} | Konturpunkte: {stats['points']}\n{result[0]}"
    )
    return result


@mcp.tool()
def image_to_relief(
    image: str,
    name: str = "",
    width_mm: float = 100.0,
    max_height_mm: float = 3.0,
    base_mm: float = 0.8,
    dark_is_high: bool = True,
    resolution_mm: float = 0.4,
    border_mm: float = 0.0,
) -> list:
    """Macht aus einem Foto ein Höhenrelief: Helligkeit wird zu Höhe.

    Standard ist eine Lithophane: dunkle Stellen werden dick. Gegen das Licht
    gehalten erscheint das Foto. Für 3D-Druck typisch: base_mm 0.8,
    max_height_mm 2.4, border_mm 3, hochkant und mit 100 % Füllung drucken.

    image:         Dateiname im Bilderordner (CAD_MCP_IMAGES) oder absoluter Pfad
    width_mm:      Breite im Modell; die Höhe ergibt sich proportional
    max_height_mm: Höhenunterschied zwischen hellster und dunkelster Stelle
    base_mm:       durchgehende Grundstärke
    dark_is_high:  False = helle Stellen hoch (klassisches Relief)
    resolution_mm: Rasterweite; kleiner = feiner, aber größere Datei
    border_mm:     Rahmen auf voller Höhe rundherum, kommt zu width_mm hinzu (0 = keiner)

    Liefert eine Höhenkarte (Draufsicht) und die 3D-Ansichten.
    Ergebnis ist ein Dreiecksnetz (STL, 3MF, OBJ, GLB), kein STEP.
    """
    try:
        path = _image_path(image)
    except ValueError as e:
        return [str(e)]
    if resolution_mm < 0.1 or width_mm / resolution_mm > 1500:
        return ["resolution_mm zu fein: höchstens 1500 Rasterpunkte je Seite, mindestens 0.1 mm."]

    out_dir = _model_dir(name or path.stem)
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in ("model.step", "source.py"):  # stammt sonst von einem früheren Modell
        (out_dir / stale).unlink(missing_ok=True)

    z, total_width = image3d.relief_heights(
        image3d.load_gray(path), width_mm, max_height_mm, base_mm, dark_is_high, resolution_mm, border_mm
    )
    mesh = image3d.relief_mesh(z, total_width)
    mesh.export(out_dir / "model.stl")
    png = render_views(out_dir / "model.stl", out_dir / "preview.png")
    heightmap = render_heightmap(z, total_width, out_dir / "heightmap.png")

    dx, dy, dz = mesh.extents
    summary = (
        f"Relief '{out_dir.name}' aus {path.name} erstellt.\n"
        f"Abmessungen (X×Y×Z): {dx:.2f} × {dy:.2f} × {dz:.2f} mm\n"
        f"Volumen: {mesh.volume:.2f} mm³ | Dreiecke: {len(mesh.faces)} | "
        f"Geschlossen: {mesh.is_watertight}\n"
        f"Datei: {out_dir / 'model.stl'}"
    )
    return [summary, Image(path=str(heightmap)), Image(path=str(png))]


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

    if fmt == "step" and not (src_dir / "model.step").exists():
        return f"'{_safe_name(name)}' ist ein Netzmodell (Relief) – kein STEP möglich. Nimm stl oder 3mf."
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
