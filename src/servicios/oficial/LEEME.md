# Servicio de datos oficiales

Series aprobadas con sus valores exactos, la trazabilidad de cada dato hasta el archivo original y la revisión de alertas. Contrato: `docs/diseno/07_apis.md`, sección 5. Los conectores que llenan la base siguen en `src/app` (`uv run python -m app.runs ... --db`).

```bash
uv run uvicorn servicios.oficial.api:app --port 8005
```
