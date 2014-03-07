import logging
from logging.config import dictConfig

logger = logging.getLogger('stream_analysis')
if not logger.handlers:
    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "stream_analysis": {
                "level": "DEBUG",
                "class": "logging.StreamHandler",
                },
            },
        "analysis": {
            "stream_analysis": ["analysis"],
            "level": "DEBUG"
        }
    })


from models import BaseTimeFrame, TimedIntervalMixin
from streams import AbstractStream
from utils import AnalysisTask, cleanup

__all__ = ['BaseTimeFrame', 'TimedIntervalMixin',
           'AbstractStream', 'AnalysisTask', 'cleanup']