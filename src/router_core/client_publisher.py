#-------------------------------------------------------------------------------
# Name:        client_publisher
# Purpose:     Publisher classes linked to TCP client
#
# Author:      Laurent Carré
#
# Created:     16/12/2021
# Copyright:   (c) Laurent Carré Sterwen Technolgy 2021
# Licence:     <your licence>
#-------------------------------------------------------------------------------
import socket
import threading
import logging

from .publisher import Publisher
from router_common import NavGenericMsg, N2K_MSG, NULL_MSG
from .IPCoupler import TCPBufferedReader
from .coupler import Coupler
from .nmea0183_msg import process_nmea0183_frame
from .nmea2000_msg import fromPGDY, fromPGNST, N2KEncodeError

_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class NMEAPublisher(Publisher):

    def __init__(self, client, couplers: list, filters):

        super().__init__(None, internal=True, couplers=couplers, name=client.descr(), filters=filters)
        self._client = client

        client.add_publisher(self)
        _logger.info("NMEA Publisher %s created" % self.object_name())

    def process_msg(self, msg: NavGenericMsg):
        if msg.raw is None:
            _logger.error("No transparent payload available for %s => wrong nmea2000 mode on input ?" % msg.dump())
            return True
        return not self._client.send(msg.raw)

    def last_action(self):
        if not self._stopflag:
            self._client.close()

    def descr(self):
        return self._client.descr()


class NMEA2000DYPublisher(NMEAPublisher):

    def __init__(self, client, couplers, filters):
        super().__init__(client, couplers, filters)

    def process_msg(self, msg: NavGenericMsg):
        if msg.type == N2K_MSG:
            try:
                data = msg.msg.asPDGY()
            except N2KEncodeError:
                _logger.error("Error on message %s => ignoring - check configuration" % msg.msg.format2())
                return True
            return not self._client.send(data)
        else:
            return super().process_msg(msg)


class NMEA2000STPublisher(NMEAPublisher):

    def __init__(self, client, couplers, filters):
        super().__init__(client, couplers, filters)

    def process_msg(self, msg: NavGenericMsg):
        if msg.type == N2K_MSG:
            data = msg.msg.asPGNST()
            return not self._client.send(data)
        else:
            return super().process_msg(msg)


class NMEASender(threading.Thread):

    msg_processing = {'transparent': process_nmea0183_frame,
                      'dyfmt': fromPGDY, 'stfmt': fromPGNST}

    def __init__(self, connection: socket, address, coupler: Coupler, nmea2000_mode, buffer_size, timeout):
        super().__init__(name="Sender-" + "%s:%d" % address, daemon=True)
        self._connection = connection
        self._address = address
        self._coupler = coupler
        self._buffer_size = buffer_size
        self._timeout = timeout
        self._publisher = None
        self._stop_flag = False
        self._msgcount = 0
        self._silent_count = 0
        self._msg_processing = self.msg_processing[nmea2000_mode]

    def add_publisher(self, publisher):
        self._publisher = publisher

    def run(self) -> None:
        reader = TCPBufferedReader(self._connection, b'\r\n', self._address, self._msg_processing,
                                   self._buffer_size, self._timeout)
        while not self._stop_flag:
            msg = reader.read()
            # print(msg.printable())
            if msg.type == NULL_MSG:
                break
            self._msgcount += 1
            self._coupler.send_msg_gen(msg)
            if self._publisher is not None:
                self._publisher.publish(msg)
        _logger.info("Stopping %s" % self.name)
        reader.stop()
        self._connection.close()

    def stop(self):
        _logger.info("NMEASender stop request")
        self._stop_flag = True
        if self._publisher is not None:
            self._publisher.stop()
        self._connection.close()

    def reset_period(self):
        self._msgcount = 0
        self._silent_count = 0

    def msgcount(self):
        return self._msgcount

    def add_silent_period(self):
        self._silent_count += 1

    def silent_count(self):
        return self._silent_count


class ClientConnection:
    '''
    class to implement the connection between client and server
    perform all I/O on communication socket

    Created by the server upon accept for a new client connection
    '''
    def __init__(self, connection, address, server):
        self._socket = connection
        self._address = address
        self._server = server
        self._totalmsg = 0
        self._total_recmsg = 0
        self._periodmsg = 0
        self._silent_count = 0
        self._pubs = []
        self._sender = None

    def send(self, msg):
        try:
            self._socket.sendall(msg, socket.MSG_DONTWAIT)
            self._totalmsg += 1
            self._periodmsg += 1
            return False
        except OSError as e:
            _logger.warning(
                "Client:send Error writing data on %s:%d connection:%s => STOP" % (self._address[0], self._address[1], str(e)))
            return True

    def get(self):
        try:
            msg = self._socket.recv(512)
            self._total_recmsg += 1
            self._periodmsg += 1
        except OSError as e:
            _logger.warning(
                "Error reading data on %s:%d connection:%s => STOP" % (self._address[0], self._address[1], str(e)))
            return None
        if len(msg) == 0:
            _logger.warning(
                "Error reading data on %s:%d no data => STOP" % (self._address[0], self._address[1]))
            return None
        _logger.debug("Msg received:%s"% msg.decode().strip('\n\r'))
        # print("Msg received:%s"% msg.decode().strip('\n\r'))
        return msg

    def close(self):
        self._close()
        self._server.remove_client(self._address)

    def _close(self):
        if self._sender is not None:
            self._sender.stop()
            # self._server.remove_sender()
        for p in self._pubs:
            p.deregister()
            p.stop()
        self._socket.close()

    def reset_period(self):
        self._periodmsg = 0

    def msgcount(self):
        return self._periodmsg

    def total_msg(self):
        return self._totalmsg

    def remote_ip(self):
        return self._address[0]

    def remote_port(self):
        return self._address[1]

    def add_silent_period(self):
        self._silent_count += 1

    def silent_count(self):
        return self._silent_count

    def clear_silent_count(self):
        self._silent_count = 0

    def add_publisher(self, pub):
        self._pubs.append(pub)

    def descr(self):
        return "Connection %s:%d" % self._address

    def connection(self):
        return self._socket

    def address(self):
        return self._address

    def read_status(self):
        out = {}
        out['object'] = 'connection'
        out['name'] = self.descr()
        out['total_msg_in'] = self._total_recmsg
        out['total_msg_out'] = self._totalmsg
        if self._sender is None:
            out['sender'] = None
        else:
            out['sender'] = self._sender.name
            out['sender_running'] = self._sender.is_alive()
        out['number_publisher'] = len(self._pubs)
        return out
