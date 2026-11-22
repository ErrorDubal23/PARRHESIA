"""Genera los diagramas MER (notación de Chen) y MR del proyecto en draw.io, y los exporta a PNG.

    uv run python diagramas/generar_diagramas.py

Los MR se leen de la base real (DATABASE_URL): columnas, tipos, llaves y
restricciones salen de PostgreSQL, así que el diagrama siempre coincide con lo
implementado. Los MER son el modelo conceptual y se definen aquí a mano.
Estilo: el de los diagramas del proyecto de biblioteca (colores, etiquetas, notas).
"""

from __future__ import annotations

import html
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
DRAWIO = Path("/Applications/draw.io.app/Contents/MacOS/draw.io")

# Colores (los mismos del proyecto de biblioteca)
AZUL, AZUL_CLARO = "#1F3B6F", "#DCE8FA"
AMARILLO, AMARILLO_BORDE = "#FFE7A8", "#B8860B"
VERDE, VERDE_BORDE = "#EAF5EA", "#3C8A3C"
ROJO = "#B0002A"
NOTA, NOTA_BORDE = "#FFF6DD", "#C5A56A"
ETIQUETA_PK, ETIQUETA_FK, ETIQUETA_UQ, ETIQUETA_CK, GRIS = "#B07D00", "#1F5FA8", "#2E6B4F", "#8F1D2C", "#666666"


def esc(texto: str) -> str:
    return html.escape(texto, quote=True)


class Lienzo:
    """Arma el XML de un diagrama de draw.io."""

    def __init__(self, nombre: str) -> None:
        self.nombre = nombre
        self.celdas: list[str] = []
        self.n = 1

    def nuevo_id(self) -> str:
        self.n += 1
        return f"c{self.n}"

    def vertice(self, valor: str, estilo: str, x: float, y: float, ancho: float, alto: float, padre: str = "1",
                id_: str | None = None) -> str:
        id_ = id_ or self.nuevo_id()
        self.celdas.append(
            f'<mxCell id="{id_}" value="{esc(valor)}" style="{estilo}" vertex="1" parent="{padre}">'
            f'<mxGeometry x="{x:.0f}" y="{y:.0f}" width="{ancho:.0f}" height="{alto:.0f}" as="geometry" /></mxCell>'
        )
        return id_

    def arista(self, origen: str, destino: str, estilo: str, puntos: list[tuple[float, float]] | None = None) -> str:
        id_ = self.nuevo_id()
        geo = '<mxGeometry relative="1" as="geometry">'
        if puntos:
            geo += "<Array as=\"points\">" + "".join(f'<mxPoint x="{x:.0f}" y="{y:.0f}" />' for x, y in puntos) + "</Array>"
        geo += "</mxGeometry>"
        self.celdas.append(
            f'<mxCell id="{id_}" style="{estilo}" edge="1" parent="1" source="{origen}" target="{destino}">{geo}</mxCell>'
        )
        return id_

    def xml(self) -> str:
        return ('<mxfile><diagram name="' + esc(self.nombre) + '"><mxGraphModel><root>'
                '<mxCell id="0" /><mxCell id="1" parent="0" />' + "".join(self.celdas)
                + "</root></mxGraphModel></diagram></mxfile>")


def nota(l: Lienzo, texto_html: str, x: float, y: float, ancho: float, lineas: int, amarilla: bool = True) -> float:
    alto = 26 + 15 * lineas
    estilo = (f"shape=note;whiteSpace=wrap;html=1;size=14;align=left;verticalAlign=top;spacing=10;fontSize=11;"
              f"fillColor={NOTA};strokeColor={NOTA_BORDE};") if amarilla else (
              "text;html=1;whiteSpace=wrap;align=left;verticalAlign=top;spacing=10;fontSize=11;"
              "fillColor=#FFFFFF;strokeColor=#BBBBBB;")
    l.vertice(texto_html, estilo, x, y, ancho, alto)
    return alto


# =============================================================================
# MER · notación de Chen
# =============================================================================

@dataclass
class Atributo:
    nombre: str
    clave: bool = False          # identificador (subrayado)
    parcial: bool = False        # clave parcial de una entidad débil (subrayado punteado)
    derivado: bool = False       # se calcula (elipse punteada)
    multivaluado: bool = False   # varios valores (doble elipse)


@dataclass
class Entidad:
    nombre: str
    col: float
    fila: float
    atributos: list[Atributo] = field(default_factory=list)
    debil: bool = False          # entidad débil (doble rectángulo)
    referencia: bool = False     # detallada en otro MER (borde punteado)


@dataclass
class Relacion:
    nombre: str
    a: str
    card_a: str
    b: str
    card_b: str
    atributos: list[str] = field(default_factory=list)
    identificadora: bool = False   # relación de una entidad débil (doble rombo)
    desplazamiento: float = 0      # para separar relaciones entre el mismo par
    propia: str = ""               # relación de una entidad consigo misma: "abajo", "arriba", "izquierda", "derecha"


def atributos(*nombres: str) -> list[Atributo]:
    """'*id' clave, '~numero' clave parcial, '(total)' derivado, '{marcas}' multivaluado."""
    lista = []
    for n in nombres:
        if n.startswith("*"):
            lista.append(Atributo(n[1:], clave=True))
        elif n.startswith("~"):
            lista.append(Atributo(n[1:], parcial=True))
        elif n.startswith("("):
            lista.append(Atributo(n[1:-1], derivado=True))
        elif n.startswith("{"):
            lista.append(Atributo(n[1:-1], multivaluado=True))
        else:
            lista.append(Atributo(n))
    return lista


CELDA_X, CELDA_Y, ORIGEN_X, ORIGEN_Y = 660, 540, 340, 300
ENT_W, ENT_H, ROMBO_W, ROMBO_H = 170, 46, 130, 64


def ancho_entidad(e: Entidad) -> float:
    return max(ENT_W, 10.5 * len(e.nombre) + 34)


def centro(e: Entidad) -> tuple[float, float]:
    return ORIGEN_X + e.col * CELDA_X, ORIGEN_Y + e.fila * CELDA_Y


