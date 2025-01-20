#-------------------------------------------------------------------------------
# Name:        nmea_tcp_coupler
# Purpose:     Generic coupler for NMEA ASCII sentences NMEA0183 ou NMEA2000 embedded in pseudo NMEA0183
#               all above a TCP connection
#
# Author:      Laurent Carré
#
# Created:     13/01/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------


import logging
from router_common import NavGenericMsg, N2K_MSG, NULL_MSG
from router_core import NMEA0183Msg
from router_core import fromProprietaryNmea
from router_common import IncompleteMessage
from .ikonvert import iKonvertMsg
from .shipmodul_if import ShipModulInterface
from router_core import BufferedIPCoupler
from nmea2000 import FastPacketHandler


_logger = logging.getLogger("ShipDataServer."+__name__)


class NMEATCPReader(BufferedIPCoupler):
    '''
    This class is implementing a generic NMEA reader that adapt to all known NMEA0183 based protocols
    NMEA2000 encapsulated in NMEA0183 are automatically converted to NMEA2000
    '''

    def __init__(self, opts):
        super().__init__(opts)
        self._direction = self.READ_ONLY  # no writing on generic reader
        self._fast_packet_handler = FastPacketHandler(self)
        self._separator = b'\r\n'
        self._separator_len = 2
        if self._mode != self.NMEA0183:
            self.set_message_processing(msg_processing=self.process_msg)
        else:
            self.set_message_processing()

    def process_msg(self, frame):

        if frame[0] == 4:
            return NavGenericMsg(NULL_MSG)
        self._total_msg_raw += 1
        if frame[0:5] == b'!PDGY':
            # ok we have an iKonvert frame => direct decode into NMEA2000
            ik_msg = iKonvertMsg(frame)
            if ik_msg is None:
                raise IncompleteMessage
            msg = NavGenericMsg(N2K_MSG, msg=ik_msg.msg)
            return msg
        else:
            msg0183 = NMEA0183Msg(frame)

        if msg0183.proprietary():
            return fromProprietaryNmea(msg0183)
        elif msg0183.address() == b'MXPGN':
            msg = ShipModulInterface.mxpgn_decode(self, msg0183)
            # print(msg.dump())
            return msg
        else:
            return msg0183
