# Navigation Messages and Data Server toolbox


## Description

The Navigation Messages & Data Server toolbox is a set of software that can run in a distributed environment that collects, process and distributes the data from the boat navigation and power systems.
It is built around several Python application running independently and communicating via various messaging systems. The preferred internal system is based on Google RPC or [gPRC](https://grpc.io/) and [Protobuf](https://protobuf.dev/).
Other possibility is to use NMEA0183 type streams on pseudo NMEA0183 streams encapsulating NMEA2000 (see documentation on NMEA2000 and data formats)

**The toolbox** is focusing on NMEA2000 messages and data, whatever is the format. NMEA0183 messages are also carried but with a minimum of semantic analysis.

These applications are:
   - **navigation_message_server** that acts as a router/concentrator/proxy between NMEA0183/NMEA2000 instrumentation buses with possibly some adhoc interface to be added for energy systems. There can be several **navigation_message_servers** running in the system and communicating. **navigation_message_server** can be configured to perform data processing and conversion.
   - **vedirect** application reading the VE direct protocol from the RS485 stream and convert it into gRPC messages (it can be accessed directly or via a message server)
   - **local_agent** this is a local service controlling other services via systemd through commands sent via gRPC, it can also act on the system network and operation (reboot)

The navigation application is outside the scope of the project and most of the tests have been performed using [Scannav](https://www.scannav.com/).

The toolbox also includes utilities for NMEA2000 that are described in details the NMEA2000 documentation page like the **code_generator** that is generating Protobuf and Python code to process NMEA2000 PGN.

A sample GUI application for the control of the various server is also available [see repository](https://github.com/Sterwen-Technology/navigation_server_gui). It interacts using gRPC with the servers described above. It is based on TkInter.


## Installation
The project is entirely written in Python 3 and has been tested with Python 3.7 - 3.11. It is intended to run on Linux based system. Is has been tested on Debian, Yocto and Ubuntu.
Installation on Windows 10 or 11 is working with some limitations on TCP sockets and no support on Direct CAN connection.

Current installation is based on a tar file or clone of the git repo. The tar file (**navigation.tar**) is in the head directory of the git repo. Just extract in the directory where you want to run the system.
Then you can install all the required packages: `pip install -r requirements.txt`
It is recommended to set up a Python virtual environment before the installation.

### Supported hosts hardware
 - ARM 32 bits systems: NXP iMX6 Dual or Quad core running Debian or Yocto; Raspberry Pi2
 - ARM 64 bits systems: RPi3 or 4 (1GB RAM is enough), NXP iMX8 running Debian or Yocto
 - AMD64 systems: Running Ubuntu or Debian
 - AMD64 systems with Windows 10: partial support only.

### Supported BUS and instrumentation interfaces
 - Shipmodul Miniplex3 using IP host interface (NMEA0183 and NMEA2000)
 - DigitalYacht iKonvert NMEA2000 USB adapter
 - Yacht Devices IP based systems (NMEA2000 and NMEA0183)
 - NMEA0183 over a serial or TCP/IP interface
 - CAN Direct interfaces:
   - PICAN2 HAT on RPi3 or RPi4
   - SolidRun NXP based gateways: Industrial N6 and N8 Compact with CAN interface
 - Victron VE Direct devices (requires a dedicated process to be configured)

The most versatile solution is to use a device that has a direct CAN bus access. In that case, no specific hardware is required and more features can be deployed as this system becomes a real ECU (Electronic Control Unit) that can run one or more Controller Applications (NMEA2000 devices).
The same device could combine some NMEA0183 inputs on serial port(s) and NMEA2000 bus communication.

### Running the system

The first step is to define a configuration file that describe your environment and the processing scheme that is to be implemented in the message_server. Several samples can be found in the **conf** directory. All details for the configuration are in the **Server-Router** documentation file.


### Interactive running

All servers can be started from the command line, they don't require specific permissions behind the read and write access to the interfaces.

### Automatic start

For production the system should be run through *systemd*. Services that can be used as samples are provided in the application. And a shell script that install all services at once.

## Documentation

The documentation is located in the *doc* directory.

[message_server documentation](https://github.com/Sterwen-Technology/navigation_server/blob/main/doc/Navigation%20message%20server.md)

[System API](https://github.com/Sterwen-Technology/navigation_server/blob/main/doc/Navigation%20system%20API.md)

[NMEA2000 support](https://github.com/Sterwen-Technology/navigation_server/blob/main/doc/NMEA2000.md)


## Development

The Protobuf files can be modified if needed or by generation of new NMEA2000 supporting messages (see NMEA2000 support), however, the output of the Protobuf compiler into Python needs to be adjusted. This is a known limitation of the grpcio compiler.
To overcome the problem a specific Python script has been developed (mod_pb2.py) as well as a convenience shell script (gen_proto) that generates the Python files from the protobuf ones.


## Support

For any problem encountered, please open an issue in this repository.

## Roadmap
The current stable version is V2.05. Documentation is aligned on this version.


## Contributing

All contributions welcome. 

## Authors and acknowledgment
Laurent Carré - [Sterwen Technology](http://www.sterwen-technology.eu). 

## License
Eclipse Public License 2.0. for all development from Sterwen Technology
GNU Lesser GPL v3.0 for Python-can
Apache License 2.0 for grpc

## Project status
Under development.

