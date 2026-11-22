"""Declaraciones reales de figuras públicas para la presentación, investigadas el 22 nov 2026.

    uv run python db/semillas/declaraciones.py --verificador prueba_editor

Regla: solo texto que el medio pone ENTRE COMILLAS y atribuye a la persona, copiado tal cual. Lo que el medio
parafrasea no se registra como declaración. "[…]" marca un corte entre dos frases citadas de la misma
intervención y "[…,]" una aclaración del contexto que da el propio artículo. La fecha es la de la intervención,
no la del artículo, cuando el artículo la dice.

Se eligieron citas que tocan los indicadores con datos oficiales cargados (inflación, desempleo y homicidios)
y a propósito de distintos tipos: unas comparables con la serie oficial, una local (Barranquilla, sin serie
nacional comparable), una de inflación básica (otra serie), una proyección y una condicional. Así la
presentación muestra los cuatro desenlaces sin forzar ninguno. Para las demás figuras no se encontró una cita
textual con cifras de estos indicadores; no se les atribuye nada.
Idempotente: si la misma figura ya tiene ese texto, no se repite.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.db import connect  # noqa: E402

DECLARACIONES = [
    ("Abelardo de la Espriella", date(2026, 9, 27),
     "En Barranquilla, por poner solo un ejemplo, en un trabajo articulado con el alcalde Alejandro Char […] "
     "reducimos los homicidios en 64%",
     "https://www.elheraldo.co/colombia/2026/09/28/en-barranquilla-reducimos-los-homicidios-en-64-de-la-espriella-presenta-cifras-de-seguridad-nacional/",
     ["seguridad", "homicidios"]),
    ("Leonardo Villar Gómez", date(2026, 10, 13),
     "Con una inflación que en ese momento estaba en 5%, el salario mínimo aumentó el 23%",
     "https://www.infobae.com/colombia/2026/10/13/gerente-del-banco-de-la-republica-confirmo-que-en-2026-tampoco-se-cumplira-la-meta-de-inflacion-responsabilizo-al-salario-minimo-de-gustavo-petro/",
     ["inflacion", "salariominimo"]),
    ("Leonardo Villar Gómez", date(2026, 4, 13),
     "La inflación básica se ubicaba en 4,85% en noviembre de 2025; en febrero estaba en 5,51%. "
     "El aumento, de cerca de 66 puntos básicos en tres meses, es muy preocupante",
     "https://www.infobae.com/colombia/2026/04/13/gerente-del-banco-de-la-republica-advirtio-sobres-los-riesgos-de-la-inflacion-para-los-colombianos-los-alimentos-los-mas-afectados-segun-la-entidad/",
     ["inflacion"]),
    ("Leonardo Villar Gómez", date(2026, 11, 20),
     "la inflación, que podría terminar este año alrededor de 6 % o 7 %",
     "https://www.noticiascaracol.com/economia/banco-de-la-republica-sobre-el-aumento-del-salario-minimo-debe-tenerse-en-cuenta-la-inflacion-rg10",
     ["inflacion", "salariominimo"]),
    ("Gustavo Petro Urrego", date(2026, 2, 15),
     "La inflación ha bajado a un nivel que también es de los menores en la historia de este siglo. […] "
     "Hemos descendido de 13 a 5%",
     "https://www.elcolombiano.com/negocios/chequeo-cifras-petro-alocucion-salario-minimo-inflacion-desempleo-FN33583251",
     ["inflacion"]),
    ("Gustavo Petro Urrego", date(2026, 2, 15),
     "[La carne de res,] que acumuló un alza de 11% en el último año, más del doble de la inflación anual, "
     "que cerró en 5%",
     "https://www.elcolombiano.com/negocios/chequeo-cifras-petro-alocucion-salario-minimo-inflacion-desempleo-FN33583251",
     ["inflacion"]),
    ("Miguel Gómez Martínez", date(2026, 11, 18),
     "Esa contracción abrupta de la economía produciría un aumento acelerado del desempleo de más de medio "
     "millón de personas",
     "https://www.infobae.com/colombia/2026/11/18/no-atender-la-crisis-fiscal-generara-graves-consecuencias-para-colombia-segun-el-ministro-de-hacienda-habra-un-aumento-acelerado-del-desempleo-y-la-pobreza/",
     ["desempleo"]),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verificador", required=True, help="cuenta verificadora o administradora que registra")
    args = parser.parse_args()
    conn = connect(autocommit=True)
    actor = conn.execute("SELECT id FROM social.usuario WHERE nombre_usuario = %s AND rol IN ('verificador', 'admin')",
                         (args.verificador,)).fetchone()
    if actor is None:
        raise SystemExit(f"@{args.verificador} no es verificador ni administrador")
    nuevas = 0
    for nombre, dicha_el, texto, fuente, etiquetas in DECLARACIONES:
        figura = conn.execute("SELECT id FROM social.figura_publica WHERE nombre_completo = %s", (nombre,)).fetchone()
        if figura is None:
            print(f"Falta la figura {nombre}: primero db/semillas/figuras.py")
            continue
        if conn.execute("SELECT 1 FROM social.declaracion WHERE figura_id = %s AND texto = %s", (figura[0], texto)).fetchone():
            continue
        conn.execute("CALL social.registrar_declaracion(%s, %s, %s, %s, 'declaracion', %s, %s, NULL)",
                     (actor[0], figura[0], texto, dicha_el, fuente, etiquetas))
        nuevas += 1
    print(f"Declaraciones nuevas: {nuevas} de {len(DECLARACIONES)}.")


if __name__ == "__main__":
    main()
