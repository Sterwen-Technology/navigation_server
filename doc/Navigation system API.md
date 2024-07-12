## External/Internal system API

### Introduction

We describe here only the external interfaces that can be configured on the **navigation_server** . These interfaces can transmit messages containing NMEA data on various format and protocol, but also allow the monitoring and control of each server.

The transport layer can be either raw TCP sockets or more sophisticated gRPC communication over HTTP/2. While the data layer is more variable:

- NMEA0183 formatted messages
- NMEA2000 messages over pseudo NMEA0183 messages using !PGDY  or !PGNST sentences
- NMEA0183 over gRPC
- NMEA2000 (binary format) over gRPC
- NMEA2000 decoded over gRPC
- Specific protobuf messages over gRPC
- 

They key benefit of using gRPC is that it fully structure the communication removing the need to analyse the message stream to extract each individual messages. It also provides a fully formalized definition of the interface. On the other end, today, there is no mainstream navigation software accepting gRPC interfaces for the navigation data. So the basic TCP message stream is still what is expected by Navigation software.
Using gRPC is making also easy to implement communication security, although this not included in the current version.

### TCP NMEA message server

These are straightforward TCP server that accept several simultaneous connections limited by the *max_connections* parameter. Each client will receive a copy of the stream of messages comings from the couplers active in the system.

Only NMEA0183 based messages are transmitted over each client socket starting with '$' ot '!' and ending with <cr><lf>
The transmission starts as soon as the socket is open. If there is nothing coming from the couplers, nothing is transmitted.
If the connection is lost with the client, all internal resources are released.

### TCP NMEA message sender server

This TCP server allows sending messages to the device (or bus) mostly for navigation control purposes. The server accepts only one connection at a time to avoid conflicting orders towards the navigation devices.

Same behavior as the receiving server.

### NMEA0183 and pseudo NMEA0183 messages format

*Note: the detailed NMEA0183 syntax and definition is outside the scope of this documentation*

### NMEA0183 messages

The structure of the message follow the syntax:
**[!$]<talker><formatter>,<field1>,...,<fieldn>*<checksum><cr><lf>

So a message is delimited by '!' or '$' for the beginning and <cr><lf> (0x0D0A)

### Pseudo NMEA0183 messages

These messages use the global syntax but are not part of the standard. They are used to carry NMEA2000 messages using a protocol compatible with NMEA0183.

**Important note: in the NMEA2000 message the whole PDU is always included. the transport layer is always transparently processed, except when the whole chain is configured in transparent mode, then the messages from the coupler are directly exposed downstream**


#### !PDGY Format

The format has been developed by Digital Yacht for their NMEA2000 adapters. This is allowing to transport NMEA2000 PDU over an ASCII stream.

The format is the following:

**!PDGY,<pgn>,<priority>,<source>,<destination>,<timestamp>,<PGN data><CR><LF>**

The PGN data are encoded using the base64 algorithm to transform the binary data in an ASCII string.

#### !PGNST Format

The format has been defined by Sterwen Technology and the only difference with !PDGY format is that the PGN data are transmitted as an hexadecimal string.
That requires a bit less processing but generates larger messages.

### gRPC NMEA messages

#### Generic NMEA message

*note: messages described using the Protobuf 3 syntax*

That message is able to carry NMEA0183 or encoded NMEA2000 messages

    `message nmea_msg {
        oneof Message {
            nmea2000pb N2K_msg = 1;
            nmea0183pb N0183_msg = 2;
        }
        uint32 msg_id=3;
    }`

With each flavor of NMEA being:

    `message nmea0183pb {
        string talker=1;
        string formatter=2;   // not existing for proprietary sentences
        float timestamp = 4; // seconds from the epoch
        repeated string values=3; // each field in a separate string
        bytes raw_message=5; //optional, that is the full message. When present the other fields are not tramsitted
        }

Or:

    `message nmea2000pb {  // That is the full NMEA2000 PDU above the transport layer
        uint32 pgn=1;
        uint32 priority=2;
        uint32 sa=3; // source address
        uint32 da =4; // destination address
        float timestamp = 5; // seconds from the epoch
        bytes payload = 6; // Full payload data above transport layer
        }

#### Fully decoded NMEA messages

The systems offers also the possibility to exchange fully decoded NMEA2000 PDU, each PDU field is represented by a Protobuf field.
That is avoiding further decoding or encoding process and allows a simple integration of NMEA2000 data processing in the system.

The top message is generic for all PGN and includes the header section of the NMEA2000 PDU.

    'message nmea2000_decoded_pb {
        uint32 pgn=1;
        uint32 priority=2;
        uint32 sa=3; // source address
        uint32 da =4; // destination address
        float timestamp = 5; // seconds from the epoch
        optional uint32 manufacturer_id = 6; // manufacturer ID for proprietary messages
        google.protobuf.Any payload = 7; // includes PGN specific fields
        }

