#-------------------------------------------------------------------------------
# Name:        client_common
# Purpose:     super class with all client common functions
#
# Author:      Laurent Carré
#
# Created:     05/03/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import grpc
import logging
import queue
import threading

from navigation_server.router_common import GrpcAccessException, NavThread
from navigation_server.generated.grpc_control_pb2 import GrpcCommand, GrpcAck
from navigation_server.generated.grpc_control_pb2_grpc import NavigationGrpcControlStub

class GrpcStreamTimeout(Exception):
    pass

_logger = logging.getLogger("ShipDataServer." + __name__)

class GrpcClient:
    """
    The GrpcClient class facilitates interaction with a gRPC server.

    This class provides methods for establishing connections to a gRPC server,
    managing service stubs, and making server calls for both single and multiple
    responses. It also handles server communication errors and maintains the
    current connection state.

    Attributes:
        NOT_CONNECTED: Represents the initial or disconnected state of the client.
        CONNECTING: Represents the state when a connection attempt is in progress.
        CONNECTED: Represents the state when the client is successfully connected.
    """
    (NOT_CONNECTED, CONNECTING, CONNECTED) = range(10, 13)

    clients = {}  # records all clients to avoid duplicate

    @classmethod
    def get_client(cls, server, use_request_id:bool = True):
        try:
            return cls.clients[server]
        except KeyError:
            pass
        client = GrpcClient(server, use_request_id)
        cls.clients[server] = client
        return client


    def __init__(self, server: str, use_request_id:bool = True):
        """
        Represents a client connection handler for a server.
        The __init__ method shall not be called directly use GrpcClient.get_client instead

        Parameters:
            server: this is a string in the form Address(or URL):port

        This class is responsible for managing the connection and communication
        with a server. It initializes essential attributes required to maintain
        the state of the connection, the server reference, and tracks any
        registered services or channels involved in the communication.

        Attributes:
            _server: The reference to the server with which the connection is
                established.
            _channel: Represents the communication channel for this client.
                Initially set to None.
            _services: A list that keeps track of the registered services
                associated with this client.
            _state: Indicates the current connection state of the client. This
                starts as NOT_CONNECTED.
            _req_id: A numerical identifier for tracking requests made by the
                client.
        """
        self._server: str = server
        self._channel = None
        self._services = []
        self._state = self.NOT_CONNECTED
        self._req_id = 0
        self._use_req_id = use_request_id
        self._ready = False
        self._wait_connect = threading.Event()
        self._control_stub = None

    def connect(self):
        """
        Connects to the gRPC server and initializes the stubs for the provided services.

        This method creates an insecure channel to the specified server and iterates
        through each service to initialize its gRPC stub. After successfully setting
        up the stubs, the connection state is updated to CONNECTING, and a log entry
        is created to indicate the connection status.

        """
        if self._state == self.CONNECTED:
            _logger.error(f"GrpcClient attempt to connect to {self._server} while already connected")
            return
        elif self._state == self.CONNECTING:
            _logger.error(f"GrpcClient attempt to connect to {self._server} while connecting")
            return
        _logger.info(f"GrpcClient connect attempt to {self._server}")
        self._wait_connect.clear()
        self._channel = grpc.insecure_channel(self._server)
        self._channel.subscribe(self.channel_callback)
        # create the control stub
        self._control_stub = NavigationGrpcControlStub(self._channel)
        for service in self._services:
            service.create_stub(self._channel)
        self._state = self.CONNECTING
        _logger.info(f"Server stub created on {self._server} => connecting")
        # now attempt a first connection
        request = GrpcCommand()
        request.id = self._req_id
        request.command = "TEST"
        try:
            resp = self.server_call(self._control_stub.SendCommand, request, None)
        except GrpcAccessException:
            _logger.info(f"GrpcClient connect attempt to {self._server} failed")
        else:
            _logger.info(f"GrpcClient connect attempt to {self._server} result={resp.response}")

    def wait_connect(self, timeout:float):
        """
        Wait until the connection to the server is established

        Parameters:
            timeout: float  connection timeout in seconds

        Returns True if the connection is established or False if the timeout is exhausted

        """
        return self._wait_connect.wait(timeout=timeout)

    def add_service(self, service):
        """
        Adds a service to the current server instance and initializes it based on the server's state.

        Parameters
        ----------
        service : Service
            The service instance to be added to the server.

        Raises
        ------
        None

        """
        self._services.append(service)
        service.attach_server(self)
        if self._state in (self.CONNECTING, self.CONNECTED):
            service.create_stub(self._channel)

    @property
    def state(self):
        return self._state

    @property
    def address(self):
        return self._server

    @property
    def connected(self) -> bool:
        return self._state == self.CONNECTED

    @property
    def not_connected(self) -> bool:
        return self._state == self.NOT_CONNECTED

    def server_call(self, rpc_func, req, response_class):
        """
        Performs a server call through gRPC client.

        This method invokes a remote procedure call on a gRPC server. The request
        ID is incremented for each call and assigned to the request object. The
        response is either processed by a response class, if provided, or returned
        as-is. Handles gRPC errors and updates the client state accordingly when
        connection is unavailable.

        Args:
            rpc_func: Callable
                The gRPC function representing the remote procedure call to be
                executed.
            req: Any
                The request object to be sent to the server. It must have an `id`
                attribute that gets updated to the current request identifier.
            response_class: Optional[Callable]
                A class or callable used to process and return the raw response,
                if provided. If not supplied, the raw response from the gRPC
                server is returned.

        Returns:
            Any: Processed response from the server or the raw response, depending
            on whether `response_class` is provided.

        Raises:
            GrpcAccessException:
                Raised if there is an error accessing the server or if a non-
                recoverable gRPC error occurs.
        """
        _logger.debug("gRPC Client server %s call" % self._server)
        self._req_id += 1
        if self._use_req_id:
            req.id = self._req_id
        try:
            response = rpc_func(req)
            if response_class is not None:
                return response_class(response)
            else:
                return response
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.info(f"Server error:{err.details()}")
                # self._state = self.NOT_CONNECTED
            else:
                _logger.error(f"Error accessing server:{err.details()}")
                self._state = self.NOT_CONNECTED
            raise GrpcAccessException

    def server_call_multiple(self, rpc_func, req, response_class):
        """
        Provides functionality for making server calls to a gRPC service that respond with
        multiple responses. This function handles request IDs, logs server interactions,
        and manages errors including disconnections.

        Args:
            rpc_func: Callable
                The gRPC function being invoked for making the server call.
            req: Any
                The request object to send during the gRPC call.
            response_class: Optional[Callable]
                A class or callable to transform the responses from the server. If None,
                no transformation is applied.

        Yields:
            Any
                The responses from the server, either raw or transformed by the
                response_class provided.

        Raises:
            GrpcAccessException:
                If an error occurs during the gRPC call, especially when the server is
                unreachable or another server-specific error arises.
        """
        _logger.debug("gRPC Client server call with multiple responses")
        self._req_id += 1
        if self._use_req_id:
            req.id = self._req_id
        try:
            for response in rpc_func(req):
                if response_class is not None:
                    yield response_class(response)
                else:
                    yield response
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.info(f"Server error:{err.details()}")
                # self._state = self.NOT_CONNECTED
            else:
                _logger.error(f"Error accessing server:{err.details()}")
                self._state = self.NOT_CONNECTED
            raise GrpcAccessException

    def channel_callback(self, connectivity: grpc.ChannelConnectivity):
        if connectivity == grpc.ChannelConnectivity.READY:
            _logger.info(f"GRPC Channel {self._server} Ready")
            self._ready = True
            self._state = self.CONNECTED
            if not self._wait_connect.is_set():
                self._wait_connect.set()
        elif connectivity == grpc.ChannelConnectivity.IDLE:
            _logger.info(f"GRPC Channel {self._server} IDLE")
            self._ready = False
            self._state = self.NOT_CONNECTED
        elif connectivity == grpc.ChannelConnectivity.CONNECTING:
            _logger.info(f"GRPC Channel {self._server} Connecting")
        elif connectivity == grpc.ChannelConnectivity.SHUTDOWN:
            _logger.info(f"GRPC Channel {self._server} Shutdown")
            self._state = self.NOT_CONNECTED


