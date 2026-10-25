export interface FieldOption {
  value: string;
  label: string;
  disabled?: boolean;
}
export interface RadioOption extends FieldOption {
  description?: string;
}

export function optionsError(
  options: readonly RadioOption[],
  value: string | null,
  limit: number,
): string | null {
  if (!Array.isArray(options) || options.length > limit)
    return `options must be an array of at most ${limit} choices.`;
  const seen = new Set<string>();
  for (const option of options) {
    if (
      !option ||
      typeof option !== "object" ||
      typeof option.value !== "string" ||
      !option.value.trim() ||
      typeof option.label !== "string" ||
      !option.label.trim()
    )
      return "Options need nonempty string values and labels.";
    if (seen.has(option.value)) return "Option values must be unique.";
    seen.add(option.value);
    if (option.disabled !== undefined && typeof option.disabled !== "boolean")
      return "Option disabled must be boolean.";
    if (
      option.description !== undefined &&
      typeof option.description !== "string"
    )
      return "Option descriptions must be text.";
  }
  if (value !== null && (typeof value !== "string" || !seen.has(value)))
    return "The selected value is not in this option catalog. Update the authored value explicitly.";
  return null;
}
