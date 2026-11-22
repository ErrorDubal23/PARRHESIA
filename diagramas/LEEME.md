# Diagramas del modelo de datos

MER en notación de Chen y modelo relacional (MR), en `.drawio` (se abren y editan con draw.io) y en `.png`.

| Archivo | Qué muestra |
|---|---|
| `MER_1_red_social_y_temas` | Usuarios, publicaciones, seguimientos, reacciones, etiquetas, tendencias, figuras públicas, declaraciones, y los temas del día (medios, artículos, temas, declaraciones reportadas) |
| `MER_2_verificacion_e_ia` | Afirmaciones, verificaciones, evidencia, pruebas de robustez, revisiones, palabras clave y la cola de IA. Las entidades con borde punteado vienen de otros MER |
| `MER_3_datos_oficiales` | Fuentes, indicadores, series, descargas, observaciones, contrastes y alertas |
| `NEO4J_1_modelo_de_grafo` | El grafo de Neo4j: nodos con sus propiedades y restricciones, relaciones con las suyas, y las cuatro consultas |
| `NEO4J_2_postgres_a_neo4j` | Cómo se relacionan las dos bases: qué tabla de PostgreSQL genera cada nodo o relación, por qué evento del outbox, y el camino de un evento paso a paso |
| `MR_1_oficial` … `MR_5_temas` | Un MR por esquema de PostgreSQL, con tipos, PK, FK, UQ, CK, NULL y todas las restricciones CHECK con su nombre |

## Cómo leerlos

- **MER (Chen):** rectángulo = entidad, rombo = relación, elipse = atributo. Subrayado = identificador; elipse punteada = atributo derivado (lo calcula la base, por ejemplo los contadores); doble elipse = multivaluado (`marcas`); doble rectángulo y doble rombo = entidad débil y la relación que la identifica (`INTENTO_IA`, `PALABRA_CLAVE`).
- **(mín,máx)** junto a una entidad: en cuántas relaciones de ese tipo participa cada ejemplar de esa entidad. Ejemplo: `USUARIO (0,N) escribe (1,1) PUBLICACION` → un usuario escribe de 0 a N publicaciones; cada publicación la escribe exactamente un usuario.
- **MR:** pata de gallo en la tabla hija. `→ esquema.tabla` en azul es una referencia a otro esquema que revisa un trigger, no una llave foránea (decisión 1).

## Cómo regenerarlos

Los MR se leen de la base real, así que siempre coinciden con lo implementado. Después de una migración:

```bash
uv run python diagramas/generar_diagramas.py
```

Necesita la base encendida (`docker compose up -d`) y draw.io instalado para exportar los PNG. Los MER se definen a mano en el mismo script. Si se ajusta un diagrama a mano en draw.io, regenerarlo borra ese ajuste.
