"""Figuras públicas reales para la presentación (T13), investigadas el 22 nov 2026.

    uv run python db/semillas/figuras.py --verificador prueba_editor

Criterio de selección: relevancia nacional y equilibrio entre gobierno, oposición, centro e instituciones
técnicas o de control, para que ninguna orilla quede sin voz. Ese equilibrio es solo un criterio para ELEGIR:
no se guarda ni se muestra ninguna etiqueta política, y el partido queda vacío en todas (la base solo lo
acepta con fuente oficial y nunca para agrupar). Cada cargo lleva su fuente https: el sitio oficial de la
entidad cuando muestra el cargo, o un medio nacional cuando el cargo es anterior o no tiene página propia.
No se registran declaraciones: una declaración exige la cita exacta con su fuente y la agrega el equipo.
Idempotente: si la figura ya existe, no se toca.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.db import connect  # noqa: E402

FIGURAS = [
    # Gobierno nacional y Congreso
    ("Abelardo de la Espriella", "Presidente de la República (2026-2030)", "https://www.presidencia.gov.co",
     date(2026, 8, 7), None),
    ("Miguel Gómez Martínez", "Ministro de Hacienda y Crédito Público",
     "https://www.larepublica.co/economia/estos-son-los-18-ministros-con-los-que-abelardo-de-la-espriella-comienza-su-mandato-4453827",
     date(2026, 8, 7), None),
    ("Honorio Henríquez", "Presidente del Senado de la República (2026-2027)",
     "https://www.infobae.com/colombia/2026/07/21/estas-son-las-funciones-que-tendra-honorio-henriquez-nuevo-presidente-del-senado-para-el-periodo-2026-2027/",
     date(2026, 7, 20), None),
    ("Federico Gutiérrez Zuluaga", "Alcalde de Medellín (2024-2027)", "https://www.medellin.gov.co", date(2024, 1, 1), None),
    # Oposición
    ("Gustavo Petro Urrego", "Presidente de la República (2022-2026)",
     "https://www.infobae.com/colombia/2026/08/07/gustavo-petro-oficialmente-dejo-de-ser-el-presidente-de-colombia-asi-fue-su-salida-de-la-casa-de-narino/",
     date(2022, 8, 7), date(2026, 8, 7)),
    ("Iván Cepeda Castro", "Senador de la República (2026-2030), curul del Estatuto de la Oposición",
     "https://www.infobae.com/colombia/2026/07/16/ivan-cepeda-ya-tiene-en-sus-manos-la-credencial-que-lo-certifica-como-senador-para-el-periodo-2026-2030-gracias-al-estatuto-de-la-oposicion/",
     date(2026, 7, 20), None),
    ("Claudia López Hernández", "Alcaldesa Mayor de Bogotá (2020-2023)",
     "https://www.elespectador.com/politica/elecciones-colombia-2026/quien-es-claudia-lopez-su-paso-por-la-alcaldia-de-bogota-en-el-senado-y-su-salida-de-alianza-verde-noticias-hoy/",
     date(2020, 1, 1), date(2023, 12, 31)),
    # Centro e independientes
    ("Carlos Fernando Galán", "Alcalde Mayor de Bogotá (2024-2027)", "https://bogota.gov.co", date(2024, 1, 1), None),
    ("Alejandro Eder", "Alcalde de Cali (2024-2027)", "https://www.cali.gov.co", date(2024, 1, 1), None),
    ("Sergio Fajardo Valderrama", "Candidato presidencial en la primera vuelta de 2026",
     "https://www.larepublica.co/especiales/elecciones-presidenciales-2026/sergio-fajardo-acepta-la-derrota-y-deja-en-suspenso-su-apoyo-para-la-segunda-vuelta-4404929",
     None, date(2026, 5, 31)),
    # Instituciones técnicas y de control
    ("Leonardo Villar Gómez", "Gerente General del Banco de la República", "https://www.banrep.gov.co", date(2021, 1, 4), None),
    ("Juan Manuel Alvarado Nivia", "Director del Departamento Administrativo Nacional de Estadística (DANE)",
     "https://www.portafolio.co/economia/gobierno/juan-manuel-alvarado-es-nombrado-como-nuevo-director-del-dane-en-reemplazo-de-ricardo-valencia-502494",
     date(2026, 9, 15), None),
    ("Luz Adriana Camargo", "Fiscal General de la Nación (2024-2028)", "https://www.fiscalia.gov.co", date(2024, 3, 13), None),
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
    creadas = 0
    for nombre, cargo, fuente, desde, hasta in FIGURAS:
        if conn.execute("SELECT 1 FROM social.figura_publica WHERE nombre_completo = %s", (nombre,)).fetchone():
            continue
        conn.execute("CALL social.crear_figura(%s, %s, %s, %s, %s, %s, NULL, NULL, NULL)",
                     (actor[0], nombre, cargo, fuente, desde, hasta))
        creadas += 1
    # La ficha de prueba deja de mostrarse (se archiva con su motivo en la bitácora pública; no se borra).
    prueba = conn.execute("SELECT id, cargo, url_fuente_cargo, cargo_desde, cargo_hasta FROM social.figura_publica"
                          " WHERE nombre_completo = 'Figura Ficticia de Prueba' AND estado = 'activa'").fetchone()
    if prueba:
        conn.execute("CALL social.editar_figura(%s, %s, %s, %s, %s, %s, %s, NULL, NULL, 'archivada', %s)",
                     (actor[0], prueba[0], "Figura Ficticia de Prueba", prueba[1], prueba[2], prueba[3], prueba[4],
                      "Ficha de prueba: se archiva al cargar las figuras reales de la presentación."))
    print(f"Figuras nuevas: {creadas} de {len(FIGURAS)}.")


if __name__ == "__main__":
    main()
