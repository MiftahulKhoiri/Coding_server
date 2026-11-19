"""Logging ke file berputar (logs/) + konsol. Token/password disensor."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SECRET_RE = re.compile(r"(?i)(password|token|secret|authorization|api_key)([\"']?\s*[:=]\s*[\"']?)([^\s\"',&]+)")
_URL_CRED_RE = re.compile(r"(https?://)([^/@\s:]+):([^/@\s]+)@")


def redact(text: str) -> str:
    text = _SECRET_RE.sub(lambda m: m.group(1) + m.group(2) + "***", text)
    return _URL_CRED_RE.sub(r"\1***:***@", text)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def setup_logging(logs_dir: Path, level: int = logging.INFO) -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("coding_server")
    if getattr(logger, "_cs_configured", False):
        return logger
    logger.setLevel(level)
    fmt = RedactingFormatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    fh = RotatingFileHandler(logs_dir / "server.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    audit = logging.getLogger("coding_server.audit")
    ah = RotatingFileHandler(logs_dir / "audit.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    ah.setFormatter(fmt)
    audit.addHandler(ah)
    logger._cs_configured = True  # type: ignore[attr-defined]
    return logger


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger("coding_server" + ("." + name if name else ""))
