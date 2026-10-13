#!/bin/bash
# Finds every neogeo.zip on the Pi and checks it contains the BIOS files the
# current FBNeo expects (matched by CRC, like FBNeo does). Run from the PC:
#   ssh retropie 'bash -s' < troubleshooting/neogeo/check-neogeo-bios.sh
echo "lr-fbneo build: $(grep -h pkg_repo_date /opt/retropie/libretrocores/lr-fbneo/retropie.pkg 2>/dev/null | cut -d'"' -f2)"
found=0
while read -r f; do
  found=1
  echo "--- $f ($(stat -Lc %s "$f") bytes)"
  python3 - "$f" <<'PY'
import sys, zipfile
# Files FBNeo reported missing when neogeo.zip was absent or outdated.
need = {"sp-s3.sp1": 0x91b64be3, "sm1.sm1": 0x94416d67, "sfix.sfix": 0xc2ea0cfd, "000-lo.lo": 0x5a86cff2}
z = zipfile.ZipFile(sys.argv[1])
by_crc = {i.CRC: i.filename for i in z.infolist()}
print("    %d files inside" % len(z.infolist()))
for name, crc in need.items():
    hit = by_crc.get(crc)
    print("    %-10s %s" % (name, "OK" if hit == name else ("present but named " + hit if hit else "MISSING (wrong or outdated neogeo.zip)")))
PY
done < <(find -L /home/pi/RetroPie /media/usb0 -iname 'neogeo.zip' 2>/dev/null | sort -u)
[ "$found" = 1 ] || echo "No neogeo.zip found anywhere: every Neo Geo game will fail."
