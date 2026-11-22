"""PostgreSQL: migrations, append-only guards, catalog sync, the observation store and the oficial schema logic.

Each test session creates its own temporary database (never the development one)
and drops it at the end. Skipped when DATABASE_URL is not set or the server is down.
"""

from __future__ import annotations

import shutil
from decimal import Decimal

import psycopg
import pytest

from app.db.migrate import MIGRATIONS_DIR, MigrationError, migrate
from app.db.store import PostgresObservationStore, SeriesNotSynced
from app.db.sync import sync_catalog, sync_evidence
from app import contrasts
from app.domain import Flag, ObservationStatus, Period
from app.pipeline import ingest
from app.storage.observations import InMemoryObservationStore
from tests.conftest import approved, fixture_document, target_series


@pytest.fixture
def conn(test_db_url):
    with psycopg.connect(test_db_url, autocommit=True) as c:
        yield c
        # Each test starts from empty data tables; triggers protect them, so truncate (TRUNCATE skips row triggers).
        c.execute(
            "TRUNCATE oficial.evento_alerta, oficial.alerta, oficial.comparacion_contraste, oficial.observacion,"
            " oficial.archivo_original, oficial.descarga, oficial.archivo_evidencia, oficial.diferencia_version,"
            " oficial.nota_serie, oficial.aprobacion_serie, oficial.serie, oficial.indicador, oficial.fuente,"
            " oficial.brecha_contexto"
        )


@pytest.fixture
def synced(conn):
    sync_catalog(conn)
    return conn


@pytest.fixture
def pg_store(synced):
    return PostgresObservationStore(synced)


# Migrations


def test_migrate_is_idempotent(conn):
    assert migrate(conn) == []


def test_changed_migration_is_refused(conn, tmp_path):
    copy = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIR, copy)
    first = sorted(copy.glob("*.sql"))[0]
    first.write_text(first.read_text() + "\n-- edited after being applied\n")
    with pytest.raises(MigrationError, match="changed after it was applied"):
        migrate(conn, copy)


