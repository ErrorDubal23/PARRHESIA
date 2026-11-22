# Lógica de la base de datos: procedimientos, funciones, triggers y transacciones

Versión 2 (20 nov 2026). Complementa el [MR](02_MR.md), el [modelo de grafo](04_modelo_grafo.md) y el [servicio de IA](03_servicio_ia.md). Nombres en español sin tildes (decisión 14, [glosario](glosario_codigo.md)). Todo esto se implementa en la migración 0002 y cada regla tiene al menos una prueba que intenta romperla. Las decisiones 9 a 13 que este documento necesita están aprobadas en [00_decisiones.md](00_decisiones.md).

## Convenciones

- **Procedimiento (`PROCEDURE`, se llama con `CALL`)** para toda operación que escribe en varias tablas a la vez: hace las validaciones, las inserciones y los cambios como una sola unidad. Devuelve el identificador creado en un parámetro `INOUT`.
- **Función (`FUNCTION`)** para lecturas y cálculos. Las que solo leen se declaran `STABLE`; las que solo calculan sobre sus argumentos, `IMMUTABLE`.
- **Trigger** para reglas que deben cumplirse sin importar quién escriba: contadores, historial de solo inserción, outbox, transiciones de estado e integridad entre esquemas.
- **Errores** con `RAISE EXCEPTION` y un código estable en el mensaje (por ejemplo `autor_inactivo`). El servicio lo traduce a un mensaje claro para el usuario.
- **Aislamiento:** `READ COMMITTED` (el de PostgreSQL por defecto). Donde hay carreras posibles se bloquea la fila con `SELECT ... FOR UPDATE` dentro del procedimiento; no hace falta subir el nivel de aislamiento.
- Los procedimientos no hacen `COMMIT` dentro: el servicio abre la transacción, llama al procedimiento y confirma. Si algo falla, se deshace todo.

---

## Esquema `util`

| Objeto | Tipo | Qué hace |
| --- | --- | --- |
| `util.prohibir_cambios()` | función de trigger | Lanza error en `UPDATE` o `DELETE`. Protege las tablas de solo inserción (es la `forbid_update_delete` de 0001, renombrada) |
| `util.marcar_actualizado()` | función de trigger | Pone `actualizado_en = now()` en cada `UPDATE` (es la `touch_updated_at` de 0001) |
| `util.validar_transicion()` | función de trigger | Recibe en `TG_ARGV` las transiciones permitidas de `estado` (por ejemplo `{"en_cola":["en_curso"],"en_curso":["en_cola","terminado","fallido"]}`) y rechaza cualquier otra. Se reutiliza en `ia.trabajo`, `verificacion.afirmacion`, `social.usuario` y `social.publicacion` |

---

## Esquema `oficial`

Las tablas ya existen; 0002 las mueve y renombra (ver [MR](02_MR.md), decisión general 9), lo que conserva datos, índices y triggers.

### Funciones

```sql
-- Valor vigente de cada periodo: la última versión (mayor secuencia), solo si está aceptada.
CREATE FUNCTION oficial.observaciones_vigentes(p_codigo_serie text, p_desde text, p_hasta text)
RETURNS TABLE (observacion_id uuid, periodo text, territorio text, valor numeric, marcas text[])
LANGUAGE sql STABLE AS $$
  SELECT id, periodo, territorio, valor, marcas
  FROM (
    SELECT DISTINCT ON (o.periodo, o.territorio) o.*
    FROM oficial.observacion o
    JOIN oficial.serie s ON s.id = o.serie_id
    WHERE s.codigo = p_codigo_serie AND s.aprobada
      AND o.periodo BETWEEN p_desde AND p_hasta
    ORDER BY o.periodo, o.territorio, o.secuencia DESC
  ) ultima
  WHERE ultima.estado = 'aceptada'
  ORDER BY periodo;
$$;
```

Como los periodos tienen formato fijo (`AAAA`, `AAAA-MM`, `AAAA-MM-DD`), la comparación de texto ordena bien.

