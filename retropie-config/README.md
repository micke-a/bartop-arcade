# RetroPie config as code

The arcade's RetroPie configuration, mirrored into git so changes can be made on the PC,
diffed, pushed to the Pi, and rolled back when an emulator breaks.

```
files/            mirror of the Pi's filesystem (files/opt/retropie/configs/... -> /opt/retropie/configs/...)
manifest.txt      which paths on the Pi are tracked
exclude.txt       what is never tracked (game lists, saves, per-game data, big stock assets)
redact-lines.txt  tracked files whose per-game lines stay on the Pi (e.g. FBNeo DIP switches)
secret-keys.txt   extra config keys to treat as secrets
rpcfg.py          ssh-check / pull / diff / push / restore / check
.local/           gitignored: Pi address, secret values, cached ROM names
```

Needs Python 3.9+ and `ssh` on the PC. Nothing extra is installed on the Pi.

## One-time setup

1. SSH key login, so you aren't asked for the password on every command. See [SSH setup](#ssh-setup).
2. Copy `pi.env.example` to `.local/pi.env`. Set `PI_HOST` to the `Host` alias from step 1
   (`retropie`), and `ROM_DIRS` if your ROMs live elsewhere. Then check the connection:
   ```
   python retropie-config/rpcfg.py ssh-check
   ```
3. Take the first snapshot and commit it as the "known state":
   ```
   python retropie-config/rpcfg.py pull
   git add retropie-config && git commit -m "Snapshot RetroPie config"
   ```

## SSH setup

Run these in PowerShell. Windows' built-in ssh is the one that works with the
Windows ssh-agent.

1. Create a key just for the cabinet (skip if `~/.ssh/id_retropi` exists). A passphrase is optional:
   ```
   ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\id_retropi -C bartop-arcade
   ```
2. Copy the **public** key to the Pi. This is the last time you type the Pi's password:
   ```
   type $env:USERPROFILE\.ssh\id_retropi.pub | ssh pi@retropie.local "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
   ```
   If `retropie.local` doesn't resolve, use the IP from RetroPie menu > Show IP. A DHCP
   reservation in your router keeps that IP from changing.
3. Tell ssh which key to use, in `%USERPROFILE%\.ssh\config` (no file extension):
   ```
   Host retropie
       HostName retropie.local
       User pi
       IdentityFile ~/.ssh/id_retropi
       IdentitiesOnly yes
   ```
   `PI_HOST` in `.local/pi.env` must be the alias (`retropie`). If it's the real hostname,
   ssh never applies this block. `IdentitiesOnly` stops ssh trying every other key first,
   which can make the Pi reject you for too many failed attempts.
4. If the key has a passphrase, load it into the agent once. First, in an *Administrator* PowerShell:
   ```
   Get-Service ssh-agent | Set-Service -StartupType Automatic; Start-Service ssh-agent
   ```
   Then in a normal PowerShell:
   ```
   ssh-add $env:USERPROFILE\.ssh\id_retropi
   ```
5. Verify: `python retropie-config/rpcfg.py ssh-check`

### ssh-check

`ssh-check` walks the connection one step at a time and stops at the first broken one,
with a hint for the fix:

| Step | Typical failure and fix |
|---|---|
| `.local/pi.env` present | copy `pi.env.example` |
| ssh client on PATH | Windows: Optional features > OpenSSH Client |
| effective ssh settings (`ssh -G`) | wrong key listed: `PI_HOST` doesn't match the `Host` alias |
| host name resolves | Pi off, or no mDNS: use the IP as `HostName` |
| port 22 answers | timeout: Pi off / wrong IP; refused: SSH disabled on the Pi |
| key login (password login disabled for the test) | host key changed after re-flash: `ssh-keygen -R <host>`; key refused: redo step 2 |
| Pi side: bash 4.4+, passwordless `sudo`, tar/base64/GNU find, `/opt/retropie/configs`, `ROM_DIRS` | what `pull` and `push` rely on |

It exits non-zero on any failure, so it can also gate other scripts. For deeper digging,
`ssh -v retropie` shows which keys are offered and why they're refused.

Once key login works, you can turn off SSH password login on the Pi. Keep a keyboard handy
as a fallback (F4 on the cabinet gives a terminal):
```
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config && sudo systemctl restart ssh
```

## Troubleshooting loop

```
python retropie-config/rpcfg.py pull       # get the Pi's current state; git diff shows what changed on the Pi
# edit files under files/ (or change things in the RetroPie menus, then pull again to capture them)
python retropie-config/rpcfg.py diff       # preview what push would change
python retropie-config/rpcfg.py push       # write changed files; backs up the originals on the Pi first
# test on the cabinet...
git commit -am "neogeo: use lr-fbneo"      # it works: record it
python retropie-config/rpcfg.py restore    # it doesn't: put back what the last push replaced
```

