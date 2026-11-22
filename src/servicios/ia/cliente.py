"""Una llamada de chat a un proveedor compatible con la API de OpenAI, con errores clasificados."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import httpx

from servicios.ia.proveedores import Proveedor


class LimiteAlcanzado(Exception):
    """El proveedor respondió 429: la cuenta queda en pausa y el trabajo pasa a otra."""

    def __init__(self, esperar: timedelta) -> None:
        super().__init__(f"límite alcanzado; esperar {esperar}")
        self.esperar = esperar


class ModeloSaturado(LimiteAlcanzado):
    """El 429 es del modelo (cupo compartido del proveedor), no de la cuenta: se prueba otro modelo."""


class ModeloNoDisponible(ModeloSaturado):
    """El proveedor ya no ofrece ese modelo (404): se prueba el siguiente de la lista."""


class ErrorProveedor(Exception):
    """Cualquier otra falla del proveedor: el trabajo se reintenta con espera creciente."""


@dataclass
class Respuesta:
    texto: str
    tokens_entrada: int | None
    tokens_salida: int | None


def _esperar(respuesta: httpx.Response) -> timedelta:
    for encabezado in ("retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
        valor = respuesta.headers.get(encabezado)
        if valor:
            try:
                return timedelta(seconds=max(1.0, float(valor.rstrip("s"))))
            except ValueError:
                pass
    return timedelta(seconds=60)


def llamar(http: httpx.Client, proveedor: Proveedor, llave: str, modelo: str, sistema: str, usuario: str) -> Respuesta:
    cuerpo = {"model": modelo, "temperature": 0,
              "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]}
    if proveedor.modo_json:
        cuerpo["response_format"] = {"type": "json_object"}
    cuerpo.update(dict(proveedor.extra))
    try:
        r = http.post(f"{proveedor.url}/chat/completions", json=cuerpo, timeout=120,
                      headers={"Authorization": f"Bearer {llave}"})
    except httpx.HTTPError as exc:
        raise ErrorProveedor(f"sin conexión con {proveedor.nombre}: {type(exc).__name__}") from exc
    if r.status_code == 404:
        raise ModeloNoDisponible(timedelta(seconds=60))
    if r.status_code == 503 and proveedor.cupo_por_modelo:
        raise ModeloSaturado(timedelta(seconds=60))     # "demanda alta" de un modelo: se prueba el siguiente
    if r.status_code == 429:
        if "upstream" in r.text or proveedor.cupo_por_modelo:
            raise ModeloSaturado(_esperar(r))
        raise LimiteAlcanzado(_esperar(r))
    if r.status_code != 200:
        raise ErrorProveedor(f"{proveedor.nombre} respondió {r.status_code}: {r.text[:300]}")
    datos = r.json()
    try:
        texto = datos["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as exc:
        raise ErrorProveedor(f"{proveedor.nombre}: respuesta sin contenido") from exc
    uso = datos.get("usage") or {}
    return Respuesta(texto, uso.get("prompt_tokens"), uso.get("completion_tokens"))
