# Bartop arcade

Build notes for a RetroPie bartop (Raspberry Pi 4) plus its configuration as code.
The GitHub repo is **public**.

## Privacy rules (most important)

- Never put the owner's game names anywhere: not in the repo, commit messages, docs or chat.
  That includes ROM file names, short names (e.g. MAME/FBNeo set names) and titles.
  Use `<game>` / `<ROM>` placeholders in docs.
- Never print raw output that could contain game names (ROM folders, gamelists, raw logs,
  `all/emulators.cfg`, `retroarch-core-options.cfg` per-game lines, rpcfg "mentions ROM name"
  output). Print counts, or mask on the Pi first (as `troubleshooting/fetch-logs.sh` does).
  Masking only values is not enough: some config keys contain ROM names
  (e.g. `fbneo-dipswitch-<rom>-...`).
- Before showing new kinds of output, check it locally against
  `retropie-config/.local/rom-names.txt` and `game-titles.txt` and print only a hit count.
- Secrets stay in `retropie-config/.local/` (gitignored). Never commit it.

## Talking to the Pi

- SSH alias `retropie` (in `~/.ssh/config`, key `~/.ssh/id_retropi`, user `pi`).
  `python retropie-config/rpcfg.py ssh-check` diagnoses connection problems.
  If the name doesn't resolve, the Pi is usually just switched off: ask the user.
- From the Bash tool, if Git's ssh can't resolve `retropie.local`, use
  `/c/WINDOWS/System32/OpenSSH/ssh.exe`. In PowerShell, pipe scripts with
  `Get-Content -Raw script.sh | ssh retropie 'bash -s'` (no `<` redirect).
- The `pi` user has passwordless sudo. Read-only commands are fine to run.
  Anything that changes the Pi goes through `rpcfg.py push`, after the user agrees.

## Config workflow (`retropie-config/`, see its README)

`rpcfg.py pull` -> edit `files/` -> `rpcfg.py diff` -> `rpcfg.py push` (asks first, backs up;
`rpcfg.py restore` undoes) -> user tests on the cabinet -> commit.
`pull` refuses to overwrite uncommitted edits in `files/`.

## When something doesn't work

1. Ask the user for the on-screen error (a photo is fine).
2. Fetch logs right after the failed launch (they're in RAM, a reboot clears them):
   `ssh retropie 'bash -s' < troubleshooting/fetch-logs.sh`.
   The "Last launch" section shows the exact emulator command (core, `--subsystem`, config).
3. For core-level detail, temporarily enable verbose RetroArch logging for that system
   (see `troubleshooting/README.md`), push, relaunch, fetch logs, then revert.
4. Check `troubleshooting/` for known problems. Write up new fixes as
   `troubleshooting/<topic>/README.md` without game names, and link them from `troubleshooting/README.md`.

## Git

Work ends up on `master` (feature branches get merged into it). Don't push to GitHub unless asked.
