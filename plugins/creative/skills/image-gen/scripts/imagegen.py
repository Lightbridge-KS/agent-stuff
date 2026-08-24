#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.60", "typer>=0.12"]
# ///
"""Deterministic CLI for OpenAI gpt-image-2 — the shell an agent drives.

Three verbs, three jobs:

    generate  one-shot text -> image           (Image API, cheapest)
    iterate   multi-turn refinement session    (Responses API, previous_response_id chain)
    edit      transform existing local images  (Image API edits: masks, references)

Reads OPENAI_API_KEY from the environment — inject it via `lb key run`, never inline.
Image bytes go only to --out; stdout carries a one-line summary or --json metadata.

Exit codes: 0 ok · 2 fix the request (validated before spending money) ·
3 moderation/user error — rewrite the prompt, don't retry · 4 auth/quota/network.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from contextlib import ExitStack
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    help=__doc__,
)

EXIT_PARAMS = 2  # request invalid — fix parameters and rerun
EXIT_BLOCKED = 3  # moderation / image_generation_user_error — rewrite, don't retry
EXIT_AUTH = 4  # auth, quota, rate limit, or network — environment problem

DEFAULT_MODEL = "gpt-image-2"
DEFAULT_DRIVER = "gpt-5.6"  # mainline model carrying the image_generation tool

# gpt-image-2 size constraints (validated locally before any API spend)
MAX_EDGE = 3840
MIN_PIXELS = 655_360
MAX_PIXELS = 8_294_400
MAX_RATIO = 3
EDGE_MULTIPLE = 16

BULK_LIMIT = 4  # refuse -n above this without --allow-bulk


class Quality(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    auto = "auto"


class Background(str, Enum):
    auto = "auto"
    transparent = "transparent"
    opaque = "opaque"


class Format(str, Enum):
    png = "png"
    jpeg = "jpeg"
    webp = "webp"


class Action(str, Enum):
    auto = "auto"
    generate = "generate"
    edit = "edit"


def fail(code: int, message: str) -> None:
    """Print a teaching error to stderr and exit with a stable code."""
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code)


def validate_size(size: str) -> None:
    """Enforce gpt-image-2 size constraints locally (exit 2 on violation)."""
    if size == "auto":
        return
    try:
        w_s, h_s = size.lower().split("x")
        w, h = int(w_s), int(h_s)
    except ValueError:
        fail(EXIT_PARAMS, f"--size '{size}' is not 'auto' or WIDTHxHEIGHT (e.g. 1536x1024)")
        return
    problems = []
    if w % EDGE_MULTIPLE or h % EDGE_MULTIPLE:
        problems.append(f"both edges must be multiples of {EDGE_MULTIPLE}px")
    if max(w, h) > MAX_EDGE:
        problems.append(f"max edge is {MAX_EDGE}px")
    if max(w, h) > MAX_RATIO * min(w, h):
        problems.append(f"edge ratio must not exceed {MAX_RATIO}:1")
    if not MIN_PIXELS <= w * h <= MAX_PIXELS:
        problems.append(f"total pixels must be within {MIN_PIXELS:,}–{MAX_PIXELS:,}")
    if problems:
        fail(EXIT_PARAMS, f"--size {size} violates gpt-image-2 constraints: " + "; ".join(problems))


def validate_output_opts(
    background: Background, fmt: Format, compression: Optional[int], n: int, allow_bulk: bool
) -> None:
    if background is Background.transparent and fmt is Format.jpeg:
        fail(EXIT_PARAMS, "transparent background needs --format png or webp (jpeg has no alpha)")
    if compression is not None:
        if fmt is Format.png:
            fail(EXIT_PARAMS, "--compression applies only to --format jpeg or webp")
        if not 0 <= compression <= 100:
            fail(EXIT_PARAMS, "--compression must be 0–100")
    if n < 1:
        fail(EXIT_PARAMS, "-n must be at least 1")
    if n > BULK_LIMIT and not allow_bulk:
        fail(
            EXIT_PARAMS,
            f"-n {n} exceeds {BULK_LIMIT} images (paid API). Pass --allow-bulk to confirm, "
            "and consider --quality low for bulk runs",
        )


def require_key() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        fail(
            EXIT_AUTH,
            "OPENAI_API_KEY is not set. Never paste a key — inject it per invocation:\n"
            "  lb key run openai-image-gen -- uv run <skill_dir>/scripts/imagegen.py ...",
        )


def _client():
    """Build the OpenAI client (isolated seam so tests can mock it)."""
    from openai import OpenAI

    return OpenAI()


def api_fail(exc: Exception) -> None:
    """Map an OpenAI SDK exception onto the exit-code contract."""
    import openai

    if isinstance(exc, openai.APIConnectionError):
        fail(
            EXIT_AUTH,
            "cannot reach api.openai.com — in a sandboxed shell this host is usually not "
            "allowlisted; rerun as a user-approved non-sandboxed command",
        )
    if isinstance(
        exc, (openai.AuthenticationError, openai.PermissionDeniedError, openai.RateLimitError)
    ):
        fail(EXIT_AUTH, f"{exc.__class__.__name__}: {exc}")
    if isinstance(exc, openai.APIStatusError):
        body = getattr(exc, "body", None) or {}
        err = body.get("error", body) if isinstance(body, dict) else {}
        code = err.get("code", "")
        etype = err.get("type", "")
        if code == "moderation_blocked" or etype == "image_generation_user_error":
            detail = json.dumps(err.get("moderation_details")) if err.get("moderation_details") else ""
            fail(
                EXIT_BLOCKED,
                f"request blocked ({code or etype}): {err.get('message', exc)}\n"
                f"{detail}\nRewrite the prompt or change the input images — do not retry as-is",
            )
        fail(EXIT_PARAMS, f"API rejected the request: {err.get('message', exc)}")
    raise exc


def write_images(b64_list: list[str], out: Path) -> list[Path]:
    """Decode base64 payloads to --out (numbered suffixes when more than one)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if len(b64_list) == 1:
        targets = [out]
    else:
        targets = [out.with_stem(f"{out.stem}_{i + 1}") for i in range(len(b64_list))]
    for target, b64 in zip(targets, b64_list):
        target.write_bytes(base64.b64decode(b64))
    return targets


