"""El formato fijo de cada tipo de trabajo: la salida se valida antes de guardarse.

Lo que llega al servicio de verificación siempre tiene la misma forma, venga del
proveedor que venga. Además de la forma, se revisa lo que la IA no puede inventar:
las citas deben estar textuales en la entrada y las cifras deben estar en el texto.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Literal

import calendar

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

INDICADORES = Literal["inflation", "unemployment", "minimum_wage", "public_debt", "homicides", "theft", "extortion",
                      "kidnapping"]
PERIODO = r"^\d{4}(-\d{2}(-\d{2})?)?$"


class SalidaInvalida(Exception):
    """La respuesta no cumple el formato: se registra como salida_invalida y se reintenta."""


def cifras(texto: str) -> set[Decimal]:
    """Cifras de un texto en formato colombiano (igual que util.cifras_en_texto en la base)."""
    encontradas = set()
    for m in re.finditer(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?", texto or ""):
        encontradas.add(Decimal(m.group(0).replace(".", "").replace(",", ".")).normalize())
    return encontradas


class Afirmacion(BaseModel):
    texto_citado: str = Field(min_length=3)
    codigo_indicador: INDICADORES
    variante: Literal["anual", "mensual", "anio_corrido", "tasa", "conteo", "nominal", "real"] | None = None
    periodo_desde: str | None = Field(default=None, pattern=PERIODO)
    periodo_hasta: str | None = Field(default=None, pattern=PERIODO)
    territorio: str = "national"
    valor_dicho: str
    unidad_dicha: str | None = None
    comparacion: Literal["nivel", "variacion_porcentual", "variacion_puntos"] = "nivel"
    direccion: Literal["sube", "baja"] | None = None
    confianza: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _periodo(self):
        self.periodo_desde, self.periodo_hasta = periodo_canonico(self.periodo_desde, self.periodo_hasta)
        # Igual que la restricción afirmacion_periodos_validos de la base: un periodo al revés es una lectura
        # mal hecha ("agosto de 2026 frente a agosto de 2025" leído como desde 2026-08 hasta 2025-08).
        if self.periodo_desde and self.periodo_hasta and self.periodo_desde > self.periodo_hasta:
            raise ValueError("periodo_desde es posterior a periodo_hasta")
        return self

    @field_validator("valor_dicho")
    @classmethod
    def _decimal(cls, v: str) -> str:
        try:
            return str(Decimal(str(v).replace(",", ".")).normalize())
        except InvalidOperation:
            raise ValueError("valor_dicho no es una cifra")


def periodo_canonico(desde: str | None, hasta: str | None) -> tuple[str | None, str | None]:
    """Un mes o un año completos escritos como días se escriben como mes o como año.

    "2026-08-01" a "2026-08-31" es "2026-08"; "2025-01-01" a "2025-12-31" es "2025". Así dos
    lectores que entendieron lo mismo se comparan en la misma forma (decisión 26).
    """
    if not desde or not hasta or len(desde) != 10 or len(hasta) != 10:
        return desde, hasta
    anio, mes = int(hasta[:4]), int(hasta[5:7])
    ultimo = f"{hasta[:7]}-{calendar.monthrange(anio, mes)[1]:02d}"
    if desde[:7] == hasta[:7] and desde.endswith("-01") and hasta == ultimo:
        return desde[:7], hasta[:7]
    if desde[:4] == hasta[:4] and desde[5:] == "01-01" and hasta[5:] == "12-31":
        return desde[:4], hasta[:4]
    return desde, hasta


class SalidaExtraccion(BaseModel):
    afirmaciones: list[Afirmacion] = Field(max_length=10)


class SalidaExplicacion(BaseModel):
    explicacion: str = Field(min_length=10, max_length=800)


class Grupo(BaseModel):
    titulo: str = Field(min_length=3, max_length=120, pattern=r"^[^0-9]+$")
    etiqueta: str = Field(pattern=r"^[a-z_]{2,50}$")
    articulos: list[str] = Field(min_length=1)


class SalidaAgrupacion(BaseModel):
    grupos: list[Grupo] = Field(max_length=20)


# Decisión 34: la guía no lleva cifras ni palabras de juicio (lo mismo exige la base en guia_redactada).
JUICIOS = re.compile(r"(mentir|mentira|falso|falsa|enga[ñn]|manipul|propaganda|desinform|miente)", re.I)
# Tampoco califica la cifra ni dice de dónde sale: eso no lo decidió ninguna regla (revisión de la v1).
CALIFICA = re.compile(r"(confiable|fiable|ver[ií]dic|fidedign|proviene)", re.I)


class SalidaGuia(BaseModel):
    guia: str = Field(min_length=40, max_length=700)

    @field_validator("guia")
    @classmethod
    def _limpia(cls, v: str) -> str:
        v = " ".join(v.split())
        if re.search(r"[0-9]", v):
            raise ValueError("la guía no puede llevar cifras")
        if JUICIOS.search(v) or CALIFICA.search(v):
            raise ValueError("la guía usa palabras de juicio o califica la cifra")
        if len(v.split()) > 80:
            raise ValueError("la guía es demasiado larga")
        return v


class SalidaJuez(BaseModel):
    neutral: bool
    agrega_hechos: bool
    motivo: str = Field(default="", max_length=400)


class Declaracion(BaseModel):
    actor: str = Field(min_length=2, max_length=120)
    texto_citado: str = Field(min_length=5, max_length=1000)


class SalidaDeclaraciones(BaseModel):
    declaraciones: list[Declaracion] = Field(max_length=20)


def _json(texto: str) -> dict:
    """El JSON de la respuesta, aunque venga entre ``` o con texto alrededor."""
    limpio = texto.strip()
    if "```" in limpio:
        limpio = re.sub(r"^.*?```(?:json)?\s*|\s*```.*$", "", limpio, flags=re.S)
    inicio, fin = limpio.find("{"), limpio.rfind("}")
    if inicio < 0 or fin < inicio:
        raise SalidaInvalida("la respuesta no contiene JSON")
    try:
        return json.loads(limpio[inicio:fin + 1])
    except json.JSONDecodeError as exc:
        raise SalidaInvalida(f"JSON mal formado: {exc}") from exc


