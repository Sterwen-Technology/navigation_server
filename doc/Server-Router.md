## Description
The navigation server-router aggregate and distribute navigation and other operational data aboard recreational vessels.
It is a focal point and server for all kind of data needed to control the course and operational condition of the boat.
The system is based on the building blocks described here below. 
The configuration and parameters of the system are described in a Yaml file.
All building blocks are optional, but if there is no Instrument or Publisher nothing will happen.

The system works with a single Python process and messages are exchanged internally. This can lead to a scalability problem but this was not observed so far.



### Servers
The servers are TCP servers allowing any navigation or control application to access the flow of data via TCP/IP.
There is a generic server: NMEAServer. This server is sending all messages coming from the associated instruments to the clients.
Client can also send messages to the server that are sent to the instrument input.

There are 2 server classes: NMEA0183 based protocol over TCP and binary messages over gRPC.

The NMEA0183 based protocol can be understood and messages starting with '$' or '!' including only printable ASCII characters and separated by the <CR> and <LF> characters
That is not exactly a real protocol over TCP/IP but this is working and the messages (data frames) and directly inherited from the standards NMEA0183 messages.
Even NMEA2000 data frames are carrier over such messages like it is done for Digital Yacht or Shipmodul miniplex.
Using efficient binary encoding with Protobuf and a real protocol like gRPC allows an increase in efficiency. THis is particularly true for NMEA2000 that is binary protocol by nature.

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

*transparent*: messages are transmitted in the same format as the instrument sends them. This is valid only if the instrument is able to send NMEA0183 like NMEA2000 messages. That is also implying that the instrument(s) are configured with the nmea0183 protocol

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


#### gRPCNMEAServer class (future)

Server for NMEA information and other navigation information using the gRPC protocol.

#### Console server

This a gRPC server used for external monitoring and control of the navigation server router. The protobuf interface is in the src/proto/console.proto file.

| Name       | Type                      | Default     | Signification                                                                                  |
|------------|---------------------------|-------------|------------------------------------------------------------------------------------------------|
| port       | int                       | 4502        | listening port of the server                                                                   |


#### ShipModulConfig server

TCP server allowing to bypass the routing function to the connect the Miniplex control application to a Miniplex3 device. To use this feature just configure the MPXConfig utility and assign the server IP and the port configured for it.

Warning: when the application is connected to the server all traffic is re-routed to it. So no NMEA messages are transmitted to the navigation system.

| Name    | Type   | Default | Signification                                          |
|---------|--------|---------|--------------------------------------------------------|
| port    | int    | 4501    | listening port of the server                           |
| coupler | string | None    | Name of the Miniplex coupler in the configuration file |


### Couplers
Couplers classes are connecting to instrumentation bus via direct interfaces or couplers. Direct communication via serial lines is also supported.
Currently, tested couplers:
- Shipmodul Miniplex3 Ethernet (or WiFi)
- Digital Yacht iKonvert
- Yachting Digital Ethernet
- Direct serial link on NMEA0183
- NMEA0183 over TCP/IP
- Victron energy device with VEDirect serial line

Under preparation
- Direct CAN Access

#### Coupler generic parameters

| Name           | Type                                 | Default       | Signification                                                                                                                |
|----------------|--------------------------------------|---------------|------------------------------------------------------------------------------------------------------------------------------|
| timeout        | float                                | 10            | Time out on coupler read in seconds                                                                                          |
 | report_timer   | float                                | 30            | Reporting / tracing interval in sec.                                                                                         |
 | max_attempt    | integer                              | 20            | Max number of attempt to open the device                                                                                     |
| open_delay     | float                                | 2             | Delay between attempt to open the device                                                                                     |
| talker         | string (2)                           | None          | Talker ID substitution for NMEA0183                                                                                          |
| protocol       | nmea0183, nmea2000                   | nmea0183      | Message processing directive nmea0183 treat all messages as NMEA0183 sentence, nmea2000: translate in NMEA2000 when possible |
| direction      | read_only, write_only, bidirectional | bidirectional | Direction of exchange with device                                                                                            |
| trace_messages | boolean                              | False         | Trace all messages after internal pre-processing                                                                             |
| trace_raw      | boolean                              | False         | Trace all messages in device format                                                                                          | 
| autostart      | boolean                              | True          | The coupler is started automatically when the service starts, if False it needs to be started via the Console                |

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

The class is allowing the pass through of configuration messages sent by the MPXconfig utility. This is requiring that a ShipModulConfig server class is setup in the configuration. During the connection of the MPXConfig utility, all messages are directed to it, so no messages sent to clients.

##### YDCoupler (IPCoupler)
Instantiable class to manage Yacht Device Ethernet gateway (YD02EN) for the NMEA2000 port, For NMEA0183, the generic NMEA0183TCPReader can be used.

All frames are converted in internal NMEA2000 format and can then be processed further. That includes Fast Packets reassembly.

##### iKonvert
Instantiable class to manage the DigitalYacht iKonvert USB gateway in raw mode. If the device is in MEA0183 mode and configured by the DigitalYacht utility, then the NMEASerialPort is to be used instead.
The class does not manage the device mode itself that shall be configured via the DY utility.

The device connection and initialisation logic is directly managed by the coupler. The only action needed on the device outside the scope of this coupler is only the configuration in raw mode.

**NMEA sentence !PGDY are converted internally the NMEA2000 sentences.**

| Name   | Type   | Default | Signification                 |
|--------|--------|---------|-------------------------------|
| device | string | None    | Name of the serial USB device |

### Publishers
Publishers concentrate messages from several instruments towards consumers. Publishers are implicitly created by Servers when a new client connection is created.
There are also specific Publishers for tracing and logging.
One particular Publisher is the Injector that allows sending the output of one instrument to the input of another one.

### Filters

### Configuration Yaml file

The file includes the global parameters 