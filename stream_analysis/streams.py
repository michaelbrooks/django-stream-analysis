import logging
from stream_analysis.utils import AnalysisTask

logger = logging.getLogger('stream_analysis')

class AbstractStream(object):

    def is_stream_empty(self):
        """Returns True if the target stream is empty"""
        raise NotImplemented

    def get_earliest_stream_time(self):
        """Returns the earliest time of any stream item"""
        raise NotImplemented

    def get_latest_stream_time(self):
        """Returns the latest time of any stream item"""
        raise NotImplemented

    def get_stream_data(self, start, end):
        """Returns stream data between start datetime and end datetime."""
        raise NotImplemented

    def delete_analyzed(self, num_analyses=None):
        """
        Delete analyzed stream data. Returns the amount of data deleted.

        num_analyses will give the number of configured analysis tasks.
        Using this parameter is optional.
        """
        return 0

    def mark_analyzed(self, stream_data, analysis_task):
        """
        Mark the given stream data as analyzed by the given task.
        """
        pass

