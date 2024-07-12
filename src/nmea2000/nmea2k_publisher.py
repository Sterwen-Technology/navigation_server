#-------------------------------------------------------------------------------
# Name:        nmea2000_publishers
# Purpose:     Publishers to debug and trace NMEA2000
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import datetime
import time
import os
import logging

from router_core import ExternalPublisher, NMEAInvalidFrame
from .nmea2k_decode_dispatch import get_n2k_decoded_object, N2KMissingDecodeEncodeException
from nmea_data.nmea_statistics import N2KStatistics, NMEA183Statistics
# from router_common import *
from .nmea0183_to_nmea2k import NMEA0183ToNMEA2000Converter
from router_common import NavigationConfiguration, NavGenericMsg, N2K_MSG, find_pgn, N2KDecodeException, N0183_MSG


_logger = logging.getLogger("ShipDataServer" + "." + __name__)


class PgnRecord:

    def __init__(self, pgn: int):
        self._pgn = pgn
        self._pgn_def = find_pgn(pgn)
        self._clock = time.time()
        self._count = 1

    @property
    def pgn(self):
        return self._pgn

    @property
    def pgn_def(self):
        return self._pgn_def

    def tick(self):
        self._count += 1


class N2KTracePublisher(ExternalPublisher):

    def __init__(self, opts):
        super().__init__(opts)
        self._flexible = opts.get('flexible_decode', bool, True)
        self._convert_nmea183 = opts.get('convert_nmea0183', bool, False)
        if self._convert_nmea183:
            self._converter = NMEA0183ToNMEA2000Converter()
        self._print_option = opts.get('output', str, 'ALL')
        _logger.info("%s output option %s" % (self.object_name(), self._print_option))
        self._trace_fd = None
        filename = opts.get('file', str, None)
        if filename is not None and self.is_active:
            trace_dir = NavigationConfiguration.get_conf().get_option('trace_dir', '/var/log')
            date_stamp = datetime.datetime.now().strftime("%y%m%d-%H%M")
            filename = "%s-N2K-%s.log" % (filename, date_stamp)
            filepath = os.path.join(trace_dir, filename)
            _logger.info("Opening trace file %s" % filepath)
            try:
                self._trace_fd = open(filepath, "w")
            except IOError as e:
                _logger.error("Trace file error %s" % e)
                self._trace_fd = None
        self._stats = N2KStatistics()

    def process_msg(self, gen_msg):
        if gen_msg.type != N2K_MSG:
            if self._convert_nmea183:
                self.process_nmea183(gen_msg)
                return True
            else:
                return True
        msg = gen_msg.msg
        _logger.debug("Trace publisher N2K input msg %s" % msg.format2())
        if self._print_option == 'NONE':
            return True

        # print("decoding %s", msg.format1())
        if self._flexible:
            try:
                res = msg.decode()
            except N2KDecodeException:
                return True
            except Exception as e:
                _logger.error("Error decoding PGN: %s message:%s" % (e, msg.format1()))
                return True
        else:
            try:
                res = get_n2k_decoded_object(msg)
            except N2KMissingDecodeEncodeException:
                self._stats.add_entry(msg)
                return True
            except Exception as e:
                _logger.error("Error decoding PGN: %s message:%s" % (e, msg.format1()))
                return True
        _logger.debug("Trace publisher msg:%s" % res)
        if res is not None:
            if type(res) is dict:
                print_result = res
            else:
                print_result = res.as_json()
            if self._print_option in ('ALL', 'PRINT'):
                print("Message:", print_result)
            if self._print_option in ('ALL', 'FILE') and self._trace_fd is not None:
                # self._trace_fd.write("Message from SA:%d " % msg.sa)
                self._trace_fd.write(print_result)
                self._trace_fd.write('\n')
        return True

    def process_nmea183(self, msg: NavGenericMsg):
        _logger.debug("Grpc Publisher NMEA0183 input: %s" % msg)
        if self._print_option in ('ALL', 'FILE') and self._trace_fd is not None:
            self._trace_fd.write(str(msg))
            self._trace_fd.write('\n')
        try:
            for res in self._converter.convert(msg):
                print_result = res.as_json()
                if self._print_option in ('ALL', 'PRINT'):
                    print("Message:", print_result)
                if self._print_option in ('ALL', 'FILE') and self._trace_fd is not None:
                    # self._trace_fd.write("Message from SA:%d " % msg.sa)
                    self._trace_fd.write(print_result)
                    self._trace_fd.write('\n')
        except NMEAInvalidFrame:
            return
        except Exception as e:
            _logger.error("NMEA0183 decing error:%s" % e)
            return

    def stop(self):
        print("List of missing decode for PGN")
        self._stats.print_entries()
        if self._trace_fd is not None:
            self._trace_fd.close()
        super().stop()


class N2KStatisticPublisher(ExternalPublisher):

    def __init__(self, opts):
        super().__init__(opts)
        self._n183_stats = NMEA183Statistics()
        self._n2k_stats = N2KStatistics()

    def process_msg(self, msg: NavGenericMsg):
        if msg.type == N0183_MSG:
            self._n183_stats.add_entry(msg.talker(), msg.formatter())
        else:
            self._n2k_stats.add_entry(msg.msg)
        return True

    def stop(self):
        self._n183_stats.print_entries()
        self._n2k_stats.print_entries()
        super().stop()


