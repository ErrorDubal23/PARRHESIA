"""Sesión segura (decisión 23, reforzada el 21 nov 2026).

- El token (JWT firmado con JWT_SECRETO) viaja en una cookie HttpOnly y SameSite=Strict:
  el JavaScript de la página no lo puede leer, así que un script malicioso no lo puede robar.
- Cada token lleva el identificador de una sesión guardada en la base (social.sesion). En
  cada petición se revisa con social.sesion_activa: si la sesión se cerró, venció o la cuenta
  se suspendió, el token deja de servir al instante. El rol también se lee de la base.
- Las escrituras con cookie exigen el encabezado X-Parrhesia: un sitio ajeno no puede enviar
  encabezados propios a esta API (no hay CORS), así que no puede hacer peticiones en nombre
  del usuario (CSRF).
- Además (auditoría MS-03, 22 nov 2026), si el navegador declara el origen (Origin), debe ser el mismo sitio
  (mismo host que la petición): segunda defensa por si algún día se habilitara CORS por error.
- El encabezado Authorization: Bearer sigue sirviendo para clientes que no son el navegador.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import jwt
from fastapi import Request, Response

from servicios.comun.configuracion import obligatoria, variable
from servicios.comun.errores import ErrorApi

COOKIE = "parrhesia_sesion"
ENCABEZADO_CSRF = "x-parrhesia"
DURACION = timedelta(hours=8)
ALGORITMO = "HS256"
METODOS_QUE_ESCRIBEN = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass(frozen=True)
class Usuario:
    id: str
    nombre_usuario: str
    rol: str
    jti: str

    @property
    def es_verificador(self) -> bool:
        return self.rol in ("verificador", "admin")


def emitir(jti: str, usuario_id: str, vence: datetime) -> str:
    return jwt.encode({"jti": jti, "sub": usuario_id, "exp": vence, "iat": datetime.now(timezone.utc)},
                      obligatoria("JWT_SECRETO"), algorithm=ALGORITMO)


def cookie_segura() -> bool:
    """Secure en producción (HTTPS). En local, sobre http://localhost, se puede apagar con COOKIE_SEGURA=false."""
    return (variable("COOKIE_SEGURA", "true") or "true").lower() != "false"


def poner_cookie(respuesta: Response, token: str, vence: datetime) -> None:
    respuesta.set_cookie(COOKIE, token, max_age=int((vence - datetime.now(timezone.utc)).total_seconds()),
                         httponly=True, samesite="strict", secure=cookie_segura(), path="/")


def quitar_cookie(respuesta: Response) -> None:
    respuesta.delete_cookie(COOKIE, httponly=True, samesite="strict", secure=cookie_segura(), path="/")


def _token(request: Request) -> tuple[str | None, bool]:
    """(token, vino_en_cookie)."""
    cabecera = request.headers.get("authorization", "")
    if cabecera.lower().startswith("bearer "):
        return cabecera[7:].strip(), False
    return request.cookies.get(COOKIE), True


def _mismo_origen(request: Request) -> bool:
    """Sin Origin (clientes que no son navegador, o el mismo sitio en algunos navegadores) se acepta; con Origin,
    tiene que ser el mismo sitio al que llegó la petición. Se compara el nombre del sitio sin el puerto: Nginx
    pasa el Host sin puerto (127.0.0.1) y el navegador declara el origen con él (http://127.0.0.1:8080); un sitio
    atacante tiene otro nombre."""
    origen = request.headers.get("origin")
    if not origen:
        return True
    sitio = (urlsplit(origen).hostname or "").lower()
    host = (request.headers.get("host") or "").lower()
    host = host[1:host.index("]")] if host.startswith("[") else host.split(":")[0]     # quita el puerto (y corchetes IPv6)
    return bool(sitio) and sitio == host


def _leer(request: Request) -> Usuario | None:
    token, en_cookie = _token(request)
    if not token:
        return None
    try:
        datos = jwt.decode(token, obligatoria("JWT_SECRETO"), algorithms=[ALGORITMO], options={"require": ["exp", "jti"]})
    except jwt.PyJWTError:
        raise ErrorApi("sesion_requerida", 401)
    if en_cookie and request.method in METODOS_QUE_ESCRIBEN and (
            request.headers.get(ENCABEZADO_CSRF) != "1" or not _mismo_origen(request)):
        raise ErrorApi("origen_no_permitido", 403, "La petición no viene de la aplicación.")
    with request.app.state.pool.connection() as conn:
        fila = conn.execute("SELECT usuario_id, nombre_usuario, rol FROM social.sesion_activa(%s)", (datos["jti"],)).fetchone()
    if fila is None:
        raise ErrorApi("sesion_requerida", 401)
    return Usuario(str(fila[0]), fila[1], fila[2], datos["jti"])


def usuario_opcional(request: Request) -> Usuario | None:
    try:
        return _leer(request)
    except ErrorApi as error:
        if error.estado == 401:
            return None          # una sesión vencida no impide ver lo público
        raise


def usuario_actual(request: Request) -> Usuario:
    usuario = _leer(request)
    if usuario is None:
        raise ErrorApi("sesion_requerida", 401)
    return usuario


def verificador(request: Request) -> Usuario:
    usuario = usuario_actual(request)
    if not usuario.es_verificador:
        raise ErrorApi("sin_permiso", 403)
    return usuario
