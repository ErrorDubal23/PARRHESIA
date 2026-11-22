export type EstadoVerificacion = "pendiente" | "sin_cifras" | "lista" | "requiere_revision";
export type Conclusion = "se_sostiene" | "se_debilita" | "se_invierte" | "sin_dato_comparable";

export interface Usuario {
  id: string;
  nombre_usuario: string;
  nombre_visible: string;
  rol: "usuario" | "verificador" | "admin";
  foto: string | null;
  biografia?: string | null;
  correo?: string;
}

export interface Publicacion {
  id: string;
  autor: { nombre_usuario: string; nombre_visible: string; foto: string | null };
  texto: string | null;
  estado: string;
  responde_a_id: string | null;
  comparte_id: string | null;
  etiquetas: string[];
  creado_en: string;
  totales: { respuestas: number; compartidas: number; reacciones: number; me_gusta: number; util: number };
  mi_reaccion: "me_gusta" | "util" | null;
  mi_compartida: string | null;   // mi compartida sin comentario, si existe (pulsar otra vez la deshace)
  verificacion: EstadoVerificacion;
  comunidad: { id: string; nombre: string; privacidad: "publica" | "privada" } | null;
  fijada: boolean;
  distancia?: number;
  profundidad?: number;
  responde_a: { nombre_usuario: string } | null;  // a quién responde (el contexto de una respuesta)
  original: Publicacion | null;                    // lo que se compartió (un solo nivel)
}

export interface Evidencia {
  observacion_id: string;
  rol: "citada" | "contraste" | "completa";
  serie: string;
  nombre_serie: string;
  fuente: string;
  periodo: string;
  valor: string;
}

export interface Verificacion {
  id: string;
  version: number;
  conclusion: Conclusion;
  explicacion: string | null;
  serie: string | null;
  evidencia: Evidencia[];
  pruebas: { codigo: string; nombre: string; resultado: string; detalle: string | null }[];
  creado_en: string;
}

export interface Afirmacion {
  id: string;
  texto_citado: string;
  indicador: string | null;
  variante: string | null;
  periodo: string | null;
  valor_dicho: string | null;
  estado: string;
  consenso: "coinciden" | "difieren" | null;
  verificacion: Verificacion | null;
  guia?: Guia;
}

/** Decisión 34: por qué pasa eso con el dato y cómo comprobarlo uno mismo. Sin cifras. */
export interface Guia {
  motivo: string | null;
  consejos: { origen: string; codigo: string; para_entenderlo: string; pasos: string[] }[];
  fuentes: { nombre: string; url: string; como_leer: string }[];
  redaccion: string | null;   // redactada por IA y aprobada por un juez de otro proveedor
  otros_medios: { medio: string; titulo: string; url: string; publicada_en: string | null }[];
}

export interface TextoVerificado {
  estado: EstadoVerificacion;
  afirmaciones: Afirmacion[];
}
