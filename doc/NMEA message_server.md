## Description
The navigation server-router aggregate and distribute navigation and other operational data aboard recreational vessels.
It is a focal point and server for all kind of data needed to control the course and operational condition of the boat.
The system is based on the building blocks described here below. 
The configuration and parameters of the system are described in a Yaml file.
All building blocks are optional, but if there is no Coupler or Publisher nothing will happen.

**IMPORTANT NOTE: The NMEA message server does not perform any conversion between NMEA0183 messages and NMEA2000 messages in any direction**

The system works with a single Python process and messages are exchanged internally. This can lead to a scalability problem but this was not observed so far.



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

#### NMEAServer class

This class implements a TCP server that is transmitting NMEA0183 based messages over a raw TCP stream. No additional protocol elements are transmitted.
This server is only transmitting messages from the navigation networks (couplers) to the host.

Here are the parameters associated with the server

| Name            | Type                      | Default     | Signification                                                             |
|-----------------|---------------------------|-------------|---------------------------------------------------------------------------|
| port            | int                       | 4500        | listening port of the server                                              |
| heartbeat       | float                     | 30          | Period of the heartbeat  timer                                            |
| timeout         | float                     | 5.0         | timeout socket receive                                                    |
| max_silent      | float                     | 120.0       | maximum time without traffic for a client. The connection is closed after |
| max_connections | int                       | 10          | maximum number of active connections                                      |
| nmea2000        | transparent, dyfmt, stfmt | transparent | Formatting of NMEA2000 messages (see below)                               |


**Format of NMEA2000 messages**

*transparent*: messages are transmitted in the same format as the coupler sends them. This is valid only if the coupler is able to send NMEA0183 like NMEA2000 messages. That is also implying that there is no message loss between coupler and server, so the coupler(s) are configured with the nmea0183 protocol.
When configured in NMEA2000, due to fast packet reassembly, there is no transparency possible.

*dyfmt*: NMEA2000 messages are transmitted using the Digital Yacht !PGDY format

*stfmt*: NMEA2000 messages are transmitted using the Sterwen Technology !PGNST format

if dyfmt or stfmt is selected all NMEA2000 messages will be translated in the selected format including reassembly of Fast Packet. That implies that the protocol selected in the instruments is 'nmea2000'. NMEA0183 messages are transparently transmitted in any case.

The configuration is also valid for messages sent from the host (client), in that case NMEA0183 like messages encapsulating NMEA2000 messages will be treated internally as NMEA2000.

#### NMEASenderServer class
This server allows sending NMEA commands towards a coupler. This is mostly used to control navigation and send tracking information to autopilot and displays


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

 

#### gRPCNMEAServer class (future)

Server for NMEA information and other navigation information using the gRPC protocol.

#### Console server

This a gRPC server used for external monitoring and control of the navigation server router. The protobuf interface is in the src/proto/console.proto file.

| Name       | Type                      | Default     | Signification                                                                                  |
|------------|---------------------------|-------------|------------------------------------------------------------------------------------------------|
| port       | int                       | 4502        | listening port of the server                                                                   |


#### ShipModulConfig server

TCP server allowing to bypass the routing function to connect the Shipmodul Miniplex control application to a Miniplex3 device. To use this feature just configure the MPXConfig utility and assign the server IP and the port configured for it.

Warning: when the application is connected to the server all traffic is re-routed to it. So no NMEA messages are transmitted to the navigation system.

| Name    | Type   | Default | Signification                                          |
|---------|--------|---------|--------------------------------------------------------|
| port    | int    | 4501    | listening port of the server                           |
| coupler | string | None    | Name of the Miniplex coupler in the configuration file |

#### NMEA2KController server

This is an internal server that has no direct TCP access. All accesses to this server are via the Console. This server maintain the list of devices connected on the NMEA2000 network along with the information they are sending.
It shall be associated to a coupler by defining the **nmea2000_controller** parameter to capture all relevant messages. This coupler must be configured with **nmea2000** or **nmea_mix** protocol.
This server is to be used if the access to the NMEA2000 bus is done via a adapter device (see corresponding couplers here below), meaning that the controller has no control on the bus and can only monitor activity.

