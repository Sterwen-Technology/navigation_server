#-------------------------------------------------------------------------------
# Name:        agent_service.py
# Purpose:     gRPC service for the local agent
#
# Author:      Laurent Carré
#
# Created:     26/02/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------


import subprocess
import shlex
import threading
import logging
import time
import signal
from socket import gethostname

from navigation_server.generated.agent_pb2 import NavigationSystemMsg, AgentResponse
from navigation_server.generated.services_server_pb2 import SystemProcessMsg, Server, Connection, ProcessState
from navigation_server.generated.agent_pb2_grpc import AgentServicer, add_AgentServicer_to_server
from navigation_server.router_common import (GrpcService, GenericTopServer, resolve_ref, copy_protobuf_data,
                                                MessageServerGlobals, GrpcServer)

_logger = logging.getLogger("ShipDataServer." + __name__)


def run_cmd(cmd:str):
    _logger.debug("Agent run_cmd: %s" % cmd)
    args = shlex.split(cmd)
    try:
        r = subprocess.run(args, capture_output=True, encoding='utf-8')
    except Exception as e:
        _logger.error('SendCmd %s error %s' % (args[0], e))
        return -1, str(e)
    if r.returncode != 0:
        _logger.error("Agent error for command:%s" % args[0])
        return r.returncode, 'Process return code %s' % r.returncode
    lines = r.stdout.split('\n')
    return 0, lines


def run_systemd(cmd: str, service: str):
    if cmd not in ('start', 'stop', 'restart', 'status'):
        raise ValueError
    args = ['systemctl', cmd, service]
    try:
        r = subprocess.run(args, capture_output=True, encoding='utf-8')
    except Exception as e:
        _logger.error("systemctl execution error: %s" % e)
        return -1
    _logger.debug("systemctl return code:%d" % r.returncode)
    lines = r.stdout.split('\n')
    # _logger.debug("stdout=%s" % lines)
    return r.returncode, lines


class AgentExecutor(threading.Thread):

    def __init__(self, cmd: str):
        self._cmd = cmd
        super().__init__()

    def run(self):
        time.sleep(3.0)
        run_cmd(self._cmd)


