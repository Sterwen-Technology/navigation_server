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
import os
import sys
import logging
import threading

from navigation_server.router_core import ExternalPublisher, NMEAInvalidFrame
from navigation_server.nmea2000_datamodel import FormattingOptions
from .nmea2k_decode_dispatch import get_n2k_decoded_object, N2KMissingDecodeEncodeException
from navigation_server.nmea_data import N2KStatistics, NMEA183Statistics
from .nmea0183_to_nmea2k import NMEA0183ToNMEA2000Converter
from navigation_server.router_common import get_global_option, NavGenericMsg, N2K_MSG, N2KDecodeException, N0183_MSG, \
    N2KInvalidMessageException

_logger = logging.getLogger("ShipDataServer" + "." + __name__)


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
            trace_dir = get_global_option('trace_dir', '/var/log')
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
            self.process_nmea183(gen_msg)
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
                print_result = res.as_protobuf_json()
            if self._print_option in ('ALL', 'PRINT'):
                print("Message:", print_result)
            if self._print_option in ('ALL', 'FILE') and self._trace_fd is not None:
                # self._trace_fd.write("Message from SA:%d " % msg.sa)
                self._trace_fd.write(print_result)
                self._trace_fd.write('\n')
        return True

    def process_nmea183(self, msg: NavGenericMsg):
        _logger.debug("Grpc Publisher NMEA0183 input: %s" % msg)
        if not self._convert_nmea183 and self._print_option in ('ALL', 'PRINT'):
            print(str(msg))
            return
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
            _logger.error("NMEA0183 decoding error:%s" % e)
            return

    def stop(self):
        if self._active:
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
        if self._active:
            self._n183_stats.print_entries()
            self._n2k_stats.print_entries()
        super().stop()


class N2KSourceDispatcher(ExternalPublisher):
    """
    That class is used to dispatch NMEA2000 messages towards subscribers based on the PGN
    It can work in 3 modes:
    transparent mode: assuming CAN message in - can message out - no Fast Packet processing
    message mode: fast packet reassembly is performed
    decoded mode: message is fully decoded according to SA
    Specific parameters:
    mode:  transparent= direct CAN frame expected on input |  message= NMEA2000 message (type NavGenericMsg) | decoded= decoded NMEA2000 Object
            Default is message but only transparent is implmented (V2.2)

    Objects that wants to receive NMEA2000 messages following the mode format must subscribe with a source address.
            If the source is 255, then all messages are forwarded
    """

    def __init__(self, opts):
        super().__init__(opts)
        self._mode = opts.get_choice('mode',['transparent', 'message', 'decoded'], 'message')
        self._process_msg = {'transparent': self._transparent, 'message': self._message, 'decoded': self._decoded}[self._mode]
        self._subscribers = {}
        self._direct_vector = None

    def subscribe(self, source:int, vector):
        _logger.info(f"N2KSourceDispatcher {self.name} subscription for source {source}")
        if source == 255:
            # all messages are routed no vector per PGN
            self._subscribers = None
            self._direct_vector = vector
            self._process_msg = self._direct_transparent
            return
        if self._subscribers is None:
            _logger.error(f"N2KDispatcher in ALL source mode source {source} ignored")
            return
        if source in self._subscribers:
            _logger.error(f"N2KDispatcher duplicate source {source} subscription => ignored")
            return
        self._subscribers[source] = vector

    def process_msg(self, msg: NavGenericMsg):
        # call the processing message based on mode
        return self._process_msg(msg)

    def _transparent(self, msg: NavGenericMsg):
        """
        Transparent processing for the CAN Frame
        Input is the hex str frame from the log file
        Only SA is extracted, then the can_id and data are sent to the subscriber
        """
        frame = msg.raw
        try:
            can_id = int(frame[:8], 16)
            data = bytearray.fromhex(frame[9:])
        except ValueError:
            _logger.error("Log coupler => erroneous frame:%s" % frame)
            return True
        source = can_id & 0xFF
        _logger.debug("SourceDispatcher message from source %d" % source)
        try:
            self._subscribers[source](can_id, data)
        except KeyError:
            _logger.debug("N2KDispatcher => no subscriber for source %d" % source)
        return True

    def _direct_transparent(self, msg: NavGenericMsg):
        """
        All messages are forwarded for all sources
        """
        frame = msg.raw
        try:
            can_id = int(frame[:8], 16)
            data = bytearray.fromhex(frame[9:])
        except ValueError:
            _logger.error("Log coupler => erroneous frame:%s" % frame)
            return True
        self._direct_vector(can_id, data)
        return True

    def _message(self, msg: NavGenericMsg):
        raise NotImplementedError

    def _decoded(self, msg: NavGenericMsg):
        raise NotImplementedError


