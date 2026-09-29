#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer==0.19.2", "PyYAML==6.0.3", "markdown-it-py==4.0.0", "jsonschema==4.25.1"]
# ///
"""Constrained Quarto documents that collect one human decision record."""
from pathlib import Path
import json
import tempfile

import typer
from aq_document import ASSETS, Failure, compile_form, engine, parse_source
from aq_form import SCHEMA
from aq_session import collect, launch
from aq_store import inventory, read_bundle
import aq_viewer

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
ENTRY = Path(__file__).resolve()


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


@app.command()
def example():
    """Print a supported .qmd exercising all nine answer types."""
    print((ASSETS / 'example.qmd').read_text(), end='')


@app.command()
def schema():
    """Print versioned question and source/result contracts."""
    emit({'source_profile': {'version': 1, 'required': ['title'], 'metadata': ['title', 'subtitle', 'form', 'assets'],
                            'question_fence': '{ask}', 'questions_in': 'main flow only',
                            'rich_blocks': ['prose', 'code', 'mermaid', 'panel-tabset', 'columns', 'callout', 'image']},
          'question': SCHEMA, 'result': {'status': ['submitted', 'cancelled', 'timeout'],
          'answers': 'Object keyed by question ID; see source.md for each type',
          'meta': ['ask_id', 'duration_s', 'skipped', 'other', 'notes', 'comments', 'diverged', 'saved', 'bundle', 'save_error']}})


@app.command()
def validate(source: Path, json_output: bool = typer.Option(False, '--json')):
    """Validate without opening a browser or publishing a record."""
    with tempfile.TemporaryDirectory(prefix='ask-qmd-validate-') as temp:
        work = Path(temp)
        doc = parse_source(source.expanduser().resolve(), work, engine(work))
        result = {'status': 'valid', 'questions': [q['id'] for q in doc['questions']], 'required': [q['id'] for q in doc['questions'] if q.get('required')]}
    emit(result) if json_output else print(f'Valid: {len(result["questions"])} questions')


@app.command()
def ask(source: Path, no_open: bool = False, no_save: bool = False,
        timeout: float | None = typer.Option(None, min=0.001), stage_save: bool = False):
    """Render, wait for Send/Cancel, and return exactly one result JSON."""
    if no_save and stage_save:
        raise Failure(2, 'usage', '--no-save and --stage-save are mutually exclusive.')
    with tempfile.TemporaryDirectory(prefix='ask-qmd-session-') as temp:
        bundle = Path(temp) / 'bundle'
        manifest = compile_form(source.expanduser().resolve(), bundle)
        result = collect(bundle, manifest, no_save=no_save, no_open=no_open, timeout=timeout, staged=stage_save)
        emit(result)
        if result['status'] != 'submitted':
            raise typer.Exit(1)


@app.command('list')
def list_records(limit: int = typer.Option(10, min=1, max=100), json_output: bool = typer.Option(False, '--json')):
    """List this producer's completed asks for the invocation project."""
    result = inventory(limit)
    if json_output:
        emit(result)
    else:
        for item in result['items']:
            print(f'{item["ask_id"]}  {item["title"]}')


@app.command('open')
def open_record(ask_id: str, no_open: bool = False):
    """Reopen the frozen context and submitted answers, read-only."""
    result = aq_viewer.start(read_bundle(ask_id), ENTRY)
    if not no_open and not launch(result['url']):
        result['warnings'].append('Browser launch failed; open the returned URL.')
    emit(result)


@app.command()
def stop(ask_id: str):
    """Stop the read-only viewer, preserving the saved record."""
    emit(aq_viewer.stop(ask_id))


@app.command()
def serve(ask_id: str):
    """Foreground read-only viewer for harness background runners."""
    aq_viewer.serve(read_bundle(ask_id), guard_startup=True)


@app.command('_serve', hidden=True)
def serve_internal(bundle: Path):
    aq_viewer.serve(bundle)


if __name__ == '__main__':
    try:
        app()
    except Failure as exc:
        emit(exc.result)
        raise SystemExit(exc.code)
    except (OSError, UnicodeError) as exc:
        emit({'status': 'error', 'stage': 'io', 'message': str(exc)})
        raise SystemExit(4)
