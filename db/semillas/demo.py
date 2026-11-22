"""Datos de demostración: una red que ya parece usada, sin gastar IA.

    uv run python db/semillas/demo.py               # siembra (una sola vez)
    uv run python db/semillas/demo.py --seguidor dubal_aguilar   # además conecta esa cuenta con la demo
    uv run python db/semillas/demo.py --resembrar --seguidor dubal_aguilar   # el día de la presentación
    uv run python db/semillas/demo.py --cifras      # agrega las publicaciones con cifras (las únicas que usan IA)
    uv run python db/semillas/demo.py --fotos       # avatares ilustrados para las cuentas de la demo
    uv run python db/semillas/demo.py --limpiar     # borra la demo (solo desarrollo) y rehace el grafo
    uv run python db/semillas/demo.py --retirar     # retira publicaciones y desactiva cuentas, sin borrar

Las fechas son relativas al momento de sembrar: para que la red se vea viva el día de la presentación, se
resiembra ese día (--resembrar limpia y siembra en una sola transacción, y luego reconstruye Neo4j).

Qué crea: personas ficticias (correo @demo.parrhesia.local), comunidades públicas y privadas con sus papeles,
publicaciones repartidas en los últimos 45 días (respuestas, compartidas, etiquetas, menciones y formato),
seguimientos, reacciones, solicitudes pendientes y publicaciones fijadas.

Qué NO crea, a propósito:
  - figuras públicas ni declaraciones: son personas reales y exigen fuente oficial (T13, las aporta el equipo);
  - temas del día: salen de artículos reales de medios; inventarlos sería suplantar a un medio;
  - nada que pase el filtro previo de verificación (cifra + palabra de los 8 indicadores): cada texto se
    revisa con verificacion.requiere_extraccion() y el script se detiene si alguno lo pasa. Así no gasta IA.

Las filas se insertan con su fecha original (los procedimientos usan now()); los triggers de siempre corren
igual: etiquetas y menciones salen de las mismas funciones de la base, la comunidad se fija con
parrhesia.comunidad como en la API, y el outbox lleva la fecha original a Neo4j. Las cuentas comparten una
clave de demostración, que se imprime una sola vez (solo su hash queda en la base).
"""

from __future__ import annotations

import argparse
import random
import re
import secrets
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

from argon2 import PasswordHasher  # noqa: E402

from app.db import connect  # noqa: E402

DOMINIO = "demo.parrhesia.local"
AZAR = random.Random(20261121)
AHORA = datetime.now(UTC)
DIAS = 45

# ---------------------------------------------------------------------------------------------------------
# Personas (ficticias)

PERSONAS = [
    ("valentina_rios", "Valentina Ríos", "Ingeniera civil en Bogotá. Me interesa cómo nos movemos por la ciudad."),
    ("andres_mejia", "Andrés Mejía", "Profe de colegio en Medellín. Bici, café y libros."),
    ("camila_ortega", "Camila Ortega", "Periodista de datos. Leo bases abiertas por gusto."),
    ("juan_pablo_diaz", "Juan Pablo Díaz", "Agrónomo del Huila. Escribo sobre el campo que casi nadie ve."),
    ("laura_castano", "Laura Castaño", "Estudiante de economía en Cali. Pregunto mucho."),
    ("santiago_pardo", "Santiago Pardo", "Comerciante en Bucaramanga. Opino de lo que vivo."),
    ("mariana_quintero", "Mariana Quintero", "Bióloga. Agua, páramos y ríos."),
    ("felipe_arango", "Felipe Arango", "Abogado. Me gustan los debates con argumentos."),
    ("daniela_suarez", "Daniela Suárez", "Diseñadora en Barranquilla. Carnaval todo el año."),
    ("carlos_herrera", "Carlos Herrera", "Taxista en Bogotá hace muchos años. La calle enseña."),
    ("natalia_vargas", "Natalia Vargas", "Médica general en Pasto."),
    ("sebastian_rojas", "Sebastián Rojas", "Desarrollador de software. Datos abiertos y transparencia."),
    ("paula_jimenez", "Paula Jiménez", "Mamá, contadora y vecina de Chapinero."),
    ("miguel_angel_cruz", "Miguel Ángel Cruz", "Caficultor en Caldas, tercera generación."),
    ("isabella_moreno", "Isabella Moreno", "Estudiante de ingeniería en Barranquilla."),
    ("diego_ramirez", "Diego Ramírez", "Ciclista urbano. Si se puede en bici, voy en bici."),
    ("ana_maria_lopez", "Ana María López", "Docente universitaria. Historia de Colombia."),
    ("ricardo_salazar", "Ricardo Salazar", "Ingeniero de petróleos. Energía sin dogmas."),
    ("juliana_gomez", "Juliana Gómez", "Bailarina de salsa en Cali."),
    ("tomas_restrepo", "Tomás Restrepo", "Emprendedor. Pequeñas empresas, grandes trámites."),
    ("sara_mendoza", "Sara Mendoza", "Trabajadora social en Cartagena."),
    ("alejandro_pineda", "Alejandro Pineda", "Economista. Prefiero las preguntas a las consignas."),
    ("manuela_cardenas", "Manuela Cárdenas", "Estudiante de periodismo. Aprendiendo a verificar."),
    ("oscar_beltran", "Óscar Beltrán", "Líder comunal en Soacha."),
    ("gabriela_nino", "Gabriela Niño", "Arquitecta. Ciudades para caminar."),
    ("hernan_villa", "Hernán Villa", "Pensionado. Tengo tiempo para leer y opinar."),
    ("lucia_ospina", "Lucía Ospina", "Ingeniera ambiental en Manizales."),
    ("kevin_mosquera", "Kevin Mosquera", "Músico del Pacífico. Quibdó en el corazón."),
    ("maria_jose_pena", "María José Peña", "Politóloga. Me interesan las instituciones."),
    ("jorge_ivan_rueda", "Jorge Iván Rueda", "Ganadero en Córdoba."),
    ("catalina_franco", "Catalina Franco", "Librera en Medellín. Recomiendo libros sin que me pregunten."),
    ("nicolas_acosta", "Nicolás Acosta", "Estudiante de ingeniería de sistemas en Barranquilla."),
    ("veronica_duarte", "Verónica Duarte", "Enfermera jefe. Turnos largos, opiniones cortas."),
    ("esteban_marin", "Esteban Marín", "Fotógrafo. Viajo por las carreteras del país."),
    ("adriana_rincon", "Adriana Rincón", "Contadora pública en Bucaramanga."),
    ("luis_fernando_gil", "Luis Fernando Gil", "Conductor de bus intermunicipal."),
    ("carolina_munoz", "Carolina Muñoz", "Investigadora en salud pública."),
    ("mauricio_leon", "Mauricio León", "Profesor de matemáticas. Me gustan las gráficas bien hechas."),
    ("silvia_patino", "Silvia Patiño", "Vecina de Chapinero. Huertas urbanas."),
    ("raul_cespedes", "Raúl Céspedes", "Pescador artesanal en Santa Marta."),
]

# ---------------------------------------------------------------------------------------------------------
# Comunidades: dueño, papeles, integrantes y lo que se publica en cada una. Una publicación es un texto (lo
# escribe cualquier integrante) o (autor, texto) cuando habla desde un oficio que solo tiene esa persona.

