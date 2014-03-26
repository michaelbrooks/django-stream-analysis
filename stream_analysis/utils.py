"""
Defines the Analysis task and
functions for executing scheduled analysis work
based on the settings in ANALYSIS_TIME_FRAME_TASKS.
"""

import datetime
import logging

import re
from django.utils import importlib, timezone
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
import settings
import django_rq
from rq import get_current_job

logger = logging.getLogger('stream_analysis')
scheduler = django_rq.get_scheduler()


def _import_attribute(name, reload_module=False):
    """Return an attribute from a dotted path name (e.g. "path.to.func")."""
    module_name, attribute = name.rsplit('.', 1)
    module = importlib.import_module(module_name)
    if reload_module:
        reload(module)
    return getattr(module, attribute)


class AnalysisTask(object):
    """
    A class for representing, validating, and scheduling analysis tasks.
    """
    TASK_KEY_REGEX = re.compile('\w+')
    _tasks_config = {}

    def __init__(self, key, taskdef):
        self.key = key
        self.name = taskdef['name']
        self.frame_class_path = taskdef['frame_class_path']
        self.autostart = taskdef.get('autostart', False)

    def validate(self):
        """Verify the values from the settings file."""

        # The keys must be word-like
        if not AnalysisTask.TASK_KEY_REGEX.match(self.key):
            raise ImproperlyConfigured("Key %s in ANALYSIS_TIME_FRAME_TASKS is not word-like." % self.key)

        if not isinstance(self.name, basestring):
            raise ImproperlyConfigured("Name %s in ANALYSIS_TIME_FRAME_TASKS is not a string" % self.name)


    def get_frame_class(self):
        """Get the frame class for this analysis task"""
        return _import_attribute(self.frame_class_path, reload_module=True)

    def get_rq_job(self):
        """Get the job for scheduling analysis of this task."""
        jobs = scheduler.get_jobs()
        for job in jobs:
            if job.meta.get('analysis.task.schedule') and job.meta.get('analysis.task.key') == self.key:
                return job

    def schedule(self, cancel_first=True, start_now=True):
        """Schedule this analysis task."""

        if cancel_first:
            # First cancel any old jobs
            self.cancel()

        # Use the analysis duration as the interval
        interval = self.get_frame_class().DURATION.total_seconds()

        now = datetime.datetime.now()

        job = scheduler.schedule(
            scheduled_time=now,
            interval=interval,
            func=create_frames,
            args=[self.key]
        )

        job.meta['analysis.task.key'] = self.key
        job.meta['analysis.task.schedule'] = True
        job.save()

        logger.info("Scheduled task '%s' every %d seconds", self.name, interval)

        if start_now:
            create_frames.delay(self.key)

        return True

    def cancel(self):
        """Stop this task."""
        job = self.get_rq_job()

        if job:
            scheduler.cancel(job)
            job.delete()
            logger.info("Cancelled task '%s'", self.name)

            return True

        return False

    def clear_queue(self):
        """Clear all queued analyze_frame jobs, and their corresponding frames"""

        frame_class = self.get_frame_class()

        queue = django_rq.get_queue()
        jobs = queue.get_jobs()
        cleared = 0
        frames_deleted = 0
        for job in jobs:
            # Delete jobs for this task but not scheduler jobs
            if (job.meta.get('analysis.task.key') == self.key) and not job.meta.get('analysis.task.schedule'):
                cleared += 1
                job.cancel()

                frame_id = job.meta.get('analysis.frame.id')
                if frame_id:
                    # Delete the corresponding frame
                    try:
                        frame_class.objects.filter(pk=frame_id, calculated=False).delete()
                        frames_deleted += 1
                    except Exception as e:
                        logger.warn(e, exc_info=True)

        return cleared, frames_deleted

    @classmethod
    def get(cls, key=None):
        if key:
            return cls._tasks_config.get(key, None)
        else:
            return cls._tasks_config.values()

    @classmethod
    def initialize(cls):
        """
        Sets up the analysis tasks from the config settings.
        """
        if len(cls._tasks_config):
            raise Exception("AnalysisTasks already initialized")

        for key in settings.TIME_FRAME_TASKS:
            task = AnalysisTask(key, settings.TIME_FRAME_TASKS[key])
            task.validate()
            cls._tasks_config[key] = task

            if task.autostart:
                task.schedule()


########################
# Functions for doing analysis
########################

def _insert_and_queue(task_key, time_frames):
    """
    Inserts the given TimeFrames into the database
    and creates a job to calculate each one.
    """
    for frame in time_frames:
        frame.save()
        job = analyze_frame.delay(task_key=task_key, frame_id=frame.pk)
        job.meta['analysis.task.key'] = task_key
        job.meta['analysis.frame.id'] = frame.pk
        job.save()

    if time_frames:
        logger.info("Created %d time frames", len(time_frames))


