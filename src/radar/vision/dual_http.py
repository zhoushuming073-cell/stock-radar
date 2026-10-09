"""Normalize Label Studio's existing out-of-root rejection to an opaque 403."""
from pathlib import Path
from urllib.parse import parse_qs


def guard_local_files(app, document_root):
    root = Path(document_root).resolve()

    def guarded(environ, start_response):
        if environ.get('PATH_INFO') == '/data/local-files/':
            requested = parse_qs(environ.get('QUERY_STRING', '')).get('d', [''])[0]
            try:
                (root / requested).resolve().relative_to(root)
            except (ValueError, OSError):
                body = b'Forbidden local file'
                start_response('403 Forbidden', [('Content-Type', 'text/plain'),
                    ('Cache-Control', 'no-store'), ('Content-Length', str(len(body)))])
                return [body]
        return app(environ, start_response)

    return guarded
