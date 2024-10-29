#-------------------------------------------------------------------------------
# Name:        ikonvert
# Purpose:     DigitalYacht iKonvert interface
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import serial
import threading
import queue
import base64

from router_core.coupler import Coupler
from router_core.nmea2000_msg import NMEA2000Msg
from router_common.generic_msg import *
from router_common.message_trace import NMEAMsgTrace
from router_common.nav_threading import NavThread

_logger = logging.getLogger("ShipDataServer"+"."+__name__)

# message type
(UNKNOWN, STATUS, NOT_CONN, ACK, NAK, N2K, N183) = range(7)


class iKonvertMsg:
    '''
    Class supporting the iKonvert message for processing and conversion
    '''

    __slots__ = ['_type', '_raw', '_msg', '_param']

    def __init__(self, data: bytearray):
        self._type = UNKNOWN
        self._raw = None
        self._msg = None
        self._param = {}
        self.decode(data)

    def decode(self, data: bytearray):

        self._raw = data
        if len(data) < 8:
            _logger.error("iKonvert incorrect data frame len=%d" % len(data))
            raise ValueError
        _logger.debug("iKonvert received:%s" % data)
        fields = data.split(b',')
        if len(fields) < 2:
            raise ValueError

        if fields[0][0:6] == b'!PDGY':
            self._type = N2K
            msg_data = fields[6].rstrip(b'\r\n')
            if len(msg_data) == 0:
                # we have a problem
                _logger.error(f"iKonvert incorrect NMEA2000 message (no data): {data}")
                raise ValueError
            self._msg = NMEA2000Msg(
                pgn=int(fields[1]),
                prio=int(fields[2]),
                sa=int(fields[3]),
                da=int(fields[4]),
                payload=base64.b64decode(msg_data)
                )
        elif fields[0][0:6] == b'$PDGY':
            if fields[1][0] == ord('0'):
                if len(fields[3]) == 0:
                    self._type = NOT_CONN
                else:
                    self._type = STATUS
                    self._param['bus_load'] = fields[2]
                    self._param['frame_errors'] = int(fields[3])
                    self._param['nb_devices'] = fields[4]
                    self._param['uptime'] = fields[5]
                    self._param['CAN_address'] = fields[6]
                    self._param['nb_rejected_PGN'] = int(fields[7])
            elif fields[1] == b'TEXT':
                self._type = NOT_CONN
                self._param['boot'] = fields[2]
            elif fields[1] == b'ACK':
                self._type = ACK
                self._param['message'] = fields[2]
            elif fields[1] == b'NAK':
                self._type = NAK
                self._param['error'] = fields[2]
            else:
                _logger.error("iKonvert Unknown message type %s %s" % (fields[0], fields[1]))
                raise ValueError
        else:
            if fields[0][0] == ord('$'):
                # this shall be NMEA0183
                self._type = N183
                self._msg = data
            else:
                _logger.error("iKonvert Unknown message type %s %s" % (fields[0], fields[1]))
                raise ValueError

        return self

    def get(self, param):
        return self._param.get(param, None)

    @property
    def type(self):
        return self._type

    @property
    def raw(self):
        return self._raw

    @property
    def msg(self):
        return self._msg


class iKonvertRead(NavThread):
    '''
    Class for low level read on the iKonvert adapter
    Run asynchronously and callback according to the message type
    '''

    def __init__(self, coupler, tty, callback_table):
        '''
        parameters:
        instrument: main coupler (instance of iKonvert)
        tty: serial connection
        callback_table: jump table according the message type
        '''
        self._tty = tty
        self._coupler = coupler
        super().__init__(name="IKonvertRead", daemon=True)

        self._stop_flag = False
        self._callback_table = callback_table

    def nrun(self) -> None:
        while self._stop_flag is False:
            try:
                data = self._tty.readline()
            except serial.SerialException as e:
                _logger.error("iKonvert read error: %s" % str(e))
                continue
            if len(data) == 0:
                # that is a suspected timeout
                _logger.info("iKonvert read on %s timeout" % self._coupler.tty_name)
                continue
            self._coupler.trace_raw(NMEAMsgTrace.TRACE_IN, data, strip_suffix='\r\n')
            self._coupler.increment_count()
            try:
                msg = iKonvertMsg(data)
            except (ValueError, IndexError, KeyError):
                _logger.error("iKonvert decoding error on message:%s" % data)
                continue

            self._callback_table[msg.type](msg)
            # end of read loop
        _logger.info("stopped iKonvert read")

    def stop(self):
        self._stop_flag = True


