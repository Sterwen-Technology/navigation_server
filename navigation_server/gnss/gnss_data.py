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
from calendar import firstweekday
from dataclasses import dataclass
import math
import time
import queue


from navigation_server.router_core import NMEA0183Msg
from navigation_server.nmea2000_datamodel import NMEA2000DecodedMsg, NMEA2000EncodeDecodeError
from navigation_server.generated.nmea2000_classes_gen import (Pgn129025Class, Pgn129026Class, Pgn129029Class,
                                             Pgn129539Class, Pgn129540Class)
from navigation_server.generated.gnss_pb2 import GNSS_Status, ConstellationStatus, SatellitesInView

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

def convert_float(field: bytearray, coefficient: float, field_name: str) -> float:
    if len(field) == 0:
        _logger.debug("Missing field %s" % field_name)
        return float('nan')
    else:
        return float(field) * coefficient


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
    satellites_in_fix: list = None
    nb_sats_in_fix: int = 0
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


class GNSSInputStat:

    def __init__(self, formatter):
        self._formatter = formatter
        self._count = 0
        self._last_time = time.monotonic()
        self._first_time = self._last_time
        self._interval = 0.0


    def seen(self):
        self._count += 1
        t = time.monotonic()
        self._interval = t - self._last_time
        self._last_time = t

    @property
    def formatter(self):
        return self._formatter

    @property
    def interval(self) -> float:
        return self._interval

    @property
    def average_interval(self) -> float:
        return (time.monotonic() - self._first_time) / self._count




class N2KForwarder:

    def __init__(self, pgn_set: set, output_queue: queue.Queue, constellation: str = None):
        self._pgn_set = pgn_set
        self._output_queue = output_queue
        self._suspend_flag = True       # start in suspended state
        self._messages_lost = 0
        self._total_messages = 1    # to avoid any division by 0 in boundary cases
        self._gnss_system = None
        if constellation is not None:
            self._gnss_system = gnss_dict.get(constellation, None)

    def push(self, msg:NMEA2000DecodedMsg):
        if self._suspend_flag:
            return
        if msg.pgn in self._pgn_set:
            try:
                n2k_msg = msg.message()
            except NMEA2000EncodeDecodeError:
                _logger.error(f"GNSS Data error pushing PGN{msg.pgn}:{str(msg)}")
                return
            self._total_messages += 1
            try:
                self._output_queue.put(n2k_msg, block=True, timeout=0.5)
            except queue.Full:
                _logger.error("N2KForwarder queue Full - message discarded - PGN %d" % msg.pgn)
                self._messages_lost += 1

    def pgn_in_set(self, pgn:int, constellation:Constellation = None) -> bool:
        """
        Check if the PGN is to be reported
        """
        if self._gnss_system is not None and constellation is not None:
            return constellation.gnss.systemId == self._gnss_system.systemId and pgn in self._pgn_set
        else:
            return pgn in self._pgn_set


    def suspend(self):
        self._suspend_flag = True

    def resume(self):
        self._suspend_flag = False

    def percentage_lost(self) -> float:
        return self._messages_lost / self._total_messages


gnss_systems = (   GNSSSystem('GNSS', 'GN', 0, 0, 0),  # To avoid errors for GN messages
                   GNSSSystem('GPS', 'GP', 1, 0, 1),
                   GNSSSystem('GPS-SBAS', 'GP', 1, 1, 1),
                   GNSSSystem('Galileo', 'GA', 3, 2, 8),
                   GNSSSystem('Beidou', 'GB',4, 3, 0),
                   GNSSSystem('QZSS', 'GQ',5, 5, 0),
                   GNSSSystem('GLONASS', 'GL',2, 6, 2),
                   GNSSSystem('NavIC', 'GI',6, 7, 0)
                   )

gnss_sys_dict = dict([(s.talker, s) for s in gnss_systems])
signal_id_table = dict([(s.systemId, s) for s in gnss_systems])
gnss_dict = dict([(s.name, s)for s in gnss_systems])

