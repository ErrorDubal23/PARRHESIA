"""Proveedores de IA y sus cuentas.

Todos hablan la API de chat de OpenAI, así que un solo cliente sirve para todos.
Agregar un proveedor es agregar una entrada aquí y su llave en el .env, con la forma
<PROVEEDOR>_KEY_<alias> (por ejemplo GROQ_KEY_groq_cuenta_1). La base solo guarda el alias.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from servicios.comun.configuracion import ARCHIVO_ENV


@dataclass(frozen=True)
class Proveedor:
    nombre: str
    url: str
    modelos: dict[str, tuple[str, ...]]  # tipo de trabajo -> modelos, en orden de preferencia
    modo_json: bool                  # si acepta response_format={"type": "json_object"}
    extra: tuple[tuple[str, object], ...] = ()   # parámetros propios del proveedor
    cupo_por_modelo: bool = False    # si el límite (429) es de cada modelo y no de la cuenta: se prueba el siguiente


GRATUITOS_OPENROUTER = ("nvidia/nemotron-3-ultra-550b-a55b:free", "baidu/ernie-5.5-flash-preview:free",
                        "nvidia/nemotron-3.5-super-vl:free", "google/gemma-4-31b-it:free")

# Revisados contra la lista de modelos de la cuenta y medidos el 22 nov 2026 con razonamiento bajo: 3.5-flash-lite
# ~2 s y 3.5-flash ~8 s, con la misma lectura; sin límite de razonamiento tardaban 40-70 s. Para leer cifras va
# primero el más rápido; para juzgar neutralidad y redactar, el que razona mejor.
GEMINI_RAPIDOS = ("gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite",
                  "gemini-flash-latest")
GEMINI_CUIDADOSOS = ("gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-flash-latest")
GRATUITOS_GEMINI = GEMINI_RAPIDOS

PROVEEDORES = {
    "groq": Proveedor(
        "groq", "https://api.groq.com/openai/v1",
        {"extraer_afirmaciones": ("openai/gpt-oss-120b",), "redactar_explicacion": ("openai/gpt-oss-20b",),
         "agrupar_temas": ("openai/gpt-oss-120b",), "extraer_declaraciones": ("openai/gpt-oss-120b",),
         "redactar_guia": ("openai/gpt-oss-20b",), "juzgar_neutralidad": ("openai/gpt-oss-120b",)},
        # gpt-oss razona antes de responder: con razonamiento bajo y espacio suficiente no se queda sin tokens.
        modo_json=True, extra=(("reasoning_effort", "low"), ("max_completion_tokens", 2048))),
    # Segundo lector del consenso (decisión 26): modelos de otros fabricantes, plan gratuito.
    # Los gratuitos a veces se saturan (cupo compartido): si uno está saturado, se prueba el siguiente.
    "openrouter": Proveedor(
        "openrouter", "https://openrouter.ai/api/v1",
        {tipo: GRATUITOS_OPENROUTER for tipo in
         ("extraer_afirmaciones", "redactar_explicacion", "agrupar_temas", "extraer_declaraciones",
          "redactar_guia", "juzgar_neutralidad")},
        modo_json=False),
    # Segundo lector rápido (22 nov 2026): Gemini por su API compatible con la de OpenAI, plan gratuito.
    # El cupo gratuito es por modelo y la lista de modelos cambia seguido: se prueban en orden y un modelo
    # retirado (404), sin cupo (429) o con demanda alta (503) pasa al siguiente. Fabricante distinto del primer lector (decisión 26).
    "gemini": Proveedor(
        "gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
        {"extraer_afirmaciones": GEMINI_RAPIDOS, "extraer_declaraciones": GEMINI_RAPIDOS, "agrupar_temas": GEMINI_RAPIDOS,
         "redactar_explicacion": GEMINI_CUIDADOSOS, "redactar_guia": GEMINI_CUIDADOSOS,
         "juzgar_neutralidad": GEMINI_CUIDADOSOS},
        modo_json=False, extra=(("reasoning_effort", "low"),), cupo_por_modelo=True),
}

# Si un trabajo no exige proveedor, se prefiere en este orden.
PREFERENCIA = ("groq", "gemini", "openrouter")
# Segundo lector del consenso y juez de neutralidad: el primero de esta lista que tenga una cuenta habilitada
# (lo decide la base con ia.primer_proveedor_habilitado, migración 0034).
SEGUNDOS_LECTORES = ("gemini", "openrouter")

_LLAVE = re.compile(r"^([A-Z]+)_KEY_([a-z0-9_]{3,40})=(.*)$")


def cuentas() -> dict[str, tuple[str, str]]:
    """{alias: (proveedor, llave)} de las llaves del entorno o del .env. Nunca se imprimen."""
    lineas = [f"{k}={v}" for k, v in os.environ.items()]
    if ARCHIVO_ENV.exists():
        lineas += ARCHIVO_ENV.read_text(encoding="utf-8").splitlines()
    encontradas: dict[str, tuple[str, str]] = {}
    for linea in lineas:
        m = _LLAVE.match(linea.strip())
        if m and m.group(1).lower() in PROVEEDORES and m.group(3).strip():
            encontradas.setdefault(m.group(2), (m.group(1).lower(), m.group(3).strip().strip('"').strip("'")))
    return encontradas