COMUNIDADES = [
    {
        "nombre": "Movilidad Bogotá",
        "descripcion": "Cómo nos movemos en Bogotá: buses, metro, bici, a pie y en carro. Experiencias, propuestas y datos.",
        "reglas": "Hablamos de ideas, no de personas. Nada de insultos. Si citas un dato, pon la fuente.",
        "privacidad": "publica",
        "admin": "valentina_rios", "gestor": "gabriela_nino", "moderadores": ["diego_ramirez"],
        "integrantes": ["carlos_herrera", "paula_jimenez", "oscar_beltran", "silvia_patino", "sebastian_rojas",
                        "luis_fernando_gil", "felipe_arango", "hernan_villa", "manuela_cardenas", "laura_castano"],
        "publicaciones": [
            "Hoy el trancón en la Séptima estuvo **imposible**. ¿Alguien sabe si cambiaron los semáforos de la calle de los museos? #MovilidadBogota",
            "Propuesta sencilla: que los paraderos tengan el mapa de la ruta y el horario estimado. No es caro y ayuda muchísimo. #MovilidadBogota",
            "Llevo semanas yendo al trabajo en bici por la ciclorruta de la Boyacá y la diferencia en tiempo es enorme. Lo que falta es iluminación en varios tramos.",
            "Pregunta honesta para los que manejan: ¿el pico y placa les sirve o solo los hace salir más temprano?",
            ("carlos_herrera", "Como taxista les digo: el problema no es solo la cantidad de carros, también cómo están sincronizados los semáforos. #MovilidadBogota"),
            "Caminar por el centro un domingo en la mañana es otra ciudad. Ojalá más calles peatonales con comercio.",
            "Ya vi los avances de la obra del metro por la Caracas. Hay que reconocer lo que avanza y también exigir información clara sobre los desvíos. #MetroBogota",
            "*Dato curioso:* los buses zonales de mi barrio ahora pasan con más frecuencia en la mañana, pero en la noche siguen escasos.",
            "Desde Soacha el viaje sigue siendo larguísimo. Ojalá la conexión regional no se quede en planos. #MovilidadBogota",
            "Las motos y las bicis compartiendo carril es un peligro para todos. Se necesita separación física, no solo pintura.",
            "Me parece injusto culpar solo a los conductores de bus. Trabajan jornadas larguísimas con mucha presión.",
        ],
    },
    {
        "nombre": "Barranquilla y el Caribe",
        "descripcion": "Noticias, cultura, comida y debates de Barranquilla y la región Caribe.",
        "reglas": "Respeto ante todo. Se vale no estar de acuerdo.",
        "privacidad": "publica",
        "admin": "daniela_suarez", "gestor": "isabella_moreno", "moderadores": ["sara_mendoza"],
        "integrantes": ["nicolas_acosta", "raul_cespedes", "jorge_ivan_rueda", "kevin_mosquera", "ana_maria_lopez",
                        "juliana_gomez", "manuela_cardenas"],
        "publicaciones": [
            "Ya empezaron los ensayos de las comparsas y el barrio suena distinto. ¡Qué orgullo! #Carnaval",
            "El malecón del río quedó muy bonito, pero falta sombra. Con este sol, *un árbol vale oro*. #Barranquilla",
            "¿Cuál es la mejor arepa de huevo de la ciudad? Abro debate sano. #Barranquilla",
            "Los arroyos cuando llueve siguen siendo un riesgo. Se ha avanzado en canalización, pero faltan sectores.",
            "Pesca artesanal en Santa Marta: cada vez hay que ir más lejos para encontrar peces. Algo está cambiando en el mar. #Caribe",
            "Recomendación de fin de semana: el museo del Caribe tiene una exposición nueva sobre música tradicional.",
            "En Cartagena el turismo trae trabajo, pero también encarece la vida de los que vivimos acá. Hay que hablar de las dos cosas. #Caribe",
            "La final del torneo local se vivió en la calle. El fútbol todavía nos une. #Barranquilla",
            "Me gustaría ver más bibliotecas abiertas hasta tarde en los barrios. Hay muchos pelados con ganas de estudiar.",
        ],
    },
    {
        "nombre": "Datos abiertos Colombia",
        "descripcion": "Para quienes leen, limpian y publican datos públicos colombianos. Fuentes, herramientas y buenas prácticas.",
        "reglas": "Comparte siempre el enlace a la fuente original. Las preguntas básicas también son bienvenidas.",
        "privacidad": "publica",
        "admin": "camila_ortega", "gestor": "sebastian_rojas", "moderadores": ["mauricio_leon", "manuela_cardenas"],
        "integrantes": ["alejandro_pineda", "carolina_munoz", "maria_jose_pena", "laura_castano", "felipe_arango",
                        "nicolas_acosta", "ana_maria_lopez", "valentina_rios"],
        "publicaciones": [
            "Recordatorio: antes de compartir una gráfica, revisen **desde qué valor empieza el eje**. Un eje recortado cambia toda la historia. #DatosAbiertos",
            "El portal [datos.gov.co](https://www.datos.gov.co) tiene una API con filtros por fecha. Si alguien quiere, armo una guía corta para principiantes. #DatosAbiertos",
            "Una lección que aprendí a las malas: un dato *provisional* puede cambiar. Siempre anoten la fecha de corte.",
            "¿Alguien ha trabajado con los anexos del [DANE](https://www.dane.gov.co)? Cambian de formato de vez en cuando y rompen los scripts. #DatosAbiertos",
            "No es lo mismo un promedio que una mediana. Cuando la distribución está sesgada, la mediana cuenta mejor la historia.",
            "Propuesta para la comunidad: un glosario colaborativo de términos estadísticos explicados en lenguaje sencillo. ¿Quién se anima?",
            "Comparar dos fuentes que miden distinto no es contradicción: es información. Lo importante es decir qué mide cada una. #Verificacion",
            "Me encanta cuando una entidad publica la metodología junto con los datos. Debería ser la norma. #DatosAbiertos",
            "Pequeño truco: guarden el archivo original y su huella digital. Si la fuente lo reemplaza, pueden demostrar qué decía antes.",
            "Un número sin periodo, sin territorio y sin fuente no es un dato, es una frase. #Verificacion",
        ],
    },
    {
        "nombre": "Ciclistas de Medellín",
        "descripcion": "Rutas, seguridad vial, talleres recomendados y salidas grupales en el Valle de Aburrá.",
        "reglas": "Casco siempre. Respeto a peatones y conductores.",
        "privacidad": "publica",
        "admin": "andres_mejia", "gestor": None, "moderadores": ["diego_ramirez"],
        "integrantes": ["catalina_franco", "esteban_marin", "gabriela_nino", "lucia_ospina", "tomas_restrepo"],
        "publicaciones": [
            "Salida del domingo: subimos a Las Palmas temprano. Punto de encuentro en el parque de El Poblado. ¿Quién se apunta? #BiciMedellin",
            "Las ciclorrutas nuevas del centro están bien, pero algunas terminan de la nada. Necesitamos red, no tramos sueltos. #BiciMedellin",
            "Recomiendo un taller en Belén que arregla rapidísimo y explica qué le hicieron a la bici. Eso vale mucho.",
            "La calidad del aire en temporada seca se siente cuando uno pedalea. Ojalá más incentivos para el transporte limpio. #CalidadDelAire",
            "Respeto para los peatones también: la acera no es ciclorruta. Prediquemos con el ejemplo.",
            "¿Qué opinan de las bicicletas eléctricas en las ciclorrutas? Algunas van muy rápido. #BiciMedellin",
            "Hoy un conductor me dio el espacio de un metro y medio al adelantarme. Pequeños gestos que salvan vidas.",
        ],
    },
    {
        "nombre": "Campo y agro colombiano",
        "descripcion": "Producción agropecuaria, vías terciarias, precios al productor y vida rural.",
        "reglas": "Aquí hablamos quienes trabajamos la tierra y quienes quieren entenderla. Sin estigmas.",
        "privacidad": "publica",
        "admin": "juan_pablo_diaz", "gestor": "miguel_angel_cruz", "moderadores": [],
        "integrantes": ["jorge_ivan_rueda", "raul_cespedes", "lucia_ospina", "mariana_quintero", "hernan_villa",
                        "luis_fernando_gil", "alejandro_pineda"],
        "publicaciones": [
            "Las vías terciarias siguen siendo el gran pendiente. Sacar la cosecha cuesta más que producirla en muchas veredas. #Campo",
            ("miguel_angel_cruz", "Este año la cosecha de café viene buena en mi finca, pero la mano de obra para recoger es cada vez más difícil de conseguir. #Cafe"),
            "La ganadería también puede ser sostenible: cercas vivas, rotación de potreros y árboles en los potreros. Se puede. #Campo",
            "Muchos jóvenes se van del campo porque no hay internet ni oportunidades. Conectividad rural ya. #Campo",
            "Los intermediarios se quedan con buena parte del valor. Las cooperativas bien manejadas son una salida.",
            "Ojalá más ciudadanos visitaran una finca y vieran todo el trabajo que hay detrás de un plátano en el supermercado.",
            "El cambio en las lluvias nos tiene adivinando cuándo sembrar. Necesitamos mejor información climática local. #Campo",
            "Hoy vendimos en el mercado campesino del pueblo. Venta directa, sin intermediarios y la gente feliz. #MercadoCampesino",
        ],
    },
    {
        "nombre": "Lectores de economía",
        "descripcion": "Leemos y discutimos economía colombiana con calma: libros, informes y preguntas.",
        "reglas": "Argumentos con fuentes. Ninguna escuela tiene el monopolio de la razón.",
        "privacidad": "publica",
        "admin": "alejandro_pineda", "gestor": None, "moderadores": ["laura_castano"],
        "integrantes": ["felipe_arango", "tomas_restrepo", "adriana_rincon", "santiago_pardo", "ricardo_salazar",
                        "maria_jose_pena", "hernan_villa", "camila_ortega"],
        "publicaciones": [
            "Club de lectura de este mes: un libro sobre historia económica de Colombia en el siglo veinte. ¿Lo votamos? #ClubDeLectura",
            "Pregunta para el grupo: ¿qué tan bien entendemos la diferencia entre valores *nominales* y *reales*? Creo que es la confusión más común en los debates.",
            "La reforma pensional divide opiniones en mi familia. Mi papá la defiende y mi tía la critica. Ambos tienen argumentos que vale la pena escuchar. #ReformaPensional",
            "Me preocupa la informalidad: mucha gente trabaja sin seguridad social. Sea cual sea la reforma, ese tema debería estar en el centro.",
            "Los impuestos a las bebidas azucaradas: ¿salud pública o carga para los hogares? Leí estudios en las dos direcciones. #Impuestos",
            "Un buen ejercicio: leer el mismo informe económico desde dos posiciones distintas y ver qué conclusiones saca cada una.",
            "Para las pequeñas empresas el problema no siempre es la tasa de impuestos, sino la cantidad de trámites. #Emprendimiento",
            "La transición energética tiene costos y beneficios. Me gustaría ver más debate técnico y menos consignas. #Energia",
        ],
    },
    {
        "nombre": "Vecinos de Chapinero",
        "descripcion": "Grupo de vecinos: seguridad del barrio, eventos, huertas, perdidos y encontrados.",
        "reglas": "Solo vecinos. Lo que se comparte aquí se queda aquí.",
        "privacidad": "privada",
        "admin": "paula_jimenez", "gestor": "silvia_patino", "moderadores": [],
        "integrantes": ["gabriela_nino", "valentina_rios", "felipe_arango", "veronica_duarte"],
        "publicaciones": [
            "Vecinos, este sábado hay jornada de siembra en la huerta del parque. Traigan guantes. #Chapinero",
            "Encontré un perro criollo, café con manchas blancas, cerca del parque. Está en mi casa mientras aparece el dueño.",
            "¿Alguien sabe si ya arreglaron la luminaria de la esquina de la panadería? Sigue oscuro en la noche.",
            "Gracias a todos los que vinieron a la reunión del sábado. Quedó un acta con los compromisos.",
            "Recomiendo la tienda nueva de la esquina: frutas del mercado campesino y precios justos.",
        ],
    },
    {
        "nombre": "Ingeniería en el Caribe",
        "descripcion": "Estudiantes de ingeniería de la región: proyectos, parciales, prácticas y oportunidades.",
        "reglas": "Comparte apuntes y oportunidades. Nada de copias en exámenes.",
        "privacidad": "privada",
        "admin": "isabella_moreno", "gestor": "nicolas_acosta", "moderadores": [],
        "integrantes": ["daniela_suarez", "sebastian_rojas", "mauricio_leon"],
        "publicaciones": [
            "¿Alguien tiene buenos apuntes de bases de datos? El tema de normalización me está costando. #BasesDeDatos",
            "Abrieron convocatoria de prácticas en una empresa de energía de la región. Dejo el enlace en los comentarios.",
            "Truco para modelar: primero el modelo entidad-relación en papel, después el código. Ahorra muchas horas. #BasesDeDatos",
            "Grupo de estudio el jueves en la biblioteca para el parcial de cálculo. ¡Todos bienvenidos!",
        ],
    },
    {
        "nombre": "Cali, cultura y salsa",
        "descripcion": "Agenda cultural, escuelas de baile, música y gastronomía caleña.",
        "reglas": "Comparte eventos con fecha y lugar. Promoción comercial solo si es cultural.",
        "privacidad": "publica",
        "admin": "juliana_gomez", "gestor": None, "moderadores": ["laura_castano"],
        "integrantes": ["kevin_mosquera", "natalia_vargas", "carolina_munoz", "esteban_marin"],
        "publicaciones": [
            "Este viernes hay noche de salsa en vivo en el bulevar del río. ¡Los espero! #SalsaCali",
            "Las escuelas de baile de barrio son patrimonio. Muchos niños encuentran ahí disciplina y alegría. #SalsaCali",
            "El Petronio se viene y ya se siente la marimba en las calles. Pacífico, siempre. #Petronio",
            "¿Dónde comen el mejor sancocho de gallina en Cali? Necesito recomendaciones para la visita de mi familia.",
            "Me encantaría que los festivales tuvieran más rutas de transporte nocturno para volver seguros a casa.",
        ],
    },
    {
        "nombre": "Agua y páramos",
        "descripcion": "Conservación de páramos, ríos y humedales. Ciencia ciudadana y buenas prácticas.",
        "reglas": "Basado en evidencia. Se valen todas las posturas, también las de quienes viven del territorio.",
        "privacidad": "publica",
        "admin": "mariana_quintero", "gestor": "lucia_ospina", "moderadores": [],
        "integrantes": ["juan_pablo_diaz", "ricardo_salazar", "silvia_patino", "raul_cespedes", "gabriela_nino",
                        "carolina_munoz"],
        "publicaciones": [
            "Visitamos el páramo de Sumapaz con un grupo de estudiantes. Ver los frailejones de cerca cambia la forma de pensar el agua. #Paramos",
            "La conservación funciona mejor cuando las comunidades que viven en el territorio participan en las decisiones. #Paramos",
            "Los humedales de Bogotá son refugio de aves migratorias. ¿Alguien conoce jornadas de avistamiento abiertas? #Humedales",
            "Debate necesario: ¿cómo conciliar la minería con la protección del agua? Quiero escuchar a quienes trabajan en el sector. #Agua",
            "Ahorrar agua en casa sí importa, pero también hay que mirar los grandes consumos. Las dos cosas. #Agua",
            "Ciencia ciudadana: estamos registrando la calidad del agua de una quebrada con kits sencillos. Les cuento los resultados pronto.",
        ],
    },
    {
        "nombre": "Emprendedores de Santander",
        "descripcion": "Red de pequeños empresarios de Santander: trámites, ventas, alianzas y aprendizajes.",
        "reglas": "Nada de cadenas ni esquemas piramidales. Ayudémonos.",
        "privacidad": "privada",
        "admin": "tomas_restrepo", "gestor": "adriana_rincon", "moderadores": [],
        "integrantes": ["santiago_pardo", "luis_fernando_gil"],
        "publicaciones": [
            "¿Alguien ha usado la facturación electrónica gratuita? Quiero saber si vale la pena para un negocio pequeño. #Emprendimiento",
            "Aprendizaje del mes: no le fíen a todo el mundo, por muy amable que sea. Contratos claros, amistades largas.",
            "Feria de emprendimiento el próximo mes en el parque principal. Hay puestos disponibles para los del grupo.",
        ],
    },
]

