#-------------------------------------------------------------------------------
# Name:        nmea0183_to_nmea2k
#              NMEA0183 to NMEA2000 (Python class) conversion
# Author:      Laurent Carré
#
# Created:     21/01/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------


import logging
import datetime
import time
import math
import collections

from router_core import NMEA0183Msg, NMEAInvalidFrame
from generated.nmea2000_classes_gen import (Pgn129025Class, Pgn129026Class, Pgn129029Class, Pgn130306Class,
                                            Pgn128267Class, Pgn128259Class, Pgn127250Class, Pgn129539Class,
                                            Pgn129540Class)
from router_common import IncompleteMessage, NavGenericMsg, N2K_MSG


_logger = logging.getLogger("ShipDataServer." + __name__)

jan170 = datetime.date(1970, 1, 1).toordinal()


def convert_time(time_bytes) -> float:
    # return number of seconds since midnight
    h = int(time_bytes[0:2]) * 3600
    m = int(time_bytes[2:4]) * 60
    s = int(time_bytes[4:6])
    ms = int(time_bytes[7:9]) * 1e-6
    return h + m + s + ms


def convert_date(date_bytes) -> int:
    d = int(date_bytes[0:2])
    m = int(date_bytes[2:4])
    y = int(date_bytes[4:6]) + 2000
    gd = datetime.date(y, m, d)
    return gd.toordinal() - jan170


def convert_latitude(ns_indicator, latitude_bytes) -> float:
    lat = float(latitude_bytes[0:2]) + (float(latitude_bytes[2:7]) / 60.0)
    if ns_indicator == b'S':
        lat = -lat
    return lat


def convert_longitude(ew_indicator, longitude_bytes) -> float:
    long = float(longitude_bytes[0:3]) + (float(longitude_bytes[3:8]) / 60.0)
    if ew_indicator == b'W':
        long = -long
    return long


knots_to_ms = 1852.0 / 3600.0


SatellitesData = collections.namedtuple('SatellitesData',
                                         ['ts', 'nb_sats', 'sats_list', 'hdop', 'pdop', 'vdop'])

SatInView = collections.namedtuple('SatInView', ['prn', 'elevation', 'azimuth', 'snr', 'status'])


