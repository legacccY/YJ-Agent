# Contributing to HPC Companion

Thanks for your interest in improving HPC Companion. This document covers how to report bugs, propose features, and submit code changes.

---

## Reporting a Bug

Open an issue using the **Bug Report** template. Please include:

- Your OS (Windows / macOS / Linux) and version
- Python version and how you installed it (Anaconda, system Python, venv, etc.)
- HPC Companion version or commit hash
- Steps to reproduce
- What you expected vs. what actually happened
- Relevant error messages or tracebacks (paste as text, not screenshots)

For connection issues, include the SLURM version on your cluster if you know it (`sinfo --version`).

---

## Requesting a Feature

Open an issue using the **Feature Request** template. Describe the workflow you are trying to accomplish and why the current tool does not cover it.

---

## Submitting a Pull Request

### 1. Fork and clone

```bash
git clone https://github.com/<your-fork>/hpc-companion.git
cd hpc-companion
```

### 2. Set up the development environment

Python 3.10 or later is required.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Run the test suite

The tests in `tests/` cover the SLURM parsing and script-generation logic. They do not require a real cluster or a display server.

```bash
python -m pytest tests/ -q
```

All five tests should pass before you open a PR.

### 4. Code style

- Follow the existing style in each file (PEP 8, type hints where the surrounding code uses them).
- Keep each function focused. The `core/` modules are pure functions by design — avoid adding side effects or GUI imports there.
- If you add new parsing or generation logic, add a corresponding test in `tests/test_slurm.py`.

### 5. Commit and push

```bash
git checkout -b fix/short-description
# make your changes
git add <files>
git commit -m "fix: short description of what changed"
git push origin fix/short-description
```

Then open a pull request against `main`. Fill in the PR description with what you changed and why.

---

## Project Layout

```
main.py              Entry point
core/
  config.py          App-wide paths, constants, and cluster presets
  profiles.py        Profile CRUD and keyring password storage
  ssh_client.py      paramiko SSH/SFTP wrapper (thread-safe)
  slurm.py           squeue/scontrol/sinfo parsing + sbatch generation (pure functions)
  worker.py          QThreadPool async executor
ui/
  theme.py           Dark/light QSS themes
  app_context.py     Shared SSH connection and status signal
  main_window.py     Tab shell and top status bar
  connection_panel.py  Connection and profile management
  jobs_panel.py      Job monitor (table, logs, GPU curve)
  transfer_panel.py  SFTP dual-pane file transfer
  submit_panel.py    Job submission wizard
tests/
  test_slurm.py      Pure-function unit tests (no HPC, no display)
docs/
  使用教程.md         Chinese user guide with screenshots
```

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
