"""
End-to-End-Test für die Bild-Tools: erzeugt zwei Testbilder und ruft
image_to_extrusion und image_to_relief über einen MCP-Client auf.

    python test_bilder.py

Ausgabe (Testbilder, Modelle, Vorschaubilder) in ./test-output.
"""

import asyncio
import base64
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent
OUT = HERE / "test-output"
BILDER = OUT / "bilder"


def make_images() -> None:
    BILDER.mkdir(parents=True, exist_ok=True)
    # Logo: Ring (Loch) mit Punkt darin (Insel im Loch), Dreieck, Schriftzug
    logo = Image.new("RGB", (800, 400), "white")
    d = ImageDraw.Draw(logo)
    d.ellipse((40, 60, 320, 340), fill="black")
    d.ellipse((100, 120, 260, 280), fill="white")
    d.ellipse((150, 170, 210, 230), fill="black")
    d.polygon([(360, 340), (450, 60), (540, 340)], fill="black")
    try:
        font = ImageFont.load_default(size=70)
    except TypeError:
        font = ImageFont.load_default()
    d.text((570, 240), "CAD", fill="black", font=font, anchor="ls")
    logo.save(BILDER / "logo.png")
    # "Foto": weicher Verlauf mit Kreis, als Ersatz für ein echtes Bild
    y, x = np.mgrid[0:300, 0:400]
    img = 255 * (x / 400) * 0.6 + 80 * np.exp(-((x - 200) ** 2 + (y - 150) ** 2) / 4000)
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(BILDER / "foto.jpg")


async def call(s, tool, args, name):
    res = await s.call_tool(tool, args)
    images = 0
    for c in res.content:
        if c.type == "text":
            print(c.text)
        else:
            images += 1
            png = OUT / f"{name}-{images}.png"
            png.write_bytes(base64.b64decode(c.data))
            print("Vorschaubild:", png)
    print("---")
    return res


async def main() -> int:
    make_images()
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(HERE / "server.py")],
        env={"CAD_MCP_WORKSPACE": str(OUT), "CAD_MCP_IMAGES": str(BILDER)},
    )
    ok = True
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await call(s, "image_to_extrusion",
                             {"image": "logo.png", "width_mm": 80, "height_mm": 4, "base_mm": 2}, "logo")
            ok &= any(c.type == "image" for c in res.content)
            res = await call(s, "image_to_relief",
                             {"image": "foto.jpg", "width_mm": 100, "max_height_mm": 2.4,
                              "border_mm": 3, "name": "lithophane"}, "lithophane")
            ok &= any(c.type == "image" for c in res.content)
            await call(s, "image_to_extrusion", {"image": "gibtsnicht.png"}, "fehlt")
            msg = (await s.call_tool("export_model", {"name": "lithophane", "fmt": "3mf"})).content[0].text
            print(msg)
            ok &= msg.startswith("Exportiert")
            print((await s.call_tool("export_model", {"name": "lithophane", "fmt": "step"})).content[0].text)
    print("OK" if ok else "FEHLER")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
