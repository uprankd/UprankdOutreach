"""Production entry point: one HTTP process and one outreach worker."""
import fcntl
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'engine'))
import envfile

def validate():
    envfile.load(str(ROOT))
    if os.environ.get('ALMO_SERVER') != '1':
        raise RuntimeError('Set ALMO_SERVER=1 in .env')
    url = urlsplit(os.environ.get('DATABASE_URL', ''))
    if (url.scheme not in ('postgres', 'postgresql') or
            url.hostname not in ('127.0.0.1', 'localhost', '::1') or
            not url.path.strip('/') or url.query or url.fragment):
        raise RuntimeError('DATABASE_URL must name a local PostgreSQL database without query overrides')
    if not os.environ.get('ALMO_PUBLIC_URL', '').startswith('https://'):
        raise RuntimeError('Set an HTTPS ALMO_PUBLIC_URL')
    if os.environ.get('ALMO_INSECURE_COOKIES'):
        raise RuntimeError('Remove ALMO_INSECURE_COOKIES on the server')
    data = os.environ.get('ALMO_DATA_DIR', '')
    if not data or not Path(data).is_absolute():
        raise RuntimeError('Set an absolute ALMO_DATA_DIR outside the repository')
    os.umask(0o077)
    os.environ.setdefault('TZ', 'Europe/Riga')
    time.tzset()
    Path(data).mkdir(parents=True, exist_ok=True)
    lock = open(Path(data) / 'server.lock', 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError('Another production instance is already running') from None
    return lock

def main():
    lock = validate()  # Keep the lock open throughout the process lifetime.
    import app as almo
    from waitress import serve
    if not almo.auth.enabled():
        raise RuntimeError('Configure Google OAuth before starting the server')
    if almo.db.KIND != 'postgres':
        raise RuntimeError('PostgreSQL is required')
    almo.db.init()
    if not os.environ.get('ALMO_NO_WORKER'):
        almo.worker.start()
    serve(almo.app, host='127.0.0.1', port=almo.PORT, threads=4,
          trusted_proxy='127.0.0.1',
          trusted_proxy_headers={'x-forwarded-for', 'x-forwarded-proto', 'x-forwarded-host'},
          max_request_body_size=50 * 1024 * 1024)
    lock.close()

if __name__ == '__main__':
    main()
