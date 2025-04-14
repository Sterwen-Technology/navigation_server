#-------------------------------------------------------------------------------
# Name:        gnss_data
#              Acquisition of GNSS NMEA0183 data with state management and N2K conversion
# Author:      Laurent Carré
#
# Created:     11/04/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import datetime
from dataclasses import dataclass
import math
import time
import queue


from navigation_server.router_core import NMEA0183Msg
from navigation_server.nmea2000_datamodel import NMEA2000DecodedMsg
from navigation_server.generated.nmea2000_classes_gen import (Pgn129025Class, Pgn129026Class, Pgn129029Class,
                                             Pgn129539Class, Pgn129540Class)

_logger = logging.getLogger("ShipDataServer." + __name__)

jan170 = datetime.date(1970, 1, 1).toordinal()

knots_to_ms = 1852.0 / 3600.0
# 2024/09/21 convert direct to SI
deg_to_radian = math.pi / 180.


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


@dataclass
class SatellitesInView:
    svn: int            # satellites number
    elevation: float    # elevation in radian
    azimuth: float      # azimuth in radian
    cno: float            # signal strength C/NO 0-99
    ts: float           # last time we have seen it
    status: int = 0     # used in fix



@dataclass
class GNSSSystem:
    name: str
    talker: str
    systemId: int
    UBX_gnssid: int
    n2k_fix: int


@dataclass
class Constellation:
    gnss: GNSSSystem             # constellation numeric ID
    ts: float           # last TS seen
    nb_satellites: int  # number of satellites in view for the constellation
    satellites: dict
    gsv_nb_seq: int
    gsv_seq_recv: list
    gsv_in_progress: bool = False

    def __init__(self, gnss):
        self.gnss = gnss
        self.ts = 0
        self.nb_satellites = 0
        self.gsv_nb_seq = 0
        self.satellites = {}
        self.gsv_seq_recv = None
        self.gsv_in_progress = False

    def update_status(self, sats_in_use: list):
        for sats in self.satellites.values():
            if sats.svn in sats_in_use:
                sats.status = 2
            elif sats.elevation != float('nan'):
                sats.status = 1
            else:
                sats.status = 0


class N2KForwarder:

    def __init__(self, pgn_set: set, output_queue: queue.Queue):
        self._pgn_set = pgn_set
        self._output_queue = output_queue

    def push(self, msg:NMEA2000DecodedMsg):
        if msg.pgn in self._pgn_set:
            n2k_msg = msg.message()
            try:
                self._output_queue.put(n2k_msg, block=True, timeout=0.5)
            except queue.Full:
                _logger.error("N2KForwarder queue Full")

    def pgn_in_set(self, pgn:int) -> bool:
        return pgn in self._pgn_set


gnss_systems = ( GNSSSystem('GPS', 'GP', 1, 0, 1),
                   GNSSSystem('SBAS', 'GP', 1, 1, 1),
                   GNSSSystem('Galileo', 'GA', 3, 2, 8),
                   GNSSSystem('Beidou', 'GB',4, 3, 0),
                   GNSSSystem('QZSS', 'GQ',5, 5, 0),
                   GNSSSystem('GLONASS', 'GL',2, 6, 2),
                   GNSSSystem('NavIC', 'GI',6, 7, 0)
                   )

gnss_sys_dict = dict([(s.talker, s) for s in gnss_systems])
signal_id_table = dict([(s.systemId, s.talker) for s in gnss_systems])

