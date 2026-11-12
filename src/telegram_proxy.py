"""Optional Xray lifecycle for Telegram's local SOCKS5 proxy."""

import asyncio
import json
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


def vless_config(url: str, port: int = 10808) -> dict:
    """Import VLESS XHTTP + TLS links, preserving XHTTP extra options."""
    try:
        parsed = urlsplit(url)
        query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
        if parsed.scheme != 'vless' or not parsed.hostname or not parsed.port or not parsed.username:
            raise ValueError
        if query.get('type') != 'xhttp' or query.get('security') != 'tls':
            raise ValueError
        extra = json.loads(query.get('extra', '{}'))
        if not isinstance(extra, dict):
            raise ValueError
        xhttp = {
            'path': query.get('path', '/'),
            'mode': query.get('mode', 'auto'),
            'extra': extra,
        }
        if query.get('host'):
            xhttp['host'] = query['host']
        tls = {
            'serverName': query.get('sni', parsed.hostname),
            'fingerprint': query.get('fp', 'chrome'),
        }
        if query.get('alpn'):
            tls['alpn'] = query['alpn'].split(',')
        return {
            'log': {'loglevel': 'warning'},
            'inbounds': [{
                'listen': '127.0.0.1', 'port': port, 'protocol': 'socks',
                'settings': {'auth': 'noauth', 'udp': False},
            }],
            'outbounds': [{
                'protocol': 'vless',
                'settings': {
                    'address': parsed.hostname, 'port': parsed.port,
                    'id': unquote(parsed.username),
                    'encryption': query.get('encryption', 'none'),
                    'flow': query.get('flow', ''),
                },
                'streamSettings': {
                    'method': 'xhttp', 'security': 'tls',
                    'tlsSettings': tls, 'xhttpSettings': xhttp,
                },
            }],
        }
    except (ValueError, TypeError, IndexError):
        raise ValueError(
            'VLESS_URL: нужен корректный профиль VLESS XHTTP + TLS. '
            'Для других транспортов используйте XRAY_CONFIG.'
        ) from None


def validate_proxy(proxy: str, managed: bool = False) -> tuple[str, int] | None:
    if not proxy and not managed:
        return None
    parsed = urlsplit(proxy)
    if parsed.scheme not in {"socks5", "socks4", "http"}:
        raise ValueError(
            "TELEGRAM_PROXY должен быть SOCKS/HTTP URL. Для VLESS настройте "
            "XRAY_CONFIG и TELEGRAM_PROXY=socks5://127.0.0.1:10808"
        )
    if not parsed.hostname or not parsed.port:
        raise ValueError("В TELEGRAM_PROXY нужны адрес и порт")
    if managed and parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("При XRAY_CONFIG TELEGRAM_PROXY должен указывать на localhost")
    return parsed.hostname, parsed.port


async def _port_open(host: str, port: int) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=0.5)
    except (OSError, asyncio.TimeoutError):
        return False
    writer.close()
    await writer.wait_closed()
    return True


@asynccontextmanager
async def xray_proxy(binary: str, config: str, proxy: str, vless_url: str = ''):
    """Start only our Xray process and stop it on failure or shutdown."""
    if vless_url:
        if config:
            raise ValueError('Задайте только VLESS_URL или XRAY_CONFIG')
        endpoint = validate_proxy(proxy, managed=True)
        if endpoint[0] != '127.0.0.1' or urlsplit(proxy).scheme != 'socks5':
            raise ValueError('Для VLESS_URL нужен socks5://127.0.0.1:<порт>')
        generated = vless_config(vless_url, endpoint[1])
        with tempfile.TemporaryDirectory(prefix='nolighttoday-xray-') as directory:
            config_path = Path(directory) / 'config.json'
            config_path.write_text(json.dumps(generated), encoding='utf-8')
            config_path.chmod(0o600)
            async with xray_proxy(binary, str(config_path), proxy):
                yield
        return
    endpoint = validate_proxy(proxy, managed=bool(config))
    if not config:
        yield
        return
    config_path = Path(config).resolve()
    if not config_path.is_file():
        raise FileNotFoundError(f"Не найден конфиг Xray: {config_path}")
    host, port = endpoint
    if await _port_open(host, port):
        raise RuntimeError("Порт Xray уже занят. Для внешнего Xray оставьте XRAY_CONFIG пустым")
    process = await asyncio.create_subprocess_exec(
        binary, "run", "-c", str(config_path),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        for _ in range(60):
            if process.returncode is not None:
                raise RuntimeError(
                    "Xray завершился при запуске. Проверьте: xray run -test -c <конфиг>"
                )
            if await _port_open(host, port):
                break
            await asyncio.sleep(0.25)
        else:
            raise RuntimeError("Xray не открыл локальный прокси за отведённое время")
        yield
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