| Name       | Type   | Default | Signification                                    |
|------------|--------|---------|--------------------------------------------------|
| queue_size | int    | 20      | input message queue size                         |
| save_file  | string | None    | Name of the file for saving the NMEA2000 devices |

#### NMEA2KActiveController(NMEA2KController) server

This class extends the NMEA2KController feature by adding the capability to claim an address on the CAN bus and therefore send messages. Therefore, it only works when the server has a direct connection to the NMEA2000 (CAN) bus.
By adding this class, the server becomes a full NMEA2000 device and no adapter is needed.
This controller performs the role of an ECU referring to J1939 standard. It can manage several applications (CA) that have each their own address on the CAN bus.

| Name             | Type   | Default | Signification                                                            |
|------------------|--------|---------|--------------------------------------------------------------------------|
| channel          | string | can0    | interface device supporting the socket CAN                               |
| mac_source       | string | eth0    | Interface with MAC address to generate the device Unique ID from         |
| manufacturer_id  | int    | 999     | This is the registration number of the manufacturer by the NMEA2000 body |
| message_interval | float  | 0.1     | minimum interval between message sending on the bus in seconds           |
| max_applications | int    | 8       | maximum number of applications supported by the controller               |
| start_address    | int    | 128     | start address for allocation. 2x max_applications addresses are reserved |
| applications | string list | None | List of the applications running on the controller |
| trace | boolean | false | If true traces all CAN messages in a file (see tracing section) |



### Couplers
Couplers classes are connecting to instrumentation bus via direct interfaces or couplers. Direct communication via serial lines is also supported.
Currently, tested couplers:
- Shipmodul Miniplex3 Ethernet (or WiFi): NMEA0183 or NMEA2000 via $MXPGN pseudo NMEA0183 messages
- Digital Yacht iKonvert: NMEA2000 only (mode Raw)
- Yachting Digital Ethernet (or WiFi): NMEA2000 only (the device can be used in NMEA0183 using NMEA0183 over TCP/IP)
- Direct serial link on NMEA0183: NMEA0183 and NMEA2000 using pseudo NMEA0183 messages (check speed)
- NMEA0183 over TCP/IP: NMEA0183 and NMEA2000 using pseudo NMEA0183 messages
- Victron energy device with VEDirect serial line
- Direct CAN Access: NMEA2000 only
- gRPC data injector: allows data flow from a server to another

Under preparation
- Actisense adapter (NGT-1-USB)

#### Coupler generic parameters

| Name                | Type                                 | Default       | Signification                                                                                                                |
|---------------------|--------------------------------------|---------------|------------------------------------------------------------------------------------------------------------------------------|
| timeout             | float                                | 10            | Time out on coupler read in seconds                                                                                          |
 | report_timer        | float                                | 30            | Reporting / tracing interval in sec.                                                                                         |
 | max_attempt         | integer                              | 20            | Max number of attempt to open the device                                                                                     |
| open_delay          | float                                | 2             | Delay between attempt to open the device                                                                                     |
| talker              | string (2)                           | None          | Talker ID substitution for NMEA0183                                                                                          |
| protocol            | nmea0183, nmea2000, nmea_mix         | nmea0183      | Message processing directive nmea0183 treat all messages as NMEA0183 sentence, nmea2000: translate in NMEA2000 when possible |
| direction           | read_only, write_only, bidirectional | bidirectional | Direction of exchange with device                                                                                            |
| trace_messages      | boolean                              | False         | Trace all messages after internal pre-processing                                                                             |
| trace_raw           | boolean                              | False         | Trace all messages in device format (see tracing and replay paragraph)                                                       | 
| autostart           | boolean                              | True          | The coupler is started automatically when the service starts, if False it needs to be started via the Console                |
| nmea2000_controller | string                               | None          | Name of the server of class NMEA2KController associated with the coupler                                                     |

Remarks on protocol behavior:

a) When nmea2000 is selected, NMEA0183 messages are anyway routed transparently when the coupler encodes NMEA2000 frames in pseudo NMEA0183 messages, only NMEA2000 messages (encoded via NMEA0183) are partially decoded in order to reformat them in one of the supported NMEA2000 format. PGN that are part of the ISO protocol are fully decoded and processed locally in the NMEA2KController instance.

