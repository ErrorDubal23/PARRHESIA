"""Servicio de grafo: proyección de la red social en Neo4j, alimentada por el outbox de PostgreSQL.

PostgreSQL es la fuente de verdad. El grafo solo lo escribe este servicio, a partir
de los eventos de social.evento_salida y verificacion.evento_salida, y se puede
reconstruir completo desde ellos (docs/diseno/04_modelo_grafo.md).
"""
