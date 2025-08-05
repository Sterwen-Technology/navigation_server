#-------------------------------------------------------------------------------
# Name:        raw_log_reader
# Purpose:     Class to handle processing of raw log files
#
# Author:      Laurent Carré
#
# Created:     23/07/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import datetime
import time
import threading

_logger = logging.getLogger("ShipDataServer." + __name__)


class LogReadError(Exception):

    def __init__(self, reason, message=None, index=0, record_time=0):
        self._reason = reason
        self._message = message
        self._index = index
        self._record_time = record_time

    @property
    def reason(self):
        return self._reason

    @property
    def message(self):
        return self._message

    @property
    def index(self):
        return self._index

    @property
    def record_time(self):
        return self._record_time


class RawLogRecord:

    __slots__ = ('_timestamp', '_message')

    def __init__(self, timestamp):
        self._timestamp = timestamp

    @property
    def timestamp(self):
        return self._timestamp

    @property
    def message(self):
        return self._message


class RawLogNMEARecord(RawLogRecord):

    def __init__(self, timestamp, message):
        super().__init__(timestamp)
        self._message = message.encode() + b'\r\n'


class VEDirectRecord(RawLogRecord):

    def __init__(self, timestamp, message):
        super().__init__(timestamp)
        self._message = message


class RawLogCANMessage(RawLogRecord):

    source_addresses = []

    def __init__(self, timestamp, message):
        self._timestamp = timestamp
        self._message = message
        # find the source address
        try:
            sa = int(message[6:8], 16)
        except ValueError:
            _logger.error("RawLog read message error %s" % message)
            return
        if sa not in self.source_addresses:
            self.source_addresses.append(sa)

    @staticmethod
    def seen_addresses():
        return RawLogCANMessage.source_addresses