class GrpcStreamingReader(NavThread):
    """
    Manages a gRPC streaming communication in a separate thread.

    The GrpcStreamingReader class is designed to handle gRPC streaming communication.
    It extends the NavThread class to run as a separate daemon thread. This class
    connects to a specified gRPC server, invokes the provided RPC method, and processes
    incoming messages either by passing them to a callback function or by pushing them
    to an output queue. It also incorporates error handling and facilitates orderly
    thread termination.

    Attributes:
        _request (any): The gRPC request object to send to the server.
        _rpc_func (Callable): The gRPC remote procedure call function to invoke.
        _process_msg_callback (Callable): The callback function used to process received
            messages when no output queue is provided.
        _process_func (Callable): Determines how to process incoming gRPC messages
            (either push to queue or invoke callback).
        _out_queue (queue.Queue): A shared queue to store received messages when provided.
        _stop_flag (bool): A flag indicating whether the thread should stop.
        _grpc_server (any): The gRPC server instance to communicate with.
        _error_callback (Callable): A callback function to handle errors.

    Methods:
        send_callback(msg):
            Executes the user-defined callback function for processing a received message.

        push_to_queue(msg):
            Pushes a received message into the shared queue.

        nrun():
            Executes the main logic of the thread, which reads from the gRPC stream.
            Handles messages and errors in the streaming process.

        stop():
            Signals the thread to stop execution during its next processing loop.
    """
    def __init__(self, client, grpc_server, rpc_func, request, out_queue:queue.Queue, process_msg_callback, error_callback):
        """
        Represents a thread for handling gRPC requests, processing messages, and managing output queues
        or callbacks.

        Attributes:
            _request: Request object containing client information.
            _rpc_func: Callable function for handling RPC requests.
            _out_queue (queue.Queue): Queue for managing outgoing messages if provided.
            _process_msg_callback: Callable function for processing messages in callback mode.
            _process_func: Function used for either pushing messages to the queue or sending via callback.
            _stop_flag: Boolean flag to indicate if the thread should stop its operations.
            _grpc_server: Reference to the gRPC server instance.
            _error_callback: Callable function for handling errors.
        """
        super().__init__(name=client, daemon=True)
        self._request = request
        self._client = client
        self._rpc_func = rpc_func
        if out_queue is None:
            self._process_msg_callback = process_msg_callback
            self._process_func = self.send_callback
        else:
            self._out_queue: queue.Queue = out_queue
            self._process_func = self.push_to_queue
        self._stop_flag = False
        self._grpc_server = grpc_server
        self._error_callback = error_callback

    def send_callback(self, msg):
        self._process_msg_callback(msg)

    def push_to_queue(self, msg):
        self._out_queue.put(msg, block=True)

    def nrun(self):
        _logger.debug("Starting gRPC stream reading thread")
        try:
            for msg in self._rpc_func(self._request):
                if self._stop_flag:
                    break
                self._process_func(msg)
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.info(f"Server error:{err.details()}")
                # self._state = self.NOT_CONNECTED
            else:
                _logger.error(f"GrpcStreamReader => Error accessing server:{err.details()}")
        self._error_callback()
        _logger.info(f"gRPC read stream {self.name} stops")

    def stop(self):
        self._stop_flag = True