b) When nmea0183 is selected, all messages are routed in NMEA0183 and no decoding of possible NMEA2000 is performed.

c) When nmea_mix is selected, the protocol PGN are decoded and processed in the corresponding NMEA2KController instance to give a view of the network. All other messages are routed internally as NMEA2000, but externally they stay in their input format. That mode is only working if a NMEA2KController has been instanced.

**When a NMEA2KController is defined, all ISO protocol messages are processed locally and not forwarded to the message server, so they are not visible by the client**

#### Coupler classes

##### NMEASerialPort
This class handle serial or emulated serial line with NMEA0183 based protocols.
Specific parameters

| Name     | Type    | Default    | Signification             |
|----------|---------|------------|---------------------------|
| device   | string  | no default | Name of the serial device |
| baudrate | integer | 4800       | baud rate for the device  |

##### IPCoupler
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

##### NMEATCPReader (IPCoupler)
Instantiable class to communicate with NMEA0183 based protocol over TCP/IP. It can work in 2 modes: nmea0183 (default) or nmea2000/nmea_mixed.
This is set via the 'protocol' parameter of the base class.
In nmea0183 mode, all frames are transmitted without any transformation.
In nmea2000 (or nmea_mixed) $MXPGN from the Miniplex sentences are transformed in NMEA2000 messages. 
The format of transmission to the server shall be either 'dyfmt' or 'stfmt'. Transparent mode will not work as the messages are transformed.



##### Shipmodul (IPCoupler)
Instantiable class to manage Ethernet or WiFi interface for Shipmodul Miniplex3

The class instance has 2 possible behavior depending on the protocol selected.
- nmea0183: all frames are transparently transmitted as NMEA0183
- nmea2000: All $MXPGN frames are interpreted as NMEA2000 and interpreted as such, including Fast Packet reassembly. Further processing on NMEA2000 frames is explained in the dedicated paragraph.
- nmea_mixed: Only the NMEA2000 bus PGN are reassembled and decoded to be sent to a NMEA2000 Controller, other messages are transmitted transparently

The class is allowing the pass through of configuration messages sent by the MPXconfig utility. This is requiring that a ShipModulConfig server class is setup in the configuration. During the connection of the MPXConfig utility, all messages are directed to it, so no messages sent to clients.

##### YDCoupler (IPCoupler)
Instantiable class to manage Yacht Device Ethernet gateway (YD02EN) for the NMEA2000 port, For NMEA0183, the generic NMEA0183TCPReader can be used.

All frames are converted in internal NMEA2000 format and can then be processed further. That includes Fast Packets reassembly.

##### iKonvert
Instantiable class to manage the DigitalYacht iKonvert USB gateway in raw mode. If the device is in MEA0183 mode and configured by the DigitalYacht utility, then the NMEASerialPort is to be used instead.
The class does not manage the device mode itself that shall be configured via the DY utility.

The device connection and initialisation logic is directly managed by the coupler. The only action needed on the device outside the scope of this coupler is only the configuration in raw mode.

**NMEA sentence !PGDY are converted internally the NMEA2000 sentences when the coupler is set in nmea2000 mode.**

| Name   | Type   | Default | Signification                 |
|--------|--------|---------|-------------------------------|
| device | string | None    | Name of the serial USB device |

#### VEDirect

This class manages the interface with the VEDirect interface service (see) and convert the data into NMEA0183 XDR messages.

| Name    | Type   | Default   | Signification            |
|---------|--------|-----------|--------------------------|
| address | string | 127.0.0.1 | IP address of the server |
| port    | int    | 4505      | listening port           |

#### DirectCANCoupler
This coupler class works when a CAN bus interface with socketcan driver is installed on the system. Obviously, only NMEA2000 messages can be processed.
The CAN bus the coupler must be declared as **application** with a specific NMEA2000 controller: **NMEA2KActiveController**. This controller handles the bus access control protocol and all CAN parameters and the coupler is considered as a specific device (CA) on the CAN bus. 

#### GrpcNmeaCoupler

The coupler creates a gRPC server on which NMEA0183 or NMEA2000 can be pushed (see server.proto). The server that wants to send data has only to declare a **NMEAGrpcDataClient** to forward all NMEA messages to the coupler.

