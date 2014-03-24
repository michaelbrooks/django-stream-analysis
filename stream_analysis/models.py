import datetime
import time

from django.core.exceptions import ObjectDoesNotExist
from django.db import models
import streams


class TimedIntervalMixin(models.Model):
    """
    Provides several convenient methods for working with models that have
    a start_time field and a DURATION property.
    """

    # Tells Django not to make a table for this abstract class.
    class Meta:
        abstract = True

    # A timedelta representing the size of these time frames.
    # They will all be the same.
    DURATION = datetime.timedelta(minutes=1)

    # The time when this time frame starts.
    start_time = models.DateTimeField(db_index=True)

    #######
    # Object properties - for convenience.
    #######

    @property
    def duration(self):
        """
        Get the duration (a timedelta) of this time frame.
        """
        return type(self).DURATION

    @property
    def duration_seconds(self):
        """
        Get the duration in seconds of this time frame.
        """
        return type(self).DURATION.total_seconds()

    @property
    def end_time(self):
        """
        The end time for this time frame.
        """
        return self.start_time + self.duration

    #######
    # Class methods
    #######

    @classmethod
    def get_latest(cls):
        """
        Returns the latest time frame, or None.
        """
        try:
            return cls.objects \
                .latest(field_name='start_time')
        except ObjectDoesNotExist:
            return None

    @classmethod
    def get_earliest(cls):
        """
        Returns the earliest time frame, or None.
        """
        try:
            return cls.objects \
                .earliest(field_name='start_time')
        except ObjectDoesNotExist:
            return None

    @classmethod
    def get_latest_end_time(cls):
        """
        Returns end time of the latest time frame.
        This is much more efficient than get_latest().end_time.
        """
        result = cls.objects.aggregate(latest_start_time=models.Max('start_time'))
        if result['latest_start_time']:
            return result['latest_start_time'] + cls.DURATION
        else:
            return None

    @classmethod
    def get_earliest_start_time(cls):
        """
        Returns the start time of the earliest time frame.
        This is much more efficient than get_earliest().start_time.
        """
        result = cls.objects.aggregate(earliest_start_time=models.Min('start_time'))
        return result['earliest_start_time']

    @classmethod
    def get_in_range(cls, start=None, end=None, calculated=None):
        """
        Returns a queryset that provides all of the frames.

        If start and end are provided, only frames overlapping
        with the time specified will be returned.

        May be filtered to only calculated frames.
        """

        query = cls.objects.all()

        if calculated is not None:
            query = query.filter(calculated=calculated)

        if end:
            query = query.filter(start_time__lt=end)

        if start:
            # We only have a start_time field, so modify "start"
            # to reflect the duration.
            query = query.filter(start_time__gt=start - cls.DURATION)

        return query


class BaseTimeFrame(TimedIntervalMixin, models.Model):
    """
    Describes a frame of analysis, a fixed interval of time.
    It has a start and a duration.

    Any properties added on subclasses should have default
    values set!

    Instructions to use:
    1. Extend the BaseTimeFrame class.
    2. Indicate how often to run the analysis (same as the time frame duration)
    3. Add any fields you need to store per Time Frame.
       You can also store data on separate models,
       if your data is not strictly 1:1 with time frames.
    4. Implement calculate(self, stream_data, task). This is where you do your work.
       At the end, return any data you are done with.
    5. Add any additional functions related to your time frames
       that will make them easier to work with.
    """

    # The class that interfaces with your stream data.
    # Recommended to extend AbstractStream.
    STREAM_CLASS = streams.AbstractStream

    # Tells Django not to make a table for this abstract class.
    class Meta:
        abstract = True

    # True if this frame has been calculated
    calculated = models.BooleanField(default=False)

    # True if we think the data for this frame is missing data
    missing_data = models.BooleanField(default=False)

    # The time in seconds taken by analysis. Before calculated=True, this is analysis start time.
    analysis_time = models.FloatField(default=None, null=True, blank=True)

    # The time in seconds taken for cleanup.
    cleanup_time = models.FloatField(default=None, null=True, blank=True)

    #######
    # Instance methods
    #######

    def calculate(self, stream_data):
        """
        Perform the analysis procedure for this frame of stream data.

        Should be overridden in derived classes.

        The 'stream_data' parameter is the
        all of the stream data enclosed in this time frame.

        Set self.missing_data field to True to indicate
        if the time frame had incomplete data.
        """
        pass

    def cleanup(self):
        """
        Perform any maintenance tasks on the analysis
        data. Probably should not clean up stream data.

        This is separated from the calculate() method only
        so that performance can be tracked separately.

        Remember that you should not depend on TimeFrames being processed
        in chronological order, or even one-at-a-time.
        """
        pass


    @classmethod
    def get_stream_memory_cutoff(cls):
        """
        Get the datetime before which stream data may safely be deleted.

        The default implementation returns the start of the oldest incomplete frame,
        making the assumption that no data needs to be retained for completed frames.
        If the stream class has no incomplete timeframes, returns the time of the latest complete frame.
        If there are no timeframes, returns the None (meaning don't delete anything)

        If you require more data than this to be preserved, make sure to extend this method.
        """
        result = cls.objects.filter(calculated=False)\
            .aggregate(earliest_start_time=models.Min('start_time'))

        if result['earliest_start_time'] is not None:
            return result['earliest_start_time']

        result = cls.objects.filter(calculated=True) \
            .aggregate(latest_start_time=models.Max('start_time'))

        if result['latest_start_time'] is not None:
            return result['latest_start_time']

        return None

    def mark_started(self):
        """
        Saves the current time, indicating analysis is beginning.
        This will be called for you.
        """
        self.analysis_time = time.time()
        self.save()

    def mark_cleanup_started(self):
        """
        Saves the current time, indicating cleanup is beginning.
        This will be called for you.
        """
        self.cleanup_time = time.time()
        self.save()

    def mark_done(self):
        """
        Marks the time frame as calculated.
        This will be called for you. If you override it,
        make sure to do all these things yourself.
        """

        self.calculated = True

        # Calculate the time taken for cleanup
        if self.cleanup_time:
            self.cleanup_time = time.time() - self.cleanup_time

        # Calculate the time taken for analysis
        if self.analysis_time:
            self.analysis_time = time.time() - self.analysis_time

            # Deduct the cleanup time
            if self.cleanup_time:
                self.analysis_time -= self.cleanup_time

        self.save()

    def __unicode__(self):
        """Printing for Django admin / debugging"""
        return "Frame %s" % self.start_time

    @classmethod
    def get_performance_stats(cls, start=None, end=None):
        """Returns the average time taken to analyze and cleanup these time frames."""

        query = cls.get_in_range(start=start, end=end, calculated=True)

        result = query.aggregate(average_analysis_time=models.Avg('analysis_time'),
                                 average_cleanup_time=models.Avg('cleanup_time'))
        return {
            'analysis_time': result['average_analysis_time'],
            'cleanup_time': result['average_cleanup_time'],
        }

    @classmethod
    def count_completed(cls):
        """Counts the number of completed frames of this type."""
        query = cls.get_in_range(calculated=True)
        return query.count()
