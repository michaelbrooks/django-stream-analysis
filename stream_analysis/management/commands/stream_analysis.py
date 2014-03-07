from django.core.management.base import BaseCommand
from stream_analysis.utils import AnalysisTask

class Command(BaseCommand):
    """
    Starts or stops a stream analysis task.
    """

    help = "Starts or stops a stream analysis task."
    args = "<start|stop> <task_key>"
    def handle(self, cmd, task_key, *args, **options):

        task = AnalysisTask.get(key=task_key)
        if not task:
            print "No analysis task matching key %s" % task_key
            print self.usage("stream_analysis")
            return

        if cmd == 'start':
            task.schedule()
            print "%s started." % task.name
        elif cmd == 'stop':
            task.cancel()
            print "%s stopped." % task.name
