from __future__ import annotations

import logging
import re
import sys
from datetime import datetime, timedelta
from typing import Optional


def setup_logging(name: str = "peru_job_hunter", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(handler)
    return logger


def normalize_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_relative_date(text: str) -> Optional[datetime]:
    text = text.lower().strip()
    now = datetime.now()

    patterns = [
        (r"hace\s+(\d+)\s+minuto", "minutes"),
        (r"hace\s+(\d+)\s+hora", "hours"),
        (r"hace\s+(\d+)\s+d[ií]a", "days"),
        (r"hace\s+(\d+)\s+semana", "weeks"),
        (r"hace\s+(\d+)\s+mes", "months"),
        (r"(\d+)\s+minute", "minutes"),
        (r"(\d+)\s+hour", "hours"),
        (r"(\d+)\s+day", "days"),
        (r"(\d+)\s+week", "weeks"),
        (r"(\d+)\s+month", "months"),
        (r"hoy", None),
        (r"ayer", None),
    ]

    for pattern, unit in patterns:
        match = re.search(pattern, text)
        if match:
            if pattern == r"hoy":
                return now
            if pattern == r"ayer":
                return now - timedelta(days=1)
            value = int(match.group(1))
            if unit == "minutes":
                return now - timedelta(minutes=value)
            if unit == "hours":
                return now - timedelta(hours=value)
            if unit == "days":
                return now - timedelta(days=value)
            if unit == "weeks":
                return now - timedelta(weeks=value)
            if unit == "months":
                return now - timedelta(days=value * 30)
    return None


def normalize_url(url: str) -> str:
    url = re.sub(r"[?&](utm_\w+|ref|trk|tracking\w*)=[^&]*", "", url)
    url = re.sub(r"\?$", "", url)
    return url.rstrip("/")
