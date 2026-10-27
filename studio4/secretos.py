"""Secretos (cuentas y claves) en el Administrador de credenciales de Windows, cifrados con tu usuario de Windows, en
vez de en texto plano en .env. Se leen primero de ahí; si no están, del entorno (.env), para no romper nada.

Para pasar un secreto del .env al almacén: `python -m studio4.secretos SUPABASE_CLAVE` (lo quita del .env).
"""

from __future__ import annotations

import os
import re
import sys

SERVICIO = "Studio4"


def _almacen():
    try:
        import keyring
        return keyring
    except ImportError:
        return None


def leer(nombre: str) -> str:
    k = _almacen()
    if k:
        try:
            valor = k.get_password(SERVICIO, nombre)
            if valor:
                return valor
        except Exception:  # noqa: BLE001 - sin almacén disponible: se usa el entorno
            pass
    return os.getenv(nombre, "").strip()


def guardar(nombre: str, valor: str) -> None:
    k = _almacen()
    if not k:
        raise RuntimeError("Falta la librería keyring (pip install keyring).")
    k.set_password(SERVICIO, nombre, valor)


def mover_del_env(nombre: str, env: str | None = None) -> bool:
    """Pasa un secreto del .env al almacén de Windows y lo borra del .env. True si lo movió."""
    from . import config
    ruta = env or str(config.ENV_FILE)
    try:
        texto = open(ruta, encoding="utf-8").read()
    except FileNotFoundError:
        return False
    m = re.search(rf"^{re.escape(nombre)}=(.*)$", texto, re.M)
    if not m or not m.group(1).strip():
        return False
    guardar(nombre, m.group(1).strip().strip('"').strip("'"))
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(re.sub(rf"^{re.escape(nombre)}=.*\n?", "", texto, flags=re.M))
    os.environ.pop(nombre, None)
    return True


if __name__ == "__main__":
    for n in sys.argv[1:]:
        print(f"{n}: {'movido al almacén de Windows' if mover_del_env(n) else 'no estaba en .env'}")
