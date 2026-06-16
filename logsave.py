from datetime import datetime
from pathlib import Path
import re
import traceback


APP_DIR = Path(__file__).resolve().parent
LOG_DIR = APP_DIR / "log"
ERROR_LOG = LOG_DIR / "errorlog.txt"
USER_LOG_DIR = LOG_DIR / "userlog"


def _now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _stamp_text():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _ensure_dirs():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    USER_LOG_DIR.mkdir(parents=True, exist_ok=True)


def _safe_name(value):
    text = str(value or "unknown").strip() or "unknown"
    text = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", text)
    return text[:80] or "unknown"


def _clean_message(value):
    text = str(value or "").replace("\r", " ").replace("\n", " | ")
    return text[:4000]


def log_error(kind, message):
    """Append one error/crash line. Logging failures are intentionally ignored."""
    try:
        _ensure_dirs()
        safe_kind = "crash" if kind == "crash" else "error"
        ERROR_LOG.open("a", encoding="utf-8").write(
            "{time}, {kind}, {message}\n".format(
                time=_now_text(),
                kind=safe_kind,
                message=_clean_message(message),
            )
        )
    except Exception:
        pass


def log_exception(kind, exc, context=""):
    try:
        detail = "{} {}: {} | {}".format(
            context,
            exc.__class__.__name__,
            exc,
            traceback.format_exc(limit=8),
        )
        log_error(kind, detail)
    except Exception:
        pass


def start_user_log(username):
    """Create one log file for the current user session."""
    try:
        _ensure_dirs()
        filename = "{}_{}.txt".format(_safe_name(username), _stamp_text())
        path = USER_LOG_DIR / filename
        path.touch(exist_ok=False)
        return filename
    except Exception:
        return ""


def _session_path(username, session_name):
    _ensure_dirs()
    if session_name:
        filename = Path(str(session_name)).name
    else:
        filename = "{}_unknown.txt".format(_safe_name(username))
    if not filename.endswith(".txt"):
        filename += ".txt"
    return USER_LOG_DIR / filename


def log_user_action(username, session_name, action_type, target):
    """Append one user action line. Logging failures are intentionally ignored."""
    try:
        path = _session_path(username, session_name)
        line = "{action}, {time}, {target}\n".format(
            action=_clean_message(action_type),
            time=_now_text(),
            target=_clean_message(target),
        )
        path.open("a", encoding="utf-8").write(line)
    except Exception:
        pass
