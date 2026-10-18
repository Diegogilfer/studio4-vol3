"""Sonda de ingeniería inversa para APIs compatibles con OpenAI / TTS y estado local de STUDIO 4.

Uso:
  python .agents/skills/ingenieria-inversa/scripts/sondar_api.py --estado
  python .agents/skills/ingenieria-inversa/scripts/sondar_api.py --modelos https://api.xiaomimimo.com/v1 XIAOMIMIMO_API_KEY
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def sondar_estado(puerto: int = 8000) -> None:
    url = f"http://127.0.0.1:{puerto}/api/estado"
    with urllib.request.urlopen(url, timeout=10) as r:
        d = json.loads(r.read().decode("utf-8"))
    prod = d.get("produccion") or {}
    opc = d.get("opciones") or {}
    voz = prod.get("voz") or {}
    print(f"=== ESTADO VIVO EN PUERTO {puerto} ===")
    print("Producción activa:", prod.get("id"), "| Estado:", prod.get("estado"))
    print("Proveedor voz:", prod.get("proveedor_voz"), "| Voice ID:", prod.get("voice_id"))
    print("Trabajo:", json.dumps(prod.get("trabajo") or {}, ensure_ascii=False))
    print("Voz generada:", bool(voz), "| Proveedor:", voz.get("proveedor"), "| Duración:", voz.get("duracion"))
    print("Opciones voz:", json.dumps(opc.get("voces") or {}, ensure_ascii=False))
    print("Claves activas:", {k: opc.get(k) for k in ("gemini_ok", "deepseek_ok", "mimo_ok", "elevenlabs_ok")})


def sondar_modelos(base_url: str, var_entorno: str) -> None:
    import os
    import requests
    from studio4 import config  # carga .env automáticamente

    clave = os.getenv(var_entorno, "").strip() or getattr(config, var_entorno, "")
    if not clave:
        raise SystemExit(f"No se encontró la variable {var_entorno} en el entorno ni en config.")
    r = requests.get(
        f"{base_url.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {clave}"},
        timeout=15,
    )
    print(f"GET {base_url.rstrip('/')}/models -> HTTP {r.status_code}")
    try:
        datos = r.json()
        modelos = [m.get("id") for m in (datos.get("data") or [])]
        print("Modelos disponibles:", modelos or datos)
    except Exception:
        print(r.text[:600])


def main() -> None:
    p = argparse.ArgumentParser(description="Sonda de ingeniería inversa para STUDIO 4")
    p.add_argument("--estado", action="store_true", help="Inspecciona /api/estado del servidor local")
    p.add_argument("--puerto", type=int, default=8000, help="Puerto del servidor local (por defecto 8000)")
    p.add_argument("--modelos", nargs=2, metavar=("URL_BASE", "VAR_CLAVE"), help="Lista los modelos de una API")
    args = p.parse_args()
    if args.estado:
        sondar_estado(args.puerto)
    elif args.modelos:
        sondar_modelos(args.modelos[0], args.modelos[1])
    else:
        p.print_help()


if __name__ == "__main__":
    main()
