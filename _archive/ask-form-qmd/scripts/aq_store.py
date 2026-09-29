"""Submitted ask records: immutable bundles with a Markdown completion marker."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import uuid

import yaml
from aq_document import Failure, SNAPSHOT, command


def check_id(ask_id):
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-z0-9-]+-[a-f0-9]{12}', ask_id):
        raise Failure(2, 'usage', 'Use an ask ID returned by ask or list.')


def new_id(title):
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:40].rstrip('-') or 'form'
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + slug + '-' + uuid.uuid4().hex[:12]


def archive_root():
    lb = shutil.which('lb') or shutil.which('lightbridge')
    if not lb:
        raise Failure(4, 'persist', 'Install lb on PATH to save forms, or explicitly use --no-save.')
    try:
        result = json.loads(command([lb, 'path', '--json'], cwd=Path.cwd()))
        config = Path(result['config'])
        if not config.is_absolute() or config.name != 'config.toml':
            raise ValueError('invalid config path')
        return config.parent / 'asks'
    except (KeyError, ValueError) as exc:
        raise Failure(4, 'persist', f'Cannot resolve Lightbridge state: {exc}') from exc


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fence(text, language=''):
    mark = '`' * max(3, 1 + max((len(s) for s in re.findall(r'`+', text)), default=0))
    return f'{mark}{language}\n{text}\n{mark}'


def transcript(form, result, manifest):
    ask_id = manifest['id']
    meta = {'title': form['title'], 'producer': 'ask-form-qmd', 'record_version': 1,
            'ask_id': ask_id, 'created': manifest['created'], 'submitted': manifest['submitted'],
            'status': 'submitted', 'bundle': f'_bundles/{ask_id}', 'duration_s': result['meta']['duration_s']}
    context = form['context']
    # Pandoc GFM escapes underscore in placeholder text.
    for q in form['questions']:
        value = result['answers'].get(q['id'], None)
        answer = 'Skipped' if q['id'] not in result['answers'] else value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        block = f'### {q["label"]}  `{q["id"]}`\n\n**Answer:**\n\n' + fence(answer)
        recommended = q.get('recommended')
        if recommended is not None:
            block += '\n\n**Recommended value:** ' + str(recommended)
        labels = [o['label'] for o in q.get('options', []) if o.get('recommended')]
        labels += [i['label'] + ': ' + i['recommended'] for i in q.get('items', []) if i.get('recommended')]
        if labels:
            block += '\n\n**Recommended:** ' + '; '.join(labels)
        if q.get('recommendation'):
            block += '\n\n**Recommendation:** ' + q['recommendation']
        if q['id'] in result['meta'].get('diverged', []):
            block += '\n\n**Diverged** from the recommendation.'
        if q['id'] in result['meta'].get('notes', {}):
            block += '\n\n**Note:**\n\n' + fence(result['meta']['notes'][q['id']])
        for content in form.get('question_context', {}).get(q['id'], []):
            if content['label']:
                block += '\n\n**' + content['label'] + ':**'
            block += '\n\n' + content['markdown']
        marker = form.get('slots', {}).get(q['id'], 'AQANSWER_' + q['id'])
        context = context.replace(marker.replace('_', '\\_'), block).replace(marker, block)
    context = context.replace('](assets/', f'](_bundles/{ask_id}/assets/')
    out = '---\n' + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True) + '---\n\n# ' + form['title'] + '\n\n' + context
    if result['meta'].get('comments'):
        out += '\n\n## Comments\n\n' + fence(result['meta']['comments'])
    out += '\n\n## Raw\n\n' + fence(json.dumps({'form': form, 'result': result}, ensure_ascii=False, indent=2), 'json') + '\n'
    return out


def prepare(bundle, result, manifest):
    """Freeze the read-only rendering and all data; never persist a session capability."""
    manifest = copy.deepcopy(manifest)
    manifest.update({'id': result['meta']['ask_id'], 'title': json.loads((bundle / 'form.json').read_text())['title'],
                     'submitted': datetime.now(timezone.utc).isoformat(), 'saved': True})
    frozen = copy.deepcopy(result)
    for key in ('saved', 'bundle', 'save_error'):
        frozen['meta'].pop(key, None)
    (bundle / 'result.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + '\n')
    html_path = bundle / 'rendered/index.html'
    html = html_path.read_text()
    if html.count(SNAPSHOT) != 1:
        raise Failure(4, 'persist', 'Rendered form snapshot marker is missing or duplicated.')
    snapshot = json.dumps({'mode': 'review', 'result': frozen}, ensure_ascii=False).replace('<', '\\u003c')
    html_path.write_text(html.replace(SNAPSHOT, f'<script id="aq-snapshot" type="application/json">{snapshot}</script>'))
    manifest['files'] = {str(p.relative_to(bundle)): digest(p) for p in sorted(bundle.rglob('*')) if p.is_file() and p.name != 'manifest.json'}
    manifest['html_sha256'] = manifest['files']['rendered/index.html']
    form = json.loads((bundle / 'form.json').read_text())
    record = transcript(form, frozen, manifest)
    manifest['record_sha256'] = hashlib.sha256(record.encode()).hexdigest()
    (bundle / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return record


def verify_bundle(bundle, *, record=None):
    try:
        if bundle.is_symlink():
            raise ValueError('bundle is a symlink')
        manifest = json.loads((bundle / 'manifest.json').read_text())
        check_id(manifest['id'])
        if manifest.get('producer') != 'ask-form-qmd' or manifest.get('schema_version') != 1:
            raise ValueError('unsupported archive format')
        files = manifest['files']
        if not {'source.qmd', 'form.json', 'result.json', 'rendered/index.html'} <= files.keys():
            raise ValueError('incomplete bundle')
        for relative, expected in files.items():
            target = bundle / relative
            if Path(relative).is_absolute() or target.is_symlink() or not target.resolve().is_relative_to(bundle.resolve()) or digest(target) != expected:
                raise ValueError(f'hash/path mismatch: {relative}')
        if digest(bundle / 'rendered/index.html') != manifest['html_sha256']:
            raise ValueError('HTML hash mismatch')
        if record is not None and (record.is_symlink() or digest(record) != manifest['record_sha256']):
            raise ValueError('record hash mismatch')
        return manifest
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise Failure(4, 'persist', f'Archive is incomplete or modified: {exc}') from exc


def save(bundle, result, manifest, *, root=None, staged=False, stage_timeout=120):
    root = root if root is not None else archive_root()
    ask_id = result['meta']['ask_id']
    record_text = prepare(bundle, result, manifest)
    destination = root / '_bundles' / ask_id
    record = root / (ask_id + '.md')
    if staged:
        source_record = bundle.parent / (ask_id + '.md')
        source_record.write_text(record_text)
        abort = bundle.parent / 'abort-save'
        request = {'source_bundle': str(bundle), 'source_record': str(source_record), 'destination_bundle': str(destination), 'destination_record': str(record), 'manifest_sha256': digest(bundle / 'manifest.json'), 'record_sha256': digest(source_record), 'abort': str(abort)}
        print('ASK_QMD_SAVE_REQUEST ' + json.dumps(request), file=sys.stderr, flush=True)
        deadline = time.monotonic() + stage_timeout
        while time.monotonic() < deadline and not abort.exists():
            if destination.is_dir() and record.is_file():
                if digest(destination / 'manifest.json') != request['manifest_sha256']:
                    raise Failure(4, 'persist', 'Staged manifest copy differs from source.')
                verify_bundle(destination, record=record)
                break
            time.sleep(.1)
        else:
            raise Failure(4, 'persist', 'Staged save aborted or timed out; answers are retained.')
    else:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination.parent.mkdir(exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix='.staging-', dir=root) as temporary:
            stage = Path(temporary)
            shutil.copytree(bundle, stage / 'bundle')
            (stage / 'record.md').write_text(record_text)
            verify_bundle(stage / 'bundle', record=stage / 'record.md')
            # Exclusive reservation avoids overwriting an existing bundle even on ID collision.
            destination.mkdir()
            for child in (stage / 'bundle').iterdir():
                child.rename(destination / child.name)
            os.link(stage / 'record.md', record)  # exclusive atomic completion marker
        verify_bundle(destination, record=record)
    result['meta'].update({'saved': str(record), 'bundle': str(destination)})


def read_bundle(ask_id, root=None):
    check_id(ask_id)
    root = root if root is not None else archive_root()
    bundle = root / '_bundles' / ask_id
    manifest = verify_bundle(bundle, record=root / (ask_id + '.md'))
    if manifest['id'] != ask_id:
        raise Failure(4, 'persist', 'Bundle ID mismatch')
    return bundle


def inventory(limit=10):
    root = archive_root()
    items = []
    for record in sorted(root.glob('*.md'), reverse=True):
        bundle = root / '_bundles' / record.stem
        if not (bundle / 'manifest.json').is_file():
            continue
        try:
            manifest = verify_bundle(bundle, record=record)
            items.append({'ask_id': manifest['id'], 'title': manifest['title'], 'submitted': manifest['submitted'], 'record': str(record)})
        except Failure:
            continue
        if len(items) == limit:
            break
    return {'items': items}
