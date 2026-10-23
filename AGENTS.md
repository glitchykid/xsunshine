# Repository Guidelines

## Structure & Commands

Separate application code, tests, assets, and documentation following language conventions. Document the actual layout, prerequisites, and exact installation, run, build, lint, and test commands in `README.md`. Run relevant checks before committing and report anything not run.

## Development Approach

Act as a senior developer. Follow DRY, KISS, pragmatic SOLID, and YAGNI: avoid duplication, keep solutions simple, justify abstractions, and implement only what is needed. Ask questions to clarify requirements, assumptions, and consequential decisions.

Prioritize reliability and Windows usability in ongoing development. Use reproduced failures and small, tested improvements to guide the next increment.

Use tracer-bullet development from *The Pragmatic Programmer*: build a small working slice through all layers, validate it end to end, and extend it through feedback. Keep these slices as production code with tests and error handling. Diagnostic logging is a separate concern.

Use only the latest stable technologies. Before writing code, consult official documentation for the exact version used; verify current stable releases instead of relying on remembered APIs.

## Coding & Testing

Use consistent indentation, descriptive names, and modules with a single responsibility. Configure formatting and linting alongside the first implementation; avoid unrelated formatting changes.

Use TDD: write a failing test, implement the minimum passing code, then refactor with tests green. Test thoroughly, including boundary values, unexpected or invalid inputs, empty values, and error paths. Add regression tests for fixes. Name tests after observable behavior and document the runner and coverage requirements.

## Application Requirements

Build a Windows-focused terminal application. Choose technologies for platform fit and maintainability; Python with a PowerShell launcher is the selected approach.

Use colors to distinguish live terminal statuses. End each run with calculated totals and category breakdowns, including partial progress after interruption. Keep redirected output and diagnostic logs readable without color codes.

Recursively clean empty filesystem directories and registry keys throughout the system; registry cleanup is required. Process children before parents so newly empty parents are eligible immediately. Preserve files and registry values. Provide preview and explicit apply modes, retain scope roots, and report skipped or inaccessible objects. Test destructive behavior only in isolated fixtures.

## Graphical Interfaces

If a graphical interface is introduced, minimize whitespace while preserving readability and usability. Show a visual preview and obtain the user's agreement before implementation.

## Commits, Documentation & Releases

Commit and push every meaningful, validated change. Use focused, imperative subjects such as `Add cleanup command`. Pull requests should explain purpose, link issues, report validation and setup changes, and show screenshots for interface changes.

Maintain the README and wiki. Publish release pages for meaningful milestones with version tags, changes, validation, and limitations; distinguish documentation milestones from runnable releases.

Add every user suggestion and instruction to this file, consolidating overlapping rules. Keep guidance general and reusable; exclude repository URLs.
