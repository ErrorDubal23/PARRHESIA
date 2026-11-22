"""Lee los RSS de los medios registrados (docs/diseno/06_temas_del_dia.md).

Solo título, resumen, enlace y fecha: el texto completo de los artículos no se
descarga en la v1. El XML se lee con defusedxml, porque viene de afuera.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx
from defusedxml import ElementTree

# Lista pública, de distintas líneas editoriales (aprobada el 21 nov 2026, abierta a cambios).
# Comprobados el 21 nov 2026: responden con artículos y su robots.txt permite leerlos.
# El Espectador (RSS vacío) y Blu Radio (sin RSS) quedan pendientes; GDELT es el respaldo.
MEDIOS = [
    ("El Tiempo", "https://www.eltiempo.com", "https://www.eltiempo.com/rss/colombia.xml"),
    ("Semana", "https://www.semana.com", "https://www.semana.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("La Silla Vacía", "https://www.lasillavacia.com", "https://www.lasillavacia.com/feed/"),
    ("Caracol Radio", "https://caracol.com.co", "https://caracol.com.co/arc/outboundfeeds/rss/?outputType=xml"),
    ("Portafolio", "https://www.portafolio.co", "https://www.portafolio.co/rss/economia.xml"),
    ("La República", "https://www.larepublica.co", "https://www.larepublica.co/rss/"),
    ("Infobae Colombia", "https://www.infobae.com/colombia", "https://www.infobae.com/arc/outboundfeeds/rss/category/colombia/?outputType=xml"),
    ("RTVC Noticias", "https://www.rtvcnoticias.com", "https://www.rtvcnoticias.com/rss.xml"),
]
AGENTE = "Mozilla/5.0 (compatible; lector-de-temas/1.0)"
ATOM = "{http://www.w3.org/2005/Atom}"


def texto_plano(valor: str | None, maximo: int = 1500) -> str | None:
    if not valor:
        return None
    limpio = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", valor))).strip()
    return limpio[:maximo] or None


def _fecha(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        fecha = parsedate_to_datetime(valor)          # RSS: "Fri, 21 Nov 2026 14:30:00 -0500"
    except (TypeError, ValueError):
        try:
            fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))  # Atom: ISO 8601
        except ValueError:
            return None
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)


def leer_rss(contenido: bytes) -> list[dict]:
    """Artículos de un RSS 2.0 o de un Atom: url, título, resumen y fecha. Los incompletos se descartan."""
    raiz = ElementTree.fromstring(contenido)
    articulos = []
    for item in raiz.iter("item"):
        articulos.append({"url": (item.findtext("link") or "").strip(), "titulo": texto_plano(item.findtext("title"), 300),
                          "resumen": texto_plano(item.findtext("description")), "publicado_en": _fecha(item.findtext("pubDate"))})
    for entrada in raiz.iter(f"{ATOM}entry"):
        enlace = entrada.find(f"{ATOM}link")
        articulos.append({"url": (enlace.get("href") if enlace is not None else "").strip(),
                          "titulo": texto_plano(entrada.findtext(f"{ATOM}title"), 300),
                          "resumen": texto_plano(entrada.findtext(f"{ATOM}summary")),
                          "publicado_en": _fecha(entrada.findtext(f"{ATOM}published") or entrada.findtext(f"{ATOM}updated"))})
    return [{**a, "publicado_en": a["publicado_en"].isoformat(), "texto": None} for a in articulos
            if a["url"].startswith("http") and a["titulo"] and a["publicado_en"]]


def descargar(http: httpx.Client, url_canal: str) -> list[dict]:
    r = http.get(url_canal, headers={"User-Agent": AGENTE}, follow_redirects=True, timeout=30)
    r.raise_for_status()
    return leer_rss(r.content)
