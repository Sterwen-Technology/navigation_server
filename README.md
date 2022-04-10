# Navigation Server-Router


## Description
The navigation server-router aggregate and distribute navigation and other operational data aboard recreational vessels.
It is a focal point and server for all kind of data needed to control the course and operational condition of the boat.
The system is based on the building blocks described here below. The configuration and parameters of the system are described in a Yaml file.

### Servers
The servers are TCP servers allowing any navigation or control application to access the flow of data via TCP/IP.
There is a generic server: NMEAServer. This server is sending all messages coming from the associated instruments to the clients.
Client can also send messages to the server that are sent to the instrument input.
The default protocol is NMEA0183 based even if it carries NMEA2000 messages

### Instruments
Instrument classes are connecting to instrumentation bus via direct interfaces or couplers. Direct communication via serial lines is also supported.
Currently, tested instruments:
- Shipmodul Miniplex3 Ethernet
- Digital Yacht iKonvert
- Yachting Digital Ethernet
- Direct serial link on NMEA0183
- Victron energy device with VEDirect serial line

Under preparation
- Direct CAN Access

### Publishers
Publishers concentrate messages from several instruments towards consumers. Publishers are implicitly created by Servers when a new client connection is created.
There are also specific Publishers for tracing and logging.
One particular Publisher is the Injector that allows sending the output of one instrument to the input of another one.


## Installation
The project is entirely written in Python 3 and has been tested with Python 3.7 - 3.9. It is intended to run on Linux based system 

## Usage


## Support

## Roadmap
The current stage is under development a version 1.0 is planned for the .

## Contributing
.

## Authors and acknowledgment
Laurent Carré - Sterwen Technology.

## License
Eclipse Public License 2.0.

## Project status
Under development.

