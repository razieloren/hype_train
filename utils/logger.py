import os
import datetime

import logging
import logging.handlers


def setup_logging(name: str, logs_dir: str, verbose_logs: bool = True, timed_logs: bool = True,
                  file_logging: bool = False) -> logging.Logger:
    level = logging.DEBUG
    if not verbose_logs:
        level = logging.ERROR
    if timed_logs:
        console_formatter = logging.Formatter("[%(asctime)s] %(levelname)10s | %(name)30s | %(message)s")
    else:
        console_formatter = logging.Formatter("%(name)50s | %(message)s")
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(console_formatter)

    logger = logging.getLogger().getChild(name)
    logger.setLevel(logging.DEBUG)

    logger.addHandler(stream_handler)
    if file_logging:
        os.makedirs(logs_dir, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            os.path.join(logs_dir, f'{name}.log'), when='h', interval=24, backupCount=7)
        file_formatter = logging.Formatter("[%(asctime)s] %(levelname)10s | %(name)30s | %(message)s")
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

    logger.info(f'{name} logging session started at {datetime.datetime.utcnow().isoformat()}')
    return logger
