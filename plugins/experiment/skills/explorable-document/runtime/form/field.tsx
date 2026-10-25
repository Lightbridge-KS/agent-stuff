import { type ReactNode, useId, useLayoutEffect, useRef } from "react";

export interface FieldProps {
  label: string;
  id?: string;
  help?: string;
  error?: string;
  disabled?: boolean;
  required?: boolean;
  className?: string;
}
export function fieldError(props: FieldProps): string | null {
  if (typeof props.label !== "string" || !props.label.trim())
    return "A nonempty visible label is required.";
  for (const key of ["id", "help", "error", "className"] as const)
    if (props[key] !== undefined && typeof props[key] !== "string")
      return `${key} must be text.`;
  if (props.id !== undefined && (!props.id.trim() || /\s/.test(props.id)))
    return "id must be nonempty and contain no whitespace.";
  for (const key of ["disabled", "required"] as const)
    if (props[key] !== undefined && typeof props[key] !== "boolean")
      return `${key} must be boolean.`;
  return null;
}
export function FieldDiagnostic({ message }: { message: string }) {
  return <p className="ed-field-diagnostic">Field unavailable: {message}</p>;
}
export function useField(props: FieldProps, visibleError = props.error) {
  const generated = useId();
  const id = props.id ?? `ed-field-${generated}`;
  return {
    id,
    helpId: `${id}-help`,
    errorId: `${id}-error`,
    describedBy:
      [props.help && `${id}-help`, visibleError && `${id}-error`]
        .filter(Boolean)
        .join(" ") || undefined,
    invalid: Boolean(visibleError) || undefined,
  };
}
export type FieldIds = ReturnType<typeof useField>;
/** Keep authored domain errors in native form validity as well as inline text. */
export function useValidity<T extends HTMLInputElement | HTMLSelectElement>(
  error?: string | null,
) {
  const ref = useRef<T>(null);
  useLayoutEffect(() => {
    ref.current?.setCustomValidity(error || "");
  });
  return ref;
}
export function FieldMessages({
  props,
  ids,
  reservedError,
}: {
  props: FieldProps;
  ids: FieldIds;
  reservedError?: string | null;
}) {
  return (
    <>
      {props.help && (
        <p className="ed-field-help" id={ids.helpId}>
          {props.help}
        </p>
      )}
      {(props.error || reservedError !== undefined) && (
        <p
          className="ed-field-error"
          id={ids.errorId}
          aria-hidden={!props.error}
          style={{ visibility: props.error ? "visible" : "hidden" }}
        >
          {props.error || reservedError || "\u00a0"}
        </p>
      )}
    </>
  );
}
export function FieldShell({
  props,
  ids,
  children,
  output,
  reservedError,
}: {
  props: FieldProps;
  ids: FieldIds;
  children: ReactNode;
  output?: ReactNode;
  reservedError?: string | null;
}) {
  return (
    <div className={`ed-field control ${props.className || ""}`}>
      <label className="ed-field-label" htmlFor={ids.id}>
        <span>
          {props.label}
          {props.required && (
            <span className="ed-field-required"> · Required</span>
          )}
        </span>
        {output}
      </label>
      {children}
      <FieldMessages props={props} ids={ids} reservedError={reservedError} />
    </div>
  );
}
