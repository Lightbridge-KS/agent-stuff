"""Validate the document profile, render in isolation, and publish artifacts."""
from __future__ import annotations

import copy
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
import uuid
import unicodedata
from urllib.parse import urlsplit

from markdown_it import MarkdownIt
import yaml

SKILL = Path(__file__).resolve().parent.parent
ASSETS = SKILL / "assets"
ENGINE_VERSION = "1.9.38"
VIEWER_VERSION = "2026-09-24"
MAX_SOURCE = 1_000_000
MAX_ASSET = 10_000_000
MAX_ASSETS = 20_000_000
MAX_HTML = 40_000_000
MAX_DIAGRAMS = 20
ID_PATTERN = re.compile(r"[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}\Z")


class Failure(Exception):
    def __init__(self, code: int, stage: str, message: str, location: str = "", **details):
        super().__init__(message)
        self.code = code
        self.result = {"status": "error", "stage": stage, "message": message, **details}
        if location:
            self.result["location"] = location


def invalid(message: str, location: str = "source") -> None:
    raise Failure(2, "validate", message, location)


def clean_env() -> dict[str, str]:
    """Do not inherit the caller's Quarto project/profile/tool overrides."""
    return {k: v for k, v in os.environ.items()
            if not k.startswith(("QUARTO_", "PANDOC_", "DENO_"))}