class SystemdProcess:

    (NOT_STARTED, RUNNING, STOPPED) = range(0,3)

    def __init__(self, opts):
        self._name = opts.get('name', str, 'incognito')
        self._service = opts.get('service', str, self._name)
        self._follow = opts.get('follow', str, None)
        self._post = opts.get_choice('post', ['wait', 'delay', 'none'], 'none')
        self._autostart = opts.get('autostart', bool, True)
        self._controlled = opts.get('controlled', bool, True)
        self._state = self.NOT_STARTED
        self._process_msg = None
        self._start_event = threading.Event()
        self._pid = 0
        self._control_group = None

    def __getattr__(self, attr_name):
        if self._process_msg is None:
            _logger.error(f"SystemdProcess {self._name} no process msg present (bug) attr:{attr_name}")
            raise AttributeError
        try:
            return self._process_msg.__getattribute__(attr_name)
        except AttributeError:
            _logger.error(f"SystemdProcess missing {attr_name} attribute")
            raise

    def start(self):
        _logger.info(f"Agent starting systemd service {self._service}")
        if self.status() == 4:
            # non existent service
            return
        if self._state == self.RUNNING:
            _logger.error(f"Agent Service {self._service} already running")
            if not self._controlled:
                return
            if self._process_msg is None:
                # let's force registration
                run_cmd(f"kill -{signal.SIGUSR1} {self._pid}")
            return
        self._start_event.clear()
        code, lines = run_systemd('start', self._service)
        if code == 0:
            self._state = self.RUNNING
            if not self._controlled:
                return code
            elif not self._start_event.wait(20.0):
                _logger.error(f"Agent - systemd process {self._service} did not start within 20s")
                return -1
            else:
                _logger.info(f"Agent - service {self._service} successfully started")
                return code
        return code

    def status(self):
        _logger.debug("Query status for service %s" % self._service)
        code, lines = run_systemd('status', self._service)
        loaded = False
        active = False
        state = 'unknown'
        if code == 4:
            _logger.error(f"Agent service {self._service} is unknown")
        elif code == 0 or code == 3:
            in_cg = False
            for line in lines:
                if idx := line.find('Loaded') >= 0:
                    loaded = True
                elif (idx := line.find('Active')) >= 0:
                    print("idx=",idx)
                    idx += 8
                    first_space = line.find(' ', idx)
                    state = line[idx: first_space]
                    if state == 'active':
                        self._state = self.RUNNING
                    elif state == 'inactive':
                        self._state = self.NOT_STARTED
                        break
                elif (idx :=line.find('CGroup')) >= 0:
                    # start Control group
                    in_cg = True
                    idx += 8
                    self._control_group = line[idx:]
                elif in_cg:
                    idx = line.find('─')
                    if idx < 0 :
                        continue
                    idx += 1
                    idx2 = line.find(' ', idx)
                    strpid = line[idx:idx2]
                    if line.find('python3', idx2) > idx2:
                        # ok we found it
                        in_cg = False
                        self._pid = int(strpid)
                        break
            _logger.debug("Status for %s loaded %s state %s" % (self._service, loaded, state))
        return code

    def start_confirmation(self, process_msg: SystemProcessMsg):
        self._process_msg = process_msg
        self.debug_msg_attributes(['name', 'state', 'grpc_port', 'version', 'start_time', 'console_present'])
        self._state = self.RUNNING
        if not self._start_event.is_set():
            self._start_event.set()

    def start_in_progress(self) -> bool:
        return not self._start_event.is_set()

    def debug_msg_attributes(self, attr_set):
        for attr in attr_set:
            try:
                _logger.debug(f"{attr}={self._process_msg.__getattribute__(attr)}")
            except AttributeError:
                _logger.debug(f"{attr} non existent")

    def send_sigint(self):
        run_cmd(f"kill -{signal.SIGINT} {self._pid}")

    def restart(self):
        # proceed to hard restart
        if self._state == self.RUNNING:
            _logger.info(f"Restarting process '{self.name}' service:{self._service}")
            run_systemd('restart', self._service)
            return self.status()
        else:
            _logger.error(f"Agent cannot restart a process ({self.name}) that is not running")
            return 3

    def stop(self):
        # proceed to hard stop
        if self._state == self.RUNNING:
            _logger.info(f"Stopping process '{self.name}' service:{self._service}")
            self._state = self.STOPPED
            self._pid = 0
            run_systemd('stop', self._service)
        else:
            _logger.error(f"Agent cannot stop a process ({self.name}) that is not running")

    @property
    def name(self) -> str:
        return self._name

    @property
    def local_state(self):
        return self._state

    @property
    def autostart(self):
        return self._autostart

    @property
    def service(self):
        return self._service

    @property
    def is_controlled(self) -> bool:
        return self._controlled

    @property
    def is_running(self) -> bool:
        return self._state == self.RUNNING and self._process_msg is not None



