# cad-mcp

MCP-Server, mit dem ein LLM (z. B. Claude) parametrische 3D-Modelle per Sprache baut:
„Zeichne mir eine Pyramide, Grundfläche 100 mm, Höhe 80 mm" → STEP, STL und Vorschaubild.

## So funktioniert es

```
Du ──Sprache──▶ Claude ──build123d-Code──▶ cad-mcp ──▶ Subprozess (build123d / OpenCascade)
                  ▲                                             │
                  └──────── Kennzahlen + Vorschaubild ◀─────────┘   STEP + STL im Workspace
```

Der entscheidende Teil ist die Rückkopplung: Nach jedem Lauf bekommt das LLM ein Bild aus
vier Ansichten (isometrisch, vorne, oben, rechts) plus Abmessungen und Volumen. Dadurch erkennt
es eigene Fehler und korrigiert sie – ähnlich wie Playwright mit Screenshot.

## Tools

| Tool | Zweck |
|---|---|
| `run_cad_code(code, name)` | Führt build123d-Code aus (Ergebnis in `result`), speichert STEP + STL, liefert Kennzahlen und Vorschau |
| `render_preview(name)` | Vorschaubild eines gespeicherten Modells |
| `export_model(name, fmt, target_dir)` | Export als `step`, `stl`, `3mf`, `glb`, `obj` |
| `list_models()` | Alle Modelle im Workspace |
| `get_source(name)` | build123d-Code eines Modells – zum Weiterbearbeiten |
| `image_to_extrusion(image, …)` | Logo, Schriftzug, Silhouette → Umrisse extrudieren (STEP + STL, als Code weiter bearbeitbar) |
| `image_to_relief(image, …)` | Foto → Höhenrelief oder Lithophane (STL/3MF), mit Höhenkarte als Vorschau |

## Aus Bildern 3D-Modelle machen

Ein in den Chat hochgeladenes Bild sieht Claude, der MCP-Server bekommt es aber nicht.
Leg Bilder deshalb in den Bilderordner (Standard `~/cad-bilder`) und nenne den Dateinamen:

- „Nimm `logo.png` aus cad-bilder, 60 mm breit, 3 mm hoch, auf einer 2-mm-Grundplatte."
  → `image_to_extrusion`. Umrisse werden automatisch erkannt (Standard: dunkel = Form).
  Passt etwas nicht: `invert`, `threshold` (0–255) oder `simplify_mm` ändern.
- „Mach aus `oma.jpg` eine Lithophane, 100 mm breit, mit Rahmen."
  → `image_to_relief`. Dunkle Stellen werden dick, gegen das Licht erscheint das Foto.
  Für ein normales Relief (hell = hoch) `dark_is_high=false`.

Absolute Pfade (z. B. `/Users/du/Desktop/logo.png`) gehen auch.
Geeignet sind kontrastreiche Bilder: Logos, Schriftzüge, Scherenschnitte, Fotos für Reliefs.
Aus einem normalen Foto eines Gegenstands entsteht so **kein** echtes 3D-Objekt – dafür
bräuchte es ein KI-Modell (Bild → 3D).

## Schnellstart auf dem Mac mini mit Claude Code

```bash
git clone -b claude/cad-mcp-server-setup-7bb9n7 https://github.com/tomson2000/tmp.git ~/cad-mcp
cd ~/cad-mcp && claude
```

Auftrag an Claude Code:

> Installiere diesen MCP-Server laut README: venv anlegen, requirements installieren,
> mit `python test_pyramide.py` und `python test_bilder.py` testen und in meine
> Claude-Desktop-Konfiguration eintragen.

## Installation

Python 3.10–3.13.

```bash
cd cad-mcp
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

End-to-End-Test (baut eine Pyramide 100 × 100 × 80 mm, Ausgabe in `test-output/`):

```bash
python test_pyramide.py
```

Erwartet: `Abmessungen (X×Y×Z): 100.00 × 100.00 × 80.00 mm`, Volumen ≈ 266.667 mm³.

Bild-Tools testen (erzeugt eigene Testbilder, endet mit `OK`):

```bash
python test_bilder.py
```

Kurztest mit dem MCP Inspector:

```bash
npx @modelcontextprotocol/inspector .venv/bin/python server.py
```

## In Claude Desktop einbinden

`claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`,
Windows: `%APPDATA%\Claude\`):

```json
{
  "mcpServers": {
    "cad": {
      "command": "/ABSOLUTER/PFAD/cad-mcp/.venv/bin/python",
      "args": ["/ABSOLUTER/PFAD/cad-mcp/server.py"],
      "env": {
        "CAD_MCP_WORKSPACE": "/ABSOLUTER/PFAD/cad-modelle",
        "CAD_MCP_IMAGES": "/ABSOLUTER/PFAD/cad-bilder"
      }
    }
  }
}
```

Unter Windows lautet der Python-Pfad `...\cad-mcp\.venv\Scripts\python.exe`.
Claude Desktop neu starten – danach z. B.:

- „Zeichne mir eine Pyramide, Grundfläche 100 × 100 mm, Höhe 80 mm."
- „Mach daraus eine Stufenpyramide mit 5 Stufen."
- „Ein Winkel 80 × 40 × 50 mm, 10 mm Wandstärke, zwei 4-mm-Bohrungen, exportiere als 3MF."

## Konfiguration

| Variable | Standard | Bedeutung |
|---|---|---|
| `CAD_MCP_WORKSPACE` | `~/cad-mcp-output` | Ablage der Modelle (ein Ordner je Modell) |
| `CAD_MCP_TIMEOUT` | `60` | Maximale Laufzeit eines CAD-Skripts in Sekunden |
| `CAD_MCP_IMAGES` | `~/cad-bilder` | Ordner, aus dem die Bild-Tools Dateien lesen |

## Sicherheit

`run_cad_code` führt vom LLM erzeugten Python-Code aus. Er läuft in einem eigenen Prozess mit
Zeitlimit, ist aber **nicht** abgeschottet: Er hat dieselben Rechte wie dein Benutzer.
Für den Einsatz über die eigene Maschine hinaus den Runner in einen Container
(z. B. Docker ohne Netzwerk, nur Workspace gemountet) verlagern.

## Ausbauideen

- **Bessere Vorschau:** Renderer gegen `pyvista` (VTK, echter Z-Buffer) tauschen.
- **Messen und Prüfen:** Tool für Wandstärken, Überhänge (3D-Druck), Kollisionen.
- **Baugruppen:** Mehrere Teile mit Positionen verwalten und gemeinsam exportieren.
- **Bauteilbibliothek:** Schrauben, Muttern, Lager aus `bd_warehouse` bereitstellen.
- **Tests:** Ein pytest-Satz, der Referenzmodelle baut und Volumen/Abmessungen prüft.
