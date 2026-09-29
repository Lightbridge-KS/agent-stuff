"""Question semantics and authoritative answer validation; no rendering dependencies."""
from __future__ import annotations

import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA = json.loads((Path(__file__).resolve().parent.parent / 'assets/question.schema.json').read_text())
VALIDATOR = Draft202012Validator(SCHEMA)
TYPES = {s['properties']['type']['const'] for s in SCHEMA['oneOf']}
DEFAULT_DECISIONS = ['approve', 'revise', 'reject']


def number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def aligned(value, q):
    step = q.get('step', 1 if q['type'] == 'scale' else None)
    if step is None:
        return True
    units = (value - q.get('min', 0)) / step
    return math.isfinite(units) and math.isclose(units, round(units), abs_tol=1e-8, rel_tol=0)


def validate_question(q):
    errors = list(VALIDATOR.iter_errors(q))
    if errors:
        # Select the matching type's schema for a useful field diagnostic.
        match = next((s for s in SCHEMA['oneOf'] if isinstance(q, dict) and s['properties']['type']['const'] == q.get('type')), None)
        error = next(Draft202012Validator(match).iter_errors(q), errors[0]) if match else errors[0]
        return [f"{'.'.join(map(str, error.path)) or 'question'}: {error.message}"]
    out = []
    for key in ('min', 'max', 'step', 'recommended'):
        if key in q and not number(q[key]):
            out.append(f'{key} must be finite')
    for key in ('options', 'rows', 'columns', 'items'):
        if key in q:
            values = [o['id' if key == 'items' else 'value'] for o in q[key]]
            if any(not v.strip() or v != v.strip() for v in values):
                out.append(f'{key} identifiers must be nonblank with no surrounding whitespace')
            if len(set(values)) != len(values):
                out.append(f'{key} identifiers must be unique')
            if '__other__' in values:
                out.append('__other__ is reserved for free text')
    if 'min' in q and 'max' in q and q['min'] > q['max']:
        out.append('min must not exceed max')
    if q['type'] == 'multi_select':
        if q.get('min', 0) > len(q['options']) + int(q.get('allow_other', True)):
            out.append('min cannot exceed available options plus one Other answer')
        if q.get('required') and q.get('max', 1) < 1:
            out.append('required multi_select must allow at least one answer')
    if 'recommended' in q and not out:
        value = q['recommended']
        if value < q.get('min', -math.inf) or value > q.get('max', math.inf) or not aligned(value, q):
            out.append('recommended must satisfy range and step')
    if q['type'] == 'review':
        decisions = q.get('decisions', DEFAULT_DECISIONS)
        if any(not d.strip() or d != d.strip() for d in decisions):
            out.append('decisions must be nonblank with no surrounding whitespace')
        if len(set(decisions)) != len(decisions):
            out.append('decisions must be unique')
        if any(i.get('recommended', decisions[0]) not in decisions for i in q['items']):
            out.append('recommended review decision must be in decisions')
    return out


def validate_answers(body, questions):
    """Return (field errors, normalized result fields); never trust browser validation."""
    qs = {q['id']: q for q in questions}
    errors = {}
    if not isinstance(body, dict) or set(body) - {'answers', 'other', 'notes', 'comments'}:
        return {'form': 'Expected answers, other, notes, and comments only'}, {}
    answers = body.get('answers')
    if not isinstance(answers, dict):
        return {'form': 'answers must be an object'}, {}
    other, notes, comments = body.get('other', []), body.get('notes', {}), body.get('comments', '')
    if not isinstance(other, list) or not all(isinstance(x, str) for x in other) or len(set(other)) != len(other):
        return {'form': 'other must be a unique list of question IDs'}, {}
    if not isinstance(notes, dict) or any(k not in qs or not isinstance(v, str) for k, v in notes.items()):
        return {'form': 'notes must map known question IDs to text'}, {}
    if not isinstance(comments, str):
        return {'form': 'comments must be text'}, {}
    for key in other:
        if key not in answers or key not in qs or qs[key]['type'] not in {'single_select', 'multi_select'} or not qs[key].get('allow_other', True):
            errors[key] = 'Other is not allowed for this answer'
    for key, q in qs.items():
        if q.get('required') and (key not in answers or answers[key] in ('', [], {})):
            errors[key] = 'An answer is required'
    for key, value in answers.items():
        if key not in qs:
            errors[key] = 'Unknown question ID'
            continue
        q, ok = qs[key], True
        kind = q['type']
        values = [o['value'] for o in q.get('options', [])]
        if kind == 'single_select':
            ok = isinstance(value, str) and bool(value.strip()) and (value in values or key in other)
        elif kind in {'multi_select', 'ranking'}:
            ok = isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)
            if ok:
                ok = len(set(value)) == len(value)
                unknown = set(value) - set(values)
                if kind == 'ranking':
                    ok = ok and sorted(value) == sorted(values)
                else:
                    ok = ok and (not unknown or key in other and len(unknown) == 1)
                    ok = ok and q.get('min', 0) <= len(value) <= q.get('max', math.inf)
        elif kind in {'scale', 'number'}:
            ok = number(value) and q.get('min', -math.inf) <= value <= q.get('max', math.inf) and aligned(value, q)
        elif kind in {'short_text', 'long_text'}:
            ok = isinstance(value, str) and bool(value.strip()) and len(value) <= q.get('max_length', 100_000)
        elif kind == 'matrix':
            rows, cols = {r['value'] for r in q['rows']}, {c['value'] for c in q['columns']}
            ok = isinstance(value, dict) and all(r in rows and isinstance(c, str) and c in cols for r, c in value.items())
            if ok and q.get('required'):
                ok = set(value) == rows
        elif kind == 'review':
            items, decisions = {i['id'] for i in q['items']}, q.get('decisions', DEFAULT_DECISIONS)
            ok = isinstance(value, dict) and all(i in items and isinstance(v, dict) and not set(v) - {'decision', 'comment'} and v.get('decision') in decisions and isinstance(v.get('comment', ''), str) for i, v in value.items())
            if ok and q.get('required'):
                ok = set(value) == items
        if not ok:
            errors[key] = f'Answer must satisfy {kind} choices, bounds, and completeness'
    extras = {'other': other, 'notes': {k: v.strip() for k, v in notes.items() if v.strip()}, 'comments': comments.strip(),
              'skipped': [k for k in qs if k not in answers], 'diverged': []}
    if not errors:
        for key, value in answers.items():
            q = qs[key]
            rec = q.get('recommended')
            if q['type'] in {'single_select', 'multi_select'}:
                opts = [o['value'] for o in q['options'] if o.get('recommended')]
                if opts and (value != opts[0] if q['type'] == 'single_select' else set(value) != set(opts)):
                    extras['diverged'].append(key)
            elif q['type'] == 'review':
                if any(i.get('recommended') and i['id'] in value and value[i['id']]['decision'] != i['recommended'] for i in q['items']):
                    extras['diverged'].append(key)
            elif rec is not None and value != rec:
                extras['diverged'].append(key)
    return errors, {'answers': answers, 'meta': extras}
