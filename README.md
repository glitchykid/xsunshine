# XSunshine

XSunshine is in the repository setup stage. This milestone establishes contributor guidance, project documentation, and the release process. Application requirements and the technology stack have not yet been defined.

## Current status

- Contributor requirements are recorded in [AGENTS.md](AGENTS.md).
- The [project wiki](https://github.com/glitchykid/xsunshine/wiki) covers development and publishing.
- [Release pages](https://github.com/glitchykid/xsunshine/releases) record published milestones.
- Application code, a graphical interface, automated tests, and executable downloads are not available yet.

## Getting started

Git is the only prerequisite for this documentation milestone.

```sh
git clone https://github.com/glitchykid/xsunshine.git
cd xsunshine
```

Read [AGENTS.md](AGENTS.md) before making changes. There are no dependency installation, build, local run, or test commands yet. Add exact prerequisites and commands here when the application toolchain is introduced.

## Repository structure

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | General contributor and agent instructions, including user requirements. |
| `README.md` | Project status, setup, and documentation entry point. |
| `docs/releases/` | Versioned release notes used for GitHub release pages. |

The wiki has its own Git repository; see the [development guide](https://github.com/glitchykid/xsunshine/wiki/Development).

## Contributing

Follow the development, testing, and interface approval requirements in [AGENTS.md](AGENTS.md). Validate each meaningful change, commit it, and push it to the configured remote. Update the README and wiki when behavior or setup changes, and publish release notes for meaningful milestones.

For documentation changes, review Markdown rendering, check links and stated commands, and run `git diff --check`. Application changes will require the test suite established with the implementation.

## Releases

The initial `v0.1.0` milestone contains documentation only. See its [release notes](docs/releases/v0.1.0.md) for scope and validation, and the wiki's [release guide](https://github.com/glitchykid/xsunshine/wiki/Releases) for the publishing process.
