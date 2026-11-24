"""Auditoría de la base (plan de pruebas, bloques 1 y 2): revisa el catálogo de PostgreSQL y la coherencia de los
datos. Solo lee; no cambia nada.

    uv run python scripts/auditoria/bd_catalogo.py            # contra la base del .env (desarrollo)

Cada revisión imprime "OK" o la lista de hallazgos. Sale con código 1 si hay hallazgos.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

from app.db import connect  # noqa: E402

ESQUEMAS = ("oficial", "social", "verificacion", "ia", "temas", "util")
PROPIOS = "('oficial','social','verificacion','ia','temas','util')"

REVISIONES: list[tuple[str, str, str]] = [
    ("BD-03", "Llaves foráneas sin índice que empiece por sus columnas", f"""
        SELECT c.conrelid::regclass::text || ' (' || string_agg(a.attname, ', ' ORDER BY k.n) || ') → ' || c.confrelid::regclass::text
        FROM pg_constraint c
        CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, n)
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
        WHERE c.contype = 'f' AND c.connamespace::regnamespace::text IN {PROPIOS}
          AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid
                          AND (i.indkey::int2[])[0:cardinality(c.conkey) - 1] @> c.conkey
                          AND c.conkey @> (i.indkey::int2[])[0:cardinality(c.conkey) - 1])
        GROUP BY c.oid, c.conrelid, c.confrelid ORDER BY 1"""),
    ("BD-04a", "Tablas que se declaran de solo inserción (comentario) sin trigger que lo impida", f"""
        SELECT c.oid::regclass::text FROM pg_class c
        WHERE c.relkind = 'r' AND c.relnamespace::regnamespace::text IN {PROPIOS}
          AND obj_description(c.oid, 'pg_class') ILIKE '%solo inserci%'
          AND NOT EXISTS (SELECT 1 FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid
                          WHERE t.tgrelid = c.oid AND NOT t.tgisinternal AND p.proname = 'prohibir_cambios')
        ORDER BY 1"""),
    ("BD-04b", "Tablas con trigger de solo inserción que no bloquea UPDATE y DELETE a la vez", f"""
        SELECT t.tgrelid::regclass::text || ': ' || t.tgname FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid
        WHERE p.proname = 'prohibir_cambios' AND NOT t.tgisinternal
          AND t.tgname NOT LIKE '%sin_borrado'                     -- borrado lógico a propósito: solo impide DELETE
          AND NOT ((t.tgtype & 16) > 0 AND (t.tgtype & 8) > 0)   -- 16 = UPDATE, 8 = DELETE
        ORDER BY 1"""),
    ("BD-05a", "Restricciones sin validar (NOT VALID)", f"""
        SELECT conrelid::regclass::text || '.' || conname FROM pg_constraint
        WHERE NOT convalidated AND connamespace::regnamespace::text IN {PROPIOS} ORDER BY 1"""),
    ("BD-02a", "Tablas sin llave primaria", f"""
        SELECT c.oid::regclass::text FROM pg_class c
        WHERE c.relkind = 'r' AND c.relnamespace::regnamespace::text IN {PROPIOS}
          AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype = 'p') ORDER BY 1"""),
    ("BD-02b", "Tablas sin comentario (documentación en la base)", f"""
        SELECT c.oid::regclass::text FROM pg_class c
        WHERE c.relkind = 'r' AND c.relnamespace::regnamespace::text IN {PROPIOS}
          AND obj_description(c.oid, 'pg_class') IS NULL ORDER BY 1"""),
    ("PR-03", "Rutinas de los esquemas propios que cualquiera (PUBLIC) puede ejecutar", f"""
        SELECT p.oid::regprocedure::text FROM pg_proc p
        WHERE p.pronamespace::regnamespace::text IN ('oficial','social','verificacion','ia','temas')
          AND has_function_privilege('public', p.oid, 'EXECUTE')
          AND p.prorettype <> 'trigger'::regtype ORDER BY 1"""),
    ("PR-04", "Rutinas SECURITY DEFINER sin search_path fijo", f"""
        SELECT p.oid::regprocedure::text FROM pg_proc p
        WHERE p.prosecdef AND p.pronamespace::regnamespace::text IN {PROPIOS}
          AND NOT EXISTS (SELECT 1 FROM unnest(coalesce(p.proconfig, '{{}}')) cfg WHERE cfg LIKE 'search_path=%')
        ORDER BY 1"""),
    ("PR-02a", "Roles de servicio con permiso de TRUNCATE (saltaría los triggers de fila)", f"""
        SELECT r.rolname || ' → ' || c.oid::regclass::text FROM pg_class c CROSS JOIN pg_roles r
        WHERE c.relkind = 'r' AND c.relnamespace::regnamespace::text IN {PROPIOS} AND r.rolname LIKE 'svc\\_%'
          AND has_table_privilege(r.rolname, c.oid, 'TRUNCATE') ORDER BY 1"""),
    ("PR-02b", "Roles de servicio que pueden crear objetos en algún esquema", f"""
        SELECT r.rolname || ' → ' || n.nspname FROM pg_namespace n CROSS JOIN pg_roles r
        WHERE n.nspname IN ('public', 'oficial','social','verificacion','ia','temas','util') AND r.rolname LIKE 'svc\\_%'
          AND has_schema_privilege(r.rolname, n.oid, 'CREATE') ORDER BY 1"""),
    ("BD-07a", "Contadores de publicaciones distintos del conteo real", """
        SELECT p.id::text || ' respuestas ' || p.total_respuestas || '≠' || r.n || ' compartidas ' || p.total_compartidas
               || '≠' || c.n || ' reacciones ' || p.total_reacciones || '≠' || x.n
        FROM social.publicacion p
        CROSS JOIN LATERAL (SELECT count(*) n FROM social.publicacion h WHERE h.responde_a_id = p.id AND h.estado = 'visible') r
        CROSS JOIN LATERAL (SELECT count(*) n FROM social.publicacion h WHERE h.comparte_id = p.id AND h.estado = 'visible') c
        CROSS JOIN LATERAL (SELECT count(*) n FROM social.reaccion x WHERE x.publicacion_id = p.id) x
        WHERE (p.total_respuestas, p.total_compartidas, p.total_reacciones) <> (r.n, c.n, x.n) ORDER BY 1"""),
    ("BD-07b", "Contador de integrantes de comunidades distinto del conteo real", """
        SELECT c.nombre || ' ' || c.total_integrantes || '≠' || count(i.*) FROM social.comunidad c
        LEFT JOIN social.integrante i ON i.comunidad_id = c.id
        GROUP BY c.id HAVING c.total_integrantes <> count(i.*) ORDER BY 1"""),
]


def tablas_del_diseno() -> set[str]:
    texto = "\n".join(p.read_text(encoding="utf-8") for p in (RAIZ / "docs" / "diseno").glob("*.md"))
    return {n.split(".")[-1] for n in re.findall(r"`([a-z_.]+)`", texto)}


def main() -> int:
    conn = connect(autocommit=True)
    hallazgos = 0
    for codigo, titulo, consulta in REVISIONES:
        try:
            filas = [r[0] for r in conn.execute(consulta).fetchall()]
        except Exception as exc:  # una revisión que falla se reporta, no detiene las demás
            filas = [f"ERROR al revisar: {exc}".splitlines()[0]]
            conn.rollback() if not conn.autocommit else None
        print(f"\n[{codigo}] {titulo}: {'OK' if not filas else len(filas)}")
        for f in filas:
            print("   -", f)
        hallazgos += len(filas)
    # BD-08a: eventos de cada outbox, de los tipos que procesa cada consumidor, sin entregar hace más de 10 min.
    sys.path.insert(0, str(RAIZ / "src"))
    from servicios.grafo import sincronizador
    from servicios.verificacion import trabajador
    pendientes = []
    for consumidor, outbox in (("grafo", sincronizador.OUTBOX), ("verificacion", trabajador.OUTBOX)):
        for esquema, tipos in outbox:
            n = conn.execute(f"""SELECT count(*) FROM {esquema}.evento_salida e WHERE e.tipo_evento = ANY (%s)
                                  AND e.creado_en < now() - interval '10 minutes'
                                  AND NOT EXISTS (SELECT 1 FROM {esquema}.entrega_evento d
                                                  WHERE d.evento_id = e.id AND d.consumidor = %s)""",
                             (tipos, consumidor)).fetchone()[0]
            if n:
                pendientes.append(f"{consumidor} ← {esquema}: {n}")
    print(f"\n[BD-08a] Eventos sin entregar a su consumidor hace más de 10 minutos: {'OK' if not pendientes else len(pendientes)}")
    for p in pendientes:
        print("   -", p)
    hallazgos += len(pendientes)
    # BD-04c: prueba real de solo inserción sobre una fila existente de cada tabla, dentro de una transacción que
    # se deshace (no cambia nada).
    tablas_si = conn.execute("""SELECT DISTINCT t.tgrelid::regclass::text FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid
                                WHERE p.proname = 'prohibir_cambios' AND NOT t.tgisinternal AND t.tgname NOT LIKE '%sin_borrado'
                                ORDER BY 1""").fetchall()
    sin_bloqueo, sin_filas = [], 0
    for (tabla,) in tablas_si:
        for operacion in ("UPDATE {t} SET creado_en = creado_en WHERE ctid = (SELECT ctid FROM {t} LIMIT 1)",
                          "DELETE FROM {t} WHERE ctid = (SELECT ctid FROM {t} LIMIT 1)"):
            with conn.transaction(force_rollback=True):
                if not conn.execute(f"SELECT EXISTS (SELECT 1 FROM {tabla})").fetchone()[0]:
                    sin_filas += 1
                    break
                try:
                    with conn.transaction():
                        sentencia = operacion.format(t=tabla)
                        if "creado_en" in sentencia and not conn.execute(
                                "SELECT 1 FROM pg_attribute WHERE attrelid = %s::regclass AND attname = 'creado_en'", (tabla,)).fetchone():
                            sentencia = sentencia.replace("creado_en = creado_en", "ctid = ctid").replace("SET ctid = ctid", "SET " + conn.execute(
                                "SELECT attname FROM pg_attribute WHERE attrelid = %s::regclass AND attnum > 0 AND NOT attisdropped AND attidentity = '' AND attgenerated = '' ORDER BY attnum LIMIT 1",
                                (tabla,)).fetchone()[0] + " = " + conn.execute(
                                "SELECT attname FROM pg_attribute WHERE attrelid = %s::regclass AND attnum > 0 AND NOT attisdropped AND attidentity = '' AND attgenerated = '' ORDER BY attnum LIMIT 1",
                                (tabla,)).fetchone()[0])
                        conn.execute(sentencia)
                    sin_bloqueo.append(f"{tabla}: {operacion.split()[0]} se permitió")
                except Exception as exc:
                    if "solo inserci" not in str(exc):
                        sin_bloqueo.append(f"{tabla}: {operacion.split()[0]} falló por otra razón: {str(exc).splitlines()[0]}")
    print(f"\n[BD-04c] Solo inserción probada con filas reales ({len(tablas_si)} tablas, {sin_filas} vacías): {'OK' if not sin_bloqueo else len(sin_bloqueo)}")
    for f in sin_bloqueo:
        print("   -", f)
    hallazgos += len(sin_bloqueo)
    # BD-02c: tablas de la base que el diseño no nombra.
    nombradas = tablas_del_diseno()
    tablas = [r[0] for r in conn.execute(f"""SELECT relnamespace::regnamespace::text || '.' || relname, relname FROM pg_class
                                               WHERE relkind IN ('r', 'v', 'm') AND relnamespace::regnamespace::text IN {PROPIOS}
                                               ORDER BY 1""").fetchall() if r[1] not in nombradas]
    print(f"\n[BD-02c] Tablas o vistas de la base que docs/diseno no nombra: {'OK' if not tablas else len(tablas)}")
    for t in tablas:
        print("   -", t)
    hallazgos += len(tablas)
    print(f"\nTotal de hallazgos: {hallazgos}")
    return 1 if hallazgos else 0


if __name__ == "__main__":
    sys.exit(main())