- `push` only writes files that differ, keeps the existing owner and permissions, and stores
  backups in `~/rpcfg-backups/` on the Pi. `restore --list` shows them; `restore <id>` picks one.
- `push` never deletes files on the Pi. Deleting a file from `files/` just stops tracking it.
- `pull` refuses to overwrite uncommitted edits in `files/` (use `--force` to discard them).
- `/boot/config.txt` changes need a reboot; EmulationStation settings need an ES restart.

Since `git log -p retropie-config/files` is a history of every working configuration,
"it worked last week" becomes `git diff <old-commit> -- retropie-config/files`.

## Secrets

On `pull`, any value whose key looks secret (password, pass, psk, token, secret, apikey,
username, nickname, login, ssid, plus the keys in `secret-keys.txt`) is replaced with
`{{secret:KEY}}` in `files/`. The real value goes into `.local/secrets.env`. On `push`,
placeholders are filled back in, and the push stops if a value is missing.

Examples on a RetroPie: RetroAchievements login (`cheevos_*` in retroarch.cfg), netplay
passwords, and scraper accounts in `es_settings.cfg`. Wi-Fi config is not tracked at all
by default (see `manifest.txt`).

If a key is wrongly treated as secret, add `!key_name` to `secret-keys.txt`.

## Keeping game names out of git

The repo is public, so the game list is kept private:

- `pull` reads ROM **file names** from `ROM_DIRS`, and game **titles** from EmulationStation's
  `gamelist.xml`, into `.local/` (gitignored). The ROMs themselves are never read.
- Game lists, scraped media, collections, playlists, saves, `all/emulators.cfg` (per-ROM
  emulator choices) and standalone MAME per-game folders are excluded (`exclude.txt`).
- Files *named* after a ROM (RetroArch per-game overrides such as
  `config/FinalBurn Neo/<rom>.cfg`) are left on the Pi. Per-core and per-system overrides
  are kept.
- Some tracked files also store per-game settings inline, e.g. FBNeo writes
  `fbneo-dipswitch-<rom>-...` into `retroarch-core-options.cfg`. For files listed in
  `redact-lines.txt`, lines mentioning a ROM are left out on pull, and `push` takes them from
  the Pi's current copy, so per-game settings are never lost.
- If a remaining file *mentions* a ROM name or title, `pull` stops and lists it. Then either
  add an exclude, put a false positive (a common word that happens to be a game title) in
  `.local/rom-allow.txt`, or run `pull --drop-flagged`.
- `python retropie-config/rpcfg.py check` re-checks `files/` for ROM names, titles, secret
  values and excluded paths. Worth running after hand edits, before committing.

Limits: matching is on names of 4+ characters, so very short MAME names (e.g. 3-letter
ones) aren't checked. Per-game overrides have to be made on the Pi (RetroArch Quick Menu)
rather than in git. Prefer per-system or per-core overrides when troubleshooting anyway.

## Where emulator settings live (RetroPie)

| What | Path in `files/` |
|---|---|
| Default emulator per system | `opt/retropie/configs/<system>/emulators.cfg` (`default="lr-fbneo"`) |
| RetroArch global settings | `opt/retropie/configs/all/retroarch.cfg` |
| RetroArch per-system settings | `opt/retropie/configs/<system>/retroarch.cfg` |
| Core options | `opt/retropie/configs/all/retroarch-core-options.cfg` |
| Per-core / per-system overrides | `opt/retropie/configs/all/retroarch/config/<Core Name>/` |
| Controller / encoder mapping | `opt/retropie/configs/all/retroarch-joypads/`, `.../all/emulationstation/es_input.cfg` |
| Launch hooks | `opt/retropie/configs/all/runcommand-onstart.sh`, `runcommand-onend.sh`, `autostart.sh` |
| Pi display / audio | `boot/config.txt` |

For NeoGeo / arcade: the romset version has to match the emulator (e.g. lr-fbneo wants a
current FBNeo set, lr-mame2003-plus wants the 0.78-plus set), and NeoGeo needs `neogeo.zip`
from the matching set next to the games or in `~/RetroPie/BIOS`. Set the system default in
`<system>/emulators.cfg` instead of picking per game, so the choice is tracked here.

FBNeo "romset is missing files" errors listing only BIOS files (`sp-s3.sp1`, `sfix.sfix`, ...)
mean `neogeo.zip` is missing or outdated: see [troubleshooting/neogeo](../troubleshooting/neogeo/README.md).
