"""Bridge between the connectors' English values and the Spanish values stored in PostgreSQL.

The database uses Spanish names (decision 14, docs/diseno/glosario_codigo.md); the
connectors and the domain stay in English. Every value crosses this module in both
directions, so a value missing here fails loudly instead of being stored wrong.
Catalog codes (series, indicators, sources, territories) are not translated.
"""

from __future__ import annotations

from app.domain import ContrastLevel, ContrastStatus, Flag, ObservationStatus

OBSERVATION_STATUS = {ObservationStatus.QUARANTINED: "en_cuarentena", ObservationStatus.ACCEPTED: "aceptada"}

CONTRAST_STATUS = {
    ContrastStatus.PASSED: "paso",
    ContrastStatus.PENDING: "pendiente",
    ContrastStatus.NOT_APPLICABLE: "no_aplica",
    ContrastStatus.UNAVAILABLE: "no_disponible",
    ContrastStatus.FAILED: "fallo",
}

LEVEL = {ContrastLevel.MONTHLY: "mensual", ContrastLevel.ANNUAL: "anual"}

FLAG = {
    Flag.MISSING_VALUE: "valor_faltante",
    Flag.OUT_OF_RANGE: "fuera_de_rango",
    Flag.GAP_BEFORE: "hueco_anterior",
    Flag.DUPLICATE: "duplicada",
    Flag.JUMP: "salto",
    Flag.NOT_INCREASING: "no_creciente",
    Flag.CONTRAST_PENDING: "contraste_pendiente",
    Flag.CONTRAST_MISMATCH: "contraste_no_coincide",
    Flag.NO_SECOND_SOURCE: "sin_segunda_fuente",
    Flag.CONTRAST_UNAVAILABLE: "contraste_no_disponible",
    Flag.KNOWN_VERSION_DIFFERENCE: "diferencia_version_conocida",
    Flag.PRODUCER_VALUE_USED: "valor_productor_usado",
    Flag.HISTORY_CHANGED: "historia_cambio",
}

APPROVAL_STATUS = {"pending": "pendiente", "approved": "aprobada", "rejected": "rechazada"}
SOURCE_ROLE = {"producer": "productor", "access_channel": "canal_acceso"}
CATEGORY = {"economy": "economia", "security": "seguridad"}
FREQUENCY = {"monthly": "mensual", "annual": "anual"}

SYSTEM_ACTOR = "sistema"


def to_db(table: dict, value):
    """English value -> Spanish value; KeyError if the value is unknown."""
    return table[value]


def from_db(table: dict, value):
    """Spanish value -> English value; KeyError if the value is unknown."""
    for english, spanish in table.items():
        if spanish == value:
            return english
    raise KeyError(value)
