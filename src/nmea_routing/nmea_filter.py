#-------------------------------------------------------------------------------
# Name:        NMEA
# Purpose:      Utilities to analyse and generate NMEA sentences
#
# Author:      Laurent Carré
#
# Created:     06/10/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

class NMEATCPReader(BufferedIPCoupler):

    def __init__(self, opts):
        super().__init__(opts)
        if self._mode != self.NMEA0183:
            _logger.error("Protocol incompatible with NMEA0183 reader")
            raise ValueError
        ffilter = opts.getlist('white_list', bytes)
        if ffilter is None:
            self._filter = []
        else:
            self._filter = ffilter
        rfilter = opts.getlist('black_list', bytes)
        if rfilter is None:
            self._black_list = []
        else:
            self._black_list = rfilter
        if ffilter is None and rfilter is None:
            self.set_message_processing()
        else:
            _logger.info("Formatter filter %s" % self._filter)
            _logger.info("Formatter black list %s" % self._black_list)
            self.set_message_processing(msg_processing=self.filter_messages)

    def filter_messages(self, frame):
        if frame[0] == 4:
            # EOT
            return NavGenericMsg(NULL_MSG)
        msg = process_nmea0183_frame(frame)
        fmt = msg.formatter()
        if fmt in self._filter:
            _logger.debug("Message retained: %s" % frame)
            return msg
        if fmt not in self._black_list:
            return msg
        _logger.debug("Rejected message %s" % frame)
        raise ValueError


class NMEA2000TCPReader(BufferedIPCoupler):

    process_function = {'dyfmt': fromPGDY, 'stfmt': fromPGNST}

    def __init__(self, opts):
        super().__init__(opts)
        self._mode = self.NMEA2000
        self._format = opts.get_choice('format', ('dtfmt','stfmt'), 'dyfmt')
        self.set_message_processing(msg_processing=self.process_function[self._format])

