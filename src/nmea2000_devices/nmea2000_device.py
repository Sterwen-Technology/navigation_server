# -------------------------------------------------------------------------------
# Name:        NMEA2000 Generic device
# Purpose:     Implement the basic specific applicative function of a CA or NMEA2000 Devices
#               Generic J1939 / NMEA2000 functions are inherited
#
# Author:      Laurent Carré
#
# Created:     12/09/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
from collections import namedtuple
from datetime import datetime, timedelta

from can_interface import NMEA2000Application
from router_core import NMEA2000Msg
from router_common import N2KInvalidMessageException, nautical_mille, n2ktime_to_datetime, mps_to_knots, radian_to_deg
from generated.nmea2000_classes_gen import Pgn129283Class, Pgn129284Class, Pgn129285Class, Pgn129026Class, Pgn129029Class

_logger = logging.getLogger("ShipDataServer." + __name__)


class NMEA2000DeviceImplementation(NMEA2000Application):

    def __init__(self, opts):
        self._name = opts['name']
        self._requested_address = opts.get('address', int, -1)
        self._model_id = opts.get('model_id', str, 'Generic Device')
        self._processed_pgn = opts.getlist('pgn_list', int, None)
        self._pgn_vector = None

    def init_product_information(self):
        super().init_product_information()
        self._product_information.model_id = self._model_id

    def set_controller(self, controller):
        super().__init__(controller, self._requested_address)
        # here we assume that the publisher has been instantiated as well
        _logger.info(f"Device Simulator {self._name} ready")
        controller.set_pgn_vector(self, self._processed_pgn)

    def receive_data_msg(self, msg: NMEA2000Msg):
        '''
        This is a generic method that is only printing the message received
        '''
        if self._pgn_vector is None:
            raise NotImplementedError
        try:
            self._pgn_vector[msg.pgn](msg)
        except KeyError:
            _logger.error(f"{self.__class__.__name__} missing vector for PGN {msg.pgn}")

Waypoint = namedtuple('Waypoint', ['id', 'name', 'latitude', 'longitude'])

class AutoPilotEmulator(NMEA2000DeviceImplementation):
    '''
    This a example class for a NMEA2000 implementation
    '''

    def __init__(self, opts):
        super().__init__(opts)
        self._model_id = 'AutoPilot Emulator'
        self._pgn_vector = {129283: self.cross_track_error,
                            129284: self.navigation_data,
                            129285: self.route_wp_information,
                            # 129029: self.gnss_data,
                            # 129026: self.cog_sog
                            # 129039: self.ais_classb
                            }
        self._processed_pgn = list(self._pgn_vector)
        self._current_sid = -1
        self._waypoints = None
        self._gnss_date = None

    def cross_track_error(self, msg: NMEA2000Msg):
        msg129283 = Pgn129283Class(message=msg)
        _logger.debug(msg.format2())
        print(f"PGN129283 SID={msg129283.sequence_id}")
        if msg129283.XTE_mode:
            print("Navigation terminated")
        else:
            print(f"XTE {msg129283.XTE:.1f}m")

    def navigation_data(self, msg: NMEA2000Msg):
        msg129284 = Pgn129284Class(message=msg)
        _logger.debug(msg.format2())
        self._current_sid = msg129284.sequence_id
        print(f"PGN129284 SID={self._current_sid}")
        dtw = msg129284.distance_to_waypoint / nautical_mille
        btw = msg129284.bearing_position_to_destination * radian_to_deg
        dest_wp_idx = msg129284.destination_waypoint
        print(f"Destination WP index {msg129284.destination_waypoint}")
        if self._waypoints is not None:
            dest_wp_name = self._waypoints[dest_wp_idx].name
        else:
            dest_wp_name = 'Unknown'
        ete = timedelta(seconds=msg129284.distance_to_waypoint/msg129284.WCV)
        eta = n2ktime_to_datetime(msg129284.ETA_date, msg129284.ETA_time)
        eta_recomputed = self._gnss_date + ete
        # print(f"Time in sec {msg129284.ETA_time} ETE:{ete}s")
        print(f"Destination {dest_wp_name} Bearing {btw:.0f}° distance {dtw:.2f}nm VMG {msg129284.WCV*mps_to_knots:.1f} ETA {eta}")
        print(f"ETA recomputed={eta_recomputed}")


    def route_wp_information(self, msg: NMEA2000Msg):
        msg129285 = Pgn129285Class(message=msg)
        _logger.debug(msg.format2())
        wps = []
        nb_items = msg129285.nb_items
        print(f"PGN129295 Route information with {nb_items} waypoints")
        for wp in msg129285.WP_definitions:
            wps.append(Waypoint(wp.waypoint_id, wp.waypoint_name, wp.waypoint_latitude, wp.waypoint_longitude))
            print(f"Waypoint [{wp.waypoint_id}]={wp.waypoint_name}")
        assert len(wps) == nb_items
        self._waypoints = wps

    def cog_sog(self, msg: NMEA2000Msg):
        try:
            msg129026 = Pgn129026Class(message=msg)
        except N2KInvalidMessageException:
            _logger.debug(f"invalid PGN 129026 from {msg.sa}")
            return
        print(f"SA:{msg.sa} SOG:{msg129026.SOG:.2f}m/s {msg129026.SOG*mps_to_knots:.1f}kn COG {msg129026.COG:.0f}")

    def gnss_data(self, msg: NMEA2000Msg):
        msg129029 = Pgn129029Class(message=msg)
        self._gnss_date = n2ktime_to_datetime(msg129029.date, msg129029.time)
        print(f"GNSS date {self._gnss_date} SA={msg.sa}")

    def ais_classb(self, msg: NMEA2000Msg):
        print(f"PGN129039 payload length{len(msg.payload)}: {msg.payload.hex()}")


