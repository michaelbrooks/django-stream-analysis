
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

    def delete_before(self, cutoff_datetime):
        """
        Delete analyzed stream data older than cutoff_datetime.
        Returns the amount of data deleted.
        """
        return 0

    def count_before(self, cutoff_datetime):
        """
        Counts the amount of stream data older than cutoff_datetime.
        """
        return 0