| Función | Devuelve | Para qué |
| --- | --- | --- |
| `oficial.observaciones_vigentes(serie, desde, hasta)` | tabla | La usa la verificación para traer el valor oficial y la serie completa del contexto |
| `oficial.observacion_en(serie, periodo, territorio)` | una fila o nada | El valor de un solo periodo; nada si no existe o está en cuarentena (entonces la conclusión es "sin dato comparable") |
| `oficial.esta_aceptada(observacion_id)` | boolean | La usa el trigger de evidencia de `verificacion` |
| `oficial.serie_aprobada(codigo)` | boolean | La usa el trigger de `verificacion.verificacion` |
| `oficial.alertas_abiertas(serie)` | tabla | Alertas abiertas, para mostrarlas junto a la cifra |

### Procedimientos

```sql
CREATE PROCEDURE oficial.cerrar_alerta(p_alerta_id uuid, p_actor text, p_motivo text)
LANGUAGE plpgsql AS $$
BEGIN
  PERFORM 1 FROM oficial.alerta WHERE id = p_alerta_id AND estado = 'abierta' FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'alerta_no_abierta'; END IF;
  UPDATE oficial.alerta SET estado = 'cerrada' WHERE id = p_alerta_id;
  INSERT INTO oficial.evento_alerta (alerta_id, evento, actor, motivo)
  VALUES (p_alerta_id, 'cerrada', p_actor, p_motivo);
END $$;
```

`oficial.reabrir_alerta` es simétrico. El `FOR UPDATE` evita que dos revisores cierren la misma alerta a la vez y que quede con dos eventos de cierre. Un trigger nuevo, `alerta_cambio_con_evento` (diferido al final de la transacción), rechaza un cambio de `estado` que no tenga su `evento_alerta` en la misma transacción.

---

## Esquema `social`

### Funciones

| Función | Tipo | Qué hace |
| --- | --- | --- |
| `social.extraer_etiquetas(texto) → text[]` | `IMMUTABLE` | `#palabra` en minúsculas, sin repetir, máximo 10. Regex `#([[:alnum:]_]{1,50})` |
| `social.extraer_menciones(texto) → text[]` | `IMMUTABLE` | `@usuario` en minúsculas, sin repetir, máximo 10 |
| `social.hilo(publicacion_id)` | `STABLE` | Hilo completo de respuestas con `WITH RECURSIVE`: cada fila con su profundidad y su ruta, en orden de lectura; las retiradas conservan su lugar ("publicación retirada") |
| `social.estadisticas_usuario(usuario_id)` | `STABLE` | Seguidores, seguidos y publicaciones visibles |
| `social.contenido_tendencia(etiqueta, desde, hasta)` | `STABLE` | Lo que alimenta la página de una tendencia: las declaraciones ligadas a la etiqueta (con su figura y su fuente) y las publicaciones visibles con esa etiqueta en la ventana. Devuelve los `id`; las conclusiones las pone `verificacion.resumen_conclusiones` |
| `social.tendencias_basicas(desde, hasta)` | `STABLE` | Respaldo si Neo4j no está: etiquetas por número de autores distintos (≥ 3, cuentas de más de 7 días), sin diversidad. La app lo muestra como "tendencias sin calcular diversidad" |

```sql
CREATE FUNCTION social.hilo(p_publicacion_id uuid)
RETURNS TABLE (id uuid, responde_a_id uuid, profundidad int, ruta uuid[], estado text)
LANGUAGE sql STABLE AS $$
  WITH RECURSIVE hilo AS (
    SELECT p.id, p.responde_a_id, 0 AS profundidad, ARRAY[p.id] AS ruta, p.estado
    FROM social.publicacion p WHERE p.id = p_publicacion_id
    UNION ALL
    SELECT r.id, r.responde_a_id, h.profundidad + 1, h.ruta || r.id, r.estado
    FROM social.publicacion r JOIN hilo h ON r.responde_a_id = h.id
    WHERE h.profundidad < 50
  )
  SELECT * FROM hilo ORDER BY ruta;
$$;
```

