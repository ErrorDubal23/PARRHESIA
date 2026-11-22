"""Análisis de enlaces externos (decisión 29): de una URL o un texto pegado a fragmentos cortos con cifras.

El cuerpo de la página vive solo en memoria mientras se corta en fragmentos. A la base llegan los
metadatos que la página DECLARA (título, sitio, autor, fecha: se muestran como "según la página") y
los fragmentos candidatos; la base decide cuáles se guardan (filtro previo) en
verificacion.registrar_enlace. Nada de esto usa IA: la IA solo lee después cada fragmento guardado.

Cuidado con lo que se descarga (SSRF): solo http(s), nunca direcciones privadas, locales o internas
(tampoco después de una redirección), como máximo 2 MB de HTML en 15 s, y respetando robots.txt.
Las redes que bloquean el acceso automático no se intentan: se pide el texto.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

AGENTE = "ParrhesiaVerificacion/1.0 (+analisis de enlaces; solo lee lo que pide una persona)"
MAXIMO_BYTES = 2 * 1024 * 1024
TIEMPO = 15
REDIRECCIONES = 3
# Exigen sesión o bloquean la lectura automática: leerlas sería scraping. Se pide el texto.
REDES_CERRADAS = ("x.com", "twitter.com", "facebook.com", "fb.watch", "instagram.com", "tiktok.com",
                  "threads.net", "linkedin.com", "whatsapp.com")


class EnlaceNoLeido(Exception):
    """No se lee la página; el motivo es un código estable y el mensaje va a la persona."""

    def __init__(self, codigo: str, mensaje: str) -> None:
        super().__init__(mensaje)
        self.codigo, self.mensaje = codigo, mensaje


@dataclass
class Lectura:
    url: str | None
    metadatos: dict = field(default_factory=dict)
    candidatos: list[str] = field(default_factory=list)
    huella: str = ""
    fecha_referencia: date = field(default_factory=date.today)


# --- URL y destino --------------------------------------------------------------------------------

def normalizar(url: str) -> str:
    """Esquema y dominio en minúsculas, sin fragmento (#...). El resto se respeta tal cual."""
    partes = urlsplit(url.strip())
    if partes.scheme.lower() not in ("http", "https") or not partes.hostname:
        raise EnlaceNoLeido("url_invalida", "El enlace debe empezar por http:// o https://.")
    if partes.username or partes.password:
        raise EnlaceNoLeido("url_invalida", "El enlace no puede llevar usuario ni contraseña.")
    anfitrion = partes.hostname.lower() + (f":{partes.port}" if partes.port else "")
    return urlunsplit((partes.scheme.lower(), anfitrion, partes.path or "/", partes.query, ""))


def red_cerrada(url: str) -> bool:
    anfitrion = (urlsplit(url).hostname or "").lower()
    return any(anfitrion == d or anfitrion.endswith("." + d) for d in REDES_CERRADAS)


def _resolver(anfitrion: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(anfitrion, None)]


def destino_publico(url: str, resolver=_resolver) -> None:
    """Rechaza cualquier destino que no sea una dirección pública de internet (SSRF)."""
    anfitrion = urlsplit(url).hostname or ""
    try:
        direcciones = resolver(anfitrion)
    except OSError:
        raise EnlaceNoLeido("ilegible", "No se encontró ese sitio.")
    if not direcciones:
        raise EnlaceNoLeido("ilegible", "No se encontró ese sitio.")
    for d in direcciones:
        ip = ipaddress.ip_address(d.split("%")[0])
        if not ip.is_global or ip.is_multicast:
            raise EnlaceNoLeido("destino_no_permitido", "Ese enlace apunta a una dirección interna y no se lee.")


# --- Descarga ------------------------------------------------------------------------------------

def _permitido_por_robots(http: httpx.Client, url: str) -> bool:
    partes = urlsplit(url)
    robots = urlunsplit((partes.scheme, partes.netloc, "/robots.txt", "", ""))
    try:
        r = http.get(robots, headers={"User-Agent": AGENTE}, timeout=TIEMPO, follow_redirects=False)
    except httpx.HTTPError:
        return True                       # sin robots.txt alcanzable no hay prohibición declarada
    if r.status_code in (401, 403):
        return False
    if r.status_code >= 400:
        return True
    lector = RobotFileParser()
    lector.parse(r.text[:100_000].splitlines())
    return lector.can_fetch(AGENTE, url)


def descargar(http: httpx.Client, url: str, resolver=_resolver) -> tuple[str, str]:
    """Devuelve (url final, html). Sigue hasta 3 redirecciones revisando cada destino."""
    actual = normalizar(url)
    for _ in range(REDIRECCIONES + 1):
        if red_cerrada(actual):
            raise EnlaceNoLeido("red_cerrada", "Esa red no permite leer sus publicaciones automáticamente. "
                                               "Copia y pega el texto de la publicación.")
        destino_publico(actual, resolver)
        if not _permitido_por_robots(http, actual):
            raise EnlaceNoLeido("robots", "Ese sitio no permite la lectura automática. Copia y pega el texto.")
        try:
            with http.stream("GET", actual, headers={"User-Agent": AGENTE}, timeout=TIEMPO,
                             follow_redirects=False) as r:
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    actual = normalizar(urljoin(actual, r.headers["location"]))
                    continue
                if r.status_code != 200:
                    raise EnlaceNoLeido("ilegible", f"El sitio respondió con un error ({r.status_code}).")
                tipo = r.headers.get("content-type", "")
                if "html" not in tipo:
                    raise EnlaceNoLeido("ilegible", "Ese enlace no es una página web (por ahora solo se leen páginas).")
                cuerpo = b""
                for trozo in r.iter_bytes():
                    cuerpo += trozo
                    if len(cuerpo) > MAXIMO_BYTES:
                        raise EnlaceNoLeido("ilegible", "La página es demasiado grande para leerla.")
                return actual, cuerpo.decode(r.encoding or "utf-8", errors="replace")
        except httpx.HTTPError:
            raise EnlaceNoLeido("ilegible", "No se pudo leer la página. Puedes pegar el texto.")
    raise EnlaceNoLeido("ilegible", "El enlace redirige demasiadas veces.")


# --- Lectura del HTML (en memoria) ----------------------------------------------------------------

class _Lector(HTMLParser):
    BLOQUES = {"p", "li", "h1", "h2", "h3", "h4", "blockquote", "td"}
    # figcaption: los pies de foto repiten el tema con años y créditos, no son lo que dice la nota.
    IGNORAR = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "figcaption"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.titulo = ""
        self.parrafos: list[str] = []
        self._actual: list[str] | None = None
        self._enlace = 0                      # profundidad dentro de <a>
        self._en_enlace = 0                   # caracteres del bloque que son texto de un enlace
        self._ignorar = 0
        self._en_titulo = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            clave = (a.get("property") or a.get("name") or "").lower()
            if clave and a.get("content") and clave not in self.meta:
                self.meta[clave] = a["content"].strip()
        elif tag == "title":
            self._en_titulo = True
        elif tag in self.IGNORAR:
            self._ignorar += 1
        elif tag in self.BLOQUES and not self._ignorar:
            self._cerrar()
            self._actual = []
        elif tag == "br" and self._actual is not None:
            self._actual.append(" ")
        elif tag == "a":
            self._enlace += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._en_titulo = False
        elif tag in self.IGNORAR and self._ignorar:
            self._ignorar -= 1
        elif tag in self.BLOQUES:
            self._cerrar()
        elif tag == "a" and self._enlace:
            self._enlace -= 1

    def handle_data(self, data):
        if self._en_titulo:
            self.titulo += data
        elif self._actual is not None and not self._ignorar:
            self._actual.append(data)
            if self._enlace:
                self._en_enlace += len(data.strip())

    def _cerrar(self):
        if self._actual:
            texto = re.sub(r"\s+", " ", "".join(self._actual)).strip()
            # Un bloque que es casi todo un enlace es el título de OTRA nota ("noticias relacionadas"), no esta.
            if texto and self._en_enlace < 0.8 * len(texto.replace(" ", "")):
                self.parrafos.append(texto)
        self._actual = None
        self._en_enlace = 0

    def close(self):
        super().close()
        self._cerrar()


def leer_html(html: str) -> tuple[dict, list[str]]:
    lector = _Lector()
    lector.feed(html)
    lector.close()
    m = lector.meta
    metadatos = {
        "titulo": m.get("og:title") or re.sub(r"\s+", " ", lector.titulo).strip() or None,
        "sitio": m.get("og:site_name"),
        "autor": m.get("author") or m.get("article:author"),
        "publicado": m.get("article:published_time") or m.get("date"),
    }
    return {k: v for k, v in metadatos.items() if v}, lector.parrafos


# --- Fragmentos ----------------------------------------------------------------------------------

ORACION = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÑ¿¡\"“])")


