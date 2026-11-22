"""Motor de reglas (sin IA ni base): cada regla aprobada el 21 nov 2026 tiene su prueba."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from servicios.verificacion.motor import Afirmacion, coincide, explicacion_de_respaldo, verificar

SERIES = {
    ("unemployment", "monthly_rate"): [{"codigo": "dane_desempleo", "nombre": "Tasa de desempleo", "frecuencia": "mensual",
                                        "fuente": "DANE", "directa_del_productor": True},
                                       {"codigo": "suameca_desempleo", "nombre": "Tasa de desempleo (SUAMECA)",
                                        "frecuencia": "mensual", "fuente": "DANE", "directa_del_productor": False}],
    ("inflation", "annual"): [{"codigo": "ipc_anual", "nombre": "IPC anual", "frecuencia": "mensual", "fuente": "DANE",
                               "directa_del_productor": True}],
    ("inflation", "monthly"): [{"codigo": "ipc_mensual", "nombre": "IPC mensual", "frecuencia": "mensual", "fuente": "DANE",
                                "directa_del_productor": True}],
    ("homicides", "monthly_count"): [{"codigo": "homicidios", "nombre": "Homicidios", "frecuencia": "mensual",
                                      "fuente": "Policía Nacional", "directa_del_productor": True}],
}
VALORES = {
    "dane_desempleo": {"2025-08": "8.6", "2026-07": "8.1", "2026-08": "9.4"},
    "suameca_desempleo": {"2025-08": "8.6", "2026-07": "8.1", "2026-08": "9.4", "2026-09": "8.9"},
    "ipc_anual": {"2025-12": "5.20", "2026-08": "4.91", "2026-09": "4.75"},
    "ipc_mensual": {"2026-09": "0.32"},
    "homicidios": {"2026-08": "1203"},
}


class Datos:
    def __init__(self, notas=None):
        self._notas = notas or {}

    def candidatas(self, indicador, variante):
        return SERIES.get((indicador, variante), [])

    def valor(self, codigo, periodo):
        v = VALORES.get(codigo, {}).get(periodo)
        return None if v is None else {"observacion_id": f"{codigo}:{periodo}", "valor": v, "marcas": []}

    def notas(self, codigo, periodo):
        return self._notas.get((codigo, periodo), [])


def af(indicador="unemployment", variante="tasa", periodo="2026-08", valor="9.4", **otros):
    return Afirmacion(indicador, variante, periodo, periodo, "national", Decimal(valor), **otros)


def test_rounding_as_stated():
    assert coincide(Decimal("8.9"), Decimal("8.94")) and not coincide(Decimal("8.9"), Decimal("8.96"))
    assert coincide(Decimal("9"), Decimal("8.6")) and not coincide(Decimal("9"), Decimal("8.4"))
    assert coincide(Decimal("1203"), Decimal("1203")) and not coincide(Decimal("1200"), Decimal("1203"))


def test_matching_figure_holds_and_uses_the_producer_series():
    v = verificar(af(), Datos())
    assert v.conclusion == "se_sostiene" and v.codigo_serie == "dane_desempleo"
    assert v.evidencia == [("dane_desempleo:2026-08", "citada")]


def test_channel_series_is_used_only_when_the_producer_has_no_value():
    v = verificar(af(periodo="2026-09", valor="8.9"), Datos())
    assert v.conclusion == "se_sostiene" and v.codigo_serie == "suameca_desempleo"


def test_figure_from_another_period_weakens_and_says_which():
    v = verificar(af(valor="8.1"), Datos())
    assert v.conclusion == "se_debilita"
    assert v.pruebas["periodo_limitado"] == ("con_brecha", "Corresponde a 2026-07.")
    assert ("dane_desempleo:2026-07", "contraste") in v.evidencia


def test_figure_from_another_variant_weakens_and_says_which():
    v = verificar(af("inflation", "anual", "2026-09", "0.32"), Datos())
    assert v.conclusion == "se_debilita" and v.pruebas["variante_equivocada"][0] == "con_brecha"
    assert "mensual" in v.brechas[0]


def test_unexplained_difference_weakens():
    v = verificar(af(valor="7.0"), Datos())
    assert v.conclusion == "se_debilita" and v.brechas == ["El texto dice 7,0%; el dato oficial de agosto de 2026 es 9,4%."]


def test_opposite_direction_against_both_references_reverses():
    # "El desempleo bajó a 9,4 % en agosto": subió frente a julio (8,1) y frente a agosto de 2025 (8,6).
    v = verificar(af(direccion="baja"), Datos())
    assert v.conclusion == "se_invierte"
    assert {rol for _, rol in v.evidencia} == {"citada", "completa"}


def test_direction_that_depends_on_the_comparison_weakens():
    VALORES["dane_desempleo"]["2026-07"] = "9.6"  # bajó frente a julio, subió frente a agosto de 2025
    try:
        v = verificar(af(direccion="baja"), Datos())
        assert v.conclusion == "se_debilita" and v.pruebas["periodo_limitado"][0] == "con_brecha"
    finally:
        VALORES["dane_desempleo"]["2026-07"] = "8.1"


def test_annual_inflation_of_a_year_means_december():
    assert verificar(af("inflation", "anual", "2025", "5.2"), Datos()).conclusion == "se_sostiene"


def test_never_approximates():
    sin_dato = lambda a: verificar(a, Datos())
    assert sin_dato(af(periodo="2026-11")).conclusion == "sin_dato_comparable"            # periodo sin dato
    assert sin_dato(af(periodo=None)).motivo == "El texto no dice a qué periodo corresponde la cifra."
    assert sin_dato(af("inflation", None, "2026-09", "4.75")).conclusion == "sin_dato_comparable"  # variante no dicha
    en_bogota = Afirmacion("unemployment", "tasa", "2026-08", "2026-08", "bogotá", Decimal("9.4"))
    assert sin_dato(en_bogota).conclusion == "sin_dato_comparable"                         # solo hay series nacionales
    assert sin_dato(af("homicides", "conteo", "2025", "13000")).conclusion == "sin_dato_comparable"  # sumar meses = cálculo
    assert sin_dato(af(comparacion="variacion_puntos", valor="1.3")).conclusion == "sin_dato_comparable"


def test_provisional_data_and_series_notes_are_warnings_that_do_not_change_the_conclusion():
    datos = Datos(notas={("dane_desempleo", "2026-08"): [{"clave_nota": "earthquake_adjustment_2026_08"}]})
    v = verificar(af(), datos)
    assert v.conclusion == "se_sostiene" and v.pruebas["nota_serie"][0] == "con_brecha"
    h = verificar(af("homicides", "conteo", "2026-08", "1203"), Datos(), hoy=date(2026, 11, 21))
    assert h.conclusion == "se_sostiene" and h.pruebas["dato_provisional"][0] == "con_brecha"
    assert verificar(af("homicides", "conteo", "2026-08", "1203"), Datos(), hoy=date(2027, 4, 2)).pruebas["dato_provisional"][0] == "sin_brecha"


def test_fallback_explanation_uses_only_evidence_figures():
    texto = explicacion_de_respaldo(af(valor="8.1"), verificar(af(valor="8.1"), Datos()))
    assert texto == ("Según DANE, el dato oficial de agosto de 2026 es 9,4%. "
                     "La cifra 8,1% es el dato oficial de julio de 2026, no de agosto de 2026.")
    invierte = verificar(af(direccion="baja"), Datos())
    assert explicacion_de_respaldo(af(direccion="baja"), invierte) == (
        "Según DANE, el texto dice que bajó, pero según los datos oficiales subió: en agosto de 2026 fue 9,4%, "
        "frente a 8,1% en julio de 2026 y 8,6% en agosto de 2025.")


# --- Correcciones de la evaluación v1 (21 nov 2026) -----------------------------------------------

def test_a_change_in_points_of_inflation_is_not_compared_with_its_level():
    """"1,11 puntos más que un año antes" no se compara con el 6,29 %: es un cambio que la fuente no publica."""
    v = verificar(af("inflation", "anual", "2026-09", "1.11", comparacion="variacion_puntos"), Datos(), hoy=date(2026, 11, 21))
    assert v.conclusion == "sin_dato_comparable" and "no publica ese cambio" in v.motivo


def test_a_note_on_a_sibling_series_of_the_same_measure_is_shown():
    """La nota del sismo de agosto de 2026 está en la copia de SUAMECA; debe acompañar también la serie del DANE."""
    nota = {"clave_nota": "earthquake_adjustment_2026_08", "tipo": "methodological", "estado": "confirmed", "contenido": {}}
    v = verificar(af(valor="9.4"), Datos({("suameca_desempleo", "2026-08"): [nota]}), hoy=date(2026, 11, 21))
    assert v.codigo_serie == "dane_desempleo" and v.conclusion == "se_sostiene"
    assert v.pruebas["nota_serie"] == ("con_brecha", "earthquake_adjustment_2026_08")


def test_every_no_data_answer_has_a_registered_reason():
    # Decisión 34: el motivo es un código de verificacion.motivo_sin_dato, para mostrar su guía.
    motivo = lambda a: verificar(a, Datos()).motivo_codigo
    assert motivo(af(periodo="2026-11")) == "periodo_sin_dato"
    assert motivo(af(periodo=None)) == "periodo_no_dicho"
    assert motivo(af("inflation", None, "2026-09", "4.75")) == "variante_no_dicha"
    assert motivo(Afirmacion("unemployment", "tasa", "2026-08", "2026-08", "bogotá", Decimal("9.4"))) == "territorio_no_nacional"
    assert motivo(af("homicides", "conteo", "2025", "13000")) == "total_anual_calculado"
    assert motivo(af(comparacion="variacion_puntos", valor="1.3")) == "cambio_no_publicado"
    assert motivo(af()) is None                                    # hay dato: no hay motivo