### Procedimientos

| Procedimiento | Qué hace en una sola transacción |
| --- | --- |
| `social.registrar_usuario(nombre_usuario, nombre_visible, correo, clave_hash, INOUT usuario_id)` | Inserta la cuenta con el nombre de usuario en minúsculas. Los duplicados los rechazan las restricciones únicas |
| `social.publicar(autor_id, texto, responde_a_id, comparte_id, figuras_ids uuid[], INOUT publicacion_id)` | Ver abajo |
| `social.retirar_publicacion(publicacion_id, actor_id, motivo)` | Si el actor es el autor: `retirada_por_autor`; si es `admin`: `retirada_por_moderacion`. Bloquea la fila con `FOR UPDATE` |
| `social.seguir(seguidor_id, seguido_id)` | `INSERT ... ON CONFLICT DO NOTHING`: seguir dos veces no es un error ni duplica el evento |
| `social.dejar_de_seguir(seguidor_id, seguido_id)` | Borra la fila si existe |
| `social.reaccionar(publicacion_id, usuario_id, tipo)` | `INSERT ... ON CONFLICT (publicacion_id, usuario_id) DO UPDATE SET tipo = ...`: cambiar de "me gusta" a "útil" no suma dos reacciones |
| `social.quitar_reaccion(publicacion_id, usuario_id)` | Borra la reacción si existe |
| `social.registrar_declaracion(registrada_por, figura_id, texto, dicha_el, tipo, url_fuente, etiquetas text[], INOUT declaracion_id)` | Revisa que quien registra sea `verificador` o `admin`, inserta la declaración y sus etiquetas (creándolas si no existen). Un trigger de outbox emite `declaracion_creada` para que el servicio de verificación la procese igual que una publicación |
| `social.registrar_tendencias(ventana_inicio, ventana_fin, filas jsonb)` | La llama el servicio de grafo: inserta las filas de una ventana de tendencias, todas o ninguna |

```sql
CREATE PROCEDURE social.publicar(
  p_autor_id uuid, p_texto text, p_responde_a_id uuid, p_comparte_id uuid,
  p_figuras_ids uuid[], INOUT p_publicacion_id uuid)
LANGUAGE plpgsql AS $$
DECLARE v_etiqueta text;
BEGIN
  PERFORM 1 FROM social.usuario WHERE id = p_autor_id AND estado = 'activo';
  IF NOT FOUND THEN RAISE EXCEPTION 'autor_inactivo'; END IF;

  -- No se responde ni se comparte una publicación retirada.
  IF p_responde_a_id IS NOT NULL OR p_comparte_id IS NOT NULL THEN
    PERFORM 1 FROM social.publicacion
    WHERE id = coalesce(p_responde_a_id, p_comparte_id) AND estado = 'visible'
    FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'publicacion_destino_no_visible'; END IF;
  END IF;

  INSERT INTO social.publicacion (autor_id, texto, responde_a_id, comparte_id, estado)
  VALUES (p_autor_id, p_texto, p_responde_a_id, p_comparte_id, 'visible')
  RETURNING id INTO p_publicacion_id;

  FOREACH v_etiqueta IN ARRAY social.extraer_etiquetas(coalesce(p_texto, '')) LOOP
    INSERT INTO social.etiqueta (nombre) VALUES (v_etiqueta) ON CONFLICT (nombre) DO NOTHING;
    INSERT INTO social.publicacion_etiqueta (publicacion_id, etiqueta_id)
    SELECT p_publicacion_id, id FROM social.etiqueta WHERE nombre = v_etiqueta;
  END LOOP;

  -- Solo se guardan menciones de cuentas que existen.
  INSERT INTO social.mencion_usuario (publicacion_id, usuario_id)
  SELECT p_publicacion_id, u.id FROM social.usuario u
  WHERE u.nombre_usuario = ANY (social.extraer_menciones(coalesce(p_texto, '')));

  INSERT INTO social.mencion_figura (publicacion_id, figura_id)
  SELECT p_publicacion_id, f FROM unnest(coalesce(p_figuras_ids, '{}')) AS f;
END $$;
```

