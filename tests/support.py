# -*- coding: utf-8 -*-
"""Wspólne drobiazgi testów: raportowanie i atrapa nicegui.

Testy mają działać bez żadnej zewnętrznej biblioteki - także wtedy, gdy nicegui
nie jest zainstalowane (importuje je pakiet caveweb, a nie sama logika).
"""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FAILED = []


def check(name, cond):
    print(("OK  " if cond else "FAIL"), name)
    if not cond:
        FAILED.append(name)


def done():
    print("done" if not FAILED else f"done, {len(FAILED)} FAIL: {', '.join(FAILED)}")
    sys.exit(1 if FAILED else 0)


def ensure_nicegui():
    """Podstawia atrapę nicegui, jeśli biblioteki nie ma w środowisku."""
    try:
        import nicegui  # noqa: F401
        return False
    except ImportError:
        from unittest.mock import MagicMock
        stub = types.ModuleType('nicegui')
        stub.ui = MagicMock(name='ui')
        stub.app = MagicMock(name='app')
        stub.app.storage.user = {}
        stub.run = MagicMock(name='run')
        sys.modules['nicegui'] = stub
        print('(nicegui niedostępne - używam atrapy)')
        return True
