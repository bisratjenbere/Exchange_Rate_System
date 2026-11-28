import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

workers = 1
worker_class = "sync"
worker_connections = 100
timeout = 120
keepalive = 5

accesslog = "-"
errorlog = "-"
loglevel = "info"

proc_name = "exchange-rates-api"

daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

def post_fork(server, worker):
    try:
        from api.app import _reset_pool
        _reset_pool()
    except ImportError as exc:
        server.log.warning("post_fork: could not import _reset_pool: %s", exc)
    except AttributeError as exc:
        server.log.warning("post_fork: _reset_pool not found: %s", exc)
    except RuntimeError as exc:
        server.log.warning("post_fork: _reset_pool failed: %s", exc)

