"""Errores con la misma forma en todos los servicios (docs/diseno/07_apis.md).

La base lanza códigos estables ("autor_inactivo: ..."); aquí se traducen a un estado
HTTP y a un mensaje en español para la app:

    {"error": {"codigo": "autor_inactivo", "mensaje": "La cuenta no está activa."}}
"""

from __future__ import annotations

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

MENSAJES = {
    "autor_inactivo": "La cuenta no existe o no está activa.",
    "usuario_inactivo": "La cuenta no existe o no está activa.",
    "publicacion_destino_no_visible": "La publicación fue retirada y ya no se puede responder ni compartir.",
    "publicacion_no_visible": "La publicación no existe o fue retirada.",
    "sin_permiso": "No tienes permiso para hacer esto.",
    "usuario_nombre_usuario_key": "Ese nombre de usuario ya está en uso.",
    "usuario_correo_key": "Ya hay una cuenta con ese correo.",
    "usuario_nombre_usuario_valido": "El nombre de usuario debe tener de 3 a 30 letras minúsculas, números o guion bajo.",
    "usuario_correo_valido": "El correo no es válido.",
    "usuario_nombre_visible_valido": "El nombre visible debe tener de 1 a 60 caracteres.",
    "usuario_biografia_valida": "La biografía puede tener hasta 280 caracteres.",
    "publicacion_texto_valido": "La publicación debe tener de 1 a 500 caracteres visibles.",
    "publicacion_formato_valido": "El formato ocupa demasiado espacio: simplifica los enlaces o las marcas.",
    "publicacion_texto_o_compartida": "La publicación no puede estar vacía.",
    "publicacion_un_solo_origen": "Una publicación responde o comparte, pero no las dos cosas.",
    "seguimiento_no_a_si_mismo": "No puedes seguirte a ti mismo.",
    "reaccion_tipo_valido": "La reacción debe ser \"me gusta\" o \"útil\".",
    "no_encontrado": "No encontramos lo que buscas.",
    "credenciales_invalidas": "Correo o contraseña incorrectos.",
    "sesion_requerida": "Inicia sesión para continuar.",
    "demasiados_intentos": "Demasiados intentos fallidos. Por seguridad, espera 15 minutos e inténtalo de nuevo.",
    "clave_debil": "Esa contraseña es fácil de adivinar. Usa al menos 8 caracteres, sin tu usuario ni tu correo.",
    "origen_no_permitido": "La solicitud no proviene de la aplicación.",
    "nombre_reservado": "Ese nombre de usuario perteneció a otra cuenta.",
    "cambio_nombre_reciente": "El nombre de usuario se puede cambiar una vez cada 30 días.",
    "ultimo_administrador": "La comunidad debe conservar al menos un administrador.",
    "no_integrante": "Solo los integrantes pueden hacer esto en la comunidad.",
    "publicacion_privada": "Lo publicado en una comunidad privada no se comparte fuera de ella.",
    "motivo_requerido": "Expulsar exige un motivo de al menos 10 caracteres.",
    "limite_fijadas": "Una comunidad puede fijar hasta 3 publicaciones.",
    "solicitud_no_pendiente": "La solicitud ya fue resuelta.",
    "comunidad_nombre_key": "Ya existe una comunidad con ese nombre.",
    "comunidad_inexistente": "No existe esa comunidad.",
    "figura_publica_partido_con_fuente": "El partido solo se registra con una fuente oficial (https).",
    "figura_publica_nombre_comparable_key": "Esa figura pública ya tiene ficha.",
    "figura_ya_registrada": "Esa figura pública ya tiene ficha.",
    "cargo_sin_fuente": "El cargo y su fuente oficial son obligatorios.",
    "propuesta_no_pendiente": "La propuesta ya fue resuelta.",
    "figura_publica_periodo_valido": "La fecha de fin del cargo no puede ser anterior a la de inicio.",
    "clave_incorrecta": "La contraseña actual no es correcta.",
    "cuenta_desactivada": "Esta cuenta está desactivada.",
    "usuario_foto_valida": "El archivo de la foto no es válido.",
    "datos_invalidos": "Revisa los datos: alguno no es válido.",
    "publicacion_una_compartida_idx": "Ya compartiste esta publicación.",
    "ultimo_admin": "Parrhesia debe conservar al menos un administrador: nombra a otra persona antes.",
    "rol_sin_cambio": "Esa cuenta ya tiene ese rol.",
    "cambio_rol_motivo_valido": "El motivo debe tener al menos 10 caracteres.",
    # Restricciones que se pueden alcanzar desde la página (auditoría BD-05, 22 nov 2026).
    "comunidad_nombre_valido": "El nombre de la comunidad debe tener de 3 a 60 caracteres (sin contar espacios al inicio o al final).",
    "comunidad_descripcion_valida": "La descripción debe tener de 10 a 500 caracteres.",
    "comunidad_reglas_validas": "Las reglas pueden tener hasta 2.000 caracteres.",
    "figura_publica_nombre_valido": "El nombre completo debe tener de 3 a 120 caracteres.",
    "propuesta_figura_nombre_valido": "El nombre completo debe tener de 3 a 120 caracteres.",
    "propuesta_figura_cargo_valido": "El cargo debe tener de 2 a 160 caracteres.",
    "figura_publica_url_cargo_valida": "La fuente del cargo debe ser un enlace https.",
    "figura_publica_url_partido_valida": "La fuente del partido debe ser un enlace https.",
    "propuesta_figura_url_valida": "La fuente debe ser un enlace https.",
    "declaracion_url_valida": "La fuente de la declaración debe ser un enlace web.",
    "declaracion_texto_valido": "La declaración no puede estar vacía.",
    "propuesta_figura_nota_valida": "La nota puede tener hasta 500 caracteres.",
    "solicitud_ingreso_mensaje_valido": "El mensaje puede tener hasta 280 caracteres.",
    "figura_publica_nombre_completo_key": "Esa figura pública ya tiene ficha.",
    "limite_enlaces": "Puedes analizar hasta 10 enlaces por hora. Inténtalo más tarde.",
}

