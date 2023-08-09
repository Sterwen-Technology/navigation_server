#-------------------------------------------------------------------------------
# Name:        date_time_utilities
# Purpose:     Set of functions and classes for handling date and time
#
# Author:      Laurent Carré
#
# Created:     06/08/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------


import time
import datetime


def format_timestamp(timestamp: float, format_str: str) -> str:
    dt = datetime.datetime.fromtimestamp(timestamp)
    return dt.strftime(format_str)

