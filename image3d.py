"""
Aus Bildern 3D-Modelle machen – ohne KI, rein lokal.

  * Kontur:  Logo, Schriftzug, Silhouette → Umrisse finden → build123d-Code,
             der sie extrudiert (bleibt als STEP parametrisch weiterbearbeitbar).
  * Relief:  Helligkeit → Höhe → geschlossenes Dreiecksnetz (STL),
             z. B. für Lithophanen oder Reliefplatten.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import trimesh
from PIL import Image as PILImage, ImageOps

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}


def load_gray(path: Path) -> np.ndarray:
    """Bild als Graustufen-Array (0 = schwarz, 255 = weiß).
    Transparenz wird zu Weiß, damit freigestellte PNG-Logos funktionieren."""
    img = ImageOps.exif_transpose(PILImage.open(path))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = PILImage.new("RGBA", img.size, (255, 255, 255, 255))
        img = PILImage.alpha_composite(bg, img)
    return np.asarray(img.convert("L"), dtype=np.uint8)


# --------------------------------------------------------------------------
# Kontur → Extrusion
# --------------------------------------------------------------------------
def trace_shapes(
    gray: np.ndarray,
    width_mm: float,
    threshold: int | None = None,
    invert: bool = False,
    simplify_mm: float = 0.2,
    min_area_mm2: float = 1.0,
) -> tuple[list[tuple[list, list[list]]], dict]:
    """Findet die Formen im Bild.

    Standard: dunkle Bereiche sind die Form (schwarzes Logo auf weißem Grund).
    Rückgabe: [(außenkontur, [loch, …]), …] in mm, Y nach oben, plus Kennzahlen.
    """
    if threshold is None:
        threshold, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
    if invert:
        mask = 255 - mask
    # Ränder freihalten, sonst verschmilzt eine Form am Bildrand mit dem Rahmen
    mask = cv2.copyMakeBorder(mask, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0)

    h_px, w_px = gray.shape
    scale = width_mm / w_px
    eps_px = max(simplify_mm / scale, 0.5)
    min_area_px = min_area_mm2 / scale**2

    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)

    def to_mm(cnt: np.ndarray) -> list | None:
        if cv2.contourArea(cnt) < min_area_px:
            return None
        pts = cv2.approxPolyDP(cnt, eps_px, True).reshape(-1, 2).astype(float)
        if len(pts) < 3:
            return None
        pts -= 2  # Rand wieder abziehen
        # Bild-Koordinaten (Y nach unten) → CAD (Y nach oben), Mitte auf Ursprung
        x = (pts[:, 0] - w_px / 2) * scale
        y = (h_px / 2 - pts[:, 1]) * scale
        return [(round(float(a), 3), round(float(b), 3)) for a, b in zip(x, y)]

    shapes: list[tuple[list, list[list]]] = []
    if hierarchy is not None:
        hier = hierarchy[0]
        for i, (_, _, first_child, parent) in enumerate(hier):
            if parent != -1:
                continue
            outer = to_mm(contours[i])
            if outer is None:
                continue
            holes, child = [], first_child
            while child != -1:
                hole = to_mm(contours[child])
                if hole is not None:
                    holes.append(hole)
                child = hier[child][0]
            shapes.append((outer, holes))

    stats = {
        "threshold": int(threshold),
        "shapes": len(shapes),
        "holes": sum(len(h) for _, h in shapes),
        "points": sum(len(o) + sum(map(len, h)) for o, h in shapes),
        "size_mm": (round(width_mm, 2), round(h_px * scale, 2)),
    }
    return shapes, stats


def extrusion_code(shapes: list, height_mm: float, base_mm: float = 0.0, margin_mm: float = 3.0) -> str:
    """build123d-Code, der die Formen extrudiert – optional auf einer Grundplatte."""
    lines = [
        "# Automatisch aus einem Bild erzeugt (image_to_extrusion).",
        f"HEIGHT = {height_mm}   # Höhe der Form in mm",
        f"BASE = {base_mm}       # Grundplatte in mm (0 = keine)",
        f"MARGIN = {margin_mm}   # Rand der Grundplatte in mm",
        "",
        "SHAPES = [  # (Außenkontur, [Löcher])",
    ]
    for outer, holes in shapes:
        lines.append(f"    ({outer!r},\n     {holes!r}),")
    lines += [
        "]",
        "",
        "faces = [",
        "    Face(Wire.make_polygon(outer, close=True),",
        "         [Wire.make_polygon(h, close=True) for h in holes])",
        "    for outer, holes in SHAPES",
        "]",
        "result = extrude(Compound(faces), amount=HEIGHT)",
        "if BASE > 0:",
        "    bb = result.bounding_box()",
        "    plate = Pos(bb.center().X, bb.center().Y, -BASE / 2) * Box(",
        "        bb.size.X + 2 * MARGIN, bb.size.Y + 2 * MARGIN, BASE)",
        "    result = plate + result",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Helligkeit → Relief
# --------------------------------------------------------------------------
def relief_heights(
    gray: np.ndarray,
    width_mm: float,
    max_height_mm: float = 3.0,
    base_mm: float = 0.8,
    dark_is_high: bool = True,
    resolution_mm: float = 0.4,
    border_mm: float = 0.0,
) -> tuple[np.ndarray, float]:
    """Höhenraster: base + Helligkeit × max_height. Rückgabe (z, Gesamtbreite in mm).

    dark_is_high=True ergibt eine Lithophane (dunkle Stellen dick, gegen Licht
    erscheint das Bild positiv). False ergibt ein klassisches Relief.
    """
    h_px, w_px = gray.shape
    nx = max(int(round(width_mm / resolution_mm)) + 1, 2)
    ny = max(int(round(nx * h_px / w_px)), 2)
    img = np.asarray(PILImage.fromarray(gray).resize((nx, ny), PILImage.LANCZOS), dtype=float) / 255.0
    level = 1.0 - img if dark_is_high else img
    z = base_mm + level * max_height_mm

    step = width_mm / (nx - 1)
    if border_mm > 0:  # Rahmen auf voller Höhe, stabilisiert dünne Lithophanen
        b = max(int(round(border_mm / step)), 1)
        z = np.pad(z, b, constant_values=base_mm + max_height_mm)
    return z, step * (z.shape[1] - 1)


def relief_mesh(z: np.ndarray, width_mm: float) -> trimesh.Trimesh:
    """Geschlossenes Netz aus einem Höhenraster, Boden auf z=0."""
    ny, nx = z.shape
    step = width_mm / (nx - 1)
    xs = (np.arange(nx) - (nx - 1) / 2) * step
    ys = ((ny - 1) / 2 - np.arange(ny)) * step  # Bildzeile 0 = oben
    X, Y = np.meshgrid(xs, ys)

    top = np.column_stack([X.ravel(), Y.ravel(), z.ravel()])
    bottom = np.column_stack([X.ravel(), Y.ravel(), np.zeros(X.size)])
    verts = np.vstack([top, bottom])
    n = X.size
    idx = np.arange(n).reshape(ny, nx)

    # Oberseite und Boden (Boden mit umgekehrter Orientierung)
    a, b_, c, d = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, :-1].ravel(), idx[1:, 1:].ravel()
    faces = [
        np.column_stack([a, c, b_]), np.column_stack([b_, c, d]),
        np.column_stack([a, b_, c]) + n, np.column_stack([b_, d, c]) + n,
    ]
    # Seitenwände entlang des Randes (im Uhrzeigersinn von oben gesehen)
    ring = np.concatenate([idx[0, :], idx[1:, -1], idx[-1, -2::-1], idx[-2:0:-1, 0]])
    nxt = np.roll(ring, -1)
    faces += [np.column_stack([ring, nxt, ring + n]), np.column_stack([nxt, nxt + n, ring + n])]

    # Orientierung stimmt per Konstruktion (Normalen nach außen)
    return trimesh.Trimesh(vertices=verts, faces=np.vstack(faces), process=True)
