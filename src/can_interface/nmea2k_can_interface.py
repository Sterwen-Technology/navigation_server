# -------------------------------------------------------------------------------
# Name:        NMEA2K-CAN Interface class
# Purpose:     Implements the direct CAN Bus interface
#
# Author:      Laurent Carré
#
# Created:     12/09/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

# update notes
# 4/1/2024  => adding a first minimal version of ISO (J1939) Transport protocol - Only broadcast receipt

import datetime
import logging
import threading
import queue
import time
import subprocess

from can import Message, CanError, ThreadSafeBus

from router_core.nmea2000_msg import NMEA2000Msg
from nmea2000 import FastPacketHandler, FastPacketException
from nmea2000 import IsoTransportHandler, IsoTransportException
from nmea2000_datamodel import PGNDef
from router_common import NMEAMsgTrace, MessageTraceError, NavThread
from router_common import ObjectFatalError


_logger = logging.getLogger("ShipDataServer." + __name__)


class SocketCanError(Exception):
    pass


class SocketCanReadInvalid(Exception):
    pass


def check_can_device(link):
    """

    """
    proc = subprocess.run('/sbin/ip link | grep %s' % link, shell=True, capture_output=True, text=True)
    lines = proc.stdout.split('\n')
    #  print(len(lines), lines)
    if len(lines) <= 1:
        raise SocketCanError("SocketCAN channel %s non existent" % link)
    try:
        i = lines[0].index(link)
    except ValueError:
        raise SocketCanError("SocketCAN channel %s non existent" % link)
    try:
        i = lines[0].index('UP')
    except ValueError:
        raise SocketCanError("SocketCAN channel %s not ready" % link)
    return


class SocketCANInterface(NavThread):
    """

    """
    (BUS_NOT_CONNECTED, BUS_CONNECTED, BUS_READY, BUS_SENS_ALLOWED) = range(0, 4)

    def __init__(self, channel, out_queue, trace=False):

        try:
            check_can_device(channel)
        except SocketCanError as err:
            err_str = "CAN bus not available"
            _logger.critical("%s: %s" % (err_str, err))
            raise ObjectFatalError(err_str)

        super().__init__(name="CAN-if-%s" % channel)
        self._channel = channel
        self._bus = None
        self._queue = out_queue
        self._stop_flag = False
        # self._data_queue = None
        self._allowed_send = threading.Event()
        self._allowed_send.clear()
        self._bus_ready = threading.Event()
        self._bus_ready.clear()
        self._in_queue = queue.Queue(30)
        self._bus_queue = queue.Queue(50)
        self._fp_handler = FastPacketHandler(self)
        self._iso_tp_handler = IsoTransportHandler()
        self._total_msg_in = 0
        # self._access_lock = threading.Lock()
        self._addresses = [255]
        self._write_errors = 0

        # self._notifier = None
        # self._listener = NMEA2000MsgListener(self, self._bus_queue)
        self._state = self.BUS_NOT_CONNECTED

        if trace:
            try:
                self._trace = NMEAMsgTrace(self.name, self.__class__.__name__)
            except MessageTraceError:
                self._trace = None
        else:
            self._trace = None

        self._writer = SocketCANWriter(self._in_queue, self, self._trace)

    def start(self):
        # connect to the CAN bus
        try:
            self._bus = ThreadSafeBus(channel=self._channel, interface="socketcan", bitrate=250000)
        except CanError as e:
            _logger.error("Error initializing CAN Channel %s: %s" % (self._channel, e))
            raise SocketCanError
        # self._notifier = Notifier(self._bus, [self._listener])
        self._writer.set_bus(self._bus)
        self._state = self.BUS_CONNECTED
        super().start()
        self._writer.start()
        # once the first message is received, the bus is considered as ready
        self._bus_ready.set()
        self._state = self.BUS_READY

    def stop(self):
        self._stop_flag = True
        self._writer.stop()
        if self._trace is not None:
            self._trace.stop_trace()

    def add_address(self, address: int):
        self._addresses.append(address & 0xFF)

    def remove_address(self, address: int):
        try:
            self._addresses.remove(address)
        except ValueError:
            _logger.error("CAN interface removing non existent destination address %d" % address)

    @property
    def channel(self):
        return self._channel

