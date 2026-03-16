#-------------------------------------------------------------------------------
# Name:        agent_cli.py
# Purpose:     top module for the navigation server
#
# Author:      Laurent Carré
#
# Created:     30/12/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import sys
import os
import logging
import time
from argparse import ArgumentParser
from curses.ascii import isdigit

from navigation_server.router_common import GrpcClient, AgentClient, GrpcAccessException
from navigation_server.navigation_clients import NetworkClient

_logger = logging.getLogger("ShipDataServer")


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument("-p", "--port", action="store", type=int,
                   default=4545,
                   help="Console listening port, default 4545")
    p.add_argument("-a", "--address", action="store", type=str,
                   default='127.0.0.1',
                   help="IP address or hostname for Navigation server, default is localhost")
    p.add_argument("-c", "--certificate", action="store", type=str, default=None,
                   help="Certificate file to use, default is None, in that case the default certificate is used")
    p.add_argument("-ns", "--no_sec", action="store_true", default=False,)
    p.add_argument("-st", "--start", action="store", type=str, default=None,
                   help="Start a specific process")
    p.add_argument("-sp", "--stop", action="store", type=str, default=None,
                   help="Stop a specific process")
    p.add_argument("-n", "--network", action="store_true", default=False,
                   help="Network configuration")
    p.add_argument("-v", "--verbose", action="store_true", default=False,
                   help="Verbose mode - set trace level to info")
    p.add_argument("-d", "--debug", action="store_true", default=False,
                   help="Debug mode - set trace level to debug")
    p.add_argument("-hs", "--halt", action="store_true", default=None,
                   help="Halt the server")
    p.add_argument("-rs", "--restart", action="store_true", default=None,
                   help="Restart the server")
    p.add_argument("-l", "--log", action="store", type=str,default=None,
                   help="systemd log for the service ctrl<c> to stop")
    p.add_argument("-gc", "--global_conf", action="store", type=str, default=None,
                   help=" Network Global configuration to be set. Requires the -n flag to be present")

    return p


parser = _parser()


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


class ProcessManager(object):
    def __init__(self, agent):
        self._processes = None
        self._process_list = None
        self._agent = agent
        self._system_proxy = agent.system_cmd('status')

    def refresh_processes(self):
        try:
            processes = self._system_proxy.get_processes()
        except GrpcAccessException:
            return
        self._processes = {p.name: p for p in processes}
        self._process_list = list(self._processes.keys())

    def display_processes(self):
        proc_index = 1
        for proc in self._processes.values():
            print(f"{proc_index}:{proc.name}\t\t{proc.state}")
            proc_index += 1

    def display_processes_list(self):
        proc_index = 1
        for proc in self._process_list:
            print(f"{proc_index}:{proc}")
            proc_index += 1

    def display_status(self):
        print(f"Connected to:{self._system_proxy.hostname} - version:{self._system_proxy.version}")

    def process_cmd(self, cmd, process_name):
        if process_name not in self._processes:
            _logger.error(f"Unknown process {process_name}")
            return
        self._agent.process_cmd(cmd, process_name)
        time.sleep(1)
        self.refresh_processes()

    def start_process(self, process_name):
        if isinstance(process_name, int):
            process_name = self._process_list[process_name-1]
        _logger.info(f"Starting process {process_name}")
        self.process_cmd('start', process_name)

    def server_cmd(self, cmd):
        self._agent.system_cmd(cmd)

    def print_log(self, process_name):
        if isinstance(process_name, int):
            process_name = self._process_list[process_name-1]
        try:
            for line in self._agent.get_log_msg(process_name):
                print(line)
        except GrpcAccessException:
            _logger.error(f"Error accessing server for logs on:{process_name}")
            return
        except KeyboardInterrupt:
            return



class NetworkManagerCli(object):

    def __init__(self, client:NetworkClient):
        self._client = client
        # let's read the global configuration
        self._status = client.network_status('update')
        _logger.info(f"Network status: {self._status.status}-{self._status.details}")
        self._configuration = client.get_global_configuration()

    def print_interfaces(self):
        for interface in self._status.interfaces():
            if interface.state == 'connected':
                print(f"{interface.name} {interface.device_type()} connected to:{interface.connection.name}")
            else:
                print(f"{interface.name} {interface.device_type()} {interface.state}")

    def print_configuration(self):
        print("Network configurations:")
        for conf in self._configuration.configuration_names():
            print(f"\t{conf}")

    def set_configuration(self, configuration_name):
        print(f"Setting network configuration to {configuration_name}")
        if configuration_name not in self._configuration.configuration_names():
            _logger.error(f"Unknown network configuration {configuration_name}")
            return
        self._client.set_global_configuration(configuration_name)
        self._status = self._client.network_status('update')


def main():
    options = Options(parser)
    # logger setup => stream handler for now
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    if options.debug:
        _logger.setLevel(logging.DEBUG)
    elif options.verbose:
        _logger.setLevel(logging.INFO)
    else:
        _logger.setLevel(logging.WARNING)

    # Now we try to connect to the server
    secure_grpc = False
    if options.certificate is None:
        if os.getenv('NAV_CONF_DIR') is not None:
            cert_dir = os.getenv('NAV_CONF_DIR')
        else:
            cert_dir = os.getenv('HOME')
        default= os.path.join(cert_dir, 'certificates', 'nav_ca_cert.pem')
        if os.path.exists(default):
            _logger.info(f"Using default certificate file:{default}")
            options.certificate = default
        else:
            _logger.warning(f"No default certificate file specified: {default}")


    if options.no_sec:
        secure_grpc = False
    elif options.certificate is not None:
        try:
            with open(options.certificate, 'rb') as f:
                certificate = f.read()
                GrpcClient.set_ca_certificate(certificate)
                secure_grpc = True
        except (FileNotFoundError, IOError) as e:
            _logger.error(e)
            secure_grpc = False


    navigation_agent_server = GrpcClient.get_client(f"{options.address}:{options.port}", secure=secure_grpc)
    agent = AgentClient()
    navigation_agent_server.add_service(agent)
    navigation_agent_server.connect()
    if not navigation_agent_server.wait_connect(10.):
        # if no response from the agent server, let's give up
        _logger.error("No agent available")
        return
    process_manager = ProcessManager(agent)
    # let's process the global server command
    if options.halt is not None:
        print("Halting the server")
        process_manager.server_cmd('halt')
        return
    elif options.restart is not None:
        print("Restarting the server")
        process_manager.server_cmd('reboot')
        return

    process_manager.refresh_processes()
    process_manager.display_status()
    if options.log is not None:
        if isdigit(options.log):
            options.log = int(options.log)
        process_manager.print_log(options.log)
        return
    process_manager.display_processes()


    # process_manager.display_processes_list()
    if options.start is not None:
        if isdigit(options.start):
            options.start = int(options.start)
        process_manager.start_process(options.start)
        process_manager.display_processes()

    if options.network:
        network_client = NetworkClient()
        navigation_agent_server.add_service(network_client)
        network_manager = NetworkManagerCli(network_client)
        network_manager.print_interfaces()
        network_manager.print_configuration()
        if options.global_conf is not None:
            network_manager.set_configuration(options.global_conf)
            network_manager.print_interfaces()


if __name__ == '__main__':
    main()


