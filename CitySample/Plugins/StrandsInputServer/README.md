# Strands Input Server (UE 5.6) — Runtime TCP NDJSON Command Server

Version: 0.1.0  
Module: StrandsInputServer (Runtime)  
Platforms: Win64, Linux  
Engine: Unreal Engine 5.6

Lightweight in-game TCP JSON command server to control Character movement, camera look, jump, and sprint. Works in PIE, Standalone, and packaged builds.

## How it works

- Subsystem: `UStrandsInputServerSubsystem` (UTickableWorldSubsystem) runs once per UWorld.
- Startup:
  - Reads `UStrandsInputServerSettings` (DeveloperSettings) from config and Project Settings.
  - If `bAutoStart=true` and the world is a game world, it starts a `FTcpListener` on `127.0.0.1:Port` (default 17777).
- Networking:
  - Non-blocking sockets; accepts clients via FTcpListener.
  - Drain/poll reads pending bytes, accumulates into per-client buffer, and splits newline-delimited JSON (NDJSON).
- Commands (one JSON object per line):
  - Move: `{ "cmd": "move", "forward": 1.0, "right": 0.0, "duration": 0.25 }`
  - Look: `{ "cmd": "look", "yawRate": 90.0, "pitchRate": 0.0, "duration": 1.0 }` (deg/sec)
  - Jump: `{ "cmd": "jump" }`
  - Sprint: `{ "cmd": "sprint", "enabled": true }`
- Application:
  - Each tick, subsystem sums active `move/look` actions and applies:
    - Movement via `ACharacter::AddMovementInput()`
    - View via `APawn::AddControllerYawInput/PitchInput()`
    - Jump via `ACharacter::Jump()` using a queued counter
    - Sprint toggles `UCharacterMovementComponent::MaxWalkSpeed`

## Key Files

- Descriptor:
  - `Plugins/StrandsInputServer/StrandsInputServer.uplugin`
- Module and Build:
  - `Plugins/StrandsInputServer/Source/StrandsInputServer/StrandsInputServer.Build.cs`
  - `Plugins/StrandsInputServer/Source/StrandsInputServer/Private/StrandsInputServerModule.cpp`
- Subsystem:
  - `Plugins/StrandsInputServer/Source/StrandsInputServer/Public/StrandsInputServerSubsystem.h`
  - `Plugins/StrandsInputServer/Source/StrandsInputServer/Private/StrandsInputServerSubsystem.cpp`
- Settings:
  - `Plugins/StrandsInputServer/Source/StrandsInputServer/Public/StrandsInputServerSettings.h`
  - `Plugins/StrandsInputServer/Config/DefaultStrandsInputServer.ini`
- Client tooling:
  - `Tools/StrandsInputClient/send_cmd.ps1` (PowerShell client; supports -HoldMs keepalive)
  - `Tools/StrandsInputClient/send_cmd.py` (optional Python client)
  - `Tools/StrandsInputClient/RebuildAndTest-StrandsInputServer.ps1` (automation: stop editor, clean, build, launch, send commands, tail logs)

## Settings (Project Settings > Plugins > Strands Input Server)

- `bAutoStart` (bool, default true)
- `Port` (int, default 17777)
- `DefaultMoveDuration` (sec, default 0.25)
- `DefaultLookDuration` (sec, default 0.2)
- `NormalWalkSpeed` (default 600)
- `SprintWalkSpeed` (default 1000)

These can be overridden in `Config/DefaultStrandsInputServer.ini`:

```
[/Script/StrandsInputServer.StrandsInputServerSettings]
bAutoStart=True
Port=17777
DefaultMoveDuration=0.25
DefaultLookDuration=0.2
NormalWalkSpeed=600.0
SprintWalkSpeed=1000.0
```

## Usage

1) Ensure your PlayerController possesses an `ACharacter` (e.g., `BP_ThirdPersonCharacter`).  
2) Play (PIE/Standalone). Output Log should show:
   - `StrandsInputServer: Listening on 127.0.0.1:17777`
3) From PowerShell, send commands while the session is running, for example:

- Jump once:
```
powershell -NoProfile -ExecutionPolicy Bypass -File "Tools/StrandsInputClient/send_cmd.ps1" -Cmd jump -HoldMs 100
```

- Move forward for 1s:
```
powershell -NoProfile -ExecutionPolicy Bypass -File "Tools/StrandsInputClient/send_cmd.ps1" -Cmd move -Forward 1 -Duration 1 -HoldMs 100
```

- Yaw right at 90 deg/sec for 1s:
```
powershell -NoProfile -ExecutionPolicy Bypass -File "Tools/StrandsInputClient/send_cmd.ps1" -Cmd look -YawRate 90 -Duration 1 -HoldMs 100
```

- Enable sprint:
```
powershell -NoProfile -ExecutionPolicy Bypass -File "Tools/StrandsInputClient/send_cmd.ps1" -Cmd sprint -Enabled $true -HoldMs 100
```

Expected logs:
- `StrandsInputServer: Client connected.`
- `StrandsInputServer: Received cmd 'jump'`
- `StrandsInputServer: Axes Move=(...), LookRate=(...), PendingJump=N`
- `StrandsInputServer: Jumping N time(s)`

## Design Notes

- Fire-and-forget clients (short-lived) are supported by draining data immediately on accept and before disconnect checks during polling.
- Actions are time-bounded; overlapping Move/Look commands sum and are clamped per tick.
- Sprint toggles `MaxWalkSpeed` and persists until toggled again.
- Security: bind address is localhost-only by default.

## Compatibility

- Tested with UE 5.6 (include paths updated accordingly).
- Build deps: `Sockets`, `Networking`, `Json`, `JsonUtilities`, `DeveloperSettings`.

## Packaging this bundle

Suggested bundle contents for S3 upload:
- `Plugins/StrandsInputServer/StrandsInputServer.uplugin`
- `Plugins/StrandsInputServer/Source/StrandsInputServer/**` (all .h/.cpp/.Build.cs)
- `Plugins/StrandsInputServer/Config/DefaultStrandsInputServer.ini`
- `Plugins/StrandsInputServer/README.md` (this file)
- `Tools/StrandsInputClient/send_cmd.ps1`
- `Tools/StrandsInputClient/send_cmd.py` (optional)
- `Tools/StrandsInputClient/RebuildAndTest-StrandsInputServer.ps1`

## License

Internal use. Update this section as needed.
