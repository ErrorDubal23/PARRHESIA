"""Lo que reciben los endpoints del servicio social (validado por FastAPI antes de tocar la base)."""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class NuevaCuenta(BaseModel):
    nombre_usuario: str = Field(min_length=3, max_length=30)
    nombre_visible: str = Field(min_length=1, max_length=60)
    correo: str = Field(min_length=5, max_length=254)
    clave: str = Field(min_length=8, max_length=200)


class InicioSesion(BaseModel):
    correo: str
    clave: str


class CambioPerfil(BaseModel):
    nombre_visible: str | None = Field(default=None, min_length=1, max_length=60)
    nombre_usuario: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_]{3,30}$")
    biografia: str | None = Field(default=None, max_length=280)  # "" la borra


class CambioCorreo(BaseModel):
    correo: str = Field(min_length=5, max_length=254)
    clave_actual: str = Field(min_length=1, max_length=200)


class CambioClave(BaseModel):
    clave_actual: str = Field(min_length=1, max_length=200)
    clave_nueva: str = Field(min_length=8, max_length=200)


class Desactivacion(BaseModel):
    clave_actual: str = Field(min_length=1, max_length=200)


class NuevaPublicacion(BaseModel):
    texto: str | None = Field(default=None, max_length=1500)  # con marcas de formato; la base limita lo visible a 500
    responde_a_id: UUID | None = None
    comparte_id: UUID | None = None
    figuras_ids: list[UUID] = Field(default_factory=list, max_length=10)


class Reaccion(BaseModel):
    tipo: Literal["me_gusta", "util"]


URL_HTTPS = r"^https://"


class NuevaFigura(BaseModel):
    nombre_completo: str = Field(min_length=3, max_length=120)
    cargo: str = Field(min_length=2, max_length=160)
    url_fuente_cargo: str = Field(pattern=URL_HTTPS, max_length=500)
    cargo_desde: date | None = None
    cargo_hasta: date | None = None
    partido: str | None = Field(default=None, max_length=120)
    url_fuente_partido: str | None = Field(default=None, pattern=URL_HTTPS, max_length=500)


class CambioFigura(BaseModel):
    nombre_completo: str | None = Field(default=None, min_length=3, max_length=120)
    cargo: str | None = Field(default=None, min_length=2, max_length=160)
    url_fuente_cargo: str | None = Field(default=None, pattern=URL_HTTPS, max_length=500)
    cargo_desde: date | None = None
    cargo_hasta: date | None = None
    partido: str | None = Field(default=None, max_length=120)  # "" lo quita
    url_fuente_partido: str | None = Field(default=None, pattern=URL_HTTPS, max_length=500)
    estado: Literal["activa", "archivada"] | None = None
    motivo: str | None = Field(default=None, max_length=500)


class PropuestaFigura(BaseModel):
    nombre_completo: str = Field(min_length=3, max_length=120)
    cargo: str = Field(min_length=2, max_length=160)
    url_fuente: str = Field(pattern=URL_HTTPS, max_length=500)
    nota: str | None = Field(default=None, max_length=500)


class ResolucionPropuesta(BaseModel):
    aceptar: bool
    motivo: str | None = Field(default=None, max_length=500)


class NuevaDeclaracion(BaseModel):
    texto: str = Field(min_length=1, max_length=2000)
    dicha_el: date
    tipo: Literal["declaracion", "promesa"] = "declaracion"
    url_fuente: str = Field(pattern=r"^https?://")
    etiquetas: list[str] = Field(default_factory=list, max_length=10)


__all__ = ["NuevaCuenta", "InicioSesion", "CambioPerfil", "CambioCorreo", "CambioClave", "Desactivacion", "NuevaFigura", "CambioFigura", "PropuestaFigura", "ResolucionPropuesta", "NuevaPublicacion", "Reaccion", "NuevaDeclaracion"]


class CambioRol(BaseModel):
    """Un administrador da o quita un rol (migración 0035). El motivo queda en la bitácora pública."""
    nombre_usuario: str = Field(min_length=3, max_length=30, pattern=r"^[a-z0-9_]+$")
    rol: Literal["usuario", "verificador", "admin"]
    motivo: str = Field(min_length=10, max_length=500)