def fragmentos(parrafos: list[str], maximo: int = 600) -> list[str]:
    """Oraciones con algún dígito, agrupadas hasta 600 caracteres dentro de su párrafo.

    Es solo un corte: la base decide qué candidatos pasan el filtro previo y cuáles se guardan.
    """
    candidatos = []
    for parrafo in parrafos:
        actual = ""
        for oracion in ORACION.split(parrafo):
            if not re.search(r"\d", oracion) or len(oracion) > maximo:
                if actual:
                    candidatos.append(actual)
                    actual = ""
                continue
            if actual and len(actual) + 1 + len(oracion) > maximo:
                candidatos.append(actual)
                actual = oracion
            else:
                actual = f"{actual} {oracion}".strip()
        if actual:
            candidatos.append(actual)
    return candidatos


def _fecha(publicado: str | None) -> date:
    if publicado:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", publicado)
        if m:
            try:
                return date(int(m[1]), int(m[2]), int(m[3]))
            except ValueError:
                pass
    return date.today()


def huella(texto: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", texto).strip().encode()).hexdigest()


def leer_enlace(http: httpx.Client, url: str, resolver=_resolver) -> Lectura:
    final, html = descargar(http, url, resolver)
    metadatos, parrafos = leer_html(html)
    return Lectura(url=final, metadatos=metadatos, candidatos=fragmentos(parrafos),
                   huella=huella("\n".join(parrafos)), fecha_referencia=_fecha(metadatos.get("publicado")))


def leer_texto(texto: str) -> Lectura:
    parrafos = [p.strip() for p in re.split(r"\n\s*\n|\n", texto) if p.strip()]
    return Lectura(url=None, candidatos=fragmentos(parrafos), huella=huella(texto))
