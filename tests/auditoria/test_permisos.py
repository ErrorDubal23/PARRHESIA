"""Auditoría, bloque 2 (permisos): cada servicio puede ejecutar lo que su código llama y nada más de otros
servicios; nada queda abierto a PUBLIC (migración 0036)."""

from __future__ import annotations

import re
from pathlib import Path

import psycopg
import pytest

SERVICIOS = Path(__file__).resolve().parents[2] / "src" / "servicios"
LLAMADA = re.compile(r"\b(oficial|social|verificacion|ia|temas)\.([a-z_]+)\(")


@pytest.fixture
def db(test_db_url):
    with psycopg.connect(test_db_url, autocommit=True) as c:
        yield c


def rutinas_llamadas(servicio: str) -> set[tuple[str, str]]:
    llamadas = set()
    for archivo in (SERVICIOS / servicio).rglob("*.py"):
        llamadas |= set(LLAMADA.findall(archivo.read_text(encoding="utf-8")))
    return llamadas


def test_no_routine_in_our_schemas_is_executable_by_everyone(db):
    abiertas = [r for (r,) in db.execute(
        "SELECT p.oid::regprocedure::text FROM pg_proc p"
        " WHERE p.pronamespace::regnamespace::text IN ('oficial','social','verificacion','ia','temas')"
        "   AND p.prorettype <> 'trigger'::regtype AND has_function_privilege('public', p.oid, 'EXECUTE')")]
    assert abiertas == []


def test_routines_created_later_are_born_closed(db):
    db.execute("CREATE FUNCTION social.prueba_auditoria() RETURNS int LANGUAGE sql AS 'SELECT 1'")
    try:
        assert db.execute("SELECT has_function_privilege('public', 'social.prueba_auditoria()', 'EXECUTE')").fetchone()[0] is False
    finally:
        db.execute("DROP FUNCTION social.prueba_auditoria()")


@pytest.mark.parametrize("servicio", ["social", "verificacion", "temas", "oficial", "ia", "grafo"])
def test_each_service_can_execute_every_routine_its_code_calls(db, servicio):
    faltan = []
    for esquema, nombre in sorted(rutinas_llamadas(servicio)):
        firmas = db.execute("SELECT p.oid FROM pg_proc p WHERE p.pronamespace::regnamespace::text = %s AND p.proname = %s",
                            (esquema, nombre)).fetchall()
        if not firmas:
            continue                      # no es una rutina de la base (por ejemplo, un método de Python)
        if not any(db.execute("SELECT has_function_privilege(%s, %s, 'EXECUTE')", (f"svc_{servicio}", oid)).fetchone()[0]
                   for (oid,) in firmas):
            faltan.append(f"{esquema}.{nombre}")
    assert faltan == [], f"svc_{servicio} no puede ejecutar: {faltan}"


@pytest.mark.parametrize("rol", ["svc_temas", "svc_oficial", "svc_grafo", "svc_verificacion", "svc_ia"])
def test_other_services_cannot_act_as_the_social_network(db, rol):
    for rutina in ("social.cambiar_clave(uuid,text,uuid,integer)", "social.asignar_rol(uuid,uuid,text,text)",
                   "social.crear_figura(uuid,text,text,text,date,date,text,text,uuid)", "social.publicar_en_comunidad(uuid,uuid,text,uuid[],uuid)"):
        assert db.execute("SELECT has_function_privilege(%s, %s, 'EXECUTE')", (rol, rutina)).fetchone()[0] is False, (rol, rutina)


def test_console_role_change_is_for_the_owner_only(db):
    for rol in ("svc_social", "svc_verificacion", "svc_temas", "svc_oficial", "svc_grafo", "svc_ia"):
        for rutina in ("social.asignar_rol_consola(uuid,text,text)", "social._cambiar_rol(uuid,uuid,text,text)"):
            assert db.execute("SELECT has_function_privilege(%s, %s, 'EXECUTE')", (rol, rutina)).fetchone()[0] is False


# Las únicas escrituras fuera del propio esquema: marcar entregas del outbox y guardar tendencias (grafo).
ESCRITURAS_PERMITIDAS = {
    ("svc_grafo", "social.entrega_evento", "INSERT"), ("svc_grafo", "social.tendencia", "INSERT"),
    ("svc_grafo", "verificacion.entrega_evento", "INSERT"),
    ("svc_verificacion", "social.entrega_evento", "INSERT"), ("svc_verificacion", "temas.entrega_evento", "INSERT"),
}


def test_no_service_writes_in_another_schema_beyond_the_outbox(db):
    filas = db.execute("""
        SELECT r.rolname, c.oid::regclass::text, p.priv
        FROM pg_roles r CROSS JOIN pg_class c CROSS JOIN unnest(ARRAY['INSERT', 'UPDATE', 'DELETE']) AS p(priv)
        WHERE r.rolname LIKE 'svc\\_%' AND c.relkind = 'r'
          AND c.relnamespace::regnamespace::text IN ('oficial','social','verificacion','ia','temas')
          AND c.relnamespace::regnamespace::text <> substr(r.rolname, 5)
          AND has_table_privilege(r.rolname, c.oid, p.priv)""").fetchall()
    assert set(filas) - ESCRITURAS_PERMITIDAS == set()


def test_only_the_social_service_reads_accounts(db):
    lectores = {r for (r,) in db.execute(
        "SELECT rolname FROM pg_roles WHERE rolname LIKE 'svc\\_%' AND has_table_privilege(rolname, 'social.usuario', 'SELECT')")}
    assert lectores == {"svc_social"}
