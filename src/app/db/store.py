"""PostgreSQL implementation of the ObservationStore protocol (source of truth for data, contrasts and alerts)."""

from __future__ import annotations

from collections.abc import Sequence

import psycopg

from app.domain import (
    ALERT_FLAGS,
    ContrastStatus,
    Download,
    Observation,
    Period,
    RawFileRef,
)
from app.db.vocabulary import (
    CONTRAST_STATUS,
    FLAG,
    LEVEL,
    OBSERVATION_STATUS,
    SYSTEM_ACTOR,
    from_db,
    to_db,
)
from app.storage.observations import Key


class SeriesNotSynced(Exception):
    """The series is not in the database: run the catalog sync (app.db.sync) first."""


class PostgresObservationStore:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def add(self, download: Download, observations: Sequence[Observation]) -> None:
        if any(o.download_id != download.id for o in observations):
            raise ValueError("observations must belong to the download being added")
        with self.conn.transaction():
            series_id = self._series_id(download.series_code)
            self.conn.execute(
                "INSERT INTO oficial.descarga (id, serie_id, canal, descargado_en, actualizado_fuente) VALUES (%s, %s, %s, %s, %s)",
                (download.id, series_id, download.channel, download.downloaded_at, download.source_updated),
            )
            for ref in download.raw_files:
                self.conn.execute(
                    "INSERT INTO oficial.archivo_original (descarga_id, nombre, url, sha256, ubicacion) VALUES (%s, %s, %s, %s, %s)",
                    (download.id, ref.name, ref.url, ref.sha256, ref.location),
                )
            for obs in observations:
                self._insert_observation(series_id, obs)

    def downloads(self, series_code: str) -> list[Download]:
        rows = self.conn.execute(
            "SELECT d.id, d.canal, d.descargado_en, d.actualizado_fuente FROM oficial.descarga d"
            " JOIN oficial.serie s ON s.id = d.serie_id WHERE s.codigo = %s ORDER BY d.creado_en, d.descargado_en",
            (series_code,),
        ).fetchall()
        files: dict[str, list[RawFileRef]] = {}
        for download_id, name, url, sha, location in self.conn.execute(
            "SELECT f.descarga_id, f.nombre, f.url, f.sha256, f.ubicacion FROM oficial.archivo_original f"
            " JOIN oficial.descarga d ON d.id = f.descarga_id JOIN oficial.serie s ON s.id = d.serie_id"
            " WHERE s.codigo = %s ORDER BY f.creado_en, f.nombre",
            (series_code,),
        ):
            files.setdefault(str(download_id), []).append(RawFileRef(name, url, sha, location))
        return [
            Download(str(i), series_code, channel, at, tuple(files.get(str(i), ())), updated)
            for i, channel, at, updated in rows
        ]

    def latest(self, series_code: str, *, include_quarantined: bool = False) -> dict[Key, Observation]:
        status_filter = "" if include_quarantined else "AND o.estado = 'aceptada'"
        rows = self.conn.execute(
            f"""
            SELECT DISTINCT ON (o.periodo, o.territorio)
                   o.id, o.descarga_id, o.periodo, o.territorio, o.valor, o.estado,
                   o.estado_contraste, o.nivel_contraste, o.marcas
            FROM oficial.observacion o JOIN oficial.serie s ON s.id = o.serie_id
            WHERE s.codigo = %s {status_filter}
            ORDER BY o.periodo, o.territorio, o.secuencia DESC
            """,
            (series_code,),
        ).fetchall()
        result = {}
        for obs_id, download_id, period, territory, value, status, contrast, level, flags in rows:
            obs = Observation(
                id=str(obs_id),
                series_code=series_code,
                download_id=str(download_id),
                period=Period.parse(period),
                territory=territory,
                value=value,
                status=from_db(OBSERVATION_STATUS, status),
                contrast=from_db(CONTRAST_STATUS, contrast),
                contrast_level=from_db(LEVEL, level) if level else None,
                flags=frozenset(from_db(FLAG, f) for f in flags),
            )
            result[(obs.period, obs.territory)] = obs
        return result

    def open_alerts(self, series_code: str) -> list[tuple[str, str, str]]:
        """(period, territory, kind) of the open alerts of a series; kind is the English flag value."""
        return [
            (period, territory, from_db(FLAG, kind).value)
            for period, territory, kind in self.conn.execute(
                "SELECT periodo, territorio, tipo FROM oficial.alertas_abiertas(%s)", (series_code,)
            )
        ]

    def _series_id(self, code: str):
        row = self.conn.execute("SELECT id FROM oficial.serie WHERE codigo = %s", (code,)).fetchone()
        if row is None:
            raise SeriesNotSynced(f"series {code!r} is not in the database; run the catalog sync first")
        return row[0]

    def _insert_observation(self, series_id, obs: Observation) -> None:
        self.conn.execute(
            "INSERT INTO oficial.observacion (id, serie_id, descarga_id, periodo, territorio, valor, estado,"
            " estado_contraste, nivel_contraste, marcas) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (obs.id, series_id, obs.download_id, str(obs.period), obs.territory, obs.value,
             to_db(OBSERVATION_STATUS, obs.status), to_db(CONTRAST_STATUS, obs.contrast),
             to_db(LEVEL, obs.contrast_level) if obs.contrast_level else None,
             sorted(to_db(FLAG, f) for f in obs.flags)),
        )
        for check in obs.contrast_checks:
            self.conn.execute(
                "INSERT INTO oficial.comparacion_contraste (observacion_id, fuente, nivel, periodo_comparado, valor_fuente,"
                " valor_serie, tolerancia, resultado, diferencia_conocida) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (obs.id, check.source, to_db(LEVEL, check.level), str(check.compared_period), check.source_value,
                 check.series_value, check.tolerance, to_db(CONTRAST_STATUS, ContrastStatus(check.outcome)),
                 check.known_difference),
            )
        for flag in sorted(obs.flags & ALERT_FLAGS):
            row = self.conn.execute(
                "INSERT INTO oficial.alerta (serie_id, observacion_id, periodo, territorio, tipo, valor)"
                " VALUES (%s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (serie_id, periodo, territorio, tipo, valor) WHERE estado = 'abierta' DO NOTHING RETURNING id",
                (series_id, obs.id, str(obs.period), obs.territory, to_db(FLAG, flag), obs.value),
            ).fetchone()
            if row is not None:
                self.conn.execute(
                    "INSERT INTO oficial.evento_alerta (alerta_id, evento, actor, motivo) VALUES (%s, 'abierta', %s, %s)",
                    (row[0], SYSTEM_ACTOR, f"marca {to_db(FLAG, flag)} en {obs.period}"),
                )