#   @property
#  def access_lock(self):
#     return self._access_lock

    def total_msg_raw(self):
        return self._total_msg_in

    def total_msg_raw_out(self):
        self._writer.total_msg()

    def wait_for_bus_ready(self):
        self._bus_ready.wait()
        _logger.debug("NMEA CAN Interface BUS ready")

    def allow_send(self):
        self._allowed_send.set()

    def send_trace(self, direction, can_id, timestamp, data):
        if timestamp == 0.0:
            timestamp = time.time()
        date_ts = datetime.datetime.fromtimestamp(timestamp)
        trace_str = "%08X,%s" % (can_id, data.hex())
        self._trace.trace_n2k_raw_can(date_ts, self._total_msg_in, direction, trace_str)

    def process_receive_msg(self, msg_recv: Message):
        # sub-function to read the bus and perform Fast packet reassembly
        # return a NMEA200Msg when a valid message as been received or reassembled

        can_id = msg_recv.arbitration_id
        pgn, da = PGNDef.pgn_pdu1_adjust((can_id >> 8) & 0x1FFFF)
        if da not in self._addresses:
            _logger.debug("CAN interface discarding message:%s" % msg_recv)
            return
        sa = can_id & 0xFF
        prio = (can_id >> 26) & 0x7
        data = msg_recv.data
        if self._trace is not None:
            self.send_trace(NMEAMsgTrace.TRACE_IN, can_id, msg_recv.timestamp, data)
        self._total_msg_in += 1
        # ISO TP handling
        # only Broadcast messages are handled, others will raise an exception
        if pgn == 60416:
            self._iso_tp_handler.new_transaction(sa, prio, data)
            return
        elif pgn == 60160:
            try:
                n2k_msg = self._iso_tp_handler.incoming_packet(sa, data)
            except IsoTransportException:
                return
            if n2k_msg is not None:
                try:
                    self._queue.put(n2k_msg, block=False)
                except queue.Full:
                    _logger.warning("CAN read queue full for ISO-TP (J1939/21), message ignored")
            return

        # Fast packet handling
        if self._fp_handler.is_pgn_active(pgn, sa, data):
            try:
                data = self._fp_handler.process_frame(pgn, sa, data)
            except FastPacketException as e:
                _logger.error("CAN interface Fast packet error %s pgn %d sa %d data %s" % (e, pgn, sa, data.hex()))
                return None
            if data is None:
                return None
        else:
            if PGNDef.fast_packet_check(pgn):
                data = self._fp_handler.process_frame(pgn, sa, data)
            if data is None:
                return None
        # end fast packet handling
        n2k_msg = NMEA2000Msg(pgn, prio, sa, da, data)
        if n2k_msg is not None:
            try:
                self._queue.put(n2k_msg, block=False)
            except queue.Full:
                _logger.warning("CAN read queue full, message discarded: %s" % n2k_msg.header_str())
                time.sleep(0.02)

    def read_can(self) -> Message:
        # if self._access_lock.acquire(timeout=0.5):
            # _logger.debug("Acquire read lock")
        try:
            msg = self._bus.recv(0.5)
        except CanError as e:
            _logger.error("Error on CAN reading on channel %s: %s" % (self._channel, e))
            # self._access_lock.release()
            raise SocketCanReadInvalid
        # _logger.debug("release read lock")
        # self._access_lock.release()
        if msg is None:
            raise SocketCanReadInvalid
        if not msg.is_extended_id or msg.is_remote_frame:
            raise SocketCanReadInvalid
        return msg
        # else:
            # _logger.error("%s unable to lock CAN interface" % self.name)
            # raise SocketCanReadInvalid

    @staticmethod
    def build_arbitration_id(n2k_msg: NMEA2000Msg) -> int:
        can_id = n2k_msg.sa
        pf = (n2k_msg.pgn >> 8) & 0xFF
        if pf < 240:
            can_id |= (n2k_msg.pgn + n2k_msg.da) << 8
        else:
            can_id |= n2k_msg.pgn << 8
        can_id |= (n2k_msg.prio & 7) << 26
        return can_id

    def nrun(self):

        #  Run loop

        while not self._stop_flag:

            # read the CAN bus
            try:
                msg = self.read_can()
            except SocketCanReadInvalid:
                continue
            _logger.debug("CAN RECV:%s" % str(msg))
            self.process_receive_msg(msg)

            # end of the run loop

        # thread exit section
        if self._trace is not None:
            self._trace.stop_trace()
        self._bus.shutdown()
        _logger.info("CAN Interface %s stopped" % self.name)

    def put_can_msg(self, can_id, data) -> bool:
        msg = Message(arbitration_id=can_id, is_extended_id=True, timestamp=time.time(), data=data)
        try:
            self._in_queue.put(msg, timeout=5.0)
        except queue.Full:
            _logger.error("Socket CAN Write buffer full")
            self._write_errors += 1
            if self._write_errors > 20:
                raise SocketCanError("Socket write buffer full")
            else:
                return False
        self._write_errors = 0
        return True

    def send(self, n2k_msg: NMEA2000Msg, force_send=False):

        if not self._allowed_send.is_set() and not force_send:
            _logger.error("Trying to send messages on the CAN BUS while no address claimed")
            return

        can_id = self.build_arbitration_id(n2k_msg)

        _logger.debug("CAN interface send in queue message: %s" % n2k_msg.format1())

        # Fast packet processing
        if n2k_msg.fast_packet:
            _logger.debug("CAN interface -> start split fast packet")
            for data in self._fp_handler.split_message(n2k_msg.pgn, n2k_msg.payload):
                if not self.put_can_msg(can_id, data):
                    return False
        else:
            return self.put_can_msg(can_id, n2k_msg.payload)
        return True

    def send_broadcast_with_iso_tp(self, msg: NMEA2000Msg):
        '''
        Send a PGN with the J1939/21 Transport protocol
        '''
        tp_transact, tpcm_msg = self._iso_tp_handler.new_output_transaction(msg)
        can_id = self.build_arbitration_id(tpcm_msg)
        # send the broadcast announcement
        if not self.put_can_msg(can_id, tpcm_msg.payload):
            return False
        # now send the data
        bam_tpdt_can_id = self.build_arbitration_id(NMEA2000Msg(60160, 7, msg.sa, 255))
        for data in tp_transact.split_message():
            if not self.put_can_msg(bam_tpdt_can_id, data):
                return False
        return True

    def stop_trace(self):
        if self._trace is not None:
            self._trace.stop_trace()