def usage_dict(usage: Any) -> Optional[dict]:
    if usage is None:
        return None
    return {
        k: v
        for k in ("input_tokens", "output_tokens", "total_tokens")
        if (v := getattr(usage, k, None)) is not None
    }


def emit(as_json: bool, payload: dict, summary: str) -> None:
    print(json.dumps(payload, indent=2) if as_json else summary)


# ── shared option annotations ──────────────────────────────────────────────

OutOpt = Annotated[Path, typer.Option("--out", "-o", help="Output image path (bytes go here, never stdout).")]
SizeOpt = Annotated[str, typer.Option(help="'auto' or WIDTHxHEIGHT; edges ×16, ≤3840px, ratio ≤3:1.")]
QualityOpt = Annotated[Quality, typer.Option(help="low ≈ $0.005/img (drafts, bulk) · medium · high (finals).")]
BackgroundOpt = Annotated[Background, typer.Option(help="'transparent' needs png/webp.")]
FormatOpt = Annotated[Format, typer.Option("--format", "-f", help="png (default) · jpeg (fastest) · webp.")]
CompressionOpt = Annotated[Optional[int], typer.Option(help="0–100, jpeg/webp only.")]
JsonOpt = Annotated[bool, typer.Option("--json", help="Emit metadata JSON instead of the summary line.")]


@app.command()
def generate(
    prompt: Annotated[str, typer.Argument(help="Image prompt: scene → subject → details → constraints.")],
    out: OutOpt,
    size: SizeOpt = "auto",
    quality: QualityOpt = Quality.medium,
    background: BackgroundOpt = Background.auto,
    fmt: FormatOpt = Format.png,
    compression: CompressionOpt = None,
    n: Annotated[int, typer.Option("-n", help="Images per request (>4 needs --allow-bulk).")] = 1,
    allow_bulk: Annotated[bool, typer.Option("--allow-bulk", help=f"Confirm -n above {BULK_LIMIT}.")] = False,
    model: Annotated[str, typer.Option(help="Image model.")] = DEFAULT_MODEL,
    as_json: JsonOpt = False,
) -> None:
    """One-shot text -> image via the Image API (cheapest path)."""
    validate_size(size)
    validate_output_opts(background, fmt, compression, n, allow_bulk)
    require_key()
    kwargs: dict[str, Any] = dict(
        model=model, prompt=prompt, size=size, quality=quality.value,
        background=background.value, output_format=fmt.value, n=n,
    )
    if compression is not None:
        kwargs["output_compression"] = compression
    try:
        result = _client().images.generate(**kwargs)
    except Exception as exc:  # mapped onto the exit-code contract
        api_fail(exc)
    paths = write_images([d.b64_json for d in result.data], out)
    payload = {
        "op": "generate", "paths": [str(p) for p in paths], "size": size,
        "quality": quality.value, "model": model, "usage": usage_dict(getattr(result, "usage", None)),
    }
    emit(as_json, payload, f"wrote {', '.join(map(str, paths))} ({size}, {quality.value}, {model})")


