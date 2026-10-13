# Development Standards

This document records how the project's external engineering standards apply locally. It is a pointer and enforcement summary, not a replacement for the canonical documents.

## Python

Canonical source:

`/home/mastergray/claymoretechgroup/github/projects/ctg-spec-ops/code-styles/python-code-style.md`

All new production Python follows that document. The most consequential conventions are:

- camelCase methods rather than PEP-8 snake_case;
- underscore-prefixed camelCase instance attributes;
- `UPPERCASE_WITH_UNDERSCORES` module constants;
- prescribed class member ordering and section headings;
- no module docstrings; use a single-line module comment;
- a purpose comment on every import;
- complete parameter and return annotations using Python 3.8-compatible syntax;
- Hindley–Milner-inspired signature comments for every method;
- an `init` class factory where applicable;
- immutable defaults and `from __future__ import annotations` for forward references.

### Python 3.8 adaptation

The deployment target is this machine's Python 3.8.10 runtime. That runtime requirement overrides only the canonical guide's Python 3.10 syntax examples; the guide's naming, structure, typing intent, and documentation rules remain binding.

Use `typing.List`, `typing.Dict`, `typing.Tuple`, `typing.Optional`, and `typing.Union` rather than PEP 585 built-in generics or PEP 604 `|` unions. Avoid standard-library APIs added after Python 3.8 unless a project dependency supplies an intentional compatibility layer. Static analysis is configured for Python 3.8.

Tool configuration and repository-owned style tests must enforce these rules without enabling contradictory PEP-8 naming checks.

The `ref/` tree is historical/reference material and is exempt. Production code derived from it must be brought into compliance as it is extracted rather than reformatting the reference snapshots.

## Testing

Section 14 of [the product and technical specification](metalheart-studio-spec.md) is the testing source of truth. It defines unit, integration, visual, and slow/end-to-end levels; generated audio fixtures; deterministic visual baselines; synchronization checks; coverage targets; and style enforcement.

## Git and GitHub

Canonical source:

`/home/mastergray/aleph-null-media/prompts/ctg-github-practices.md`

This is a personal project, so CTG organization-specific values are adapted as follows:

| Practice | Metalheart value |
|---|---|
| Owner | `mastergray` |
| Repository name | `metalheart-studio-py` |
| Python distribution | `metalheart-studio` |
| Python import package | `metalheart` |
| Local Git identity | `mastergray <me@mastergray.com>` |
| Default branch | `main` |
| SSH host alias | `github-mastergray` |
| Future remote | `git@github-mastergray:mastergray/metalheart-studio-py.git` |

No remote repository exists yet. Local initialization must not add a guessed remote or create a GitHub repository. Before the first push, verify branch, local author identity, working tree, commit authors, and the explicitly chosen remote URL.

Commit messages use a short summary line, followed by a blank line and details when useful. Do not add automated `Co-Authored-By` trailers.
