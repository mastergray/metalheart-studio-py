# Repository instructions

These instructions apply to the entire repository.

## Before changing Python

Read the canonical style guide in full:

`/home/mastergray/claymoretechgroup/github/projects/ctg-spec-ops/code-styles/python-code-style.md`

New production Python must follow that guide, including its camelCase naming, class ordering, import comments, type annotations, and Hindley–Milner-inspired signature comments. Do not apply PEP-8 naming rules that conflict with it.

This repository targets the machine's Python 3.8 series. Where the canonical guide requires Python 3.10 annotation syntax, preserve its typing intent using Python 3.8-compatible `typing` forms such as `List`, `Dict`, `Optional`, and `Union`. Do not introduce `X | Y`, `list[X]`, or other syntax/runtime APIs unavailable on Python 3.8.

`ref/` is immutable reference material. Do not reformat it or include it in production lint, type, style, or coverage gates.

## Before Git or GitHub setup changes

Read:

`/home/mastergray/aleph-null-media/prompts/ctg-github-practices.md`

Adapt it for the personal `mastergray` account as documented in `docs/development-standards.md`. Keep the default branch as `main`, use repository-local identity, and do not add or push a remote unless the user supplies or approves the repository destination.

## Verification

Follow the test levels and acceptance requirements in section 14 of `docs/metalheart-studio-spec.md`. New behavior requires focused tests at the cheapest suitable level. Rendering, timing, cache, and mux changes require integration coverage.
