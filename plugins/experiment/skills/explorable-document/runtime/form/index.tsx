import { useId } from "react";
import {
  FieldDiagnostic,
  FieldMessages,
  type FieldProps,
  FieldShell,
  fieldError,
  useField,
  useValidity,
} from "./field";
import { type FieldOption, optionsError, type RadioOption } from "./options";
import "./form.css";

export type { FieldProps } from "./field";
export type { FieldOption, RadioOption } from "./options";

export interface RadioGroupProps extends FieldProps {
  value: string | null;
  options: readonly RadioOption[];
  onChange: (value: string) => void;
  layout?: "row" | "column";
}
export function RadioGroup(props: RadioGroupProps) {
  const ids = useField(props);
  const name = `ed-radio-${useId()}`;
  const validity = useValidity<HTMLInputElement>(props.error);
  const diagnostic =
    fieldError(props) ||
    optionsError(props.options, props.value, 12) ||
    (typeof props.onChange !== "function"
      ? "onChange must be a function."
      : null) ||
    (props.layout !== undefined && !["row", "column"].includes(props.layout)
      ? "layout must be row or column."
      : null);
  if (diagnostic) return <FieldDiagnostic message={diagnostic} />;
  const unavailable = props.options.length === 0;
  return (
    <fieldset
      id={ids.id}
      className={`ed-field ed-radio ${props.className || ""}`}
      disabled={props.disabled || unavailable}
      aria-describedby={ids.describedBy}
      aria-invalid={ids.invalid}
    >
      <legend>
        {props.label}
        {props.required && (
          <span className="ed-field-required"> · Required</span>
        )}
      </legend>
      {unavailable ? (
        <p className="ed-field-help">No options available.</p>
      ) : (
        <div
          className={`ed-radio-options ed-radio-${props.layout || "column"}`}
        >
          {props.options.map((option, index) => {
            const optionId = `${ids.id}-option-${index}`;
            return (
              <div className="ed-choice" key={option.value}>
                <input
                  type="radio"
                  id={optionId}
                  name={name}
                  value={option.value}
                  ref={
                    index === props.options.findIndex((o) => !o.disabled)
                      ? validity
                      : undefined
                  }
                  required={props.required}
                  checked={props.value === option.value}
                  disabled={option.disabled}
                  aria-invalid={ids.invalid}
                  aria-describedby={
                    [
                      ids.describedBy,
                      option.description && `${optionId}-description`,
                    ]
                      .filter(Boolean)
                      .join(" ") || undefined
                  }
                  onChange={() => props.onChange(option.value)}
                />
                <div>
                  <label htmlFor={optionId}>{option.label}</label>
                  {option.description && (
                    <p className="ed-field-help" id={`${optionId}-description`}>
                      {option.description}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <FieldMessages props={props} ids={ids} />
    </fieldset>
  );
}
export interface SelectFieldProps extends FieldProps {
  value: string | null;
  options: readonly FieldOption[];
  onChange: (value: string | null) => void;
  placeholder?: string;
}
export function SelectField(props: SelectFieldProps) {
  const ids = useField(props);
  const ref = useValidity<HTMLSelectElement>(props.error);
  const diagnostic =
    fieldError(props) ||
    optionsError(props.options, props.value, 200) ||
    (typeof props.onChange !== "function"
      ? "onChange must be a function."
      : null) ||
    (props.placeholder !== undefined &&
    (typeof props.placeholder !== "string" || !props.placeholder.trim())
      ? "placeholder must be nonempty text."
      : null);
  if (diagnostic) return <FieldDiagnostic message={diagnostic} />;
  const unavailable = props.options.length === 0;
  return (
    <FieldShell props={props} ids={ids}>
      <span className="ed-select-wrap">
        <select
          id={ids.id}
          ref={ref}
          value={props.value ?? ""}
          required={props.required}
          disabled={props.disabled || unavailable}
          aria-describedby={ids.describedBy}
          aria-invalid={ids.invalid}
          onChange={(e) => props.onChange(e.target.value || null)}
        >
          <option value="" disabled={props.required || unavailable}>
            {unavailable
              ? "No options available"
              : props.placeholder || "Choose an option"}
          </option>
          {props.options.map((option) => (
            <option
              key={option.value}
              value={option.value}
              disabled={option.disabled}
            >
              {option.label}
            </option>
          ))}
        </select>
        <span className="ed-select-caret" aria-hidden="true" />
      </span>
    </FieldShell>
  );
}
export interface CheckboxFieldProps extends FieldProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
}
export function CheckboxField(props: CheckboxFieldProps) {
  const ids = useField(props);
  const ref = useValidity<HTMLInputElement>(props.error);
  const diagnostic =
    fieldError(props) ||
    (typeof props.checked !== "boolean" ? "checked must be boolean." : null) ||
    (typeof props.onChange !== "function"
      ? "onChange must be a function."
      : null);
  if (diagnostic) return <FieldDiagnostic message={diagnostic} />;
  return (
    <div className={`ed-field ed-checkbox ${props.className || ""}`}>
      <div className="ed-choice">
        <input
          id={ids.id}
          ref={ref}
          type="checkbox"
          checked={props.checked}
          required={props.required}
          disabled={props.disabled}
          aria-describedby={ids.describedBy}
          aria-invalid={ids.invalid}
          onChange={(e) => props.onChange(e.target.checked)}
        />
        <label htmlFor={ids.id}>
          {props.label}
          {props.required && (
            <span className="ed-field-required"> · Required</span>
          )}
        </label>
      </div>
      <FieldMessages props={props} ids={ids} />
    </div>
  );
}
export interface RangeProps extends Omit<FieldProps, "required"> {
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
}
export function Range(props: RangeProps) {
  const ids = useField(props);
  const ref = useValidity<HTMLInputElement>(props.error);
  const step = props.step ?? 1;
  const diagnostic =
    fieldError(props) ||
    (![props.value, props.min, props.max, step].every(
      (v) => typeof v === "number" && Number.isFinite(v),
    ) ||
    props.min > props.max ||
    step <= 0
      ? "Range requires finite value/bounds and a positive step."
      : null) ||
    (typeof props.onChange !== "function"
      ? "onChange must be a function."
      : null);
  if (diagnostic) return <FieldDiagnostic message={diagnostic} />;
  return (
    <FieldShell props={props} ids={ids} output={<output>{props.value}</output>}>
      <input
        id={ids.id}
        ref={ref}
        type="range"
        min={props.min}
        max={props.max}
        step={step}
        value={props.value}
        disabled={props.disabled}
        aria-describedby={ids.describedBy}
        aria-invalid={ids.invalid}
        onChange={(e) => props.onChange(Number(e.target.value))}
      />
    </FieldShell>
  );
}
export type { NumberReading, NumberRules } from "./number";
export { readNumber } from "./number";
export type { NumberFieldProps } from "./number-field";
export { NumberField } from "./number-field";