def validar(tipo: str, texto_respuesta: str, entrada: dict) -> dict:
    """Valida la salida contra el formato fijo y contra la entrada. Devuelve el dict limpio."""
    datos = _json(texto_respuesta)
    try:
        if tipo == "extraer_afirmaciones":
            salida = SalidaExtraccion.model_validate(datos)
            texto, cifras_texto = entrada["texto"], cifras(entrada["texto"])
            for a in salida.afirmaciones:
                if a.texto_citado not in texto:
                    raise SalidaInvalida("una cita no está textual en el texto")
                if Decimal(a.valor_dicho) not in cifras_texto:
                    raise SalidaInvalida(f"el valor {a.valor_dicho} no aparece en el texto")
        elif tipo == "redactar_explicacion":
            salida = SalidaExplicacion.model_validate(datos)
            permitidas = {Decimal(c).normalize() for c in entrada.get("cifras_permitidas", [])}
            sobrantes = cifras(salida.explicacion) - permitidas
            if sobrantes:
                raise SalidaInvalida(f"la explicación usa cifras que no están en la evidencia: {sorted(sobrantes)}")
        elif tipo == "agrupar_temas":
            salida = SalidaAgrupacion.model_validate(datos)
            ids = {a["id"] for a in entrada["articulos"]}
            if any(i not in ids for g in salida.grupos for i in g.articulos):
                raise SalidaInvalida("un grupo incluye un artículo que no estaba en la entrada")
        elif tipo == "extraer_declaraciones":
            salida = SalidaDeclaraciones.model_validate(datos)
            articulo = entrada["articulo"]
            fuente = "\n".join(filter(None, (articulo.get("titulo"), articulo.get("resumen"), articulo.get("texto"))))
            for d in salida.declaraciones:
                if d.texto_citado not in fuente or not cifras(d.texto_citado):
                    raise SalidaInvalida("una cita no está textual en el artículo o no tiene cifras")
        elif tipo == "redactar_guia":
            salida = SalidaGuia.model_validate(datos)
        elif tipo == "juzgar_neutralidad":
            salida = SalidaJuez.model_validate(datos)
        else:
            raise SalidaInvalida(f"tipo de trabajo desconocido: {tipo}")
    except ValidationError as exc:
        raise SalidaInvalida(f"no cumple el formato: {exc.error_count()} errores") from exc
    return salida.model_dump(mode="json")
