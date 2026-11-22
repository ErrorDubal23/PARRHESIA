"""Copy what git owns into PostgreSQL: fichas, approvals, series notes, known differences, evidence manifests.

Git is the source of truth for these (docs/PROYECTO.md); the database copy is
rewritten on every run and never edited by hand. Approvals and evidence lines
are only ever added, so their history survives later changes in git.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from pydantic import ValidationError

from app.catalog import CATALOG_DIR, Ficha, load_ficha
from app.domain import Period
from app.db.vocabulary import APPROVAL_STATUS, CATEGORY, FREQUENCY, LEVEL, SOURCE_ROLE, to_db
from app.evidence import EVIDENCE_DIR, EvidenceManifest

# Indicator categories of the v1 scope (docs/PROYECTO.md, section 4).
CATEGORIES = {
    "inflation": "economy",
    "unemployment": "economy",
    "minimum_wage": "economy",
    "public_debt": "economy",
    "homicides": "security",
    "theft": "security",
    "extortion": "security",
    "kidnapping": "security",
}


@dataclass
class SyncReport:
    series: list[str] = field(default_factory=list)
    skipped_drafts: list[str] = field(default_factory=list)  # fichas that do not load as connectable
    evidence_lines: int = 0


def sync_catalog(conn: psycopg.Connection, catalog_dir: Path = CATALOG_DIR) -> SyncReport:
    report = SyncReport()
    with conn.transaction():
        for path in sorted(catalog_dir.glob("*.yaml")):
            try:
                ficha = load_ficha(path)
            except ValidationError:
                report.skipped_drafts.append(path.stem)
                continue
            _sync_series(conn, ficha)
            report.series.append(ficha.code)
    return report


def sync_evidence(conn: psycopg.Connection, evidence_dir: Path = EVIDENCE_DIR) -> int:
    inserted = 0
    with conn.transaction():
        for path in sorted(evidence_dir.glob("*.jsonl")):
            for record in EvidenceManifest(path).records():
                cursor = conn.execute(
                    "INSERT INTO oficial.archivo_evidencia (manifiesto, fuente, url, descargado_en, sha256, tamano, ubicacion,"
                    " cambio, ultima_modificacion)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (path.stem, record.source, record.url, record.downloaded_at, record.sha256, record.size,
                     record.location, record.changed, record.last_modified),
                )
                inserted += cursor.rowcount
    return inserted


def sync_all(conn: psycopg.Connection) -> SyncReport:
    report = sync_catalog(conn)
    report.evidence_lines = sync_evidence(conn)
    return report


def _source(conn, code: str, role: str):
    return conn.execute(
        "INSERT INTO oficial.fuente (codigo, nombre, rol) VALUES (%s, %s, %s)"
        " ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre, rol = EXCLUDED.rol RETURNING id",
        (code, code, to_db(SOURCE_ROLE, role)),
    ).fetchone()[0]


def _sync_series(conn, ficha: Ficha) -> None:
    category = CATEGORIES.get(ficha.indicator)
    if category is None:
        raise ValueError(f"{ficha.code}: indicator {ficha.indicator!r} is outside the v1 scope")
    indicator_id = conn.execute(
        "INSERT INTO oficial.indicador (codigo, categoria) VALUES (%s, %s)"
        " ON CONFLICT (codigo) DO UPDATE SET categoria = EXCLUDED.categoria RETURNING id",
        (ficha.indicator, to_db(CATEGORY, category)),
    ).fetchone()[0]
    producer_id = _source(conn, ficha.producer, "producer")
    channel_id = _source(conn, ficha.access_channel, "access_channel")
    series_id = conn.execute(
        """
        INSERT INTO oficial.serie (codigo, indicador_id, fuente_productora_id, fuente_canal_id, variante, nombre,
                                   unidad, etiqueta_unidad, frecuencia, geografia, huella_contenido, aprobada)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (codigo) DO UPDATE SET
            indicador_id = EXCLUDED.indicador_id, fuente_productora_id = EXCLUDED.fuente_productora_id,
            fuente_canal_id = EXCLUDED.fuente_canal_id, variante = EXCLUDED.variante,
            nombre = EXCLUDED.nombre, unidad = EXCLUDED.unidad, etiqueta_unidad = EXCLUDED.etiqueta_unidad,
            frecuencia = EXCLUDED.frecuencia, geografia = EXCLUDED.geografia,
            huella_contenido = EXCLUDED.huella_contenido, aprobada = EXCLUDED.aprobada
        RETURNING id
        """,
        (ficha.code, indicator_id, producer_id, channel_id, ficha.variant, ficha.name, ficha.model_extra.get("unit", ""),
         ficha.unit_label, to_db(FREQUENCY, ficha.frequency), ficha.geography, ficha.content_sha256, ficha.is_approved),
    ).fetchone()[0]

    a = ficha.approval
    conn.execute(
        "INSERT INTO oficial.aprobacion_serie (serie_id, estado, huella_contenido, aprobada_por, aprobada_el, comentarios)"
        " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (series_id, to_db(APPROVAL_STATUS, a.status), a.content_sha256, a.approved_by, a.approved_on, (a.model_extra or {}).get("comments")),
    )

    conn.execute("DELETE FROM oficial.nota_serie WHERE serie_id = %s", (series_id,))
    for index, note in enumerate(ficha.model_extra.get("series_notes") or [], start=1):
        conn.execute(
            "INSERT INTO oficial.nota_serie (serie_id, clave_nota, tipo, vigente_desde, vigente_hasta, estado, contenido)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (series_id, note.get("id") or f"note_{index}", note["type"], _period_text(note.get("valid_from")),
             _period_text(note.get("valid_to")), note["status"], json.dumps(note, ensure_ascii=False, default=str)),
        )

    conn.execute("DELETE FROM oficial.diferencia_version WHERE serie_id = %s", (series_id,))
    for d in ficha.known_version_differences:
        conn.execute(
            "INSERT INTO oficial.diferencia_version (serie_id, periodo, nivel, fuente, valor_fuente, valor_serie)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (series_id, str(d.period), to_db(LEVEL, d.level), d.source, d.source_value, d.series_value),
        )


def _period_text(value) -> str | None:
    return None if value is None else str(Period.parse(value))
