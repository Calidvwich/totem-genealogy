# Startup config

`startup.json` stores the default launch parameters for the local WSL + TotemDB + FastAPI stack.

If a machine needs different values, copy `startup.json` to `startup.local.json` and edit the copy. The startup script prefers `startup.local.json` when it exists.

Common fields:

- `wsl.distro`: WSL distribution name, for example `Ubuntu-18.04`.
- `wsl.database_user`: Linux user used to start Totem, usually `totem`.
- `wsl.app_user`: Linux user used to run the web app.
- `totem.port`: Totem listen port, currently `55432`.
- `totem.database`: project database name, currently `genealogy`.
- `app.project_dir`: project path inside WSL.
- `app.python`: Python executable relative to `app.project_dir`.
- `app.port`: Uvicorn web port.
- `app.background`: when `true`, start Uvicorn in the WSL background so the shortcut window can close.
- `app.pid_file`: WSL path used to store the Uvicorn PID.
- `app.log_file`: WSL path used to store Uvicorn logs.