| Name    | Type   | Default | Signification     |
|---------|--------|---------|-------------------|
| address | string | 0.0.0.0 | listening address |
| port    | int    | None    | listening port    |



### Publishers
Publishers concentrate messages from several instruments towards consumers. Publishers are implicitly created by Servers when a new client connection is created.
There are also specific Publishers for tracing and logging.
One particular Publisher is the Injector that allows sending the output of one instrument to the input of another one.

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

## Data client

Data clients are used to forward the NMEA messages (both formats) to an external application. These applications are generally data servers or transcoders to interface other applications.
Currently only one version is developed based on gRPC.

### NMEAGrpcDataClient

Parameters:

| Name    | Type        | Default   | Signification                                |
|---------|-------------|-----------|----------------------------------------------|
| address | string      | 127.0.0.1 | address of the server receiving the messages |
| port    | int         | 4504      | server listening port                        |
| filters | string list | none      | Set of filters applied for the forwarding    |



## Tracing and replay





## Victron VE Direct gRPC server
This service is permanently reading the VEDirect (RS485 over USB) of the MPPT device.
Data are available via the gRPC interface.





## Configuration files

All configurations files are using the [Yaml language](https://yaml.org/spec/1.2.2/)
Keywords used and structure(s) are explained here below

### Messages server configuration file

That is the main file read by the application upon starts and that instanciate all objects that are declared in the file with the corresponding parameters. There are also some global parameters



The file is divided in 2 main sections: global section and objects section. The file is read only upon the server startup, so to update the server parameters a restart is needed.

The global section includes the definition of the following global parameters:

| Name             | Type                     | Default                        | Signification                                                   |
|------------------|--------------------------|--------------------------------|-----------------------------------------------------------------|
| log_level        | DEBUG/INFO/WARNING/ERROR | INFO                           | Level of logging (traces)                                       |
| manufacturer_xml | string                   | ./def/Manufacturers.N2kDfn.xml | XML file containing NMEA Manufacturers definition               |
| nmea2000_xml     | string                   | ./def/PGNDefns.N2kDfn.xml      | XML file containing NMEA2000 PGN definitions                    |
| trace_dir        | string                   | /var/log                       | Directory where all the traces and logs will be stored          |
| log_file         | string                   | None                           | Filename for all program traces, if None stderr is used instead |

There is  also a subsection (log_module) allowing to adjust the log level per module for fine grain debugging

The per object section includes a list oh object and each object as the following syntax:

-<object name>:
   class: <Class name of the object>
   Then all other parameters as defined in the corresponding section

The following sections are recognized:

- servers
- couplers
- publishers
- data_clients
- filters

Sections are not mandatory

#### Exemple configuration files

First example with only the the connectio to a replay server

```
log_level: INFO
trace_dir: /mnt/meaban/Bateau/tests
# log_file: test_log
log_module:
    nmea_routing.message_server: INFO
    nmea2000.nmea2k_controller: INFO
    nmea_data.data_client: INFO
    nmea_routing.IPCoupler: INFO
    nmea_routing.publisher: DEBUG

servers:

- NMEAServer:
    class: NMEAServer
    port: 4500
    nmea2000: transparent

- Console:
    class: Console
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
      filter: [129026]
      file: trace129026


data_clients:

- DataAnalyser:
      class: NMEAGrpcDataClient


```

Second example with direct CAN access

```
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

servers:

- NMEAServer:
      class: NMEAServer
      port: 4500
      nmea2000: dyfmt

- Console:
      class: Console
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

### Default port assignments for services

| service                       | port | transport protocol | application protocol |
|-------------------------------|------|--------------------|----------------------|
| NMEA Messages server          | 4500 | TCP                | NMEA0183 like        |
| Miniplex configuration server | 4501 | TCP                | Miniplex specific    |
| NMEA router console           | 4502 | gRPC               | see console.proto    |
| NMEA message sender           | 4503 | TCP                | NMEA0183 like        |
| NMEA data analyser            | 4504 | gRPC               | see server.proto     |
| VE Direct MPPT server         | 4505 | gRPC               | see vedirect.proto   |
| Local Linux agent             | 4506 | gRPC               | see agent.proto      |

## Implementation structure