Las figuras públicas no tienen `@`; la app las elige de una lista y las manda en `figuras_ids`. La llave foránea rechaza una figura que no exista. Los eventos del outbox y los contadores no se escriben aquí: los ponen los triggers, así que también se cumplen si alguien inserta sin el procedimiento.

### Triggers

| Trigger | Tabla y momento | Qué hace |
| --- | --- | --- |
| `publicacion_contadores` | `publicacion`, `AFTER INSERT` y `AFTER UPDATE OF estado` | Al crear: suma 1 a `total_respuestas` o `total_compartidas` de la publicación original. Al retirar: resta 1. Los contadores cuentan solo publicaciones visibles |
| `reaccion_contadores` | `reaccion`, `AFTER INSERT OR DELETE` | Suma o resta 1 a `total_reacciones`. Cambiar el tipo no cambia el contador |
| `publicacion_cambios_permitidos` | `publicacion`, `BEFORE UPDATE` | Solo pueden cambiar `estado` (de `visible` a retirada, sin vuelta) y los contadores. Cambiar `texto`, el autor o la publicación original lanza error (decisión 11) |
| `usuario_cambios_permitidos` | `usuario`, `BEFORE UPDATE` | `nombre_usuario` y `correo` en minúsculas; `id` y `creado_en` no cambian |
| `<tabla>_actualizado` | `usuario`, `publicacion`, `reaccion`, `figura_publica` | `util.marcar_actualizado()` |
| `<tabla>_solo_insercion` | `tendencia`, `declaracion` | `util.prohibir_cambios()` |
| `<tabla>_solo_insercion` | `evento_salida`, `entrega_evento` | `util.prohibir_cambios()`. Quién leyó cada evento queda en `entrega_evento` (decisión 18) |
| `<tabla>_salida` | `usuario`, `seguimiento`, `publicacion`, `publicacion_etiqueta`, `declaracion`, `mencion_usuario`, `mencion_figura`, `reaccion`, `AFTER` | Insertan el evento en `evento_salida` (tabla siguiente) |
| `evento_salida_aviso` | `evento_salida`, `AFTER INSERT`, `FOR EACH STATEMENT` | `pg_notify('evento_salida', 'social')` para despertar a los servicios de grafo y de verificación sin que tenga que preguntar a cada rato |

Eventos que generan los triggers del outbox:

| Tabla | Operación | `tipo_evento` | `datos` |
| --- | --- | --- | --- |
| `usuario` | INSERT | `usuario_creado` | `id`, `nombre_usuario`, `estado`, `creado_en` |
| `usuario` | UPDATE de `estado` | `usuario_cambio_estado` | `id`, `estado` |
| `seguimiento` | INSERT / DELETE | `seguimiento_creado` / `seguimiento_borrado` | `seguidor`, `seguido`, `en` |
| `publicacion` | INSERT | `publicacion_creada` | `id`, `autor`, `responde_a`, `comparte`, `creado_en` |
| `publicacion` | UPDATE de `estado` | `publicacion_retirada` | `id`, `estado` |
| `publicacion_etiqueta` | INSERT | `publicacion_etiquetada` | `publicacion`, `etiqueta` |
| `declaracion` | INSERT | `declaracion_creada` | `id`, `figura`, `dicha_el` (el servicio de verificación la lee para extraer sus cifras; el grafo la ignora) |
| `mencion_usuario`, `mencion_figura` | INSERT | `publicacion_menciona` | `publicacion`, `tipo_destino`, `destino_id` |
| `reaccion` | INSERT o UPDATE / DELETE | `reaccion_puesta` / `reaccion_quitada` | `publicacion`, `usuario`, `tipo`, `en` |

Nunca van en `datos` el correo, la contraseña ni el texto de la publicación: el grafo no los necesita.

---

## Esquema `verificacion`

### Funciones

