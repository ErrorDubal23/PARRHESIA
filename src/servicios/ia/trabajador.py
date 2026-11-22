"""Trabajador de IA: toma trabajos de la cola, llama al proveedor y guarda el intento.

    uv run python -m servicios.ia.trabajador

Independiente de la cuenta: si una cuenta llega a su límite, la base la pone en
pausa y el trabajo pasa a otra; si todas están en pausa, el trabajo espera. Agregar
una cuenta = agregar su llave al .env y reiniciar solo este trabajador.

Un hilo por proveedor con cuenta (22 nov 2026): así una llamada lenta de un proveedor no detiene a los
demás. No chocan entre sí porque ia.tomar_trabajo entrega cada trabajo a uno solo (SKIP LOCKED) y cada
hilo tiene su propia conexión.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from servicios.comun.configuracion import conectar_postgres
from servicios.ia.cliente import ErrorProveedor, LimiteAlcanzado, ModeloSaturado, llamar
from servicios.ia.formatos import SalidaInvalida, validar
from servicios.ia.proveedores import PREFERENCIA, PROVEEDORES, cuentas

registro = logging.getLogger("ia")
PROMPTS = Path(__file__).parent / "prompts"
TIPOS = ["extraer_afirmaciones", "redactar_explicacion", "agrupar_temas", "extraer_declaraciones", "redactar_guia",
         "juzgar_neutralidad"]


def prompt(version: str) -> str:
    ruta = PROMPTS / f"{version}.md"
    if not ruta.exists():
        raise SalidaInvalida(f"no existe el prompt {version}")
    return ruta.read_text(encoding="utf-8")


def sincronizar_cuentas(pg: psycopg.Connection) -> dict[str, tuple[str, str]]:
    """Registra en ia.credencial el alias de cada llave encontrada (nunca la llave)."""
    encontradas = cuentas()
    for alias, (proveedor, _) in encontradas.items():
        pg.execute("CALL ia.configurar_credencial(%s, %s, true)", (alias, proveedor))
    # Una cuenta cuya llave ya no está queda deshabilitada: así la base no elige un proveedor sin llave.
    for alias, proveedor in pg.execute("SELECT alias, proveedor FROM ia.credencial WHERE habilitada").fetchall():
        if alias not in encontradas:
            pg.execute("CALL ia.configurar_credencial(%s, %s, false)", (alias, proveedor))
    return encontradas


def disponibles(pg: psycopg.Connection) -> list[str]:
    return [p for p in PREFERENCIA
            if pg.execute("SELECT ia.elegir_credencial(%s)", (p,)).fetchone()[0] is not None]


def procesar_uno(pg: psycopg.Connection, http: httpx.Client, llaves: dict[str, tuple[str, str]],
                 solo: str | None = None) -> str | None:
    """Toma un trabajo y lo resuelve. Devuelve el resultado del intento, o None si no había trabajo.
    Con `solo`, el hilo de ese proveedor toma únicamente trabajos que ese proveedor puede hacer."""
    proveedores = [p for p in disponibles(pg) if solo is None or p == solo]
    if not proveedores:
        return None
    with pg.cursor(row_factory=dict_row) as cur:
        trabajo = cur.execute("SELECT * FROM ia.tomar_trabajo(%s, %s)", (TIPOS, proveedores)).fetchone()
    if trabajo is None:
        return None
    nombre = trabajo["proveedor"] or proveedores[0]
    proveedor = PROVEEDORES[nombre]
    alias = pg.execute("SELECT ia.elegir_credencial(%s)", (nombre,)).fetchone()[0]
    modelos = proveedor.modelos[trabajo["tipo"]]
    modelo = modelos[0]
    # La hora de inicio la da la base (el mismo reloj que pone la hora de fin del intento).
    iniciado = pg.execute("SELECT clock_timestamp()").fetchone()[0]
    resultado, salida, esperar, error, tokens = "ok", None, None, None, (None, None)
    try:
        for i, modelo in enumerate(modelos):
            try:
                respuesta = llamar(http, proveedor, llaves[alias][1], modelo, prompt(trabajo["version_prompt"]),
                                   json.dumps(trabajo["entrada"], ensure_ascii=False))
                break
            except ModeloSaturado:
                if i == len(modelos) - 1:
                    raise
        tokens = (respuesta.tokens_entrada, respuesta.tokens_salida)
        salida = validar(trabajo["tipo"], respuesta.texto, trabajo["entrada"])
    except LimiteAlcanzado as exc:
        resultado, esperar, error = "limite_alcanzado", exc.esperar, str(exc)
    except SalidaInvalida as exc:
        resultado, error = "salida_invalida", str(exc)
    except ErrorProveedor as exc:
        resultado, error = "error_proveedor", str(exc)
    pg.execute(
        "CALL ia.registrar_intento(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (trabajo["id"], alias, modelo, resultado, tokens[0], tokens[1], error,
         Jsonb(salida) if salida is not None else None, esperar, iniciado))
    registro.info("trabajo %s (%s) con %s/%s: %s", trabajo["id"], trabajo["tipo"], nombre, alias, resultado)
    return resultado


def trabajar(proveedor: str, llaves: dict[str, tuple[str, str]]) -> None:
    """Bucle de un proveedor: procesa mientras haya trabajo y espera el aviso de la cola (o 15 s)."""
    escucha = conectar_postgres("PG_URL_IA")
    escucha.execute("LISTEN trabajo_ia")
    with conectar_postgres("PG_URL_IA") as pg, httpx.Client() as http:
        while True:
            try:
                while procesar_uno(pg, http, llaves, solo=proveedor) is not None:
                    pass
            except psycopg.Error:
                registro.exception("hilo %s: error de base; se reintenta en la próxima vuelta", proveedor)
            for _ in escucha.notifies(timeout=15, stop_after=1):
                pass


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    with conectar_postgres("PG_URL_IA") as pg:
        llaves = sincronizar_cuentas(pg)
    registro.info("cuentas: %s", ", ".join(f"{a} ({p})" for a, (p, _) in llaves.items()))
    con_cuenta = [p for p in PREFERENCIA if any(prov == p for prov, _ in llaves.values())]
    hilos = [threading.Thread(target=trabajar, args=(p, llaves), name=f"ia-{p}", daemon=True) for p in con_cuenta]
    for hilo in hilos:
        hilo.start()
    registro.info("un hilo por proveedor: %s", ", ".join(con_cuenta))
    for hilo in hilos:
        hilo.join()


if __name__ == "__main__":
    main()