class iKonvert(Coupler):
    """
    This class implement the interface towards the iKonvert Digital Yacht USB-NMEA2000 device
    Inherits from Coupler
    The full connection logic is handled by the class
    NMEA0183 or NMEA2000 messages are pushed in the input queue of the coupler
    """

    (IKIDLE, IKREADY, IKCONNECTED) = range(10, 13)
    (WAIT_MSG, WAIT_CONN, WAIT_ACKNAK) = range(20, 23)
    end_line = b'\r\n'

    def __init__(self, opts):
        # opts["name"] = "iKonvert"
        super().__init__(opts)
        self._separator = b'\r\n'
        self._separator_len = 2
        self._tty_name = opts.get("device", str, "/dev/ttyUSB0")
        self._mode = opts.get("mode", str, "ALL")  # ALL (send all PGN) or NORMAL (send only requested PGN)
        self._tty = None
        self._reader = None
        self._wait_sem = threading.Semaphore(0)
        self._lock = threading.Lock()  # to prevent re-entering some operations
        self._rx_pgn = []
        self._tx_pgn = []
        self._ikstate = self.IKIDLE
        self._wait_event = 0
        self._queue_size = opts.get('msg_queue_size', int, 10)
        self._queue = queue.Queue(self._queue_size)
        self._queue_tpass = False
        self._cmd_result = None
        self._status_count = 0

    @property
    def tty_name(self):
        return self._tty_name

    def open(self):
        # this section is critical
        self._lock.acquire()  # block
        _logger.info("iKonvert opening serial interface with initial state %d" % self._ikstate)
        if self._ikstate == self.IKCONNECTED:
            self._lock.release()
            return True
        if self._tty is None:
            try:
                self._tty = serial.Serial(self._tty_name, baudrate=230400, timeout=2.0)
            except serial.serialutil.SerialException as e:
                _logger.error("Opening serial interface for IKonvert: %s" % str(e))
                self._lock.release()
                return False
            _logger.info("iKonvert serial interface %s open" % self._tty_name)
        # build the callback_table
        callback_table = {UNKNOWN: self.process_status, STATUS: self.process_status, NOT_CONN: self.process_status,
              ACK: self.process_acknak, NAK: self.process_acknak, N2K: self.process_nmea, N183: self.process_nmea}
        if self._reader is None:
            self._reader = iKonvertRead(self, self._tty, callback_table)
            self._reader.start()
        self.wait_status()
        if self._ikstate == self.IKREADY:
            # the gateway is not connected
            self.send_loc_cmd('N2NET_INIT', self._mode)
            self.wait_status()
        self._lock.release()
        if self._ikstate != self.IKCONNECTED:
            return False
        else:
            _logger.info("%s coupler ready" % self.object_name())
            return True

    def process_nmea(self, msg):
        # print("N2K message received pgn %s" % msg.get('pgn'))
        if self._ikstate != self.IKCONNECTED:
            #  a normal message is received before the status
            #  lets put it for status process
            self.process_status(msg)
            if self._ikstate != self.IKCONNECTED:
                return

        if msg.type == N183:
            nav_msg = NavGenericMsg(N0183_MSG, msg.raw)
        else:
            nav_msg = NavGenericMsg(N2K_MSG, msg.raw, msg.msg)
        # self.trace(self.TRACE_IN, nav_msg)
        try:
            self._queue.put(nav_msg, block=False)
        except queue.Full:
            # just discard
            _logger.error("iKonvert write queue full discard message:%s" % msg.raw)

    def process_status(self, msg):

        if msg.type == NOT_CONN:
            if self._ikstate == self.IKCONNECTED:
                _logger.info("iKonvert disconnected from NMEA network")
            self._ikstate = self.IKREADY
            if self._wait_event == self.WAIT_MSG:
                self._wait_event = 0
                self._wait_sem.release()
        else:
            if self._ikstate != self.IKCONNECTED:
                self._ikstate = self.IKCONNECTED
            if self._wait_event == self.WAIT_CONN or self._wait_event == self.WAIT_MSG:
                self._wait_event = 0
                self._wait_sem.release()
            if msg.type == STATUS:
                _logger.debug("iKonvert connected to NMEA2000 network addr:%s" % msg.get('CAN_address'))
                frame_errors = msg.get('frame_errors')
                rejected_pgn = msg.get('nb_rejected_PGN')
                if frame_errors + rejected_pgn > 0 :
                    _logger.warning(f'iKonvert frame errors:{frame_errors} rejected PGN:{rejected_pgn}')
                self._status_count += 1

    def process_acknak(self, msg):
        _logger.info("iKonvert ACK/NAK message")
        if self._wait_event == self.WAIT_ACKNAK:
            if msg.type == ACK:
                self._cmd_result = (ACK, msg.get('message'))
            else:
                self._cmd_result = (NAK, msg.get('error'))
            self._wait_event = 0
            self._wait_sem.release()
        else:
            # unexpected ACK/NACK
            if msg.type == ACK:
                info = msg.get('message')
                t = 'ACK'
            else:
                info = msg.get('error')
                t = 'NAK'
            _logger.error("iKonvert unexpected %s reason %s" % (t, info))

    def wait_status(self):
        self._wait_event = self.WAIT_MSG
        self._wait_sem.acquire()

    def increment_count(self):
        self._total_msg_raw += 1

    def send_loc_cmd(self, cmd, option=None, wait=ACK):
        self._cmd_result = None
        cmd_buf = "$PDGY,%s" % cmd
        if option is not None:
            cmd_buf = "%s,%s" % (cmd_buf, option)
        _logger.info("iKonvert sending command %s" % cmd_buf)
        send_buf = cmd_buf.encode()
        self.trace_raw(NMEAMsgTrace.TRACE_OUT, send_buf)
        self._tty.write(send_buf)
        self._tty.write(self.end_line)
        self._tty.flush()
        if wait == ACK:
            self._wait_event = self.WAIT_ACKNAK
        else:
            self._wait_event = self.WAIT_MSG
        self._wait_sem.acquire()
        if wait == ACK:
            if self._cmd_result[0] == ACK:
                _logger.info("iKonvert CMD result OK")
            else:
                _logger.error("iKonvert CMD error %s" % self._cmd_result[1])

    def _read(self):
        return self._queue.get()

    def stop_communication(self):
        _logger.debug("iKonvert entering stop state=%d" % self._ikstate)
        if self._ikstate > self.IKREADY:
            self.send_loc_cmd('N2NET_OFFLINE', wait=0)
            self.wait_status()
        if self._reader is not None:
            self._reader.stop()
        self._queue.put(NavGenericMsg(NULL_MSG))
        self._ikstate = self.IKIDLE
        _logger.debug("iKonvert exiting stop state=%d" % self._ikstate)

    def close(self):
        _logger.info("iKonvert closing")
        if self._tty is not None:
            self._reader.join()
            self._tty.close()
            self._tty = None

    def send(self, msg: NavGenericMsg):
        '''
        That method is to send NMEA0183 messages
        '''
        if self._ikstate != self.IKCONNECTED:
            return False
        if self._trace_msg:
            self.trace(NMEAMsgTrace.TRACE_OUT, msg)
        _logger.debug("iKonvert write %s" % msg.printable())
        return self._send(msg.raw)

    def _send(self, frame) -> bool:
        '''
        Physical write to the iKonvert adapter
        '''
        try:
            self._tty.write(frame)
            self._tty.flush()
            return True
        except serial.SerialException as e:
            _logger.error("IKonvert write error: %s" % e)
            return False

    def define_n2k_writer(self):
        return self

    def stop_writer(self):
        pass  # do nothing to avoid recursion

    def send_n2k_msg(self, msg: NMEA2000Msg) -> bool:
        # encode the message TX PGN
        frame = b'!PGDY,%d,%d,%s\r\n' % (msg.pgn, msg.da, base64.b64encode(msg.payload))
        self.trace_raw(NMEAMsgTrace.TRACE_OUT, frame, strip_suffix='\r\n')
        return self._send(frame)




