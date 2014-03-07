from django.core.management.base import BaseCommand
from stream_analysis.utils import cleanup

class Command(BaseCommand):
    """
    Removes streaming data we no longer need.
    """

    help = "Removes streaming data we no longer need."

    def handle(self, *args, **options):
        cleanup()