class ServiceClient:
    """
    ServiceClient abstracts and manages gRPC client-server communications.

    This class provides an interface to interact with gRPC services, allowing
    the attachment of a gRPC server object, creation of stubs, and handling
    RPC calls either for single or multiple responses. The ServiceClient class
    is designed as a utility to encapsulate common gRPC client interactions,
    offering streamlined functionality for communicating with servers.

    Attributes:
        _stub_class: The gRPC stub class associated with the service.
        _stub: Represents the gRPC stub instance created using the stub class.
               It is None by default until initialized.
        _server (GrpcClient): The server object to which the client is attached.
               Used for executing various RPC calls.
    """
    def __init__(self, stub_class):
        self._stub_class = stub_class
        self._stub = None
        self._server: GrpcClient = None
        self._read_queue = None
        self._stream_reader = None

    def attach_server(self, server:GrpcClient):
        """
        Attaches a gRPC client server to the current instance to establish a server
        connection.

        Args:
            server (GrpcClient): The gRPC client instance to be attached.
        """
        self._server = server

    def create_stub(self, channel):
        self._stub = self._stub_class(channel)

    def _server_call(self, rpc_func, request, response_class):
        """
        Call a server function via the RPC mechanism. The method handles server-side
        logic, forwarding the call to the attached server. If no server is attached,
        an error is logged, and an exception is raised.

        Args:
            rpc_func: The RPC function to be called. Expected to be a callable representing
                the server-side procedure.
            request: The request object constructed for the RPC call. Contains all the
                necessary data to process the request.
            response_class: The class of the response object that the RPC call will return.

        Raises:
            GrpcAccessException: Raised when an attempt is made to call a service
                without an attached server.
        """
        if self._server is not None:
            return self._server.server_call(rpc_func, request, response_class)
        else:
            _logger.error("Attempt to call a service not attached to a server")
            raise GrpcAccessException

    def _server_call_multiple(self, rpc_func, request, response_class):
        """
        Yields responses from a server call for a given gRPC function, request, and response class.

        If the server attribute is available, this method delegates to the server's
        `server_call_multiple` method to yield responses. If the server is not attached,
        it logs an error and raises a GrpcAccessException.

        Parameters:
            rpc_func
                The RPC function to be called.
            request
                The request object to be sent to the server.
            response_class
                The class representing the type of response expected from the server.

        Yields:
            Response objects of type `response_class` returned by the `rpc_func` execution
            on the server.

        Raises:
            GrpcAccessException
                Indicates an attempt was made to call a service without a server being attached.
        """
        if self._server is not None:
            for response in self._server.server_call_multiple(rpc_func, request, response_class):
                yield response
        else:
            _logger.error("attempt to call a service not attached to a server")
            raise GrpcAccessException

    def _start_read_stream_to_queue(self, client:str, rpc_func, request):
        """
        Starts a gRPC streaming reader and initializes the read queue.

        This method attempts to start a gRPC streaming reader to process
        incoming streams using the provided remote procedure call (RPC)
        function and request. If the streaming reader is already running,
        an error is logged, and the method exits without making changes.

        Parameters:
        client: str
            a key to distinguish the stream reader from other streams
        rpc_func: Callable
            The gRPC remote procedure call function to invoke for the
            stream.
        request: Any
            The request object passed to the gRPC call.

        Raises:
        queue.Full
            If the internal read queue exceeds its maximum size while
            processing messages.
        """
        _logger.debug("GrpcClient => Creating Starting gRPC stream reader with a queue")
        if self.stream_is_alive():
            _logger.error("Grpc Stream reader: attempt to start the stream reader while it is already running")
            return
        self._read_queue = queue.Queue(20)
        self._stream_reader = GrpcStreamingReader(client, self._server, rpc_func, request, self._read_queue, None, self._stream_error)
        self._stream_reader.start()

    def _start_read_stream_to_callback(self, client:str, rpc_func, request, process_msg_callback):
        """
        Starts and manages a gRPC streaming reader which handles incoming stream data
        using a provided callback function. Ensures that only one streaming reader is
        active at a time.

        Args:
            rpc_func: Callable
                The gRPC function used to initialize the stream.
            request: object
                The request object to send when starting the gRPC stream.
            process_msg_callback: Callable
                A callback function to handle messages received from the stream.

        Returns:
            None
        """
        _logger.debug("GrpcClient => Creating Starting gRPC stream reader with a callback")
        if self.stream_is_alive():
            _logger.error("Grpc Stream reader: attempt to start the stream reader while it is already running")
            return
        self._stream_reader = GrpcStreamingReader(client, self._server, rpc_func, request, None, process_msg_callback, self._stream_error)
        self._stream_reader.start()

    def _read_stream(self):
        """
        Reads data from a gRPC stream queue. This method checks the state of the
        stream reader, attempts to retrieve data from the queue, and raises
        appropriate exceptions in case of errors or timeouts.

        Raises:
            GrpcAccessException: If the stream reader is not initialized or
                has terminated unexpectedly.
            GrpcStreamTimeout: If the queue times out while waiting for a
                stream message and the stream reader is still alive.
        """
        if self._stream_reader is None:
            _logger.error("GrpcStreamReader not started")
            raise GrpcAccessException("StreamReader not started")
        if self._read_queue is None:
            _logger.error("GrpcStreamReader not in queue mode")
            raise GrpcAccessException("GrpcStreamReader not in queue mode")
        try:
            msg = self._read_queue.get(block=True, timeout=1.0)
            _logger.debug("GrpcStreamReader got msg PGN %d" % msg.pgn)
            return msg
        except queue.Empty:
            if self._stream_reader is None:
                # ok the steam is over
                raise GrpcAccessException("Grpc StreamReader terminated")
            elif self._stream_reader.is_alive():
                _logger.debug("Grpc Stream time out")
                raise GrpcStreamTimeout(f"GrpcStreamReader time out on:{self.server.address}")
            else:
                _logger.debug("StreamReader gRPC error suspected")
                raise GrpcAccessException(f"GrpcError during stream read on:{self.server.address}")

    def _stop_read_stream(self):
        if self._stream_reader is not None:
            self._stream_reader.stop()
            self._stream_reader = None

    def stream_is_alive(self) -> bool:
        if self._stream_reader is not None and self._stream_reader.is_alive():
            _logger.debug("gRPC Stream is alive")
            return True
        else:
            return False

    def _stream_error(self):
        # the stream is signalling that it is stopping
        self._stream_reader = None # so we forget it

    def server_state(self):
        return self._server.state

    def _wait_for_stream_end(self):
        if self._stream_reader is not None:
            self._stream_reader.join()
            self._stream_reader = None

    @property
    def server_connected(self) -> bool:
        return self._server.connected

    @property
    def server_not_connected(self) -> bool:
        return self._server.not_connected

    def server_connect(self):
        self._server.connect()


    def server_connect_wait(self, timeout: float) -> bool:
        self._server.connect()
        return self._server.wait_connect(timeout)

    @property
    def server(self) -> GrpcClient:
        return self._server


class GrpcStreamIteratorError(Exception):
    pass


class GrpcSendStreamIterator:
    """
    An iterator for sending gRPC stream data.

    This class serves as a wrapper to facilitate sending data in a gRPC stream
    by utilizing a custom function to fetch the next data item. It implements
    the iterator protocol, making it suitable for use in loops or any context
    that requires iteration.

    Attributes:
        _get_next_function: Callable without parameters that returns the next
            object from the stream.
        _service: The gRPC service associated with this stream.
    """
    def __init__(self, service, get_next_function):
        self._get_next_function = get_next_function
        self._service = service

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return self._get_next_function()
        except GrpcStreamIteratorError:
            raise StopIteration


