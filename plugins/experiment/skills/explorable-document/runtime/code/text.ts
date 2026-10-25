export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };
export const TEXT_LIMIT = 100_000;
const DEPTH_LIMIT = 12;
export type PanelText = { text: string; format: string; error: string | null };
/** Serialize plain JSON without invoking accessors/toJSON or dropping unsupported values. */
export function jsonText(value: unknown): string {
  const chunks: string[] = [];
  let length = 0;
  const ancestors = new Set<object>();
  const append = (text: string) => {
    length += text.length;
    if (length > TEXT_LIMIT)
      throw Error(`Text exceeds ${TEXT_LIMIT} characters.`);
    chunks.push(text);
  };
  const quote = (text: string) => {
    if (text.length > TEXT_LIMIT)
      throw Error(`Text exceeds ${TEXT_LIMIT} characters.`);
    return JSON.stringify(text);
  };
  function visit(item: unknown, depth: number): void {
    if (item === null) {
      append("null");
      return;
    }
    if (typeof item === "string") {
      append(quote(item));
      return;
    }
    if (typeof item === "boolean") {
      append(String(item));
      return;
    }
    if (typeof item === "number") {
      if (!Number.isFinite(item)) throw Error("JSON numbers must be finite.");
      append(JSON.stringify(item));
      return;
    }
    if (typeof item !== "object")
      throw Error("JSON contains an unsupported value.");
    if (depth >= DEPTH_LIMIT)
      throw Error(`JSON nesting exceeds ${DEPTH_LIMIT} containers.`);
    if (ancestors.has(item)) throw Error("JSON contains a cycle.");
    const array = Array.isArray(item);
    if (
      !array &&
      Object.getPrototypeOf(item) !== Object.prototype &&
      Object.getPrototypeOf(item) !== null
    )
      throw Error("JSON objects must be plain objects.");
    const keys = Reflect.ownKeys(item);
    if (keys.length > TEXT_LIMIT)
      throw Error(`Text exceeds ${TEXT_LIMIT} characters.`);
    if (keys.some((k) => typeof k !== "string"))
      throw Error("JSON keys must be strings.");
    let names: string[];
    if (array) {
      if (item.length > TEXT_LIMIT || keys.length !== item.length + 1)
        throw Error("JSON arrays must be dense and have no extra properties.");
      names = Array.from({ length: item.length }, (_, i) => String(i));
    } else names = keys as string[];
    ancestors.add(item);
    append(array ? "[" : "{");
    for (const [index, key] of names.entries()) {
      const descriptor = Object.getOwnPropertyDescriptor(item, key);
      if (!descriptor?.enumerable || !("value" in descriptor))
        throw Error(
          "JSON requires enumerable data properties; no holes or accessors.",
        );
      append(`${index ? "," : ""}\n${"  ".repeat(depth + 1)}`);
      if (!array) append(`${quote(key)}: `);
      visit(descriptor.value, depth + 1);
    }
    if (names.length) append(`\n${"  ".repeat(depth)}`);
    append(array ? "]" : "}");
    ancestors.delete(item);
  }
  visit(value, 0);
  return chunks.join("");
}
export function panelText(input: {
  code?: unknown;
  value?: unknown;
  language?: unknown;
}): PanelText {
  try {
    const code = Object.hasOwn(input, "code"),
      value = Object.hasOwn(input, "value");
    if (code === value) throw Error("Provide exactly one of code or value.");
    if (value && input.language !== undefined)
      throw Error("JSON values use a fixed JSON label; omit language.");
    if (
      input.language !== undefined &&
      (typeof input.language !== "string" || !input.language.trim())
    )
      throw Error("language must be nonempty text.");
    if (code && typeof input.code !== "string")
      throw Error("code must be text.");
    const text = value ? jsonText(input.value) : (input.code as string);
    if (text.length > TEXT_LIMIT)
      throw Error(`Text exceeds ${TEXT_LIMIT} characters.`);
    return {
      text: text.replace(/\r\n?/g, "\n"),
      format: value ? "JSON" : (input.language as string | undefined) || "Text",
      error: null,
    };
  } catch (error) {
    return {
      text: "",
      format: "Text",
      error:
        error instanceof Error ? error.message : "Cannot display this value.",
    };
  }
}
