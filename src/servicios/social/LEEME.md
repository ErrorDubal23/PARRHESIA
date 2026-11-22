# Servicio social

Cuentas, publicaciones, seguimientos, reacciones, feed, tendencias y figuras públicas. Contrato: `docs/diseno/07_apis.md`, sección 1.

```bash
uv run uvicorn servicios.social.api:app --port 8001    # documentación interactiva en http://127.0.0.1:8001/docs
```

- Toda escritura es un `CALL` a un procedimiento de `social`: la API no escribe en las tablas directamente.
- Contraseñas con argon2id (la base rechaza cualquier otra cosa); sesión con JWT firmado con `JWT_SECRETO`.
- El feed pide el orden al servicio de grafo (`GRAFO_URL`); si no responde, usa la base con solo las personas que sigo (`"fuente": "respaldo"`).
- Los errores de la base llegan con la forma `{"error": {"codigo", "mensaje"}}` (`servicios/comun/errores.py`).
