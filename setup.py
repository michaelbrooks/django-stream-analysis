import os
from setuptools import setup

# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name='django-stream-analysis',
    version='0.1.0',
    packages=['stream_analysis'],
    url='http://github.com/michaelbrooks/django-stream-analysis',
    license='MIT',
    author='Michael Brooks',
    author_email='mjbrooks@uw.edu',
    description='A Django app for running periodic analysis of streaming data, such as tweets.',
    long_description=read('README.md'),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Topic :: Utilities",
        "License :: OSI Approved :: MIT License",
    ],
    install_requires=[
        "django",
        "rq == 0.3.13",
        "django-rq >= 0.6.1",
        "rq-scheduler >= 0.4.0"
    ]
)
