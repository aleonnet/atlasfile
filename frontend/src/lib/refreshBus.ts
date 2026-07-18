/** Bus mínimo de reatividade: qualquer mutação de dados (scan, decisão de
 *  triagem, restauração) emite um evento global e os cards que exibem dados
 *  derivados (histórico, fila da INBOX, rejeitados) recarregam sozinhos.
 *  Princípio do produto: nada depende de reload de página. */

const EVENT = "atlas:data-refresh";

export function emitDataRefresh(): void {
  window.dispatchEvent(new CustomEvent(EVENT));
}

/** Assina o evento; retorna o unsubscribe (usar no cleanup do useEffect). */
export function onDataRefresh(listener: () => void): () => void {
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}
