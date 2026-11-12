import asyncio
import json
from urllib.parse import urlencode
from unittest.mock import AsyncMock

import pytest

import telegram_proxy as proxy


def test_vless_xhttp_tls_link():
    options = {'type': 'xhttp', 'security': 'tls', 'sni': 'cover.example',
               'fp': 'chrome', 'path': '/tunnel/', 'mode': 'auto',
               'extra': json.dumps({'noGRPCHeader': True}), 'encryption': 'none'}
    config = proxy.vless_config('vless://test-id@server.example:443?' + urlencode(options))
    outbound, = config['outbounds']
    assert outbound['settings']['address'] == 'server.example'
    assert outbound['settings']['id'] == 'test-id'
    assert outbound['streamSettings']['tlsSettings']['serverName'] == 'cover.example'
    assert outbound['streamSettings']['xhttpSettings'] == {
        'path': '/tunnel/', 'mode': 'auto', 'extra': {'noGRPCHeader': True}}
    assert config['inbounds'][0]['listen'] == '127.0.0.1'
    with pytest.raises(ValueError, match='VLESS_URL'):
        proxy.vless_config('vless://secret@server.example:443?type=unknown')


def test_proxy_validation():
    assert proxy.validate_proxy("") is None
    assert proxy.validate_proxy("socks5://127.0.0.1:10808", True) == ("127.0.0.1", 10808)
    for url in ("vless://secret@example.com:443", "socks5://example.com", ""):
        with pytest.raises(ValueError):
            proxy.validate_proxy(url, True)
    with pytest.raises(ValueError):
        proxy.validate_proxy("socks5://example.com:10808", True)


def test_unmanaged_proxy_does_not_start_process(monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', create)

    async def run():
        async with proxy.xray_proxy('xray', '', 'socks5://localhost:10808'):
            pass

    asyncio.run(run())
    create.assert_not_called()


def test_xray_cleanup_on_application_error(tmp_path, monkeypatch):
    config = tmp_path / 'xray.json'
    config.write_text('{}')
    process = type('Process', (), {
        'returncode': None,
        'terminate': lambda self: setattr(self, 'returncode', 0),
        'wait': AsyncMock(return_value=0),
    })()
    create = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', create)
    monkeypatch.setattr(proxy, '_port_open', AsyncMock(side_effect=[False, True]))

    async def run():
        async with proxy.xray_proxy('xray', str(config), 'socks5://127.0.0.1:10808'):
            raise RuntimeError('application failed')

    with pytest.raises(RuntimeError, match='application failed'):
        asyncio.run(run())
    assert process.returncode == 0
    assert create.call_args.args == ('xray', 'run', '-c', str(config.resolve()))


def test_busy_port_prevents_start(tmp_path, monkeypatch):
    config = tmp_path / 'xray.json'
    config.write_text('{}')
    create = AsyncMock()
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', create)
    monkeypatch.setattr(proxy, '_port_open', AsyncMock(return_value=True))

    async def run():
        async with proxy.xray_proxy('xray', str(config), 'socks5://127.0.0.1:10808'):
            pass

    with pytest.raises(RuntimeError, match='уже занят'):
        asyncio.run(run())
    create.assert_not_called()