To simplify the Protobuf construction the PDU specific fields are defined in a specific Protobuf that is generated (see NMEA2000 document).

Serialization-deserialization code can be generated in many languages [see Protobuf documentation](https://protobuf.dev/reference/). Some clients are provided in the framework like the *GrpcPublisher*.
Some other can be developed by anyone in any programming language.

### Services

These are gRPC services that are attached to the message_server gRPC server. Messages communication services are using the NMEA messages described in the previous section.
The full Protobuf description can be found in the proto directory of the repository.

*note: currently the rpc services do not use streams. That is simplifying the processing structure, but also limits the throughput. Moving heavy messaging services to streaming is in the plan*


#### gRPC InputService

This service is allowing to push NMEA messages (NMEA0183/NMEA200 Encoded/NMEA200 Decode) in a server. It is implemented in:
- GrpcNmeaCoupler: coupler that can be used to feed additional processing services
- GrpcInputApplication: that Application (CA) running on the CAN controller injects the NMEA messages received on the CAN bus


    `service NMEAInputServer {
        rpc status (server_cmd) returns (server_resp) {}
        rpc pushNMEA( nmea_msg ) returns (server_resp) {}
        rpc pushDecodedNMEA2K (nmea2000_decoded_pb) returns (server_resp) {}
        }

The *status* method is used mainly to test the connection from the client standpoint.

#### gRPC NmeaServer service

This service allows to pull NMEA messages from the server. This is in the plan but not yet implemented. One of the hurdle is the lack of external client for test.

### Console

The console is also a service running on the gRPC server, but its function is different from the others services and servers.
The console allow to monitor and perform some control on **nmea_message_server** objects. It has a comprehensive Protobuf interface to interact with.

The full details for each object can be found in the **console.proto** file.

An example application using the full console interface is available. It is written in Python and uses a very basic GUI library.

#### Nmea_message_server status

The rpc call **ServerStatus** return the high level status of the nmea_message_server process and the list of servers running inside.

If the connection succeeds to the server, the following information is retrieved:
    - Name (IP + port) and hostname
    - Software version
    - Uptime
    - list of the servers created in the process (but necessarily running)

A few commands can be sent to the main (root) server using the **ServerCmd** rpc call

| command       | target         | result                                |
|---------------|----------------|---------------------------------------|
| stop          | None           | stop the message_server               |
| start_coupler | <coupler name> | start (or restart) the target coupler |


#### Server objects

The server objects have the following information but no command is today possible on them

    'message Server {
        string server_class=1;
        string name=2;
        string server_type=3;
        bool running=4;
        uint32 nb_connections=5; // only for TCP severs
        uint32 port=6;          // only for TCP and gRPC servers
        string protocol=8;      // only for NMEA TCP servers
        repeated Connection connections=7;  // only for TCP servers
        }

#### Coupler objects

Protobuf definition:

    'message CouplerMsg {
        string  name=1;
        string coupler_class=2;
        State state=3;
        enum Device_state {
            NOT_READY=0;
            OPEN=1;
            CONNECTED=2;
            ACTIVE=3;
        }
        Device_state dev_state=4;
        string protocol=5;      // nmea0183/nmea2000/nmea_mix
        uint32 msg_in=6;        // Total number messages received at application layer
        uint32 msg_raw=13;      // Total number messages received at tranport layer
        uint32 msg_out=7;       // Total number messages sent at application layer
        string status=8;        // Coupler device depndent
        uint32 error=9;
        float input_rate=10;  //  all rates in messages / sec
        float input_rate_raw=12;
        float output_rate=11;
    }

On the coupler objects several commands can be sent with some valid only for some couplers. Some commands may have arguments and return values.
Commands arguments and replied values are based on the ArgumentList Protobuf massage that is a list of (key, value) pairs.

| command                  | target         | coupler class | arguments        | effect                                        |
|--------------------------|----------------|---------------|------------------|-----------------------------------------------|
| stop                     | <coupler name> | All           | None             | stop the coupler thread and release resources |
| suspend                  |                | All           | None             | Stop reading the inputs                       |
| resume                   |                | All           | None             | Resume reading                                |
| current_date             | <coupler_name> | LogReplay     | None             | Reply with the current replay date & time     |
| log_file_characteristics |                | LogReplay     | None             | Replay with the current file characteristics  |
| move_to_date             |                | LogReplay     | target timestamp | Move the replay index to the target           |
| restart                  |                | LogReplay     | None             | Restart the log replay at the beginning       |