def borde(cx: float, cy: float, ancho: float, alto: float, hacia: tuple[float, float]) -> tuple[float, float]:
    """Punto del borde de un rectángulo en la dirección de otro punto."""
    dx, dy = hacia[0] - cx, hacia[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    t = min((ancho / 2) / abs(dx) if dx else math.inf, (alto / 2) / abs(dy) if dy else math.inf)
    return cx + dx * t, cy + dy * t


def dibujar_mer(nombre: str, titulo: str, entidades: list[Entidad], relaciones: list[Relacion],
                reglas: list[str]) -> Lienzo:
    l = Lienzo(nombre)
    por_nombre = {e.nombre: e for e in entidades}
    ids: dict[str, str] = {}
    angulos: dict[str, list[float]] = {e.nombre: [] for e in entidades}

    l.vertice(f"<b>{esc(titulo)}</b>", f"text;html=1;align=left;verticalAlign=middle;fontSize=20;fontColor={AZUL};",
              40, 20, 1400, 40)

    # Entidades
    for e in entidades:
        cx, cy = centro(e)
        estilo = (f"rounded=0;whiteSpace=wrap;html=1;fillColor={AZUL_CLARO};strokeColor={AZUL};strokeWidth=2;"
                  "fontStyle=1;fontSize=14;")
        if e.debil:
            estilo = estilo.replace("rounded=0;", "shape=ext;double=1;rounded=0;")
        if e.referencia:
            estilo += "dashed=1;fillColor=#F2F5FA;"
        w = ancho_entidad(e)
        ids[e.nombre] = l.vertice(e.nombre, estilo, cx - w / 2, cy - ENT_H / 2, w, ENT_H)

    # Relaciones
    linea = "endArrow=none;html=1;strokeColor=#555555;"
    for r in relaciones:
        ea, eb = por_nombre[r.a], por_nombre[r.b]
        (ax, ay), (bx, by) = centro(ea), centro(eb)
        if r.propia:
            dx, dy = {"abajo": (0, 1), "arriba": (0, -1), "derecha": (1, 0), "izquierda": (-1, 0)}[r.propia]
            mx, my = ax + dx * 250 + dy * r.desplazamiento, ay + dy * 250 + dx * r.desplazamiento
        else:
            mx, my = (ax + bx) / 2, (ay + by) / 2
            if r.desplazamiento:
                largo = math.hypot(bx - ax, by - ay)
                mx += -(by - ay) / largo * r.desplazamiento
                my += (bx - ax) / largo * r.desplazamiento
        estilo_rombo = (f"rhombus;whiteSpace=wrap;html=1;fillColor={AMARILLO};strokeColor={AMARILLO_BORDE};"
                        "fontSize=12;")
        if r.identificadora:
            estilo_rombo += "double=1;strokeWidth=1;"
        rombo = l.vertice(r.nombre, estilo_rombo, mx - ROMBO_W / 2, my - ROMBO_H / 2, ROMBO_W, ROMBO_H)

        lados = [(ea, r.card_a), (eb, r.card_b)]
        for i, (ent, card) in enumerate(lados):
            ex, ey = centro(ent)
            if r.propia:
                # Dos líneas rectas desde dos puntos distintos de la entidad hacia dos vértices del rombo.
                w = ancho_entidad(ent)
                if r.desplazamiento < 0:
                    salidas, entradas = (0.08, 0.34), ((0.5, 0), (1, 0.5))
                elif r.desplazamiento > 0:
                    salidas, entradas = (0.66, 0.92), ((0, 0.5), (0.5, 0))
                else:
                    salidas, entradas = (0.25, 0.75), ((0, 0.5), (1, 0.5))
                sx = salidas[i]
                sy = 1 if r.propia == "abajo" else 0
                if r.propia == "arriba":
                    entradas = tuple((a, 1 - b) for a, b in entradas)
                estilo = (linea + f"exitX={sx};exitY={sy};exitDx=0;exitDy=0;"
                          f"entryX={entradas[i][0]};entryY={entradas[i][1]};entryDx=0;entryDy=0;")
                l.arista(ids[ent.nombre], rombo, estilo)
                px_ = ex - w / 2 + sx * w
                py_ = ey + (ENT_H / 2 if sy == 1 else -ENT_H / 2)
                # La etiqueta va sobre su propia línea, a un tercio del camino hacia el rombo.
                rx = mx - ROMBO_W / 2 + entradas[i][0] * ROMBO_W
                ry = my - ROMBO_H / 2 + entradas[i][1] * ROMBO_H
                lx, ly = px_ + (rx - px_) * 0.35 + (-46 if i == 0 else 6), py_ + (ry - py_) * 0.35 - 10
                # Las dos líneas reales, no solo la dirección del rombo.
                for f in (0.3, 0.6):
                    angulos[ent.nombre].append(math.atan2(py_ + (ry - py_) * f - ey, px_ + (rx - px_) * f - ex))
            else:
                l.arista(ids[ent.nombre], rombo, linea)
                bx_, by_ = borde(ex, ey, ancho_entidad(ent), ENT_H, (mx, my))
                largo = math.hypot(mx - ex, my - ey) or 1
                ux, uy = (mx - ex) / largo, (my - ey) / largo
                lx, ly = bx_ + ux * 34 - uy * 18 - 20, by_ + uy * 34 + ux * 18 - 10
                angulos[ent.nombre].append(math.atan2(my - ey, mx - ex))
            l.vertice(card, f"text;html=1;align=center;verticalAlign=middle;fontStyle=1;fontSize=13;fontColor={ROJO};",
                      lx, ly, 40, 20)

        # Atributos de la relación: a los dos lados del rombo, perpendiculares a la línea.
        if r.atributos:
            if r.propia:
                ux, uy = {"abajo": (0, 1), "arriba": (0, -1), "derecha": (1, 0), "izquierda": (-1, 0)}[r.propia]
            else:
                largo = math.hypot(bx - ax, by - ay) or 1
                ux, uy = (bx - ax) / largo, (by - ay) / largo
            px, py = -uy, ux
            for j, nombre_atr in enumerate(r.atributos):
                if r.desplazamiento and not r.propia:
                    lado, paso = (1 if r.desplazamiento > 0 else -1), 1 + j
                    ox = mx + px * (70 + 55 * j) * lado + ux * (70 if j % 2 else -70)
                    oy = my + py * (70 + 55 * j) * lado + uy * (70 if j % 2 else -70)
                    elipse = elipse_atributo(l, Atributo(nombre_atr), ox, oy)
                    l.arista(rombo, elipse, linea)
                    continue
                lado = 1 if j % 2 == 0 else -1
                paso = 1 + j // 2
                ox = mx + px * 120 * lado + ux * 60 * (paso - 1) * lado
                oy = my + py * 120 * lado + uy * 60 * (paso - 1) * lado
                if r.propia:
                    ox, oy = mx + ux * 85 + px * 80 * lado * paso, my + uy * 85 + py * 80 * lado * paso
                elipse = elipse_atributo(l, Atributo(nombre_atr), ox, oy)
                l.arista(rombo, elipse, linea)

    # Atributos de las entidades, alrededor y lejos de las líneas de sus relaciones.
    for e in entidades:
        if not e.atributos:
            continue
        cx, cy = centro(e)
        ocupados = angulos[e.nombre]
        ranuras = [i * 2 * math.pi / 36 for i in range(36)]

        def distancia(a: float) -> float:
            return min((abs((a - o + math.pi) % (2 * math.pi) - math.pi) for o in ocupados), default=math.pi)

        k = len(e.atributos)
        ranuras = [i * 2 * math.pi / 72 for i in range(72)]
        # Nunca en la dirección de una línea; si no hay espacio, se relaja el margen.
        for margen in (26, 20, 14, 0):
            libres = [a for a in ranuras if distancia(a) >= math.radians(margen)]
            if len(libres) >= k * 2:
                break
        ranuras = libres
        elegidas: list[float] = []
        for _ in range(k):
            mejor = max(ranuras, key=lambda a: min(
                [distancia(a) * 1.25] + [abs((a - o + math.pi) % (2 * math.pi) - math.pi) for o in elegidas]))
            elegidas.append(mejor)
        elegidas.sort()
        w = ancho_entidad(e)
        radios = [150 if k <= 6 else ((145, 225)[i % 2] if k <= 9 else (140, 215, 290)[i % 3]) for i in range(k)]

        def posicion(i: int) -> tuple[float, float]:
            ang = elegidas[i]
            return (cx + math.cos(ang) * (radios[i] + (w / 2 - 50) * abs(math.cos(ang))),
                    cy + math.sin(ang) * radios[i] * 0.92)

        def caja(i: int) -> tuple[float, float, float, float]:
            x, y = posicion(i)
            ancho = max(96, 7.2 * len(e.atributos[i].nombre) + 26)
            return x - ancho / 2 - 6, y - 21, x + ancho / 2 + 6, y + 21

        # Si dos elipses se enciman, la más lejana se aleja un poco más de la entidad.
        for _ in range(40):
            movida = False
            for i in range(k):
                for j in range(i + 1, k):
                    a1, b1 = caja(i), caja(j)
                    if a1[0] < b1[2] and b1[0] < a1[2] and a1[1] < b1[3] and b1[1] < a1[3]:
                        lejana = i if radios[i] >= radios[j] else j
                        radios[lejana] += 28
                        movida = True
            if not movida:
                break
        for i, atr in enumerate(e.atributos):
            elipse = elipse_atributo(l, atr, *posicion(i))
            l.arista(ids[e.nombre], elipse, linea)

    # Notas: reglas y leyenda
    abajo = max(centro(e)[1] for e in entidades) + 330
    texto = "<b>Reglas que el diagrama no muestra por sí solo</b><br>" + "<br>".join("· " + r for r in reglas)
    alto = nota(l, texto, 40, abajo, 900, len(reglas) + 2 + sum(len(r) // 120 for r in reglas))
    leyenda = ("<b>Notación de Chen</b><br>Rectángulo: entidad · Rombo: relación · Elipse: atributo<br>"
               "<u>Subrayado</u>: identificador · Elipse punteada: atributo derivado (lo calcula la base) · "
               "Doble elipse: atributo multivaluado<br>Doble rectángulo: entidad débil · Doble rombo: relación que la identifica · "
               "Subrayado punteado: clave parcial<br>Borde punteado: entidad detallada en otro MER<br>"
               "(mín,máx) junto a una entidad: en cuántas relaciones de ese tipo participa cada ejemplar de esa entidad")
    nota(l, leyenda, 980, abajo, 760, 7, amarilla=False)
    return l


def elipse_atributo(l: Lienzo, atr: Atributo, x: float, y: float) -> str:
    ancho = max(96, 7.2 * len(atr.nombre) + 26)
    valor = esc(atr.nombre)
    if atr.clave:
        valor = f"<u><b>{valor}</b></u>"
    elif atr.parcial:
        valor = f'<span style="border-bottom: 1.5px dashed #333333;"><b>{valor}</b></span>'
    estilo = f"ellipse;whiteSpace=wrap;html=1;fillColor={VERDE};strokeColor={VERDE_BORDE};fontSize=11;"
    if atr.derivado:
        estilo += "dashed=1;"
    if atr.multivaluado:
        estilo = estilo.replace("ellipse;", "ellipse;shape=doubleEllipse;")
    return l.vertice(valor, estilo, x - ancho / 2, y - 15, ancho, 30)


def mer_red_social() -> Lienzo:
    E = Entidad
    entidades = [
        E("TENDENCIA", 0, 0, atributos("*id", "ventana_inicio", "ventana_fin", "total_publicaciones", "total_autores",
                                       "diversidad", "puntaje", "posicion")),
        E("ETIQUETA", 1, 0, atributos("*id", "nombre")),
        E("DECLARACION", 2, 0, atributos("*id", "texto", "dicha_el", "tipo", "url_fuente", "estado_promesa")),
        E("USUARIO", 0, 1, atributos("*id", "nombre_usuario", "nombre_visible", "correo", "clave_hash", "rol",
                                     "estado", "biografia", "creado_en")),
        E("PUBLICACION", 1, 1, atributos("*id", "texto", "estado", "(total_respuestas)", "(total_compartidas)",
                                         "(total_reacciones)", "creado_en")),
        E("FIGURA_PUBLICA", 2, 1, atributos("*id", "nombre_completo", "cargo", "partido")),
        E("DECLARACION_REPORTADA", 3, 1, atributos("*id", "actor", "texto_citado")),
        E("TEMA", 2, 2, atributos("*id", "ventana_inicio", "ventana_fin", "titulo", "etiqueta", "(total_articulos)",
                                  "(total_medios)", "posicion")),
        E("ARTICULO", 3, 2, atributos("*id", "url", "titulo", "resumen", "texto", "publicado_en", "(huella)")),
        E("MEDIO", 4, 2, atributos("*id", "nombre", "url_sitio", "canal", "url_canal", "habilitado")),
    ]
    R = Relacion
    relaciones = [
        R("escribe", "USUARIO", "(0,N)", "PUBLICACION", "(1,1)"),
        R("reacciona", "USUARIO", "(0,N)", "PUBLICACION", "(0,N)", ["tipo", "fecha"], desplazamiento=-120),
        R("menciona", "PUBLICACION", "(0,N)", "USUARIO", "(0,N)", desplazamiento=-120),
        R("sigue", "USUARIO", "(0,N)", "USUARIO", "(0,N)", ["fecha"], propia="abajo"),
        R("responde_a", "PUBLICACION", "(0,N)", "PUBLICACION", "(0,1)", propia="abajo", desplazamiento=-150),
        R("comparte", "PUBLICACION", "(0,N)", "PUBLICACION", "(0,1)", propia="abajo", desplazamiento=150),
        R("se_etiqueta", "PUBLICACION", "(0,N)", "ETIQUETA", "(0,N)"),
        R("aparece_en", "ETIQUETA", "(0,N)", "TENDENCIA", "(1,1)"),
        R("trata", "DECLARACION", "(0,N)", "ETIQUETA", "(0,N)"),
        R("hace", "FIGURA_PUBLICA", "(0,N)", "DECLARACION", "(1,1)"),
        R("menciona", "PUBLICACION", "(0,N)", "FIGURA_PUBLICA", "(0,N)"),
        R("la_dijo", "FIGURA_PUBLICA", "(0,N)", "DECLARACION_REPORTADA", "(0,1)"),
        R("reporta", "ARTICULO", "(0,N)", "DECLARACION_REPORTADA", "(1,1)"),
        R("agrupa", "TEMA", "(1,N)", "ARTICULO", "(0,N)"),
        R("publica", "MEDIO", "(0,N)", "ARTICULO", "(1,1)"),
    ]
    reglas = [
        "Una publicación es original, respuesta o compartida, nunca las dos cosas; solo una compartida puede no tener texto.",
        "Nadie se sigue a sí mismo ni sigue dos veces a la misma persona. Una reacción por usuario y publicación (se puede cambiar el tipo).",
        "Reacciones: solo \"me gusta\" y \"útil\" (decisión 3). A los usuarios nunca se les asigna partido; a las figuras públicas sí, porque es público.",
        "Una publicación no se edita ni se borra: solo se retira. Los contadores (atributos derivados) los mantienen triggers.",
        "La contraseña solo se guarda como huella bcrypt o argon2id. Correo y nombre de usuario son únicos, en minúsculas.",
        "Una tendencia necesita al menos 3 autores con cuentas de más de 7 días. Cada ventana queda guardada (solo inserción).",
        "Un tema necesita al menos 3 medios distintos; título y etiqueta sin cifras. La IA agrupa; la base cuenta, descarta y ordena.",
        "La cita de una declaración reportada aparece textual en el artículo y tiene al menos una cifra. Se liga a una figura solo si el nombre coincide exactamente.",
        "Cada declaración la registra un verificador o administrador (registrada_por, en el MR).",
    ]
    return dibujar_mer("MER red social y temas", "MER 1 · Red social y temas del día", entidades, relaciones, reglas)


def mer_verificacion() -> Lienzo:
    E = Entidad
    ref = dict(referencia=True)
    entidades = [
        E("PALABRA_CLAVE", 0, 0, atributos("~palabra"), debil=True),
        E("INDICADOR", 0, 1, atributos("*id", "codigo"), **ref),
        E("PUBLICACION", 1, 0, atributos("*id"), **ref),
        E("DECLARACION", 2, 0, atributos("*id"), **ref),
        E("DECLARACION_REPORTADA", 3, 0, atributos("*id"), **ref),
        E("AFIRMACION", 2, 1, atributos("*id", "posicion", "texto_citado", "variante", "periodo_desde", "periodo_hasta",
                                        "territorio", "valor_dicho", "unidad_dicha", "comparacion",
                                        "confianza_extraccion", "estado")),
        E("TRABAJO_IA", 3, 1, atributos("*id", "tipo", "version_prompt", "entrada", "(huella_entrada)", "estado",
                                        "salida", "proximo_intento_en")),
        E("CREDENCIAL_IA", 4, 0, atributos("*alias", "proveedor", "habilitada", "pausada_hasta")),
        E("INTENTO_IA", 4, 1, atributos("~numero", "modelo", "resultado", "tokens_entrada", "tokens_salida", "error",
                                        "iniciado_en", "terminado_en"), debil=True),
        E("SERIE", 1, 2, atributos("*codigo", "aprobada"), **ref),
        E("VERIFICACION", 2, 2, atributos("*id", "version", "conclusion", "explicacion", "explicacion_validada",
                                          "version_motor", "creado_en")),
        E("PRUEBA_ROBUSTEZ", 3, 2, atributos("*codigo", "nombre", "descripcion")),
        E("OBSERVACION", 2, 3, atributos("*id", "valor", "estado"), **ref),
        E("REVISION_HUMANA", 3, 3, atributos("*id", "decision", "motivo", "creado_en")),
        E("USUARIO", 4, 3, atributos("*id", "rol"), **ref),
    ]
    R = Relacion
    relaciones = [
        R("identifica", "INDICADOR", "(1,N)", "PALABRA_CLAVE", "(1,1)", identificadora=True),
        R("trata_sobre", "INDICADOR", "(0,N)", "AFIRMACION", "(0,1)"),
        R("contiene", "PUBLICACION", "(0,N)", "AFIRMACION", "(0,1)"),
        R("contiene", "DECLARACION", "(0,N)", "AFIRMACION", "(0,1)"),
        R("contiene", "DECLARACION_REPORTADA", "(0,N)", "AFIRMACION", "(0,1)"),
        R("la_extrajo", "TRABAJO_IA", "(0,N)", "AFIRMACION", "(0,1)"),
        R("tiene", "TRABAJO_IA", "(0,N)", "INTENTO_IA", "(1,1)", identificadora=True),
        R("se_usa_en", "CREDENCIAL_IA", "(0,N)", "INTENTO_IA", "(1,1)"),
        R("se_verifica", "AFIRMACION", "(0,N)", "VERIFICACION", "(1,1)"),
        R("usa", "SERIE", "(0,N)", "VERIFICACION", "(0,1)"),
        R("aplica", "VERIFICACION", "(0,N)", "PRUEBA_ROBUSTEZ", "(0,N)", ["resultado", "detalle"]),
        R("se_respalda", "VERIFICACION", "(0,N)", "OBSERVACION", "(0,N)", ["rol"]),
        R("se_revisa", "VERIFICACION", "(0,N)", "REVISION_HUMANA", "(1,1)"),
        R("realiza", "USUARIO", "(0,N)", "REVISION_HUMANA", "(1,1)"),
    ]
    reglas = [
        "Arco exclusivo: cada afirmación sale de exactamente uno de sus tres textos (publicación, declaración o declaración reportada).",
        "Las verificaciones no se editan: una corrección es una versión nueva y la vigente es la de mayor versión (decisión 5).",
        "Una conclusión distinta de \"sin dato comparable\" tiene al menos una observación citada; hay serie si y solo si hay dato comparable.",
        "La evidencia solo puede ser una observación vigente y aceptada (nunca en cuarentena), y la serie debe estar aprobada.",
        "Una explicación validada no puede tener una cifra que no esté en la evidencia, en el valor dicho o en los periodos (trigger diferido).",
        "Solo un usuario con rol verificador o admin realiza revisiones humanas.",
        "Una credencial no guarda la llave secreta: solo su alias. Un trabajo tiene salida si y solo si terminó; la misma entrada se resuelve una vez (caché).",
        "Las entidades con borde punteado viven en otros esquemas: la relación la revisa un trigger con una función, no una llave foránea (decisión 1).",
    ]
    return dibujar_mer("MER verificación e IA", "MER 2 · Verificación automática y servicio de IA", entidades, relaciones, reglas)


def mer_oficial() -> Lienzo:
    E = Entidad
    entidades = [
        E("ARCHIVO_EVIDENCIA", 0, 0, atributos("*id", "manifiesto", "fuente", "url", "descargado_en", "sha256",
                                               "tamano", "ubicacion")),
        E("FUENTE", 1, 0, atributos("*id", "codigo", "nombre", "rol")),
        E("INDICADOR", 2, 0, atributos("*id", "codigo", "categoria")),
        E("APROBACION_SERIE", 3, 0, atributos("*id", "estado", "huella_contenido", "aprobada_por", "aprobada_el",
                                              "comentarios")),
        E("ARCHIVO_ORIGINAL", 0, 1, atributos("*id", "nombre", "url", "sha256", "ubicacion")),
        E("DESCARGA", 1, 1, atributos("*id", "canal", "descargado_en", "actualizado_fuente")),
        E("SERIE", 2, 1, atributos("*id", "codigo", "variante", "nombre", "unidad", "frecuencia", "geografia",
                                   "huella_contenido", "aprobada")),
        E("NOTA_SERIE", 3, 1, atributos("*id", "clave_nota", "tipo", "vigente_desde", "vigente_hasta", "estado",
                                        "contenido")),
        E("OBSERVACION", 2, 2, atributos("*id", "secuencia", "periodo", "territorio", "valor", "estado",
                                         "estado_contraste", "nivel_contraste", "{marcas}")),
        E("DIFERENCIA_VERSION", 3, 2, atributos("*id", "periodo", "nivel", "fuente", "valor_fuente", "valor_serie")),
        E("EVENTO_ALERTA", 0, 3, atributos("*id", "evento", "actor", "motivo", "creado_en")),
        E("ALERTA", 1, 3, atributos("*id", "periodo", "territorio", "tipo", "valor", "estado")),
        E("COMPARACION_CONTRASTE", 2, 3, atributos("*id", "fuente", "nivel", "periodo_comparado", "valor_fuente",
                                                   "valor_serie", "tolerancia", "resultado", "diferencia_conocida")),
        E("BRECHA_CONTEXTO", 3, 3, atributos("*id", "codigo", "nombre", "explicacion", "prueba")),
    ]
    R = Relacion
    relaciones = [
        R("produce", "FUENTE", "(0,N)", "SERIE", "(1,1)", desplazamiento=-75),
        R("distribuye", "FUENTE", "(0,N)", "SERIE", "(1,1)", desplazamiento=75),
        R("se_mide_con", "INDICADOR", "(0,N)", "SERIE", "(1,1)"),
        R("se_aprueba", "SERIE", "(0,N)", "APROBACION_SERIE", "(1,1)"),
        R("tiene_nota", "SERIE", "(0,N)", "NOTA_SERIE", "(1,1)"),
        R("registra", "SERIE", "(0,N)", "DIFERENCIA_VERSION", "(1,1)"),
        R("se_descarga", "SERIE", "(0,N)", "DESCARGA", "(1,1)"),
        R("guarda", "DESCARGA", "(1,N)", "ARCHIVO_ORIGINAL", "(1,1)"),
        R("trae", "DESCARGA", "(0,N)", "OBSERVACION", "(1,1)"),
        R("tiene", "SERIE", "(0,N)", "OBSERVACION", "(1,1)"),
        R("se_contrasta", "OBSERVACION", "(0,N)", "COMPARACION_CONTRASTE", "(1,1)"),
        R("abre", "OBSERVACION", "(0,N)", "ALERTA", "(1,1)"),
        R("historial", "ALERTA", "(1,N)", "EVENTO_ALERTA", "(1,1)"),
    ]
    reglas = [
        "Observaciones, descargas, archivos, contrastes, aprobaciones y eventos de alerta son de solo inserción: una versión nueva es una fila nueva.",
        "El valor vigente de un periodo es la observación de mayor secuencia; si está en cuarentena, el periodo no tiene valor (nunca se usa uno anterior).",
        "Una alerta solo cambia de estado (abierta ↔ cerrada) y cada cambio deja su evento con quién y por qué (trigger diferido).",
        "Una sola alerta abierta por serie, periodo, territorio, tipo y valor. La alerta también guarda su serie (relación omitida en el dibujo).",
        "Fuente, indicador, serie, notas y diferencias son copia de git (fichas aprobadas con su huella); los códigos del catálogo no se traducen.",
        "Los valores son numeric sin escala: decimal exacto, nunca float. Archivo de evidencia y brecha de contexto no se relacionan con otras entidades.",
    ]
    return dibujar_mer("MER datos oficiales", "MER 3 · Datos oficiales", entidades, relaciones, reglas)


# =============================================================================
# MR · leído de la base
# =============================================================================

# Referencias entre esquemas (no son llaves foráneas: las revisa un trigger con una función).
REFERENCIAS_LOGICAS = {
    "verificacion.afirmacion.publicacion_id": "social.publicacion",
    "verificacion.afirmacion.declaracion_id": "social.declaracion",
    "verificacion.afirmacion.declaracion_reportada_id": "temas.declaracion_reportada",
    "verificacion.afirmacion.trabajo_ia_id": "ia.trabajo",
    "verificacion.verificacion.codigo_serie": "oficial.serie.codigo",
    "verificacion.evidencia.observacion_id": "oficial.observacion",
    "verificacion.revision_humana.revisor_id": "social.usuario",
    "verificacion.procesamiento.origen_id": "texto de origen",
    "temas.declaracion_reportada.figura_id": "social.figura_publica",
    "temas.declaracion_reportada.trabajo_ia_id": "ia.trabajo",
    "temas.tema.trabajo_ia_id": "ia.trabajo",
}

REGLAS_MR = {
    "oficial": [
        "Triggers de solo inserción en aprobacion_serie, archivo_evidencia, descarga, archivo_original, observacion, comparacion_contraste y evento_alerta.",
        "alerta: solo cambia estado (alerta_solo_cambia_estado, alerta_transicion) y cada cambio exige su evento al confirmar (alerta_cambio_con_evento, diferido).",
        "Índice único parcial alerta_una_abierta_idx: una alerta abierta por (serie_id, periodo, territorio, tipo, valor).",
        "Funciones: observaciones_vigentes, observacion_en, esta_aceptada, serie_aprobada, alertas_abiertas. Procedimientos: cerrar_alerta, reabrir_alerta.",
    ],
    "social": [
        "Contadores de publicacion mantenidos por triggers (publicacion_contadores, reaccion_contadores); el texto no se edita y una retirada no vuelve a visible.",
        "Outbox: cada cambio escribe su evento en evento_salida en la misma transacción; entrega_evento registra qué consumidor (grafo, verificación) lo procesó.",
        "declaracion: solo cambia estado_promesa. tendencia, evento_salida y entrega_evento: solo inserción.",
        "Procedimientos: registrar_usuario, publicar, retirar_publicacion, seguir, dejar_de_seguir, reaccionar, quitar_reaccion, registrar_declaracion, registrar_tendencias, marcar_entregados.",
    ],
    "verificacion": [
        "Las columnas con → apuntan a otros esquemas: las revisa un trigger (afirmacion_destino_existe, evidencia_observacion_aceptada, verificacion_serie_existe, revision_por_verificador).",
        "Triggers diferidos al confirmar: verificacion_tiene_evidencia y explicacion_cifras_respaldadas (ninguna cifra fuera de la evidencia).",
        "verificacion, evidencia, resultado_prueba y revision_humana: solo inserción. afirmacion: solo cambia estado (máquina de estados).",
        "Procedimientos: registrar_afirmaciones, registrar_procesamiento, registrar_verificacion, registrar_revision, marcar_entregados.",
    ],
    "ia": [
        "credencial no tiene columna para la llave secreta: la llave vive en la configuración del servicio de IA, con el mismo alias.",
        "Índices únicos parciales en trabajo (tipo, version_prompt, huella_entrada): uno WHERE estado = 'terminado' (caché) y otro WHERE estado IN ('en_cola', 'en_curso').",
        "huella_entrada la calcula un trigger; tipo, versión y entrada no cambian; máquina de estados en_cola → en_curso → terminado / fallido. intento: solo inserción.",
        "tomar_trabajo usa FOR UPDATE SKIP LOCKED con un plazo de 5 minutos; registrar_intento pausa la cuenta ante un límite y reintenta con espera creciente.",
    ],
    "temas": [
        "declaracion_reportada_validar: la cita debe aparecer textual en el artículo; la figura, si se da, debe existir en social.",
        "registrar_temas: la base cuenta los medios distintos, descarta los grupos de menos de 3, ordena y guarda 7 como máximo (todo o nada).",
        "articulo, tema, tema_articulo, declaracion_reportada, evento_salida y entrega_evento: solo inserción. huella la calcula un trigger.",
        "Procedimientos: configurar_medio, registrar_articulos, registrar_temas, registrar_declaraciones, marcar_entregados.",
    ],
}

TITULOS_MR = {"oficial": "MR 1 · Esquema oficial", "social": "MR 2 · Esquema social",
              "verificacion": "MR 3 · Esquema verificacion", "ia": "MR 4 · Esquema ia", "temas": "MR 5 · Esquema temas"}


def tipo_corto(t: str) -> str:
    return (t.replace("timestamp with time zone", "timestamptz").replace("character varying", "varchar")
            .replace("double precision", "float8"))


def simplificar_check(definicion: str) -> str:
    d = re.sub(r"::(text|numeric|bigint|integer)(\[\])?", "", definicion)
    d = re.sub(r"= ANY \(ARRAY\[(.*?)\]\)", r"IN (\1)", d)
    d = re.sub(r"^CHECK \((.*)\)$", r"\1", d)
    while d.startswith("((") and d.endswith("))"):
        d = d[1:-1]
    return d if len(d) <= 170 else d[:167] + "…"


def leer_esquema(conn, esquema: str):
    tablas: dict[str, list[dict]] = {}
    for tabla, col, tipo, nulo, pos in conn.execute(
        """SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), NOT a.attnotnull, a.attnum
           FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = %s AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
           ORDER BY c.relname, a.attnum""", (esquema,)):
        tablas.setdefault(tabla, []).append({"nombre": col, "tipo": tipo_corto(tipo), "nulo": nulo, "etiquetas": set()})
    restricciones = conn.execute(
        """SELECT c.relname, k.conname, k.contype, pg_get_constraintdef(k.oid),
                  ARRAY(SELECT a.attname FROM unnest(k.conkey) WITH ORDINALITY u(n, o)
                        JOIN pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = u.n ORDER BY u.o),
                  fc.relname, ARRAY(SELECT a.attname FROM unnest(k.confkey) WITH ORDINALITY u(n, o)
                        JOIN pg_attribute a ON a.attrelid = k.confrelid AND a.attnum = u.n ORDER BY u.o)
           FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid JOIN pg_namespace n ON n.oid = c.relnamespace
           LEFT JOIN pg_class fc ON fc.oid = k.confrelid
           WHERE n.nspname = %s ORDER BY c.relname, k.conname""", (esquema,)).fetchall()
    return tablas, restricciones


def dibujar_mr(conn, esquema: str) -> Lienzo:
    tablas, restricciones = leer_esquema(conn, esquema)
    claves_unicas: dict[str, list[list[str]]] = {}
    foraneas: list[tuple[str, list[str], str, list[str]]] = []
    checks: list[tuple[str, str, str]] = []
    for tabla, nombre, tipo, definicion, cols, tabla_ref, cols_ref in restricciones:
        columnas = {c["nombre"]: c for c in tablas[tabla]}
        if tipo == "p":
            for c in cols:
                columnas[c]["etiquetas"].add("PK")
            claves_unicas.setdefault(tabla, []).append(cols)
        elif tipo == "u":
            for c in cols:
                columnas[c]["etiquetas"].add("UQ")
            claves_unicas.setdefault(tabla, []).append(cols)
        elif tipo == "f":
            for c in cols:
                columnas[c]["etiquetas"].add("FK")
            foraneas.append((tabla, cols, tabla_ref, cols_ref))
        elif tipo == "c":
            for c in cols:
                columnas[c]["etiquetas"].add("CK")
            checks.append((tabla, nombre, simplificar_check(definicion)))

    # Niveles: las tablas padre a la izquierda.
    padres = {t: {p for (h, _, p, _) in foraneas if h == t and p != t} for t in tablas}
    nivel: dict[str, int] = {}

    def calcular(t: str, visitando=()) -> int:
        if t not in nivel:
            nivel[t] = 0 if not padres[t] else 1 + max(calcular(p, visitando + (t,)) for p in padres[t] if p not in visitando)
        return nivel[t]

    for t in tablas:
        calcular(t)

    l = Lienzo(f"MR {esquema}")
    l.vertice(f"<b>{esc(TITULOS_MR[esquema])}</b>", f"text;html=1;align=left;verticalAlign=middle;fontSize=20;fontColor={AZUL};",
              40, 10, 1200, 40)
    filas_id: dict[tuple[str, str], str] = {}
    x, abajo = 40.0, 0.0
    # Orden dentro de cada columna: cerca de sus padres (o de sus hijas), para cruzar menos líneas.
    columnas = {n: sorted(t for t in tablas if nivel[t] == n) for n in range(max(nivel.values()) + 1)}
    hijas = {t: {h for (h, _, p, _) in foraneas if p == t and h != t} for t in tablas}
    for _ in range(4):
        posicion = {t: i for col in columnas.values() for i, t in enumerate(col)}
        for n in sorted(columnas):
            def baricentro(t, n=n):
                vecinos = [posicion[p] for p in (padres[t] if n else hijas[t])]
                return sum(vecinos) / len(vecinos) if vecinos else posicion[t]
            columnas[n].sort(key=baricentro)
            posicion = {t: i for col in columnas.values() for i, t in enumerate(col)}
    for n in range(max(nivel.values()) + 1):
        columna = columnas[n]
        ancho_col = 0.0
        y = 70.0
        for t in columna:
            textos = []
            for c in tablas[t]:
                ref = REFERENCIAS_LOGICAS.get(f"{esquema}.{t}.{c['nombre']}")
                nombre = esc(c["nombre"])
                if "PK" in c["etiquetas"]:
                    nombre = f"<u><b>{nombre}</b></u>"
                if "FK" in c["etiquetas"] or ref:
                    nombre = f"<i>{nombre}</i>"
                etiquetas = []
                for e, color in (("PK", ETIQUETA_PK), ("FK", ETIQUETA_FK), ("UQ", ETIQUETA_UQ), ("CK", ETIQUETA_CK)):
                    if e in c["etiquetas"]:
                        etiquetas.append(f'<font color="{color}"><b>{e}</b></font>')
                if c["nulo"] and "PK" not in c["etiquetas"]:
                    etiquetas.append('<font color="#999999">NULL</font>')
                if ref:
                    etiquetas.append(f'<font color="{ETIQUETA_FK}">→ {esc(ref)}</font>')
                textos.append((c["nombre"], f'{nombre} <font color="{GRIS}">{esc(c["tipo"])}</font> ' + " ".join(etiquetas),
                               len(c["nombre"]) + len(c["tipo"]) + 4 * len(etiquetas) + (len(ref) + 3 if ref else 0)))
            ancho = max(250, max(n_ for _, _, n_ in textos) * 7.0 + 40, len(t) * 9 + 40)
            alto = 30 + 22 * len(textos)
            tabla_id = l.vertice(t, f"swimlane;fontStyle=1;startSize=30;fillColor={AZUL};fontColor=#FFFFFF;strokeColor={AZUL};"
                                 "swimlaneFillColor=#F7F9FC;html=1;fontSize=13;collapsible=0;", x, y, ancho, alto)
            for i, (col, texto, _) in enumerate(textos):
                filas_id[(t, col)] = l.vertice(
                    texto, "text;html=1;align=left;verticalAlign=middle;spacingLeft=8;fontSize=11;"
                    "points=[[0,0.5],[1,0.5]];portConstraint=eastwest;", 0, 30 + 22 * i, ancho, 22, padre=tabla_id)
            y += alto + 45
            ancho_col = max(ancho_col, ancho)
        abajo = max(abajo, y)
        x += ancho_col + 150

    # Llaves foráneas: pata de gallo en la tabla hija.
    for hija, cols, padre, cols_ref in foraneas:
        columnas = {c["nombre"]: c for c in tablas[hija]}
        uno_a_uno = any(sorted(u) == sorted(cols) for u in claves_unicas.get(hija, []))
        inicio = "ERzeroToOne" if uno_a_uno else "ERzeroToMany"
        fin = "ERmandOne" if all(not columnas[c]["nulo"] for c in cols) else "ERzeroToOne"
        estilo = (f"html=1;startArrow={inicio};endArrow={fin};startFill=0;endFill=0;strokeColor=#4A5568;strokeWidth=1.3;")
        if hija == padre:
            estilo = "edgeStyle=orthogonalEdgeStyle;rounded=0;exitX=1;exitY=0.5;entryX=1;entryY=0.5;" + estilo
        else:
            estilo = "edgeStyle=entityRelationEdgeStyle;" + estilo
        l.arista(filas_id[(hija, cols[0])], filas_id[(padre, cols_ref[0])], estilo)

    # Notas: CHECK, reglas del esquema y leyenda.
    y_notas = abajo + 20
    lineas_check = [f"<b>{esc(t)}</b> · {esc(n)}: <font color=\"#555555\">{esc(d)}</font>" for t, n, d in checks]
    alto = nota(l, "<b>Restricciones CHECK</b><br><br>" + "<br>".join(lineas_check), 40, y_notas, 1100,
                len(lineas_check) + 2 + sum(1 for _, _, d in checks if len(d) > 110), amarilla=False)
    reglas = REGLAS_MR[esquema]
    texto = "<b>Reglas que el diagrama no muestra por sí solo</b><br>" + "<br>".join("· " + esc(r) for r in reglas)
    nota(l, texto, 1180, y_notas, 760, len(reglas) + 2 + sum(len(r) // 105 for r in reglas))
    leyenda = (f'<b>Leyenda</b><br><font color="{ETIQUETA_PK}"><b>PK</b></font> llave primaria · '
               f'<font color="{ETIQUETA_FK}"><b>FK</b></font> llave foránea · <font color="{ETIQUETA_UQ}"><b>UQ</b></font> único · '
               f'<font color="{ETIQUETA_CK}"><b>CK</b></font> CHECK · <font color="#999999">NULL</font> admite vacío<br>'
               f'<font color="{ETIQUETA_FK}">→ esquema.tabla</font>: referencia a otro esquema, revisada por un trigger (no es llave foránea)<br>'
               "Línea: pata de gallo en la tabla hija; O = opcional, | = obligatorio. Todas las tablas son de PostgreSQL 17.")
    nota(l, leyenda, 1180, y_notas + 40 + 15 * (len(reglas) + 3 + sum(len(r) // 105 for r in reglas)), 760, 4, amarilla=False)
    return l


# =============================================================================
# Neo4j · modelo de grafo y relación con PostgreSQL
# =============================================================================

COLOR_NODO = {"Usuario": ("#DCE8FA", AZUL), "Publicacion": ("#FFE7A8", AMARILLO_BORDE), "Etiqueta": ("#EAF5EA", VERDE_BORDE),
              "Figura": ("#F6E1E5", "#8F1D2C"), "Serie": ("#E8E4F5", "#4B3C8F")}
PROPIEDADES_NODO = {
    "Usuario": ["id (único)", "nombre_usuario", "estado", "creado_en"],
    "Publicacion": ["id (único)", "estado", "creado_en (índice)"],
    "Etiqueta": ["nombre (único)"],
    "Figura": ["id (único)", "nombre_completo"],
    "Serie": ["codigo (único)", "indicador"],
}


def nodo_grafo(l: Lienzo, etiqueta: str, cx: float, cy: float, diametro: float = 150) -> str:
    relleno, borde_ = COLOR_NODO[etiqueta]
    id_ = l.vertice(f"<b>:{etiqueta}</b>", f"ellipse;whiteSpace=wrap;html=1;aspect=fixed;fillColor={relleno};"
                    f"strokeColor={borde_};strokeWidth=2.5;fontSize=15;", cx - diametro / 2, cy - diametro / 2, diametro, diametro)
    props = "<br>".join(esc(p) for p in PROPIEDADES_NODO[etiqueta])
    l.vertice(props, f"text;html=1;align=center;verticalAlign=top;fontSize=11;fontColor={GRIS};",
              cx - 90, cy + diametro / 2 + 4, 180, 18 * len(PROPIEDADES_NODO[etiqueta]))
    return id_


def flecha_grafo(l: Lienzo, origen: str, destino: str, texto: str, puntos=None, extra: str = "") -> None:
    estilo = ("endArrow=block;endFill=1;html=1;strokeColor=#4A5568;strokeWidth=2;fontSize=12;fontStyle=1;"
              "labelBackgroundColor=#FFFFFF;fontColor=#1F3B6F;" + extra)
    id_ = l.nuevo_id()
    geo = '<mxGeometry relative="1" as="geometry">'
    if puntos:
        geo += '<Array as="points">' + "".join(f'<mxPoint x="{x:.0f}" y="{y:.0f}" />' for x, y in puntos) + "</Array>"
    geo += "</mxGeometry>"
    l.celdas.append(f'<mxCell id="{id_}" value="{esc(texto)}" style="{estilo}" edge="1" parent="1" '
                    f'source="{origen}" target="{destino}">{geo}</mxCell>')


def grafo_modelo() -> Lienzo:
    l = Lienzo("Modelo de grafo")
    l.vertice("<b>Neo4j 1 · Modelo de grafo de propiedades</b>",
              f"text;html=1;align=left;verticalAlign=middle;fontSize=20;fontColor={AZUL};", 40, 20, 1200, 40)
    u = nodo_grafo(l, "Usuario", 300, 480)
    p = nodo_grafo(l, "Publicacion", 900, 480)
    e = nodo_grafo(l, "Etiqueta", 1500, 200)
    f = nodo_grafo(l, "Figura", 1500, 520)
    s = nodo_grafo(l, "Serie", 1500, 840)
    flecha_grafo(l, u, p, "PUBLICO", extra="exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    flecha_grafo(l, u, p, "REACCIONO {tipo, en}", puntos=[(600, 330)], extra="exitX=0.85;exitY=0.15;entryX=0.15;entryY=0.15;")
    flecha_grafo(l, p, u, "MENCIONA", puntos=[(600, 640)], extra="exitX=0.15;exitY=0.85;entryX=0.85;entryY=0.85;")
    flecha_grafo(l, u, u, "SIGUE {desde}", puntos=[(170, 250), (430, 250)], extra="exitX=0.2;exitY=0.1;entryX=0.8;entryY=0.1;")
    flecha_grafo(l, p, p, "RESPONDE_A", puntos=[(800, 250), (1000, 250)], extra="exitX=0.2;exitY=0.1;entryX=0.8;entryY=0.1;")
    flecha_grafo(l, p, p, "COMPARTE", puntos=[(780, 760), (1020, 760)], extra="exitX=0.2;exitY=0.95;entryX=0.8;entryY=0.95;")
    flecha_grafo(l, p, e, "ETIQUETADA_CON", extra="exitX=0.95;exitY=0.25;entryX=0;entryY=0.5;")
    flecha_grafo(l, p, f, "MENCIONA", extra="exitX=1;exitY=0.55;entryX=0;entryY=0.5;")
    flecha_grafo(l, p, s, "VERIFICADA_CON {conclusion, version}", extra="exitX=0.9;exitY=0.85;entryX=0;entryY=0.5;")

    reglas = [
        "PostgreSQL es la fuente de verdad: Neo4j es una proyección de la red y solo lo escribe el servicio de grafo, a partir del outbox.",
        "No guarda correos, contraseñas, textos de publicaciones ni etiquetas políticas: solo identificadores, nombres públicos, fechas y estados.",
        "Una publicación retirada no se borra del grafo (estado = retirada): se conserva su árbol de difusión.",
        "VERIFICADA_CON guarda la conclusión vigente; una versión vieja que llegue tarde no pisa a una más nueva.",
        "Restricciones de unicidad en Usuario.id, Publicacion.id, Etiqueta.nombre, Figura.id y Serie.codigo; índice en Publicacion.creado_en.",
    ]
    nota(l, "<b>Reglas</b><br>" + "<br>".join("· " + esc(r) for r in reglas), 40, 1020, 980, len(reglas) + 3)
    consultas_txt = ("<b>Las cuatro consultas que justifican el grafo</b><br>"
                     "1. <b>Feed:</b> (yo)-[:SIGUE]->()-[:PUBLICO]->(p) y a dos saltos, últimos 7 días<br>"
                     "2. <b>A quién seguir:</b> (yo)-[:SIGUE]->(amigo)-[:SIGUE]->(sugerido), por amigos en común<br>"
                     "3. <b>Difusión:</b> (original)&lt;-[:COMPARTE*1..10]-(c): quién compartió a quién<br>"
                     "4. <b>Tendencias por diversidad:</b> autores de una etiqueta que NO se siguen entre sí pesan más<br>"
                     "&nbsp;&nbsp;&nbsp;diversidad = 1 − enlaces / (n·(n−1)); puntaje = publicaciones × diversidad")
    nota(l, consultas_txt, 1060, 1020, 760, 7, amarilla=False)
    return l


MAPEO = [
    ("social.usuario", "usuario_creado · usuario_cambio_estado", "(:Usuario)"),
    ("social.seguimiento", "seguimiento_creado · seguimiento_borrado", "(:Usuario)-[:SIGUE]->(:Usuario)"),
    ("social.publicacion", "publicacion_creada · publicacion_retirada",
     "(:Usuario)-[:PUBLICO]->(:Publicacion)<br>(:Publicacion)-[:RESPONDE_A | :COMPARTE]->(:Publicacion)"),
    ("social.publicacion_etiqueta", "publicacion_etiquetada", "(:Publicacion)-[:ETIQUETADA_CON]->(:Etiqueta)"),
    ("social.mencion_usuario · mencion_figura", "publicacion_menciona", "(:Publicacion)-[:MENCIONA]->(:Usuario | :Figura)"),
    ("social.reaccion", "reaccion_puesta · reaccion_quitada", "(:Usuario)-[:REACCIONO {tipo}]->(:Publicacion)"),
    ("social.figura_publica", "figura_creada", "(:Figura)"),
    ("verificacion.verificacion", "verificacion_publicada", "(:Publicacion)-[:VERIFICADA_CON {conclusion}]->(:Serie)"),
]


def grafo_desde_postgres() -> Lienzo:
    l = Lienzo("PostgreSQL a Neo4j")
    l.vertice("<b>Neo4j 2 · De PostgreSQL a Neo4j (transactional outbox)</b>",
              f"text;html=1;align=left;verticalAlign=middle;fontSize=20;fontColor={AZUL};", 40, 20, 1400, 40)
    # Encabezados de las tres franjas
    for x, titulo, color in ((40, "PostgreSQL · fuente de verdad", AZUL), (560, "Evento en el outbox (mismo trigger, misma transacción)", AMARILLO_BORDE),
                             (1080, "Neo4j · proyección", "#2E6B4F")):
        l.vertice(f"<b>{titulo}</b>", f"rounded=1;whiteSpace=wrap;html=1;fillColor={color};fontColor=#FFFFFF;strokeColor={color};fontSize=13;",
                  x, 80, 460 if x < 1080 else 560, 36)
    y = 140
    for tabla, evento, grafo in MAPEO:
        alto = 58 if "<br>" in grafo else 44
        a = l.vertice(f"<b>{esc(tabla)}</b>", f"rounded=0;whiteSpace=wrap;html=1;fillColor={AZUL_CLARO};strokeColor={AZUL};strokeWidth=1.5;fontSize=12;",
                      40, y, 460, alto)
        b = l.vertice(esc(evento), f"rounded=1;whiteSpace=wrap;html=1;fillColor={AMARILLO};strokeColor={AMARILLO_BORDE};fontSize=12;fontStyle=2;",
                      560, y, 460, alto)
        c = l.vertice(grafo,
                      "rounded=1;whiteSpace=wrap;html=1;fillColor=#EAF5EA;strokeColor=#2E6B4F;fontSize=12;fontFamily=Courier New;",
                      1080, y, 560, alto)
        flecha = "endArrow=block;endFill=1;html=1;strokeColor=#4A5568;strokeWidth=1.5;"
        l.arista(a, b, flecha)
        l.arista(b, c, flecha)
        y += alto + 18

    # El camino de un evento, paso a paso
    pasos = [
        ("1. Transacción en PostgreSQL", "CALL social.publicar(…)<br>inserta la publicación <b>y</b>, por trigger, su evento en <b>social.evento_salida</b>. Si algo falla, no queda ninguno de los dos"),
        ("2. Aviso", "pg_notify('evento_salida') despierta al servicio de grafo (si el aviso se pierde, revisa cada 30 s)"),
        ("3. Sincronizador", "eventos_pendientes('grafo') → aplica el lote en Neo4j con MERGE (idempotente) en una transacción de Neo4j"),
        ("4. Confirmación", "marcar_entregados('grafo', …) en <b>entrega_evento</b>. Verificación lee el mismo outbox con su propio consumidor"),
        ("5. Reconstrucción", "POST /v1/reconstruir: vacía Neo4j y vuelve a aplicar todo el outbox en orden → el mismo grafo"),
    ]
    x = 40
    y += 30
    anterior = None
    for titulo, detalle in pasos:
        caja = l.vertice(f"<b>{titulo}</b><br><font style=\"font-size: 11px\">{detalle}</font>",
                         f"rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor={AZUL};strokeWidth=1.5;fontSize=13;align=center;spacing=8;",
                         x, y, 300, 130)
        if anterior:
            l.arista(anterior, caja, "endArrow=block;endFill=1;html=1;strokeColor=#1F3B6F;strokeWidth=2;")
        anterior = caja
        x += 335
    nota(l, "<b>Por qué así</b><br>· PostgreSQL y Neo4j no comparten transacción: el outbox garantiza que ningún cambio se pierda "
            "y que ninguno llegue al grafo sin haberse confirmado en PostgreSQL.<br>"
            "· Entrega \"al menos una vez\": si el servicio se cae entre Neo4j y PostgreSQL, el lote se repite; como todo es MERGE, "
            "el grafo queda igual.<br>· El outbox es de solo inserción: es la historia completa de la red, por eso Neo4j se puede "
            "reconstruir desde cero.", 40, y + 160, 1640, 5)
    return l


# =============================================================================


def guardar(l: Lienzo, nombre: str) -> Path:
    ruta = CARPETA / f"{nombre}.drawio"
    ruta.write_text(l.xml(), encoding="utf-8")
    return ruta


def exportar_png(ruta: Path) -> None:
    if not DRAWIO.exists():
        print(f"  (draw.io no está en {DRAWIO}: solo se generó {ruta.name})")
        return
    salida = ruta.with_suffix(".png")
    subprocess.run([str(DRAWIO), "-x", "-f", "png", "-s", "2", "-b", "20", "-o", str(salida), str(ruta)],
                   check=True, capture_output=True)
    print(f"  {salida.name}")


def main() -> int:
    sys.path.insert(0, str(CARPETA.parent / "src"))
    from app.db import connect

    rutas = [
        guardar(mer_red_social(), "MER_1_red_social_y_temas"),
        guardar(mer_verificacion(), "MER_2_verificacion_e_ia"),
        guardar(mer_oficial(), "MER_3_datos_oficiales"),
        guardar(grafo_modelo(), "NEO4J_1_modelo_de_grafo"),
        guardar(grafo_desde_postgres(), "NEO4J_2_postgres_a_neo4j"),
    ]
    with connect() as conn:
        for i, esquema in enumerate(("oficial", "social", "verificacion", "ia", "temas"), start=1):
            rutas.append(guardar(dibujar_mr(conn, esquema), f"MR_{i}_{esquema}"))
    for ruta in rutas:
        print(ruta.name)
        exportar_png(ruta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
