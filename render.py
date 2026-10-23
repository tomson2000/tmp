"""Vorschaubild aus vier Ansichten – ohne GUI, nur matplotlib."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

# (Titel, Elevation, Azimut)
VIEWS = [
    ("Isometrisch", 30, -60),
    ("Vorne", 0, -90),
    ("Oben", 90, -90),
    ("Rechts", 0, 0),
]
LIGHT = np.array([0.4, -0.6, 0.7]) / np.linalg.norm([0.4, -0.6, 0.7])


def render_views(stl_path: Path, png_path: Path, size_px: int = 900) -> Path:
    mesh = trimesh.load(stl_path, force="mesh")
    tris = mesh.triangles
    # Einfache Lambert-Schattierung je Dreieck
    shade = 0.35 + 0.65 * np.clip(mesh.face_normals @ LIGHT, 0, 1)
    colors = np.column_stack([0.30 * shade, 0.55 * shade, 0.85 * shade, np.ones_like(shade)])

    lo, hi = mesh.bounds
    center, half = (lo + hi) / 2, (hi - lo).max() / 2 or 1.0

    fig = plt.figure(figsize=(size_px / 100, size_px / 100), dpi=100)
    for i, (title, elev, azim) in enumerate(VIEWS, start=1):
        ax = fig.add_subplot(2, 2, i, projection="3d")
        # Rückseiten ausblenden, sonst scheinen sie durch (matplotlib hat keinen Z-Buffer)
        e, a = np.radians(elev), np.radians(azim)
        cam = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
        visible = mesh.face_normals @ cam > 1e-6
        ax.add_collection3d(Poly3DCollection(tris[visible], facecolors=colors[visible],
                                             edgecolor=(0, 0, 0, 0.08), linewidths=0.2))
        for setlim, c in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), center):
            setlim(c - half, c + half)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=elev, azim=azim)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("X", fontsize=7)
        ax.set_ylabel("Y", fontsize=7)
        ax.set_zlabel("Z", fontsize=7)
        ax.tick_params(labelsize=6)

    dims = hi - lo
    fig.suptitle(f"{dims[0]:.1f} × {dims[1]:.1f} × {dims[2]:.1f} mm", fontsize=11)
    fig.tight_layout()
    fig.savefig(png_path)
    plt.close(fig)
    return png_path
