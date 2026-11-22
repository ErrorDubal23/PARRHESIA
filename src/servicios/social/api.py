"""API del servicio social.

    uv run uvicorn servicios.social.api:app --port 8001

Contrato: docs/diseno/07_apis.md, sección 1. Toda escritura es un CALL a un
procedimiento de la base: la API nunca escribe en las tablas directamente, y cada
petición es una transacción (si el procedimiento falla, no queda nada).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import hashlib

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, FastAPI, File, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from psycopg.rows import dict_row

from servicios.comun import errores
from servicios.comun.configuracion import crear_pool, variable
from servicios.comun.errores import ErrorApi
from servicios.comun.sesion import (DURACION, Usuario, emitir, poner_cookie, quitar_cookie, usuario_actual,
                                    usuario_opcional, verificador)
from servicios.social import fotos, lecturas
from servicios.social.modelos import (CambioClave, CambioCorreo, CambioRol, CambioFigura, CambioPerfil, Desactivacion, InicioSesion,
                                      NuevaCuenta, NuevaDeclaracion, NuevaFigura, NuevaPublicacion, PropuestaFigura, Reaccion,
                                      ResolucionPropuesta)

recursos: dict = {}
cifrador = PasswordHasher()  # argon2id
# Huella con la que se compara cuando el correo no existe: así la respuesta tarda lo mismo y no
# revela qué correos están registrados.
HUELLA_DE_RELLENO = cifrador.hash("esta-clave-no-pertenece-a-nadie")
CLAVES_COMUNES = {"12345678", "123456789", "1234567890", "password", "contraseña", "contrasena", "qwertyui",
                  "colombia", "colombia1", "11111111", "abcdefgh", "parrhesia"}


@asynccontextmanager
async def ciclo_de_vida(aplicacion: FastAPI):
    recursos["pool"] = crear_pool("PG_URL_SOCIAL")
    aplicacion.state.pool = recursos["pool"]   # la usa la sesión para revisar en la base que siga vigente
    yield
    recursos["pool"].close()


app = FastAPI(title="Servicio social", version="1", lifespan=ciclo_de_vida)
errores.instalar(app)


def conexion():
    with recursos["pool"].connection() as conn:
        yield conn


def url_grafo() -> str:
    return variable("GRAFO_URL", "http://127.0.0.1:8002")


def id_de(conn, nombre_usuario: str) -> str:
    usuario = lecturas.usuario_por_nombre(conn, nombre_usuario)
    if usuario is None:
        raise ErrorApi("usuario_inexistente", 404, "No existe ese usuario.")
    return str(usuario["id"])


@app.get("/salud")
def salud(conn=Depends(conexion)):
    conn.execute("SELECT 1")
    return {"estado": "ok", "base": "ok"}


# --- Cuentas y sesión -------------------------------------------------------------------------


def _clave_debil(clave: str, nombre_usuario: str, correo: str) -> bool:
    clave = clave.lower()
    return clave in CLAVES_COMUNES or nombre_usuario.lower() in clave or correo.split("@")[0].lower() in clave


@app.post("/v1/cuentas", status_code=201)
def crear_cuenta(datos: NuevaCuenta, conn=Depends(conexion)):
    if _clave_debil(datos.clave, datos.nombre_usuario, datos.correo):
        raise ErrorApi("clave_debil", 422)
    usuario_id = conn.execute(
        "CALL social.registrar_usuario(%s, %s, %s, %s, NULL)",
        (datos.nombre_usuario.lower(), datos.nombre_visible, datos.correo, cifrador.hash(datos.clave)),
    ).fetchone()[0]
    return {"id": str(usuario_id), "nombre_usuario": datos.nombre_usuario.lower()}


def _origen(request: Request) -> str:
    """Huella de la IP de quien pide (la puerta de entrada pone X-Forwarded-For). Nunca se guarda la IP."""
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    return hashlib.sha256(ip.encode()).hexdigest()


@app.post("/v1/sesiones")
def iniciar_sesion(datos: InicioSesion, request: Request, respuesta: Response, conn=Depends(conexion)):
    origen = _origen(request)
    if conn.execute("SELECT social.acceso_bloqueado(%s, %s)", (datos.correo, origen)).fetchone()[0]:
        raise ErrorApi("demasiados_intentos", 429)
    fila = conn.execute(
        "SELECT id, nombre_usuario, nombre_visible, rol, clave_hash FROM social.usuario"
        " WHERE correo = lower(trim(%s)) AND estado = 'activo'", (datos.correo,)).fetchone()
    try:
        valida = cifrador.verify(fila[4] if fila else HUELLA_DE_RELLENO, datos.clave) and fila is not None
    except (VerificationError, InvalidHashError):
        valida = False
    conn.execute("CALL social.registrar_intento_acceso(%s, %s, %s)", (datos.correo, origen, valida))
    if not valida:
        raise ErrorApi("credenciales_invalidas", 401)
    jti, vence = conn.execute("CALL social.iniciar_sesion(%s, %s, %s, NULL, NULL)",
                              (fila[0], request.headers.get("user-agent"), DURACION)).fetchone()
    poner_cookie(respuesta, emitir(str(jti), str(fila[0]), vence), vence)
    # El token NO va en la respuesta: solo en la cookie HttpOnly, que el JavaScript no puede leer.
    return {"vence_en": vence.isoformat(), "usuario": perfil(fila[1], conn)}


@app.delete("/v1/sesiones/actual", status_code=204)
def cerrar_sesion(usuario: Usuario | None = Depends(usuario_opcional), conn=Depends(conexion)):
    """Revoca la sesión en el servidor (el token deja de servir aunque alguien lo haya copiado) y borra la cookie."""
    if usuario is not None:
        conn.execute("CALL social.cerrar_sesion(%s)", (usuario.jti,))
    respuesta = Response(status_code=204)
    quitar_cookie(respuesta)
    return respuesta


@app.get("/v1/yo")
def yo(usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    """El propio perfil, con el correo (que solo ve su dueño)."""
    correo = conn.execute("SELECT correo FROM social.usuario WHERE id = %s", (usuario.id,)).fetchone()[0]
    return {**perfil(usuario.nombre_usuario, conn), "correo": correo}


@app.patch("/v1/yo")
def cambiar_perfil(datos: CambioPerfil, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    """Nombre visible, nombre de usuario y biografía de la propia cuenta (el id sale de la sesión, nunca del cuerpo)."""
    conn.execute("CALL social.actualizar_perfil(%s, %s, %s, %s)",
                 (usuario.id, datos.nombre_visible, datos.nombre_usuario, datos.biografia))
    nombre = conn.execute("SELECT nombre_usuario FROM social.usuario WHERE id = %s", (usuario.id,)).fetchone()[0]
    return perfil(nombre, conn)


def _exigir_clave(conn, request: Request, usuario: Usuario, clave: str) -> tuple[str, str]:
    """Confirma la contraseña actual antes de un cambio sensible. Los fallos cuentan para el mismo bloqueo
    que el inicio de sesión, así esta vía no sirve para adivinar contraseñas. Devuelve (correo, nombre)."""
    correo, nombre, huella = conn.execute(
        "SELECT correo, nombre_usuario, clave_hash FROM social.usuario WHERE id = %s", (usuario.id,)).fetchone()
    origen = _origen(request)
    if conn.execute("SELECT social.acceso_bloqueado(%s, %s)", (correo, origen)).fetchone()[0]:
        raise ErrorApi("demasiados_intentos", 429)
    try:
        valida = cifrador.verify(huella, clave)
    except (VerificationError, InvalidHashError):
        valida = False
    if not valida:
        conn.execute("CALL social.registrar_intento_acceso(%s, %s, false)", (correo, origen))
        conn.commit()  # el intento fallido queda registrado aunque la petición termine en error
        raise ErrorApi("clave_incorrecta", 403)
    return correo, nombre


@app.get("/v1/cuentas/disponible")
def nombre_disponible(nombre_usuario: str = Query(min_length=1, max_length=40), conn=Depends(conexion)):
    return {"nombre_usuario": nombre_usuario.lower(),
            "estado": conn.execute("SELECT social.nombre_usuario_disponible(%s)", (nombre_usuario,)).fetchone()[0]}


@app.put("/v1/yo/correo")
def cambiar_correo(datos: CambioCorreo, request: Request, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    _exigir_clave(conn, request, usuario, datos.clave_actual)
    conn.execute("CALL social.cambiar_correo(%s, %s)", (usuario.id, datos.correo))
    return {"correo": datos.correo.strip().lower()}


@app.put("/v1/yo/clave")
def cambiar_clave(datos: CambioClave, request: Request, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    correo, nombre = _exigir_clave(conn, request, usuario, datos.clave_actual)
    if _clave_debil(datos.clave_nueva, nombre, correo):
        raise ErrorApi("clave_debil", 422)
    cerradas = conn.execute("CALL social.cambiar_clave(%s, %s, %s, NULL)",
                            (usuario.id, cifrador.hash(datos.clave_nueva), usuario.jti)).fetchone()[0]
    return {"sesiones_cerradas": cerradas}


@app.put("/v1/yo/foto")
def cambiar_foto(foto: UploadFile = File(...), usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    webp = fotos.procesar(foto.file.read(fotos.MAXIMO_BYTES + 1))
    nombre = fotos.guardar(webp)
    try:
        anterior = conn.execute("CALL social.fijar_foto(%s, %s, NULL)", (usuario.id, nombre)).fetchone()[0]
        conn.commit()
    except Exception:
        fotos.borrar(nombre)  # si la base no la aceptó, no queda un archivo huérfano
        raise
    fotos.borrar(anterior)
    return {"foto": fotos.url(nombre)}


@app.delete("/v1/yo/foto", status_code=204)
def quitar_foto(usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    anterior = conn.execute("CALL social.fijar_foto(%s, NULL, NULL)", (usuario.id,)).fetchone()[0]
    conn.commit()
    fotos.borrar(anterior)
    return Response(status_code=204)


@app.post("/v1/yo/desactivacion", status_code=204)
def desactivar(datos: Desactivacion, request: Request, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    """Decisión 30: la cuenta se desactiva (no se borra) y se cierran todas sus sesiones."""
    _exigir_clave(conn, request, usuario, datos.clave_actual)
    conn.execute("CALL social.desactivar_cuenta(%s)", (usuario.id,))
    respuesta = Response(status_code=204)
    quitar_cookie(respuesta)
    return respuesta


@app.get("/v1/fotos/{archivo}")
def ver_foto(archivo: str):
    # El nombre es aleatorio y nunca cambia de contenido: se puede guardar en caché para siempre.
    return FileResponse(fotos.ruta(archivo), media_type="image/webp",
                        headers={"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"})


# --- Usuarios y seguimiento -------------------------------------------------------------------


@app.get("/v1/usuarios")
def buscar_usuarios(q: str = Query(min_length=2, max_length=60), limite: int = Query(20, ge=1, le=50),
                    usuario: Usuario | None = Depends(usuario_opcional), conn=Depends(conexion)):
    """Personas por nombre: solo cuentas activas y solo datos públicos."""
    with conn.cursor(row_factory=dict_row) as cur:
        filas = cur.execute("SELECT * FROM social.buscar_usuarios(%s, %s, %s)",
                            (q, usuario.id if usuario else None, limite)).fetchall()
    return {"usuarios": [{"nombre_usuario": f["nombre_usuario"], "nombre_visible": f["nombre_visible"],
                          "foto": fotos.url(f["foto"]), "biografia": f["biografia"], "seguidores": f["seguidores"],
                          "lo_sigo": f["lo_sigo"]} for f in filas]}


@app.get("/v1/usuarios/{nombre_usuario}")
def perfil_publico(nombre_usuario: str, usuario: Usuario | None = Depends(usuario_opcional), conn=Depends(conexion)):
    datos = perfil(nombre_usuario, conn)
    datos["lo_sigo"] = bool(usuario) and conn.execute(
        "SELECT EXISTS (SELECT 1 FROM social.seguimiento WHERE seguidor_id = %s AND seguido_id = %s)",
        (usuario.id, datos["id"])).fetchone()[0]
    return datos


def perfil(nombre_usuario: str, conn) -> dict:
    usuario = lecturas.usuario_por_nombre(conn, nombre_usuario)
    if usuario is None:
        raise ErrorApi("usuario_inexistente", 404, "No existe ese usuario.")
    seguidores, seguidos, publicaciones = conn.execute(
        "SELECT * FROM social.estadisticas_usuario(%s)", (usuario["id"],)).fetchone()
    return {"id": str(usuario["id"]), "nombre_usuario": usuario["nombre_usuario"],
            "nombre_visible": usuario["nombre_visible"], "biografia": usuario["biografia"], "rol": usuario["rol"],
            "estado": usuario["estado"], "foto": fotos.url(usuario["foto"]), "creado_en": usuario["creado_en"].isoformat(),
            "estadisticas": {"seguidores": seguidores, "seguidos": seguidos, "publicaciones": publicaciones}}


@app.get("/v1/usuarios/{nombre_usuario}/publicaciones")
def publicaciones_de(nombre_usuario: str, despues: datetime | None = None, limite: int = Query(20, ge=1, le=50),
                     usuario: Usuario | None = Depends(usuario_opcional), conn=Depends(conexion)):
    autor = id_de(conn, nombre_usuario)
    ids = [f[0] for f in conn.execute(
        "SELECT id FROM social.publicacion WHERE autor_id = %s AND estado = 'visible'"
        " AND (%s::timestamptz IS NULL OR creado_en < %s::timestamptz) ORDER BY creado_en DESC LIMIT %s",
        (autor, despues, despues, limite))]
    pubs = lecturas.publicaciones(conn, ids, usuario.id if usuario else None)
    return {"publicaciones": pubs, "siguiente": pubs[-1]["creado_en"] if len(pubs) == limite else None}


@app.put("/v1/usuarios/{nombre_usuario}/seguidores/yo", status_code=204)
def seguir(nombre_usuario: str, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    conn.execute("CALL social.seguir(%s, %s)", (usuario.id, id_de(conn, nombre_usuario)))
    return Response(status_code=204)


@app.delete("/v1/usuarios/{nombre_usuario}/seguidores/yo", status_code=204)
def dejar_de_seguir(nombre_usuario: str, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    conn.execute("CALL social.dejar_de_seguir(%s, %s)", (usuario.id, id_de(conn, nombre_usuario)))
    return Response(status_code=204)


@app.get("/v1/sugerencias")
def sugerencias(usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    try:
        respuesta = httpx.get(f"{url_grafo()}/v1/sugerencias/{usuario.id}", timeout=3)
        respuesta.raise_for_status()
        datos = respuesta.json()
    except httpx.HTTPError:
        return {"sugerencias": [], "aviso": "Las sugerencias no están disponibles en este momento."}
    # El grafo da el orden; la base, el nombre visible y la foto (y descarta cuentas que ya no están activas).
    ids = [s["usuario_id"] for s in datos["sugerencias"]]
    perfiles = {str(f[0]): f for f in conn.execute(
        "SELECT id, nombre_visible, foto FROM social.usuario WHERE id = ANY (%s::uuid[]) AND estado = 'activo'", (ids,))}
    datos["sugerencias"] = [{**s, "nombre_visible": perfiles[s["usuario_id"]][1], "foto": fotos.url(perfiles[s["usuario_id"]][2])}
                            for s in datos["sugerencias"] if s["usuario_id"] in perfiles]
    return datos


# --- Publicaciones ----------------------------------------------------------------------------


@app.post("/v1/publicaciones", status_code=201)
def publicar(datos: NuevaPublicacion, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    publicacion_id = conn.execute(
        "CALL social.publicar(%s, %s, %s, %s, %s, NULL)",
        (usuario.id, datos.texto, datos.responde_a_id, datos.comparte_id, [str(f) for f in datos.figuras_ids]),
    ).fetchone()[0]
    return una_publicacion(conn, publicacion_id, usuario.id)


@app.get("/v1/publicaciones/{publicacion_id}")
def ver_publicacion(publicacion_id: UUID, usuario: Usuario | None = Depends(usuario_opcional), conn=Depends(conexion)):
    encontradas = lecturas.publicaciones(conn, [publicacion_id], usuario.id if usuario else None)
    if not encontradas:
        raise ErrorApi("publicacion_inexistente", 404, "No existe esa publicación.")
    return encontradas[0]


@app.get("/v1/publicaciones/{publicacion_id}/hilo")
def hilo(publicacion_id: UUID, usuario: Usuario | None = Depends(usuario_opcional), conn=Depends(conexion)):
    filas = conn.execute("SELECT id, profundidad FROM social.hilo(%s)", (publicacion_id,)).fetchall()
    if not filas:
        raise ErrorApi("publicacion_inexistente", 404, "No existe esa publicación.")
    profundidad = {str(i): p for i, p in filas}
    pubs = lecturas.publicaciones(conn, [i for i, _ in filas], usuario.id if usuario else None)
    # Si quien mira no puede ver la publicación (comunidad privada), el hilo no existe para esa persona: 404 como
    # el detalle, no un hilo vacío (auditoría PR-07).
    if not any(p["id"] == str(publicacion_id) for p in pubs):
        raise ErrorApi("publicacion_inexistente", 404, "No existe esa publicación.")
    return {"hilo": [{**p, "profundidad": profundidad[p["id"]]} for p in pubs]}


def una_publicacion(conn, publicacion_id, yo):
    """La publicación tal como la ve `yo`; si no puede verla (o no existe), 404 en vez de un error del servidor."""
    filas = lecturas.publicaciones(conn, [publicacion_id], yo)
    if not filas:
        raise ErrorApi("publicacion_inexistente", 404, "No existe esa publicación.")
    return filas[0]


@app.get("/v1/publicaciones/{publicacion_id}/difusion")
def difusion(publicacion_id: UUID, usuario: Usuario | None = Depends(usuario_opcional), conn=Depends(conexion)):
    # La base decide qué puede ver quien mira (auditoría PR-07): la publicación y cada compartida de la difusión.
    yo = usuario.id if usuario else None
    if not conn.execute("SELECT social.puede_ver_publicacion(%s, %s)", (publicacion_id, yo)).fetchone()[0]:
        raise ErrorApi("publicacion_inexistente", 404, "No existe esa publicación.")
    try:
        respuesta = httpx.get(f"{url_grafo()}/v1/difusion/{publicacion_id}", timeout=5)
        respuesta.raise_for_status()
        datos = respuesta.json()
    except httpx.HTTPError:
        raise ErrorApi("grafo_no_disponible", 503, "La difusión no está disponible en este momento.")
    ids = [c["compartida_id"] for c in datos.get("compartidas", [])]
    visibles = {str(i) for (i,) in conn.execute(
        "SELECT id FROM unnest(%s::uuid[]) AS id WHERE social.puede_ver_publicacion(id, %s)", (ids, yo))} if ids else set()
    datos["compartidas"] = [c for c in datos.get("compartidas", []) if c["compartida_id"] in visibles]
    datos["alcance"] = len({c["compartida_por"] for c in datos["compartidas"]})
    datos["profundidad_maxima"] = max((c["profundidad"] for c in datos["compartidas"]), default=0)
    return datos


@app.delete("/v1/publicaciones/{publicacion_id}", status_code=204)
def retirar(publicacion_id: UUID, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    conn.execute("CALL social.retirar_publicacion(%s, %s)", (publicacion_id, usuario.id))
    return Response(status_code=204)


@app.put("/v1/publicaciones/{publicacion_id}/reacciones/yo")
def reaccionar(publicacion_id: UUID, datos: Reaccion, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    conn.execute("CALL social.reaccionar(%s, %s, %s)", (publicacion_id, usuario.id, datos.tipo))
    return una_publicacion(conn, publicacion_id, usuario.id)


@app.delete("/v1/publicaciones/{publicacion_id}/reacciones/yo")
def quitar_reaccion(publicacion_id: UUID, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    conn.execute("CALL social.quitar_reaccion(%s, %s)", (publicacion_id, usuario.id))
    return una_publicacion(conn, publicacion_id, usuario.id)


# --- Feed, tendencias y figuras ---------------------------------------------------------------


@app.get("/v1/feed")
def feed(despues: datetime | None = None, limite: int = Query(30, ge=1, le=50),
         usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    """El grafo da el orden (quienes sigo y quienes siguen ellos); la base completa cada publicación.

    Si el grafo no responde, la red sigue funcionando: se usa la base, solo con quienes sigo.
    """
    try:
        parametros = {"limite": limite} | ({"antes_de": despues.isoformat()} if despues else {})
        respuesta = httpx.get(f"{url_grafo()}/v1/feed/{usuario.id}", params=parametros, timeout=3)
        respuesta.raise_for_status()
        del_grafo = respuesta.json()["publicaciones"]
        ids, distancia, fuente = ([f["publicacion_id"] for f in del_grafo],
                                  {f["publicacion_id"]: f["distancia"] for f in del_grafo}, "grafo")
    except httpx.HTTPError:
        ids = lecturas.feed_de_respaldo(conn, usuario.id, despues, limite)
        distancia, fuente = {i: 1 for i in ids}, "respaldo"
    pubs = [{**p, "distancia": distancia[p["id"]]} for p in lecturas.publicaciones(conn, ids, usuario.id)]
    return {"publicaciones": pubs, "fuente": fuente,
            "siguiente": pubs[-1]["creado_en"] if len(pubs) == limite else None}


@app.get("/v1/tendencias")
def tendencias(conn=Depends(conexion)):
    with conn.cursor(row_factory=dict_row) as cur:
        filas = cur.execute(
            "SELECT e.nombre AS etiqueta, t.total_publicaciones, t.total_autores, t.diversidad::text, t.puntaje::text,"
            " t.posicion, t.ventana_inicio, t.ventana_fin FROM social.tendencia t"
            " JOIN social.etiqueta e ON e.id = t.etiqueta_id"
            " WHERE (t.ventana_inicio, t.ventana_fin) = (SELECT ventana_inicio, ventana_fin FROM social.tendencia"
            "        WHERE ventana_fin >= now() - interval '2 hours' ORDER BY ventana_fin DESC LIMIT 1)"
            " ORDER BY t.posicion").fetchall()
        if filas:
            return {"fuente": "grafo", "tendencias": filas}
        ahora = datetime.now(timezone.utc)
        basicas = cur.execute("SELECT * FROM social.tendencias_basicas(%s, %s)",
                              (ahora - timedelta(hours=24), ahora)).fetchall()
        return {"fuente": "basica", "aviso": "Tendencias sin calcular diversidad.", "tendencias": basicas}


@app.get("/v1/tendencias/{etiqueta}")
def pagina_tendencia(etiqueta: str, usuario: Usuario | None = Depends(usuario_opcional), conn=Depends(conexion)):
    ahora = datetime.now(timezone.utc)
    contenido = conn.execute("SELECT tipo, id FROM social.contenido_tendencia(%s, %s, %s)",
                             (etiqueta, ahora - timedelta(days=7), ahora)).fetchall()
    publicaciones_ids = [str(i) for t, i in contenido if t == "publicacion"]
    declaraciones_ids = [str(i) for t, i in contenido if t == "declaracion"]
    with conn.cursor(row_factory=dict_row) as cur:
        declaraciones = cur.execute(
            "SELECT d.id::text, d.texto, d.dicha_el, d.tipo, d.url_fuente, f.id::text AS figura_id, f.nombre_completo"
            " FROM social.declaracion d JOIN social.figura_publica f ON f.id = d.figura_id"
            " WHERE d.id = ANY (%s) ORDER BY d.dicha_el DESC", (declaraciones_ids,)).fetchall()
        resumen = cur.execute("SELECT * FROM verificacion.resumen_conclusiones(%s, %s, NULL)",
                              (publicaciones_ids, declaraciones_ids)).fetchall()
    return {"etiqueta": etiqueta.lower(), "declaraciones": declaraciones,
            "publicaciones": lecturas.publicaciones(conn, publicaciones_ids, usuario.id if usuario else None),
            "resumen": resumen}


FIGURA = ("SELECT id::text, nombre_completo, cargo, url_fuente_cargo, cargo_desde, cargo_hasta, partido,"
          " url_fuente_partido, foto, estado FROM social.figura_publica")


def _figura(f: dict) -> dict:
    return {**f, "foto": fotos.url(f["foto"])}


# --- Equipo: quién verifica y quién administra (migración 0035) ---------------------------------------------


@app.get("/v1/equipo")
def equipo(conn=Depends(conexion)):
    """Público, como la bitácora de figuras: quién tiene permiso de verificar y quién se lo dio, y por qué."""
    with conn.cursor(row_factory=dict_row) as cur:
        miembros = cur.execute(
            "SELECT e.nombre_usuario, e.nombre_visible, e.rol, e.desde, u.foto FROM social.equipo e"
            " JOIN social.usuario u ON u.id = e.id ORDER BY e.rol = 'admin' DESC, e.nombre_visible").fetchall()
        bitacora = cur.execute(
            "SELECT c.id, u.nombre_usuario, u.nombre_visible, c.rol_anterior, c.rol_nuevo, a.nombre_usuario AS actor,"
            " c.motivo, c.creado_en FROM social.cambio_rol c JOIN social.usuario u ON u.id = c.usuario_id"
            " LEFT JOIN social.usuario a ON a.id = c.actor_id ORDER BY c.id DESC LIMIT 100").fetchall()
    for m in miembros:
        m["foto"] = fotos.url(m["foto"])
    return {"miembros": miembros, "bitacora": bitacora}


@app.post("/v1/equipo/roles")
def asignar_rol(datos: CambioRol, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    """La base decide: solo un administrador, con motivo, y nunca dejando a Parrhesia sin administrador."""
    destino = conn.execute("SELECT id FROM social.usuario WHERE nombre_usuario = %s AND estado = 'activo'",
                           (datos.nombre_usuario,)).fetchone()
    if destino is None:
        raise ErrorApi("usuario_inexistente", 404, "No hay una cuenta activa con ese nombre de usuario.")
    conn.execute("CALL social.asignar_rol(%s, %s, %s, %s)", (usuario.id, destino[0], datos.rol, datos.motivo.strip()))
    return equipo(conn)


@app.get("/v1/figuras")
def figuras(archivadas: bool = False, conn=Depends(conexion)):
    with conn.cursor(row_factory=dict_row) as cur:
        filas = cur.execute(FIGURA + (" " if archivadas else " WHERE estado = 'activa'") + " ORDER BY nombre_completo").fetchall()
    return {"figuras": [_figura(f) for f in filas]}


@app.get("/v1/figuras/parecidas")
def figuras_parecidas(nombre: str = Query(min_length=3, max_length=120), conn=Depends(conexion)):
    """Fichas con nombre parecido: se consulta antes de crear o proponer, para no duplicar."""
    with conn.cursor(row_factory=dict_row) as cur:
        filas = cur.execute("SELECT id::text, nombre_completo, cargo, parecido FROM social.figuras_parecidas(%s)", (nombre,)).fetchall()
    return {"parecidas": filas}


@app.get("/v1/figuras/{figura_id}")
def figura(figura_id: UUID, conn=Depends(conexion)):
    with conn.cursor(row_factory=dict_row) as cur:
        datos = cur.execute(FIGURA + " WHERE id = %s", (figura_id,)).fetchone()
        if datos is None:
            raise ErrorApi("figura_inexistente", 404, "No existe esa figura pública.")
        datos["declaraciones"] = cur.execute(
            "SELECT d.id::text, d.texto, d.dicha_el, d.tipo, d.url_fuente, d.estado_promesa,"
            " ARRAY(SELECT e.nombre FROM social.declaracion_etiqueta de JOIN social.etiqueta e ON e.id = de.etiqueta_id"
            "       WHERE de.declaracion_id = d.id ORDER BY e.nombre) AS etiquetas"
            " FROM social.declaracion d WHERE d.figura_id = %s ORDER BY d.dicha_el DESC", (figura_id,)).fetchall()
    return _figura(datos)


@app.post("/v1/figuras", status_code=201)
def crear_figura(datos: NuevaFigura, usuario: Usuario = Depends(verificador), conn=Depends(conexion)):
    figura_id = conn.execute("CALL social.crear_figura(%s, %s, %s, %s, %s, %s, %s, %s, NULL)",
                             (usuario.id, datos.nombre_completo, datos.cargo, datos.url_fuente_cargo, datos.cargo_desde,
                              datos.cargo_hasta, datos.partido, datos.url_fuente_partido)).fetchone()[0]
    return figura(figura_id, conn)


@app.patch("/v1/figuras/{figura_id}")
def editar_figura(figura_id: UUID, datos: CambioFigura, usuario: Usuario = Depends(verificador), conn=Depends(conexion)):
    conn.execute("CALL social.editar_figura(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                 (usuario.id, figura_id, datos.nombre_completo, datos.cargo, datos.url_fuente_cargo, datos.cargo_desde,
                  datos.cargo_hasta, datos.partido, datos.url_fuente_partido, datos.estado, datos.motivo))
    return figura(figura_id, conn)


@app.put("/v1/figuras/{figura_id}/foto")
def foto_figura(figura_id: UUID, foto: UploadFile = File(...), usuario: Usuario = Depends(verificador), conn=Depends(conexion)):
    nombre = fotos.guardar(fotos.procesar(foto.file.read(fotos.MAXIMO_BYTES + 1)))
    try:
        anterior = conn.execute("CALL social.fijar_foto_figura(%s, %s, %s, NULL)", (usuario.id, figura_id, nombre)).fetchone()[0]
        conn.commit()
    except Exception:
        fotos.borrar(nombre)
        raise
    fotos.borrar(anterior)
    return {"foto": fotos.url(nombre)}


@app.get("/v1/figuras/{figura_id}/bitacora")
def bitacora_figura(figura_id: UUID, conn=Depends(conexion)):
    """Quién cambió qué en la ficha (antes y después). Pública: la ficha es de interés público."""
    with conn.cursor(row_factory=dict_row) as cur:
        filas = cur.execute(
            "SELECT b.accion, u.nombre_usuario AS actor, b.cambios, b.motivo, b.creada_en FROM social.bitacora_figura b"
            " JOIN social.usuario u ON u.id = b.actor_id WHERE b.figura_id = %s ORDER BY b.id DESC LIMIT 100", (figura_id,)).fetchall()
    return {"bitacora": [{**f, "creada_en": f["creada_en"].isoformat()} for f in filas]}


@app.post("/v1/propuestas-figura", status_code=201)
def proponer_figura(datos: PropuestaFigura, usuario: Usuario = Depends(usuario_actual), conn=Depends(conexion)):
    propuesta = conn.execute("CALL social.proponer_figura(%s, %s, %s, %s, %s, NULL)",
                             (usuario.id, datos.nombre_completo, datos.cargo, datos.url_fuente, datos.nota)).fetchone()[0]
    return {"id": str(propuesta), "estado": "pendiente"}


@app.get("/v1/propuestas-figura")
def propuestas_figura(usuario: Usuario = Depends(verificador), conn=Depends(conexion)):
    with conn.cursor(row_factory=dict_row) as cur:
        filas = cur.execute(
            "SELECT p.id::text, p.nombre_completo, p.cargo, p.url_fuente, p.nota, p.creada_en, u.nombre_usuario AS propuesta_por"
            " FROM social.propuesta_figura p JOIN social.usuario u ON u.id = p.propuesta_por"
            " WHERE p.estado = 'pendiente' ORDER BY p.creada_en").fetchall()
        for f in filas:
            f["parecidas"] = cur.execute("SELECT id::text, nombre_completo, cargo FROM social.figuras_parecidas(%s)",
                                         (f["nombre_completo"],)).fetchall()
    return {"propuestas": [{**f, "creada_en": f["creada_en"].isoformat()} for f in filas]}


@app.post("/v1/propuestas-figura/{propuesta_id}/resolucion")
def resolver_propuesta_figura(propuesta_id: UUID, datos: ResolucionPropuesta, usuario: Usuario = Depends(verificador),
                              conn=Depends(conexion)):
    figura_id = conn.execute("CALL social.resolver_propuesta_figura(%s, %s, %s, %s, NULL)",
                             (usuario.id, propuesta_id, datos.aceptar, datos.motivo)).fetchone()[0]
    return {"figura_id": str(figura_id) if figura_id else None}


@app.post("/v1/figuras/{figura_id}/declaraciones", status_code=201)
def registrar_declaracion(figura_id: UUID, datos: NuevaDeclaracion, usuario: Usuario = Depends(verificador),
                          conn=Depends(conexion)):
    declaracion_id = conn.execute(
        "CALL social.registrar_declaracion(%s, %s, %s, %s, %s, %s, %s, NULL)",
        (usuario.id, figura_id, datos.texto, datos.dicha_el, datos.tipo, datos.url_fuente, datos.etiquetas),
    ).fetchone()[0]
    return {"id": str(declaracion_id)}


# --- Comunidades (decisión 28): endpoints en su propio módulo -------------------------------------
from servicios.social import comunidades  # noqa: E402  (al final: el módulo usa conexion e id_de de aquí)

app.include_router(comunidades.router)
