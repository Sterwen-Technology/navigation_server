#-------------------------------------------------------------------------------
# Name:        navigation_server.py
# Purpose:     top module for the navigation server
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import sys
import os
from argparse import ArgumentParser
import signal

import nmea0183
from server_common import NavTCPServer
from shipmodul_if import *
from console import Console
from publisher import *
from client_publisher import *
from internal_gps import *
from simulator_input import *


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument("-p", "--port", action="store", type=int,
                   default=10110,
                   help="Listening port for Shipmodul input, default is 10110")
    p.add_argument("-a", "--address", action="store", type=str,
                   default='',
                   help="IP address or URL for Shipmodul, no default")
    p.add_argument("-pr", "--protocol", action="store", type=str,
                   choices=['TCP','UDP'], default='UDP',
                   help="Protocol to read NMEA sentences, default UDP")
    p.add_argument("-s", "--server", action="store", type=int,
                   default=4500,
                   help="NMEA server port, default 4500")
    p.add_argument('-d', '--trace_level', action="store", type=str,
                   choices=["CRITICAL","ERROR", "WARNING", "INFO", "DEBUG"],
                   default="INFO",
                   help="Level of traces, default INFO")
    p.add_argument('-cp', '--config_port', action="store", type=int,
                   default=4501,
                   help="port for Shipmodul configuration server, default 4501")
    p.add_argument("-t", "--timeout", action="store", type=float,
                   default=30.0,
                   help="Timeout on reception of messages from Shipmodul, default 30sec")
    p.add_argument("-m", "--max_connections", action="store", type=int, default=16,
                   help="Maximum number of simultaneous connections on server, default 16"
                   )
    p.add_argument("-b", "--heartbeat", action="store", type=float,
                   default=10.0,
                   help="Active connection heartbeat period, default 60.0s")
    p.add_argument("-l", "--log", action="store", type=str,
                   help="Logfile for all incoming NMEA sentences")
    p.add_argument("-c", "--console", action="store", type=int,
                   default=4502,
                   help="Console port, default 4502")
    p.add_argument("-ns", "--nmea_sender", action="store", type=int,
                   default=4503,
                   help="NMEA message sender port, default 4503")
    p.add_argument("-sm", "--simul", action="store", type=str,
                   help="IP address of NMEA Simulator")
    p.add_argument("-sp", "--simul_port", action="store", type=int,
                   default=3555, help="Port for simulator default is 3555")
    p.add_argument('-ti', '--trace_input', action='store', type=str)
    return p


parser = _parser()
_logger = logging.getLogger("ShipDataServer")


class Options(object):
    def __init__(self, p):
        self.parser = p
        self.options = None

    def __getattr__(self, name):
        if self.options is None:
            self.options = self.parser.parse_args()
        try:
            return getattr(self.options, name)
        except AttributeError:
            raise AttributeError(name)


class NMEA_server(NavTCPServer):

    '''
    Server class for NMEA clients

    '''
    def __init__(self, port, options):
        super().__init__("NMEA_Server", port)
        self._instruments = []
        self._options = options
        self._connections = {}
        self._timer = None
        self._sender = None
        self._sender_instrument = None

    def start_timer(self):
        self._timer = threading.Timer(self._options.heartbeat, self.heartbeat)
        self._timer.name = "NMEA server timer"
        self._timer.start()

    def stop_timer(self):
        if self._timer is not None:
            self._timer.cancel()

    def run(self):
        _logger.info("NMEA server ready")
        self.start_timer()
        self._socket.settimeout(5.0)
        while not self._stop_flag:
            _logger.info("Data server waiting for new connection")
            self._socket.listen(1)
            if len(self._connections) <= self._options.max_connections:
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
                _logger.critical("Maximum number of connections (%d) reached:" % self._options.max_connections)
                time.sleep(5.0)
                continue

            _logger.info("New connection from IP %s port %d" % address)
            client = ClientConnection(connection, address, self)
            self._connections[address] = client
            # now create a publisher for all instruments
            pub = NMEA_Publisher(client, self._instruments)
            pub.start()
            if self._sender_instrument is not None and self._sender is None:
                self._sender = NMEA_Sender(client, self._sender_instrument)
                if self._options.trace_input is not None:
                    trpub = SendPublisher(self._sender, self._options.trace_input)
                    trpub.start()
                self._sender.start()
            # end of while loop
        _logger.info("NMEA server thread stops")
        self._socket.close()

    def add_instrument(self, instrument):
        self._instruments.append(instrument)
        if instrument.default_sender():
            self._sender_instrument = instrument
        # now if we had some active connections we need to create the publishers
        for client in self._connections.values():
            pub = NMEA_Publisher(client, instrument)
            pub.start()

    def remove_client(self, address):
        del self._connections[address]

    def remove_sender(self):
        self._sender = None

    def heartbeat(self):
        _logger.info("Server heartbeat number of connections: %d"
                     % len(self._connections))
        if self._stop_flag:
            return
        self.start_timer()
        to_be_closed = []
        for client in self._connections.values():
            if client.msgcount() == 0:
                # no message during period
                _logger.info("Sending heartbeat on %s" % client.descr())
                heartbeat_msg = nmea0183.ZDA().message()
                if client.send(heartbeat_msg):
                    to_be_closed.append(client)
                client.reset_period()
        for client in to_be_closed:
            client.close()

    def stop(self):
        _logger.info("Main NMEA server stopping")
        self._stop_flag = True
        self.stop_timer()
        clients = self._connections.values()
        for client in clients:
            client._close()
        self._connections = {}

    def read_status(self):
        out = {}
        out['object'] = 'server'
        out['name'] = self.name
        out['port'] = self._port
        if len(self._connections) > 0:
            connections = []
            for c in self._connections.values():
                connections.append(c.read_status())
            out['connections'] = connections
        else:
            out['connection'] = 'no connections'
        return out


