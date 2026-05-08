"""Module-level dependency injection for Slingo QA tools.

The worker sets these at startup so tool handlers can access shared resources.
"""

from typing import Optional

_screen_db = None
_mcp_manager = None


def set_screen_db(db) -> None:
    global _screen_db
    _screen_db = db


def get_screen_db():
    return _screen_db


def set_mcp_manager(manager) -> None:
    global _mcp_manager
    _mcp_manager = manager


def get_mcp_manager():
    return _mcp_manager
