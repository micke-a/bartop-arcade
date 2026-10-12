#!/usr/bin/env python3
"""RetroPie configuration as code.

    python retropie-config/rpcfg.py ssh-check  # can we reach and log in to the Pi?
    python retropie-config/rpcfg.py pull       # Pi -> files/ (sanitised)
    python retropie-config/rpcfg.py diff       # what a push would change
    python retropie-config/rpcfg.py push       # files/ -> Pi (with backup)
    python retropie-config/rpcfg.py restore    # undo the last push
    python retropie-config/rpcfg.py check      # secret / game-name guard

Secrets are swapped for {{secret:KEY}} placeholders on pull and the real values
are kept in .local/secrets.env (gitignored). Files named after a ROM, and files
whose contents mention a ROM, never make it into files/.
"""
import argparse
import base64
import difflib
import fnmatch
import html
import io
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import time
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
FILES = ROOT / "files"
LOCAL = ROOT / ".local"
PI_ENV = LOCAL / "pi.env"
SECRETS_ENV = LOCAL / "secrets.env"
ROM_NAMES = LOCAL / "rom-names.txt"
GAME_TITLES = LOCAL / "game-titles.txt"
ROM_ALLOW = LOCAL / "rom-allow.txt"

MAX_FILE_KB = 1024
MIN_ROM_TOKEN = 4
PLACEHOLDER_RE = re.compile(r"\{\{secret:([A-Za-z0-9_.-]+)\}\}")
SECRET_WORDS = {"password", "passwd", "pass", "psk", "token", "secret", "apikey",
                "username", "nickname", "login", "ssid", "credentials"}
# Names that show up in ROM folders but are not games.
IGNORE_NAMES = {"gamelist", "readme", "bios", "media", "images", "videos", "marquees",
                "screenshots", "covers", "wheel", "manuals", "neogeo", "systeminfo"}
WINDOWS_BAD_CHARS = set('<>:"\\|?*')

DEFAULTS = {
    "PI_USER": "pi",
    "ROM_DIRS": "/home/pi/RetroPie/roms /media/usb0/retropie-mount/roms",
}


# --------------------------------------------------------------------------- helpers

def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def read_list(path):
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]


def read_env(path):
    env = {}
    for line in read_list(path):
        key, sep, value = line.partition("=")
        if sep:
            env[key.strip()] = value.strip()
    return env


def load_pi_env():
    if not PI_ENV.exists():
        die(f"{PI_ENV.relative_to(ROOT)} not found. Copy pi.env.example to .local/pi.env and fill it in.")
    cfg = dict(DEFAULTS)
    cfg.update({k: v.strip("'\"") for k, v in read_env(PI_ENV).items()})
    if not cfg.get("PI_HOST"):
        die("PI_HOST is not set in .local/pi.env")
    return cfg


def as_text(data):
    if b"\0" in data:
        return None
    return data.decode("utf-8", errors="surrogateescape")


def as_bytes(text):
    return text.encode("utf-8", errors="surrogateescape")


def ssh_args(cfg, *options):
    """ssh command line for the Pi. PI_HOST may be an alias from ~/.ssh/config."""
    port = ["-p", cfg["PI_PORT"]] if cfg.get("PI_PORT") else []
    return ["ssh", *port, *options, f"{cfg['PI_USER']}@{cfg['PI_HOST']}"]


def ssh(cfg, command, data=None):
    """Run a command on the Pi; stderr goes straight to the terminal."""
    target = f"{cfg['PI_USER']}@{cfg['PI_HOST']}"
    res = subprocess.run([*ssh_args(cfg), command], input=data, stdout=subprocess.PIPE)
    if res.returncode != 0:
        die(f"ssh to {target} failed (exit {res.returncode})")
    return res.stdout


def bash_array(name, items):
    return f"{name}=(" + " ".join(shlex.quote(i) for i in items) + ")\n"


