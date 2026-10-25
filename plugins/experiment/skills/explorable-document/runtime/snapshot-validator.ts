/** Build-time seam: replaced by the exact revision's precompiled JSON Schema. */
export default function validateSnapshot(_value: unknown): boolean {
  throw new Error(
    "Snapshot validator was not compiled. Rebuild this artifact.",
  );
}
