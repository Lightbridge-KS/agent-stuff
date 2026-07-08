# Python conventions (pinned)

Python 3.10+. Only my divergences from defaults — everything else, standard knowledge applies.

## Interfaces: ABC with `I*` prefix

Default to `abc.ABC` + `@abstractmethod`, named `IPatientRepository`-style. Use `typing.Protocol` **only** for code I don't control (third-party, retrofitting) or where duck typing is genuinely acceptable.

## What gets injected

```
VOLATILE → inject          │ STABLE → direct use
───────────────────────────┼──────────────────────────────
Runtime env (DB, API, fs,  │ stdlib (datetime, pathlib, …)
network); needs mocking;   │ well-known stable libs
non-stdlib lib that churns │ (numpy/pandas in data context)
```

Constructor injection is the default; method injection when the dependency varies per call. Composition root (`main.py`) only at Full tier.

## Value objects: **ask**

Two sanctioned styles — ask which, per project:

- **(A)** `@dataclass(frozen=True, slots=True)` + `__post_init__` validation — stdlib, lightweight
- **(B)** Pydantic `BaseModel` (`frozen=True`) + `field_validator` — validation + serialization built in, adds the dependency

## Type hints

Built-in generics (`list[str]`), `X | None` over `Optional[X]` — per global Python conventions.
