import { useState } from "react";
import {
  FieldDiagnostic,
  type FieldProps,
  FieldShell,
  fieldError,
  useField,
  useValidity,
} from "./field";
import { type NumberRules, numberRulesError, readNumber } from "./number";
export interface NumberFieldProps extends FieldProps, NumberRules {
  value: string;
  onChange: (raw: string) => void;
  validation?: "blur" | "change";
}
export function NumberField(props: NumberFieldProps) {
  const [touched, setTouched] = useState(false);
  const reading = readNumber(props.value, props);
  const visibleError =
    props.error ||
    (touched || props.validation === "change" ? reading.error : undefined) ||
    undefined;
  const displayed = { ...props, error: visibleError };
  const ids = useField(props, visibleError);
  const ref = useValidity<HTMLInputElement>(props.error || reading.error);
  const diagnostic =
    fieldError(props) ||
    numberRulesError(props) ||
    (typeof props.value !== "string" ? "Numeric draft must be text." : null) ||
    (typeof props.onChange !== "function"
      ? "onChange must be a function."
      : null) ||
    (props.validation !== undefined &&
    !["blur", "change"].includes(props.validation)
      ? "validation must be blur or change."
      : null);
  if (diagnostic) return <FieldDiagnostic message={diagnostic} />;
  return (
    <FieldShell
      props={displayed}
      ids={ids}
      reservedError={props.error || reading.error}
    >
      <input
        id={ids.id}
        ref={ref}
        type="text"
        inputMode={props.integer ? "numeric" : "decimal"}
        value={props.value}
        required={props.required}
        disabled={props.disabled}
        aria-invalid={ids.invalid}
        aria-describedby={ids.describedBy}
        onChange={(e) => props.onChange(e.target.value)}
        onBlur={() => setTouched(true)}
        onInvalid={() => setTouched(true)}
      />
    </FieldShell>
  );
}
