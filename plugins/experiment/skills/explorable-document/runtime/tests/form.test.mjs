import assert from "node:assert/strict";
import test from "node:test";
import { readNumber } from "../form/number.ts";
import { optionsError } from "../form/options.ts";

test("numeric drafts distinguish empty, unfinished, invalid and complete zero", () => {
  assert.deepEqual(readNumber(""), {
    status: "empty",
    value: null,
    error: null,
  });
  assert.equal(readNumber("  ", { required: true }).status, "empty");
  assert(readNumber("", { required: true }).error);
  for (const text of ["-", "+", ".", "-.", "1e", "1e-", ".5E+"])
    assert.equal(readNumber(text).status, "incomplete", text);
  for (const text of [
    "12x",
    "1,000",
    "NaN",
    "Infinity",
    "0x10",
    "1+2",
    "1/2",
    "e",
    "1e309",
  ])
    assert.equal(readNumber(text).status, "invalid", text);
  for (const [text, value] of [
    ["0", 0],
    ["  +.5  ", 0.5],
    ["1.", 1],
    ["-2.5", -2.5],
    ["1e3", 1000],
  ]) {
    assert.equal(readNumber(text).status, "valid");
    assert.equal(readNumber(text).value, value);
  }
});
test("numeric rules reject unsafe integers and invalid bounds without coercion", () => {
  const rules = { integer: true, min: 0, max: 1000000 };
  for (const text of ["2.5", "-1", "1000001", "9007199254740992"])
    assert.equal(readNumber(text, rules).status, "invalid", text);
  assert.equal(readNumber("1e6", rules).value, 1000000);
  assert.equal(
    readNumber("9007199254740992", "2.0000000000000001", "1e-999", {
      integer: true,
    }).status,
    "invalid",
  );
  assert.equal(readNumber("1.1", { min: 1, max: 1.1 }).value, 1.1);
  for (const rules of [
    { min: 2, max: 1 },
    { min: NaN },
    { max: Infinity },
    { integer: "yes" },
    null,
  ])
    assert.equal(readNumber("2", rules).status, "invalid");
  assert.equal(readNumber(0).status, "invalid");
});
test("option catalogs diagnose stale and duplicate values; null remains unselected", () => {
  const choices = [{ value: "a", label: "Alpha", disabled: true }];
  assert.equal(optionsError(choices, "a", 12), null);
  assert.equal(optionsError(choices, null, 12), null);
  assert.equal(optionsError([], null, 12), null);
  assert.match(optionsError(choices, "missing", 12), /not in/);
  assert.match(optionsError([...choices, ...choices], null, 12), /unique/);
  assert.match(
    optionsError([{ value: "", label: "Empty" }], null, 12),
    /nonempty/,
  );
  assert.match(optionsError(Array(13).fill(choices[0]), null, 12), /at most/);
});
