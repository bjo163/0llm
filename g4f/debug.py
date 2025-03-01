import sys

logging: bool = False
version_check: bool = True
version: str = None
log_handler: callable = print
logs: list = []

def log(text, file = None):
    if logging:
        log_handler(text, file=file)

def error(error, name: str = None):
    log(
        error if isinstance(error, str) else f"{type(error).__name__ if name is None else name}: {error}",
        file=sys.stderr
    )