class SocketCANWriter(NavThread):

    def __init__(self, in_queue, can_interface, trace):

        super().__init__(name=f"{can_interface.name}-Writer", daemon=True)
        self._can_interface = can_interface
        self._in_queue = in_queue
        self._bus = None
        self._trace = trace
        self._stop_flag = False
        self._total_msg = 0
        # self._access_lock = can_interface.access_lock

    def set_bus(self, bus):
        self._bus = bus

    def stop(self):
        self._stop_flag = True

    def total_msg(self):
        return self._total_msg

    def nrun(self):
        '''
        Wait for messages to be sent on the queue and then send them to the CAN BUS
        Message pacing is implemented with a fixed timing of 5ms (to be improved)
        '''

        #  Run loop
        last_write_time = time.monotonic()
        while not self._stop_flag:

            try:
                msg = self._in_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            # 2024-09-07 change the pacing algorithm
            msg_pace = time.monotonic() - last_write_time
            # each ECU is allowed to max 20% of the bus, so 1 msg every 5ms
            if msg_pace < 0.005:
                # stop the thread for the delta
                time.sleep(0.005 - msg_pace)
            if self._trace is not None:
                dts = datetime.datetime.fromtimestamp(msg.timestamp)
                self._trace.trace_n2k_raw_can(dts, self._total_msg, NMEAMsgTrace.TRACE_OUT,
                                              "%08X,%s" % (msg.arbitration_id, msg.data.hex()))
            # if self._access_lock.acquire(timeout=2.0):
                #_logger.debug("Acquire write lock")
            try:
                _logger.debug("CAN sending: %s" % str(msg))
                self._total_msg += 1
                self._bus.send(msg, 5.0)
                last_write_time = time.monotonic()
            except ValueError:
                # can happen if the thread was blocked while the CAN interface is closed
                break
            except CanError as e:
                _logger.error("Error receiving message from channel %s: %s" % (self._can_interface.channel, e))
                #_logger.debug("release write lock")
                # self._access_lock.release()
            # else:
                # _logger.error("%s CAN write lock failed" % self._can_interface.name)
            '''
            except CanTimeoutError:
                _logger.error("CAN send timeout error - message lost")
                continue
            '''

            # end of the run loop
        _logger.info("Socket CAN Write thread stops")