def test_migrations_must_be_numbered_without_gaps(conn, tmp_path):
    copy = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIR, copy)
    gap = len(list(copy.glob("*.sql"))) + 2  # skips one number
    (copy / f"{gap:04d}_skipped_one.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationError, match="without gaps"):
        migrate(conn, copy)


# Catalog sync (copy of git)


def test_sync_copies_connectable_fichas_and_skips_drafts(conn):
    report = sync_catalog(conn)
    assert "homicides_intentional_national" in report.series and len(report.series) == 8
    assert set(report.skipped_drafts) == {
        "unemployment_rate_national_as_published",
        "unemployment_rate_national_cnpv2018_recalc",
    }
    approved_count = conn.execute("SELECT count(*) FROM oficial.serie WHERE aprobada").fetchone()[0]
    assert approved_count == 8
    assert conn.execute(
        "SELECT count(*) FROM oficial.diferencia_version k JOIN oficial.serie s ON s.id = k.serie_id"
        " WHERE s.codigo = 'homicides_intentional_national'"
    ).fetchone()[0] == 11
    conflict = conn.execute(
        "SELECT estado, contenido->'sources' IS NOT NULL FROM oficial.nota_serie WHERE clave_nota = 'marco_2018_start_conflict'"
    ).fetchone()
    assert conflict == ("official_sources_in_conflict", True)


def test_sync_is_idempotent_and_keeps_approval_history(conn):
    sync_catalog(conn)
    query = "SELECT (SELECT count(*) FROM oficial.serie), (SELECT count(*) FROM oficial.aprobacion_serie)"
    counts = conn.execute(query).fetchone()
    sync_catalog(conn)
    assert conn.execute(query).fetchone() == counts


def test_sync_evidence_copies_manifest_lines_once(conn):
    first = sync_evidence(conn)
    assert first > 0
    assert sync_evidence(conn) == 0


# Append-only guards


def _wage(ficha, connector, raw_store, store):
    return ingest(approved(ficha("minimum_wage_monthly")), connector, raw_store, store)


def test_observations_cannot_be_updated_or_deleted(ficha, connector, raw_store, pg_store, synced):
    _wage(ficha, connector, raw_store, pg_store)
    with pytest.raises(psycopg.errors.RaiseException, match="solo inserción"):
        synced.execute("UPDATE oficial.observacion SET valor = 0")
    with pytest.raises(psycopg.errors.RaiseException, match="solo inserción"):
        synced.execute("DELETE FROM oficial.observacion")


def test_alert_can_only_change_status(ficha, connector, fake_suameca, raw_store, pg_store, synced):
    _wage(ficha, connector, raw_store, pg_store)
    doc = fixture_document(500023)
    target_series(doc, 15416)["data"][-2][1] = Decimal("1423501")
    fake_suameca.set(500023, doc)
    _wage(ficha, connector, raw_store, pg_store)
    with pytest.raises(psycopg.errors.RaiseException, match="solo puede cambiar el estado"):
        synced.execute("UPDATE oficial.alerta SET tipo = 'salto'")
    with pytest.raises(psycopg.errors.RaiseException, match="solo inserción"):
        synced.execute("DELETE FROM oficial.alerta")


# Store


def test_unsynced_series_is_refused(ficha, connector, raw_store, conn):
    with pytest.raises(SeriesNotSynced):
        _wage(ficha, connector, raw_store, PostgresObservationStore(conn))


def test_store_matches_in_memory_store(ficha, connector, raw_store, pg_store):
    memory = InMemoryObservationStore()
    for store in (memory, pg_store):
        _wage(ficha, connector, raw_store, store)
    mem, pg = memory.latest("minimum_wage_monthly"), pg_store.latest("minimum_wage_monthly")
    assert set(mem) == set(pg) and len(pg) == 43
    for key in mem:
        a, b = mem[key], pg[key]
        assert (a.value, a.status, a.contrast, a.contrast_level, a.flags) == (b.value, b.status, b.contrast, b.contrast_level, b.flags)
    assert pg[(Period(2026), "national")].value == Decimal("1750905.00")  # exact, as published
    [download] = pg_store.downloads("minimum_wage_monthly")
    assert download.source_updated == "07 de enero de 2026" and download.raw_files[0].name == "menu"


def test_changed_final_value_opens_one_alert_and_falls_back(ficha, connector, fake_suameca, raw_store, pg_store, synced):
    _wage(ficha, connector, raw_store, pg_store)
    doc = fixture_document(500023)
    target_series(doc, 15416)["data"][-2][1] = Decimal("1423501")
    fake_suameca.set(500023, doc)
    _wage(ficha, connector, raw_store, pg_store)
    _wage(ficha, connector, raw_store, pg_store)  # same changed value again: no second alert

    assert pg_store.open_alerts("minimum_wage_monthly") == [("2025", "national", "history_changed")]
    events = synced.execute("SELECT evento, actor FROM oficial.evento_alerta").fetchall()
    assert events == [("abierta", "sistema")]
    assert pg_store.latest("minimum_wage_monthly")[(Period(2025), "national")].value == Decimal("1423500.00")
    quarantined = pg_store.latest("minimum_wage_monthly", include_quarantined=True)[(Period(2025), "national")]
    assert quarantined.status is ObservationStatus.QUARANTINED and Flag.HISTORY_CHANGED in quarantined.flags


def test_contrast_checks_are_stored(ficha, connector, raw_store, pg_store, synced):
    unemployment = approved(ficha("unemployment_rate_national"))
    dane = {Period(2026, 8): Decimal("9.3636797215898682"), Period(2026, 7): Decimal("8.30")}  # July differs
    runner = contrasts.suameca_unemployment(unemployment, dane)
    ingest(unemployment, connector, raw_store, pg_store, contrast=runner)

    rows = {
        period: rest
        for period, *rest in synced.execute(
            "SELECT periodo_comparado, valor_fuente, valor_serie, tolerancia, resultado FROM oficial.comparacion_contraste"
        ).fetchall()
    }
    assert rows["2026-08"] == [Decimal("9.3636797215898682"), Decimal("9.36"), Decimal("0.005"), "paso"]
    assert rows["2026-07"][3] == "fallo"
    assert ("2026-07", "national", "contrast_mismatch") in pg_store.open_alerts("unemployment_rate_national")
    unavailable = synced.execute(
        "SELECT count(*) FROM oficial.observacion WHERE estado_contraste = 'no_disponible'"
    ).fetchone()[0]
    assert unavailable == 306  # every other month: no DANE value given in this test


# Esquema oficial (migración 0002): funciones, procedimientos y triggers


def _alerta_abierta(ficha, connector, fake_suameca, raw_store, pg_store, conn):
    """Ingiere el salario mínimo, cambia un valor definitivo y devuelve la alerta que se abre."""
    _wage(ficha, connector, raw_store, pg_store)
    doc = fixture_document(500023)
    target_series(doc, 15416)["data"][-2][1] = Decimal("1423501")
    fake_suameca.set(500023, doc)
    _wage(ficha, connector, raw_store, pg_store)
    return conn.execute("SELECT alerta_id FROM oficial.alertas_abiertas('minimum_wage_monthly')").fetchone()[0]


def test_tables_live_in_oficial_with_spanish_names(conn):
    tables = {r[0] for r in conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'oficial'")}
    assert tables == {
        "fuente", "indicador", "serie", "aprobacion_serie", "nota_serie", "diferencia_version", "archivo_evidencia",
        "brecha_contexto", "descarga", "archivo_original", "observacion", "comparacion_contraste", "alerta",
        "evento_alerta", "consulta_fuente",
    }
    left_in_public = conn.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name <> 'schema_migrations'"
    ).fetchone()[0]
    assert left_in_public == 0


def test_check_constraints_reject_english_values(ficha, connector, raw_store, pg_store, synced):
    _wage(ficha, connector, raw_store, pg_store)
    with pytest.raises(psycopg.errors.CheckViolation, match="observacion_estado_valido"):
        synced.execute(
            "INSERT INTO oficial.observacion (id, serie_id, descarga_id, periodo, territorio, valor, estado, estado_contraste)"
            " SELECT gen_random_uuid(), serie_id, descarga_id, '2099', territorio, 1, 'accepted', 'paso'"
            " FROM oficial.observacion LIMIT 1"
        )


def test_current_values_skip_a_quarantined_latest_version(ficha, connector, fake_suameca, raw_store, pg_store, synced):
    _alerta_abierta(ficha, connector, fake_suameca, raw_store, pg_store, synced)
    vigentes = dict(
        (periodo, valor) for periodo, valor in synced.execute(
            "SELECT periodo, valor FROM oficial.observaciones_vigentes('minimum_wage_monthly', '2024', '2026')")
    )
    assert vigentes == {"2024": Decimal("1300000.00"), "2026": Decimal("1750905.00")}  # 2025 changed: in quarantine
    assert synced.execute(
        "SELECT count(*) FROM oficial.observacion_en('minimum_wage_monthly', '2025', 'national')").fetchone()[0] == 0
    [latest_2026] = synced.execute(
        "SELECT observacion_id FROM oficial.observacion_en('minimum_wage_monthly', '2026', 'national')").fetchone()
    assert synced.execute("SELECT oficial.esta_aceptada(%s)", (latest_2026,)).fetchone()[0] is True
    quarantined = synced.execute(
        "SELECT id FROM oficial.observacion WHERE periodo = '2025' ORDER BY secuencia DESC LIMIT 1").fetchone()[0]
    assert synced.execute("SELECT oficial.esta_aceptada(%s)", (quarantined,)).fetchone()[0] is False
    assert synced.execute("SELECT oficial.serie_aprobada('minimum_wage_monthly')").fetchone()[0] is True
    assert synced.execute("SELECT oficial.serie_aprobada('no_existe')").fetchone()[0] is False


def test_close_and_reopen_alert_keep_their_events(ficha, connector, fake_suameca, raw_store, pg_store, synced):
    alerta = _alerta_abierta(ficha, connector, fake_suameca, raw_store, pg_store, synced)
    synced.execute("CALL oficial.cerrar_alerta(%s, 'Dubal', 'El decreto confirma el valor')", (alerta,))
    synced.execute("CALL oficial.reabrir_alerta(%s, 'Dubal', 'Se revisa de nuevo')", (alerta,))
    eventos = synced.execute(
        "SELECT evento, actor FROM oficial.evento_alerta WHERE alerta_id = %s ORDER BY creado_en, evento", (alerta,)
    ).fetchall()
    assert [e for e, _ in eventos] == ["abierta", "cerrada", "reabierta"]
    with pytest.raises(psycopg.errors.RaiseException, match="alerta_no_cerrada"):
        synced.execute("CALL oficial.reabrir_alerta(%s, 'Dubal', 'otra vez')", (alerta,))
    with pytest.raises(psycopg.errors.RaiseException, match="alerta_sin_motivo"):
        synced.execute("CALL oficial.cerrar_alerta(%s, 'Dubal', '  ')", (alerta,))


def test_alert_status_change_without_event_is_refused_at_commit(ficha, connector, fake_suameca, raw_store, pg_store, synced):
    alerta = _alerta_abierta(ficha, connector, fake_suameca, raw_store, pg_store, synced)
    with pytest.raises(psycopg.errors.RaiseException, match="no tiene su evento"):
        with synced.transaction():
            synced.execute("UPDATE oficial.alerta SET estado = 'cerrada' WHERE id = %s", (alerta,))
    assert synced.execute("SELECT estado FROM oficial.alerta WHERE id = %s", (alerta,)).fetchone()[0] == "abierta"


def test_two_reviewers_cannot_close_the_same_alert_twice(test_db_url, ficha, connector, fake_suameca, raw_store, pg_store, synced):
    alerta = _alerta_abierta(ficha, connector, fake_suameca, raw_store, pg_store, synced)
    with psycopg.connect(test_db_url) as a, psycopg.connect(test_db_url) as b:
        a.execute("CALL oficial.cerrar_alerta(%s, 'Revisor A', 'motivo A')", (alerta,))  # A holds the row lock
        b.execute("SET lock_timeout = '200ms'")
        with pytest.raises(psycopg.errors.LockNotAvailable):
            b.execute("CALL oficial.cerrar_alerta(%s, 'Revisor B', 'motivo B')", (alerta,))
        a.commit()
    with psycopg.connect(test_db_url) as b:
        with pytest.raises(psycopg.errors.RaiseException, match="alerta_no_abierta"):
            b.execute("CALL oficial.cerrar_alerta(%s, 'Revisor B', 'motivo B')", (alerta,))
    cierres = synced.execute(
        "SELECT count(*) FROM oficial.evento_alerta WHERE alerta_id = %s AND evento = 'cerrada'", (alerta,)).fetchone()[0]
    assert cierres == 1


def test_state_machine_rejects_invalid_transitions(conn):
    conn.execute("CREATE TEMP TABLE maquina (id int PRIMARY KEY, estado text)")
    conn.execute(
        "CREATE TRIGGER maquina_transicion BEFORE UPDATE ON maquina FOR EACH ROW"
        " EXECUTE FUNCTION util.validar_transicion('{\"en_cola\": [\"en_curso\"], \"en_curso\": [\"terminado\"]}')"
    )
    conn.execute("INSERT INTO maquina VALUES (1, 'en_cola')")
    conn.execute("UPDATE maquina SET estado = 'en_curso'")
    with pytest.raises(psycopg.errors.RaiseException, match="no se permite pasar de en_curso a en_cola"):
        conn.execute("UPDATE maquina SET estado = 'en_cola'")
    conn.execute("DROP TABLE maquina")
