# Troubleshooting

Known problems and fixes:

- [neogeo](neogeo/README.md): FBNeo "romset is missing files" listing only BIOS files (`neogeo.zip` missing or outdated)

## Fetching logs from the Pi

Right after a game fails to start (before rebooting, because the launch log lives in RAM):

```
ssh retropie 'bash -s' < troubleshooting/fetch-logs.sh
```

In PowerShell, which has no `<` redirect:

```
Get-Content -Raw troubleshooting\fetch-logs.sh | ssh retropie 'bash -s'
```

It prints, with ROM paths, ROM names and game titles masked **on the Pi** (`<ROM>`, `<GAME>`):

| Section | Source | Use it for |
|---|---|---|
| Pi health | `uptime`, `vcgencmd get_throttled`, `df` | under-voltage / overheating (`throttled` should be `0x0`), full disks |
| Last launch | `/dev/shm/runcommand.log` | the exact emulator command for the last game: which core, which `--subsystem`, which config, which folder |
| RetroArch log file | `.../retroarch/logs/*.log` | only exists if `log_to_file` is turned on |
| EmulationStation | `~/.emulationstation/es_log.txt` | missing systems, game lists, controllers |

The script is read-only. The raw logs contain game names, so don't paste them into issues
or commit them: use the masked output.

## Getting more detail from RetroArch / FBNeo

By default the launch log only shows the command. To see why a core rejects a game (which
files and paths FBNeo searched), turn on verbose logging for that system for a while:

1. In `retropie-config/files/opt/retropie/configs/<system>/retroarch.cfg`, add:
   ```
   log_verbosity = "true"
   frontend_log_level = "0"
   libretro_log_level = "0"
   ```
2. Push it with `python retropie-config/rpcfg.py push`, launch the game again, then run `fetch-logs.sh`.
   runcommand writes RetroArch's output into `/dev/shm/runcommand.log`, below the command line.
3. Remove the lines and push again (or `rpcfg.py restore`). Don't commit verbose logging.

## Common reading of the launch command

- `--subsystem neocd` on a non Neo Geo CD system: the system's default emulator is set to
  `lr-fbneo-neocd`. Check `default` in `<system>/emulators.cfg`.
- Wrong core for a romset (e.g. `lr-mame2003` vs `lr-fbneo`): romsets are built for one
  emulator version. Set the matching `default` in `<system>/emulators.cfg`.