| Función | Tipo | Qué hace |
| --- | --- | --- |
| `verificacion.verificacion_vigente(afirmacion_id)` | `STABLE` | La versión vigente (la de mayor `version`) |
| `verificacion.estado_publicacion(publicacion_id) → text` | `STABLE` | `sin_cifras` (es opinión), `pendiente` (alguna afirmación sin verificación todavía), `lista` o `requiere_revision`. Es lo que la app muestra junto a la publicación |
| `verificacion.resumen_conclusiones(publicaciones uuid[], declaraciones uuid[])` | `STABLE` | Para la página de una tendencia: la verificación vigente de cada afirmación de esas publicaciones y declaraciones, el conteo por conclusión y las series oficiales citadas. Solo cuenta y agrupa lo guardado; no produce cifras nuevas |
| `verificacion.requiere_extraccion(texto) → boolean` | `STABLE` | Filtro previo sin IA (decisión 20): verdadero si el texto tiene al menos una cifra y una palabra de `verificacion.palabra_clave`. Si es falso, no se llama a la IA y la publicación queda como opinión |
| `util.cifras_en_texto(texto) → numeric[]` | `IMMUTABLE` | Está en `util` porque también la usa `temas`. Extrae las cifras de un texto en formato colombiano (`1.234,5` → `1234.5`; `9,28 %` → `9.28`) |
| `verificacion.cifras_permitidas(verificacion_id) → numeric[]` | `STABLE` | Las cifras que una explicación puede usar: valores de la evidencia, el valor que dijo la publicación y los años y meses de los periodos citados |

### Procedimientos

| Procedimiento | Qué hace en una sola transacción |
| --- | --- |
| `verificacion.registrar_afirmaciones(publicacion_id, declaracion_id o declaracion_reportada_id, trabajo_ia_id, afirmaciones jsonb)` | Inserta las afirmaciones que extrajo la IA, con su posición. Si no hay ninguna, no inserta nada y la publicación queda como opinión |
| `verificacion.registrar_verificacion(afirmacion_id, codigo_serie, conclusion, explicacion, explicacion_validada, version_motor, evidencias jsonb, pruebas jsonb, INOUT verificacion_id)` | Ver abajo |
| `verificacion.registrar_revision(verificacion_id, revisor_id, decision, motivo)` | Inserta la revisión. Si es `corregida`, la corrección llega como una versión nueva por `registrar_verificacion` |

```sql
CREATE PROCEDURE verificacion.registrar_verificacion(
  p_afirmacion_id uuid, p_codigo_serie text, p_conclusion text, p_explicacion text,
  p_explicacion_validada boolean, p_version_motor text,
  p_evidencias jsonb, p_pruebas jsonb, INOUT p_verificacion_id uuid)
LANGUAGE plpgsql AS $$
DECLARE v_version smallint;
BEGIN
  -- Bloquear la afirmación: dos verificaciones simultáneas no pueden tomar el mismo número de versión.
  PERFORM 1 FROM verificacion.afirmacion WHERE id = p_afirmacion_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'afirmacion_no_existe'; END IF;

  SELECT coalesce(max(version), 0) + 1 INTO v_version
  FROM verificacion.verificacion WHERE afirmacion_id = p_afirmacion_id;

  INSERT INTO verificacion.verificacion (afirmacion_id, version, codigo_serie, conclusion,
         explicacion, explicacion_validada, version_motor)
  VALUES (p_afirmacion_id, v_version, p_codigo_serie, p_conclusion,
          p_explicacion, p_explicacion_validada, p_version_motor)
  RETURNING id INTO p_verificacion_id;

  INSERT INTO verificacion.evidencia (verificacion_id, observacion_id, rol)
  SELECT p_verificacion_id, (e->>'observacion_id')::uuid, e->>'rol'
  FROM jsonb_array_elements(p_evidencias) e;

  INSERT INTO verificacion.resultado_prueba (verificacion_id, codigo_prueba, resultado, detalle)
  SELECT p_verificacion_id, r->>'codigo', r->>'resultado', r->>'detalle'
  FROM jsonb_array_elements(p_pruebas) r;

  UPDATE verificacion.afirmacion
  SET estado = CASE WHEN p_conclusion = 'sin_dato_comparable' THEN 'no_verificable' ELSE 'verificada' END
  WHERE id = p_afirmacion_id;
END $$;
```

