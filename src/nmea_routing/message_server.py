#-------------------------------------------------------------------------------
# Name:        message_server.py
# Purpose:     module for the TCP data server
#
# Author:      Laurent Carré
#
# Created:     29/02/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

from nmea_routing.server_common import NavTCPServer, ConnectionRecord
from nmea_routing.client_publisher import *
from nmea0183.nmea0183_msg import *


_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class NMEAServer(NavTCPServer):

    '''
    Server class for NMEA clients

    '''
    publisher_class = {'transparent': NMEAPublisher, 'dyfmt': NMEA2000DYPublisher, 'stfmt': NMEA2000STPublisher}

    def __init__(self, options):

        super().__init__(options)
        self._couplers = []
        self._options = options
        self._nmea2000 = options.get_choice('nmea2000', ('transparent', 'dyfmt', 'stfmt'), 'transparent')
        # self._master = options.get('master', str, None)
        self._connections = {}
        self._timer = None
        self._timer_name = self.name + "-timer"
        # self._sender = None
        # self._sender_coupler = None
        self._client_lock = threading.Lock()

    def start_timer(self):
        self._timer = threading.Timer(self._heartbeat, self.heartbeat)
        self._timer.name = self._timer_name
        self._timer.start()

    def stop_timer(self):
        if self._timer is not None:
            self._timer.cancel()

    def run(self):
        _logger.info("%s ready listening on port %d" % (self.name, self._port))
        # self._sender_coupler = self.resolve_ref('sender')
        # print("Sender:", self._sender_instrument)
        self.start_timer()
        self._socket.settimeout(5.0)
        while not self._stop_flag:
            _logger.debug("%s waiting for new connection" % self.name)
            self._socket.listen(1)
            if len(self._connections) <= self._max_connections:
                try:
                    connection, address = self._socket.accept()
                except socket.timeout:
                    if self._stop_flag:
                        break
                    else:
                        continue
                if self._stop_flag:
                    connection.close()
                    break
            else:
                _logger.critical("Maximum number of connections (%d) reached:" % self._max_connections)
                time.sleep(5.0)
                continue

            _logger.info("New connection from IP %s port %d" % address)
            if len(self._couplers) == 0:
                _logger.critical("No coupler associated with NMEA server %s => connection refused" % self._name)
                connection.close()
                continue

            client = ClientConnection(connection, address, self)
            # critical section for adding the new client
            if self._client_lock.acquire(timeout=5.0):
                _logger.debug("NMEAServer lock acquire OK")
                self._connections[address] = client
                self._client_lock.release()
                _logger.debug("NMEAServer lock release OK")
            else:
                _logger.warning("Client add client lock acquire failed")
                connection.close()
                continue

            # now create a publisher for all instruments
            pub = self.publisher_class[self._nmea2000](client, self._couplers, self._filters)
            pub.start()

            # end of while loop => the thread stops
        _logger.info("%s thread stops" % self.name)
        self._socket.close()

    def add_coupler(self, coupler):
        '''
        The following test is too restrictive and does not work always - removed until better solution implemented
        if self._nmea2000 in ['dyfmt', 'stfmt']:
            if coupler.protocol() != 'nmea2000':
                _logger.error("Coupler %s is not configured for NMEA2000 and incompatible with server %s protocol" %
                              (coupler.name(), self._name))
                return
        '''
        self._couplers.append(coupler)
        _logger.info("Server %s adding coupler %s" % (self.name, coupler.object_name()))
        # now if we had some active connections we need to create the publishers
        for client in self._connections.values():
            #  Correction on 2024/05/18 => modify the existing publisher
            client.publisher.add_coupler(coupler)

    def remove_client(self, address) -> None:
        '''
        remove is protected by lock
        :param address:
        '''
        _logger.debug("NMEAServer removing client at address %s:%d" % address)
        if self._client_lock.acquire(timeout=5.0):
            _logger.debug("NMEAServer lock acquire OK")
            try:
                del self._connections[address]
                _logger.debug("NMEAServer removing client at address %s:%d successful" % address)
            except KeyError:
                _logger.warning("Client remove unknown address %s:%d" % address)
            self._client_lock.release()
            _logger.debug("NMEAServer lock release OK")
        else:
            _logger.warning("Client remove client lock acquire failed")

    #def remove_sender(self):
    #   self._sender = None

    def remove_coupler(self, coupler):
        _logger.info("Server %s removing coupler %s" % (self.name, coupler.object_name()))
        try:
            self._couplers.remove(coupler)
        except ValueError:
            _logger.error("Server %s removing coupler %s failed" % (self.name, coupler.object_name()))

    def heartbeat(self):
        _logger.info("%s heartbeat number of connections: %d"
                     % (self._name, len(self._connections)))
        if self._stop_flag:
            return
        self.start_timer()
        to_be_closed = []
        # this is a critical section
        if self._client_lock.acquire(timeout=2.0):
            _logger.debug("NMEAServer heartbeat lock acquire OK")
            for client in self._connections.values():
                _logger.debug("Heartbeat check %s msg:%d silent period:%d" %
                              (client.descr(), client.msgcount(), client.silent_count()))
                _logger.info("%s - number of messages sent:%d" % (client.descr(), client.total_msg()))
                if client.msgcount() == 0:
                    client.add_silent_period()
                    # no message during period
                    if client.silent_count() >= self._max_silent_period:
                        _logger.warning("No traffic on connection %s" % client.descr())
                        to_be_closed.append(client)
                    else:
                        _logger.info("Sending heartbeat on %s" % client.descr())
                        heartbeat_msg = ZDA().message()
                        if client.send(heartbeat_msg):
                            to_be_closed.append(client)
                else:
                    client.clear_silent_count()
                client.reset_period()
            for client in to_be_closed:
                _logger.debug("NMEA Server heartbeat - removing client %s" % client.descr())
                client._close()
                try:
                    del self._connections[client.address()]
                    _logger.debug("NMEAServer heartbeat removing client %s successful" % client.descr())
                except KeyError:
                    _logger.debug("NMEAServer heartbeat removing client %s => non existent" % client.descr())
            self._client_lock.release()
            _logger.debug("NMEAServer heartbeat lock release OK")
        else:
            _logger.warning("Cannot acquire lock during heartbeat")

    def stop(self):
        _logger.info("%s stopping" % self.name)
        self._stop_flag = True
        self.stop_timer()
        clients = self._connections.values()
        for client in clients:
            client._close()
        self._connections = {}

    def connections(self):
        result = []
        if self._client_lock.acquire(timeout=2.0):
            for c in self._connections.values():
                result.append(ConnectionRecord(c.remote_ip(), c.remote_port(), c.total_msg()))
            self._client_lock.release()
        else:
            _logger.warning("Cannot acquire lock during heartbeat")
        return result

    def connected(self) -> bool:
        return len(self._connections) > 0

    def nb_connections(self):
        return len(self._connections)

    def protocol(self) -> str:
        return self._nmea2000


