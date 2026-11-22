// Foto de perfil o, si no hay, la inicial. La foto la sirve el propio servicio (CSP: solo 'self').
export function Avatar({ nombre, foto, grande = false }: { nombre: string; foto?: string | null; grande?: boolean }) {
  const clase = `avatar${grande ? " avatar--grande" : ""}`;
  if (foto) return <img className={`${clase} avatar--foto`} src={foto} alt="" loading="lazy" decoding="async" />;
  return <span className={clase} aria-hidden="true">{nombre.slice(0, 1).toUpperCase()}</span>;
}
