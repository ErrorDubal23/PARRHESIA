"""Imagen de cada tema del día, buscada en Unsplash una sola vez (migración 0028).

La imagen acompaña al tema; no dice nada de él. Por eso:
  - nunca se busca con el título (los nombres propios traen cualquier cosa): reglas fijas convierten el tema
    en una búsqueda genérica (versión "categoria-1", migración 0030), con el filtro de contenido alto y en horizontal;
  - un tema con la misma etiqueta que uno anterior reutiliza esa imagen sin buscar otra vez;
  - se guarda la dirección (Unsplash pide enlazar sus imágenes, no copiarlas), el autor y los enlaces del
    crédito, y se avisa a Unsplash que la foto se usó (download_location), como piden sus condiciones;
  - si no hay llave o no hay resultado, se guarda la búsqueda sin imagen y la app muestra un fondo neutro.
La llave se lee de UNSPLASH_ACCESS_KEY y nunca se guarda en la base.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

registro = logging.getLogger("temas.imagenes")
API = "https://api.unsplash.com/search/photos"
UTM = "utm_source=parrhesia&utm_medium=referral"
VERSION = "categoria-1"

# Reglas fijas: raíz de palabra (sin tildes) -> búsqueda genérica en inglés (Unsplash busca mejor en inglés).
# Nunca se busca con el título: un nombre propio trae cualquier cosa, incluso la cara de otra persona real.
# Para temas de seguridad se muestra la ciudad, no violencia ni armas. El orden importa: gana la primera.
CATEGORIAS = [
    (("congres", "senad", "camara de representantes", "legislat"), "parliament building"),
    (("eleccion", "votacion", "registradur", "candidat"), "ballot box voting"),
    (("tormenta", "lluvia", "inundac", "aguacero", "clima", "ola invernal"), "storm clouds city"),
    (("incendi",), "forest smoke"),
    (("sismo", "temblor", "terremoto"), "city skyline dusk"),
    (("jep", "fiscal", "corte suprema", "corte constitucional", "tribunal", "justicia", "juez"), "courthouse columns"),
    (("salud", "hospital", "eps", "vacun", "medic"), "hospital corridor"),
    (("educac", "universid", "colegio", "estudiant", "icfes"), "university library"),
    (("inflac", "desempleo", "salario", "impuest", "tributari", "econom", "dolar", "peso"), "colombian pesos money"),
    (("metro", "transmilenio", "movilidad", "transito", "carretera", "via ", "vias "), "city traffic"),
    (("energia", "petrole", "mineri", "gas "), "power lines sunset"),
    (("futbol", "seleccion colombia", "deport"), "football stadium"),
    (("captur", "clan", "polic", "homicid", "ataque", "armad", "seguridad", "extorsi", "secuestr", "crimen",
      "disidenc", "violenc"), "city street night"),
]
CIUDADES = {"bogota": "Bogota", "medellin": "Medellin", "cali": "Cali", "barranquilla": "Barranquilla",
            "cartagena": "Cartagena", "bucaramanga": "Bucaramanga", "manizales": "Manizales", "pereira": "Pereira",
            "santa marta": "Santa Marta", "cucuta": "Cucuta", "pasto": "Pasto", "ibague": "Ibague",
            "villavicencio": "Villavicencio", "popayan": "Popayan", "quibdo": "Quibdo"}


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def consultas(titulo: str) -> list[str]:
    """Búsquedas de la más específica a la más general, sin nombres propios."""
    t = f" {_sin_tildes(titulo.lower())} "
    categoria = next((consulta for raices, consulta in CATEGORIAS if any(r in t for r in raices)), None)
    ciudad = next((nombre for clave, nombre in CIUDADES.items() if re.search(rf"\b{clave}\b", t)), None)
    opciones = []
    if categoria and ciudad:
        opciones.append(f"{ciudad} {categoria}")
    if categoria:
        opciones.append(categoria)
    if ciudad:
        opciones.append(f"{ciudad} Colombia")
    opciones.append("Colombia landscape")
    return list(dict.fromkeys(opciones))


def buscar(http: httpx.Client, llave: str, titulo: str) -> dict:
    for consulta in consultas(titulo):
        r = http.get(API, params={"query": consulta, "orientation": "landscape", "content_filter": "high",
                                  "per_page": 1}, headers={"Authorization": f"Client-ID {llave}", "Accept-Version": "v1"},
                     timeout=15)
        r.raise_for_status()
        resultados = r.json().get("results") or []
        if resultados:
            foto = resultados[0]
            # Condición de uso: avisar que la foto se mostró.
            http.get(foto["links"]["download_location"], headers={"Authorization": f"Client-ID {llave}"}, timeout=15)
            return {"consulta": consulta, "proveedor_id": foto["id"], "url": foto["urls"]["regular"],
                    "autor": foto["user"]["name"], "url_autor": f"{foto['user']['links']['html']}?{UTM}",
                    "url_foto": f"{foto['links']['html']}?{UTM}", "color": foto.get("color")}
    return {"consulta": " | ".join(consultas(titulo))}


def completar(pg: psycopg.Connection, http: httpx.Client) -> int:
    """Busca la imagen de los temas actuales que no la tienen. Devuelve cuántos temas quedaron resueltos."""
    llave = os.environ.get("UNSPLASH_ACCESS_KEY")
    with pg.cursor(row_factory=dict_row) as cur:
        pendientes = cur.execute("SELECT * FROM temas.temas_sin_imagen(%s)", (VERSION,)).fetchall()
    resueltos = 0
    for tema in pendientes:
        datos = tema["reutilizable"]
        if datos is None:
            if not llave:
                continue                     # sin llave no se busca ni se marca: se buscará cuando la haya
            try:
                datos = buscar(http, llave, tema["titulo"])
            except (httpx.HTTPError, KeyError, ValueError):
                registro.warning("imagen de %s: Unsplash no respondió; se intenta en la próxima vuelta", tema["etiqueta"])
                continue
        pg.execute("CALL temas.registrar_imagen_tema(%s, %s, %s)", (tema["tema_id"], VERSION, Jsonb(datos)))
        resueltos += 1
    return resueltos