NO_ENCONTRADO = ("_inexistente", "_no_visible", "no_encontrado", "_no_existe")


class ErrorApi(Exception):
    def __init__(self, codigo: str, estado: int, mensaje: str | None = None) -> None:
        self.codigo, self.estado = codigo, estado
        self.mensaje = mensaje or MENSAJES.get(codigo, codigo.replace("_", " ").capitalize() + ".")


def respuesta(codigo: str, estado: int, mensaje: str | None = None) -> JSONResponse:
    error = ErrorApi(codigo, estado, mensaje)
    return JSONResponse({"error": {"codigo": error.codigo, "mensaje": error.mensaje}}, status_code=estado)


def desde_postgres(exc: psycopg.Error) -> JSONResponse:
    diag = exc.diag
    if isinstance(exc, psycopg.errors.RaiseException):
        codigo = (diag.message_primary or "").split(":", 1)[0].strip()
        if codigo.endswith(NO_ENCONTRADO):
            return respuesta(codigo, 404)
        if codigo in ("sin_permiso", "no_integrante") or codigo.endswith("_inactivo"):
            return respuesta(codigo, 403)
        if codigo.startswith("limite_"):
            return respuesta(codigo, 429)
        return respuesta(codigo or "conflicto", 409, diag.message_primary if codigo not in MENSAJES else None)
    if isinstance(exc, psycopg.errors.UniqueViolation):
        return respuesta(diag.constraint_name or "duplicado", 409)
    if isinstance(exc, psycopg.errors.CheckViolation):
        return respuesta(diag.constraint_name or "datos_invalidos", 422)
    if isinstance(exc, psycopg.errors.ForeignKeyViolation):
        return respuesta("no_encontrado", 404)
    if isinstance(exc, (psycopg.errors.InvalidTextRepresentation, psycopg.errors.NotNullViolation)):
        return respuesta("datos_invalidos", 422)
    raise exc


def instalar(app: FastAPI) -> None:
    """Registra los traductores de errores en una app de FastAPI."""

    @app.exception_handler(ErrorApi)
    async def _api(_: Request, exc: ErrorApi):
        return respuesta(exc.codigo, exc.estado, exc.mensaje)

    @app.exception_handler(psycopg.Error)
    async def _postgres(_: Request, exc: psycopg.Error):
        return desde_postgres(exc)

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, exc: RequestValidationError):
        campos = ", ".join(".".join(str(p) for p in e["loc"][1:]) for e in exc.errors())
        return respuesta("datos_invalidos", 422, f"Revisa estos campos: {campos}.")

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException):
        return respuesta(str(exc.detail) if isinstance(exc.detail, str) else "error", exc.status_code)
