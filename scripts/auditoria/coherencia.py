"""Coherencia entre PostgreSQL (fuente de verdad) y Neo4j (proyección), y de los datos entre sí.

    uv run python scripts/auditoria/coherencia.py

Solo lee. Compara, entidad por entidad, lo que hay en PostgreSQL con lo que proyecta el grafo, y revisa
invariantes de la base que deben cumplirse siempre. Antes de comparar espera a que el outbox esté al día (si
el grafo va atrasado, la diferencia no es incoherencia sino demora). Sale con 1 si encuentra algo.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

from app.db import connect  # noqa: E402

# (qué, consulta en PostgreSQL, consulta en Neo4j). Cada par cuenta lo mismo con la regla de la proyección.
PARES = [
    ("cuentas", "SELECT count(*) FROM social.usuario", "MATCH (u:Usuario) RETURN count(u)"),
    ("cuentas activas", "SELECT count(*) FROM social.usuario WHERE estado = 'activo'",
     "MATCH (u:Usuario {estado: 'activo'}) RETURN count(u)"),
    ("publicaciones", "SELECT count(*) FROM social.publicacion", "MATCH (p:Publicacion) RETURN count(p)"),
    ("publicaciones visibles", "SELECT count(*) FROM social.publicacion WHERE estado = 'visible'",
     "MATCH (p:Publicacion {estado: 'visible'}) RETURN count(p)"),
    ("respuestas", "SELECT count(*) FROM social.publicacion WHERE responde_a_id IS NOT NULL",
     "MATCH (:Publicacion)-[r:RESPONDE_A]->() RETURN count(r)"),
    ("compartidas", "SELECT count(*) FROM social.publicacion WHERE comparte_id IS NOT NULL",
     "MATCH (:Publicacion)-[r:COMPARTE]->() RETURN count(r)"),
    ("autoría", "SELECT count(*) FROM social.publicacion", "MATCH (:Usuario)-[r:PUBLICO]->() RETURN count(r)"),
    ("seguimientos", "SELECT count(*) FROM social.seguimiento", "MATCH (:Usuario)-[r:SIGUE]->(:Usuario) RETURN count(r)"),
    ("reacciones", "SELECT count(*) FROM social.reaccion", "MATCH (:Usuario)-[r:REACCIONO]->() RETURN count(r)"),
    ("etiquetas usadas", "SELECT count(DISTINCT etiqueta_id) FROM social.publicacion_etiqueta",
     "MATCH (e:Etiqueta)<-[:ETIQUETADA_CON]-() RETURN count(DISTINCT e)"),
    ("etiquetado", "SELECT count(*) FROM social.publicacion_etiqueta", "MATCH ()-[r:ETIQUETADA_CON]->(:Etiqueta) RETURN count(r)"),
    ("comunidades", "SELECT count(*) FROM social.comunidad", "MATCH (c:Comunidad) RETURN count(c)"),
    ("integrantes", "SELECT count(*) FROM social.integrante", "MATCH (:Usuario)-[r:INTEGRA]->(:Comunidad) RETURN count(r)"),
    ("publicaciones en comunidad", "SELECT count(*) FROM social.publicacion WHERE comunidad_id IS NOT NULL",
     "MATCH (:Publicacion)-[r:EN]->(:Comunidad) RETURN count(r)"),
    ("figuras", "SELECT count(*) FROM social.figura_publica", "MATCH (f:Figura) RETURN count(f)"),
]

# Invariantes de la base: cada consulta debe devolver 0.
INVARIANTES = [
    ("contadores de publicaciones", """SELECT count(*) FROM social.publicacion p WHERE (p.total_respuestas, p.total_compartidas, p.total_reacciones) <>
        ((SELECT count(*) FROM social.publicacion h WHERE h.responde_a_id = p.id AND h.estado = 'visible'),
         (SELECT count(*) FROM social.publicacion h WHERE h.comparte_id = p.id AND h.estado = 'visible'),
         (SELECT count(*) FROM social.reaccion x WHERE x.publicacion_id = p.id))"""),
    ("contador de integrantes", """SELECT count(*) FROM social.comunidad c
        WHERE c.total_integrantes <> (SELECT count(*) FROM social.integrante i WHERE i.comunidad_id = c.id)"""),
    ("comunidades sin administrador", """SELECT count(*) FROM social.comunidad c WHERE NOT EXISTS
        (SELECT 1 FROM social.integrante i JOIN social.usuario u ON u.id = i.usuario_id
         WHERE i.comunidad_id = c.id AND i.papel = 'administrador' AND u.estado = 'activo')"""),
    ("Parrhesia sin administrador", "SELECT CASE WHEN EXISTS (SELECT 1 FROM social.usuario WHERE rol = 'admin' AND estado = 'activo') THEN 0 ELSE 1 END"),
    ("roles sin registro en la bitácora", """SELECT count(*) FROM social.usuario u WHERE u.rol <> 'usuario'
        AND NOT EXISTS (SELECT 1 FROM social.cambio_rol c WHERE c.usuario_id = u.id AND c.rol_nuevo = u.rol)"""),
    ("más de una compartida por persona", """SELECT count(*) FROM (SELECT autor_id, comparte_id FROM social.publicacion
        WHERE comparte_id IS NOT NULL AND estado = 'visible' GROUP BY 1, 2 HAVING count(*) > 1) x"""),
    ("reacciones de quien no puede ver la publicación", """SELECT count(*) FROM social.reaccion r
        WHERE NOT social.puede_ver_publicacion(r.publicacion_id, r.usuario_id)"""),
    ("respuestas a publicaciones privadas de quien no es integrante", """SELECT count(*) FROM social.publicacion h
        JOIN social.publicacion p ON p.id = h.responde_a_id WHERE p.comunidad_id IS NOT NULL
        AND NOT social.puede_ver_publicacion(p.id, h.autor_id)"""),
    ("conclusiones fuera de las cuatro", """SELECT count(*) FROM verificacion.verificacion
        WHERE conclusion NOT IN ('se_sostiene', 'se_debilita', 'se_invierte', 'sin_dato_comparable')"""),
    ("verificaciones con cifra oficial sin evidencia", """SELECT count(*) FROM verificacion.verificacion v
        WHERE v.conclusion <> 'sin_dato_comparable' AND NOT EXISTS (SELECT 1 FROM verificacion.evidencia e WHERE e.verificacion_id = v.id)"""),
    ("evidencia con observación no aceptada", """SELECT count(*) FROM verificacion.evidencia e
        JOIN oficial.observacion o ON o.id = e.observacion_id WHERE o.estado <> 'aceptada'"""),
    ("sesiones vigentes de cuentas no activas", """SELECT count(*) FROM social.sesion s JOIN social.usuario u ON u.id = s.usuario_id
        WHERE u.estado <> 'activo' AND EXISTS (SELECT 1 FROM social.sesion_activa(s.jti))"""),
    ("trabajos de IA atascados en curso (más de 15 min)", """SELECT count(*) FROM ia.trabajo
        WHERE estado = 'en_curso' AND proximo_intento_en < now() - interval '15 minutes'"""),
]


def cypher(consulta: str) -> int:
    r = subprocess.run(["docker", "compose", "exec", "-T", "neo4j", "sh", "-c",
                        f'cypher-shell -u neo4j -p "${{NEO4J_AUTH#neo4j/}}" --format plain "{consulta}"'],
                       cwd=RAIZ, capture_output=True, text=True, timeout=60)
    filas = [l for l in r.stdout.splitlines() if l.strip().lstrip("-").isdigit()]
    if not filas:
        raise RuntimeError(r.stderr.strip()[:200] or r.stdout[:200])
    return int(filas[-1])


def outbox_al_dia(conn) -> bool:
    sys.path.insert(0, str(RAIZ / "src"))
    from servicios.grafo import sincronizador
    for esquema, tipos in sincronizador.OUTBOX:
        n = conn.execute(f"""SELECT count(*) FROM {esquema}.evento_salida e WHERE e.tipo_evento = ANY (%s)
                             AND NOT EXISTS (SELECT 1 FROM {esquema}.entrega_evento d WHERE d.evento_id = e.id AND d.consumidor = 'grafo')""",
                         (tipos,)).fetchone()[0]
        if n:
            return False
    return True


def main() -> int:
    conn = connect(autocommit=True)
    fallas = 0
    for _ in range(30):                       # hasta 60 s para que el grafo se ponga al día
        if outbox_al_dia(conn):
            break
        time.sleep(2)
    else:
        print("FALLA el grafo no se puso al día con el outbox en 60 s")
        fallas += 1
    print("PostgreSQL ↔ Neo4j")
    for que, sql, cy in PARES:
        pg, neo = conn.execute(sql).fetchone()[0], cypher(cy)
        ok = pg == neo
        fallas += not ok
        print(f"{'OK   ' if ok else 'FALLA'} {que}: PostgreSQL {pg} · Neo4j {neo}")
    print("\nInvariantes de la base")
    for que, sql in INVARIANTES:
        n = conn.execute(sql).fetchone()[0]
        fallas += bool(n)
        print(f"{'OK   ' if not n else 'FALLA'} {que}{'' if not n else f': {n}'}")
    print(f"\nFallas: {fallas}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
