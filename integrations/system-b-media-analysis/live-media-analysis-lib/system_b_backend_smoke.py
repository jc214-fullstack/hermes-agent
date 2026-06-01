"""Manual smoke harness for media-analysis-z-backend.

This does not restart Hermes. It imports the hook from disk and invokes handle()
with a synthetic Discord context.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

HOOK = Path('/home/imagi/.hermes/hooks/media-analysis-z-backend/handler.py')


def load_hook():
    spec = importlib.util.spec_from_file_location('system_b_backend_hook_smoke', HOOK)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'could not load {HOOK}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def run(url: str, thread_id: str = 'system-b-backend-smoke') -> None:
    module = load_hook()
    await module.handle('agent:start', {
        'platform': 'discord',
        'chat_id': thread_id,
        'parent_chat_id': '1509517024345194617',
        'user_id': 'smoke-user',
        'session_id': thread_id,
        'message': url,
    })


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        raise SystemExit('usage: python system_b_backend_smoke.py URL [THREAD_ID]')
    asyncio.run(run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else 'system-b-backend-smoke'))
