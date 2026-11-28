// Pilihan font editor & terminal (id -> CSS font-family). File font dibundel oleh build.mjs.
export const FONT_FAMILIES = {
  system: "monospace",
  jetbrains: '"CS JetBrains Mono", monospace',
  fira: '"CS Fira Code", monospace',
  sourcecode: '"CS Source Code Pro", monospace',
  ubuntu: '"CS Ubuntu Mono", monospace',
  roboto: '"CS Roboto Mono", monospace',
  plex: '"CS IBM Plex Mono", monospace',
};
export const fontCss = (id) => FONT_FAMILIES[id] || FONT_FAMILIES.jetbrains;

/** Muat font dulu (agar lebar huruf yang diukur benar), lalu panggil cb. */
export function whenFontReady(id, cb) {
  const fam = fontCss(id);
  if (!document.fonts || id === "system") { cb(fam); return; }
  Promise.all([document.fonts.load(`14px ${fam}`), document.fonts.load(`bold 14px ${fam}`)])
    .catch(() => {}).then(() => cb(fam));
}
