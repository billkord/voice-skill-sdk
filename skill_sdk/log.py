#
# voice-skill-sdk
#
# (C) 2021, Deutsche Telekom AG
#
# This file is distributed under the terms of the MIT license.
# For details see the file LICENSE in the top directory.
#

"""Logging"""

import os
import re
import time
import json
import logging.config
from traceback import format_exc
from typing import Dict, Optional

from skill_sdk import config


def setup_logging(
    log_level: Optional[int] = None, log_format: Optional[config.FormatType] = None
):
    """
    Set log level either to the level provided as argument
    or get it from LOB_LEVEL environment var

    :param log_level:
    :param log_format:
    :return:
    """

    log_level = log_level or config.settings.LOG_LEVEL
    log_format = log_format or config.settings.LOG_FORMAT

    logging.getLogger().setLevel(log_level)
    logging.basicConfig(level=log_level)

    try:
        logging.config.dictConfig(get_config_dict(log_level, log_format))
    except KeyError:
        raise RuntimeError("Invalid log format: %s", repr(log_format))

    # Patch Uvicorn logger default formats and level
    if isinstance(log_level, str):
        log_level = logging.getLevelName(log_level)
    for _ in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi"):
        logger = logging.getLogger(_)
        #
        # Change loggers level to target,
        # unless the target level is DEBUG and Uvicorn loggers level is TRACE:
        # we don't have TRACE logging level
        #
        if not (log_level == logging.DEBUG and logger.level < logging.DEBUG):
            logger.setLevel(log_level)
        if log_format == config.FormatType.GELF:
            for handler in logger.handlers:
                handler.setFormatter(CloudGELFFormatter())


def tracing_headers() -> Dict:
    """Extract tracing headers from Starlette's context"""
    from skill_sdk.middleware import HeaderKeys, context

    try:
        return {
            key: context.data[key]
            for key in HeaderKeys
            if context.data[key] is not None
        }
    # If we're not inside a request
    except RuntimeError:
        return {}


class CloudGELFFormatter(logging.Formatter):
    """Graylog Extended Format (GELF) formatter"""

    def format(self, record: logging.LogRecord):
        from skill_sdk.middleware import HeaderKeys

        headers = tracing_headers()

        # Cloud log record format
        line = {
            # Timestamp in milliseconds
            "@timestamp": int(round(time.time() * 1000)),
            # Log message level
            "level": record.levelname,
            # Process id
            "process": os.getpid(),
            # Thread id
            "thread": str(record.thread),
            # Logger name
            "logger": record.name,
            # Log message
            "message": record.getMessage(),
            # Trace id
            "traceId": headers.get(HeaderKeys.trace_id, None),
            # Span id
            "spanId": headers.get(HeaderKeys.span_id, None),
            # Testing flag
            "testing": str(headers.get(HeaderKeys.testing_flag, False)).lower()
            in ("true", "1"),
            # Tenant: a skill is not aware of tenant
            "tenant": headers.get(HeaderKeys.tenant_id, None),
            # Magenta Transaction Id
            "magentaTransactionId": headers.get(
                HeaderKeys.magenta_transaction_id, None
            ),
        }

        if record.exc_info:
            line["_traceback"] = format_exc()

        return json.dumps(line)


def get_config_dict(log_level: int, log_format: config.FormatType) -> Dict:
    """Logging configuration dictionary"""

    conf = {
        "gelf": {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {"class": "skill_sdk.log.CloudGELFFormatter"},
            },
            "handlers": {
                "default": {
                    "level": log_level,
                    "formatter": "standard",
                    "class": "logging.StreamHandler",
                },
            },
            "loggers": {
                "": {"handlers": ["default"], "level": log_level, "propagate": True},
            },
        },
        "human": {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s %(levelname)-8s %(name)s - %(message)s",
                }
            },
            "handlers": {
                "default": {
                    "level": log_level,
                    "formatter": "standard",
                    "class": "logging.StreamHandler",
                },
            },
            "loggers": {
                "": {"handlers": ["default"], "level": log_level, "propagate": True},
            },
        },
    }

    return conf[log_format]


def patch_logger():
    """
    Patch the `logging.Logger.isEnabledFor` method.

    :return:
    """

    from skill_sdk.middleware import HeaderKeys, context

    _super = logging.Logger.isEnabledFor

    def is_enabled_for(instance: logging.Logger, level):
        """
        Return True if "X-User-Debug-Log" flag is set

        :param instance:    logging.Logger instance
        :param level:       logging level
        :return:
        """
        try:
            return context.data[HeaderKeys.user_debug_log] or _super(instance, level)
        except (KeyError, RuntimeError):
            return _super(instance, level)

    logging.Logger.isEnabledFor = is_enabled_for


patch_logger()


###############################################################################
#                                                                             #
#   Optional formatter for GunicornLogger                                     #
#                                                                             #
###############################################################################
try:
    from gunicorn.glogging import Logger

    class GunicornLogger(Logger):
        """Gunicorn logger that formats log messages with CloudGELFFormatter"""

        def setup(self, cfg):
            self.loglevel = config.settings.LOG_LEVEL
            self.error_log.setLevel(self.loglevel)
            self.access_log.setLevel(self.loglevel)

            if config.settings.LOG_FORMAT == config.FormatType.GELF:
                self._set_handler(self.error_log, cfg.errorlog, CloudGELFFormatter())
                self._set_handler(self.access_log, cfg.errorlog, CloudGELFFormatter())

except ModuleNotFoundError:  # pragma: no cover
    pass


###############################################################################
#                                                                             #
#  Limit log message size, and hide tokens from logs                          #
#                                                                             #
###############################################################################
JWT_REGEX = re.compile(r"^eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9._-]*")


def _trim(s):
    """Trim long string to LOG_ENTRY_MAX_STRING(+3) length"""

    return (
        s
        if not isinstance(s, str) or len(s) < config.settings.LOG_ENTRY_MAX_STRING
        else s[: config.settings.LOG_ENTRY_MAX_STRING] + "..."
    )


def _copy(d, hide_tokens: bool = False):
    """
    Recursively copy dictionary values, trimming long strings, and hiding possible JWT tokens
    """

    if isinstance(d, dict):
        return {k: _copy(v) for k, v in d.items()}
    elif isinstance(d, (list, tuple)):
        return [_copy(v) for v in d]
    else:
        return _trim(JWT_REGEX.sub("eyJ*****", d) if hide_tokens else d)


def prepare_for_logging(record, hide_tokens: bool = False):
    """
    Trim long strings before logging a record

    :param record:      value to log
    :param hide_tokens: specifies if JWT-like values should be replaced by asterisks
    :return:
    """
    return _copy(record, hide_tokens)