### Triggers

| Trigger | Tabla y momento | Qué revisa |
| --- | --- | --- |
| `afirmacion_destino_existe` | `afirmacion`, `BEFORE INSERT` | Que `publicacion_id` exista en `social.publicacion`, `declaracion_id` en `social.declaracion` o `declaracion_reportada_id` en `temas.declaracion_reportada` |
| `evidencia_observacion_aceptada` | `evidencia`, `BEFORE INSERT` | `oficial.esta_aceptada(observacion_id)` |
| `verificacion_serie_existe` | `verificacion`, `BEFORE INSERT` | `oficial.serie_aprobada(codigo_serie)` si no es nulo; y que `codigo_serie` sea nulo si y solo si la conclusión es `sin_dato_comparable` |
| `verificacion_tiene_evidencia` | `verificacion`, `CONSTRAINT TRIGGER ... DEFERRABLE INITIALLY DEFERRED` | Al confirmar la transacción: una conclusión distinta de `sin_dato_comparable` tiene al menos una evidencia `citada`. Es diferido porque la evidencia se inserta después de la verificación |
| `explicacion_cifras_respaldadas` | `verificacion`, `CONSTRAINT TRIGGER` diferido | Si `explicacion_validada` es verdadero, toda cifra de `util.cifras_en_texto(explicacion)` está en `cifras_permitidas(id)` (decisión 12). Si no, la transacción completa se deshace |
| `revision_por_verificador` | `revision_humana`, `BEFORE INSERT` | Que el revisor tenga rol `verificador` o `admin` en `social.usuario` |
| `afirmacion_transicion` | `afirmacion`, `BEFORE UPDATE` | `util.validar_transicion`: `extraida → verificada / no_verificable / requiere_revision`, `requiere_revision → verificada`; el resto de columnas no cambia |
| `<tabla>_solo_insercion` | `verificacion`, `evidencia`, `resultado_prueba`, `revision_humana` | `util.prohibir_cambios()` (decisión 5) |
| `verificacion_salida` | `verificacion`, `AFTER INSERT` | Inserta `verificacion_publicada` en `verificacion.evento_salida` (decisión 10) |

Las funciones de los triggers que leen otro esquema se declaran `SECURITY DEFINER` con `search_path` fijo: así el rol del servicio de verificación puede comprobar que una publicación existe sin tener permiso de leer la tabla `social.publicacion` completa.

---

## Esquema `ia`

### Funciones y procedimientos

| Objeto | Qué hace |
| --- | --- |
| `PROCEDURE ia.encolar_trabajo(tipo, version_prompt, entrada jsonb, INOUT trabajo_id, INOUT desde_cache boolean)` | Calcula `huella_entrada = encode(sha256(convert_to(entrada::text, 'UTF8')), 'hex')` (el texto de un `jsonb` sale siempre igual, con las llaves ordenadas). Si hay un trabajo `terminado` con el mismo tipo, versión y huella, devuelve ese y `desde_cache = true`. Si hay uno `en_cola` o `en_curso` igual, devuelve ese. Si no, crea uno nuevo `en_cola` |
| `FUNCTION ia.tomar_trabajo(tipos text[]) → ia.trabajo` | Toma un trabajo de la cola (ver abajo) |
| `FUNCTION ia.elegir_credencial(proveedor) → text` | El alias habilitado y sin pausa que lleva más tiempo sin usarse (reparte la carga entre cuentas). Nulo si todas están en pausa |
| `PROCEDURE ia.registrar_intento(trabajo_id, alias, modelo, resultado, tokens_entrada, tokens_salida, error, salida jsonb, esperar interval, iniciado_en)` | Guarda el intento y mueve el trabajo (ver abajo) |
| `PROCEDURE ia.configurar_credencial(alias, proveedor, habilitada)` | Agrega o habilita una cuenta |