@django_rq.job
def create_frames(task_key):
    """
    Creates new time frames that are needed to analyze new stream data.
    Takes as input a task key from the ANALYSIS_TIME_FRAME_TASKS dict.

    It checks the time on the newest stream data and the newest frame.
    If there is room for new frames, it adds these.

    For every new frame, an RQ job is created to analyze it.
    """

    me = get_current_job()
    for job in django_rq.get_queue().get_jobs():
        if job.get_call_string() == me.get_call_string() and job.id != me.id:
            logger.info("Skipping duplicate create_frames job")
            return

    # Get the stream interface
    task = AnalysisTask.get(key=task_key)
    frame_class = task.get_frame_class()
    duration = frame_class.DURATION
    stream = frame_class.STREAM_CLASS()

    if stream.is_stream_empty():
        logger.info("No data to analyze")
        return

    logger.info("Creating frames for %s", task.name)

    new_time_frames = []

    # Get the most recent time frame.
    # We'll start analyzing after this.
    latest_analyzed = frame_class.get_latest_end_time()
    if latest_analyzed is None:
        # There are no frames, so we will start with the first stream item.
        latest_analyzed = stream.get_earliest_stream_time()

        if latest_analyzed is None:
            logger.info("No data to analyze")
            return

        latest_analyzed = latest_analyzed.replace(second=0, microsecond=0)  # chop off the small bits

    # Get the latest stream time. We'll stop analyzing here.
    latest_allowable_start = stream.get_latest_stream_time()
    if latest_allowable_start is None:
        logger.info("No data to analyze")
        return

    # but the frame can stop no later than this time so subtract the duration of the frame
    latest_allowable_start -= duration

    # Add any time frames that fit between the most recent time frame and now
    frame_start = latest_analyzed

    if frame_start < latest_allowable_start:
        logger.info("Analyzing from %s to %s", frame_start, latest_allowable_start)

    while frame_start < latest_allowable_start:
        # Create a new global (no word) time frame
        new_time_frames.append(frame_class(start_time=frame_start))
        frame_start += duration

    _insert_and_queue(task_key, new_time_frames)


def backfill_tasks(task_key):
    """
    Fills in any missing tasks for stream data older than the oldest
    time frame for this task.

    TODO: Make this not defective
    """

    task = AnalysisTask.get(key=task_key)
    frame_class = task.get_frame_class()
    duration = frame_class.DURATION
    stream = frame_class.STREAM_CLASS()

    if stream.is_stream_empty():
        logger.info("No data to analyze")
        return

    logger.info("Backfilling frames for %s", task.name)

    # Done looking forwards, now look backwards
    new_time_frames = []

    # Get the oldest stream data
    # We'll start analysis here
    earliest_allowable_start = stream.get_earliest_stream_time() - duration
    if earliest_allowable_start is None:
        logger.info("No data to analyze")
        return

    # Get the oldest time frame
    # We'll stop analysis here
    try:
        earliest = frame_class.get_earliest_start_time()
    except ObjectDoesNotExist:
        logger.info("No backfilling necessary.")
        return

    # Add any time frames that fit between the oldest stream data and the oldest time frame
    frame_start = earliest - duration
    if frame_start > earliest_allowable_start:
        logger.info("Analyzing from %s to %s", earliest_allowable_start, frame_start)

    while frame_start > earliest_allowable_start:
        # go until we've overshot the stream front
        # Create a new global (no word) time frame
        new_time_frames.append(frame_class(start_time=frame_start))
        frame_start -= duration

    _insert_and_queue(task_key, new_time_frames)


@django_rq.job
def analyze_frame(task_key, frame_id):
    """
    Run the analysis for a frame as part of a task.
    """

    task = AnalysisTask.get(key=task_key)
    frame_class = task.get_frame_class()
    stream = frame_class.STREAM_CLASS()

    frame = frame_class.objects.get(pk=frame_id)

    logger.info("Running %s frame #%s (%s)", task.name, str(frame.pk), frame.start_time)

    # Get the stream data for this time frame
    stream_data = stream.get_stream_data(frame.start_time, frame.end_time)

    frame.mark_started()

    frame.calculate(stream_data)

    frame.mark_cleanup_started()

    frame.cleanup()

    frame.mark_done()

    logger.info('Processed data from %s for %s frame #%s', frame_class.STREAM_CLASS.__name__, frame_class.__name__, str(frame_id))


def get_stream_cutoff_times():
    """
    Find the earliest time that we can safely delete
    for any the stream classes referenced by our analysis tasks.

    Returns a dict of stream classes -> date times.
    """
    tasks = AnalysisTask.get()

    # Find the earliest time that we can safely delete
    # for any the stream classes referenced by our analysis tasks.
    stream_class_memory_cutoffs = {}
    for task in tasks:
        frame_class = task.get_frame_class()
        stream_class = frame_class.STREAM_CLASS

        if stream_class not in stream_class_memory_cutoffs:
            stream_class_memory_cutoffs[stream_class] = timezone.now()

        cutoff_for_this_task = frame_class.get_stream_memory_cutoff()

        if cutoff_for_this_task is None or stream_class_memory_cutoffs[stream_class] is None:
            stream_class_memory_cutoffs[stream_class] = None
        else:
            stream_class_memory_cutoffs[stream_class] = min(cutoff_for_this_task, stream_class_memory_cutoffs[stream_class])

    return stream_class_memory_cutoffs


@django_rq.job(timeout=3600)  # up to 1 hour
def cleanup():
    """
    For all streams, deletes data that have been analyzed
    by all tasks that use those streams.
    """

    stream_class_memory_cutoffs = get_stream_cutoff_times()

    total = 0
    for stream_class, cutoff_time in stream_class_memory_cutoffs.iteritems():
        if cutoff_time is None:
            logger.info("Skipped cleaning for stream %s due to null cutoff time.", stream_class.__name__)
        stream = stream_class()
        deleted = stream.delete_before(cutoff_time)
        logger.info("Cleaned %s stream items before %s from %s.", deleted, cutoff_time, stream_class.__name__)
        total += deleted

    return total


AnalysisTask.initialize()
