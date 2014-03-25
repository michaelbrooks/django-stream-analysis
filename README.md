Django Stream Analysis
======================

Django app for running periodic analysis of streaming data, such as tweets.

To use this you have to define a simple interface to your
streaming data source by extending `stream_analysis.AbstractStream`.

You then define the actual analysis that you want to do
by extending `stream_analysis.BaseTimeFrame`.

Once you set everything up, this app will manage periodically
calling your analysis code as new data streams in.

This application relies on [RQ](https://github.com/nvie/rq/),
[rq-scheduler](https://github.com/ui/rq-scheduler),
and [django-rq](https://github.com/ui/django-rq) to manage and execute analysis.


Installation
------------

Install with pip:

```bash
pip -e git+https://github.com/michaelbrooks/django-stream-analysis.git#egg=django-stream-analysis
```

Add to `INSTALLED_APPS` in your Django settings file:

```python
INSTALLED_APPS = (
    # other apps
    "stream_analysis",
)
```


Streaming Data Interface
------------------------

Define a class with certain methods that this app
needs to access your streaming data. You can extend
`stream_analysis.AbstractStream`.
Below is an example of how this might be done
if your streaming data was stored in a
database table of tweets, with a `Tweet` Django model:

```python
class TweetStream(stream_analysis.AbstractStream):
    """Stream interface for Tweets"""

    def is_stream_empty(self):
        return Tweet.objects.count() == 0

    def get_earliest_stream_time(self):
        return Tweet.get_earliest_created_at()

    def get_latest_stream_time(self):
        return Tweet.get_latest_created_at()

    def get_stream_data(self, start, end):
        return Tweet.get_created_in_range(start, end) \
            .order_by('created_at')

    def delete_before(self, cutoff_datetime):
        if cutoff_datetime is None:
            return 0
        analyzed = Tweet.objects.filter(created_at__lte=cutoff_datetime)
        count = analyzed.count()
        analyzed.delete()
        return count

    def count_before(self, cutoff_datetime):
        if cutoff_datetime is None:
            return 0
        analyzed = Tweet.objects.filter(start_time__lte=cutoff_datetime)
        return analyzed.count()
```

Some documentation of what these methods should do
is located in the `AbstractStream` class.

Defining Time Frames
--------------------

In order to analyze your streaming data, you'll
need to define a new model that extends `stream_analysis.BaseTimeFrame`.

In this app, a "Time Frame" is associated with a fixed duration
of streaming data with a particular start and end time.
Regardless of the rate at which streaming data actually arrives,
new Time Frames will be instantiated whenever the specified duration of time has passed.
When a new Time Frame is instantiated, an RQ job is created
that will execute your analysis on the data
associated with that Time Frame.

Below is an example of a minimal Time Frame model that just counts the streaming data.

You must set STREAM_CLASS to point to the stream interface class
you defined earlier.
You should also set the `DURATION` of your
time frames, which determines how often your analysis will be run,
and how much stream time each one covers.

You must override the `calculate(self, stream_data)` method,
where you actually do some operations on the stream data for this time frame.

Optionally, you may attach new fields to your Time Frame if there
are data you want to store every `DURATION` of time.
You can do whatever you like inside the calculate() method,
including the creation or modification of model data from other tables.
The `cleanup(self)` method can be filled in to remove any
old data accumulated elsewhere by the time frame analysis.
It will be called after `calculate()`.

To ensure that stream data is not saved for too long,
the `get_stream_memory_cutoff()` class method is used to
determine the earliest stream data that your time frame
still needs. You may optionally override this.

```python
class DemoTimeFrame(stream_analysis.BaseTimeFrame):

    # This works with the TweetStream
    STREAM_CLASS = TweetStream

    # Analyze every 15 seconds
    DURATION = timedelta(seconds=15)

    # Store the total tweet count in this time frame
    item_count = models.IntegerField(default=0)

    def calculate(self, stream_data):
        # store the result of our "calculation"
        self.item_count = len(stream_data)
```

There is more documentation in the BaseTimeFrame model itself.

Note: It is best not to rely on calculations for Time Frames executing in order.

Configuring Analysis Tasks
--------------------------

Once you have defined your stream interface and Time Frame model,
you have to point the `stream_analysis` app at it.

Add an entry like the following to your Django settings:

```python
ANALYSIS_TIME_FRAME_TASKS = {
    "demo": {
        "name": "Demo Analysis",
        "frame_class_path": "import.path.to.DemoTimeFrame",
        "autostart": True
    },
}
```

You may define multiple analysis tasks in this dictionary.

The `frame_class_path` should point to your time frame class.

If you set `autostart` to True, then your
task will be scheduled to begin as soon as the stream_analysis module
is imported. Otherwise you must start your task manually (see below).


Starting Your Analyses
----------------------

To run your analyses, you should launch a running RQ scheduler instance.
More information about rq-scheduler can be found [here](http://github.com/ui/rq-scheduler).

```bash
$ ./manage.py rqscheduler
```

You will also need to launch one or more RQ worker processes.
See the documentation for [django-rq](https://github.com/ui/django-rq)
and [RQ](http://github.com/nvie/rq) for more details.

```bash
$ ./manage.py rqworker
```

If your analysis task is not configured to be "autostart", you
will need to use the `stream_analysis` command to start or stop it:

```bash
$ ./manage.py stream_analysis start demo
$ ./manage.py stream_analysis stop demo
```

You can also control your analysis tasks in Python:

```python
task = stream_analysis.AnalysisTask.get(key="demo")
task.schedule()
task.cancel()
```


Extra Features
--------------

There are a couple of additional features/considerations.

### Auto Reload
Whenever your analysis task is executed, your Time Frame class
will be reloaded, meaning that you can edit your Time Frame code
without having to restart your RQ workers.

### TimeIntervalMixin
The mixin `TimedIntervalMixin` can be added to your model
if you would like to create a Time Frame-like model
that does not fully extend the `BaseTimeFrame`.
`TimeIntervalMixin` confers a `DURATION` class field, a `start_time`,
and several convenient properties and methods.

### Removing Analyzed Data
Running the command `./manage.py cleanup_streams` will cause stream
data that has been analyzed (according to the stream interface you are using)
to be deleted.

You can also accomplish this by calling `stream_analysis.cleanup()`.
