"""Owned native HTML controls. Every source string crosses HTML escaping here."""
from html import escape

from aq_form import DEFAULT_DECISIONS


def e(value):
    return escape(str(value), quote=True)


def input_tag(kind, name, **attrs):
    fields = {'type': kind, 'name': name, 'form': 'aq-form', **attrs}
    return '<input ' + ' '.join(f'{e(k.replace("_", "-"))}="{e(v)}"' for k, v in fields.items() if v is not None) + '>'


def control(q):
    key, kind = q['id'], q['type']
    label = e(q['label'])
    required = ' <span class="aq-required">Required</span>' if q.get('required') else ''
    out = f'<fieldset class="aq-controls"><legend>{label}{required}</legend>'
    if q.get('recommendation'):
        out += f'<p class="aq-recommendation">Recommendation: {e(q["recommendation"])}</p>'
    if kind in {'single_select', 'multi_select'}:
        for opt in q['options']:
            badge = ' <span class="aq-badge">Recommended</span>' if opt.get('recommended') else ''
            out += '<label class="aq-option">' + input_tag('radio' if kind == 'single_select' else 'checkbox', key, value=opt['value']) + f'<span>{e(opt["label"])}{badge}'
            if opt.get('description'):
                out += f'<small>{e(opt["description"])}</small>'
            out += '</span></label>'
        if q.get('allow_other', True):
            out += '<label class="aq-option">' + input_tag('radio' if kind == 'single_select' else 'checkbox', key, value='__other__') + '<span>Other</span></label>'
            out += input_tag('text', 'other:' + key, placeholder='Your own answer', aria_label=f'Other answer for {q["label"]}')
        if kind == 'multi_select':
            out += f'<small>Choose {q.get("min", 0)}–{q.get("max", "any")} options.</small>'
    elif kind in {'scale', 'number'}:
        attrs = {k: q[k] for k in ('min', 'max', 'step') if k in q}
        attrs['step'] = q.get('step', 1 if kind == 'scale' else 'any')
        attrs['aria_label'] = q['label']
        if kind == 'scale':
            attrs['value'] = q['min']
        out += input_tag('range' if kind == 'scale' else 'number', key, **attrs)
        if kind == 'scale':
            out += f'<output id="aq-output-{e(key)}">Unanswered — move the slider</output>'
            if q.get('labels'):
                out += '<p>' + ' · '.join(f'{e(k)}: {e(v)}' for k, v in q['labels'].items()) + '</p>'
        if 'recommended' in q:
            out += f'<small>Recommended: {e(q["recommended"])}</small>'
        if q.get('unit'):
            out += f'<small>{e(q["unit"])}</small>'
    elif kind in {'short_text', 'long_text'}:
        if kind == 'short_text':
            out += input_tag('text', key, maxlength=q.get('max_length'), placeholder=q.get('placeholder', ''), aria_label=q['label'])
        else:
            out += f'<textarea form="aq-form" name="{e(key)}" aria-label="{label}" placeholder="{e(q.get("placeholder", ""))}" rows="4"></textarea>'
    elif kind == 'ranking':
        out += f'<ol data-ranking="{e(key)}">'
        for opt in q['options']:
            out += f'<li data-value="{e(opt["value"])}"><span>{e(opt["label"])}</span><button type="button" data-move="up" aria-label="Move {e(opt["label"])} up">↑</button><button type="button" data-move="down" aria-label="Move {e(opt["label"])} down">↓</button></li>'
        out += '</ol><label>' + input_tag('checkbox', 'confirm:' + key) + ' Use this order</label>'
    elif kind == 'matrix':
        out += '<div class="aq-table"><table><thead><tr><th>Item</th>' + ''.join(f'<th>{e(c["label"])}</th>' for c in q['columns']) + '</tr></thead><tbody>'
        for row in q['rows']:
            out += f'<tr><th scope="row">{e(row["label"])}</th>'
            for col in q['columns']:
                out += '<td>' + input_tag('radio', key + '.' + row['value'], value=col['value'], aria_label=f'{row["label"]}: {col["label"]}') + '</td>'
            out += '</tr>'
        out += '</tbody></table></div>'
    elif kind == 'review':
        for item in q['items']:
            name = key + '.' + item['id']
            out += f'<label class="aq-review">{e(item["label"])}<select form="aq-form" name="{e(name)}"><option value="">Choose a decision</option>' + ''.join(f'<option value="{e(d)}">{e(d)}</option>' for d in q.get('decisions', DEFAULT_DECISIONS)) + '</select></label>'
            if item.get('description'):
                out += f'<p>{e(item["description"])}</p>'
            if item.get('recommended'):
                out += f'<small>Recommended: {e(item["recommended"])}</small>'
            if q.get('comment', True):
                out += input_tag('text', 'comment:' + key + ':' + item['id'], placeholder='Optional comment', aria_label=f'Comment on {item["label"]}')
    out += f'<details class="aq-note"><summary>Add a note</summary><textarea form="aq-form" name="note:{e(key)}" aria-label="Note for {label}" rows="2"></textarea></details></fieldset>'
    out += f'<p id="aq-error-{e(key)}" class="aq-error" role="alert"></p><div class="aq-recorded" hidden></div>'
    return out


FOOTER = '''<form id="aq-form"></form>
<div id="aq-comments"><label for="aq-comments-input">Overall comments</label><textarea form="aq-form" id="aq-comments-input" name="form:comments" rows="3"></textarea></div>
<footer id="aq-footer"><span id="aq-progress"></span><button type="button" id="aq-cancel">Cancel</button><button type="submit" form="aq-form" id="aq-submit">Send answers</button></footer>
<p id="aq-status" role="status" aria-live="polite">This archived page is read-only until a collecting session is started.</p>
<noscript>JavaScript is required to answer this form.</noscript>'''