def command(args: list[str], *, cwd: Path, stdin: str | None = None, timeout: int = 120,
            warnings: list[str] | None = None) -> str:
    try:
        proc = subprocess.Popen(args, cwd=cwd, env=clean_env(), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=os.name != "nt")
        try:
            out, err = proc.communicate(stdin, timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name != "nt":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
            proc.communicate()
            raise Failure(4, "render", "Operation timed out; shorten the document or diagrams.")
    except OSError as exc:
        raise Failure(4, "dependency", f"Cannot run {args[0]}: {exc}") from exc
    if proc.returncode:
        raise Failure(4, "render", (err or out or "Engine failed")[-4000:])
    if err.strip():
        message = err.strip()[-4000:]
        print(message, file=sys.stderr)
        if warnings is not None:
            warnings.append(message)
    return out


def engine(work: Path) -> str:
    executable = shutil.which("quarto")
    if not executable:
        raise Failure(4, "dependency", f"Install Quarto {ENGINE_VERSION} and put quarto on PATH.")
    version = command([executable, "--version"], cwd=work).strip()
    if version != ENGINE_VERSION:
        raise Failure(4, "dependency", f"Quarto {version} is not verified; this profile requires {ENGINE_VERSION}.")
    return executable


class StrictLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            invalid("YAML aliases are unsupported; write literal metadata values.", "frontmatter")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                invalid("Metadata keys must be unique strings.", "frontmatter")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def metadata(text: str) -> tuple[dict, str, int]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        invalid("Add YAML frontmatter with a title.", "line 1")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        invalid("Close YAML frontmatter with ---.", "line 1")
    try:
        meta = yaml.load("".join(lines[1:end]), Loader=StrictLoader)
    except yaml.YAMLError as exc:
        invalid(f"Fix YAML frontmatter: {str(exc)[:400]}", "frontmatter")
    if not isinstance(meta, dict):
        invalid("Frontmatter must be a mapping with a title.", "frontmatter")
    unknown = set(meta) - {"title", "subtitle", "form", "assets"}
    if unknown:
        invalid(f"Unsupported metadata: {', '.join(sorted(unknown))}. The renderer owns Quarto configuration.", "frontmatter")
    for key in ("title", "subtitle"):
        if key == "title" or key in meta:
            if not isinstance(meta.get(key), str) or not meta[key].strip() or len(meta[key]) > 300:
                invalid(f"{key} must be a nonempty string of at most 300 characters.", key)
            if any(s in meta[key] for s in ("<", ">", "{{", "[", "]", "`", "$", "\\")):
                invalid("Use plain text in titles and subtitles.", key)
    art = meta.get("form", {})
    if not isinstance(art, dict) or set(art) - {"version", "layout"}:
        invalid("form accepts only version and layout.", "form")
    if type(art.get("version", 1)) is not int or art.get("version", 1) != 1 or art.get("layout", "article") != "article":
        invalid("Use form.version: 1 and layout: article.", "form")
    declarations = meta.get("assets", {})
    if not isinstance(declarations, dict) or len(declarations) > 20:
        invalid("assets must map at most 20 IDs to relative image paths.", "assets")
    return meta, "".join(lines[end + 1:]), end + 1


def normalize_fences(body: str, offset: int) -> str:
    """Markdown-it preserves fence spelling that Pandoc's AST normalizes away."""
    lines = body.splitlines(keepends=True)
    for token in MarkdownIt().parse(body):
        if token.type != "fence":
            continue
        info = token.info.strip()
        if info == "{ask}":
            lines[token.map[0]] = lines[token.map[0]].replace("{ask}", "{.aq-question}", 1)
        elif info == "{mermaid}":
            start = token.map[0]
            lines[start] = lines[start].replace("{mermaid}", "{.mermaid}", 1)
        elif info and not re.fullmatch(r"[A-Za-z0-9_+.-]{1,40}", info):
            invalid("Use an ordinary language fence for code, or {mermaid} for a diagram; executable cells and fence options are unsupported.", f"line {offset + token.map[0] + 1}")
    return "".join(lines)


def resolve_assets(meta: dict, source: Path) -> dict[str, Path]:
    result = {}
    total = 0
    for asset_id, relative in meta.get("assets", {}).items():
        location = f"assets.{asset_id}"
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", asset_id):
            invalid("Use a lowercase asset ID beginning with a letter.", location)
        if not isinstance(relative, str) or Path(relative).is_absolute():
            invalid("Use an image path relative to the source directory.", location)
        path = (source.parent / relative).resolve()
        if not path.is_relative_to(source.parent.resolve()) or not path.is_file():
            invalid("Image must exist within the source directory; escaping paths/symlinks are unsupported.", location)
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            invalid("Use PNG, JPEG, or WebP; SVG and remote assets are unsupported.", location)
        size = path.stat().st_size
        total += size
        if size > MAX_ASSET or total > MAX_ASSETS:
            invalid("Limit each image to 10 MB and total assets to 20 MB.", location)
        with path.open("rb") as stream:
            header = stream.read(16)
        signatures = {".png": header.startswith(b"\x89PNG\r\n\x1a\n"),
                      ".jpg": header.startswith(b"\xff\xd8\xff"),
                      ".jpeg": header.startswith(b"\xff\xd8\xff"),
                      ".webp": header.startswith(b"RIFF") and header[8:12] == b"WEBP"}
        if not signatures[path.suffix.lower()]:
            invalid("Image bytes do not match its extension.", location)
        result[asset_id] = path
    return result


PLAIN_NODES = {"Str", "Space", "SoftBreak", "LineBreak", "Emph", "Strong", "Strikeout",
               "Quoted", "DoubleQuote", "SingleQuote",
               "Para", "Plain", "BlockQuote", "BulletList", "OrderedList", "HorizontalRule",
               "Table", "Figure", "AlignLeft", "AlignRight", "AlignCenter", "AlignDefault", "ColWidthDefault",
               "ColWidth", "DefaultStyle", "Decimal", "LowerRoman", "UpperRoman", "LowerAlpha",
               "UpperAlpha", "DefaultDelim", "Period", "OneParen", "TwoParens"}


def check_attr(attr: list, location: str, *, classes: set[str] | None = None, keys: set[str] | None = None):
    ident, found, pairs = attr
    if ident and (len(ident) > 101 or not ident[0].isalpha()
                  or any(not (ch.isalnum() or ch in "_.:-" or unicodedata.category(ch).startswith("M")) for ch in ident)):
        invalid("Use a simple heading/block ID.", location)
    if ident.startswith(("aq-", "rd-")):
        invalid("IDs beginning aq- or rd- are reserved for the form viewer.", location)
    if set(found) - (classes or set()) or len(found) != len(set(found)):
        invalid(f"Unsupported classes: {found}.", location)
    if len(dict(pairs)) != len(pairs) or set(dict(pairs)) - (keys or set()):
        invalid(f"Unsupported attributes: {dict(pairs)}.", location)


def validate_tree(ast: dict, assets: dict[str, Path]) -> list[str]:
    diagrams = []

    def walk(value, location="blocks", context="main"):
        if isinstance(value, list):
            if (len(value) == 3 and isinstance(value[0], str) and isinstance(value[1], list)
                    and all(isinstance(c, str) for c in value[1]) and isinstance(value[2], list)
                    and all(isinstance(p, list) and len(p) == 2 for p in value[2])):
                check_attr(value, location)
                return
            for i, child in enumerate(value):
                walk(child, f"{location}[{i}]", context)
            return
        if not isinstance(value, dict):
            return
        kind, content = value.get("t"), value.get("c")
        if kind == "CodeBlock":
            attr, code = content
            if "aq-question" in attr[1]:
                invalid("Questions belong in the main flow, outside layouts and quotations.", location)
            check_attr(attr, location, classes=set(attr[1]))
            if attr[0] or len(attr[1]) > 1 or any(not re.fullmatch(r"[A-Za-z0-9_+.-]{1,40}", s) for s in attr[1]):
                invalid("Code accepts one language and no ID/options.", location)
            if attr[1] == ["mermaid"]:
                if context == "callout":
                    invalid("Place diagrams outside callouts.", location)
                if len(code) > 30_000 or len(diagrams) >= MAX_DIAGRAMS:
                    invalid("Limit diagrams to 30 KB each and 20 per document.", location)
                if re.search(r"\{\{|%%\{|(?:^|;)\s*(?:---|click\b|link\b|style\b|classDef\b|linkStyle\b)|<[A-Za-z/!]", code, re.M):
                    invalid("Mermaid accepts diagram content only; remove directives, HTML, links, and custom styles.", location)
                diagrams.append(code)
            return  # Literal code must never be inspected as active content.
        if kind == "Code":
            check_attr(content[0], location)
            return
        if kind == "Div":
            attr, children = content
            allowed = {"panel-tabset", "columns", "column", "callout-note", "callout-tip", "callout-warning"}
            check_attr(attr, location, classes=allowed, keys={"collapse", "width"})
            if len(attr[1]) != 1:
                invalid("Each div needs exactly one supported semantic class.", location)
            name, props = attr[1][0], dict(attr[2])
            if name == "panel-tabset":
                if context != "main" or props:
                    invalid("Tabsets belong in the main article and accept no options.", location)
                heads = [n for n in children if n.get("t") == "Header"]
                if not 2 <= len(heads) <= 6 or not children or children[0].get("t") != "Header" or len({h["c"][0] for h in heads}) != 1:
                    invalid("Use 2–6 same-level headings, starting immediately inside the tabset.", location)
                walk(children, location + ".tabs", "tab")
            elif name == "columns":
                if context != "main" or props or len(children) != 2 or any(n.get("t") != "Div" or n["c"][0][1] != ["column"] for n in children):
                    invalid("Columns require exactly two column divs in the main article.", location)
                walk(children, location + ".columns", "columns")
            elif name == "column":
                if context != "columns" or set(props) - {"width"} or props.get("width", "50%") != "50%":
                    invalid("Use width=50% inside a two-column div.", location)
                walk(children, location + ".column", "column")
            else:
                if context not in {"main", "tab", "column"} or set(props) - {"collapse"} or props.get("collapse", "false") not in {"true", "false"}:
                    invalid("Callouts accept collapse=true/false and cannot nest layouts.", location)
                walk(children, location + ".callout", "callout")
            return
        if kind == "Header":
            check_attr(content[1], location)
        elif kind in {"Link", "Image"}:
            check_attr(content[0], location)
            target = content[2][0]
            if kind == "Image":
                if not target.startswith("asset:") or target[6:] not in assets or not content[1]:
                    invalid("Images need alt text and a declared asset:<id> reference.", location)
                asset_id = target[6:]
                content[2][0] = f"assets/{asset_id}{assets[asset_id].suffix.lower()}"
            else:
                parsed = urlsplit(target)
                if not (target.startswith("#") or (parsed.scheme in {"https", "http"} and parsed.netloc and not parsed.username)):
                    invalid("Links must be heading anchors or HTTP(S) URLs without credentials.", location)
        elif kind not in PLAIN_NODES:
            invalid(f"Unsupported Markdown node {kind}; use the documented source profile.", location)
        if kind == "Str" and ("{{" in content or "}}" in content):
            invalid("Quarto shortcodes are unsupported; show them inside code instead.", location)
        walk(content, location + ".content", context)

    walk(ast["blocks"])
    return diagrams


def mermaid_bundle(work: Path, quarto: str) -> Path:
    """Locate both parser and browser builds from the verified Quarto install."""
    paths = command([quarto, "--paths"], cwd=work).splitlines()
    if len(paths) == 2:
        directory = Path(paths[1]) / "formats/html/mermaid"
        if all((directory / name).is_file() for name in ("mermaid.js", "mermaid.min.js", "embed-mermaid.css")):
            return directory
    raise Failure(4, "dependency", "Cannot locate Quarto's bundled Mermaid files; reinstall the verified Quarto version.")


def parse_source(source: Path, work: Path, quarto: str) -> dict:
    from aq_form import validate_question
    if not source.is_file() or source.stat().st_size > MAX_SOURCE:
        invalid('Source must be an existing UTF-8 document no larger than 1 MB.')
    try:
        text = source.read_text(encoding='utf-8')
    except UnicodeError:
        invalid('Save the source as UTF-8.')
    meta, body, offset = metadata(text)
    normalized = normalize_fences(body, offset)
    assets = resolve_assets(meta, source)
    ast = json.loads(command([quarto, 'pandoc', '--from', 'markdown-yaml_metadata_block', '--to', 'json'], cwd=work, stdin=normalized))
    if ast.get('meta'):
        invalid('Metadata is allowed only in leading frontmatter.')
    questions, positions, lines, question_context = [], {}, {}, {}
    for token in MarkdownIt().parse(body):
        if token.type == 'fence' and token.info.strip() == '{ask}':
            lines.setdefault(token.content.rstrip('\n'), []).append(offset + token.map[0] + 1)
    for index, block in enumerate(ast['blocks']):
        if block.get('t') != 'CodeBlock' or block['c'][0][1] != ['aq-question']:
            continue
        code = block['c'][1]
        line = lines[code.rstrip('\n')].pop(0)
        location = f'line {line}'
        try:
            q = yaml.load(code, Loader=StrictLoader)
        except (yaml.YAMLError, Failure) as exc:
            invalid(f'Invalid question YAML: {exc}', location)
        errors = validate_question(q)
        if errors:
            invalid('; '.join(errors), location)
        if q['id'] in {v['id'] for v in questions}:
            invalid(f'Duplicate question ID {q["id"]}', location)
        q['_line'] = line
        questions.append(q)
        positions[index] = q
        ast['blocks'][index] = {'t': 'Para', 'c': [{'t': 'Str', 'c': 'AQPLACEHOLDER'}]}
    if not questions:
        invalid('Add at least one {ask} block in the main document.')
    diagrams = validate_tree(ast, assets)
    from aq_controls import control
    for index, q in positions.items():
        question_context[q['id']] = []
        children = [{'t': 'RawBlock', 'c': ['html', control(q)]}]
        snippets = [(None, q.get('help'))]
        for opt in q.get('options', []) + q.get('items', []):
            snippets.append((opt['label'], opt.get('detail')))
        for label, content in snippets:
            if not content:
                continue
            fragment = json.loads(command([quarto, 'pandoc', '--from', 'markdown-yaml_metadata_block', '--to', 'json'], cwd=work, stdin=normalize_fences(content, q['_line'])))
            if fragment.get('meta') or any(n.get('t') in {'Header', 'Div'} for n in fragment['blocks']):
                invalid('Question help/detail accepts prose, code, images and diagrams; put headings/layouts in main context.', f'line {q["_line"]}')
            diagrams.extend(validate_tree(fragment, assets))
            reading = command([quarto, 'pandoc', '--from', 'json', '--to', 'gfm-raw_html', '--wrap=none'], cwd=work, stdin=json.dumps(fragment))
            question_context[q['id']].append({'label': label, 'markdown': reading})
            if label:
                from html import escape
                children.append({'t': 'RawBlock', 'c': ['html', f'<details class="aq-detail"><summary>Detail: {escape(label)}</summary>']})
            children.extend(fragment['blocks'])
            if label:
                children.append({'t': 'RawBlock', 'c': ['html', '</details>']})
        ast['blocks'][index] = {'t': 'Div', 'c': [[f'aq-question-{q["id"]}', ['aq-question'], [['data-question', q['id']], ['tabindex', '-1']]], children]}
    if len(diagrams) > MAX_DIAGRAMS:
        invalid('Limit the document and all question details to 20 diagrams.')
    if diagrams:
        diagram_file = work / 'diagrams.json'
        diagram_file.write_text(json.dumps(diagrams))
        bundle = mermaid_bundle(work, quarto) / 'mermaid.js'
        checked = json.loads(command([quarto, 'run', str(ASSETS / 'check_mermaid.ts'), str(bundle), str(diagram_file)], cwd=work))
        for item in checked:
            if not item['valid']:
                invalid('Fix Mermaid syntax: ' + item['message'], f'diagram[{item["index"]}]')
    # Archive a readable context projection independently of presentation wrappers.
    transcript = copy.deepcopy(ast)
    slots = {q['id']: 'AQSLOT' + uuid.uuid4().hex for q in questions}
    for index, q in positions.items():
        transcript['blocks'][index] = {'t': 'Para', 'c': [{'t': 'Str', 'c': slots[q['id']]}]}
    def flatten(blocks):
        result = []
        for block in blocks:
            if block.get('t') == 'Div':
                result.extend(flatten(block['c'][1]))
            else:
                result.append(block)
        return result
    transcript['blocks'] = flatten(transcript['blocks'])
    context = command([quarto, 'pandoc', '--from', 'json', '--to', 'gfm-raw_html', '--wrap=none'], cwd=work, stdin=json.dumps(transcript))
    return {'meta': meta, 'body': body, 'text': text, 'ast': ast, 'assets': assets, 'diagrams': diagrams, 'questions': questions, 'context': context, 'slots': slots, 'question_context': question_context}


def canonical_body(document: dict, work: Path, quarto: str) -> tuple[str, dict]:
    ast = copy.deepcopy(document['ast'])
    literal_code = {'code': {}, 'diagrams': {}, 'html': {}}
    def rewrite(value):
        if isinstance(value, list):
            for child in value:
                rewrite(child)
        elif isinstance(value, dict):
            kind = value.get('t')
            if kind == 'RawBlock':
                key = 'AQHTML' + uuid.uuid4().hex
                literal_code['html'][key] = value['c'][1]
                value['t'], value['c'] = 'CodeBlock', [['', ['aq-owned'], []], key]
            elif kind == 'CodeBlock' and value['c'][0][1] == ['mermaid']:
                key = 'AQDIAGRAM' + uuid.uuid4().hex
                literal_code['diagrams'][key] = value['c'][1]
                value['c'] = [['', [], []], key]
            elif kind in {'CodeBlock', 'Code'}:
                key = 'AQCODE' + uuid.uuid4().hex
                literal_code['code'][key] = value['c'][1]
                value['c'][1] = key
            else:
                rewrite(value.get('c'))
    rewrite(ast['blocks'])
    body = command([quarto, 'pandoc', '--from', 'json', '--to', 'markdown', '--wrap=none'], cwd=work, stdin=json.dumps(ast))
    return body, literal_code


SNAPSHOT = '<script id="aq-snapshot" type="application/json">null</script>'


def audit_html(html: str) -> None:
    class Audit(HTMLParser):
        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag in {'iframe', 'object', 'embed', 'base'}:
                raise Failure(4, 'render', f'Unexpected active element: {tag}')
            if tag in {'script', 'img', 'source', 'audio', 'video', 'link'}:
                target = values.get('src', values.get('href', ''))
                if target and not target.startswith('data:'):
                    raise Failure(4, 'render', f'Unembedded resource: {tag}')
    Audit().feed(html)


def compile_form(source: Path, destination: Path) -> dict:
    from aq_controls import FOOTER
    with tempfile.TemporaryDirectory(prefix='ask-qmd-build-') as temp:
        work = Path(temp)
        quarto = engine(work)
        doc = parse_source(source.resolve(), work, quarto)
        (work / 'assets').mkdir()
        archived_meta = copy.deepcopy(doc['meta'])
        archived_meta['assets'] = {}
        hashes = {}
        for key, path in doc['assets'].items():
            relative = f'assets/{key}{path.suffix.lower()}'
            shutil.copyfile(path, work / relative)
            archived_meta['assets'][key] = relative
            hashes[relative] = hashlib.sha256((work / relative).read_bytes()).hexdigest()
        for name in ('theme.css', 'theme-dark.scss', 'viewer.css', 'viewer.js', 'form.css', 'form.js', 'restore-code.lua'):
            shutil.copyfile(ASSETS / name, work / name)
        diagram_script = ''
        if doc['diagrams']:
            bundle = mermaid_bundle(work, quarto)
            shutil.copyfile(bundle / 'mermaid.min.js', work / 'mermaid.min.js')
            theme = json.dumps((bundle / 'embed-mermaid.css').read_text()).replace('<', '\\u003c')
            diagram_script = f'<script type="application/json" id="rd-mermaid-theme">{theme}</script><script src="mermaid.min.js"></script>'
        form = {'version': 1, 'title': doc['meta']['title'], 'questions': [{k: v for k, v in q.items() if not k.startswith('_')} for q in doc['questions']], 'context': doc['context'], 'slots': doc['slots'], 'question_context': doc['question_context']}
        payload = json.dumps(form, ensure_ascii=False).replace('<', '\\u003c')
        owned = {'title': doc['meta']['title'], 'format': {'html': {
            'theme': {'light': 'cosmo', 'dark': ['cosmo', 'theme-dark.scss']},
            'respect-user-color-scheme': True, 'toc': True, 'toc-title': 'On this page',
            'embed-resources': True, 'code-copy': True, 'anchor-sections': True,
            'css': ['theme.css', 'viewer.css', 'form.css'],
            'include-after-body': {'text': FOOTER + f'<script id="aq-spec" type="application/json">{payload}</script>' + SNAPSHOT + diagram_script + '<script src="viewer.js"></script><script src="form.js"></script>'}}},
            'execute': {'enabled': False}, 'filters': ['restore-code.lua']}
        if 'subtitle' in doc['meta']:
            owned['subtitle'] = doc['meta']['subtitle']
        body, literals = canonical_body(doc, work, quarto)
        (work / 'literal-code.json').write_text(json.dumps(literals))
        (work / 'document.qmd').write_text('---\n' + yaml.safe_dump(owned, sort_keys=False) + '---\n\n' + body)
        (work / '_quarto.yml').write_text('project:\n  type: default\n')
        warnings = []
        command([quarto, 'render', 'document.qmd', '--to', 'html', '--no-execute', '--output', 'index.html', '--quiet'], cwd=work, warnings=warnings)
        html = work / 'index.html'
        if not html.is_file() or html.stat().st_size > MAX_HTML:
            raise Failure(4, 'render', 'HTML missing or exceeds 40 MB')
        audit_html(html.read_text())
        destination.mkdir(exist_ok=True)
        (destination / 'rendered').mkdir()
        shutil.copyfile(html, destination / 'rendered/index.html')
        shutil.copytree(work / 'assets', destination / 'assets')
        (destination / 'source.qmd').write_text('---\n' + yaml.safe_dump(archived_meta, sort_keys=False, allow_unicode=True) + '---\n' + doc['body'])
        (destination / 'form.json').write_text(json.dumps(form, ensure_ascii=False, indent=2) + '\n')
        return {'producer': 'ask-form-qmd', 'schema_version': 1, 'profile_version': 1, 'renderer': f'quarto {ENGINE_VERSION}', 'theme_version': VIEWER_VERSION, 'viewer_version': VIEWER_VERSION, 'assets': hashes, 'original_source_sha256': hashlib.sha256(doc['text'].encode()).hexdigest(), 'created': datetime.now(timezone.utc).isoformat(), 'warnings': warnings, 'provenance': json.loads((ASSETS / 'provenance.json').read_text())}