class GNSSDataManager:
    """
    The class manages all global data for the GNSS
    Visible constellations and satellites
    Current position
    fix
    """

    def __init__(self):
        """
        All units here below are the one from NMEA2000 so ISO standard
        """
        self._fix = False
        self._fix_quality = None
        self._mode = 0
        self._const_in_fix = []         # signal ID (constellation for the fix)
        self._fix_time = 0.0    # datetime from system
        self._start_time = datetime.datetime.now(datetime.UTC)
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
                                  'RMC': self.processRMC,
                                  'TXT': self.processTXT
                                 }
        self._sequence = 0
        self._stats = {}


    def set_fix(self):
        if not self._fix:
            self._fix_time = time.time()
            self._fix = True
            _logger.info(f"GNSS is becoming fixed")

    def lost_fix(self):
        if not self._fix:
            _logger.info("GNSS lost fix")
            self._fix = False
            self._const_in_fix = []
            self._nb_sats_in_fix = 0

    @property
    def fix(self) -> bool:
        return self._fix

    def stats(self):
        return list(self._stats.values())

    def process_nmea0183(self, msg: NMEA0183Msg, forwarder):
        fmt = msg.formatter().decode()
        talker = msg.talker().decode()
        try:
            stat = self._stats[fmt]
            stat.seen()
        except KeyError:
            self._stats[fmt] = GNSSInputStat(fmt)

        try:
            func = self._process_vector[fmt]
        except KeyError:
            _logger.debug("GNSS data no process for %s" % fmt)
            return
        _logger.debug("GNSS_data: %s", str(msg))
        try:
            func(talker, msg.fields(), forwarder)
        except Exception as err:
            _logger.error(f"GNSS data error:{err} for {msg}")


    def get_constellation(self, talker:str) -> Constellation:
        gnss = gnss_sys_dict[talker]
        try:
            const = self._constellations[gnss.systemId]
        except KeyError:
            # we create a new constellation view
            const = Constellation(gnss=gnss)
            self._constellations[gnss.systemId] = const
        return const

    def get_constellation_from_id(self, signal_id:int):
        try:
            return self._constellations[signal_id]
        except KeyError:
            gnss = signal_id_table[signal_id]
            const = Constellation(gnss=gnss)
            self._constellations[gnss.systemId] = const
            return const

    def adjust_sequence(self, current_time):
        if current_time != self._utc_time:
            if self._sequence == 253:
                self._sequence = 0
            else:
                self._sequence += 1
            self._utc_time = current_time

    def processGSV(self, talker: str, fields: list, forwarder):
        """
        Process the GSV NMEA message and generate a 129540 PGN
        """
        const = self.get_constellation(talker)
        _logger.debug("Start GSV processing for %s" % const.gnss.name)
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
        _logger.debug("Process GSV sequence %d for GNSS %s nb_fields=%d" % (seq_num, const.gnss.name, nb_fields))
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
                sat.cno = snr
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
        _logger.debug("End GSV analysis for constellation %s" % const.gnss.name)
        const.gsv_in_progress = False
        if forwarder.pgn_in_set(129540, const):
            pgn129540 = Pgn129540Class()
            pgn129540.sequence_id = self._sequence
            pgn129540.mode = 0
            pgn129540.sats_in_view = const.nb_satellites
            for sat in const.satellites.values():
                sat_obj = Pgn129540Class.Satellites_DataClass()
                sat_obj.satellite_number = sat.svn
                sat_obj.elevation = sat.elevation * deg_to_radian
                sat_obj.azimuth = sat.azimuth * deg_to_radian
                sat_obj.signal_noise_ratio = sat.cno
                sat_obj.range_residuals = 0x7fffffff
                sat_obj.status = sat.status
                pgn129540.satellites_data.append(sat_obj)
            _logger.debug("Pushing PGN 129540 with total number of satellites=%d constellation:%s" %
                          (pgn129540.sats_in_view, const.gnss.name))
            forwarder.push(pgn129540)


    def processGNS(self, talker, fields, forwarder):
        """
        That is single constellation
        """
        _logger.debug("GNS talker %s posMode %s" % (talker, fields[5]))

    def processGSA(self, talker, fields, forwarder):
        """
        Process GSA NMEA message =>GNSS DOP and active satellites
        Generate a 129539 PGN
        """
        assert (talker == 'GN')
        self._mode = int(fields[1])
        if int(fields[1]) >= 2:
            self.set_fix()
        else:
            self.lost_fix()
            return   # nothing meaningful here
        if len(fields[17]) > 0:
            signal_id = int(fields[17])
        else:
            return
        _logger.debug("GSA signal id %d" % signal_id)
        const = self.get_constellation_from_id(signal_id)
        nb_sats_in_fix = 0
        satellites_in_fix = []
        for f in fields[2:14]:
            if len(f) != 0:
                nb_sats_in_fix += 1
                satellites_in_fix.append(int(f))
        if nb_sats_in_fix == 0:
            return
        # now we update the list for the fix
        if const not in self._const_in_fix:
            self._const_in_fix.append(const)
        const.nb_sats_in_fix = nb_sats_in_fix
        const.satellites_in_fix = satellites_in_fix
        self._PDOP = float(fields[14])
        self._HDOP = float(fields[15])
        self._VDOP = float(fields[16])

        _logger.debug("GSA const %s nb sats:%d sats %s" % (const.gnss.name, nb_sats_in_fix, satellites_in_fix))
        const.update_status(satellites_in_fix)
        if forwarder.pgn_in_set(129539, const):
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
            _logger.debug("Pushing PGN 129539")
            forwarder.push(pgn129539)

    def processGGA(self, talker, fields, forwarder):
        """
        Process the GGA NMEA message => Global positioning fix data
        Generate a 129039 PGN
        """
        assert(talker == 'GN')
        if fields[5] == b'0':
            # no fix
            self.lost_fix()
            return
        else:
            self.set_fix()
        current_time = convert_time(fields[0])
        self.adjust_sequence(current_time)
        self._latitude = convert_latitude(fields[2], fields[1])
        self._longitude = convert_longitude(fields[4], fields[3])
        self._altitude = float(fields[8])
        self._geoidal_separation = float(fields[10])
        _logger.debug("GGA processing lat %f long %f nb constellations %d" % (self._latitude, self._longitude, len(self._const_in_fix)))
        self._nb_sats_in_fix = 0
        for const in self._const_in_fix:
            self._nb_sats_in_fix += const.nb_sats_in_fix
        if forwarder.pgn_in_set(129029):
            # we must also have received a GSA message for that
            pgn129029 = Pgn129029Class()
            pgn129029.priority = 3
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
            pgn129029.GNSS_type = 0
            pgn129029.method = int(fields[5])
            pgn129029.integrity = 0
            pgn129029.HDOP = float(fields[7])
            pgn129029.geoidal_separation = self._geoidal_separation
            pgn129029.PDOP = self._PDOP
            pgn129029.nb_ref_stations = 0
            _logger.debug("GGA pushing PGN 129029")
            forwarder.push(pgn129029)

    def processRMC(self, talker, fields, forwarder):
        """
        process the RMC NMEA message => Recommended minimum data
        Generate 120025 and 129026 PGN
        """
        if fields[1] != b'A':
            self.lost_fix()
            return
        current_time = convert_time(fields[0])
        self.adjust_sequence(current_time)
        self._latitude = convert_latitude(fields[3], fields[2])
        self._longitude = convert_longitude(fields[5], fields[4])
        self._SOG = float(fields[6]) * knots_to_ms
        self._COG = convert_float(fields[7], deg_to_radian, 'COG')
        self._date = convert_date(fields[8])
        if forwarder.pgn_in_set(129025):
            pgn129025 = Pgn129025Class()
            pgn129025.priority = 3
            pgn129025.latitude = convert_latitude(fields[3], fields[2])
            pgn129025.longitude = convert_longitude(fields[5], fields[4])
            _logger.debug("RMC pushing PGN 129025")
            forwarder.push(pgn129025)
        if forwarder.pgn_in_set(129026):
            pgn129026 = Pgn129026Class()
            pgn129026.priority = 3
            pgn129026.sequence_id = self._sequence
            pgn129026.COG_reference = 0
            pgn129026.SOG = self._SOG
            pgn129026.COG = self._COG
            _logger.debug("RMC pushing PGN 129026")
            forwarder.push(pgn129026)

    def processTXT(self, talker, fields, forwarder):
        """
        This is here just in case
        """
        if int(fields[2]) == 0:
            _logger.error(f"GNSS Chip is issuing an error: {fields[3].decode()}")
        else:
            _logger.info(f"TXT: msg:{fields[3].decode()}")

    def get_status(self, cmd) -> GNSS_Status:
        """
        Return a Protobuf object that includes the fields corresponding to keywords in cmd
        """
        resp = GNSS_Status()
        resp.fixed = self._fix
        if self._fix:
            # ok we can fill additional info
            resp.fix_time = self._fix_time
            resp.gnss_time = (datetime.datetime.fromordinal(self._date + jan170)
                              + datetime.timedelta(seconds=self._utc_time)).isoformat()
            resp.nb_satellites_in_fix = self._nb_sats_in_fix
        return resp










