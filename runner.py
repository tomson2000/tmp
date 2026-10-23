"""
Wird vom Server als eigener Prozess gestartet:
    python -I runner.py <script.py> <ausgabeordner>

Führt den build123d-Code aus, exportiert STEP + STL und gibt die
Kennzahlen als JSON-Zeile auf stdout aus.
"""

import json
import sys
from pathlib import Path

import build123d as bd


def main() -> None:
    script, out_dir = Path(sys.argv[1]), Path(sys.argv[2])

    namespace: dict = {"__name__": "__cad__"}
    exec("from build123d import *", namespace)
    exec(compile(script.read_text(encoding="utf-8"), "<cad-code>", "exec"), namespace)

    result = namespace.get("result")
    if result is None:
        sys.exit("Der Code hat keine Variable `result` gesetzt.")

    # Builder-Objekte (BuildPart, BuildSketch …) in Geometrie umwandeln
    for attr in ("part", "sketch", "line"):
        if not isinstance(result, bd.Shape) and hasattr(result, attr):
            result = getattr(result, attr)
    if isinstance(result, (list, tuple)):
        result = bd.Compound(children=list(result))
    if not isinstance(result, bd.Shape):
        sys.exit(f"`result` ist kein build123d-Shape, sondern {type(result).__name__}.")
    if not result.solids():
        sys.exit("`result` enthält keinen Volumenkörper (Solid). Für 3D-Export wird ein Körper benötigt.")

    bd.export_step(result, out_dir / "model.step")
    bd.export_stl(result, out_dir / "model.stl", tolerance=0.01, angular_tolerance=0.1)

    bb = result.bounding_box()
    print(json.dumps({
        "bbox": [bb.size.X, bb.size.Y, bb.size.Z],
        "volume": result.volume,
        "area": result.area,
        "solids": len(result.solids()),
        "valid": result.is_valid,
    }))


if __name__ == "__main__":
    main()
