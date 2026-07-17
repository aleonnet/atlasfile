/** Identidade visual determinística por projeto (avatar do switcher e do palette). */

const HUES = [14, 268, 32, 162, 221, 338, 46, 245]; // ancorados na paleta chart-1..8

export function projectColor(projectId: string): string {
  let hash = 0;
  for (let i = 0; i < projectId.length; i++) {
    hash = (hash * 31 + projectId.charCodeAt(i)) >>> 0;
  }
  const hue = HUES[hash % HUES.length];
  return `hsl(${hue} 62% 46%)`;
}

export function projectInitial(label: string): string {
  return (label.trim()[0] || "?").toUpperCase();
}