class NavigationServer:

    def __init__(self):

        self._name = 'main'
        self._console = None
        self._servers = []
        self._instruments = []
        self._publishers = []
        self._sigint_count = 0
        self._is_running = False
        self._logfile = None

        signal.signal(signal.SIGINT, self.stop_handler)

    @property
    def instruments(self):
        return self._instruments

    def name(self):
        return self._name

    def set_console(self, console):
        self._console = console
        self._servers.append(console)
        console.add_server(self)

    def add_server(self, server):
        self._servers.append(server)
        self._console.add_server(server)

    def start(self):
        def start_publisher(pub):
            for instrument in self._instruments:
                instrument.register(pub)
            pub.start()
        for publisher in self._publishers:
            start_publisher(publisher)
        for server in self._servers:
            server.start()
        for inst in self._instruments:
            inst.start()
        self._is_running = True

    def wait(self):
        for server in self._servers:
            server.join()
            _logger.info("%s threads joined" % server.name())
        for inst in self._instruments:
            inst.join()
            _logger.info("Instrument %s thread joined" % inst.name())
        print_threads()
        self._is_running = False

    def stop_server(self):
        for server in self._servers:
            server.stop()
        for inst in self._instruments:
            inst.stop()
        for pub in self._publishers:
            pub.stop()
        # self._console.close()
        _logger.info("All servers stopped")

    def stop_handler(self, signum, frame):
        self._sigint_count += 1
        if self._sigint_count == 1:
            _logger.info("SIGINT received => stopping the system")
            self.stop_server()
        else:
            print_threads()
            if self._sigint_count > 2:
                os._exit(1)
        # sys.exit(0)

    def add_instrument(self, instrument):
        self._instruments.append(instrument)
        for server in self._servers:
            server.add_instrument(instrument)
        if self._is_running:
            instrument.start()

    def add_publisher(self, publisher: Publisher):
        self._publishers.append(publisher)
        publisher.start()


def print_threads():
    print("Number of active threads:", threading.active_count())
    thl = threading.enumerate()
    for t in thl:
        print(t.name)


def main():
    opts = Options(parser)
    # logger setup => stream handler for now
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel(opts.trace_level)

    nmea0183.NMEA0183Sentences.init('SN')
    #  start the console

    console = Console(opts.console)

    main_server = NavigationServer()
    main_server.set_console(console)

    # create the NMEA server
    main_server.add_server(NMEA_server(opts.server, opts))
    shipmodul = ShipModulInterface.create_instrument(opts)
    main_server.add_instrument(shipmodul)
    main_server.add_server(ShipModulConfig(opts.config_port, shipmodul))
    # add additional instruments
    # server.add_instrument(InternalGps())
    # add the simulator
    try:
        simul_addr = opts.simul
        if simul_addr is not None:
            simul = SimulatorInput(simul_addr, opts.simul_port)
            main_server.add_instrument(simul)
            pub = Injector('Simulator', [simul], shipmodul)
            main_server.add_publisher(pub)
    except AttributeError:
        pass

    # do we have log
    try:
        logfile = opts.log
        if logfile is not None:
            logpub = LogPublisher(main_server.instruments, logfile)
            main_server.add_publisher(logpub)

    except AttributeError:
        pass
    main_server.start()
    main_server.wait()


if __name__ == '__main__':
    main()