# ---------------------------------------------------------------------------------------------------------
# Publicaciones fuera de comunidades (opiniones de todo tipo: misma vara para todos)

GENERALES = [
    ("felipe_arango", "Una sociedad madura discute ideas sin convertir al otro en enemigo. Lo digo para todos los lados."),
    ("maria_jose_pena", "La separación de poderes no es un tecnicismo: es lo que protege a la minoría de turno, sea cual sea. #Instituciones"),
    ("hernan_villa", "Llevo toda la vida votando y nunca había visto debates tan acalorados en mi familia. Sigo creyendo en la conversación."),
    ("ana_maria_lopez", "Leer historia ayuda a ver que muchos debates de hoy ya los tuvimos antes. Cambian los nombres, no tanto las preguntas. #Historia"),
    ("manuela_cardenas", "Primer aprendizaje en la clase de verificación: *quién lo dice* no es lo mismo que *qué dicen los datos*. #Verificacion"),
    ("camila_ortega", "Antes de compartir algo que les indigna, pregúntense: ¿de dónde sale? ¿qué periodo? ¿qué fuente? #Verificacion"),
    ("ricardo_salazar", "La transición energética necesita gas por un tiempo. Decirlo no es estar en contra del ambiente; es hablar de la transición real. #Energia"),
    ("mariana_quintero", "Respeto a quienes defienden la exploración, pero creo que los ecosistemas estratégicos deben quedar por fuera. #Energia"),
    ("santiago_pardo", "En mi negocio lo que más pesa es la inseguridad en la noche. Cerramos más temprano y eso se nota en las ventas."),
    ("oscar_beltran", "En Soacha la junta de acción comunal logró arreglar el parque con trabajo de los vecinos. Lo comunitario funciona."),
    ("natalia_vargas", "Turno largo en el hospital. Gracias a los colegas que siguen dando todo aunque el sistema esté cansado. #Salud"),
    ("veronica_duarte", "La reforma a la salud tiene que escuchar a quienes estamos en los hospitales todos los días, defiendan lo que defiendan. #Salud"),
    ("carolina_munoz", "Prevenir sale más barato que curar. La atención primaria debería ser prioridad sin importar el modelo. #Salud"),
    ("kevin_mosquera", "El Pacífico no es solo noticias difíciles: también es música, cocina y gente que trabaja duro. #Choco"),
    ("sara_mendoza", "Trabajo con familias desplazadas y lo que más piden es estabilidad: una casa, un colegio, un trabajo. #Paz"),
    ("jorge_ivan_rueda", "En Córdoba la gente del campo quiere tranquilidad para trabajar. Eso no tiene color político. #Campo"),
    ("luis_fernando_gil", "Las carreteras entre ciudades están mejorando en algunos tramos, pero los derrumbes en temporada de lluvias siguen siendo un drama. #Vias"),
    ("esteban_marin", "Fotografié amaneceres en la Guajira esta semana. Colombia es absurdamente hermosa. #Viajes"),
    ("catalina_franco", "Libro recomendado de la semana: una novela colombiana sobre una familia de pescadores. Me hizo llorar en el bus. #Libros"),
    ("mauricio_leon", "Una gráfica de barras que no empieza en cero exagera las diferencias. Una de líneas, no necesariamente. Depende de lo que quieras mostrar. #DatosAbiertos"),
    ("alejandro_pineda", "No hay reforma perfecta. La pregunta útil es: ¿quién gana, quién pierde y cómo se compensa? #ReformaPensional"),
    ("laura_castano", "En clase discutimos la reforma pensional y lo más interesante fue ver que todos usábamos los mismos datos para llegar a conclusiones distintas. #ReformaPensional"),
    ("tomas_restrepo", "Abrir una empresa en Colombia es más fácil que hace años, pero sostenerla sigue siendo un reto. #Emprendimiento"),
    ("adriana_rincon", "Época de declaraciones de renta: revisen bien sus soportes y no dejen todo para el último día. #Impuestos"),
    ("gabriela_nino", "Una ciudad para caminar es una ciudad más segura: más gente en la calle, más ojos, más vida. #Ciudades"),
    ("valentina_rios", "Las obras públicas necesitan algo más que ingenieros: necesitan comunicación clara con los vecinos. #MetroBogota"),
    ("diego_ramirez", "Bogotá tiene una de las redes de ciclorrutas más grandes de la región. Cuidémosla y exijamos mantenimiento. #MovilidadBogota"),
    ("carlos_herrera", "A los que critican a los taxistas: hay de todo, como en todo oficio. Yo llevo años trabajando honrado. #MovilidadBogota"),
    ("daniela_suarez", "El diseño también es servicio público: señales claras, letras legibles, mapas que se entiendan. #Ciudades"),
    ("isabella_moreno", "Semana de parciales. Café, apuntes y fe. #BasesDeDatos"),
    ("nicolas_acosta", "Terminé mi primer proyecto con una base de datos de verdad: llaves foráneas, triggers y todo. ¡Qué satisfacción! #BasesDeDatos"),
    ("sebastian_rojas", "Software abierto para el Estado: si lo pagamos entre todos, el código debería ser de todos. #DatosAbiertos"),
    ("paula_jimenez", "Los colegios públicos de mi barrio necesitan más orientadores. Los chicos cargan con mucho. #Educacion"),
    ("ana_maria_lopez", "La educación pública de calidad es el mejor proyecto de país, lo diga quien lo diga. #Educacion"),
    ("miguel_angel_cruz", "Tomarse un café colombiano es apoyar a miles de familias. Prefieran el de origen. #Cafe"),
    ("raul_cespedes", "Hoy salimos a pescar antes del amanecer. El mar estaba tranquilo y volvimos con buena pesca. #Caribe"),
    ("lucia_ospina", "Manizales tiene uno de los mejores sistemas de alertas por lluvias del país. Hay que contarlo más. #Ciudades"),
    ("juliana_gomez", "Bailar es mi forma de pensar. Hoy di clase a un grupo de abuelos y fue lo mejor de la semana. #SalsaCali"),
    ("felipe_arango", "La presunción de inocencia aplica para todos, también para los que no nos caen bien. #Instituciones"),
    ("maria_jose_pena", "Votar es importante, pero la ciudadanía no se acaba el día de elecciones. Juntas, veedurías, cabildos. #Instituciones"),
    ("hernan_villa", "Con la pensión que tengo me alcanza para lo básico. Me preocupa más la de mis nietos. #ReformaPensional"),
    ("santiago_pardo", "Los arriendos de los locales comerciales en Bucaramanga están por las nubes. ¿Les pasa en otras ciudades?"),
    ("oscar_beltran", "Más canchas y menos rejas. Los jóvenes necesitan espacios. #Juventud"),
    ("camila_ortega", "Si alguien comparte una cifra en esta red, el sistema la conecta con el dato oficial completo. Eso me gusta: no te dice qué pensar, te muestra el contexto."),
    ("manuela_cardenas", "Entrevisté a una fuente que me dio una cifra sin fecha. Le pedí la fuente y la fecha, y resultó ser de hace años. Moraleja: siempre pedir el periodo. #Verificacion"),
    ("kevin_mosquera", "Concierto de chirimía en Quibdó este fin de semana. Si están por allá, no se lo pierdan. #Choco"),
    ("natalia_vargas", "Pasto en diciembre es otra cosa. Ya se siente el Carnaval de Negros y Blancos. #Carnaval"),
    ("esteban_marin", "Recorrí la vía al Llano y el paisaje compensa cualquier trancón. #Viajes"),
    ("ricardo_salazar", "Me gustaría un debate sobre energía donde nadie use la palabra *traidor*. Se puede pensar distinto y querer el mismo país. #Energia"),
    ("carolina_munoz", "Los datos de salud pública son más útiles cuando se publican por municipio. Lo nacional esconde mucha desigualdad. #Salud"),
    ("adriana_rincon", "Las pymes somos las que más empleamos y las que menos voz tenemos en los debates económicos. #Emprendimiento"),
    ("gabriela_nino", "Los andenes rotos son una barrera enorme para las personas con discapacidad y para los mayores. #Ciudades"),
    ("jorge_ivan_rueda", "Para los de la ciudad: la leche no sale de la tienda. Detrás hay madrugadas y mucho trabajo. #Campo"),
    ("laura_castano", "Pregunta de economía para el que sepa: ¿por qué los precios de los alimentos suben más rápido en unas ciudades que en otras?"),
    ("alejandro_pineda", "Hilo pendiente: cómo leer un boletín estadístico sin perderse. Spoiler: empiecen por las notas metodológicas. #DatosAbiertos"),
    ("silvia_patino", "Las huertas urbanas no van a alimentar a la ciudad, pero sí enseñan de dónde viene la comida. #Chapinero"),
    ("veronica_duarte", "A los pacientes: pregunten todo lo que no entiendan. Es su derecho. #Salud"),
    ("luis_fernando_gil", "Conducir de noche entre Bucaramanga y Cúcuta exige cuidado. Gracias a los que respetan las distancias. #Vias"),
    ("catalina_franco", "La librería está llena de estudiantes buscando libros de historia. Eso me da esperanza. #Libros"),
    ("diego_ramirez", "Hoy hice el recorrido completo de la ciclovía dominical. Familias, perros y bicis de todas las épocas. #MovilidadBogota"),
]

