# -------------------------------------------------------------------------------
# Name:        NMEA2K-CAN Interface class
# Purpose:     Implements the direct CAN Bus interface
#
# Author:      Laurent Carré
#
# Created:     12/09/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
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
from queue import Queue

from can import Message, CanError, ThreadSafeBus

from navigation_server.router_core.nmea2000_msg import NMEA2000Msg
from navigation_server.nmea2000 import FastPacketHandler, FastPacketException
from navigation_server.nmea2000 import IsoTransportHandler, IsoTransportException
from navigation_server.nmea2000_datamodel import PGNDef
from navigation_server.router_common import NMEAMsgTrace, MessageTraceError, NavThread, build_subclass_dict
from navigation_server.router_common import ObjectFatalError


_logger = logging.getLogger("ShipDataServer." + __name__)


class SocketCanError(Exception):
    pass


class SocketCanReadInvalid(Exception):
    pass


def check_can_device(link: str):
    """
    This method checks the readiness of the can channel (link)
    link: name of the can channel to be checked
    No return => raise SocketCanError if not present or not ready
    """
    proc = subprocess.run(f'/sbin/ip link | grep {link}', shell=True, capture_output=True, text=True)
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
    Manage a socket CAN interface including transport layer both ISO and Fast Packets
    """
    (BUS_NOT_CONNECTED, BUS_CONNECTED, BUS_READY, BUS_SENS_ALLOWED) = range(0, 4)

    def __init__(self, channel: str, out_queue: queue.Queue, trace=False):

        try:
            check_can_device(channel)
        except SocketCanError as err:
            err_str = "CAN bus not available"
            _logger.critical("%s: %s" % (err_str, err))
            raise ObjectFatalError(err_str)

        super().__init__(name="CAN-if-%s" % channel)
        self._channel = channel
        self._bus = None
        self._queue = out_queue     # that is the queue used to push all message received towards application
        self._stop_flag = False
        # self._data_queue = None
        self._allowed_send = threading.Event()
        self._allowed_send.clear()
        self._bus_ready = threading.Event()
        self._bus_ready.clear()
        self._write_buffer_size: int = 40
        self._in_queue = queue.Queue(self._write_buffer_size)    # queue for outgoing messages to the bus (internal queue)
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
        self._writer.stop()
        self._writer.join() # change 2025-05-26 => wait until the writer stops before stopping the full service
        self._stop_flag = True
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
#  navigation_definitions access_lock(self):
#     return self._access_lock

    def total_msg_raw(self) -> int:
        return self._total_msg_in

    def total_msg_raw_out(self) -> int:
        return self._writer.total_msg()

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
        """
        function to read the bus and perform Fast packet reassembly
        push a NMEA200Msg when a valid message as been received or reassembled
        """

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
        try:
            fp_active = self._fp_handler.is_pgn_active(pgn, sa, data)
        except FastPacketException:
            return

        if fp_active:
            try:
                data = self._fp_handler.process_frame(pgn, sa, data)
                if data is None:
                    return
            except FastPacketException as e:
                _logger.error("CAN interface Fast packet (active) error %s pgn %d sa %d data %s" % (e, pgn, sa, data.hex()))
                return
        else:
            if PGNDef.fast_packet_check(pgn):
                try:
                    data = self._fp_handler.process_frame(pgn, sa, data)
                    if data is None:
                        return
                except FastPacketException as e:
                    _logger.error("CAN interface Fast packet (start) error %s pgn %d sa %d data %s" % (e, pgn, sa, data.hex()))
                    return
        # end fast packet handling
        n2k_msg = NMEA2000Msg(pgn, prio, sa, da, data)
        if n2k_msg is not None:
            try:
                # new in version 2.2 put a small timeout to allow the queue messages to be processed
                self._queue.put(n2k_msg, timeout=0.5)
            except queue.Full:
                _logger.warning("CAN read queue full, message discarded: %s" % n2k_msg.header_str())
                #  time.sleep(0.02) # remove as we have the timeout
        return

    def read_can(self) -> Message:
        """
        Perform the actual read on the CAN bus
        return a Message (python-can)
        raise SocketCanReadInvalid if any error occurs
        """
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
        """
        CAN bus read loop
        Ignore read errors
        """

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

    def put_can_msg(self, can_id: int, data: bytearray) -> bool:
        """
        Send a CAN message to the sending queue
        """
        msg = Message(arbitration_id=can_id, is_extended_id=True, timestamp=time.time(), data=data)
        try:
            self._in_queue.put(msg, timeout=5.0)
            self._write_errors = 0
        except queue.Full:
            _logger.error(f"CAN Interface {self.name} Write buffer full occurrence {self._write_errors}")
            self._write_errors += 1
            if self._write_errors > 10:
                raise SocketCanError("Socket write buffer full")
            else:
                return False
        return True

    def send(self, n2k_msg: NMEA2000Msg, force_send=False) -> bool:
        """
        Send a NMEA2000 message to the CAN bus
        Message will be split if FastPacket and send to the sending queue
        """

        if not self._allowed_send.is_set() and not force_send:
            _logger.error("Trying to send messages on the CAN BUS while no address claimed")
            return False

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


    def send_broadcast_with_iso_tp(self, msg: NMEA2000Msg):
        """
        Send a PGN with the J1939/21 Transport protocol
        """
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

    #
    #   Trace management methods
    #
    def stop_trace(self):
        if self._trace is not None:
            self._trace.stop_trace()
            self._trace = None
            self._writer.update_trace(None)


    def is_trace_active(self) -> bool:
        return self._trace is not None

    def start_trace(self, file_root:str = None):
        if file_root is None or len(file_root) == 0:
            file_root = self.name
        self._trace  = NMEAMsgTrace(file_root, self.__class__.__name__)
        self._writer.update_trace(self._trace)


class SocketCANWriter(NavThread):

    max_throughput = 2000.0
    min_interval_100 = 1. / max_throughput

    def __init__(self, in_queue: Queue, can_interface, trace):

        super().__init__(name=f"{can_interface.name}-Writer", daemon=True)
        self._can_interface = can_interface
        self._in_queue: Queue = in_queue
        self._in_queue_size = self._in_queue.maxsize
        self._bus = None
        self._trace = trace
        self._stop_flag = False
        self._total_msg = 0
        self._min_interval = (100. / 20.) * self.min_interval_100  # 20% of the bandwidth by default
        # self._access_lock = can_interface.access_lock

    def set_bus(self, bus):
        self._bus = bus

    def stop(self):
        self._stop_flag = True

    def update_trace(self, trace):
        self._trace = trace

    def total_msg(self) -> int:
        return self._total_msg

    def change_bandwidth(self, bandwidth: float):
        if 5. < bandwidth <= 50.:
            self._min_interval = (100. / bandwidth) * self.min_interval_100
        else:
            _logger.error("Cannot increase bandwidth over 50% of the bus bandwidth")


    def nrun(self):
        """
        CAN bus write loop
        Wait for messages to be sent on the queue and then send them to the CAN BUS
        Message pacing is implemented with a fixed timing of 5ms (to be improved)
        """

        #  Run loop
        last_write_time = time.monotonic()
        nberr = 0
        retry = False
        while not self._stop_flag:

            if not retry:
                try:
                    msg = self._in_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
            # 2024-09-07 change the pacing algorithm
            msg_pace = time.monotonic() - last_write_time
            # each ECU is allowed to a max bandwidth% of the bus, so a minimum interval is setup
            # except when the input queue start to fill-up
            # Burst implemented in version 2.2 to speed up the processing of the queue
            if self._in_queue.qsize() > self._in_queue_size - 2:
                # the input is filling up => burst mode
                burst = 5
            else:
                burst = 1
            if burst == 1 and msg_pace < self._min_interval:
                # stop the thread for the delta
                time.sleep(self._min_interval - msg_pace)
            while burst > 0:
                #
                # message can be sent as burst when the queue is filling up
                #
                if self._trace is not None:
                    dts = datetime.datetime.fromtimestamp(msg.timestamp)
                    self._trace.trace_n2k_raw_can(dts, self._total_msg, NMEAMsgTrace.TRACE_OUT,
                                                  "%08X,%s" % (msg.arbitration_id, msg.data.hex()))

                try:
                    _logger.debug("CAN sending: %s" % str(msg))
                    self._total_msg += 1
                    self._bus.send(msg, 5.0)
                    last_write_time = time.monotonic()
                    if retry:
                        _logger.info("SocketCANWriter success after retry (%4X) attempt:%d" % (msg.arbitration_id, nberr))
                    retry = False
                    nberr = 0
                except ValueError:
                    # can happen if the thread was blocked while the CAN interface is closed
                    raise SocketCanError(f"SocketCANWriter {self.name} CAN access closed during write => STOP")
                except CanError as e:
                    nberr += 1
                    _logger.error("SocketCANWriter: Error writing message (%4X) to channel %s: %s retry:%d" %
                                  (msg.arbitration_id, self._can_interface.channel, e, nberr))
                    burst = 1 # we stop burst
                    retry = True
                    last_write_time = time.monotonic()
                    if nberr > 20:
                        # more than 20 consecutive error no need to continue
                        _logger.critical("CAN Write too many errors stopping")
                        raise SocketCanError(f"Too many errors in write operations - suspecting CAN bus problem")
                burst -= 1
                if burst > 0:
                    # in case of burst limit anyway to 1000 msg/sec
                    # decrease to 500msg/sec 25-04-2025
                    time.sleep(0.002)
                    # then get one more message
                    try:
                        msg = self._in_queue.get(block=False)
                    except queue.Empty:
                        break  # stop burst


            # end of the run loop
        _logger.info("Socket CAN Write thread stops")


