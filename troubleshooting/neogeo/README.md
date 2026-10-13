# Neo Geo games fail to start in FBNeo

## Symptom

Starting a Neo Geo game (lr-fbneo) shows an **FBNeo Error** screen instead of the game:

```
This game is known but one of your romsets is missing files for THIS VERSION of FBNeo.
Verify the following romsets : <game> neogeo

ROM with name sp-s3.sp1 and CRC 0x91b64be3 is missing
ROM with name sm1.sm1 and CRC 0x94416d67 is missing
ROM with name sfix.sfix and CRC 0xc2ea0cfd is missing
ROM with name 000-lo.lo and CRC 0x5a86cff2 is missing
```

## Cause

Every missing file belongs to **`neogeo.zip`, the Neo Geo BIOS**, not to the game. In FBNeo
romsets the BIOS is a separate zip that every Neo Geo game needs. FBNeo checks each file by
CRC, so the error shows up both when `neogeo.zip` is missing and when it's the wrong version
(e.g. taken from a MAME set or an old pack).

On this cabinet `neogeo.zip` was missing entirely. The game zips and FBNeo itself were fine.

How to tell it apart: if only BIOS files (`sp-*.sp1`, `sm1.sm1`, `sfix.sfix`, `000-lo.lo`, ...)
are listed, it's the BIOS. If files named after the game are listed, the game zip doesn't
match this FBNeo version and needs replacing from a current FBNeo romset.

## Fix

1. Get `neogeo.zip` from an **FBNeo romset matching the installed FBNeo version** (RetroPie
   updates lr-fbneo, so use a current set). Keep it zipped and named `neogeo.zip`.
2. Copy it into the same folder as the Neo Geo games. From Windows, via the Samba share:
   ```
   \retropie\roms-usb0\neogeo\neogeo.zip
   ```
   Neo Geo games kept in other folders (e.g. `arcade`) need a copy there too.
3. Start the game again. No reboot or config change is needed.

## Check

From the PC, list every `neogeo.zip` on the Pi and check it has the right files by CRC:

```
ssh retropie 'bash -s' < troubleshooting/neogeo/check-neogeo-bios.sh
```

All four lines should say `OK`. It only reads files and never launches anything.