# Respuestas: una por cada tipo de conversación, elegidas según la etiqueta o, si no hay, genéricas.
RESPUESTAS = {
    "movilidadbogota": [
        "Totalmente de acuerdo. Y que la información de los desvíos llegue antes, no el mismo día.",
        "Yo vivo en Kennedy y lo vivo a diario. Lo de los semáforos es clave.",
        "Ojalá alguien de la secretaría lea esto. Son propuestas sencillas.",
        "En bici también se sufre, pero se llega. Lo que falta es seguridad en las ciclorrutas de noche.",
    ],
    "metrobogota": [
        "Lo importante es que no se frene, sea quien sea el que gobierne.",
        "Coincido en lo de la información. Los vecinos de la Caracas merecen claridad.",
    ],
    "datosabiertos": [
        "¡Sí a la guía! Yo me apunto para ayudar a revisarla.",
        "Muy buen punto. Agrego: siempre revisen si el dato es provisional.",
        "Esto debería enseñarse en el colegio.",
        "Me pasó exactamente eso con un anexo que cambió de formato. Ahora guardo todo.",
    ],
    "verificacion": [
        "Esto es lo más útil que he leído hoy.",
        "Exacto: el contexto completo cambia la conclusión.",
        "Me lo llevo para mi clase.",
    ],
    "reformapensional": [
        "En mi casa pasa lo mismo. Al final coincidimos en más cosas de las que creíamos.",
        "Buen enfoque. Me gustaría ver más debates así, con argumentos de los dos lados.",
        "La informalidad es el elefante en la sala, cierto.",
        "Yo tengo dudas sobre la transición entre regímenes. ¿Alguien la ha estudiado a fondo?",
    ],
    "energia": [
        "Gracias por plantearlo sin agresividad. Así sí se puede conversar.",
        "Yo creo que la clave está en los tiempos de la transición, no en el destino.",
        "Respeto la postura, aunque pienso distinto. Me interesa leer más.",
    ],
    "salud": [
        "Gracias por su trabajo. Lo vemos y lo valoramos.",
        "La atención primaria es la gran olvidada, totalmente de acuerdo.",
        "Desde el centro de salud de mi barrio pensamos igual.",
    ],
    "campo": [
        "Vivo en la ciudad y no tenía idea. Gracias por contarlo.",
        "Las vías terciarias deberían ser prioridad nacional.",
        "Las cooperativas funcionan cuando hay confianza. Hay ejemplos muy buenos en el Huila.",
    ],
    "bicimedellin": [
        "¡Me apunto el domingo!",
        "Lo de los tramos sueltos es cierto. Que conecten la red.",
        "Gracias por la recomendación del taller.",
    ],
    "barranquilla": [
        "¡La de la esquina de mi casa, sin duda!",
        "Lo de la sombra es clave. Más árboles nativos.",
        "Qué orgullo nuestra ciudad.",
    ],
    "caribe": [
        "Muy cierto. El turismo tiene que dejar algo a los que viven ahí.",
        "Lo del mar es preocupante. ¿Alguien tiene estudios de la zona?",
    ],
    "carnaval": ["¡Quien lo vive es quien lo goza!", "Ya estoy contando los días."],
    "salsacali": ["¡Allá nos vemos!", "Las escuelas de barrio son lo máximo."],
    "paramos": [
        "Qué experiencia tan bonita. ¿Cómo se organiza una visita así?",
        "La participación de las comunidades es la clave, de acuerdo.",
    ],
    "agua": ["Las dos cosas, exacto.", "Me interesa el debate. Ojalá se dé con datos."],
    "emprendimiento": [
        "A mí me ha funcionado bien la gratuita para empezar.",
        "Lo de los trámites es real. Uno pierde días enteros.",
    ],
    "basesdedatos": [
        "Te paso mis apuntes por el grupo.",
        "La tercera forma normal es la que más cuesta. Con ejemplos se entiende.",
        "¡Felicitaciones! Los triggers son lo máximo cuando funcionan.",
    ],
    "instituciones": [
        "Muy de acuerdo. Las instituciones son de todos.",
        "Ojalá se pensara así sin importar quién esté en el poder.",
    ],
    "educacion": ["Los orientadores hacen una labor enorme.", "Totalmente de acuerdo."],
    "ciudades": ["Las ciudades para caminar son ciudades para todos.", "Excelente punto."],
    "_": [
        "Muy de acuerdo.",
        "Interesante, no lo había pensado así.",
        "Gracias por compartirlo.",
        "Yo lo veo distinto, pero entiendo tu punto.",
        "¿Tienes la fuente? Me gustaría leer más.",
        "Esto merece más conversación.",
        "Qué bueno leer opiniones con calma.",
        "Se lo comparto a mi familia.",
    ],
}

# ---------------------------------------------------------------------------------------------------------
# Publicaciones CON cifras (las únicas que usan IA): muestran el análisis en la demo. Son exactamente frases de
# la evaluación (evaluacion/afirmaciones_*.yaml), cuya conclusión ya se conoce, puestas en boca de personas
# ficticias. Ninguna atribuye cifras a una institución o persona real. Si se siembran el mismo día (UTC) en que
# corrió la evaluación, el sistema reutiliza las lecturas guardadas y no gasta cupo; otro día, cuestan ~1
# lectura de cada proveedor por publicación.
#   (autor, texto, comunidad o None, respuestas [(autor, texto)])
CIFRAS = [
    ("alejandro_pineda", "La tasa de desempleo en marzo de 2026 fue de 8,8 %.", "Lectores de economía",
     [("laura_castano", "¿Y cómo va comparado con el mismo mes del año pasado?"),
      ("alejandro_pineda", "Buena pregunta: la ficha del dato trae la serie completa, ahí se ve.")]),
    ("camila_ortega", "En octubre de 2025 se registraron 1.112 homicidios en Colombia.", "Datos abiertos Colombia",
     [("sebastian_rojas", "Gracias por poner el mes exacto. Así se puede revisar contra la fuente."),
      ("manuela_cardenas", "¿Ese conteo ya es definitivo o todavía puede cambiar?")]),
    ("santiago_pardo", "En agosto de 2026 el desempleo bajó a 9,4 %.", None,
     [("mauricio_leon", "Ojo: la cifra está bien, pero según el dato oficial ese mes no bajó, subió."),
      ("santiago_pardo", "Tienes razón, lo leí mal. Gracias por la corrección.")]),
    ("laura_castano", "La inflación anual de julio de 2026 fue de 0,17 %.", "Lectores de economía",
     [("adriana_rincon", "Me parece muy baja para ser anual. ¿No será la mensual?")]),
    ("hernan_villa", "El desempleo de mayo de 2026 se ubicó en 8,8 %.", None,
     [("carolina_munoz", "Creo que ese valor es de otro mes. Vale la pena revisar el periodo.")]),
    ("adriana_rincon", "En julio de 2026 la inflación anual bajó a 6,03 %.", "Lectores de economía",
     [("felipe_arango", "Depende contra qué mes se compare, ¿no?")]),
    ("andres_mejia", "En Medellín el desempleo fue de 8,5 % en julio de 2026.", None,
     [("catalina_franco", "Sería bueno ver el dato de la ciudad junto al nacional.")]),
    ("mauricio_leon", "El desempleo se disparó: pasó de 8,1 % en julio a 9,4 % en agosto de 2026.", "Datos abiertos Colombia",
     [("camila_ortega", "Ese mes tiene una nota oficial que conviene leer junto al dato.")]),
    ("maria_jose_pena", "La deuda pública llegó a un récord de $1.238,2 billones en febrero de 2026.", None,
     [("alejandro_pineda", "¿Hay una serie oficial de deuda conectada para compararlo?")]),
    ("manuela_cardenas", "En lo corrido de 2026, hasta septiembre, la inflación acumula 5,74 %.", "Datos abiertos Colombia", []),
    ("tomas_restrepo", "La inflación anual de septiembre de 2026 fue 6,29 %, 1,11 puntos más que un año antes.",
     "Lectores de economía", [("laura_castano", "El primer dato es fácil de revisar; el cambio en puntos, no tanto.")]),
]