@app.command()
def edit(
    prompt: Annotated[str, typer.Argument(help="What to change; state what must be preserved.")],
    out: OutOpt,
    inputs: Annotated[list[Path], typer.Option("--input", "-i", help="Input image(s); repeat for references.")],
    mask: Annotated[Optional[Path], typer.Option(help="PNG mask: transparent areas get replaced (applies to the first input).")] = None,
    size: SizeOpt = "auto",
    quality: QualityOpt = Quality.medium,
    background: BackgroundOpt = Background.auto,
    fmt: FormatOpt = Format.png,
    compression: CompressionOpt = None,
    n: Annotated[int, typer.Option("-n", help="Variants per request (>4 needs --allow-bulk).")] = 1,
    allow_bulk: Annotated[bool, typer.Option("--allow-bulk", help=f"Confirm -n above {BULK_LIMIT}.")] = False,
    model: Annotated[str, typer.Option(help="Image model.")] = DEFAULT_MODEL,
    as_json: JsonOpt = False,
) -> None:
    """Transform existing local image(s) via the Image API edits endpoint."""
    validate_size(size)
    validate_output_opts(background, fmt, compression, n, allow_bulk)
    for p in [*inputs, *([mask] if mask else [])]:
        if not p.is_file():
            fail(EXIT_PARAMS, f"input file not found: {p}")
    require_key()
    try:
        with ExitStack() as stack:
            files = [stack.enter_context(open(p, "rb")) for p in inputs]
            kwargs: dict[str, Any] = dict(
                model=model, prompt=prompt, image=files, size=size, quality=quality.value,
                background=background.value, output_format=fmt.value, n=n,
            )
            if mask:
                kwargs["mask"] = stack.enter_context(open(mask, "rb"))
            if compression is not None:
                kwargs["output_compression"] = compression
            result = _client().images.edit(**kwargs)
    except Exception as exc:
        api_fail(exc)
    paths = write_images([d.b64_json for d in result.data], out)
    payload = {
        "op": "edit", "paths": [str(p) for p in paths], "size": size,
        "quality": quality.value, "model": model, "usage": usage_dict(getattr(result, "usage", None)),
    }
    emit(as_json, payload, f"wrote {', '.join(map(str, paths))} ({size}, {quality.value}, {model})")


@app.command()
def iterate(
    prompt: Annotated[str, typer.Argument(help="First turn: full prompt. Later turns: one refinement at a time.")],
    out: OutOpt,
    session: Annotated[Path, typer.Option(help="Session sidecar JSON — created if absent, else continued.")],
    size: SizeOpt = "auto",
    quality: QualityOpt = Quality.medium,
    background: BackgroundOpt = Background.auto,
    fmt: FormatOpt = Format.png,
    compression: CompressionOpt = None,
    action: Annotated[Action, typer.Option(help="Tool behavior: auto (model decides) · generate · edit.")] = Action.auto,
    driver_model: Annotated[Optional[str], typer.Option(help=f"Mainline model carrying the tool (default {DEFAULT_DRIVER}; continuations reuse the session's).")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Multi-turn refinement via the Responses API (chained by previous_response_id).

    The tool selects its own GPT Image model; costs add driver-model tokens on top
    of image tokens — use for assets that earn refinement, not for bulk.
    """
    validate_size(size)
    validate_output_opts(background, fmt, compression, n=1, allow_bulk=False)
    previous_id = None
    sess: dict[str, Any] = {"driver_model": driver_model or DEFAULT_DRIVER, "turns": []}
    if session.exists():
        try:
            sess = json.loads(session.read_text())
            previous_id = sess["turns"][-1]["response_id"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            fail(EXIT_PARAMS, f"session file {session} is not a valid imagegen session — "
                              "point --session at a fresh path to start over")
        if driver_model:
            sess["driver_model"] = driver_model
    require_key()
    tool: dict[str, Any] = {
        "type": "image_generation", "quality": quality.value, "size": size,
        "background": background.value, "output_format": fmt.value,
    }
    if compression is not None:
        tool["output_compression"] = compression
    if action is not Action.auto:
        tool["action"] = action.value
    try:
        response = _client().responses.create(
            model=sess["driver_model"], input=prompt,
            **({"previous_response_id": previous_id} if previous_id else {}),
            tools=[tool],
        )
    except Exception as exc:
        api_fail(exc)
    calls = [o for o in response.output if getattr(o, "type", "") == "image_generation_call"]
    if not calls:
        texts = [
            part.text
            for o in response.output if getattr(o, "type", "") == "message"
            for part in getattr(o, "content", []) if getattr(part, "type", "") == "output_text"
        ]
        fail(EXIT_BLOCKED, "driver model returned no image. It said:\n"
                           + ("\n".join(texts) or "(no text)")
                           + "\nRephrase the prompt or force --action generate")
    paths = write_images([c.result for c in calls], out)
    revised = getattr(calls[0], "revised_prompt", None)
    sess["turns"].append({
        "prompt": prompt, "response_id": response.id, "output": str(paths[0]),
        "revised_prompt": revised, "quality": quality.value, "size": size,
    })
    session.parent.mkdir(parents=True, exist_ok=True)
    session.write_text(json.dumps(sess, indent=2) + "\n")
    payload = {
        "op": "iterate", "turn": len(sess["turns"]), "paths": [str(p) for p in paths],
        "size": size, "quality": quality.value, "driver_model": sess["driver_model"],
        "response_id": response.id, "revised_prompt": revised,
        "usage": usage_dict(getattr(response, "usage", None)),
    }
    emit(as_json, payload,
         f"wrote {paths[0]} (turn {len(sess['turns'])}, {quality.value}, session {session})")


if __name__ == "__main__":
    app()
