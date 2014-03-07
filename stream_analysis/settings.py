"""
Add something like this to your settings

ANALYSIS_TIME_FRAME_TASKS = {
    "thermometer": {
        "name": "Thermometer",
        "frame_class_path": "twitter_feels.apps.thermometer.models.TimeFrame",
    },
    "other": {
        "name": "Something Else",
        "frame_class_path": "some.other.OtherTimeFrame",
        "autostart": True,
    },
}
"""

from django.conf import settings

TIME_FRAME_TASKS = getattr(settings, 'ANALYSIS_TIME_FRAME_TASKS', {})
