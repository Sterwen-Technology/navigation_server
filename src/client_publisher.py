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

import threading
import logging
from publisher import Publisher

_logger = logging.getLogger("ShipDataServer")


class NMEA_Publisher(Publisher):

    def __init__(self, client, instruments: list):

        super().__init__(None, internal=True, instruments=instruments, name=client.descr())
        self._client = client

        client.add_publisher(self)
        # reader.register(self)

    def process_msg(self, msg):
        return not self._client.send(msg)

    def last_action(self):
        if not self._stopflag:
            self._client.close()

    def descr(self):
        return self._client.descr()


class NMEA_Sender(threading.Thread):

    def __init__(self, client, instrument):
        super().__init__(name="Sender-"+client.descr())
        self._client = client
        self._instrument = instrument
        self._client.set_sender(self)
        self._publisher = None

    def add_publisher(self, publisher):
        self._publisher = publisher

    def run(self) -> None:
        while True:
            msg = self._client.get()
            if msg is None:
                break
            # we can have several messages in a single TCP message
            start = 0
            while start < len(msg):
                try:
                    end = msg.index(b'\n', start)
                except ValueError:
                    _logger.error("Error splitting message at index:%d %s" % (start, str(msg[start:])))
                    break
                message = msg[start:end+1]
                # print("Command sent:", message)
                self._instrument.send_cmd(message)
                if self._publisher is not None:
                    self._publisher.publish(message)
                start = end + 1

    def stop(self):
        if self._publisher is not None:
            self._publisher.stop()


class ClientConnection:
    def __init__(self, connection, address, server):
        self._socket = connection
        self._address = address
        self._server = server
        self._totalmsg = 0
        self._total_recmsg = 0
        self._periodmsg = 0
        self._pubs = []
        self._sender = None

    def send(self, msg):
        try:
            self._socket.sendall(msg)
            self._totalmsg += 1
            self._periodmsg += 1
            return False
        except OSError as e:
            _logger.warning(
                "Error writing data on %s:%d connection:%s => STOP" % (self._address[0], self._address[1], str(e)))
            return True

    def get(self):
        try:
            msg = self._socket.recv(512)
            self._total_recmsg += 1
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
            self._server.remove_sender()
        for p in self._pubs:
            p.deregister()
            p.stop()
        self._socket.close()

    def reset_period(self):
        self._periodmsg = 0

    def msgcount(self):
        return self._periodmsg

    def add_publisher(self, pub):
        self._pubs.append(pub)

    def set_sender(self, sender):
        self._sender = sender

    def descr(self):
        return "Connection %s:%d" % self._address

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
