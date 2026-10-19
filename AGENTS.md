# AGENTS.md

Instructions for any AI agent working on Form4Clean.

## Keep the code simple

Nothing here should read as AI-generated. Write it the way a good developer would by hand.

- Solve the problem asked, nothing more. No speculative abstractions, options, or future-proofing.
- Plain functions over class hierarchies. Standard library over a new dependency.
- Comments only where the code cannot explain itself. No docstrings that restate the name, no
  section banners, no step-by-step narration.
- No defensive boilerplate: do not validate what cannot happen or wrap everything in try/except.
- No emoji anywhere. No marketing adjectives in docs.
- Small, direct tests. Short, plain commit messages.
- If a change is growing, stop and cut rather than add.

The test: a stranger reading the diff should not think an AI wrote it.
