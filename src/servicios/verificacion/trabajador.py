"""Trabajador de verificación: de un texto publicado a una verificación con evidencia oficial.

    uv run python -m servicios.verificacion.trabajador

Avanza por etapas guardadas en la base, así que si se reinicia retoma donde iba
(encolar un trabajo de IA es idempotente: devuelve el mismo trabajo):

  1. Textos nuevos (outbox de social y temas): filtro previo sin IA; si pasa, dos
     lecturas en proveedores distintos (decisión 26). Cuando las dos terminan, la base
     las compara y guarda las afirmaciones (o las deja en revisión si difieren).
  2. Afirmaciones extraídas sin verificar: el motor de reglas decide la conclusión con
     el dato oficial; la IA redacta la explicación, que pasa por el validador de cifras.
     Si la IA falla, se usa la explicación armada por reglas. La base revisa otra vez
     las cifras al confirmar (trigger diferido).
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal

import httpx

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from servicios.comun.configuracion import conectar_postgres
from servicios.ia.formatos import cifras
from servicios.verificacion import motor

registro = logging.getLogger("verificacion")
CONSUMIDOR = "verificacion"
VERSION_EXTRACCION = "extraer_afirmaciones.v2"
VERSION_REDACCION = "redactar_explicacion.v2"
VERSION_MOTOR = "motor-1"
QUE_SIGNIFICA = {
    "se_sostiene": "La cifra coincide con el dato oficial.",
    "se_debilita": "El dato oficial no respalda la cifra tal como se dijo.",
    "se_invierte": "El dato oficial va en la dirección contraria a la que dice el texto.",
    "sin_dato_comparable": "No hay un dato oficial registrado con el que se pueda comparar.",
    "en_revision": "Todavía no hay conclusión: una persona del equipo revisa la cifra.",
}
FACT_CHECK = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
PRIMER_LECTOR = "groq"
# Segundo lector y juez: de otro fabricante. La base elige el primero de esta lista con una cuenta habilitada
# (ia.primer_proveedor_habilitado, migración 0034): Gemini es mucho más rápido que el plan gratuito de OpenRouter.
SEGUNDOS_LECTORES = ["gemini", "openrouter"]


def _segundo_lector(pg) -> str:
    return pg.execute("SELECT ia.primer_proveedor_habilitado(%s)", (SEGUNDOS_LECTORES,)).fetchone()[0] or "openrouter"
OUTBOX = (("social", ["publicacion_creada", "declaracion_creada"]), ("temas", ["declaracion_reportada_creada"]),
          ("verificacion", ["fragmento_enlace_creado"]))
ORIGEN = {"publicacion_creada": "publicacion", "declaracion_creada": "declaracion",
          "declaracion_reportada_creada": "declaracion_reportada", "fragmento_enlace_creado": "fragmento_enlace"}


class DatosEnLaBase:
    """Los datos oficiales, leídos solo con las funciones autorizadas de oficial."""

    def __init__(self, pg: psycopg.Connection) -> None:
        self.pg = pg

    def candidatas(self, indicador, variante):
        with self.pg.cursor(row_factory=dict_row) as cur:
            return cur.execute("SELECT * FROM oficial.series_candidatas(%s, %s)", (indicador, variante)).fetchall()

    def valor(self, codigo_serie, periodo):
        with self.pg.cursor(row_factory=dict_row) as cur:
            fila = cur.execute("SELECT observacion_id::text, valor, marcas FROM oficial.observacion_en(%s, %s, 'national')",
                               (codigo_serie, periodo)).fetchone()
        return fila

    def notas(self, codigo_serie, periodo):
        with self.pg.cursor(row_factory=dict_row) as cur:
            return cur.execute("SELECT * FROM oficial.notas_en(%s, %s)", (codigo_serie, periodo)).fetchall()


def _texto(pg, origen: str, origen_id: str) -> str | None:
    if origen == "declaracion_reportada":
        return pg.execute("SELECT temas.texto_para_verificar(%s)", (origen_id,)).fetchone()[0]
    if origen == "fragmento_enlace":
        return pg.execute("SELECT verificacion.texto_fragmento(%s)", (origen_id,)).fetchone()[0]
    return pg.execute("SELECT social.texto_para_verificar(%s, %s)", (origen, origen_id)).fetchone()[0]


def _encolar(pg, tipo, version, entrada, proveedor) -> str:
    return str(pg.execute("CALL ia.encolar_trabajo(%s, %s, %s, %s, NULL, NULL)",
                          (tipo, version, Jsonb(entrada), proveedor)).fetchone()[0])


def _resultado(pg, trabajo_id) -> tuple[str, dict | None]:
    return pg.execute("SELECT estado, salida FROM ia.resultado_trabajo(%s)", (trabajo_id,)).fetchone()


def procesar_textos(pg: psycopg.Connection) -> int:
    """Etapa 1. Devuelve cuántos textos quedaron resueltos (y marcados como entregados)."""
    resueltos = 0
    for esquema, tipos in OUTBOX:
        with pg.cursor(row_factory=dict_row) as cur:
            eventos = cur.execute(f"SELECT id, tipo_evento, datos FROM {esquema}.eventos_pendientes(%s, %s, 100)",
                                  (CONSUMIDOR, tipos)).fetchall()
        for evento in eventos:
            origen, origen_id = ORIGEN[evento["tipo_evento"]], evento["datos"]["id"]
            try:
                listo = _resolver_texto(pg, origen, origen_id, evento["datos"])
            except psycopg.Error:
                # Un texto que la base rechaza (por ejemplo, una lectura que no cumple una restricción) no
                # puede detener la cola: queda 'fallido', es decir, en revisión humana, y se sigue.
                registro.exception("%s %s: la base rechazó lo leído; queda en revisión humana", origen, origen_id)
                pg.execute("CALL verificacion.registrar_procesamiento(%s, %s, 'fallido')", (origen, origen_id))
                listo = True
            if listo:
                pg.execute(f"CALL {esquema}.marcar_entregados(%s, %s)", (CONSUMIDOR, [evento["id"]]))
                resueltos += 1
    return resueltos


def _resolver_texto(pg, origen: str, origen_id: str, datos: dict) -> bool:
    texto = _texto(pg, origen, origen_id)
    if texto is None:                       # retirada antes de verificarse: no hay nada que revisar
        return True
    if not pg.execute("SELECT verificacion.requiere_extraccion(%s)", (texto,)).fetchone()[0]:
        pg.execute("CALL verificacion.registrar_procesamiento(%s, %s, 'sin_cifras')", (origen, origen_id))
        return True                         # opinión sin cifras: no se gasta IA
    fecha = str(datos.get("creado_en") or datos.get("dicha_el") or "")[:10]
    entrada = {"texto": texto, "fecha": fecha}
    trabajos = [_encolar(pg, "extraer_afirmaciones", VERSION_EXTRACCION, entrada, p)
                for p in (PRIMER_LECTOR, _segundo_lector(pg))]
    resultados = [_resultado(pg, t) for t in trabajos]
    if any(estado == "fallido" for estado, _ in resultados):
        pg.execute("CALL verificacion.registrar_procesamiento(%s, %s, 'fallido')", (origen, origen_id))
        return True
    if not all(estado == "terminado" for estado, _ in resultados):
        return False                        # todavía esperando a la IA: se vuelve a mirar en la próxima vuelta
    guardadas, consenso = pg.execute(
        "CALL verificacion.registrar_afirmaciones_consenso(%s, %s, %s, %s, %s, %s, NULL, NULL)",
        (origen, origen_id, trabajos[0], trabajos[1], Jsonb(resultados[0][1]["afirmaciones"]),
         Jsonb(resultados[1][1]["afirmaciones"]))).fetchone()
    registro.info("%s %s: %d afirmaciones, lecturas %s", origen, origen_id, guardadas, consenso)
    return True


def procesar_afirmaciones(pg: psycopg.Connection) -> int:
    """Etapa 2. Devuelve cuántas afirmaciones quedaron verificadas."""
    with pg.cursor(row_factory=dict_row) as cur:
        pendientes = cur.execute(
            "SELECT * FROM verificacion.afirmacion a WHERE a.estado = 'extraida'"
            " AND NOT EXISTS (SELECT 1 FROM verificacion.verificacion v WHERE v.afirmacion_id = a.id)"
            " ORDER BY a.creado_en LIMIT 50").fetchall()
    datos = DatosEnLaBase(pg)
    verificadas = 0
    for fila in pendientes:
        af = motor.Afirmacion(fila["codigo_indicador"], fila["variante"], fila["periodo_desde"], fila["periodo_hasta"],
                              fila["territorio"], fila["valor_dicho"], fila["unidad_dicha"], fila["comparacion"],
                              fila["direccion"], fila["texto_citado"])
        try:
            veredicto = motor.verificar(af, datos)
            explicacion = _explicacion(pg, af, veredicto)
            if explicacion is None:
                continue                    # la IA todavía está redactando
            pg.execute(
                "CALL verificacion.registrar_verificacion(%s, %s, %s, %s, true, %s, %s, %s, %s, NULL)",
                (fila["id"], veredicto.codigo_serie, veredicto.conclusion, explicacion, VERSION_MOTOR,
                 Jsonb([{"observacion_id": o, "rol": r} for o, r in dict.fromkeys(veredicto.evidencia)]),
                 Jsonb([{"codigo": c, "resultado": r, "detalle": d} for c, (r, d) in veredicto.pruebas.items()]),
                 veredicto.motivo_codigo))
        except psycopg.Error:
            # La base rechazó la verificación (un validador o una restricción): no se publica nada y la
            # afirmación pasa a revisión humana, sin detener a las demás.
            registro.exception("afirmación %s: la base rechazó la verificación; queda en revisión humana", fila["id"])
            pg.execute("UPDATE verificacion.afirmacion SET estado = 'requiere_revision' WHERE id = %s", (fila["id"],))
            continue
        verificadas += 1
        registro.info("afirmación %s: %s", fila["id"], veredicto.conclusion)
    return verificadas


def _explicacion(pg, af: motor.Afirmacion, v: motor.Veredicto) -> str | None:
    respaldo = motor.explicacion_de_respaldo(af, v)
    if v.conclusion == "sin_dato_comparable":
        return respaldo
    valores = [Decimal(v.oficial["valor"])] + [Decimal(r["valor"]) for r in v.referencias]
    permitidas = ({Decimal(af.valor_dicho).normalize()}
                  | {motor.para_mostrar(x, d).normalize() for x in valores for d in (0, 1, 2)}
                  | {x.normalize() for x in valores}
                  | cifras(" ".join([v.oficial["periodo"]] + [r["periodo"] for r in v.referencias])))
    entrada = {"texto_citado": af.texto_citado, "valor_dicho": str(af.valor_dicho), "conclusion": v.conclusion,
               "oficial": {"serie": v.serie["nombre"], "fuente": v.serie["fuente"], "periodo": v.oficial["periodo"],
                           "valor_para_mostrar": str(motor.para_mostrar(v.oficial["valor"], v.precision))},
               "brechas": v.brechas, "explicacion_de_referencia": respaldo,
               "cifras_permitidas": sorted({str(c) for c in permitidas | cifras(respaldo)})}
    estado, salida = _resultado(pg, _encolar(pg, "redactar_explicacion", VERSION_REDACCION, entrada, None))
    if estado == "terminado":
        return salida["explicacion"]
    if estado == "fallido":
        return respaldo
    return None


# --- Etapa 3 · Guías de lectura (decisión 34) --------------------------------------------------------

def _ficha(pg, afirmacion_id) -> dict:
    """Lo que decidieron las reglas, sin cifras: la IA solo lo redacta; nunca decide nada."""
    with pg.cursor(row_factory=dict_row) as cur:
        a = cur.execute("SELECT texto_citado, estado FROM verificacion.afirmacion WHERE id = %s", (afirmacion_id,)).fetchone()
        v = cur.execute("SELECT conclusion FROM verificacion.verificacion_vigente(%s)", (afirmacion_id,)).fetchone()
        guia = cur.execute("SELECT verificacion.guia_de(%s) AS g", (afirmacion_id,)).fetchone()["g"]
    conclusion = "en_revision" if a["estado"] == "requiere_revision" else (v["conclusion"] if v else None)
    return {"frase_citada": a["texto_citado"], "conclusion": conclusion, "que_significa": QUE_SIGNIFICA.get(conclusion),
            "motivo": guia["motivo"],
            "consejos": [{"para_entenderlo": c["para_entenderlo"], "pasos": c["pasos"]} for c in guia["consejos"]],
            "donde_consultar": [f["nombre"] for f in guia["fuentes"]]}


def _versiones(pg) -> tuple[str, str]:
    """La versión de cada prompt que se publica la fija la base (verificacion.prompt_vigente, migración 0033)."""
    vigentes = dict(pg.execute("SELECT tipo, version FROM verificacion.prompt_vigente").fetchall())
    return vigentes["redactar_guia"], vigentes["juzgar_neutralidad"]


def procesar_guias(pg: psycopg.Connection) -> int:
    """Redacta la guía con IA y la somete a un juez de otro proveedor. Solo se publica si es neutral y no
    agrega hechos; mientras tanto (o si falla) la app muestra la guía armada por reglas."""
    hechas = 0
    version_guia, version_juez = _versiones(pg)
    ids = [r[0] for r in pg.execute("SELECT verificacion.afirmaciones_sin_guia(%s, 50)", (version_guia,)).fetchall()]
    for afirmacion_id in ids:
        ficha = _ficha(pg, afirmacion_id)
        redaccion = _encolar(pg, "redactar_guia", version_guia, ficha, "groq")
        estado, salida = _resultado(pg, redaccion)
        if estado != "terminado":
            continue                        # todavía redactando, o falló: queda la guía por reglas
        juez = _encolar(pg, "juzgar_neutralidad", version_juez, {"guia": salida["guia"], "ficha": ficha},
                       _segundo_lector(pg))
        estado_juez, veredicto = _resultado(pg, juez)
        if estado_juez not in ("terminado", "fallido"):
            continue                        # el juez aún no responde (por ejemplo, sin cupo): se espera
        neutral = (veredicto["neutral"] and not veredicto["agrega_hechos"]) if estado_juez == "terminado" else None
        try:
            pg.execute("INSERT INTO verificacion.guia_redactada (afirmacion_id, version_prompt, texto, trabajo_ia_id,"
                       " trabajo_juez_id, neutral, motivo_juez) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                       " ON CONFLICT DO NOTHING",
                       (afirmacion_id, version_guia, salida["guia"], redaccion,
                        juez if neutral is not None else None, neutral, (veredicto or {}).get("motivo")))
            hechas += 1
        except psycopg.Error:
            registro.exception("guía de %s: la base la rechazó; queda la guía por reglas", afirmacion_id)
    return hechas


def procesar_otros_medios(pg: psycopg.Connection, http: httpx.Client) -> int:
    """Verificaciones relacionadas de otros medios (Google Fact Check Tools), sin su calificación."""
    llave = os.environ.get("GOOGLE_FACTCHECK_KEY")
    if not llave:
        return 0
    pendientes = pg.execute(
        "SELECT a.id, a.texto_citado FROM verificacion.afirmacion a"
        " WHERE a.estado IN ('verificada', 'no_verificable', 'requiere_revision')"
        " AND NOT EXISTS (SELECT 1 FROM verificacion.consulta_externa c WHERE c.afirmacion_id = a.id)"
        " ORDER BY a.creado_en DESC LIMIT 10").fetchall()
    for afirmacion_id, cita in pendientes:
        try:
            r = http.get(FACT_CHECK, params={"query": cita, "languageCode": "es", "pageSize": 3, "key": llave}, timeout=15)
            r.raise_for_status()
        except httpx.HTTPError:
            registro.warning("otros medios: Google Fact Check no respondió; se intenta después")
            return 0
        resultados = []
        for reclamo in r.json().get("claims", [])[:3]:
            revision = (reclamo.get("claimReview") or [{}])[0]
            if revision.get("url", "").startswith("https://") and revision.get("title"):
                # textualRating se descarta a propósito: Parrhesia no dice verdadero o falso.
                resultados.append({"medio": (revision.get("publisher") or {}).get("name") or "Otro medio",
                                   "titulo": revision["title"][:300], "url": revision["url"],
                                   "publicada_en": (revision.get("reviewDate") or "")[:10] or None})
        pg.execute("CALL verificacion.registrar_consulta_externa(%s, %s)", (afirmacion_id, Jsonb(resultados)))
    return len(pendientes)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    escucha = conectar_postgres("PG_URL_VERIFICACION")
    escucha.execute("LISTEN evento_salida")
    with conectar_postgres("PG_URL_VERIFICACION") as pg, httpx.Client() as http:
        while True:
            procesar_textos(pg)
            procesar_afirmaciones(pg)
            procesar_guias(pg)
            procesar_otros_medios(pg, http)
            for _ in escucha.notifies(timeout=5, stop_after=1):
                pass


if __name__ == "__main__":
    main()
