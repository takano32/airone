#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" upload_yaml.py


"""

import datetime
import os
import sys

from django import setup
from django.test.client import Client
from django.urls import reverse
from optparse import OptionParser
from datetime import datetime

from statistics import mean, stdev

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/..' )
os.environ["DJANGO_SETTINGS_MODULE"] = 'airone.settings'


def get_options():
    usage = "usage: %prog [options] FILE1 FILE2 ..."
    parser = OptionParser(usage=usage)

    parser.add_option("-u", "--username", type=str, dest="username", default="racktables",
                      help="AirOne username")
    parser.add_option("-p", "--password", type=str, dest="password", default="demo",
                      help="AirOne password")
    parser.add_option("-d", "--debug", dest="debug", default=False, action="store_true",
                      help="show statistics information after import processing")

    (options, args) = parser.parse_args()
    return (options, args)
        
def main():
    options, args = get_options()

    client = Client()
    client.login(username=options.username, password=options.password)
    time_data = []

    for i in range(len(args)):
        filepath = args[i]
        start_time = datetime.now()

        sys.stdout.write("(%4d/%4d) upload %s(%s) " % (i, len(args), filepath, start_time))
        sys.stdout.flush()

        with open(filepath, 'r') as fp:
            client.post(reverse('dashboard:do_import'), {'file': fp})

        exit_time = datetime.now()
        diff_time = exit_time - start_time
        sys.stdout.write("done(%s) [diff: %s]\n" % (exit_time, diff_time))

        time_data.append(diff_time.seconds)

    # show statistics results
    if options.debug:
        print('=== statistics results [seconds] ===')
        print('total: %f' % sum(time_data))
        print('average: %f' % mean(time_data))
        print('SD: %f' % stdev(time_data))
        
if __name__ == "__main__":
    # setup Django configuraiton
    setup()
    main()
