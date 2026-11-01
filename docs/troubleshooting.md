# Troubleshooting

Problems met while building the project, added as soon as each one is solved.

Format for each entry:

```
## Short title
- **Symptom:** what was seen, with the exact error if short.
- **Cause:** why it happened.
- **Fix:** what solved it.
```

## Creating a virtual environment fails in WSL
- **Symptom:** `python3 -m venv .venv` stops with `ensurepip is not available`.
- **Cause:** Ubuntu ships the part of venv that installs pip as a separate package, and it was not installed.
- **Fix:** `sudo apt install -y python3.12-venv`, then create the venv again.

## `sudo` fails from the Claude Code `!` prefix
- **Symptom:** `sudo: a terminal is required to read the password`.
- **Cause:** the `!` prefix runs the command without a terminal, so `sudo` cannot ask for the password.
- **Fix:** run `sudo` commands in a separate WSL terminal.
