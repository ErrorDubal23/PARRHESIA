"""Formato de las publicaciones (migración 0016): la base y la app quitan las marcas igual, el límite
cuenta lo visible, las etiquetas salen del texto visible y la verificación lee el texto plano."""

from __future__ import annotations

import json
from decimal import Decimal
import shutil
import subprocess
from pathlib import Path

import psycopg
import pytest

RAIZ = Path(__file__).resolve().parents[1]
CASOS = json.loads((RAIZ / "tests/datos/casos_formato.json").read_text())


@pytest.fixture
def db(test_db_url):
    with psycopg.connect(test_db_url, autocommit=True) as c:
        c.execute("TRUNCATE social.cambio_rol, social.usuario, social.publicacion, social.etiqueta, social.evento_salida CASCADE")
        uid = c.execute("CALL social.registrar_usuario('ana', 'Ana', 'ana@x.co', '$argon2id$v=19$m=1$x$y', NULL)").fetchone()[0]
        yield c, uid


@pytest.mark.parametrize("caso", CASOS, ids=[c["texto"][:30] for c in CASOS])
def test_database_strips_marks_like_the_app(db, caso):
    c, _ = db
    assert c.execute("SELECT util.texto_plano(%s)", (caso["texto"],)).fetchone()[0] == caso["plano"]


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node.js")
def test_app_strips_marks_like_the_database():
    r = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", "web/scripts/probar_formato.mjs"],
                       cwd=RAIZ, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def publicar(c, uid, texto):
    return c.execute("CALL social.publicar(%s, %s, NULL, NULL, '{}', NULL)", (uid, texto)).fetchone()[0]


def test_limit_counts_visible_text_and_marks_have_a_ceiling(db):
    c, uid = db
    visible = "a" * 496
    publicar(c, uid, f"**{visible[:200]}** [{visible[200:400]}](https://www.dane.gov.co/{'x' * 300}) {visible[400:]}")
    with pytest.raises(psycopg.errors.CheckViolation, match="publicacion_texto_valido"):
        publicar(c, uid, "**" + "b" * 501 + "**")
    with pytest.raises(psycopg.errors.CheckViolation, match="publicacion_formato_valido"):
        publicar(c, uid, f"[ok](https://x.co/{'y' * 1500})")


def test_tags_mentions_and_verification_use_visible_text(db):
    c, uid = db
    pid = publicar(c, uid, "La **inflación** fue *6,29 %* según [el DANE](https://www.dane.gov.co/2026/#anexo_9) #inflacion @ana")
    etiquetas = c.execute("SELECT e.nombre FROM social.publicacion_etiqueta pe JOIN social.etiqueta e ON e.id = pe.etiqueta_id"
                          " WHERE pe.publicacion_id = %s", (pid,)).fetchall()
    assert etiquetas == [("inflacion",)]  # el #anexo_9 del enlace no es una etiqueta
    texto = c.execute("SELECT social.texto_para_verificar('publicacion', %s)", (pid,)).fetchone()[0]
    assert texto == "La inflación fue 6,29 % según el DANE #inflacion @ana"
    # Las cifras de la dirección web (2026, 9) no llegan a la verificación: solo las del texto visible.
    assert c.execute("SELECT util.cifras_en_texto(%s)", (texto,)).fetchone()[0] == [Decimal("6.29")]


def test_sharing_without_comment_keeps_working(db):
    c, uid = db
    original = publicar(c, uid, "Una opinión")
    compartida = c.execute("CALL social.publicar(%s, NULL, NULL, %s, '{}', NULL)", (uid, original)).fetchone()[0]
    assert c.execute("SELECT texto FROM social.publicacion WHERE id = %s", (compartida,)).fetchone()[0] is None
    assert c.execute("SELECT util.texto_plano(NULL)").fetchone()[0] is None
