<!-- TOC -->
  * [Description](#description)
    * [Servers](#servers)
      * [NavigationMainServer class](#navigationmainserver-class)
      * [GenericTopServer class](#generictopserver-class)
      * [NMEAServer class](#nmeaserver-class)
      * [NMEASenderServer class](#nmeasenderserver-class)
      * [GrpcServer class](#grpcserver-class)
      * [ShipModulConfig server](#shipmodulconfig-server)
      * [NMEA2KController server](#nmea2kcontroller-server)
      * [NMEA2KActiveController server](#nmea2kactivecontroller-server)
    * [Couplers](#couplers)
      * [Coupler generic parameters](#coupler-generic-parameters)
      * [NMEASerialPort(Coupler)](#nmeaserialportcoupler)
      * [IPCoupler(Coupler)](#ipcouplercoupler)
      * [NMEATCPReader (IPCoupler)](#nmeatcpreader-ipcoupler)
      * [ShipmodulInterface (IPCoupler)](#shipmodulinterface-ipcoupler)
      * [YDCoupler (IPCoupler)](#ydcoupler-ipcoupler)
      * [iKonvert(Coupler)](#ikonvertcoupler)
      * [InternalGps (Coupler)](#internalgps-coupler)
      * [VEDirectCoupler(Coupler)](#vedirectcouplercoupler)
      * [DirectCANCoupler(Coupler)](#directcancouplercoupler)
      * [GrpcNmeaCoupler(Coupler)](#grpcnmeacouplercoupler)
    * [Services](#services)
      * [Console service](#console-service)
      * [AgentService](#agentservice)
      * [DataDispatchService](#datadispatchservice)
      * [Energy management service](#energy-management-service)
        * [MPPTService](#mpptservice)
    * [Publishers](#publishers)
      * [Generic Publisher (Abstract class)](#generic-publisher-abstract-class)
      * [GrpcPublisher](#grpcpublisher)
      * [N2KJsonPublisher](#n2kjsonpublisher)
      * [N2KTracePublisher](#n2ktracepublisher)
      * [PrintPublisher](#printpublisher)
      * [Injector (Publisher)](#injector-publisher)
    * [N2KSourceDispatcher (Publisher)](#n2ksourcedispatcher-publisher)
    * [Applications](#applications)
      * [NMEA2000Application](#nmea2000application)
      * [GrpcInputApplication(GrpcDataService, NMEA2000Application)](#grpcinputapplicationgrpcdataservice-nmea2000application)
    * [Filters](#filters)
    * [Filter classes](#filter-classes)
      * [NMEAFilter](#nmeafilter)
      * [NMEA0183filter (NMEAFilter)](#nmea0183filter-nmeafilter)
      * [NMEA2000Filter (NMEAFilter)](#nmea2000filter-nmeafilter)
      * [NMEA2000TimeFilter (NMEA2000Filter)](#nmea2000timefilter-nmea2000filter)
  * [Tracing and replay](#tracing-and-replay)
    * [RawLogCoupler (Coupler)](#rawlogcoupler-coupler)
    * [TransparentCanLogCoupler (RawLogCoupler)](#transparentcanlogcoupler-rawlogcoupler)
    * [DeviceReplaySimulator (NMEA2000Application)](#devicereplaysimulator-nmea2000application)
  * [Organizing the processes](#organizing-the-processes)
  * [Configuration files](#configuration-files)
    * [Messages server configuration file](#messages-server-configuration-file)
      * [Features concept and Python modules](#features-concept-and-python-modules)
      * [Exemple configuration files](#exemple-configuration-files)
      * [Profiling](#profiling)
    * [Default port assignments for servers / services](#default-port-assignments-for-servers--services)
  * [Implementation structure](#implementation-structure)
    * [Root directory](#root-directory)
    * [Launching a message server process](#launching-a-message-server-process)
<!-- TOC -->
## Description
The navigation server-router aggregate and distribute navigation and other operational data aboard recreational or small professional vessels.
It is a focal point and server for all kind of data needed to control the course and operational condition of the boat.
The system is based on the building blocks described here below. These building blocks can be configured in several processes and each 
The configuration and parameters of the system are described in a Yaml file. See the corresponding section.
All building blocks are optional, but if there is no Coupler or Publisher nothing will happen.

**IMPORTANT NOTE: Every *navigation_server* process can be configured to perform several kind of tasks, and you can also run several programs communicating via various mechanisms to distribute processing load across several CPU both locals or on remote systems. Hence, the system proposed must be seen as a toolbox to process and route NMEA and other messages**

Each *navigation_server* is a single Python process and messages are exchanged internally. That could lead to burst of messages and some delays du to the Python GIL, when the workload starts to be significant. To overcome that problem, the easiest solution is to split the processing between *navigation_server* processes.

Inside the *navigation_server* process the following entities can be configured and instantiated:

**Server**: servers can accept incoming connections and then are sending or receiving messages using several application and transport protocols that are described in details in the **Navigation system API** document. In the server category we also find NMEA CAN controllers or pseud-controllers that are not external servers but have a server function versus the CAN network. Some servers can also be purely internal. One server is used as a starting and shall be the "Main" server in the configuration file.

**Coupler**: couplers are the interfaces for external devices or for incoming messages for communication between processes

**Publisher**: publishers act as messages flows aggregators that they can push towards client with our without processing and transformation. Publishers are automatically created by servers when a new client is opening a new message stream. Publishers with a 

**Service**: A service implements a "service" a defined by the gRPC system that will be installed over a gRPC server

**Application**: an application corresponds to a Controller Application as defined by J1939 and reused by NMEA2000. An application results in a device on a NMEA2000 bus. Applications are relevant only when the process is directly linked to the CAN interface.

**Filters**: filters can be plugged at various point in the messages flows to select or reject certain type of messages that are useless downstream

*Note on the parameters tables: Only the parameter attached to the actual class are described in each class. To have the full parameter set that is applicable all superclasses descriptions must also be looked at.*

![server concepts](https://github.com/Sterwen-Technology/navigation_server/blob/main/doc/Nmea_message-server-concept-1.png)

### Servers
The servers are servers allowing any navigation or control application to access the flow of data via TCP/IP.
There is a generic server: NMEAServer. This server is sending all messages coming from the associated instruments to the clients.
Client can also send messages to the server that are sent to the instrument input.

There are 2 server classes with external access: NMEA0183 based protocol over TCP and binary messages over gRPC. And some other internal servers.

The NMEA0183 based protocol can be understood and messages starting with '$' or '!' including only printable ASCII characters and separated by the 'CR' and 'LF' characters
That is not exactly a real protocol over TCP/IP but this is working and the messages (data frames) and directly inherited from the standards NMEA0183 messages.
Even NMEA2000 data frames are carrier over such messages like it is done for Digital Yacht or Shipmodul miniplex.
Using efficient binary encoding with Protobuf and a real protocol like gRPC allows an increase in efficiency. THis is particularly true for NMEA2000 that is binary protocol by nature.
For more information on [gPRC](https://grpc.io/) and [Protobuf](https://developers.google.com/protocol-buffers/)

#### NavigationMainServer class

This shall be the **Main** server for a NMEA messages router function.

#### GenericTopServer class

This the generic top level **Main** server that is to be used for non routing function. For instance, it is used for the system agent process and the energy_management process.

#### NMEAServer class

This class implements a TCP server that is transmitting NMEA0183 based (real NMEA0183 or NMEA2000 over pseudo NMEA0183) messages over a raw TCP stream. No additional protocol elements are transmitted.
This server is only transmitting messages from the navigation networks (couplers) to the host. The server provides compatibility with navigation software accepting NMEA0183 messages over TCP/IP.

Here are the parameters associated with the server

| Name            | Type                      | Default     | Signification                                                             |
|-----------------|---------------------------|-------------|---------------------------------------------------------------------------|
| port            | int                       | 4500        | listening port of the server                                              |
| heartbeat       | float                     | 30          | Period of the heartbeat  timer                                            |
| timeout         | float                     | 5.0         | timeout socket receive                                                    |
| max_silent      | float                     | 120.0       | maximum time without traffic for a client. The connection is closed after |
| max_connections | int                       | 10          | maximum number of active connections                                      |
| nmea2000        | transparent, dyfmt, stfmt | transparent | Formatting of NMEA2000 messages (see below)                               |


**Format of NMEA2000 messages (using pseudo NMEA0183 protocol)**

*transparent*: messages are transmitted in the same format as the coupler sends them. This is valid only if the coupler is able to send NMEA0183 like NMEA2000 messages. That is also implying that there is no message loss between coupler and server, so the coupler(s) are configured with the nmea0183 protocol.
When configured in NMEA2000, due to fast packet reassembly, there is no transparency possible.

*dyfmt*: NMEA2000 messages are transmitted using the Digital Yacht !PGDY format

*stfmt*: NMEA2000 messages are transmitted using the Sterwen Technology !PGNST format

if dyfmt or stfmt is selected all NMEA2000 messages will be translated in the selected format including reassembly of Fast Packet. That implies that the protocol selected in the instruments is 'nmea2000'. NMEA0183 messages are transparently transmitted in any case.

The configuration is also valid for messages sent from the host (client), in that case NMEA0183 like messages encapsulating NMEA2000 messages will be treated internally as NMEA2000.

#### NMEASenderServer class
This server allows sending NMEA0183 messages from the host towards a coupler. This is mostly used to control navigation and send tracking information to autopilot and displays


| Name        | Type                      | Default     | Signification                                                                                  |
|-------------|---------------------------|-------------|------------------------------------------------------------------------------------------------|
| port        | int                       | 4503        | listening port of the server                                                                   |
| heartbeat   | float                     | 30          | Period of the heartbeat  timer                                                                 |
| timeout     | float                     | 5.0         | timeout socket receive. On some systems this value is too low                                  |
| max_silent  | float                     | 30.0        | maximum time without traffic for a client. The connection is closed after                      |
| coupler     | string                    | None        | Name of the instrument receiving the messages sent from client                                 |
| master      | string                    | None        | IP address of the client allowed to send messages towards instruments. First client by default |
| nmea2000    | transparent, dyfmt, stfmt | transparent | Formatting of NMEA2000 messages (see above)                                                    |
| buffer_size | int                       | 256         | Size of the receive buffer. Smaller size are useful for low message rate on the interface      |
| filters     | filter id list            | None        | List of the filters applicable for the server (see corresponding section)                      |

 

#### GrpcServer class

Server for NMEA information and other navigation information using the gRPC protocol. The server must be unique for a given process but several services can be attached to the server.
Each of these services corresponds to one *service* in a gRPC/Protobuf definition file (.proto).
Some services are explicitly defined in the configuration file (Console service for instance), while some others are implicitly defined by Couplers or other entities.

| Name      | Type | Default | Signification                                                 |
|-----------|------|---------|---------------------------------------------------------------|
| port      | int  | 4502    | listening port of the server                                  |
| nb_thread | int  | 5       | Number of thread in the pool to process simultaneous requests |



#### ShipModulConfig server

TCP server allowing to bypass the routing function to connect the Shipmodul Miniplex control application to a Miniplex3 device. To use this feature just configure the MPXConfig utility and assign the server IP and the port configured for it.

Warning: when the application is connected to the server all traffic is re-routed to it. So no NMEA messages are transmitted to the navigation system.

| Name    | Type   | Default | Signification                                          |
|---------|--------|---------|--------------------------------------------------------|
| port    | int    | 4501    | listening port of the server                           |
| coupler | string | None    | Name of the Miniplex coupler in the configuration file |

#### NMEA2KController server

This is an internal server that has no direct TCP access. All accesses to this server are via the Console. This server maintains the list of devices connected on the NMEA2000 network along with the information they are sending.
It shall be associated to a coupler by defining the **nmea2000_controller** parameter to capture all relevant messages. This coupler must be configured with **nmea2000** or **nmea_mix** protocol.
This server is to be used if the access to the NMEA2000 bus is done via an adapter device (see corresponding couplers here below), meaning that the controller has no control on the bus and can only monitor activity.

| Name       | Type   | Default | Signification                                                |
|------------|--------|---------|--------------------------------------------------------------|
| queue_size | int    | 20      | input message queue size                                     |
| save_file  | string | None    | Name of the file for saving the NMEA2000 devices             |
| max_silent | float  | 60.0    | Maximum time between message for one device (see note below) |

Note: devices that are sending messages during an interval exceeding the **max_silent** parameter are considered as switched off and therefore removed from the device table.


#### NMEA2KActiveController server

This class extends the NMEA2KController feature by adding the capability to claim an address on the CAN bus and therefore send messages. Therefore, it only works when the server has a direct connection to the NMEA2000 (CAN) bus.
By adding this class, the server becomes a full NMEA2000 device and no adapter is needed.
This controller performs the role of an ECU referring to J1939 standard. It can manage several applications (CA) that have each their own address on the CAN bus.

| Name             | Type        | Default | Signification                                                            |
|------------------|-------------|---------|--------------------------------------------------------------------------|
| channel          | string      | can0    | interface device supporting the socket CAN                               |
| mac_source       | string      | eth0    | Interface with MAC address to generate the device Unique ID from         |
| manufacturer_id  | int         | 999     | This is the registration number of the manufacturer by the NMEA2000 body |
| message_interval | float       | 0.005   | minimum interval between message sending on the bus in seconds           |
| max_applications | int         | 8       | maximum number of applications supported by the controller               |
| start_address    | int         | 128     | start address for allocation. 2x max_applications addresses are reserved |
| applications     | string list | None    | List of the applications running on the controller                       |
| trace            | boolean     | false   | If true traces all CAN messages in a file (see tracing section)          |



### Couplers
Couplers classes are connecting to instrumentation bus via direct interfaces or couplers. Direct communication via serial lines is also supported.
Currently, tested couplers:
- Shipmodul Miniplex3 Ethernet (or Wi-Fi): NMEA0183 or NMEA2000 via $MXPGN pseudo NMEA0183 messages
- Digital Yacht iKonvert: NMEA2000 only (mode Raw)
- Yachting Digital Ethernet (or Wi-Fi): NMEA2000 only (the device can be used in NMEA0183 using NMEA0183 over TCP/IP)
- Direct serial link on NMEA0183: NMEA0183 and NMEA2000 using pseudo NMEA0183 messages (check speed)
- NMEA0183 over TCP/IP: NMEA0183 and NMEA2000 using pseudo NMEA0183 messages
- Energy devices via the energy management service
- Internal GPS using GPS on cellular Modems (Fully tested with Quectel modems)
- Direct CAN Access: NMEA2000 only
- GrpcCoupler: allows data flow from a server to another based on gRPC (HTTP/2)

on hold
- Actisense adapter (NGT-1-USB or NGX-1) - Actisense is not willing to open the documentation of the interface, so development is on hold.

#### Coupler generic parameters

| Name                | Type                                   | Default       | Signification                                                                                                                                            |
|---------------------|----------------------------------------|---------------|----------------------------------------------------------------------------------------------------------------------------------------------------------|
| timeout             | float                                  | 10            | Time out on coupler read in seconds                                                                                                                      |
 | report_timer        | float                                  | 30            | Reporting / tracing interval in sec.                                                                                                                     |
 | max_attempt         | integer                                | 20            | Max number of attempt to open the device                                                                                                                 |
| open_delay          | float                                  | 2             | Delay between attempt to open the device                                                                                                                 |
| talker              | string (2)                             | None          | Talker ID substitution for NMEA0183                                                                                                                      |
| protocol            | nmea0183, nmea2000, nmea_mix, non_nmea | nmea0183      | Message processing directive nmea0183 treat all messages as NMEA0183 sentence, nmea2000: translate in NMEA2000 pseudo NMEA0183 messages                  |
| direction           | read_only, write_only, bidirectional   | bidirectional | Direction of exchange with device                                                                                                                        |
| trace_messages      | boolean                                | False         | Trace all messages after internal pre-processing                                                                                                         |
| trace_raw           | boolean                                | False         | Trace all messages in device format (see tracing and replay paragraph)                                                                                   | 
| autostart           | boolean                                | True          | The coupler is started automatically when the service starts, if False it needs to be started via the Console                                            |
| nmea2000_controller | string                                 | None          | Name of the server of class NMEA2KController associated with the coupler                                                                                 |
| nmea0183_convert    | boolean                                | False         | Convert NMEA0183 to NMEA2000, if protocol is specified as *nmea2000* then non converted messages are discarded, otherwise they are forwarded as NMEA0183 |
| stop_system         | boolean                                | False         | When true stop the whole executable when the coupler stops. Useful for log_replay and tests                                                              |


Remarks on protocol behavior:

a) When nmea2000 is selected, NMEA0183 messages are anyway routed transparently when the coupler encodes NMEA2000 frames in pseudo NMEA0183 messages, only NMEA2000 messages (encoded via NMEA0183) are partially decoded in order to reformat them in one of the supported NMEA2000 format. PGN that are part of the ISO protocol are fully decoded and processed locally in the NMEA2KController instance.

b) When nmea0183 is selected, all messages are routed in NMEA0183 and no decoding of possible NMEA2000 is performed.

c) When nmea_mix is selected, the protocol PGN are decoded and processed in the corresponding NMEA2KController instance to give a view of the network. All other messages are routed internally as NMEA2000, but externally they stay in their input format. That mode is only working if a NMEA2KController has been instanced.

d) non_nmea messages are only for internal use within a server, they must be converted to NMEA0183 or NMEA2000 to be routed externally, or exchange through a specific gRPC service

**When a NMEA2KController is defined, all ISO protocol messages are processed locally and not forwarded to the message server, so they are not visible by the client**


#### NMEASerialPort(Coupler)
This class handle serial or emulated serial line with NMEA0183 based protocols.
Specific parameters

| Name     | Type    | Default    | Signification             |
|----------|---------|------------|---------------------------|
| device   | string  | no default | Name of the serial device |
| baudrate | integer | 4800       | baud rate for the device  |

#### IPCoupler(Coupler)
Generic abstract class for all IP instruments communication.
Specific parameters

| Name           | Type     | Default    | Signification                     |
|----------------|----------|------------|-----------------------------------|
| address        | string   | no default | Address (IP or hostname)          |
| port           | integer  | no default | Port of the server                |
| transport      | TCP, UDP | TCP        | Transport protocol for the server |
| buffer_size    | integer  | 256        | size in bytes of input buffer     |
| msg_queue_size | integer  | 50         | size of reading message queue     |

Buffer size is to be adjusted taking into account average message size and number of messages per seconds.
A large buffer will create some delays for messages through the system while too small buffer size will generate a lot of overhead.

#### NMEATCPReader (IPCoupler)
Instantiable class to communicate with NMEA0183 based protocol over TCP/IP. It can work in 2 modes: nmea0183 (default) or nmea2000/nmea_mixed.
This is set via the 'protocol' parameter of the base class.
In nmea0183 mode, all frames are transmitted without any transformation.
In nmea2000 (or nmea_mixed) $MXPGN from the Miniplex sentences are transformed in NMEA2000 messages. 
The format of transmission to the server shall be either 'dyfmt' or 'stfmt'. Transparent mode will not work as the messages are transformed.


#### ShipmodulInterface (IPCoupler)
Instantiable class to manage Ethernet or Wi-Fi interface for Shipmodul Miniplex3. For USB interface, the NMEASerialPort can be used.

The class instance has 2 possible behavior depending on the protocol selected.
- nmea0183: all frames are transparently transmitted as NMEA0183
- nmea2000: All $MXPGN frames are interpreted as NMEA2000 and processed as such, including Fast Packet reassembly. Further processing on NMEA2000 frames is explained in the dedicated paragraph.
- nmea_mixed: Only the NMEA2000 bus PGN are reassembled and decoded to be sent to a NMEA2000 Controller, other messages are transmitted transparently

The class is allowing the pass through of configuration messages sent by the MPXconfig utility. This is requiring that a ShipModulConfig server class is set up in the configuration. During the connection of the MPXConfig utility, all messages are directed to it, so no messages sent to clients.

#### YDCoupler (IPCoupler)
Instantiable class to manage Yacht Device Ethernet gateway (YD02EN) for the NMEA2000 port, For NMEA0183, the generic NMEA0183TCPReader can be used.

All frames are converted in internal NMEA2000 format and can then be processed further. That includes Fast Packets reassembly.

#### iKonvert(Coupler)
Instantiable class to manage the DigitalYacht iKonvert USB gateway in raw mode. If the device is in MEA0183 mode and configured by the DigitalYacht utility, then the NMEASerialPort is to be used instead.
The class does not manage the device mode itself that shall be configured via the DY utility.

The device connection and initialisation logic is directly managed by the coupler. The only action needed on the device outside the scope of this coupler is only the configuration in raw mode.

**NMEA sentence !PGDY are converted internally the NMEA2000 sentences when the coupler is set in nmea2000 mode.**

| Name   | Type   | Default | Signification                 |
|--------|--------|---------|-------------------------------|
| device | string | None    | Name of the serial USB device |

#### InternalGps (Coupler)

No additional parameters in this version. The coupler connects to the GNSS receiver via a TTY port. For that coupler class, it is assumed that the GNSS is integrated in a cellular modem. For isolated GNSS receiver the NMEASerialPort class shall be used.


#### VEDirectCoupler(Coupler)

This class manages Victron VEDirect serial interface or a VEDirect log file as simulation. As VEDirect is not NMEA, they have a specific internal format by default. If the coupler mode is set to NMEA0183, then a XDR sentence is generated with the current, voltage and power from the panel.
This coupler is intended to be used by the energy management agent, rather than the global messaging router-server, but if only some measurements are needed for display, it can be integrated like any other coupler but only in NMEA mode (protocol => nmea0183)

| Name      | Type               | Default | Signification                                          |
|-----------|--------------------|---------|--------------------------------------------------------|
| device    | string             | None    | name of the serial device with the VEDirect connection |
| interface | serial, simulation | serial  | type of input: direct serial or simulation             |
| logfile   | string             | None    | name of the file to be used for VEDirect simulation    |

#### DirectCANCoupler(Coupler)
This coupler class works when a CAN bus interface with socketcan driver is installed on the system. Obviously, only NMEA2000 messages can be processed.
The CAN bus coupler must be declared as **application** with a specific NMEA2000 controller: **NMEA2KActiveController**. This controller handles the bus access control protocol and all CAN parameters and the coupler is considered as a specific device (CA) on the CAN bus. 

#### GrpcNmeaCoupler(Coupler)

The coupler creates a gRPC service on which NMEA0183 or NMEA2000 can be pushed (see input_server.proto).
The

| Name             | Type   | Default | Signification                                                                  |
|------------------|--------|---------|--------------------------------------------------------------------------------|
| server           | string | None    | gRPC server associated. This is a mandatory parameter                          |
| decoded_nmea2000 | bool   | False   | Indicates whether the coupler accepts fully decoded protobuf NMEA2000 messages |


### Services

The services are attached to the gRPC server that is declared and running in the process. If no gRPC server is declared, then all services definition and creation will fail
All services have a dedicated gRPC interface described in **Protobuf** language. All interfaces description files are located in the src/proto directory.
All services must be associated with a gRPC server (one per process)


| Name             | Type   | Default | Signification                                                                  |
|------------------|--------|---------|--------------------------------------------------------------------------------|
| server           | string | None    | gRPC server associated. This is a mandatory parameter                          |

#### Console service

This is a gRPC service used for external monitoring and control of the navigation server process. The protobuf interface is in the **console.proto** file.


#### AgentService

The Agent service provides a limited but useful remote control of the Linux system on which some servers are running.

**Warning: use this service only in controlled environment as in its current version no access control is implemented**

#### DataDispatchService

This is a **primary** service that is dispatching NMEA messages sent over gRPC using the same interface as the GrpcNmeaCoupler.
The messages are meant to be processed by *secondary* services that subscribe to this service using NMEA2000 PGN or NMEA0183 formatter as subscribing keys.
Messages with no subscription are simply ignored.

#### Energy management service

The service provides a global control for several services linked to energy management. The interface is described in **energy.proto**.
Currently, only the **MPPTService** is available, the team is working on the implementation of new services, for batteries and chargers.

##### MPPTService

This service receive the MPPT info via a VEDirectCoupler and keeps track of data and trends from the solar panel and MPPT output.
The service can also be used to forward NMEA0183 or NMEA2000 messages via a **GrpcPublisher** towards another server.
Interface is part of **energy.proto**

Additional parameters

| Name         | Type               | Default  | Signification                                                          |
|--------------|--------------------|----------|------------------------------------------------------------------------|
| coupler      | string             | None     | VEDirectCoupler required for data input. This is a mandatory parameter |
| publisher    | string             | None     | Optional publisher used to forward energy messages (see below)         |
| protocol     | nmea0183, nmea2000 | nmea0183 | XDR sentence for NMEA0183, PGN 127507, 127751 for NMEA2000             |
| trend_depth  | int                | 30       | number of values in the trend table                                    |
| trend_period | float              | 10       | period of the trend bucket in seconds (min 1 sec)                      |


### Publishers
Publishers concentrate messages from several instruments towards consumers. Publishers are implicitly created by Servers when a new client connection is created.
Publishers have their own thread and all messages are sent through their input queue.
There are also specific Publishers for tracing and logging and interprocess communication.

#### Generic Publisher (Abstract class)

Parameters

| Name          | Type            | Default | Signification                                                       |
|---------------|-----------------|---------|---------------------------------------------------------------------|
| queue_size    | int             | 20      | Size of the input queue (nb of messages)                            |
| max_lost      | int             | 5       | Number of messages allowed to be lost before stopping the Publisher |
| couplers      | list of strings | None    | List of couplers associated with this publisher                     |
| active        | bool            | true    | specify whether the publisher is active upon system start           |
| filters       | list of strings | None    | List of filters that are to applied before sending messages         |
| filter_select | bool            | false   | Specify the behavior of filtering (see below)                       |

The parameter **filter_select** indicates the behavior of the publisher on filtering.
    - **filter_select** is false, then all messages not matching the filter are published. Messages that match the filter are published if their **type** is 'select'
    - **filter_select** is true, then only the messages matching the filter are published when their **type** is 'select'

#### GrpcPublisher

This publisher sends NMEA messages (all formats) towards another gRPC Coupler or InputService using the gRPC service defined in input_service.proto.

| Name              | Type                                    | Default   | Signification                                              |
|-------------------|-----------------------------------------|-----------|------------------------------------------------------------|
| address           | string                                  | 127.0.0.1 | IP address of the gRPC target server                       |
| port              | int                                     | 4502      | Port number of the target gRPC server                      |
| decode_nmea2000   | bool                                    | false     | when true all NMEA2000 are fully decoded before being sent |
| trace_missing_pgn | bool                                    | false     | When true all messages with PGN not decoded are logged     |
| nmea0183          | convert_strict, convert_pass, pass_thru | pass_thru | specify processing for NMEA0183 messages (see below)       |
| retry_interval    | float                                   | 10.0      | Interval between connection retries to the gRPC server     |
| max_retry         | int                                     | 20        | Maximum number of retries, if 0, retries indefinitely      |
| filter_select     | bool                                    | true      | Default value is true for this class                       |

NMEA0183 processing flags:
* **pass_thru**: messages are forwarded without processing
* **convert_strict**: messages are converted to NMEA2000 when possible and are discarded otherwise
* **convert_pass**: messages are converted to NMEA2000 when possible or are forwarded as-is when not possible

#### N2KJsonPublisher

The publisher is serializing NMEA2000 messages using JSON syntax. Messages are separated by a newline character (ASCII 10)
That output syntax is compatible with the one used by the [canboat analyzer](https://github.com/canboat). The fields names are used for the Json keywords.

| Name           | Type         | Default | Signification                                                     |
|----------------|--------------|---------|-------------------------------------------------------------------|
| output         | stdout, file | stdout  | Where the Json is to be written                                   |
| filename       | str          | None    | If no filename is given, an automatic name is generated           |
| resolve_enum   | bool         | false   | replaces the enum integer value by the corresponding text         |
| remove_invalid | bool         | false   | remove fields with invalid value from the output                  |
| trace_invalid  | bool         | false   | Write an error message on stderr for any invalid NMEA2000 message |

Only PGN that have an associated Python class (that have the <Scope> tag defined as **Generate**) are processed for output. Meaning that all frequent PGN used in Navigation systems are included.
If some PGN in the user network are not in Scope, then the PGN XML definition file needs to be updated and the code generated.

#### N2KTracePublisher

Traces decoded NMEA2000 messages on stdout and/or in a file.

| Name             | Type             | Default | Signification                                                               |
|------------------|------------------|---------|-----------------------------------------------------------------------------|
| file             | string           | none    | Prefix of the filename used to store the traces                             |
| output           | ALL, PRINT, FILE | ALL     | Destinations of the traces                                                  |
| flexible_decode  | bool             | true    | Use interpreted decoding instead of generated decode classes                |
| convert_nmea0183 | bool             | false   | When true, an attempt to convert NMEA0183 messages to NMEA2000 is performed |


#### PrintPublisher

This Publisher simply prints the incoming messages on stdout using the standard conversion to string from Python.
Useful for debugging.


#### Injector (Publisher)

The injector is collecting the messages coming from one or more coupler and inject them on the output of the target coupler.

| Name   | Type             | Default | Signification                                                                  |
|--------|------------------|---------|--------------------------------------------------------------------------------|
| target | string           | none    | Name of the coupler that will receive the messages and send them to the device |

### N2KSourceDispatcher (Publisher)

This publisher dispatch messages based on the NMEA2000 source address. Objects need to subscribe internally to receive the messages in three possible modes.

| Name | Type             | Default | Signification                                                               |
|------|------------------|---------|-----------------------------------------------------------------------------|
| mode | string           | message | Format in which the message is passed to the application object (see below) |

Messages modes definition:
- **transparent** : The content of the message is not interpreted and the raw format from the coupler is passed to the application
- **message** : NMEA2000 binary message format with Fast packet reassembly
- **decoded** : NMEA2000 fully decoded (Python object)

### Applications

Applications are functionally Controller Applications as per J1939, they appear as a device over the CAN bus and a CAN bus address assigned to them.
They must be linked to an **Active CAN Controller** (NMEA2KActiveController) that is managing access to the bus and internal dispatching.
To be active, applications needs to be declared in the Active controller definition (parameter *applications*)

There is currently only one pre-defined application, that is used to inject on the NMEA2000 (CAN) bus messages coming on  gRPC/Protobuf

#### NMEA2000Application

This is the abstract super class for all NMEA2000 applications.

| Name    | Type | Default | Signification                                                                                                |
|---------|------|---------|--------------------------------------------------------------------------------------------------------------|
| address | int  | none    | If this parameter is present and in the range [0, 253] the value will tentatively used as the device address |

If no address is given, it will be allocated from the pool associated with the system (ECU, see NMEA2KActiveController)


#### GrpcInputApplication(GrpcDataService, NMEA2000Application)

That application implements a **service** as defined in the input_server.proto. It accepts both decoded and non decoded NMEA2000 messages (protobuf). It shall be associated with the gRPC server of the process.
All messages received on the gRPC interface are forwarded to the NMEA2000 CAN bus.

| Name             | Type   | Default | Signification                                                                  |
|------------------|--------|---------|--------------------------------------------------------------------------------|
| server           | string | None    | gRPC server associated. This is a mandatory parameter                          |



### Filters

Each filter is described in a specific object, there are 2 main classes to process the 2 message protocols. The action definition is common to both.
On all matching messages the defined action is applied.

### Filter classes

#### NMEAFilter

Abstract class holding action parameters

| Name | Type            | Default | Signification |
|------|-----------------|---------|---------------|
| type | select, discard | discard |               |


When action is *select*, all messages satisfying the criteria are selected.


#### NMEA0183filter (NMEAFilter)

All NMEA0183 messages are processed by the filter. For Coupler in nmea_mix mode, NMEA2000 messages are processed as such, not as NMEA0183.


| Name      | Type                     | Default | Signification                                                                                      |
|-----------|--------------------------|---------|----------------------------------------------------------------------------------------------------|
| talker    | string or list of string | none    | Talker ID of the message, or list of talker ID (2 letters), if none, all talker will be processed  |
| formatter | string or list of string | none    | Formatter of the message (3 letters), or list of formatters, if none, all formatters are processed |

If no talker or formatter is defined, then the filter is discarded

#### NMEA2000Filter (NMEAFilter)

All NMEA2000 Messages are processed through this filter is the Coupler is in nmea2000 or nmea_mix mode.

| Name         | Type     | Default | Signification                                                      |
|--------------|----------|---------|--------------------------------------------------------------------|
| source       | int      | none    | source address of the message. If none, all messages are processed |
| pgn          | int list | none    | list of the PGN to be filtered. If none, all PGN are processed     |
| mfg_id       | int      | none    | Manufacturer NMEA2000 ID (see NMEA2000 site)                       |
| mfg_name     | string   | None    | Manufacturer name as per NMEA2000 official table                   |
| product_name | string   | None    | Product name as published by the PGN 126996. Not always present    |

#### NMEA2000TimeFilter (NMEA2000Filter)

Select one value for each period to reduce message flow for slow moving values

| Name   | Type  | Default | Signification                              |
|--------|-------|---------|--------------------------------------------|
| period | float | 60.0    | minimum period in seconds between messages |

The period shall be defined and non-zero, otherwise the filter is disabled


## Tracing and replay

Every Coupler includes a tracing facility that writes into a file all incoming and outgoing message. The format is very close from the one used on the interface and the format can vary slightly depending on the Coupler.
Each line is using the following structure:
1) a letter R or M. R is the raw format and M the internal message format.
2) A message sequence number
3) The character '#'
4) A time stamp in ISO format
5) The character '>' for incoming messages and '<' for outgoing ones
6) The content of the message. Binary data are converted in hexadecimal format. Extra <lf> are stripped to keep file readability.

The file is written in the directory defined by the parameter *trace_dir* in the configuration file.

File naming is automatic and is build using the syntax: TRACE-<Coupler Name>-<Timesamp>.log

TRace file are useful for troubleshooting, but they can be used also for test and simulation as the files can be fed in a specific Coupler that will inject the content of the file in the **nmea_message_server**.

**Warning: File size can rapidly be very significant. So it is not recommended to activate traces for a long period. Traces can be remotely activated and stopped via the Console service**

### RawLogCoupler (Coupler)

The coupler read and injects the messages from a trace file respecting the timing of the messages. It can be remotely controlled via the Console service.


| Name           | Type        | Default | Signification                                                                            |
|----------------|-------------|---------|------------------------------------------------------------------------------------------|
| logfile        | string      | none    | Trace (log) file to be read                                                              |
| pgn_white_list | list of int | none    | List of PGN that are processed, other are discarded. When not set, all PGN are processed |

All Coupler parameters are applicable, and some must be set like the *nmea2000* or *autostart*.

To keep the message timing, the whole file is read and messages stored in memory before the messages start to be sent in the system. By consequence, the LogReplayCoupler must be used on machines with enough RAM capacity. Recommendation is minimum 4GB of RAM to use the LogReplayCoupler.

### TransparentCanLogCoupler (RawLogCoupler)

This is variant of the RawLogCoupler working only on CAN level traces. Its purpose is to inject the NMEA2000 CAN frames in the system to create a simulator based on existing traces by using the N2KSourceDispatcher as publisher on this coupler.
**Note: with that coupler, no message is sent towards the server for distribution to clients due to the specific format**

### DeviceReplaySimulator (NMEA2000Application)

That application act as Controller Application and simulate a NMEA2000 devices on the **NMEA2000 CAN bus** based on messages read from a log. Only one device per object, so to simulate multiple devices, multiple objects must be instantiated.

If the source is set to 255 the application takes all the messages, thus a single device is forwarding all messages to the CAN bus. All other applications are not receiving any message and are disabled.


| Name      | Type | Default | Signification                                                          |
|-----------|------|---------|------------------------------------------------------------------------|
| source    | int  | none    | source address to select a device in the logs  (255 select all)        |
| publisher | str  | none    | Name of the publisher dispatching messages (N2KSourceDispatcher class) |
| model_id  | str  | none    | String defining the simulated device for display                       |



## Organizing the processes

All the building blocks needs to be organized in several processes for the overall system reliability and processing distribution across CPU (local multiple cores or multiple CPU).

Here are some recommendations based on experience:

1) for reliability reason the Agent service is to be implemented in a specific process. This will allow that process to monitor other processes.
2) Connectivity to NMEA devices (via Coupler) as well as server for NMEA messages. For further processing, like NMEA2000 full decoding, a **GrpcPublisher** can be used to push the NMEA messages.
3) It is recommended to locate energy management devices without NMEA2000 interface in a dedicated server that is instantiating the **MpptService**. This service can be associated to a Publisher that will forward NMEA messages translated from the native interface.
4) The data server is another type of server that will hold data representing the current state of the yacht control system. It can be regularly polled by GUI type of applications. The first version is limited to engine data management but will be extended in the next versions. The data service is expected to receive NMEA messages via a **GrpcInputService**

Many distributions are possible, they can even be spread across several physical machines. Some practical examples are available in the conf directory.

## Configuration files

All configurations files are using the [Yaml language](https://yaml.org/spec/1.2.2/)
Keywords used and structure(s) are explained here below

### Messages server configuration file

That is the main file read by the application upon starts and that instanciate all objects that are declared in the file with the corresponding parameters. There are also some global parameters



The file is divided in 2 main sections: global section and objects section. The file is read only upon the server startup, so to update the server parameters a restart is needed.

The global section includes the definition of the following global parameters:

| Name                   | Type                     | Default                        | Signification                                                                                              |
|------------------------|--------------------------|--------------------------------|------------------------------------------------------------------------------------------------------------|
| function               | string                   | None                           | Short description of the server function                                                                   |
| server_name            | string                   | None                           | Name of the server (for traces and more)                                                                   |
| log_level              | DEBUG/INFO/WARNING/ERROR | INFO                           | Global level of logging (traces)                                                                           |
| manufacturer_xml       | string                   | ./def/Manufacturers.N2kDfn.xml | XML file containing NMEA Manufacturers definition                                                          |
| nmea2000_xml           | string                   | ./def/PGNDefns.N2kDfn.xml      | XML file containing NMEA2000 PGN definitions                                                               |
| trace_dir              | string                   | /var/log                       | Directory where all the traces and logs will be stored                                                     |
| log_file               | string                   | None                           | Filename for all program traces, if None stderr is used instead                                            |
| debug_configuration    | boolean                  | False                          | Allow debug traces during the process configuration phase                                                  |
| decode_definition_only | boolean                  | False                          | If set true then the process stops once fully configured. To be used to test and debug configuration files |

There is  also a subsection (log_module) allowing to adjust the log level per module for fine grain debugging

The per object section includes a list oh object and each object as the following syntax:

-<object name>:
   class: <Class name of the object>
   Then all other parameters as defined in the corresponding section

The following sections are recognized:

- features
- profiling
- servers
- couplers
- publishers
- services
- filters

Sections are not mandatory, but if no *features* are declared, only the default Python packages are loaded and not all needed classes will be present

#### Features concept and Python modules

A **feature** allows the dynamic import of Python packages. By default, each process comes with a minimal set of packages, then based on the functionalities that have to be supported by the process, the corresponding *feature* must be explicitly declared in the configuration file.
If no list is specified after the feature, then the full feature (package) is imported, if a list is specified only the symbols of the list are imported.

Here are the features included with the current version

| feature name  | includes                      | needed for                                   |
|---------------|-------------------------------|----------------------------------------------|
| router_core   | Message router basic features |                                              |
| nmea2000      | NMEA2000 Handling             |                                              |
| nmea0183      | NMEA0183 handling             |                                              |
| couplers      | Non CAN couplers              |                                              |  
| can_interface | direct CAN interface          | NMEA2000 Active controller, CANCoupler       |
| agent         | Linux agent service           | Implementation of the Linux Agent            |
| gnss          | GNSS service                  | STNC800 GNSS module interface and management |



#### Exemple configuration files

First example with only the connection to a replay server

```
function: Navigation messages router
server_name: navigation_router
log_level: INFO
trace_dir: /mnt/meaban/Bateau/tests
# log_file: test_log
log_module:
    nmea_routing.message_server: INFO
    nmea2000.nmea2k_controller: INFO
    nmea_data.data_client: INFO
    nmea_routing.IPCoupler: INFO
    nmea_routing.publisher: DEBUG

features:
  - router_core
  - nmea2000
  - log_replay

servers:

- Main:
    class: NavigationMainServer

- NMEAServer:
    class: NMEAServer
    port: 4500
    nmea2000: transparent

- gRPCMain:
    class: GrpcServer
    port: 4502

- NMEANetwork:
    class: NMEA2KController


couplers:

- SNReplay:
    class: NMEATCPReader
    address: 192.168.1.21
    port: 3555
    autostart: true
    nmea2000_controller: NMEANetwork
    protocol: nmea2000
    trace_messages: false
    trace_raw: false

publishers:

- TraceN2K:
      class: N2KTracePublisher
      couplers: [SNReplay]
      active: false
      filters: [129026]
      file: trace129026
      
filters:

- CatchPGN:
    class: NMEA2000Filter
    pgn: [129026]
    action: select

services:

- Console:
    class: Console
    server: gRPCMain


```

Second example with direct CAN access

```
function: Navigation messages router (CAN)
server_name: navigation_router
log_level: INFO
trace_dir: /mnt/meaban/Bateau/tests
# log_file: test_fast_packet
log_module:
  nmea_routing.coupler: INFO
  nmea2000.nmea2000_msg: INFO
  nmea2000.nmea2k_controller: INFO
  nmea2000.nmea2k_active_controller: DEBUG
  nmea2000.nmea2k_device: INFO
  nmea2000.nmea2k_application: DEBUG
  nmea2000.n2k_name: INFO
  nmea2000.nmea2k_can_interface: INFO
  nmea2000.nmea2k_can_coupler: DEBUG

features:
  - router_core
  - nmea2000
  - can_interface

servers:

- Main:
    class: NavigationMainServer

- NMEAServer:
      class: NMEAServer
      port: 4500
      nmea2000: dyfmt

- gRPCMain:
      class: GrpcServer
      port: 4502

- NMEANetwork:
      class: NMEA2KActiveController
      trace: false
      channel: can0
      applications: [CANCoupler]

- NMEAOutput:
    class: NMEASenderServer
    port: 4503
    nmea2000: dyfmt
    coupler: CANCoupler
    
services:

- Console:
      class: Console
      server: gRPCMain

couplers:

- CANCoupler:
    class: DirectCANCoupler
    autostart: true

filters:

- FastPacket:
    class: NMEA2000Filter
    pgn: [129029, 126996, 129540]
    action: select

- RaymarineProprietary:
    class: NMEA2000Filter
    pgn: [126720]
    action: select

```
#### Profiling

To tackle performance problems, it is possible to enable profiling on specific threads.
A profiling summary is printed on stdout when the server stops

Exemple profiling section

```
profiling:
  enable: true
  symbols:
    - N2KSourceDispatcher
    - NMEA2KActiveController
    - SocketCANInterface
    - SocketCANWriter
```

### Default port assignments for servers / services

In the current version, the port assignment shall be managed manually. In most of the cases that is not an issue as the configuration for one application is rather static.
However, having the system agent allocating the ports can be envisaged in future releases.

| service                       | port | transport protocol | application protocol      |
|-------------------------------|------|--------------------|---------------------------|
| NMEA Messages server          | 4500 | TCP                | NMEA0183 like             |
| Miniplex configuration server | 4501 | TCP                | Miniplex specific         |
| gRPC server                   | 4502 | gRPC               | see console.proto         |
| NMEA message sender           | 4503 | TCP                | NMEA0183 like             |
| Energy management server      | 4505 | gRPC               | see vedirect.proto        |
| Local Linux agent             | 4506 | gRPC               | see agent.proto           |
| Data management server        | 4508 | gRPC               | see navigation_data.proto |

## Implementation structure

### Root directory

### Launching a message server process

A generic Python module is used to start any server "server_main.py" and it requires the configuration file that is defining the feature and parameters of the process using the *--settings option*








