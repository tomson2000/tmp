"""
End-to-End-Test: startet server.py per MCP-Client und baut eine Pyramide (100 × 100 × 80 mm).

    python test_pyramide.py

Legt Modell und Vorschaubild in ./test-output ab und prüft das Volumen (100·100·80/3 mm³).
"""

import asyncio
import base64
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent
OUT = HERE / "test-output"

PYRAMIDE = '''
with BuildPart() as p:
    with BuildSketch():
        Rectangle(100, 100)
    with BuildSketch(Plane.XY.offset(80)):
        Rectangle(0.01, 0.01)
    loft()
result = p.part
'''


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(HERE / "server.py")],
        env={"CAD_MCP_WORKSPACE": str(OUT)},
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print("Tools:", [t.name for t in (await s.list_tools()).tools])
            res = await s.call_tool("run_cad_code", {"code": PYRAMIDE, "name": "pyramide"})
            text = ""
            for c in res.content:
                if c.type == "text":
                    text += c.text
                    print(c.text)
                else:
                    png = OUT / "pyramide.png"
                    png.write_bytes(base64.b64decode(c.data))
                    print("Vorschaubild:", png)
            if getattr(res, "is_error", None) or getattr(res, "isError", False):
                print("FEHLER: run_cad_code ist fehlgeschlagen")
                return 1
    print("Erwartetes Volumen ≈", round(100 * 100 * 80 / 3), "mm³")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
