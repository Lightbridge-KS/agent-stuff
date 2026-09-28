---
name: explain-simple
description: >-
  Explain how an idea, design pattern, algorithm, or piece of logic works by
  distilling it into the smallest possible code example.
metadata:
  version: "2026-09-28"
---

Explain how the concept works using the simplest, most minimal code example possible.

- Write the example in a programming language (default: Python) unless the user specifies another.
- Keep only the code that demonstrates the core idea. Remove unrelated functionality or replace it with stubs.

The goal is understanding, not production readiness.

By default, write the output as a `/rich-document`. If the user specifies a different format or location, follow their instructions instead.