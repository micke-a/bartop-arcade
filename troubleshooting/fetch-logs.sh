#!/bin/bash
# Prints the logs that matter when a game won't start, with ROM paths, ROM names
# and game titles masked ON THE PI, so they never leave it. Run from the PC:
#   ssh retropie 'bash -s' < troubleshooting/fetch-logs.sh
# Logs in /dev/shm are in RAM: fetch them right after the failed launch, before a reboot.

python3 - <<'PY'
import glob, html, os, re, subprocess

ROM_DIRS = ["/home/pi/RetroPie/roms", "/media/usb0/retropie-mount/roms"]
# BIOS / system names stay readable: they're what the errors are about.
KEEP = {"neogeo", "neocdz", "neocd", "pgm", "skns", "decocass", "isgsm", "nmk004", "ym2608",
        "cchip", "bubsys", "midssio", "namcoc69", "namcoc70", "namcoc75", "bios", "gamelist"}

names = set()
for d in ROM_DIRS:
    if os.path.isdir(d):
        KEEP |= {s.lower() for s in os.listdir(d)}
        for root, _, files in os.walk(d, followlinks=True):
            names |= {os.path.splitext(f)[0] for f in files}
for g in glob.glob("/home/pi/RetroPie/roms/*/gamelist.xml") + \
         glob.glob("/opt/retropie/configs/all/emulationstation/gamelists/*/gamelist.xml"):
    if "/retropie/gamelist.xml" not in g:  # that one is the settings menu
        names |= {html.unescape(n) for n in re.findall(r"<name>([^<]*)</name>", open(g, errors="replace").read())}
names = sorted({n for n in names if len(n) >= 2 and n.lower() not in KEEP}, key=len, reverse=True)
name_re = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(map(re.escape, names)) + r")(?![A-Za-z0-9])", re.I) if names else None
path_re = re.compile(r"(/roms/[^/\s\"']+/)[^\s\"']+")

def mask(text):
    text = path_re.sub(r"\1<ROM>", text)
    return name_re.sub("<GAME>", text) if name_re else text

def show(title, path, tail):
    print(f"\n===== {title}: {path}")
    if not os.path.exists(path):
        print("(not present)")
        return
    out = subprocess.run(["date", "-r", path, "+%F %T"], capture_output=True, text=True).stdout.strip()
    print(f"(last written {out}, last {tail} lines)")
    lines = open(path, errors="replace").read().splitlines()[-tail:]
    print(mask("\n".join(lines)))

print("===== Pi health")
for cmd in (["uptime"], ["vcgencmd", "get_throttled"], ["df", "-h", "/", "/media/usb0"]):
    try:
        print(subprocess.run(cmd, capture_output=True, text=True).stdout.strip())
    except FileNotFoundError:
        pass
print("(get_throttled: 0x0 is good; anything else means under-voltage or overheating)")

show("Last launch: emulator command + RetroArch output", "/dev/shm/runcommand.log", 120)
retro_logs = sorted(glob.glob("/opt/retropie/configs/all/retroarch/logs/*.log") +
                    glob.glob("/home/pi/.config/retroarch/logs/*.log"), key=os.path.getmtime)
if retro_logs:
    show("Newest RetroArch log file", retro_logs[-1], 120)
show("EmulationStation", "/home/pi/.emulationstation/es_log.txt", 30)
PY
