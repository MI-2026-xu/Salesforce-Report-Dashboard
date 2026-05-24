// Tell TypeScript that .css files are valid side-effect imports.
// Next.js handles them at build time; this declaration silences TS2882.
declare module "*.css" {
  const styles: { [className: string]: string };
  export default styles;
}
