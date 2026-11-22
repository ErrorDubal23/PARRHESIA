// Dibuja el texto de una publicación con su formato (formato.ts) y sus #etiquetas y @menciones.
// Solo elementos de React: el texto de una persona nunca se inserta como HTML.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { analizar, type Nodo } from "../formato";

/** #etiquetas y @menciones de un trozo de texto plano, como enlaces internos. */
function Marcas({ texto }: { texto: string }) {
  const partes: ReactNode[] = [];
  const patron = /([#@][\p{L}\p{N}_]+)/gu;
  let ultimo = 0;
  for (const m of texto.matchAll(patron)) {
    partes.push(texto.slice(ultimo, m.index));
    const palabra = m[0];
    const destino = palabra.startsWith("#")
      ? `/tendencias/${encodeURIComponent(palabra.slice(1).toLowerCase())}`
      : `/perfil/${palabra.slice(1).toLowerCase()}`;
    partes.push(<Link key={m.index} to={destino} className="marca-texto" onClick={(e) => e.stopPropagation()}>{palabra}</Link>);
    ultimo = (m.index ?? 0) + palabra.length;
  }
  partes.push(texto.slice(ultimo));
  return <>{partes}</>;
}

function Nodos({ nodos }: { nodos: Nodo[] }) {
  return (
    <>
      {nodos.map((n, i) => {
        if (n.tipo === "texto") return <Marcas key={i} texto={n.valor} />;
        if (n.tipo === "negrita") return <strong key={i}><Nodos nodos={n.hijos} /></strong>;
        if (n.tipo === "cursiva") return <em key={i}><Nodos nodos={n.hijos} /></em>;
        // Enlace externo: siempre con su dominio a la vista (nadie disfraza un sitio cualquiera como fuente oficial).
        return (
          <a key={i} href={n.url} target="_blank" rel="nofollow ugc noopener noreferrer" className="enlace-externo"
            onClick={(e) => e.stopPropagation()}>
            {n.etiqueta}<span className="enlace-externo__dominio">{n.dominio}</span>
          </a>
        );
      })}
    </>
  );
}

/** Texto de una publicación con su formato. Se dibuja con elementos de React: nunca se inserta HTML. */
export function TextoEnriquecido({ texto }: { texto: string }) {
  return <Nodos nodos={analizar(texto)} />;
}

