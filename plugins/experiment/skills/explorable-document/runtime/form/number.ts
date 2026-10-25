export interface NumberRules {
  min?: number;
  max?: number;
  integer?: boolean;
  required?: boolean;
}
export type NumberReading =
  | { status: "valid"; value: number; error: null }
  | { status: "empty"; value: null; error: string | null }
  | { status: "incomplete" | "invalid"; value: null; error: string };
export function numberRulesError(rules: NumberRules): string | null {
  if (!rules || typeof rules !== "object" || Array.isArray(rules))
    return "Number rules must be an object.";
  for (const key of ["min", "max"] as const)
    if (
      rules[key] !== undefined &&
      (typeof rules[key] !== "number" || !Number.isFinite(rules[key]))
    )
      return "Number bounds must be finite.";
  if (
    rules.min !== undefined &&
    rules.max !== undefined &&
    rules.min > rules.max
  )
    return "Number minimum must not exceed maximum.";
  for (const key of ["integer", "required"] as const)
    if (rules[key] !== undefined && typeof rules[key] !== "boolean")
      return `${key} must be boolean.`;
  return null;
}
const complete = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i;
const unfinished = /^(?:[+-]|[+-]?\.|[+-]?(?:\d+(?:\.\d*)?|\.\d+)e[+-]?)$/i;
/** Preserve editing text at the call site; parse only a whole, finite literal here. */
export function readNumber(
  raw: string,
  rules: NumberRules = {},
): NumberReading {
  const invalid = (error: string): NumberReading => ({
    status: "invalid",
    value: null,
    error,
  });
  const ruleError = numberRulesError(rules);
  if (ruleError) return invalid(ruleError);
  if (typeof raw !== "string") return invalid("Numeric draft must be text.");
  const text = raw.trim();
  if (!text)
    return {
      status: "empty",
      value: null,
      error: rules.required ? "Enter a value." : null,
    };
  if (unfinished.test(text))
    return {
      status: "incomplete",
      value: null,
      error: "Finish entering the number.",
    };
  if (!complete.test(text))
    return invalid("Enter a number using digits and a decimal point.");
  const value = Number(text);
  if (!Number.isFinite(value)) return invalid("Enter a finite number.");
  // Reject fractional literals even when IEEE-754 would round them to an integer.
  const [mantissa, exponent = "0"] = text
    .replace(/^[+-]/, "")
    .toLowerCase()
    .split("e");
  const fractionDigits = mantissa.includes(".")
    ? mantissa.length - mantissa.indexOf(".") - 1
    : 0;
  const digits = mantissa.replace(".", "");
  const trailingZeroes = digits.length - digits.replace(/0+$/, "").length;
  const wholeLiteral =
    /^0+$/.test(digits) || fractionDigits - Number(exponent) <= trailingZeroes;
  if (rules.integer && (!Number.isSafeInteger(value) || !wholeLiteral))
    return invalid("Enter a safe whole number.");
  if (rules.min !== undefined && value < rules.min)
    return invalid(`Enter a value of at least ${rules.min}.`);
  if (rules.max !== undefined && value > rules.max)
    return invalid(`Enter a value of at most ${rules.max}.`);
  return { status: "valid", value, error: null };
}