class NMEASenderServer(NavTCPServer):

    '''
    Class to hold server for NMEA messaging towards a Coupler
    Messages are unidirectional
    '''

    def __init__(self, options):
        super().__init__(options)

        self._coupler = None
        self._options = options
        self._nmea2000 = options.get_choice('nmea2000', ('transparent', 'dyfmt', 'stfmt'), 'transparent')
        self._sender = None
        self._timer = None
        self._address = None
        self._buffer_size = options.get('buffer_size', int, 256)
        self._timer_name = self.name + "-timer"
        self._master = options.get('master', str, None)
        # print("(init) master=", self._master)
        # print("level", _logger.getEffectiveLevel())

    def start_timer(self):
        self._timer = threading.Timer(self._heartbeat, self.heartbeat)
        self._timer.name = self._timer_name
        self._timer.start()

    def stop_timer(self):
        if self._timer is not None:
            self._timer.cancel()

    def run(self):
        self._coupler = self.resolve_ref('coupler')
        if self._coupler is None:
            _logger.error("NMEA Sender %s Coupler %s unknown => STOP server" % (self.name,
                                                                                self._options.getv('coupler')))
            return

        _logger.info("%s ready listening on port %d" % (self.name, self._port))

        self.start_timer()
        self._socket.settimeout(5.0)
        while not self._stop_flag:
            _logger.debug("%s waiting for new connection" % self.name)
            self._socket.listen(1)
            try:
                connection, address = self._socket.accept()
            except socket.timeout:
                if self._stop_flag:
                    break
                else:
                    continue
            if self._stop_flag:
                connection.close()
                break

            # print("Master", self._master)
            if self._master is not None:
                if address[0] != self._master:
                    _logger.error("%s not authorized to send NMEA commands. Only %s is" % (address[0], self._master))
                    connection.close()
                    continue

            if self._sender is not None:
                # only one input connection allowed
                if address[0] != self._address[0]:
                    _logger.warning("%s already in use" % self.name)
                    connection.close()
                    continue
                # same address but new connection => let's close the existing one
                # now stop the sender thread
                self._sender.stop()
                self._sender.join()

            self._address = address
            # we must check that a new coupler has not been instanced and run
            self._coupler = self.resolve_ref('coupler')
            if not self._coupler.is_alive():
                # the Coupler is not running
                if self._coupler.has_run():
                    # there is nothing we can do here
                    _logger.error("%s associated coupler cannot run again" % self.name)
                    connection.close()
                    break
                self._coupler.force_start()
                self._coupler.request_start()

            _logger.info("Sender new connection from IP %s port %d" % address)
            _logger.info("%s client at address %s is becoming sender" % (self.name, address[0]))
            self._sender = NMEASender(connection, address, self._coupler, self._nmea2000,
                                      self._buffer_size, self._timeout)
            self._sender.start()
            # self._sender.join()
        # end of while loop => the thread stops
        _logger.info("%s thread stops" % self.name)
        self._socket.close()

    def heartbeat(self):
        if self._sender is not None:
            cs = "connected to %s:%d" % self._address
        else:
            cs = "not connected"
        _logger.info("%s heartbeat  %s" % (self._name, cs))
        self.start_timer()
        if self._stop_flag:
            return

        if self._sender is not None:
            _logger.debug("Send Heartbeat check %s:%d msg:%d silent period:%d" %
                          (self._address[0], self._address[1], self._sender.msgcount(), self._sender.silent_count()))
            if self._sender.msgcount() == 0:
                self._sender.add_silent_period()
                # no message during period
                if self._sender.silent_count() >= self._max_silent_period:
                    _logger.warning("Send: No traffic on connection %s:%d" % self._address)
                    self._sender.stop()
                    self._sender.join()
                    self._sender = None
            else:
                self._sender.reset_period()

    def remove_client(self, address) -> None:
        pass

    def stop(self):
        _logger.info("%s stopping" % self.name)
        self._stop_flag = True
        self.stop_timer()
        if self._sender is not None:
            self._sender.stop()

    def nb_connections(self):
        if self._sender is None:
            return 0
        else:
            return 1

    def connections(self):
        result = []
        if self._sender is not None:
            result.append(ConnectionRecord(self._address[0], self._address[1], self._sender.msgcount()))
        return result