# ---------------------------------------------------------------------------------------------------------
# Debates: posturas distintas, defendidas con argumentos y con respeto. Parrhesia no elige ganador; la demo
# muestra que se puede discrepar en serio. Ninguno trae cifras (no gastan IA) ni atribuye frases a personas
# reales. Cada respuesta es (autor, texto, a qué responde: 0 = la publicación, n = la respuesta n).
DEBATES = [
    ("hernan_villa", "Defiendo que lo público tenga más peso en las pensiones: el ahorro individual deja por fuera a quien trabajó toda la vida en la informalidad. Una pensión no puede depender de cuánto pudo ahorrar alguien que ganó poco. #ReformaPensional", [
        ("alejandro_pineda", "Entiendo el objetivo, pero un sistema de reparto depende de que haya muchos trabajadores aportando por cada pensionado, y eso cambia con el envejecimiento. Sin ajustes, la cuenta la paga el presupuesto de todos.", 0),
        ("hernan_villa", "Por eso propongo que el subsidio sea explícito y vaya a quienes menos tienen, no a las pensiones más altas. El problema no es lo público, es a quién se subsidia.", 1),
        ("adriana_rincon", "Yo defiendo mantener las cuentas individuales: son del trabajador y se heredan. Lo que falta es formalizar empleo para que más gente pueda cotizar.", 0),
        ("laura_castano", "¿Y qué pasa con quien nunca logra formalizarse? Ahí el ahorro individual no alcanza. Un pilar básico para todos y un ahorro adicional voluntario combinan lo mejor de los dos.", 3),
        ("adriana_rincon", "Ese pilar básico lo comparto, siempre que se financie con reglas claras y no con más deuda.", 4),
    ]),
    ("carlos_herrera", "Necesitamos más policía en la calle de noche y castigos que se cumplan. Quien trabaja de noche lo vive: la sensación de impunidad hace que todo empeore. #Seguridad", [
        ("oscar_beltran", "Más policía ayuda, pero en mi barrio lo que cambió las cosas fue iluminar parques, abrir canchas y darles oficio a los pelados. Sin prevención, la cárcel se llena y nada cambia.", 0),
        ("carlos_herrera", "Las dos cosas sirven, pero la prevención toma años, y el que roba hoy lo hace porque sabe que sale rápido.", 1),
        ("felipe_arango", "Ojo con creer que la solución son penas más largas: muchas veces el problema es que los casos no se resuelven. Una justicia más rápida disuade más que una pena más larga.", 0),
        ("veronica_duarte", "En urgencias vemos las consecuencias cada fin de semana. Yo apoyo un control fuerte al porte de armas, venga de quien venga.", 3),
        ("carlos_herrera", "En eso estamos de acuerdo.", 4),
    ]),
    ("santiago_pardo", "Bajar los impuestos a las pequeñas empresas traería más empleo formal. Hoy formalizarse cuesta tanto que muchos prefieren quedarse por fuera. #Impuestos", [
        ("maria_jose_pena", "Bajar tarifas sin cerrar exenciones ni mejorar el recaudo deja huecos que terminan en recortes a salud o educación. Prefiero simplificar el sistema antes que bajarlo en bloque.", 0),
        ("santiago_pardo", "Simplificar me parece bien. A un negocio pequeño no solo le pesa cuánto paga, sino cuántos trámites tiene que hacer para pagarlo.", 1),
        ("tomas_restrepo", "Coincido con Santiago. Y que el impuesto llegue cuando el negocio ya vende, no antes de abrir.", 0),
        ("carolina_munoz", "Yo defiendo que quienes más ganan aporten más. Un sistema progresivo es justo y además financia lo que todos usamos.", 0),
        ("alejandro_pineda", "La progresividad funciona mejor en el impuesto a las personas que en el de las empresas; ahí podríamos encontrarnos.", 4),
    ]),
    ("natalia_vargas", "Defiendo que el Estado pague directamente a hospitales y clínicas. Los intermediarios han demorado pagos y autorizaciones durante años, y eso lo sufren los pacientes. #Salud", [
        ("paula_jimenez", "A mí me preocupa un cambio brusco. Mi EPS funciona razonablemente para mis hijos; prefiero exigirles más control que desmontarlas.", 0),
        ("natalia_vargas", "Es válido. La pregunta es cómo hacer que el control funcione, porque hasta ahora la vigilancia ha llegado tarde.", 1),
        ("carolina_munoz", "El modelo importa menos que tener datos claros: tiempos de espera, pagos y resultados por cada entidad, públicos y comparables.", 0),
        ("natalia_vargas", "De acuerdo con publicar esos datos, sea cual sea el modelo.", 3),
    ]),
    ("ricardo_salazar", "Colombia debe seguir explorando gas mientras hace la transición. Sin ese ingreso no hay con qué pagar lo social, y el gas que falte se termina importando más caro. #Energia", [
        ("mariana_quintero", "La transición no se puede aplazar siempre. Cada proyecto nuevo compromete agua y territorios por décadas. Prefiero invertir ya en solar y eólica, acordadas con las comunidades.", 0),
        ("ricardo_salazar", "Estoy de acuerdo con invertir en renovables, pero el sol no reemplaza mañana el gas de la cocina de millones de hogares.", 1),
        ("lucia_ospina", "Un punto medio: seguir con lo que ya está en producción, sin abrir frentes en ecosistemas frágiles, y con metas de salida claras y públicas.", 0),
        ("mariana_quintero", "Ese punto medio lo puedo defender si las metas se cumplen y se pueden revisar.", 3),
    ]),
    ("juan_pablo_diaz", "Defiendo seguir dialogando con los grupos armados. En el campo, cada diálogo que funciona significa familias que no tienen que salir de su tierra. #Paz", [
        ("miguel_angel_cruz", "Dialogar sin condiciones les da tiempo para fortalecerse. Apoyo el diálogo solo si primero paran la extorsión y el reclutamiento.", 0),
        ("juan_pablo_diaz", "Esas condiciones las comparto; el diálogo sirve si tiene plazos y verificación.", 1),
        ("kevin_mosquera", "En el Pacífico la gente quiere que la escuchen antes de cualquier decisión. Ni la mesa ni la fuerza sirven si se decide lejos de los territorios.", 0),
        ("maria_jose_pena", "Muy importante. La participación de las comunidades suele ser lo primero que se recorta.", 3),
    ]),
    ("mauricio_leon", "Defiendo la universidad pública gratuita: la plata no debería decidir quién estudia. #Educacion", [
        ("nicolas_acosta", "Como estudiante la apoyo, pero también hacen falta cupos y calidad, no solo matrícula cero.", 0),
        ("tomas_restrepo", "Prefiero créditos condonables y becas por mérito: así el recurso llega a quien estudia y termina.", 0),
        ("mauricio_leon", "Las becas por mérito suelen favorecer a quien tuvo mejor colegio. Por eso insisto en lo universal.", 2),
        ("tomas_restrepo", "Ahí tienes un punto. Quizá el mérito debería medirse frente al punto de partida de cada uno.", 3),
    ]),
    ("raul_cespedes", "El salario mínimo tiene que subir por encima de lo que suben los precios. Si no, cada año alcanza para menos. #SalarioMinimo", [
        ("santiago_pardo", "Lo entiendo, pero cuando sube mucho, los negocios pequeños contratamos menos o terminamos en la informalidad.", 0),
        ("raul_cespedes", "Entonces que el apoyo sea para el pequeño empleador, no frenar el salario de todos.", 1),
        ("alejandro_pineda", "La discusión debería mirar también la productividad de cada sector y región: no todos aguantan el mismo aumento.", 0),
    ]),
]

COMENTARIOS_COMPARTIDA = [
    "Vale la pena leer esto.",
    "Comparto porque me parece un buen punto.",
    "Para el debate de la semana.",
    "No estoy del todo de acuerdo, pero merece discusión.",
    "Muy claro.",
    None,
    None,
]


# ---------------------------------------------------------------------------------------------------------


def momento(dias_max: float = DIAS, despues_de: datetime | None = None) -> datetime:
    """Una fecha en los últimos días, más densa hacia hoy, entre las 6 a. m. y las 11 p. m. de Colombia."""
    if despues_de is not None:
        # La espera nunca pasa del 85 % del tiempo que queda hasta hoy: así lo reciente recibe respuestas
        # rápidas y lo antiguo, más tarde, sin que todo se amontone en el minuto de la siembra.
        queda = (AHORA - despues_de).total_seconds()
        espera = min(AZAR.uniform(4 * 60, 30 * 3600) * AZAR.random() ** 0.6, 0.85 * queda)
        return despues_de + timedelta(seconds=max(espera, min(20, 0.5 * queda)))
    dias = dias_max * AZAR.random() ** 1.7
    base = AHORA - timedelta(days=dias)
    hora_colombia = AZAR.choice([6, 7, 7, 8, 9, 10, 11, 12, 12, 13, 14, 15, 17, 18, 19, 19, 20, 20, 21, 22])
    t = base.replace(hour=(hora_colombia + 5) % 24, minute=AZAR.randint(0, 59), second=AZAR.randint(0, 59))
    return min(t, AHORA - timedelta(minutes=AZAR.randint(2, 90)))


def texto_de(item: str | tuple[str, str]) -> str:
    return item[1] if isinstance(item, tuple) else item


def hoy_en_tendencia(originales: list, comunidades: dict) -> None:
    """Una red viva tiene temas de hoy: las etiquetas públicas más usadas reciben publicaciones de las últimas
    horas, de personas distintas. Las tendencias no se escriben: las calcula el grafo con su regla de siempre
    (al menos tres personas, cuentas de más de siete días, nada de comunidades privadas)."""
    por_etiqueta: dict[str, list[int]] = {}
    for i, (_, _, texto, com) in enumerate(originales):
        if com and comunidades[com]["privada"]:
            continue
        for etiqueta in {e.lower() for e in re.findall(r"#(\w+)", texto)}:
            por_etiqueta.setdefault(etiqueta, []).append(i)
    movidas: set[int] = set()
    elegidas = sorted(por_etiqueta, key=lambda e: (-len(por_etiqueta[e]), e))[:6]
    for etiqueta in elegidas:
        autores, indices = set(), []
        for i in AZAR.sample(por_etiqueta[etiqueta], len(por_etiqueta[etiqueta])):
            if i not in movidas and originales[i][1] not in autores:
                autores.add(originales[i][1])
                indices.append(i)
        for i in indices[:AZAR.randint(3, 5)] if len(indices) >= 3 else []:
            _, autor, texto, com = originales[i]
            originales[i] = (AHORA - timedelta(hours=AZAR.uniform(0.6, 20)), autor, texto, com)
            movidas.add(i)


def etiqueta_de(texto: str) -> str:
    for palabra in texto.split():
        if palabra.startswith("#"):
            clave = palabra[1:].strip(".,;:!?").lower()
            if clave in RESPUESTAS:
                return clave
    return "_"