class N2KJsonPublisher(ExternalPublisher):
    '''
    Class that converts and push all PGN messages
    PGN are converted only via 'hard' decoding i.e. via generated classes. PGN that have no associated classes, are not decoded
    output is by default on stdout, but can be redirected to any file
    Filters can be applied
    If NMEA013 messages are sent to the publisher they will simply be discarded (debug traces)
    '''

    def __init__(self, opts):
        super().__init__(opts)
        self._std_output = False
        self._option = 0
        if not self._active:
            return
        if opts.get('resolve_enum', bool, False):
            self._option = FormattingOptions.ResolveEnum
        if opts.get('remove_invalid', bool, False):
            self._option |= FormattingOptions.RemoveInvalid
        if opts.get('alternative_units', bool, False):
            self._option |= FormattingOptions.AlternativeUnits
        self._trace_invalid = opts.get('trace_invalid', bool, False)
        self._output_def = opts.get('output', str, 'stdout')
        if self._output_def == 'stdout':
            self._output_fd = sys.stdout
            self._std_output = True
        elif self._output_def.lower() == 'file':
            self._filename = opts.get('filename', str, None)
            if self._filename is None:
            # compute default
                self._filename = "TRACE"
                trace_dir = NavigationConfiguration.get_conf().get_option('trace_dir', '/var/log')
                date_stamp = datetime.datetime.now().strftime("%y%m%d-%H%M")
                filename = "%s-N2K-%s.json" % (self._filename, date_stamp)
                filepath = os.path.join(trace_dir, filename)
            else:
                filepath = self._filename
            try:
                self._output_fd = open(filepath, "w")
            except IOError as e:
                _logger.error(f"Output file {filepath} error {e}")
                self._output_fd = None
                raise
            _logger.info(f"NMEA2000 to Json Publisher Directing output to {filepath}")
        else:
            _logger.error(f"N2KJsonPublisher incorrect output {self._output_def}")
            self._output_fd = None
            raise ValueError
        self._stats = N2KStatistics()
        self._close_lock = threading.Lock()


    def process_msg(self, msg: NavGenericMsg):
        if msg.type != N2K_MSG:
            return
        n2k_msg = msg.msg
        try:
            decoded_msg = get_n2k_decoded_object(n2k_msg)
        except N2KMissingDecodeEncodeException:
            self._stats.add_entry(n2k_msg)
            return True
        except N2KInvalidMessageException:
            if self._trace_invalid:
                _logger.info(f"Invalid message: {n2k_msg.format1()}")
            return True
        except Exception as e:
            _logger.error(f"Error during PGN {n2k_msg.pgn} from:{n2k_msg.sa} decoding: {e}")
            return True

        self._close_lock.acquire()
        if self._output_fd is not None:
            decoded_msg.push_json(self._output_fd, self._option)
            self._output_fd.write('\n')
        self._close_lock.release()
        return True

    def stop(self):
        if self._output_fd is not None:
            self._close_lock.acquire()
            if not self._std_output:
                self._output_fd.close()
            self._output_fd = None
            self._close_lock.release()
        if self._active:
            self._stats.print_entries()
        super().stop()

