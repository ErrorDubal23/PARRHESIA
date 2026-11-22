"""Fotos de perfil: se reciben, se vuelven a codificar y se guardan en disco (nunca en la base).

Seguridad:
- Tamaño máximo 2 MB y 20 megapíxeles (evita las "bombas de descompresión").
- Solo JPEG, PNG o WebP, según el contenido del archivo (no según su nombre ni su tipo declarado).
- La imagen se decodifica y se vuelve a codificar como WebP de 400 × 400: se pierden los metadatos
  (ubicación GPS de la cámara, por ejemplo) y cualquier contenido escondido dentro del archivo.
- El nombre en disco es aleatorio (32 hex) y la base solo acepta ese formato: no hay rutas inventadas.
"""

from __future__ import annotations

import os
import re
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from servicios.comun.errores import ErrorApi

MAXIMO_BYTES = 2 * 1024 * 1024
MAXIMO_PIXELES = 20_000_000
LADO = 400
FORMATOS = {"JPEG", "PNG", "WEBP"}
NOMBRE = re.compile(r"^[0-9a-f]{32}\.webp$")

Image.MAX_IMAGE_PIXELS = MAXIMO_PIXELES


def carpeta() -> Path:
    ruta = Path(os.environ.get("FOTOS_DIR", "data/fotos"))
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def procesar(datos: bytes) -> bytes:
    """La imagen recibida convertida en un WebP cuadrado limpio, o un error claro."""
    if len(datos) > MAXIMO_BYTES:
        raise ErrorApi("foto_muy_grande", 413, "La foto pesa más de 2 MB.")
    try:
        with Image.open(BytesIO(datos)) as imagen:
            if imagen.format not in FORMATOS:
                raise ErrorApi("foto_formato", 415, "La foto debe ser JPG, PNG o WebP.")
            if imagen.width * imagen.height > MAXIMO_PIXELES:
                raise ErrorApi("foto_muy_grande", 413, "La foto tiene demasiados píxeles.")
            imagen.load()
            limpia = ImageOps.exif_transpose(imagen).convert("RGB")  # respeta la orientación y descarta lo demás
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError):
        raise ErrorApi("foto_formato", 415, "No se pudo leer la imagen. Usa JPG, PNG o WebP.")
    cuadrada = ImageOps.fit(limpia, (LADO, LADO), method=Image.Resampling.LANCZOS)
    salida = BytesIO()
    cuadrada.save(salida, "WEBP", quality=86, method=6)  # sin exif ni icc: no se copian metadatos
    return salida.getvalue()


def guardar(webp: bytes) -> str:
    nombre = f"{uuid.uuid4().hex}.webp"
    destino = carpeta() / nombre
    temporal = destino.with_suffix(".tmp")
    temporal.write_bytes(webp)
    temporal.replace(destino)  # escritura atómica
    return nombre


def borrar(nombre: str | None) -> None:
    if nombre and NOMBRE.match(nombre):
        (carpeta() / nombre).unlink(missing_ok=True)


def ruta(nombre: str) -> Path:
    if not NOMBRE.match(nombre):
        raise ErrorApi("foto_inexistente", 404, "No existe esa foto.")
    destino = carpeta() / nombre
    if not destino.is_file():
        raise ErrorApi("foto_inexistente", 404, "No existe esa foto.")
    return destino


def url(nombre: str | None) -> str | None:
    """Ruta pública de la foto a través de la puerta de entrada."""
    return f"/api/social/v1/fotos/{nombre}" if nombre else None