def sembrar(conn, seguidor: str | None) -> None:
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM social.usuario WHERE correo LIKE %s", (f"%@{DOMINIO}",))
    if cur.fetchone()[0]:
        raise SystemExit("La demo ya está sembrada. Para empezar de nuevo: --resembrar.")

    # 0. Ningún texto pasa el filtro previo de verificación: la demo no gasta IA.
    textos = [texto_de(t) for c in COMUNIDADES for t in c["publicaciones"]] + [t for _, t in GENERALES]
    textos += [r for rs in RESPUESTAS.values() for r in rs] + [c for c in COMENTARIOS_COMPARTIDA if c]
    textos += [t for _, t, _ in DEBATES] + [r for _, _, rs in DEBATES for _, r, _ in rs]
    cur.execute("SELECT t FROM unnest(%s::text[]) AS t WHERE verificacion.requiere_extraccion(t)", (textos,))
    con_cifras = [r[0] for r in cur.fetchall()]
    if con_cifras:
        raise SystemExit("Estos textos pasarían a la IA; corrígelos:\n  " + "\n  ".join(con_cifras))

    clave = secrets.token_urlsafe(12)
    hash_clave = PasswordHasher().hash(clave)

    # 1. Personas, con fecha de registro antes de su primera publicación.
    ids: dict[str, str] = {}
    for usuario, nombre, bio in PERSONAS:
        creado = AHORA - timedelta(days=AZAR.uniform(DIAS + 5, DIAS + 120))
        cur.execute(
            """INSERT INTO social.usuario (nombre_usuario, nombre_visible, correo, clave_hash, biografia, creado_en)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (usuario, nombre, f"{usuario}@{DOMINIO}", hash_clave, bio, creado),
        )
        ids[usuario] = cur.fetchone()[0]

    if seguidor:
        cur.execute("SELECT id FROM social.usuario WHERE nombre_usuario = %s AND estado = 'activo'", (seguidor,))
        fila = cur.fetchone()
        if fila is None:
            raise SystemExit(f"No existe una cuenta activa @{seguidor}")
        ids_seguidor = fila[0]

    # 2. Seguimientos: cada persona sigue a entre 6 y 16 otras; algo de reciprocidad.
    seguimientos: set[tuple[str, str]] = set()
    nombres = list(ids)
    for u in nombres:
        for v in AZAR.sample([n for n in nombres if n != u], AZAR.randint(6, 16)):
            seguimientos.add((u, v))
            if AZAR.random() < 0.35:
                seguimientos.add((v, u))
    for u, v in seguimientos:
        cur.execute("INSERT INTO social.seguimiento (seguidor_id, seguido_id, creado_en) VALUES (%s, %s, %s)",
                    (ids[u], ids[v], AHORA - timedelta(days=AZAR.uniform(DIAS, DIAS + 40))))

    # 3. Comunidades con sus papeles (los integrantes entran antes de publicar).
    comunidades: dict[str, dict] = {}
    for c in COMUNIDADES:
        creada = AHORA - timedelta(days=AZAR.uniform(DIAS + 2, DIAS + 60))
        cur.execute(
            """INSERT INTO social.comunidad (nombre, descripcion, reglas, privacidad, creada_por, creada_en)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (c["nombre"], c["descripcion"], c["reglas"], c["privacidad"], ids[c["admin"]], creada),
        )
        cid = cur.fetchone()[0]
        cur.execute("INSERT INTO social.bitacora_comunidad (comunidad_id, actor_id, accion, creada_en) VALUES (%s, %s, 'creada', %s)",
                    (cid, ids[c["admin"]], creada))
        papeles = {c["admin"]: "administrador"}
        if c["gestor"]:
            papeles[c["gestor"]] = "gestor"
        for m in c["moderadores"]:
            papeles[m] = "moderador"
        for i in c["integrantes"]:
            papeles.setdefault(i, "integrante")
        for usuario, papel in papeles.items():
            desde = creada + timedelta(hours=AZAR.uniform(0.1, 24 * 5)) if papel != "administrador" else creada
            cur.execute("INSERT INTO social.integrante (comunidad_id, usuario_id, papel, desde) VALUES (%s, %s, %s, %s)",
                        (cid, ids[usuario], papel, desde))
            if papel != "administrador":
                cur.execute(
                    "INSERT INTO social.bitacora_comunidad (comunidad_id, actor_id, accion, creada_en) VALUES (%s, %s, 'ingreso', %s)",
                    (cid, ids[usuario], desde))
            if papel in ("gestor", "moderador"):
                cur.execute(
                    """INSERT INTO social.bitacora_comunidad (comunidad_id, actor_id, accion, afectado_id, datos, creada_en)
                       VALUES (%s, %s, 'papel_asignado', %s, %s::jsonb, %s)""",
                    (cid, ids[c["admin"]], ids[usuario], f'{{"papel": "{papel}"}}', desde + timedelta(minutes=30)))
        comunidades[c["nombre"]] = {"id": cid, "privada": c["privacidad"] == "privada", "integrantes": list(papeles),
                                    "admin": c["admin"]}

    # Solicitudes pendientes en las comunidades privadas.
    for c in COMUNIDADES:
        if c["privacidad"] != "privada":
            continue
        info = comunidades[c["nombre"]]
        for usuario in AZAR.sample([n for n in nombres if n not in info["integrantes"]], 2):
            cur.execute("INSERT INTO social.solicitud_ingreso (comunidad_id, usuario_id, mensaje, creada_en) VALUES (%s, %s, %s, %s)",
                        (info["id"], ids[usuario], "Hola, me gustaría unirme al grupo.", AHORA - timedelta(days=AZAR.uniform(0.2, 4))))

    def publicar(autor: str, texto: str | None, cuando: datetime, comunidad: str | None = None,
                 responde_a: str | None = None, comparte: str | None = None) -> str:
        cur.execute("SELECT set_config('parrhesia.comunidad', %s::text, true)", (str(comunidad) if comunidad else "",))
        cur.execute(
            """INSERT INTO social.publicacion (autor_id, texto, responde_a_id, comparte_id, creado_en)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (ids[autor], texto, responde_a, comparte, cuando),
        )
        pid = cur.fetchone()[0]
        # Etiquetas y menciones con las mismas funciones de la base que usa social.publicar.
        cur.execute("""INSERT INTO social.etiqueta (nombre) SELECT unnest(social.extraer_etiquetas(%s))
                       ON CONFLICT (nombre) DO NOTHING""", (texto,))
        cur.execute("""INSERT INTO social.publicacion_etiqueta (publicacion_id, etiqueta_id)
                       SELECT %s, id FROM social.etiqueta WHERE nombre = ANY (social.extraer_etiquetas(%s))""",
                    (pid, texto))
        cur.execute(
            """INSERT INTO social.mencion_usuario (publicacion_id, usuario_id)
               SELECT %s, id FROM social.usuario WHERE nombre_usuario = ANY (social.extraer_menciones(%s))""",
            (pid, texto))
        cur.execute("SELECT set_config('parrhesia.comunidad', '', true)")
        return pid

    # 4. Publicaciones originales (en comunidades y fuera de ellas), en orden de fecha.
    originales = []
    for c in COMUNIDADES:
        info = comunidades[c["nombre"]]
        for item in c["publicaciones"]:
            autor, texto = item if isinstance(item, tuple) else (AZAR.choice(info["integrantes"]), item)
            originales.append((momento(), autor, texto, c["nombre"]))
    for autor, texto in GENERALES:
        originales.append((momento(), autor, texto, None))
    # Algunas menciones entre personas de la demo.
    for i in AZAR.sample(range(len(originales)), 14):
        cuando, autor, texto, com = originales[i]
        otro = AZAR.choice([n for n in (comunidades[com]["integrantes"] if com else nombres) if n != autor])
        originales[i] = (cuando, autor, f"{texto} ¿Qué opinas, @{otro}?", com)
    hoy_en_tendencia(originales, comunidades)
    originales.sort()

    publicadas = []  # (id, autor, cuando, comunidad, etiqueta)
    for cuando, autor, texto, com in originales:
        pid = publicar(autor, texto, cuando, comunidades[com]["id"] if com else None)
        publicadas.append((pid, autor, cuando, com, etiqueta_de(texto)))

    # 5. Respuestas (en hilo y, a veces, respuesta a la respuesta).
    respuestas = []
    for pid, autor, cuando, com, etiqueta in publicadas:
        posibles = [n for n in (comunidades[com]["integrantes"] if com else nombres) if n != autor]
        # Sin tema propio, pocas respuestas: así no se llena la red de "muy de acuerdo".
        opciones = [0, 0, 0, 1] if etiqueta == "_" else [0, 1, 1, 2, 2, 3]
        for _ in range(AZAR.choice(opciones)):
            quien = AZAR.choice(posibles)
            t = momento(despues_de=cuando)
            rid = publicar(quien, AZAR.choice(RESPUESTAS.get(etiqueta, RESPUESTAS["_"])), t, responde_a=pid)
            respuestas.append((rid, quien, t, com))
            if AZAR.random() < 0.25:
                publicar(autor, AZAR.choice(["¡Gracias!", "Buen punto, lo tendré en cuenta.", "Exacto, a eso me refería.",
                                             "Te entiendo, aunque lo veo un poco distinto."]),
                         momento(despues_de=t), responde_a=rid)

    # 5b. Debates: un hilo por tema, con réplica y contrarréplica en orden.
    for autor, texto, respuestas_debate in DEBATES:
        cuando = momento(dias_max=6)
        pid = publicar(autor, texto, cuando)
        publicadas.append((pid, autor, cuando, None, "_"))
        hilo = [(pid, cuando)]
        for quien, respuesta, a_cual in respuestas_debate:
            padre, desde = hilo[a_cual]
            t = momento(despues_de=max(desde, hilo[-1][1]))
            hilo.append((publicar(quien, respuesta, t, responde_a=padre), t))

    # 6. Compartidas (lo de comunidades privadas no se comparte fuera: lo impide la base).
    compartibles = [p for p in publicadas if not (p[3] and comunidades[p[3]]["privada"])]
    for pid, autor, cuando, com, _ in AZAR.sample(compartibles, 40):
        quien = AZAR.choice([n for n in nombres if n != autor])
        publicar(quien, AZAR.choice(COMENTARIOS_COMPARTIDA), momento(despues_de=cuando), comparte=pid)

    # 7. Reacciones: más para lo reciente y lo de comunidades activas; solo de quien puede verlo.
    todas = publicadas + [(r[0], r[1], r[2], r[3], "_") for r in respuestas]
    for pid, autor, cuando, com, _ in todas:
        posibles = [n for n in (comunidades[com]["integrantes"] if com and comunidades[com]["privada"] else nombres)
                    if n != autor]
        n = min(len(posibles), int(AZAR.expovariate(1 / 5)))
        for quien in AZAR.sample(posibles, n):
            cur.execute("INSERT INTO social.reaccion (publicacion_id, usuario_id, tipo, creado_en) VALUES (%s, %s, %s, %s)",
                        (pid, ids[quien], AZAR.choice(["me_gusta", "me_gusta", "me_gusta", "util"]),
                         momento(despues_de=cuando)))

    # 8. Publicaciones fijadas por su administrador (con el procedimiento: queda en la bitácora).
    for c in COMUNIDADES[:6]:
        info = comunidades[c["nombre"]]
        pids = [p[0] for p in publicadas if p[3] == c["nombre"]]
        cur.execute("CALL social.fijar_publicacion(%s, %s, true)", (ids[info["admin"]], pids[0]))

    # 9. La cuenta indicada queda conectada con la demo: sigue, es seguida y entra a comunidades públicas.
    if seguidor:
        for u in AZAR.sample(nombres, 14):
            cur.execute("INSERT INTO social.seguimiento (seguidor_id, seguido_id, creado_en) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (ids_seguidor, ids[u], AHORA - timedelta(days=AZAR.uniform(DIAS, DIAS + 10))))
        for u in AZAR.sample(nombres, 9):
            cur.execute("INSERT INTO social.seguimiento (seguidor_id, seguido_id, creado_en) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (ids[u], ids_seguidor, AHORA - timedelta(days=AZAR.uniform(1, DIAS))))
        for nombre in ("Movilidad Bogotá", "Datos abiertos Colombia", "Lectores de economía", "Barranquilla y el Caribe"):
            info = comunidades[nombre]
            cur.execute("""INSERT INTO social.integrante (comunidad_id, usuario_id, papel, desde) VALUES (%s, %s, 'integrante', %s)
                           ON CONFLICT DO NOTHING""", (info["id"], ids_seguidor, AHORA - timedelta(days=AZAR.uniform(DIAS, DIAS + 5))))

    cur.execute("SELECT count(*) FROM social.publicacion p JOIN social.usuario u ON u.id = p.autor_id WHERE u.correo LIKE %s",
                (f"%@{DOMINIO}",))
    total = cur.fetchone()[0]
    conn.commit()
    print(f"Demo sembrada: {len(PERSONAS)} personas, {len(COMUNIDADES)} comunidades, {total} publicaciones, "
          f"{len(seguimientos)} seguimientos.")
    print(f"Clave de demostración de todas las cuentas @{DOMINIO} (no se guarda en ningún lado): {clave}")


def sembrar_cifras(conn) -> None:
    """Agrega a la demo las publicaciones con cifras (CIFRAS), en las últimas horas del día UTC de hoy."""
    cur = conn.cursor()
    cur.execute("SELECT nombre_usuario, id FROM social.usuario WHERE correo LIKE %s", (f"%@{DOMINIO}",))
    ids = dict(cur.fetchall())
    if not ids:
        raise SystemExit("Primero siembra la demo.")
    cur.execute("SELECT count(*) FROM social.publicacion WHERE autor_id = ANY (%s) AND texto = ANY (%s)",
                (list(ids.values()), [t for _, t, _, _ in CIFRAS]))
    if cur.fetchone()[0]:
        raise SystemExit("Las publicaciones con cifras ya están en la demo.")
    cur.execute("SELECT nombre, id FROM social.comunidad WHERE creada_por = ANY (%s)", (list(ids.values()),))
    comunidades = dict(cur.fetchall())
    # Dentro del mismo día UTC (la fecha forma parte de la lectura de la IA) y antes de ahora.
    inicio = max(AHORA.replace(hour=0, minute=0, second=0, microsecond=0), AHORA - timedelta(hours=10))
    ventana = (AHORA - timedelta(minutes=3) - inicio).total_seconds()
    momentos = sorted(inicio + timedelta(seconds=ventana * AZAR.random()) for _ in CIFRAS)

    def publicar(autor, texto, cuando, comunidad=None, responde_a=None):
        cur.execute("SELECT set_config('parrhesia.comunidad', %s::text, true)", (str(comunidad) if comunidad else "",))
        cur.execute("INSERT INTO social.publicacion (autor_id, texto, responde_a_id, creado_en) VALUES (%s, %s, %s, %s)"
                    " RETURNING id", (ids[autor], texto, responde_a, cuando))
        pid = cur.fetchone()[0]
        cur.execute("SELECT set_config('parrhesia.comunidad', '', true)")
        return pid

    for (autor, texto, comunidad, respuestas), cuando in zip(CIFRAS, momentos):
        pid = publicar(autor, texto, cuando, comunidades.get(comunidad))
        t = cuando
        for quien, respuesta in respuestas:
            t = min(t + timedelta(minutes=AZAR.randint(3, 40)), AHORA - timedelta(minutes=1))
            publicar(quien, respuesta, t, responde_a=pid)
        for quien in AZAR.sample([n for n in ids if n != autor], AZAR.randint(3, 12)):
            cur.execute("INSERT INTO social.reaccion (publicacion_id, usuario_id, tipo, creado_en) VALUES (%s, %s, %s, %s)",
                        (pid, ids[quien], AZAR.choice(["util", "util", "me_gusta"]), min(cuando + timedelta(minutes=AZAR.randint(2, 90)), AHORA)))
    conn.commit()
    print(f"Agregadas {len(CIFRAS)} publicaciones con cifras: la verificación las procesa en los próximos minutos.")


def retirar(conn) -> None:
    cur = conn.cursor()
    cur.execute("""SELECT p.id, p.autor_id FROM social.publicacion p JOIN social.usuario u ON u.id = p.autor_id
                   WHERE u.correo LIKE %s AND p.estado = 'visible'""", (f"%@{DOMINIO}",))
    publicaciones = cur.fetchall()
    for pid, autor in publicaciones:
        cur.execute("CALL social.retirar_publicacion(%s, %s)", (pid, autor))
    cur.execute("SELECT id FROM social.usuario WHERE correo LIKE %s AND estado = 'activo'", (f"%@{DOMINIO}",))
    cuentas = [r[0] for r in cur.fetchall()]
    for uid in cuentas:
        cur.execute("CALL social.desactivar_cuenta(%s)", (uid,))
    conn.commit()
    print(f"Retiradas {len(publicaciones)} publicaciones y desactivadas {len(cuentas)} cuentas de la demo.")


DEMO_SQL = f"""
CREATE TEMP TABLE demo_usuario ON COMMIT DROP AS SELECT id FROM social.usuario WHERE correo LIKE '%@{DOMINIO}';
CREATE TEMP TABLE demo_comunidad ON COMMIT DROP AS
    SELECT id FROM social.comunidad WHERE creada_por IN (SELECT id FROM demo_usuario);
CREATE TEMP TABLE demo_publicacion ON COMMIT DROP AS
    SELECT id FROM social.publicacion
    WHERE autor_id IN (SELECT id FROM demo_usuario) OR comunidad_id IN (SELECT id FROM demo_comunidad);
CREATE TEMP TABLE demo_etiqueta ON COMMIT DROP AS
    SELECT DISTINCT etiqueta_id AS id FROM social.publicacion_etiqueta
    WHERE publicacion_id IN (SELECT id FROM demo_publicacion);
CREATE TEMP TABLE demo_id ON COMMIT DROP AS
    SELECT id::text FROM demo_usuario UNION SELECT id::text FROM demo_comunidad
    UNION SELECT id::text FROM demo_publicacion;
"""

# Lo que la limpieza NO borra: si existe, se detiene sin tocar nada.
FUERA_DE_LA_DEMO = {
    "publicaciones de otras cuentas que responden o comparten la demo": """
        SELECT count(*) FROM social.publicacion p
        WHERE p.id NOT IN (SELECT id FROM demo_publicacion)
          AND (p.responde_a_id IN (SELECT id FROM demo_publicacion) OR p.comparte_id IN (SELECT id FROM demo_publicacion))""",
    "publicaciones de otras cuentas que mencionan a la demo": """
        SELECT count(*) FROM social.mencion_usuario
        WHERE usuario_id IN (SELECT id FROM demo_usuario) AND publicacion_id NOT IN (SELECT id FROM demo_publicacion)""",
    "revisiones humanas sobre la demo (son trabajo de una persona real)": """
        SELECT count(*) FROM verificacion.revision_humana r JOIN verificacion.verificacion v ON v.id = r.verificacion_id
        JOIN verificacion.afirmacion a ON a.id = v.afirmacion_id WHERE a.publicacion_id IN (SELECT id FROM demo_publicacion)""",
    "figuras, declaraciones o propuestas hechas por la demo": """
        SELECT (SELECT count(*) FROM social.figura_publica WHERE creada_por IN (SELECT id FROM demo_usuario))
             + (SELECT count(*) FROM social.declaracion WHERE registrada_por IN (SELECT id FROM demo_usuario))
             + (SELECT count(*) FROM social.propuesta_figura
                WHERE propuesta_por IN (SELECT id FROM demo_usuario) OR resuelta_por IN (SELECT id FROM demo_usuario))
             + (SELECT count(*) FROM social.bitacora_figura WHERE actor_id IN (SELECT id FROM demo_usuario))""",
    "acciones de la demo en comunidades que no son de la demo": """
        SELECT count(*) FROM social.bitacora_comunidad
        WHERE comunidad_id NOT IN (SELECT id FROM demo_comunidad)
          AND (actor_id IN (SELECT id FROM demo_usuario) OR afectado_id IN (SELECT id FROM demo_usuario)
               OR publicacion_id IN (SELECT id FROM demo_publicacion))""",
}

# En orden: primero lo que apunta a otras filas. Las claves foráneas siguen activas durante la limpieza.
BORRADOS = [
    # Las verificaciones de las publicaciones con cifras de la demo (los trabajos de IA se conservan: son la
    # caché que permite resembrar sin gastar cupo).
    ("verificacion.entrega_evento", """evento_id IN (SELECT id FROM verificacion.evento_salida WHERE entidad_id IN (
        SELECT v.id::text FROM verificacion.verificacion v JOIN verificacion.afirmacion a ON a.id = v.afirmacion_id
        WHERE a.publicacion_id IN (SELECT id FROM demo_publicacion)))"""),
    ("verificacion.evento_salida", """entidad_id IN (SELECT v.id::text FROM verificacion.verificacion v
        JOIN verificacion.afirmacion a ON a.id = v.afirmacion_id WHERE a.publicacion_id IN (SELECT id FROM demo_publicacion))"""),
    ("verificacion.resultado_prueba", """verificacion_id IN (SELECT v.id FROM verificacion.verificacion v JOIN verificacion.afirmacion a
        ON a.id = v.afirmacion_id WHERE a.publicacion_id IN (SELECT id FROM demo_publicacion))"""),
    ("verificacion.evidencia", """verificacion_id IN (SELECT v.id FROM verificacion.verificacion v JOIN verificacion.afirmacion a
        ON a.id = v.afirmacion_id WHERE a.publicacion_id IN (SELECT id FROM demo_publicacion))"""),
    ("verificacion.verificacion", "afirmacion_id IN (SELECT id FROM verificacion.afirmacion WHERE publicacion_id IN (SELECT id FROM demo_publicacion))"),
    ("verificacion.guia_redactada", "afirmacion_id IN (SELECT id FROM verificacion.afirmacion WHERE publicacion_id IN (SELECT id FROM demo_publicacion))"),
    ("verificacion.verificacion_externa", "afirmacion_id IN (SELECT id FROM verificacion.afirmacion WHERE publicacion_id IN (SELECT id FROM demo_publicacion))"),
    ("verificacion.consulta_externa", "afirmacion_id IN (SELECT id FROM verificacion.afirmacion WHERE publicacion_id IN (SELECT id FROM demo_publicacion))"),
    ("verificacion.afirmacion", "publicacion_id IN (SELECT id FROM demo_publicacion)"),
    ("verificacion.procesamiento", "origen_tipo = 'publicacion' AND origen_id IN (SELECT id FROM demo_publicacion)"),
    ("social.reaccion", "publicacion_id IN (SELECT id FROM demo_publicacion) OR usuario_id IN (SELECT id FROM demo_usuario)"),
    ("social.mencion_usuario", "publicacion_id IN (SELECT id FROM demo_publicacion)"),
    ("social.mencion_figura", "publicacion_id IN (SELECT id FROM demo_publicacion)"),
    ("social.publicacion_etiqueta", "publicacion_id IN (SELECT id FROM demo_publicacion)"),
    ("social.bitacora_comunidad", "comunidad_id IN (SELECT id FROM demo_comunidad)"),
    ("social.publicacion", "id IN (SELECT id FROM demo_publicacion)"),
    ("social.solicitud_ingreso", "comunidad_id IN (SELECT id FROM demo_comunidad) OR usuario_id IN (SELECT id FROM demo_usuario)"
                                 " OR resuelta_por IN (SELECT id FROM demo_usuario)"),
    ("social.integrante", "comunidad_id IN (SELECT id FROM demo_comunidad) OR usuario_id IN (SELECT id FROM demo_usuario)"),
    ("social.comunidad", "id IN (SELECT id FROM demo_comunidad)"),
    ("social.seguimiento", "seguidor_id IN (SELECT id FROM demo_usuario) OR seguido_id IN (SELECT id FROM demo_usuario)"),
    ("social.sesion", "usuario_id IN (SELECT id FROM demo_usuario)"),
    ("social.nombre_anterior", "usuario_id IN (SELECT id FROM demo_usuario)"),
    ("social.intento_acceso", f"correo LIKE '%@{DOMINIO}'"),
    ("social.usuario", "id IN (SELECT id FROM demo_usuario)"),
    # Las etiquetas que solo usaba la demo.
    ("social.etiqueta", """id IN (SELECT id FROM demo_etiqueta)
        AND NOT EXISTS (SELECT 1 FROM social.publicacion_etiqueta x WHERE x.etiqueta_id = etiqueta.id)
        AND NOT EXISTS (SELECT 1 FROM social.declaracion_etiqueta x WHERE x.etiqueta_id = etiqueta.id)
        AND NOT EXISTS (SELECT 1 FROM social.tendencia x WHERE x.etiqueta_id = etiqueta.id)"""),
    # El outbox de la demo: si quedara, reconstruir el grafo volvería a crear la demo en Neo4j.
    ("social.entrega_evento", """evento_id IN (SELECT id FROM social.evento_salida
        WHERE string_to_array(entidad_id, ':') && (SELECT array_agg(id) FROM demo_id))"""),
    ("social.evento_salida", "string_to_array(entidad_id, ':') && (SELECT array_agg(id) FROM demo_id)"),
]

# Triggers de solo inserción, sin borrado y de salida que hay que apagar SOLO dentro de esta transacción.
# DISABLE TRIGGER USER no apaga las claves foráneas; si algo falla, el ROLLBACK los deja encendidos.
TABLAS_CON_TRIGGERS = ["verificacion.entrega_evento", "verificacion.evento_salida", "verificacion.resultado_prueba",
                       "verificacion.evidencia", "verificacion.verificacion", "verificacion.guia_redactada",
                       "verificacion.verificacion_externa", "verificacion.consulta_externa", "verificacion.afirmacion",
                       "social.reaccion", "social.bitacora_comunidad", "social.publicacion", "social.integrante",
                       "social.seguimiento", "social.sesion", "social.intento_acceso", "social.entrega_evento",
                       "social.evento_salida"]


def limpiar(conn, incluir_de: str | None = None) -> None:
    """Borra de verdad todo lo de la demo (solo desarrollo): las cuentas @demo.parrhesia.local y lo que crearon.

    La base no deja borrar publicaciones, bitácoras ni el outbox, y eso está bien en producción. Aquí se apagan
    esos triggers dentro de una sola transacción, se borra solo lo de la demo y se vuelven a encender antes de
    confirmar. No se confirma nada a medias: no toca otras cuentas, datos oficiales ni verificaciones.
    """
    cur = conn.cursor()
    for sentencia in DEMO_SQL.strip().split(";\n"):
        cur.execute(sentencia)
    if incluir_de:
        # Con permiso explícito: las publicaciones de esa cuenta que responden o comparten la demo (pruebas
        # hechas sobre la demo) se borran con ella. Nada más de esa cuenta se toca.
        cur.execute("""
            WITH RECURSIVE suyas AS (   -- y las que responden o comparten esas mismas, en cadena
                SELECT p.id FROM social.publicacion p JOIN social.usuario u ON u.id = p.autor_id
                WHERE u.nombre_usuario = %(cuenta)s AND (p.responde_a_id IN (SELECT id FROM demo_publicacion)
                                                         OR p.comparte_id IN (SELECT id FROM demo_publicacion))
                UNION
                SELECT p.id FROM social.publicacion p JOIN social.usuario u ON u.id = p.autor_id JOIN suyas s
                  ON p.responde_a_id = s.id OR p.comparte_id = s.id
                WHERE u.nombre_usuario = %(cuenta)s),
            a AS (INSERT INTO demo_publicacion SELECT id FROM suyas RETURNING id),
            b AS (INSERT INTO demo_etiqueta SELECT DISTINCT etiqueta_id FROM social.publicacion_etiqueta
                  WHERE publicacion_id IN (SELECT id FROM suyas) ON CONFLICT DO NOTHING)
            INSERT INTO demo_id SELECT id::text FROM a""", {"cuenta": incluir_de})
        print(f"Se incluyen {cur.rowcount} publicaciones de @{incluir_de} hechas sobre la demo.")
    cur.execute("SELECT count(*) FROM demo_usuario")
    if cur.fetchone()[0] == 0:
        print("No hay demo sembrada: nada que limpiar.")
        return
    for motivo, consulta in FUERA_DE_LA_DEMO.items():
        cur.execute(consulta)
        n = cur.fetchone()[0]
        if n:
            conn.rollback()
            raise SystemExit(f"No se limpia: hay {n} {motivo}. Eso ya no es solo de la demo.")

    for tabla in TABLAS_CON_TRIGGERS:
        cur.execute(f"ALTER TABLE {tabla} DISABLE TRIGGER USER")
    conteos = {}
    for tabla, donde in BORRADOS:
        cur.execute(f"DELETE FROM {tabla} WHERE {donde}")
        conteos[tabla] = cur.rowcount
    for tabla in TABLAS_CON_TRIGGERS:
        cur.execute(f"ALTER TABLE {tabla} ENABLE TRIGGER USER")

    cur.execute("SELECT count(*) FROM social.usuario WHERE correo LIKE %s", (f"%@{DOMINIO}",))
    if cur.fetchone()[0]:
        raise RuntimeError("quedaron cuentas de la demo después de limpiar")
    print("Demo limpiada: " + ", ".join(f"{t.split('.')[1]} {n}" for t, n in conteos.items() if n))


# Avatares ilustrados y genéricos (DiceBear "notionists", licencia CC0): no son fotos de personas reales,
# porque una cara real en una cuenta ficticia sería atribuirle a alguien lo que nunca dijo.
AVATAR = "https://api.dicebear.com/9.x/notionists/png?seed={}&size=400&backgroundColor=e9dfd0,dccbb4,efe7da,d8c9b8"
GUARDAR_FOTO = (
    "import sys\n"
    "from servicios.comun.configuracion import conectar_postgres\n"
    "from servicios.social import fotos\n"
    "nombre = fotos.guardar(fotos.procesar(sys.stdin.buffer.read()))\n"
    "with conectar_postgres('PG_URL_SOCIAL') as pg:\n"
    "    pg.execute('CALL social.fijar_foto(%s, %s, NULL)', (sys.argv[1], nombre))\n")


def poner_fotos(conn) -> None:
    """Cada cuenta de la demo recibe su avatar por el mismo camino que una foto subida (se valida y se limpia)."""
    import httpx
    cur = conn.cursor()
    cur.execute("SELECT id::text, nombre_usuario FROM social.usuario WHERE correo LIKE %s AND foto IS NULL", (f"%@{DOMINIO}",))
    cuentas = cur.fetchall()
    puestas = 0
    with httpx.Client(timeout=20) as http:
        for uid, usuario in cuentas:
            try:
                png = http.get(AVATAR.format(usuario)).raise_for_status().content
                subprocess.run(["docker", "compose", "exec", "-T", "social", "python", "-c", GUARDAR_FOTO, uid],
                               cwd=RAIZ, input=png, check=True, capture_output=True, timeout=60)
                puestas += 1
            except (httpx.HTTPError, OSError, subprocess.SubprocessError) as error:
                print(f"  sin avatar para @{usuario}: {error}")
    print(f"Avatares puestos: {puestas} de {len(cuentas)}.")


def reconstruir_grafo() -> None:
    """Neo4j es una proyección del outbox: tras limpiar, se rehace desde PostgreSQL (el servicio no está en la puerta)."""
    # Después se calculan las tendencias de las últimas 24 horas (el trabajador lo repite cada hora).
    llamada = ("import urllib.request as u\n"
               "for r in ('reconstruir', 'tendencias/calcular'):\n"
               "    print(r, u.urlopen(u.Request('http://localhost:8000/v1/' + r, method='POST'), timeout=600).read().decode()[:200])")
    comando = ["docker", "compose", "exec", "-T", "grafo", "python", "-c", llamada]
    try:
        salida = subprocess.run(comando, cwd=RAIZ, check=True, capture_output=True, text=True, timeout=660)
        print("Grafo:\n" + salida.stdout.strip())
    except (OSError, subprocess.SubprocessError) as error:
        print(f"No se pudo reconstruir el grafo ({error}). Hazlo a mano:\n  docker compose exec -T grafo python -c \"{llamada}\"")


def main() -> None:
    parser = argparse.ArgumentParser()
    accion = parser.add_mutually_exclusive_group()
    accion.add_argument("--retirar", action="store_true", help="retira publicaciones y desactiva cuentas (no borra)")
    accion.add_argument("--limpiar", action="store_true", help="borra la demo de verdad (solo desarrollo) y rehace el grafo")
    accion.add_argument("--resembrar", action="store_true", help="limpia y siembra de nuevo en una sola transacción")
    accion.add_argument("--cifras", action="store_true", help="agrega a la demo las publicaciones con cifras (usan IA)")
    accion.add_argument("--fotos", action="store_true", help="pone avatares ilustrados a las cuentas de la demo")
    parser.add_argument("--seguidor", help="nombre de usuario de una cuenta real para conectarla con la demo")
    parser.add_argument("--incluir-de", help="al limpiar, borra también las publicaciones de esta cuenta hechas sobre la demo")
    args = parser.parse_args()
    conn = connect(autocommit=False)
    try:
        if args.retirar:
            retirar(conn)
        elif args.limpiar:
            limpiar(conn, args.incluir_de)
            conn.commit()
        elif args.resembrar:
            limpiar(conn, args.incluir_de)
            sembrar(conn, args.seguidor)  # confirma las dos cosas juntas
            sembrar_cifras(conn)
        elif args.cifras:
            sembrar_cifras(conn)
        elif args.fotos:
            poner_fotos(conn)
        else:
            sembrar(conn, args.seguidor)
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    if args.limpiar or args.resembrar:
        reconstruir_grafo()
    if args.resembrar:
        conn = connect(autocommit=True)
        try:
            poner_fotos(conn)
        finally:
            conn.close()


if __name__ == "__main__":
    main()