class RawLogFile:

    def __init__(self, logfile, tick_interval=300):
        self._abort_flag = False
        self._logfile = logfile
        self._tick_interval = tick_interval
        try:
            self._fd = open(logfile, 'r')
        except IOError as e:
            _logger.error("Error opening logfile %s: %s" % (logfile, e))
            raise
        self._lock = threading.Lock()  # to prevent race conditions while moving around in the logs
        self._records = []
        self._tick_index = []
        self._type = None

    def load_file(self):

        def read_decode(l):
            if l[0] != 'R':
                raise LogReadError('WRONG PREFIX', message=l)

            ih = l.find('#')
            if ih == -1:
                raise ValueError
            i_sup = l.find('>')
            if i_sup == -1:
                raise ValueError
            date_str = l[ih+1:i_sup]
            message = l[i_sup+1:-1]  # removing trailing LF
            timestamp = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S.%f")
            return timestamp, message

        _logger.info("Start reading log file %s" % self._logfile)
        # read the first line
        line = self._fd.readline()
        if line[0] != 'H':
            _logger.error("Log file missing header line")
            self._type = "ShipModulInterface"  # default
        else:
            fields = line.split('|')
            self._type = fields[1]
        _logger.info("Log file type:%s" % self._type)
        if self._type == "SocketCANInterface":
            record_class = RawLogCANMessage
        elif self._type == "ShipModulInterface":
            record_class = RawLogNMEARecord
        elif self._type == "VEDirectInterface":
            record_class = VEDirectRecord
        else:
            _logger.critical(f"Log Reader => unknown file type {self._type}")
            raise ValueError

        nb_record = 1

        first_line = self._fd.readline()
        while True:
            # sometimes first lines are output that needs to be filtered out
            try:
                ts, msg = read_decode(first_line)
                break
            except ValueError:
                first_line = self._fd.readline()
                continue

        self._t0 = ts
        self._records.append(record_class(ts, msg))
        self._nb_tick = 0
        self._next_tick_date = self._t0 + datetime.timedelta(seconds=self._tick_interval)

        line_nb = 1
        for line in self._fd.readlines():
            if self._abort_flag:
                self._fd.close()
                raise LogReadError("Abort requested")
            line_nb += 1
            try:
                ts, msg = read_decode(line)
            except ValueError:
                continue
            except LogReadError as err:
                # print("Error on line", line_nb, line)
                _logger.error("Log file error %s on line %d:%s" % (err.reason, line_nb, line.rstrip('\r\n')))
                continue

            self._records.append(record_class(ts, msg))
            if ts >= self._next_tick_date:
                # ok we record the index of the tick
                self._tick_index.append(nb_record)
                self._nb_tick += 1
                self._next_tick_date = self._t0 + datetime.timedelta(seconds=self._tick_interval * (self._nb_tick+1))
            nb_record += 1
            # give some time back to the scheduler
            if nb_record % 5000 == 0:
                time.sleep(0.01) # sleep 0.01 sec every 5000 lines

        self._fd.close()
        _logger.info("Logfile %s number of records:%d" % (self._logfile, nb_record))
        # self._t0 = self._records[0].timestamp
        self._tend = self._records[nb_record-1].timestamp
        self._duration = self._tend - self._t0
        self._nb_record = nb_record
        _logger.info("Log duration %d h %d m %d s" % (self._duration.seconds // 3600,
                                                    (self._duration.seconds % 3600) // 60, self._duration.seconds % 60))
        self._start_replay_time = 0.0
        self._current_replay_time = 0.0
        self._start_date = self._records[0].timestamp
        self._t0 = 0.0
        self._previous_record = None
        self._index = 0
        self._running = False
        self._first_record = False

    def filename(self):
        return self._logfile

    @property
    def file_type(self):
        if self._type is None:
            _logger.error(f"RawLogReader => file {self._logfile} must be loaded before processing")
            raise ValueError
        return self._type

    def abort_read(self):
        self._abort_flag = True
        _logger.info("%s reader abort requested" % self._logfile)

    def get_messages(self, first=0, last=0, original_timing=True):

        start_replay_time = time.time()
        current_replay_time = 0.0
        previous_record = self._records[first]
        if last == 0:
            last = self._nb_record
        t0 = previous_record.timestamp
        yield previous_record.message
        for record in self._records[first+1:last]:
            if original_timing:
                delta = (record.timestamp - t0).total_seconds()
                wait_time = delta - current_replay_time
                # print(t0.isoformat(), record.timestamp.isoformat(), delta, current_replay_time, wait_time)
                if wait_time > 0.0:
                    time.sleep(wait_time)
                current_replay_time = time.time() - start_replay_time
                # print(delta, current_replay_time)

            yield record.message

    def prepare_read(self, first=0):
        self._index = first
        self.set_references()
        self._running = True

    def read_message(self):
        self._lock.acquire()
        if self._first_record:
            self._first_record = False
            self._lock.release()
            return self._previous_record
        self._index += 1
        try:
            record = self._records[self._index]
        except IndexError:
            _logger.info("Raw Log Reader - Index out of range: %d" % self._index)
            self._lock.release()
            if self._index >= len(self._records):
                raise LogReadError("EOF")
            else:
                raise LogReadError("INDEX ERROR", index=self._index)
        delta = (record.timestamp - self._t0).total_seconds()
        wait_time = delta - self._current_replay_time
        if wait_time > 0.0:
            time.sleep(wait_time)
        self._current_replay_time = time.time() - self._start_replay_time
        self._lock.release()
        return record

    def get_current_log_date(self):
        return self._records[self._index].timestamp

    def shift_start_replay(self, delta: float):
        # adjust the start date this is needed when the replay is suspended
        self._lock.acquire()
        self._start_replay_time += delta
        self._lock.release()

    def move_forward(self, seconds: float):
        self._lock.acquire()
        target_time = self.get_current_log_date() + datetime.timedelta(seconds=seconds)
        tick_index = round(target_time / datetime.timedelta(seconds=self._tick_interval))
        self._index = self._tick_index[tick_index]
        self.set_references()
        self._lock.release()

    def move_to_date(self, target_date: datetime.datetime):
        self._lock.acquire()
        delta = target_date - self._start_date
        tick_index = round(delta / datetime.timedelta(seconds=self._tick_interval))
        if tick_index < 0 or tick_index > self._nb_tick-1:
            self._lock.release()
            _logger.error("LogReader index out of range: %d" % tick_index)
            raise ValueError
        self._index = self._tick_index[tick_index]
        self.set_references()
        self._lock.release()

    def set_references(self):
        # key function to reset the time references after a move
        self._previous_record = self._records[self._index]
        self._t0 = self._records[self._index].timestamp
        self._start_replay_time = time.time()
        self._current_replay_time = self._start_replay_time
        self._first_record = True

    def start_date(self):
        return self._start_date

    def end_date(self):
        return self._tend

    def nb_records(self):
        return self._nb_record

    def duration(self):
        return self._duration.seconds

    @property
    def index(self):
        return self._index

    def message(self, index):
        return self._records[index].message

    def restart(self):
        self._lock.acquire()
        self.prepare_read()
        self._lock.release()