class NMEA0183ToNMEA2000Converter:

    def __init__(self, default_source=251):

        self._convert_vector = {
            'RMC': self.convertRMC,
            'VTG': self.convertVTG,
            'MWV': self.convertMWV,
            'DPT': self.convertDPT,
            'GSA': self.convertGSA,
            'GSV': self.convertGSV,
            'GGA': self.convertGGA,
            'VBW': self.convertVBW,
            'HDG': self.convertHDG
        }

        self._sequences = {'GPS': 0, 'Wind': 0, 'Depth': 0, 'Speed': 0, 'Heading': 0, 'GPSDOP': 0, 'GPSGSV': 0}
        self._current_sat_gsv_data = None
        self._current_sat_gsa_data = None
        self._current_gsv_nb_sat = 0
        self._current_gsv_nb_seq = 0
        self._current_gsv_seq = None
        self._current_gsv_sat_count = 0


        self._time_fix = 0.0
        self._date = 0
        self._default_source = default_source
        self._message_stack = []

    def convert(self, msg: NMEA0183Msg):
        _logger.debug("NMEA0183 Converter input message:%s" % msg)
        formatter = msg.formatter().decode()
        try:
            result = self._convert_vector[formatter](msg.fields())
            for msg in result:
                _logger.debug("NMEA Converter output: %s" % msg)
                yield msg
        except KeyError:
            _logger.debug("No converter for formatter %s:" % formatter)
            raise NMEAInvalidFrame

    def convert_to_n2kmsg(self, msg: NMEA0183Msg):
        for conv_msg in self.convert(msg):
            ret_msg = conv_msg.message()
            ret_msg.sa = self._default_source
            _logger.debug("NMEA0183 to NMEA2000 Resulting encoded message:%s" % ret_msg.format2())
            yield NavGenericMsg(N2K_MSG, msg=ret_msg)

    def get_next_sequence(self, seq: str) -> int:
        try:
            seq_id = self._sequences[seq]
            if seq_id == 255:
                seq_id = 0
            else:
                seq_id += 1
            self._sequences[seq] = seq_id
            return seq_id
        except KeyError:
            _logger.error("NMEA0183 missing sequence %s" % seq)
            return 0

    def convertRMC(self, fields: list):
        if fields[1] != b'A':
            raise NMEAInvalidFrame("RMC message not valid")
        pgn129025 = Pgn129025Class()
        pgn129025.latitude = convert_latitude(fields[2], fields[2])
        pgn129025.longitude = convert_longitude(fields[5], fields[4])
        pgn129026 = Pgn129026Class()
        pgn129026.sequence_id = self.get_next_sequence('GPS')
        pgn129026.COG_reference = 0
        pgn129026.SOG = float(fields[6]) * knots_to_ms
        pgn129026.COG = float(fields[7])
        self._time_fix = convert_time(fields[0])
        self._date = convert_date(fields[8])
        return [pgn129025, pgn129026]

    def convertVTG(self, fields: list):
        pgn129026 = Pgn129026Class()
        pgn129026.sequence_id = self.get_next_sequence('GPS')
        pgn129026.COG_reference = 0
        pgn129026.SOG = float(fields[4]) * knots_to_ms
        pgn129026.COG = float(fields[0])
        return [pgn129026]

    def convertMWV(self, fields: list):

        if fields[4] != b'A':
            raise NMEAInvalidFrame
        pgn130306 = Pgn130306Class()
        pgn130306.sequence_id = self.get_next_sequence('Wind')
        pgn130306.wind_angle = float(fields[0])
        if fields[1] == b'R':
            pgn130306.reference = 2
        elif fields[1] == b'T':
            pgn130306.reference = 3
        else:
            raise NMEAInvalidFrame
        if fields[3] == b'N':
            pgn130306.wind_speed = float(fields[2]) * knots_to_ms
        elif fields[3] == b'M':
            pgn130306.wind_speed = float(fields[2])
        elif fields[3] == b'K':
            pgn130306.wind_speed = float(fields[2]) / 3.6
        else:
            raise NMEAInvalidFrame
        return [pgn130306]

    def convertDPT(self, fields: list):
        pgn128267 = Pgn128267Class()
        pgn128267.sequence_id = self.get_next_sequence('Depth')
        pgn128267.depth = float(fields[0])
        if len(fields[1]) > 0:
            pgn128267.offset = float(fields[1])
        else:
            pgn128267.offset = float('nan')
        if len(fields[2]) > 0:
            pgn128267.range = float(fields[2])
        else:
            pgn128267.range = float('nan')
        return [pgn128267]

    def convertGSA(self, fields: list):
        if fields[0] == b'1':
            raise NMEAInvalidFrame
        nb_sats = 0
        sats_list = []
        for f in fields[2:14]:
            if len(f) != 0:
                nb_sats += 1
                sats_list.append(int(f))
        pdop = float(fields[14])
        hdop = float(fields[15])
        vdop = float(fields[16])
        self._current_sat_gsa_data = SatellitesData(time.time(), nb_sats, sats_list, hdop, pdop, vdop)
        pgn129539 = Pgn129539Class()
        pgn129539.sequence_id = self.get_next_sequence('GPSDOP')
        if fields[0] == b'A':
            pgn129539.desired_mode = 3
        else:
            pgn129539.desired_mode = 2
        pgn129539.actual_mode = int(fields[1]) - 1
        pgn129539.HDOP = hdop
        pgn129539.VDOP = vdop
        pgn129539.TDOP = pdop
        return [pgn129539]

    def convertGSV(self, fields: list):
        if self._current_sat_gsv_data is None:
            # no on-going sequence
            if fields[1] != b'1':
                raise IncompleteMessage
            else:
                # start a new sequence
                self._current_sat_gsv_data = []
                self._current_gsv_nb_seq = int(fields[0])
                self._current_gsv_seq = [False for n in range(self._current_gsv_nb_seq)]
                self._current_gsv_nb_sat = int(fields[2])
                self._current_gsv_sat_count = 0

        # now we go over the list
        seq_num = int(fields[1])
        self._current_gsv_seq[seq_num - 1] = True
        field_idx = 3
        for count in range(4):
            prn = int(fields[field_idx])
            field_idx += 1
            if len(fields[field_idx]) > 0:
                elevation = float(fields[field_idx])
            else:
                elevation = float('nan')
            field_idx += 1
            if len(fields[field_idx]) > 0:
                azimuth = float(fields[field_idx])
            else:
                azimuth = float('nan')
            field_idx += 1
            if len(fields[field_idx]) > 0:
                snr = float(fields[field_idx])
            else:
                snr = float('nan')
            field_idx += 1
            # now the satellite usage
            status = 0xf
            if self._current_sat_gsa_data is not None:
                if prn in self._current_sat_gsa_data.sats_list:
                    status = 2
            if status != 2:
                if math.isnan(elevation):
                    status = 0
                else:
                    status = 1
            self._current_sat_gsv_data.append(
                SatInView(prn, elevation, azimuth, snr, status)
            )
            self._current_gsv_sat_count += 1
            if self._current_gsv_sat_count >= self._current_gsv_nb_sat:
                break
        # do we have all the sentences
        if False in self._current_gsv_seq:
            raise IncompleteMessage
        # ok we have all the sentences let's build the NMEA2000 object
        pgn129540 = Pgn129540Class()
        pgn129540.sequence_id = self.get_next_sequence('GPSGSV')
        pgn129540.mode = 0
        pgn129540.sats_in_view = self._current_gsv_nb_sat
        for sat in self._current_sat_gsv_data:
            sat_obj = Pgn129540Class.Satellites_DataClass()
            sat_obj.satellite_number = sat.prn
            sat_obj.elevation = sat.elevation
            sat_obj.azimuth = sat.azimuth
            sat_obj.signal_noise_ratio = sat.snr
            sat_obj.range_residuals = 0x7fffffff
            sat_obj.status = sat.status
            pgn129540.satellites_data.append(sat_obj)
        # ok done => let's clear the data
        self._current_sat_gsv_data = None
        return [pgn129540]

    def convertGGA(self, fields: list):
        if fields[5] == b'0':
            raise NMEAInvalidFrame
        self._time_fix = convert_time(fields[0])
        pgn129029 = Pgn129029Class()
        pgn129029.sequence_id = self.get_next_sequence('GPS')
        pgn129029.latitude = convert_latitude(fields[2], fields[1])
        pgn129029.longitude = convert_longitude(fields[4], fields[3])
        pgn129029.altitude = float(fields[8])
        pgn129029.number_of_sv = int(fields[6])
        if self._date == 0:
            pgn129029.date = 0xffff
        else:
            pgn129029.date = self._date
        pgn129029.time = self._time_fix
        pgn129029.GNSS_type = 0
        pgn129029.method = int(fields[5])
        pgn129029.integrity = 0
        pgn129029.HDOP = float(fields[7])
        pgn129029.geoidal_separation = float(fields[8])
        if self._current_sat_gsa_data is not None:
            pgn129029.PDOP = self._current_sat_gsa_data.pdop
        else:
            pgn129029.PDOP = float('nan')
        pgn129029.nb_ref_stations = 0
        return [pgn129029]

    def convertVBW(self, fields: list):
        pgn128259 = Pgn128259Class()
        pgn128259.sequence_id = self.get_next_sequence('Speed')
        pgn128259.speed_through_water = float(fields[0]) * knots_to_ms
        pgn128259.speed_over_ground = float('nan')
        pgn128259.speed_through_water_reference = 0
        return [pgn128259]

    def convertHDG(self, fields: list):
        pgn127250 = Pgn127250Class()
        pgn127250.sequence_id = self.get_next_sequence('Heading')
        pgn127250.heading = float(fields[0])
        pgn127250.reference = 1
        pgn127250.deviation = float('nan')
        pgn127250.variation = float('nan')
        return [pgn127250]

