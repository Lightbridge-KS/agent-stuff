import assert from "node:assert/strict";
import test from "node:test";
import { jsonText, panelText, TEXT_LIMIT } from "../code/text.ts";

test("JSON is deterministic, exact and never drops or coerces non-JSON values", () => {
  const value = {
    b: 17,
    a: [null, true, 1.23456789012345, "<script>literal</script>"],
  };
  assert.equal(jsonText(value), JSON.stringify(value, null, 2));
  assert.equal(jsonText(null), "null");
  assert.equal(jsonText([]), "[]");
  assert.equal(jsonText({}), "{}");
  for (const invalid of [
    undefined,
    () => 0,
    Symbol("s"),
    1n,
    NaN,
    Infinity,
    new Date(),
    Array(1),
    { a: undefined },
    { a: NaN },
  ])
    assert.throws(() => jsonText(invalid));
  const cycle = {};
  cycle.self = cycle;
  assert.throws(() => jsonText(cycle), /cycle/);
  const shared = { a: 1 };
  assert.equal(
    jsonText([shared, shared]),
    JSON.stringify([shared, shared], null, 2),
  );
  let invoked = false;
  const getter = {
    get a() {
      invoked = true;
      return 1;
    },
  };
  assert.throws(() => jsonText(getter), /accessor/);
  assert.equal(invoked, false);
  assert.throws(() => jsonText({ [Symbol("s")]: 1 }), /keys/);
  assert.throws(
    () => jsonText(Object.defineProperty({}, "hidden", { value: 1 })),
    /enumerable/,
  );
  const extra = [1];
  extra.note = "x";
  assert.throws(() => jsonText(extra), /extra/);
  const hole = Array(3);
  hole[0] = 1;
  hole[2] = 3;
  hole.extra = "x";
  assert.throws(() => jsonText(hole));
  const plain = Object.create(null);
  Object.defineProperty(plain, "__proto__", {
    value: "literal",
    enumerable: true,
  });
  assert.equal(jsonText(plain), '{\n  "__proto__": "literal"\n}');
});
test("source/JSON limits fail visibly without truncation or stale text", () => {
  assert.equal(
    panelText({ code: "x".repeat(TEXT_LIMIT) }).text.length,
    TEXT_LIMIT,
  );
  assert.match(
    panelText({ code: "x".repeat(TEXT_LIMIT + 1) }).error,
    /exceeds/,
  );
  assert.match(panelText({ value: "\\".repeat(TEXT_LIMIT) }).error, /exceeds/);
  let nested = 0;
  for (let i = 0; i < 12; i++) nested = [nested];
  assert.equal(panelText({ value: nested }).error, null);
  assert.match(panelText({ value: [nested] }).error, /nesting/);
  assert.deepEqual(panelText({ code: "a\r\nb\rc", language: "Python" }), {
    text: "a\nb\nc",
    format: "Python",
    error: null,
  });
  for (const input of [
    {},
    { code: "a", value: null },
    { value: null, language: "JSON" },
    { code: 3 },
    { value: undefined },
  ]) {
    assert(panelText(input).error);
    assert.equal(panelText(input).text, "");
  }
});
