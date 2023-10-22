# Navigation Data Server


## Description

The Navigation Data Server is a piece of software that can run in a distributed environment that collects and distributes the data from the boat navigation and power systems.
It is built around several Python application running independently and communicating via various messaging systems. The preferred internal system is based on Google RPC or [gPRC](https://grpc.io/) and [Protobuf](https://protobuf.dev/).
Other possibility is to use NMEA0183 type streams on pseudo NMEA0183 streams encapsulating NMEA2000 (see documentation on NMEA2000 and data formats)

These applications are:
   - **navigation_message_server** that acts as a router/concentrator/proxy between NMEA0183/NMEA2000 instrumentation buses with possibly some adhoc interface to be added for energy systems. There can be several **navigation_message_servers** running in the system and communicating.
   - **navigation_data_server** that consolidates the data, filter and make them available synchronized in time and grouped by function with a simple semantic. The protocol can be specific based on *gRPC* or in the future be compatible with [SignalK](https://signalk.org/)
   - **vedirect** application reading the VE direct protocol from the RS485 stream and convert it into gRPC messages (it can be accessed directly or via a message server)
   - **local_agent** this is a local service controlling other services via systemd through commands sent via gRPC, it can also act on the system network and operation (reboot)

The navigation application is outside the scope of the project and most of the tests have been performed using [Scannav](https://www.scannav.com/).

A sample GUI application for the control of the various server is also available . It interacts using gRPC with the servers described above. It is based on TkInter.


## Installation
The project is entirely written in Python 3 and has been tested with Python 3.7 - 3.11. It is intended to run on Linux based system. Is has been tested on Debian, Yocto and Ubuntu.
Installation on Windows can work but not with all couplers.

Current installation is based on a tar file or clone of the git repo. The tar file (**navigation.tar**) is in the head directory of the git repo. Just extract in the directory where you want to run the system.
Then you can install all the required packages: `pip install -r requirements.txt`
It is recommended to set up a Python virtual environment before the installation.

### Supported hosts hardware (non-imitative list)
 - ARM 32 bits systems: NXP iMX6 Dual or Quad core running Debian or Yocto; Raspberry Pi2
 - ARM 64 bits systems: RPi3 or 4 (1GB RAM is enough), NXP iMX8 running Debian or Yocto
 - AMD64 systems: Running Ubuntu
 - AMD64 systems with Windows 10: partial support only.

### Supported BUS and instrumentation interfaces
 - Shipmodul Miniplex3 using IP host interface (NMEA0183 and NMEA2000)
 - DigitalYacht iKonvert NMEA2000 USB adapter
 - Yacht Devices IP based systems (NMEA2000 and NMEA0183)
 - Actisense NMEA2000 USB adapter (under development)
 - NMEA0183 over a serial or TCP/IP interface
 - CAN Direct interfaces:
   - PICAN2 HAT on RPi3 or RPi4
   - SolidRun NXP based gateways: Industrial N6 and N8 Compact with CAN interfaces
 - Victron VE Direct devices (requires a dedicated process part of the application delivery)

### Running the system

The first step is to define a configuration file that describe your environment. Several samples can be found in the **conf** directory. All details for the configuration are in the **Server-Router** documentation file.

### Interactive running

All servers can be started from the command line, they don't require specific permissions behind the read and write access to the interfaces.

### Automatic start

For production the system is should be run through *systemd*. Services that can be used as sample are provided in the application.


## Usage


## Support

## Roadmap
The current stable version is V1.33.

Next version planned is V1. with the notable add of CAN direct coupler

## Contributing
.

## Authors and acknowledgment
Laurent Carré - Sterwen Technology.

## License
Eclipse Public License 2.0.

## Project status
Under development.