class GNSSDataManager:
    """
    The class manages all global data for the GNSS
    Visible constellations and satellites
    Current position
    fix
    """

    def __init__(self):
        """
        All units herebelow are the one from NMEA2000 so ISO standard
        """
        self._fix = False
        self._fix_quality = None
        self._mode = 0
        self._signal_id = 0         # signal ID (constellation for the fix)
        self._fix_time = 0.0
        self._latitude = 0.0    # decimal degree
        self._longitude = 0.0   # decimal degree
        self._utc_time = 0.0    # seconds since midnight
        self._SOG = 0.0
        self._COG = 0.0
        self._date: int = 0
        self._satellites_in_fix = None
        self._nb_sats_in_fix = 0
        self._PDOP = 0.0
        self._HDOP = 0.0
        self._VDOP = 0.0
        self._altitude = 0.0
        self._geoidal_separation = 0.0
        self._constellations = {}
        self._process_vector = { 'GSV': self.processGSV,
                                  'GNS': self.processGNS,
                                  'GSA': self.processGSA,
                                  'GGA': self.processGGA,
                                  'RMC': self.processRMC
                                 }
        self._sequence = 0


    def process_nmea0183(self, msg: NMEA0183Msg, forwarder):
        fmt = msg.formatter().decode()
        talker = msg.talker().decode()
        try:
            func = self._process_vector[fmt]
        except KeyError:
            _logger.debug("GNSS data no process for %s" % fmt)
            return
        _logger.debug("GNSS_data: %s", str(msg))
        func(talker, msg.fields(), forwarder)


    def get_constellation(self, talker:str) -> Constellation:
        try:
            const = self._constellations[talker]
        except KeyError:
            # we create a new constellation view
            gnss = gnss_sys_dict[talker]
            const = Constellation(gnss=gnss)
            self._constellations[talker] = const
        return const

    def adjust_sequence(self, current_time):
        if current_time != self._utc_time:
            if self._sequence == 253:
                self._sequence = 0
            else:
                self._sequence += 1
            self._utc_time = current_time

    def processGSV(self, talker: str, fields: list, forwarder):

        const = self.get_constellation(talker)
        if not const.gsv_in_progress:
            # that is the first msg in sequence
            if fields[1] != b'1':
                _logger.debug("Constellation %s misaligned sequence %s" % (const.gnss.name, fields[1]))
                return
            const.nb_satellites = int(fields[2])
            const.gsv_nb_seq = int(fields[0])
            const.gsv_seq_recv = [False for n in range(const.gsv_nb_seq)]
            _logger.debug("Starting new GSV sequence for GNSS %s with %d messages" % (const.gnss.name, const.gsv_nb_seq))
            const.gsv_in_progress = True

        seq_num = int(fields[1])
        const.gsv_seq_recv[seq_num - 1] = True
        field_idx = 3
        sat_timestamp = time.time()
        nb_fields = len(fields) - 1
        _logger.debug("Process GCV sequence %d for GNSS %s nb_fields=%d" % (seq_num, const.gnss.name, nb_fields))
        for count in range(4):
            # print("start field=", field_idx)
            if field_idx >= nb_fields:
                break
            sat_id = int(fields[field_idx])
            field_idx += 1
            if len(fields[field_idx]) > 0:
                elevation = float(fields[field_idx]) * deg_to_radian
            else:
                elevation = float('nan')
            field_idx += 1
            if len(fields[field_idx]) > 0:
                azimuth = float(fields[field_idx]) * deg_to_radian
            else:
                azimuth = float('nan')
            field_idx += 1
            if len(fields[field_idx]) > 0:
                snr = float(fields[field_idx])
            else:
                snr = float('nan')
            field_idx += 1
            # now the satellite usage
            try:
                sat = const.satellites[sat_id]
                sat.elevation = elevation
                sat.azimuth = azimuth
                sat.snr = snr
            except KeyError:
                sat = SatellitesInView(svn = sat_id, elevation=elevation, azimuth=azimuth,ts=sat_timestamp, cno=snr)
                const.satellites[sat_id] = sat

        # last field is signal id
        const.signal_id = fields[field_idx]
        # ok the message analysis is over
        if False in const.gsv_seq_recv:
            # the sequence is not over
            return
        # ok go
        _logger.debug("End GSV analysis for constellation %s" % gnss_sys_dict[talker].name)
        const.gsv_in_progress = False
        if forwarder.pgn_in_set(129540):
            pgn129540 = Pgn129540Class()
            pgn129540.sequence_id = self._sequence
            pgn129540.mode = 0
            pgn129540.sats_in_view = const.nb_satellites
            for sat in const.satellites:
                sat_obj = Pgn129540Class.Satellites_DataClass()
                sat_obj.satellite_number = sat.svn
                sat_obj.elevation = sat.elevation * deg_to_radian
                sat_obj.azimuth = sat.azimuth * deg_to_radian
                sat_obj.signal_noise_ratio = sat.snr
                sat_obj.range_residuals = 0x7fffffff
                sat_obj.status = sat.status
                pgn129540.satellites_data.append(sat_obj)
            forwarder.push(pgn129540)


    def processGNS(self, talker, fields, forwarder):
        """
        That is single constellation
        """
        _logger.debug("GNS talker %s posMode %s" % (talker, fields[5]))

    def processGSA(self, talker, fields, forwarder):
        assert (talker == 'GN')
        self._mode = int(fields[1])
        if int(fields[1]) >= 2:
            self._fix = True
        else:
            self._fix = False
            return   # nothing meaningful here

        self._nb_sats_in_fix = 0
        self._satellites_in_fix = []
        for f in fields[2:14]:
            if len(f) != 0:
                self._nb_sats_in_fix += 1
                self._satellites_in_fix.append(int(f))
        self._PDOP = float(fields[14])
        self._HDOP = float(fields[15])
        self._VDOP = float(fields[16])
        if len(fields[17]) > 0:
            self._signal_id = int(fields[17])
        else:
            self._signal_id = 0
        _logger.debug("GSA nb sats:%d signal %d sats %s" % (self._nb_sats_in_fix, self._signal_id, self._satellites_in_fix))
        try:
            const = self._constellations[signal_id_table[self._signal_id]]
        except KeyError:
            _logger.debug("Missing constellation for systemId %d" % self._signal_id)
            return
        const.update_status(self._satellites_in_fix)
        if forwarder.pgn_in_set(129539):
            pgn129539 = Pgn129539Class()
            pgn129539.sequence_id = self._sequence
            if fields[0] == b'A':
                pgn129539.desired_mode = 3
            else:
                pgn129539.desired_mode = 2
            pgn129539.actual_mode = int(fields[1]) - 1
            pgn129539.HDOP = self._HDOP
            pgn129539.VDOP = self._VDOP
            pgn129539.TDOP = self._PDOP
            forwarder.push(pgn129539)

    def processGGA(self, talker, fields, forwarder):
        assert(talker == 'GN')
        if fields[5] == b'0':
            # no fix
            self._fix = False
            return
        else:
            self._fix = True
        current_time = convert_time(fields[0])
        self.adjust_sequence(current_time)
        self._latitude = convert_latitude(fields[2], fields[1])
        self._longitude = convert_longitude(fields[4], fields[3])
        self._altitude = float(fields[8])
        self._geoidal_separation = float(fields[10])

        if forwarder.pgn_in_set(129029) and self._nb_sats_in_fix > 0:
            # we must also have received a GSA message for that
            pgn129029 = Pgn129029Class()
            pgn129029.sequence_id = self._sequence
            pgn129029.latitude = self._latitude
            pgn129029.longitude = self._longitude
            pgn129029.altitude = self._altitude
            pgn129029.number_of_sv = self._nb_sats_in_fix
            if self._date == 0:
                pgn129029.date = 0xffff
            else:
                pgn129029.date = self._date
            pgn129029.time = self._utc_time
            pgn129029.GNSS_type = self._constellations[signal_id_table[self._signal_id]].n2k_fix
            pgn129029.method = int(fields[5])
            pgn129029.integrity = 0
            pgn129029.HDOP = float(fields[7])
            pgn129029.geoidal_separation = self._geoidal_separation
            pgn129029.PDOP = self._PDOP
            pgn129029.nb_ref_stations = 0
            forwarder.push(pgn129029)

    def processRMC(self, talker, fields, forwarder):
        if fields[1] != b'A':
            self._fix = False
            return
        current_time = convert_time(fields[0])
        self.adjust_sequence(current_time)
        self._latitude = convert_latitude(fields[3], fields[2])
        self._longitude = convert_longitude(fields[5], fields[4])
        self._SOG = float(fields[6]) * knots_to_ms
        self._COG = float(fields[7]) * deg_to_radian
        self._date = convert_date(fields[8])
        if forwarder.pgn_in_set(129025):
            pgn129025 = Pgn129025Class()
            pgn129025.latitude = convert_latitude(fields[3], fields[2])
            pgn129025.longitude = convert_longitude(fields[5], fields[4])
            forwarder.push(pgn129025)
        if forwarder.pgn_in_set(129026):
            pgn129026 = Pgn129026Class()
            pgn129026.sequence_id = self._sequence
            pgn129026.COG_reference = 0
            pgn129026.SOG = self._SOG
            pgn129026.COG = self._COG
            forwarder.push(pgn129026)