def read_tar(blob):
    files = {}
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for member in tf:
            path = PurePosixPath(member.name.lstrip("/"))
            if not member.isfile() or ".." in path.parts or str(path) in (".", ""):
                continue
            files[path.as_posix().removeprefix("./")] = tf.extractfile(member).read()
    return files


def write_tar(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for rel, data in sorted(files.items()):
            info = tarfile.TarInfo(rel)
            info.size, info.mode, info.mtime = len(data), 0o644, int(time.time())
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def local_files():
    if not FILES.exists():
        return {}
    return {p.relative_to(FILES).as_posix(): p.read_bytes()
            for p in sorted(FILES.rglob("*")) if p.is_file() and p.name != ".gitkeep"}


def system_names(paths):
    """RetroPie system names, taken from opt/retropie/configs/<system>/..."""
    prefix = ("opt", "retropie", "configs")
    return {PurePosixPath(p).parts[3] for p in paths
            if PurePosixPath(p).parts[:3] == prefix and len(PurePosixPath(p).parts) > 4}


def is_excluded(rel, patterns):
    parts = PurePosixPath(rel).parts
    prefixes = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
    return any(fnmatch.fnmatchcase(p, pat) for p in prefixes for pat in patterns)


def git(*args):
    res = subprocess.run(["git", *args], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return res.stdout if res.returncode == 0 else None


# --------------------------------------------------------------------------- secrets

class SecretRules:
    """Decides which config keys hold secrets. secret-keys.txt can force (KEY) or veto (!KEY)."""

    def __init__(self):
        self.force, self.never = set(), set()
        for key in read_list(ROOT / "secret-keys.txt"):
            (self.never if key.startswith("!") else self.force).add(key_id(key.lstrip("!")).lower())

    def is_secret(self, key):
        kl = key_id(key).lower()  # "pam password change" and pam_password_change are the same key
        if kl in self.never:
            return False
        if kl in self.force:
            return True
        words = [w.lower() for w in re.split(r"[^A-Za-z0-9]+|(?<=[a-z0-9])(?=[A-Z])", key) if w]
        return any(w in SECRET_WORDS for w in words) or "apikey" in "".join(words)


KV_RE = re.compile(r'^(\s*)([^\s#;=\[<][^=]*?)(\s*=\s*)(.*?)(\s*)$')
XML_KV_RE = re.compile(r'(\bname="([^"]*)"\s+value=")([^"]*)(")')


def key_id(key):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", key.strip())


def sanitize(data, rules):
    """Replace secret values with {{secret:KEY}}. Returns (new_data, {KEY: value})."""
    text = as_text(data)
    if text is None:
        return data, {}
    found = {}

    def keep(key, value):
        if not value or PLACEHOLDER_RE.fullmatch(value) or not rules.is_secret(key):
            return None
        found[key_id(key)] = value
        return "{{secret:%s}}" % key_id(key)

    def xml_sub(m):
        new = keep(m.group(2), m.group(3))
        return m.group(0) if new is None else m.group(1) + new + m.group(4)

    out = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        end = line[len(body):]
        body = XML_KV_RE.sub(xml_sub, body)
        m = KV_RE.match(body)
        if m:
            indent, key, sep, value, trail = m.groups()
            quote = value[0] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else ""
            inner = value[1:-1] if quote else value
            new = keep(key, inner)
            if new is not None:
                body = f"{indent}{key}{sep}{quote}{new}{quote}{trail}"
        out.append(body + end)
    return as_bytes("".join(out)), found


def render(data, secrets):
    """Fill {{secret:KEY}} placeholders. Returns (data, missing_keys)."""
    text = as_text(data)
    if text is None:
        return data, set()
    missing = set()

    def sub(m):
        if m.group(1) not in secrets:
            missing.add(m.group(1))
            return m.group(0)
        return secrets[m.group(1)]

    return as_bytes(PLACEHOLDER_RE.sub(sub, text)), missing


def load_secrets():
    return read_env(SECRETS_ENV)


def save_secrets(secrets):
    LOCAL.mkdir(exist_ok=True)
    lines = ["# Real values for {{secret:KEY}} placeholders. Gitignored - never commit.", ""]
    lines += [f"{k}={v}" for k, v in sorted(secrets.items())]
    SECRETS_ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- privacy

class Privacy:
    """Detects ROM / game names, using the ROM list cached in .local/ by `pull`."""

    WORD = re.compile(r"[a-z0-9]+")

    def __init__(self, systems):
        self.has_roms = ROM_NAMES.exists()
        allow = IGNORE_NAMES | {s.lower() for s in systems} | {s.lower() for s in read_list(ROM_ALLOW)}
        files = ROM_NAMES.read_text(encoding="utf-8").splitlines() if self.has_roms else []
        titles = GAME_TITLES.read_text(encoding="utf-8").splitlines() if GAME_TITLES.exists() else []
        tokens = set()
        for stem in [os.path.splitext(f.strip())[0] for f in files] + [t.strip() for t in titles]:
            # "Game (USA) [!]", "Game - Subtitle", "Game: Subtitle" -> "Game"
            short = re.split(r"\s*(?:[(\[]|\s-\s|:\s)", stem)[0].strip()
            tokens |= {t.lower() for t in (stem, short)
                       if len(t) >= MIN_ROM_TOKEN and t.lower() not in allow}
        self.tokens = tokens
        self.index = {}
        for tok in tokens:
            m = self.WORD.search(tok)
            if m:
                self.index.setdefault(m.group(), []).append((m.start(), tok))

    def path_hits(self, rel):
        return [part for part in PurePosixPath(rel).parts
                if part.lower() in self.tokens or os.path.splitext(part)[0].lower() in self.tokens]

    def line_hits(self, line):
        low, hits = line.lower(), []
        for m in self.WORD.finditer(low):
            for offset, tok in self.index.get(m.group(), ()):
                s = m.start() - offset
                e = s + len(tok)
                if s < 0 or not low.startswith(tok, s):
                    continue
                if (s > 0 and low[s - 1].isalnum()) or (e < len(low) and low[e].isalnum()):
                    continue
                hits.append(line[s:e])
        return hits

    def text_hits(self, data):
        text = as_text(data)
        if text is None or not self.tokens:
            return []
        return [(n, hit) for n, line in enumerate(text.splitlines(), 1) for hit in self.line_hits(line)]


def split_rom_lines(data, privacy):
    """Split a text file into (lines without ROM names, lines with ROM names)."""
    text = as_text(data)
    if text is None:
        return data, b""
    public, private = [], []
    for line in text.splitlines(keepends=True):
        (private if privacy.line_hits(line) else public).append(line)
    return as_bytes("".join(public)), as_bytes("".join(private))


# --------------------------------------------------------------------------- remote scripts

COLLECT_SH = r'''
set -uo pipefail
cd /
paths=()
for p in "${PATHS[@]}"; do
  if [ -e "$p" ]; then paths+=("$p"); else echo "  (not on Pi, skipped) /$p" >&2; fi
done
[ ${#paths[@]} -gt 0 ] || { echo "nothing to collect" >&2; exit 1; }
prune=()
for x in "${EXCLUDES[@]}"; do prune+=(-path "$x" -prune -o); done
find "${paths[@]}" "${prune[@]}" -type f -size +%{MAXKB}k -printf '  (over %{MAXKB}KB, skipped) /%p\n' >&2
find "${paths[@]}" "${prune[@]}" -type f -size -%{MAXKB}k -print0 | tar -czf - --null -T - | base64
'''.replace("%{MAXKB}", str(MAX_FILE_KB))

ROM_LIST_SH = r'''
for d in "${ROM_DIRS[@]}"; do
  [ -d "$d" ] && find -L "$d" -mindepth 2 -type f -printf '%f\n' 2>/dev/null
done | sort -u
'''

# Human-readable titles from EmulationStation game lists ("Metal Slug X" vs mslugx.zip).
# The "retropie" list is the settings menu (Audio, WiFi, Retroarch...), not games.
GAME_TITLES_SH = r'''
for d in "${ROM_DIRS[@]}" /opt/retropie/configs/all/emulationstation/gamelists "$HOME/.emulationstation/gamelists"; do
  [ -d "$d" ] && find -L "$d" -maxdepth 2 -name gamelist.xml -not -path '*/retropie/gamelist.xml' \
    -exec grep -ho '<name>[^<]*</name>' {} + 2>/dev/null
done | sed 's/<\/\?name>//g' | sort -u
'''

APPLY_SH = r'''
set -euo pipefail
STAGE=$(mktemp -d /tmp/rpcfg-stage.XXXXXX)
trap 'rm -rf "$STAGE"' EXIT
base64 -d <<'RPCFG_PAYLOAD' | tar -xzf - -C "$STAGE"
%PAYLOAD%
RPCFG_PAYLOAD
TS=$(date +%Y%m%d-%H%M%S)
BK="$HOME/rpcfg-backups"; mkdir -p "$BK"
cd "$STAGE"
mapfile -d '' FILES < <(find . -type f -printf '%P\0' | sort -z)
existing=(); created=()
for p in "${FILES[@]}"; do
  if [ -e "/$p" ]; then existing+=("$p"); else created+=("$p"); fi
done
if [ ${#existing[@]} -gt 0 ]; then
  sudo -n tar -czpf "$BK/$TS.tgz" -C / "${existing[@]}"
  sudo -n chown "$(id -u):$(id -g)" "$BK/$TS.tgz"
fi
: > "$BK/$TS.created"
for p in "${existing[@]}"; do
  sudo -n cp "$STAGE/$p" "/$p"   # copying onto an existing file keeps its owner and mode
  echo "  updated /$p"
done
for p in "${created[@]}"; do
  case "/$p" in /opt/retropie/configs/*|/home/*) owner="$OWNER" ;; *) owner=root ;; esac
  case "$p" in *.sh) mode=0755 ;; *) mode=0644 ;; esac
  sudo -n -u "$owner" mkdir -p "$(dirname "/$p")"
  sudo -n install -m "$mode" -o "$owner" -g "$owner" "$STAGE/$p" "/$p"
  echo "$p" >> "$BK/$TS.created"
  echo "  created /$p"
done
echo "Backup on Pi: ~/rpcfg-backups/$TS (undo with: rpcfg.py restore $TS)"
'''

RESTORE_SH = r'''
set -euo pipefail
BK="$HOME/rpcfg-backups"
if [ "$LIST" = 1 ]; then ls -1t "$BK"/*.created 2>/dev/null | head -20 | xargs -r -n1 basename | sed 's/\.created$//'; exit 0; fi
if [ -z "$TS" ]; then
  TS=$(ls -1t "$BK"/*.created 2>/dev/null | head -1 | xargs -r basename | sed 's/\.created$//')
fi
[ -n "$TS" ] && [ -f "$BK/$TS.created" ] || { echo "no backup found" >&2; exit 1; }
[ -f "$BK/$TS.tgz" ] && sudo -n tar -xzpf "$BK/$TS.tgz" -C / && echo "  restored files from $TS"
while IFS= read -r p; do
  [ -n "$p" ] && sudo -n rm -f -- "/$p" && echo "  removed /$p"
done < "$BK/$TS.created"
mv "$BK/$TS.created" "$BK/$TS.created.restored"
'''


# --------------------------------------------------------------------------- commands

def cmd_pull(args):
    cfg = load_pi_env()
    if not args.force and (git("status", "--porcelain", "--", str(FILES)) or b"").strip():
        die("files/ has uncommitted changes; commit or stash them first (or use --force).")

    print("Listing ROM file names and game titles on the Pi (cached in .local/, never committed)...")
    rom_dirs = bash_array("ROM_DIRS", cfg["ROM_DIRS"].split())
    roms = ssh(cfg, "bash -s", as_bytes(rom_dirs + ROM_LIST_SH))
    titles = ssh(cfg, "bash -s", as_bytes(rom_dirs + GAME_TITLES_SH)).decode("utf-8", errors="replace")
    LOCAL.mkdir(exist_ok=True)
    ROM_NAMES.write_bytes(roms)
    GAME_TITLES.write_text(html.unescape(titles), encoding="utf-8")

    print("Collecting config files...")
    script = (bash_array("PATHS", [p.lstrip("/") for p in read_list(ROOT / "manifest.txt")])
              + bash_array("EXCLUDES", read_list(ROOT / "exclude.txt")) + COLLECT_SH)
    remote = read_tar(base64.b64decode(ssh(cfg, "bash -s", as_bytes(script))))

    privacy = Privacy(system_names(remote))
    rules = SecretRules()
    secrets = load_secrets()
    out, dropped, flagged, secret_keys = {}, [], {}, set()
    redact, redacted = read_list(ROOT / "redact-lines.txt"), 0
    for rel, data in sorted(remote.items()):
        if privacy.path_hits(rel):
            dropped.append(rel)
            continue
        if any(c in WINDOWS_BAD_CHARS for c in rel):
            print(f"  (unsafe file name, skipped) /{rel}")
            continue
        data, found = sanitize(data, rules)
        for key, value in found.items():
            if key in secrets and secrets[key] != value and key in secret_keys:
                print(f"  warning: secret {key} has different values in different files")
            secrets[key] = value
            secret_keys.add(key)
        if is_excluded(rel, redact):
            data, private = split_rom_lines(data, privacy)
            if private:
                redacted += private.count(b"\n")
        hits = privacy.text_hits(data)
        if hits:
            flagged[rel] = hits
        out[rel] = data

    if flagged:
        print("\nThese files mention ROM names:")
        for rel, hits in flagged.items():
            for line, hit in hits[:5]:
                print(f"  /{rel}:{line}: {hit}")
        if not args.drop_flagged:
            die("nothing written. Add a pattern to exclude.txt, add a false positive to "
                ".local/rom-allow.txt, or re-run with --drop-flagged to leave these files out.")
        for rel in flagged:
            del out[rel]

    save_secrets(secrets)
    if FILES.exists():
        shutil.rmtree(FILES)
    for rel, data in out.items():
        target = FILES.joinpath(*PurePosixPath(rel).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    print(f"\nPulled {len(out)} files.")
    if dropped:
        print(f"Left out {len(dropped)} file(s) named after ROMs (per-game overrides stay on the Pi only).")
    if redacted:
        print(f"Left out {redacted} per-game line(s) from files in redact-lines.txt (kept on the Pi, preserved by push).")
    if flagged:
        print(f"Left out {len(flagged)} file(s) that mention ROM names.")
    if secret_keys:
        print(f"Templated secrets: {', '.join(sorted(secret_keys))} (values in .local/secrets.env)")
    status = git("status", "--short", "--", str(FILES))
    if status:
        print("\nChanges vs. git:\n" + status.decode(errors="replace"))


def plan_push(cfg):
    """Compare files/ with the Pi. Returns {rel: rendered_bytes} for files that differ."""
    templates = local_files()
    if not templates:
        die("files/ is empty; run pull first.")
    secrets = load_secrets()
    rules = SecretRules()
    rendered, missing = {}, set()
    for rel, data in templates.items():
        text = as_text(data)
        if text is not None and "\r\n" in text:
            print(f"  note: converting CRLF to LF in {rel}")
            data = templates[rel] = data.replace(b"\r\n", b"\n")
        rendered[rel], miss = render(data, secrets)
        missing |= miss
    if missing:
        die(f"missing secrets in .local/secrets.env: {', '.join(sorted(missing))}")

    listing = as_bytes("\n".join(templates) + "\n")
    blob = ssh(cfg, "cd / && tar -czf - --ignore-failed-read -T - 2>/dev/null | base64", listing)
    remote = read_tar(base64.b64decode(blob)) if blob.strip() else {}

    # Per-game lines were left out on pull; take them from the Pi so push keeps them.
    redact = read_list(ROOT / "redact-lines.txt")
    privacy = Privacy(system_names(templates))
    if any(is_excluded(rel, redact) for rel in templates) and not privacy.has_roms:
        die("no ROM list in .local/ to tell which lines to preserve; run pull first.")
    changed = {}
    for rel in templates:
        public, private = remote.get(rel), b""
        if public is not None and is_excluded(rel, redact):
            public, private = split_rom_lines(public, privacy)
        if public == rendered[rel]:
            continue
        if private and not rendered[rel].endswith(b"\n"):
            rendered[rel] += b"\n"
        changed[rel] = rendered[rel] + private
        before = as_text(sanitize(public, rules)[0]) if public is not None else ""
        after = as_text(templates[rel])
        if before is None or after is None:
            print(f"--- /{rel}: binary file differs")
            continue
        diff = list(difflib.unified_diff(before.splitlines(), after.splitlines(),
                                         f"pi:/{rel}", f"repo:/{rel}", lineterm=""))
        print("\n".join(diff) if diff else f"--- /{rel}: secret value differs")
    return changed


def cmd_diff(args):
    changed = plan_push(load_pi_env())
    print(f"\n{len(changed)} file(s) differ from the Pi." if changed else "Pi matches files/.")


def cmd_push(args):
    cfg = load_pi_env()
    changed = plan_push(cfg)
    if not changed:
        print("Pi already matches files/. Nothing to push.")
        return
    print(f"\n{len(changed)} file(s) will be written to {cfg['PI_HOST']}.")
    if not args.yes:
        if not sys.stdin.isatty():
            die("not a terminal; re-run with --yes to confirm.")
        if input("Push? [y/N] ").strip().lower() != "y":
            print("Aborted.")
            return
    payload = base64.encodebytes(write_tar(changed)).decode().strip()
    script = f"OWNER={shlex.quote(cfg['PI_USER'])}\n" + APPLY_SH.replace("%PAYLOAD%", payload)
    sys.stdout.write(ssh(cfg, "bash -s", as_bytes(script)).decode(errors="replace"))
    if any(rel.startswith("boot/") for rel in changed):
        print("A /boot file changed: reboot the Pi for it to take effect (sudo reboot).")
    elif any("emulationstation" in rel for rel in changed):
        print("Restart EmulationStation for its settings to take effect.")


def cmd_restore(args):
    cfg = load_pi_env()
    script = f"TS={shlex.quote(args.backup or '')}\nLIST={1 if args.list else 0}\n" + RESTORE_SH
    sys.stdout.write(ssh(cfg, "bash -s", as_bytes(script)).decode(errors="replace"))


def cmd_check(args):
    entries = local_files()
    privacy = Privacy(system_names(entries))
    rules = SecretRules()
    excludes = read_list(ROOT / "exclude.txt")
    problems = []
    for rel, data in entries.items():
        shown = f"files/{rel}"
        if privacy.path_hits(rel):
            problems.append(f"{shown}: file name contains a ROM name")
        for line, hit in privacy.text_hits(data):
            problems.append(f"{shown}:{line}: mentions ROM name '{hit}'")
        if is_excluded(rel, excludes):
            problems.append(f"{shown}: matches exclude.txt and should not be tracked")
        for key in sanitize(data, rules)[1]:
            problems.append(f"{shown}: real value for secret '{key}' (run pull, or use {{{{secret:{key}}}}})")
    if not privacy.has_roms:
        print("rpcfg check: no ROM list in .local/ yet, so game names were not checked (run pull once).",
              file=sys.stderr)
    if problems:
        print("rpcfg check failed:", *problems, sep="\n  ", file=sys.stderr)
        sys.exit(1)
    print(f"rpcfg check: {len(entries)} file(s) OK")


REMOTE_CHECK_SH = r'''
ok()   { echo "OK|$1"; }
bad()  { echo "FAIL|$1|$2"; }
warn() { echo "WARN|$1|$2"; }
if (( BASH_VERSINFO[0] > 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] >= 4) )); then
  ok "bash $BASH_VERSION"
else
  bad "bash $BASH_VERSION is too old" "push needs bash 4.4+ (any RetroPie image from 2019 on has it)"
fi
if sudo -n true 2>/dev/null; then ok "passwordless sudo"
else bad "sudo asks for a password" "push/restore use sudo -n; RetroPie normally gives the pi user passwordless sudo"; fi
for c in tar base64 find grep; do
  command -v "$c" >/dev/null && ok "$c available" || bad "$c not installed" "sudo apt install $c"
done
find / -maxdepth 0 -printf '' 2>/dev/null && ok "GNU find" || bad "find has no -printf" "GNU findutils is required"
[ -d /opt/retropie/configs ] && ok "/opt/retropie/configs exists" \
  || bad "/opt/retropie/configs not found" "is this the RetroPie machine? check PI_HOST"
for d in "${ROM_DIRS[@]}"; do
  [ -d "$d" ] && ok "ROM folder $d" \
    || warn "ROM folder $d not found" "fix ROM_DIRS in .local/pi.env; game-name checks only know ROMs in folders that exist"
done
'''


def cmd_ssh_check(args):
    failures = 0

    def report(status, msg, hint=None):
        nonlocal failures
        failures += status == "FAIL"
        print(f"[{status:^4}] {msg}")
        if hint:
            print(f"       -> {hint}")

    def finish():
        print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
        sys.exit(1 if failures else 0)

    cfg = load_pi_env()
    target = f"{cfg['PI_USER']}@{cfg['PI_HOST']}"
    report("OK", f".local/pi.env: target {target}")

    exe = shutil.which("ssh")
    if not exe:
        report("FAIL", "ssh client not found on PATH",
               "Windows: Settings > System > Optional features > add 'OpenSSH Client'")
        finish()
    report("OK", f"ssh client: {exe}")
    if os.name == "nt" and "git" in exe.lower():
        report("WARN", "using Git Bash's ssh, which can't see keys loaded into the Windows ssh-agent",
               "fine if your key has no passphrase; otherwise run rpcfg.py from PowerShell")

    # What ssh will actually do once ~/.ssh/config is applied.
    effective, identities = {}, []
    res = subprocess.run(ssh_args(cfg, "-G"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in res.stdout.splitlines():
        key, _, value = line.partition(" ")
        if key == "identityfile":
            identities.append(value)
        else:
            effective.setdefault(key, value)
    host = effective.get("hostname", cfg["PI_HOST"])
    port = int(effective.get("port", cfg.get("PI_PORT") or 22))
    report("OK", f"ssh will connect to {effective.get('user', cfg['PI_USER'])}@{host} port {port}")
    keys = [i for i in identities if Path(os.path.expanduser(i)).exists()]
    if keys:
        report("OK", "private key(s) ssh will offer: " + ", ".join(keys))
        if len(keys) > 2 and effective.get("identitiesonly") != "yes":
            report("WARN", f"ssh may try {len(keys)} keys before the right one; the Pi stops after 6 attempts",
                   "add 'IdentitiesOnly yes' and 'IdentityFile' for this host in ~/.ssh/config")
    else:
        report("WARN", "no private key file found for this host",
               "create one with ssh-keygen and point IdentityFile at it in ~/.ssh/config")

    try:
        addr = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[0][4][0]
        report("OK", f"{host} resolves to {addr}")
    except socket.gaierror:
        report("FAIL", f"can't resolve {host}",
               "is the Pi switched on? '.local' names also need mDNS to work on your network; "
               "if it is on, use the IP from RetroPie menu > Show IP as HostName in ~/.ssh/config")
        finish()

    try:
        with socket.create_connection((addr, port), timeout=5) as sock:
            sock.settimeout(5)
            banner = sock.recv(256).decode(errors="replace").strip()
        report("OK", f"port {port} open: {banner or 'no banner'}")
    except ConnectionRefusedError:
        report("FAIL", f"{addr} refused port {port}",
               "SSH is off: create an empty file called 'ssh' on the SD card's boot partition, "
               "or enable it in RetroPie menu > Raspi-Config > Interface Options > SSH")
        finish()
    except OSError as e:
        report("FAIL", f"no answer from {addr}:{port} ({e.__class__.__name__})",
               "is the Pi switched on and on the same network? has its IP changed?")
        finish()

    batch = ssh_args(cfg, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10")
    res = subprocess.run([*batch, "true"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    err = res.stderr.strip()
    if res.returncode == 0:
        report("OK", "key login works without a password")
    elif "IDENTIFICATION HAS CHANGED" in err:
        report("FAIL", "the Pi's host key changed (expected after re-flashing the SD card)",
               f"run: ssh-keygen -R {host}   then connect once with: ssh {target}")
    elif "Host key verification failed" in err:
        report("FAIL", "the Pi's host key isn't trusted yet",
               f"connect once by hand and answer 'yes': ssh {target}")
    elif "Too many authentication failures" in err:
        report("FAIL", "the Pi gave up after too many keys were tried",
               "add 'IdentitiesOnly yes' and 'IdentityFile' for this host in ~/.ssh/config")
    elif "Permission denied" in err:
        report("FAIL", "the Pi didn't accept any key (password login is disabled for this check)",
               "copy the .pub key to the Pi (README step 1); if the key has a passphrase, "
               "load it with ssh-add; 'ssh -v " + target + "' shows which keys are offered")
    else:
        report("FAIL", "ssh login failed: " + (err.splitlines()[-1] if err else f"exit {res.returncode}"))
    if res.returncode != 0:
        finish()

    script = bash_array("ROM_DIRS", cfg["ROM_DIRS"].split()) + REMOTE_CHECK_SH
    res = subprocess.run([*batch, "bash -s"], input=as_bytes(script), stdout=subprocess.PIPE)
    for line in res.stdout.decode(errors="replace").splitlines():
        status, _, rest = line.partition("|")
        msg, _, hint = rest.partition("|")
        report(status, f"Pi: {msg}", hint or None)
    finish()


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ssh-check", help="diagnose the SSH connection to the Pi, step by step").set_defaults(
        func=cmd_ssh_check)
    p = sub.add_parser("pull", help="copy config from the Pi into files/")
    p.add_argument("--force", action="store_true", help="overwrite uncommitted changes in files/")
    p.add_argument("--drop-flagged", action="store_true", help="leave out files that mention ROM names")
    p.set_defaults(func=cmd_pull)
    sub.add_parser("diff", help="show what push would change").set_defaults(func=cmd_diff)
    p = sub.add_parser("push", help="write changed files/ to the Pi (backs up first)")
    p.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    p.set_defaults(func=cmd_push)
    p = sub.add_parser("restore", help="undo a push using the backup on the Pi")
    p.add_argument("backup", nargs="?", help="backup id (default: most recent)")
    p.add_argument("--list", action="store_true", help="list backups")
    p.set_defaults(func=cmd_restore)
    sub.add_parser("check", help="fail if files/ contains secrets, ROM names or excluded files").set_defaults(
        func=cmd_check)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