```sql
CREATE FUNCTION ia.tomar_trabajo(p_tipos text[]) RETURNS SETOF ia.trabajo
LANGUAGE sql VOLATILE AS $$
  UPDATE ia.trabajo t
  SET estado = 'en_curso',
      proximo_intento_en = now() + interval '5 minutes'   -- plazo: si el trabajador muere, otro lo retoma
  WHERE t.id = (
    SELECT id FROM ia.trabajo
    WHERE tipo = ANY (p_tipos)
      AND proximo_intento_en <= now()
      AND estado IN ('en_cola', 'en_curso')   -- 'en_curso' vencido = trabajador caído
    ORDER BY proximo_intento_en
    FOR UPDATE SKIP LOCKED
    LIMIT 1)
  RETURNING t.*;
$$;
```

`FOR UPDATE SKIP LOCKED` hace que dos trabajadores que piden a la vez reciban trabajos distintos: el segundo se salta la fila que el primero tiene bloqueada en lugar de esperarla.

`ia.registrar_intento`, en una transacción, con el trabajo bloqueado (`FOR UPDATE`):

| Resultado | Intento | Trabajo | Credencial |
| --- | --- | --- | --- |
| `ok` | Se guarda con `numero = máximo + 1` | `terminado`, `salida`, `terminado_en` | — |
| `limite_alcanzado` | Se guarda | Vuelve a `en_cola`; `proximo_intento_en = now()` si queda otra credencial libre, o la pausa más corta si todas están en pausa. **No cuenta** como fallo | `pausada_hasta = now() + esperar` |
| `error_proveedor`, `salida_invalida` | Se guarda | `en_cola` con espera creciente (2, 4, 8, 16 s); al quinto fallo, `fallido` | — |

Si un trabajo de extracción queda `fallido`, la publicación sigue visible y su estado de verificación es "requiere revisión", nunca un resultado inventado.

### Triggers

| Trigger | Tabla | Qué hace |
| --- | --- | --- |
| `trabajo_transicion` | `trabajo`, `BEFORE UPDATE` | `util.validar_transicion`: `en_cola → en_curso`, `en_curso → en_curso` (plazo vencido), `en_curso → en_cola / terminado / fallido`. `terminado` y `fallido` son finales. `tipo`, `entrada` y `huella_entrada` no cambian |
| `trabajo_aviso` | `trabajo`, `AFTER INSERT`, `FOR EACH STATEMENT` | `pg_notify('trabajo_ia', tipo)` para despertar al servicio de IA |
| `intento_solo_insercion` | `intento` | `util.prohibir_cambios()` |
| `credencial_actualizado` | `credencial` | `util.marcar_actualizado()` |

---

## Transacciones: dónde importan y qué protegen

| Operación | Qué se hace junto | Qué pasaría sin transacción |
| --- | --- | --- |
| Publicar (`publicar`) | Publicación, etiquetas, menciones, contadores de la original y eventos del outbox | Una publicación sin sus etiquetas, o un evento en el outbox de una publicación que no existe |
| Reaccionar (`reaccionar`) | Reacción, contador y evento | Contador distinto del número real de reacciones |
| Verificar (`registrar_verificacion`) | Versión, evidencia, pruebas, estado de la afirmación; triggers diferidos al confirmar | Una conclusión publicada sin evidencia, o con una cifra que no está en la evidencia |
| Tomar un trabajo (`tomar_trabajo`) | Bloqueo de la fila y cambio a `en_curso` | Dos trabajadores gastando cupo de Groq en el mismo trabajo |
| Registrar un intento (`registrar_intento`) | Intento, estado del trabajo, pausa de la credencial | Un trabajo `terminado` sin su intento, o una cuenta agotada que se sigue usando |
| Cerrar una alerta (`cerrar_alerta`) | Estado y evento | Una alerta cerrada sin quién ni por qué |
| Sincronizar el grafo | Ver abajo | — |

