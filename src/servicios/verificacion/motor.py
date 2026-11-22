"""Motor de reglas: decide la conclusión de una afirmación con el dato oficial. Sin IA.

Reglas aprobadas el 21 nov 2026 (docs/diseno/08_motor_de_reglas.md):
  · la afirmación se une a una serie aprobada por indicador, variante y territorio; si no
    hay una que coincida exactamente, o falta el periodo, o el dato oficial no existe o
    está en cuarentena: SIN DATO COMPARABLE (nunca se usa algo parecido);
  · se compara con la precisión con que se dijo la cifra ("8,9" coincide con 8,94);
  · coincide -> SE SOSTIENE; no coincide -> SE DEBILITA (y se busca si la cifra
    corresponde a otra variante o a otro periodo: es la brecha de contexto);
  · si el texto dice que el indicador subió o bajó y el dato oficial fue en la dirección
    contraria frente al periodo anterior y frente al mismo periodo del año anterior ->
    SE INVIERTE; si esas dos comparaciones no están de acuerdo -> SE DEBILITA;
  · un cambio que la fuente no publica no se calcula: SIN DATO COMPARABLE.
El motor no produce cifras nuevas: solo compara las que dijo el texto con las publicadas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol

from servicios.comun.reglas_datos import es_provisional

# (indicador, variante de la afirmación) -> variante de la serie en el catálogo
VARIANTES = {
    ("inflation", "anual"): "annual",
    ("inflation", "mensual"): "monthly",
    ("inflation", "anio_corrido"): "year_to_date",
    ("unemployment", "tasa"): "monthly_rate",
    ("minimum_wage", "nominal"): "nominal",
    ("homicides", "conteo"): "monthly_count",
}
# Si el texto no dice la variante, solo se asume cuando el indicador tiene una sola.
VARIANTE_UNICA = {"unemployment": "tasa", "minimum_wage": "nominal", "homicides": "conteo"}
NOMBRE_VARIANTE = {"annual": "anual", "monthly": "mensual", "year_to_date": "año corrido", "monthly_rate": "tasa mensual",
                   "nominal": "valor nominal", "monthly_count": "conteo mensual"}
UNIDAD = {"inflation": "%", "unemployment": "%", "public_debt": "%"}
PRUEBAS = ("variante_equivocada", "periodo_limitado", "nominal_vs_real", "fuente_distinta", "dato_provisional", "nota_serie")


class DatosOficiales(Protocol):
    def candidatas(self, indicador: str, variante: str) -> list[dict]: ...
    def valor(self, codigo_serie: str, periodo: str) -> dict | None: ...
    def notas(self, codigo_serie: str, periodo: str) -> list[dict]: ...


@dataclass
class Afirmacion:
    codigo_indicador: str | None
    variante: str | None
    periodo_desde: str | None
    periodo_hasta: str | None
    territorio: str | None
    valor_dicho: Decimal | None
    unidad_dicha: str | None = None
    comparacion: str | None = "nivel"
    direccion: str | None = None
    texto_citado: str = ""


@dataclass
class Veredicto:
    conclusion: str
    codigo_serie: str | None = None
    serie: dict | None = None
    oficial: dict | None = None
    evidencia: list[tuple[str, str]] = field(default_factory=list)      # (observacion_id, rol)
    pruebas: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    motivo: str | None = None                                          # para "sin dato comparable"
    motivo_codigo: str | None = None                                   # su código (verificacion.motivo_sin_dato)
    brechas: list[str] = field(default_factory=list)                   # frases, solo con cifras de la evidencia
    referencias: list[dict] = field(default_factory=list)              # valores usados para la dirección
    precision: int = 2                                                 # decimales para mostrar el valor oficial


def decimales(valor: Decimal) -> int:
    exponente = valor.as_tuple().exponent
    return -exponente if isinstance(exponente, int) and exponente < 0 else 0


def coincide(dicho: Decimal, oficial: Decimal) -> bool:
    """Coincide si la diferencia cabe en el redondeo con que se dijo la cifra."""
    return abs(dicho - oficial) <= Decimal(5) * Decimal(10) ** (-decimales(dicho) - 1)


def para_mostrar(valor, precision: int) -> Decimal:
    """El valor oficial redondeado para leerse (decisión 27). La evidencia conserva el exacto."""
    valor = Decimal(valor)
    return valor.quantize(Decimal(1).scaleb(-precision)) if decimales(valor) > precision else valor


MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre")


def en_palabras(periodo: str) -> str:
    """'2026-08' -> 'agosto de 2026'; '2025' -> '2025'. Solo cambia la forma, no agrega cifras."""
    return periodo if len(periodo) == 4 else f"{MESES[int(periodo[5:7]) - 1]} de {periodo[:4]}"


def periodo_anterior(periodo: str) -> str:
    if len(periodo) == 4:
        return str(int(periodo) - 1)
    anio, mes = int(periodo[:4]), int(periodo[5:7])
    return f"{anio - 1}-12" if mes == 1 else f"{anio}-{mes - 1:02d}"


def mismo_periodo_anio_anterior(periodo: str) -> str:
    return f"{int(periodo[:4]) - 1}{periodo[4:]}"


def cifra(valor: Decimal) -> str:
    """Formato colombiano: 1.423.500 y 8,9."""
    texto = f"{valor:,f}" if decimales(valor) else f"{valor:,.0f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def _sin_dato(codigo: str, motivo: str) -> Veredicto:
    return Veredicto("sin_dato_comparable", motivo=motivo, motivo_codigo=codigo,
                     pruebas={p: ("no_aplica", None) for p in PRUEBAS})


def verificar(af: Afirmacion, datos: DatosOficiales, hoy: date | None = None) -> Veredicto:
    hoy = hoy or date.today()
    if af.valor_dicho is None or af.codigo_indicador is None:
        return _sin_dato("sin_cifra_indicador", "La afirmación no tiene una cifra sobre uno de los indicadores registrados.")
    variante = af.variante or VARIANTE_UNICA.get(af.codigo_indicador)
    variante_ficha = VARIANTES.get((af.codigo_indicador, variante))
    if variante_ficha is None:
        if variante:
            return _sin_dato("variante_sin_serie", "No hay una serie oficial registrada para esa variante del indicador.")
        return _sin_dato("variante_no_dicha", "El texto no dice qué variación del indicador cita.")
    if (af.territorio or "national") != "national":
        return _sin_dato("territorio_no_nacional", "Solo hay series oficiales registradas para el total nacional.")
    # Un CAMBIO del indicador (en puntos o en porcentaje) no lo publica la fuente: no se calcula. También
    # para la inflación: "1,11 puntos más" no se compara con el nivel (evaluación v1, 21 nov 2026).
    if af.comparacion in ("variacion_porcentual", "variacion_puntos"):
        return _sin_dato("cambio_no_publicado", "La fuente oficial no publica ese cambio; calcularlo no está permitido en esta versión.")
    if not af.periodo_hasta:
        return _sin_dato("periodo_no_dicho", "El texto no dice a qué periodo corresponde la cifra.")
    candidatas = datos.candidatas(af.codigo_indicador, variante_ficha)
    if not candidatas:
        return _sin_dato("indicador_sin_serie", "No hay una serie oficial aprobada para ese indicador.")

    # El periodo en la forma de la serie. "La inflación de 2025" es la variación anual a diciembre.
    periodo = af.periodo_hasta
    if candidatas[0]["frecuencia"] == "mensual" and len(periodo) == 4:
        if variante_ficha != "annual":
            return _sin_dato("total_anual_calculado", "La serie oficial es mensual y el texto habla del año completo; sumarla o promediarla sería un cálculo propio.")
        periodo = f"{periodo}-12"
    elif candidatas[0]["frecuencia"] == "anual":
        periodo = periodo[:4]
    periodo = periodo[:7]

    serie, obs = None, None
    for candidata in candidatas:        # primero la serie que viene directa del productor
        obs = datos.valor(candidata["codigo"], periodo)
        if obs is not None:
            serie = {**candidata, "unidad": UNIDAD.get(af.codigo_indicador, "")}
            break
    if obs is None:
        return _sin_dato("periodo_sin_dato", f"No hay un dato oficial aceptado para el periodo {af.periodo_hasta} en las series registradas.")

    v = Veredicto("se_sostiene", codigo_serie=serie["codigo"], serie=serie, oficial={**obs, "periodo": periodo},
                  evidencia=[(obs["observacion_id"], "citada")], pruebas={p: ("sin_brecha", None) for p in PRUEBAS})
    v.pruebas["nominal_vs_real"] = ("no_aplica", None)
    v.pruebas["fuente_distinta"] = ("no_aplica", None)
    v.pruebas["variante_equivocada"] = ("no_aplica", None)
    oficial = Decimal(obs["valor"])
    unidad = serie["unidad"]
    dicho = Decimal(af.valor_dicho)
    # Se muestra con los decimales con que se dijo la cifra (mínimo 1 en porcentajes, máximo 2).
    v.precision = min(2, max(decimales(dicho), 1 if unidad == "%" else 0))
    mostrar = lambda x: cifra(para_mostrar(x, v.precision))

    # Dirección: frente al periodo anterior y al mismo periodo del año anterior.
    direccion_mixta = False
    if af.direccion in ("sube", "baja"):
        esperado = 1 if af.direccion == "sube" else -1
        signos = []
        for ref_periodo in dict.fromkeys((periodo_anterior(periodo), mismo_periodo_anio_anterior(periodo))):
            if ref_periodo == periodo:
                continue
            ref = datos.valor(serie["codigo"], ref_periodo)
            if ref is None:
                continue
            v.evidencia.append((ref["observacion_id"], "completa"))
            v.referencias.append({**ref, "periodo": ref_periodo})
            diferencia = oficial - Decimal(ref["valor"])
            signos.append((diferencia > 0) - (diferencia < 0))
        if signos and all(s == -esperado for s in signos):
            v.conclusion = "se_invierte"
            refs = " y ".join(f"{mostrar(r['valor'])}{unidad} en {en_palabras(r['periodo'])}" for r in v.referencias)
            v.brechas.append(f"El texto dice que {'subió' if esperado > 0 else 'bajó'}, pero según los datos oficiales "
                             f"{'bajó' if esperado > 0 else 'subió'}: en {en_palabras(periodo)} fue {mostrar(oficial)}{unidad}, "
                             f"frente a {refs}.")
        elif signos and any(s == -esperado for s in signos):
            direccion_mixta = True
            v.pruebas["periodo_limitado"] = ("con_brecha", "La dirección depende del periodo con que se compare.")
            v.brechas.append("Que haya subido o bajado depende del periodo con que se compare: frente al mes anterior y "
                             "frente al mismo mes del año anterior el resultado no es el mismo.")

    if v.conclusion != "se_invierte":
        if coincide(dicho, oficial):
            v.conclusion = "se_debilita" if direccion_mixta else "se_sostiene"
        else:
            v.conclusion = "se_debilita"
            _buscar_brecha(af, datos, dicho, periodo, serie, v, unidad)

    # Avisos que no cambian la conclusión.
    if es_provisional(af.codigo_indicador, periodo, hoy):
        v.pruebas["dato_provisional"] = ("con_brecha", f"El dato de {periodo} es provisional hasta abril del año siguiente.")
        v.brechas.append(f"El dato oficial de {en_palabras(periodo)} todavía es provisional y puede cambiar.")
    # Las notas oficiales de un periodo describen la medición, no el canal: se buscan en todas las series
    # del mismo indicador y variante (p. ej., la nota del DANE sobre agosto de 2026 guardada en la copia de
    # SUAMECA también acompaña la serie que publica el DANE directamente).
    notas, vistas = [], set()
    for candidata in candidatas:
        for nota in datos.notas(candidata["codigo"], periodo):
            if nota["clave_nota"] not in vistas:
                vistas.add(nota["clave_nota"])
                notas.append(nota)
    if notas:
        v.pruebas["nota_serie"] = ("con_brecha", ", ".join(n["clave_nota"] for n in notas))
        v.brechas.append("La serie tiene una nota oficial para ese periodo que conviene leer junto al dato.")
    return v


def _buscar_brecha(af, datos, dicho, periodo, serie, v, unidad) -> None:
    """La cifra no coincide: ¿corresponde a otra variante del mismo periodo, o al mismo dato de otro periodo?"""
    v.pruebas["variante_equivocada"] = ("sin_brecha", None)
    for (indicador, _), otra in VARIANTES.items():
        if indicador != af.codigo_indicador or otra == VARIANTES.get((indicador, af.variante or VARIANTE_UNICA.get(indicador))):
            continue
        for candidata in datos.candidatas(indicador, otra):
            ref = datos.valor(candidata["codigo"], periodo)
            if ref is not None and coincide(dicho, Decimal(ref["valor"])):
                v.evidencia.append((ref["observacion_id"], "contraste"))
                v.pruebas["variante_equivocada"] = ("con_brecha", f"Corresponde a la variación {NOMBRE_VARIANTE[otra]}.")
                v.brechas.append(f"La cifra {cifra(dicho)}{unidad} corresponde a la variación {NOMBRE_VARIANTE[otra]} "
                                 f"de {en_palabras(periodo)}, no a la que dice el texto.")
                return
    for desplazamiento in range(1, 13):
        cercano = periodo
        for _ in range(desplazamiento):
            cercano = periodo_anterior(cercano)
        ref = datos.valor(serie["codigo"], cercano)
        if ref is not None and coincide(dicho, Decimal(ref["valor"])):
            v.evidencia.append((ref["observacion_id"], "contraste"))
            v.pruebas["periodo_limitado"] = ("con_brecha", f"Corresponde a {cercano}.")
            v.brechas.append(f"La cifra {cifra(dicho)}{unidad} es el dato oficial de {en_palabras(cercano)}, "
                             f"no de {en_palabras(periodo)}.")
            return
    v.brechas.append(f"El texto dice {cifra(dicho)}{unidad}; el dato oficial de {en_palabras(periodo)} es "
                     f"{cifra(para_mostrar(v.oficial['valor'], v.precision))}{unidad}.")


def explicacion_de_respaldo(af: Afirmacion, v: Veredicto) -> str:
    """Explicación armada por reglas, para cuando la IA no redacta: solo usa cifras de la evidencia."""
    if v.conclusion == "sin_dato_comparable":
        return f"No hay dato comparable. {v.motivo}"
    unidad = v.serie["unidad"]
    base = (f"Según {v.serie['fuente']}, el dato oficial de {en_palabras(v.oficial['periodo'])} es "
            f"{cifra(para_mostrar(v.oficial['valor'], v.precision))}{unidad}.")
    if v.conclusion == "se_sostiene":
        return " ".join([f"El texto dice {cifra(Decimal(af.valor_dicho))}{unidad}.", base,
                         "La cifra coincide con la fuente oficial."] + v.brechas)
    if v.conclusion == "se_invierte":
        texto = " ".join(v.brechas)
        return f"Según {v.serie['fuente']}, {texto[0].lower()}{texto[1:]}"
    return " ".join([base] + v.brechas)
