# Repository Guidelines

## Project Structure & Module Organization

Follow the chosen framework's layout. Suggested directories are `src/` for application code, `tests/` for tests, `assets/` for static resources, and `docs/` for documentation. Create directories only when needed and describe the actual structure in `README.md`.

## Build, Test, and Development Commands

Document prerequisites and exact installation, run, build, and test commands in `README.md`. Keep them synchronized with scripts and configuration. Run relevant checks before committing; report any checks that could not run.

## Development Approach

Act as a senior developer. Follow DRY, KISS, pragmatic SOLID, and YAGNI: avoid duplication, keep solutions simple, justify abstractions, and implement only what is needed. Develop using the trace method. Ask questions to clarify requirements, assumptions, and consequential design decisions.

Use only the latest stable versions of technologies. Before writing code, consult official documentation for the exact version being used. Verify stable releases rather than relying on remembered APIs or outdated examples.

## Coding Style & Naming Conventions

Follow language conventions and configure formatting and linting with the first source files. Use consistent indentation, descriptive names, and modules with a single responsibility. Avoid unrelated formatting changes.

## Testing Guidelines

Use TDD: write a failing test, implement the minimum code to pass it, then refactor while keeping tests green. Test thoroughly, including boundary values, unexpected or invalid inputs, empty values, and error paths. Add regression tests for bug fixes. Document the runner and any coverage requirements; name tests after observable behavior.

## Graphical Interface Design

Minimize whitespace while preserving readability and usability. Before implementing a graphical interface, show the user a visual mockup or design preview. Obtain agreement on the design before building the interface.

## Commit & Pull Request Guidelines

Commit and push every meaningful, validated change to the configured remote. Use focused commits with imperative subjects such as `Add project configuration`. Pull requests should explain the purpose, link relevant issues, report validation and setup changes, and include screenshots for interface changes.

## Documentation, Releases & Persistent Instructions

Maintain the README and project wiki as the project evolves. Publish release pages for meaningful milestones, with version tags, changes, validation results, and known limitations. Clearly distinguish documentation milestones from runnable application releases.

Add every user suggestion and instruction to this file, consolidating overlapping rules. Keep guidance general and reusable; exclude repository URLs.
