# -------------------------------------------------------------------------------
# Name:        constants_conversion.py
# Purpose:    Global constants and conversion functions
#
# Author:      Laurent Carré
#
# Created:     14/09/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import datetime
import math

nautical_mille = 1852.0

mps_to_knots = 3600.0 / nautical_mille

radian_to_deg = 180. / math.pi

n2k_initial_date = datetime.datetime(1970, 1 , 1)

def n2ktime_to_datetime(date: int, time_s: float):
    '''
    Convert a int pair from a NMEA2000 into a datetime
    '''
    return n2k_initial_date + datetime.timedelta(days=date, seconds=time_s)





