from django.core.management.base import BaseCommand
from stream_analysis.utils import AnalysisTask

class Command(BaseCommand):
    """
    Deletes queued jobs for the given analysis task, or for all.
    """

    args = "<task_key>"
    help = "Deletes queued jobs for the given analysis task."

    def handle(self, task_key=None, *args, **options):

        if not task_key:
            print "Must specify an analysis task key from:"
            tasks = AnalysisTask.get()
            for task in tasks:
                print "\t* %s : %s" % (task.key, task.name)

        task = AnalysisTask.get(key=task_key)
        if not task:
            print "No analysis task matching key %s" % task_key
            print self.usage("stream_analysis")
            return

        cleared = task.clear_queue()
        print "Cleared %d jobs for task %s" % (cleared, task_key)