**Sincronizar el grafo no es una transacción distribuida.** Neo4j y PostgreSQL no comparten transacción. El servicio de grafo lee un lote de eventos pendientes, los aplica en Neo4j en una transacción de Neo4j y luego inserta sus filas en `entrega_evento` en PostgreSQL. Si se cae entre los dos pasos, al volver aplica de nuevo los mismos eventos; como todo es `MERGE` (o `DELETE` de algo que ya no está), aplicarlos dos veces deja el mismo grafo. Esto se llama entrega "al menos una vez" con operaciones idempotentes, y es la razón de usar outbox.

## Roles y permisos (decisión 13)

| Rol | Escribe en | Lee además |
| --- | --- | --- |
| `svc_oficial` | `oficial` | — |
| `svc_social` | `social` | `verificacion.estado_publicacion` (solo la función) |
| `svc_verificacion` | `verificacion`; `entrega_evento` de `social` y `temas` (consumidor `verificacion`) | `oficial.observaciones_vigentes`, `oficial.observacion_en` (solo las funciones) |
| `svc_ia` | `ia` | — |
| `svc_grafo` | `entrega_evento` de `social` y `verificacion` (consumidor `grafo`), `social.registrar_tendencias` | Los `evento_salida` de `social` y `verificacion` |
| `svc_temas` | `temas` | `social.figura_publica` (solo con `temas.buscar_figura`) |

Los servicios ejecutan los procedimientos con `EXECUTE`; no tienen `UPDATE` ni `DELETE` directo sobre las tablas de historial.

## Cómo se prueba

Una prueba con `pytest` contra la base de Docker por cada regla, del estilo "intenta romperla y espera el error": modificar una observación, insertar evidencia en cuarentena, verificar con una cifra que no está en la evidencia, dos trabajadores tomando la cola a la vez (dos conexiones), responder a una publicación retirada, comprobar que los contadores coinciden con `count(*)` después de muchas operaciones, y que reaplicar el outbox deja el mismo grafo.

## Requisitos de la materia

| Requisito | Dónde se cumple |
| --- | --- |
| Procedimientos | `registrar_articulos`, `registrar_temas`, `registrar_declaraciones`, `publicar`, `registrar_declaracion`, `retirar_publicacion`, `seguir`, `reaccionar`, `registrar_tendencias`, `registrar_afirmaciones`, `registrar_verificacion`, `registrar_revision`, `encolar_trabajo`, `registrar_intento`, `cerrar_alerta`, `reabrir_alerta` |
| Funciones | `articulos_ventana`, `buscar_figura`, `pagina_tema`, `cobertura_tema`, `actividad_tema`, `requiere_extraccion`, `observaciones_vigentes`, `observacion_en`, `extraer_etiquetas`, `extraer_menciones`, `hilo` (recursiva), `estadisticas_usuario`, `contenido_tendencia`, `resumen_conclusiones`, `tendencias_basicas`, `estado_publicacion`, `cifras_en_texto`, `cifras_permitidas`, `texto_plano` (0016), `nombre_usuario_disponible`, `buscar_usuarios`, `resolver_nombre`, `tomar_trabajo`, `elegir_credencial` |
| Triggers | Cita textual y título sin cifras (temas), contadores, outbox, solo inserción, transiciones de estado, integridad entre esquemas, triggers diferidos de evidencia y cifras, `pg_notify` |
| Transacciones | Todas las operaciones de la tabla anterior; bloqueo con `FOR UPDATE` y `SKIP LOCKED`; restricciones diferidas al confirmar |
| Microservicios | Un esquema y un rol por servicio, sin llaves foráneas entre esquemas, comunicación por outbox y cola |
| Base de grafos | Neo4j alimentado por outbox ([04_modelo_grafo.md](04_modelo_grafo.md)) |
| Docker | PostgreSQL, Neo4j, los servicios y la app web en `docker-compose.yml` |