class AgentServicerImpl(AgentServicer):

    def __init__(self, agent):
        self._agent = agent
        self._response_id = 1
        self._vector = {
            'status' : self.status ,
            'start' : self.start,
            'stop' : self.stop,
            'restart' : self.restart,
            'get_port' : self.get_port,
            'interrupt': self.interrupt
        }

        self._system_vector = {
            'status' : self.system_status,
            'halt' : self.system_halt,
            'reboot' : self.system_reboot,
            'navigation_restart': self.navigation_restart
        }

    def RegisterProcess(self, request: SystemProcessMsg, context):
        _logger.info("AgentService RegisterProcess received for %s" % request.name)
        resp = AgentResponse()
        resp.id = self._response_id
        self._response_id += 1
        try:
            process = self._agent.get_process(request.name)
            if not process.start_in_progress():
                _logger.info(f"Agent spontaneous registration for {request.name}")
            process.start_confirmation(request)
            resp.response = f"process {request.name} started with service {process.service}"
        except KeyError:
            _logger.error(f"Agent Register for unknown process {request.name}")
            resp.response = f"registration error for process {request.name} unknown from Agent"
        return resp

    def AgentCmd(self, request, context):
        cmd = request.cmd
        _logger.info("Agent command %s on %s" % (cmd, request.target))
        resp = AgentResponse()
        resp.id = request.id
        if cmd not in self._vector:
            resp.err_code = 10
            resp.response = f"Unknown command:{cmd}"
            return resp
        try:
            process = self._agent.get_process(request.target)
        except KeyError:
            resp.err_code = 4
            resp.response = f"Unknown process {resp.target}"
            return resp
        self._vector[cmd](process, resp)
        return resp

    def AgentSystemCmd(self, request, context):
        cmd = request.cmd
        _logger.info("Agent system command: %s" % cmd)
        resp = AgentResponse()
        resp.id = request.id
        if cmd not in self._system_vector:
            resp.err_code = 10
            resp.response = f"Unknown command:{cmd}"
            return resp
        self._system_vector[cmd](resp)
        return resp

    def fill_process_response(self, process, resp):
        if process.is_controlled:
            copy_protobuf_data(process, resp, ['grpc_port', 'version', 'start_time', 'console_present'])
        resp.state = ProcessState.RUNNING
        resp.name = process.name
        _logger.debug(f"Process {process.name} console {resp.console_present}")

    def status(self, process:SystemdProcess, resp):
        code = process.status()
        if code == 0:
            # process is running
            resp.err_code = 0
            resp.response = f"process {process.name} is running"
            # process.debug_msg_attributes(['name', 'grpc_port', 'version', 'start_time', 'console_present'])
            self.fill_process_response(process, resp.process)
        elif code == 3:
            # process is not running
            resp.err_code = 0
            resp.response = f"process {process.name} is inactive"
            resp.process.name = process.name
            resp.process.state = ProcessState.STOPPED
        else:
            resp.err_code = 4
            resp.response = f"process {process.name} is unknown state"

    def start(self, process:SystemdProcess, resp):
        code = process.start()
        if code == 0:
            resp.err_code = 0
            resp.response = f"process {process.name} is started"
            self.fill_process_response(process, resp.process)
        else:
            resp.err_code = code
            resp.response = f"Error starting {process.name}"
            resp.process.state = ProcessState.NOT_STARTED

    def stop(self, process:SystemdProcess, resp):
        process.stop()
        resp.err_code = 0
        resp.process.state = ProcessState.STOPPED
        resp.process.name = process.name

    def restart(self, process:SystemdProcess, resp):
        code = process.restart()
        if code == 0:
            resp.err_code = 0
            resp.response = f"{process.name} started"
            self.fill_process_response(process, resp.process)
        else:
            resp.err_code = code
            resp.response = f"Error starting {process.name}"

    def get_port(self,process:SystemdProcess, resp):
        if process.state == SystemdProcess.RUNNING:
            resp.err_code = 0
            resp.response = process.name
            resp.grpc_port = process.grpc_port
        else:
            resp.err_code = 3
            resp.response = f"{process.name} is inactive"

    def interrupt(self, process: SystemdProcess, resp):
        # send an interrupt signal to the process
        process.send_sigint()
        resp.err_code = 0
        resp.response = f"process {process.name} stopped with SIGINT"
        resp.process.name = process.name
        resp.process.state = ProcessState.STOPPED



    def system_status(self, resp):
        _logger.debug("Agent system status")
        resp.system.name = MessageServerGlobals.server_name
        resp.system.version = MessageServerGlobals.version
        resp.system.start_time = MessageServerGlobals.main_server.start_time_str()
        # some information are independent of the main server
        resp.system.hostname = gethostname()
        resp.system.settings = MessageServerGlobals.configuration.settings_file
        for process in self._agent.get_processes():
            # _logger.debug("Agent system status adding %s" % process.name)
            process_pb = SystemProcessMsg()
            if process.is_controlled and process.is_running:
                self.fill_process_response(process, process_pb)
            else:
                process_pb.name = process.name
                if process.local_state == SystemdProcess.RUNNING:
                    process_pb.state = ProcessState.RUNNING
                else:
                    process_pb.state = ProcessState.NOT_STARTED
            resp.system.processes.append(process_pb)
        return resp

    def system_halt(self, resp):
        ex = AgentExecutor('halt')
        ex.start()
        resp.err_code = 0

    def system_reboot(self, resp):
        ex = AgentExecutor('reboot')
        ex.start()
        resp.err_code = 0

    def navigation_restart(self, resp):
        pass


class AgentService(GrpcService):
    """

    """
    def __init__(self, opts):
        super().__init__(opts)
        self._processes = {}

    def finalize(self):
        super().finalize()
        add_AgentServicer_to_server(AgentServicerImpl(self), self.grpc_server)

    def add_process(self, process):
        self._processes[process.name] = process

    def get_process(self, name):
        return self._processes[name]

    def start_processes(self):
        processes = list(self._processes.values())
        for process in processes:
            code = process.status()
            if code == 4:
                # unknown service
                _logger.info(f"Agent deleting process {process.name} => no service associated")
                del self._processes[process.name]
                continue
            if process.autostart:
                process.start()

    def get_processes(self):
        return self._processes.values()


class AgentTopServer(GenericTopServer):

    def __init__(self, opts):
        super().__init__(opts)
        self._agent = None

    def is_agent(self):
        return True

    def pre_build(self):
        self._agent = resolve_ref('Agent')
        assert self._agent is not None

    def add_process(self, process):
        self._agent.add_process(process)

    def start(self):
        if super().start():
            self._agent.start_processes()
            return True
        else:
            return False



