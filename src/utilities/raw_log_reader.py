#-------------------------------------------------------------------------------
# Name:        raw_log_reader
# Purpose:     Class to handle processing of raw log files
#
# Author:      Laurent Carré
#
# Created:     23/07/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import datetime
import time

_logger = logging.getLogger("ShipDataServer." + __name__)


class RawLogRecord:

    def __init__(self, timestamp, message):
        self._timestamp = timestamp
        self._message = message[:len(message)-1].encode() + b'\r\n'

    @property
    def timestamp(self):
        return self._timestamp

    @property
    def message(self):
        return self._message


class RawLogFile:

    def __init__(self, logfile, tick_interval=300):
        self._logfile = logfile
        try:
            fd = open(logfile, 'r')
        except IOError as e:
            _logger.error("Error opening logfile %s: %s" % (logfile, e))
            raise

        def read_decode(l):
            if l[0] != 'R':
                _logger.error('Wrong line type:%s' % l)
                raise ValueError

            ih = l.find('#')
            if ih == -1:
                raise ValueError
            i_sup = l.find('>')
            if i_sup == -1:
                raise ValueError
            date_str = l[ih+1:i_sup]
            message = l[i_sup+1:]
            timestamp = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S.%f")
            return timestamp, message

        _logger.info("Start reading log file %s" % logfile)
        nb_record = 1
        self._records = []
        self._tick_index = []
        self._tick_interval = tick_interval
        first_line = fd.readline()
        ts, msg = read_decode(first_line)
        self._t0 = ts
        self._records.append(RawLogRecord(ts, msg))
        self._nb_tick = 0
        self._next_tick_date = self._t0 + datetime.timedelta(seconds=tick_interval)

        for line in fd.readlines():
            try:
                ts, msg = read_decode(line)
            except ValueError:
                continue

            self._records.append(RawLogRecord(ts, msg))
            if ts >= self._next_tick_date:
                # ok we record the index of the tick
                self._tick_index.append(nb_record)
                self._nb_tick += 1
                self._next_tick_date = self._t0 + datetime.timedelta(seconds=tick_interval * (self._nb_tick+1))
            nb_record += 1

        fd.close()
        _logger.info("Logfile %s number of records:%d" % (logfile, nb_record))
        # self._t0 = self._records[0].timestamp
        self._tend = self._records[nb_record-1].timestamp
        self._duration = self._tend - self._t0
        self._nb_record = nb_record
        _logger.info("Log duration %d h %d m %d s" % (self._duration.seconds // 3600,
                                                    (self._duration.seconds % 3600) // 60, self._duration.seconds % 60))
        self._start_replay_time = 0.0
        self._current_replay_time = 0.0
        self._t0 = 0.0
        self._previous_record = None
        self._index = 0
        self._running = False
        self._first_record = False

    def filename(self):
        return self._logfile

    def get_messages(self, first=0, last=0):

        start_replay_time = time.time()
        current_replay_time = 0.0
        previous_record = self._records[first]
        if last == 0:
            last = self._nb_record
        t0 = previous_record.timestamp
        yield previous_record.message
        for record in self._records[first+1:last]:
            delta = (record.timestamp - t0).total_seconds()
            wait_time = delta - current_replay_time
            # print(t0.isoformat(), record.timestamp.isoformat(), delta, current_replay_time, wait_time)
            if wait_time > 0.0:
                time.sleep(wait_time)
            current_replay_time = time.time() - start_replay_time
            # print(delta, current_replay_time)

            yield record.message

    def prepare_read(self, first=0):
        self._start_replay_time = time.time()
        self._previous_record = self._records[first]
        self._index = first
        self._t0 = self._previous_record.timestamp
        self._first_record = True
        self._running = True

    def read_message(self):
        if self._first_record:
            self._first_record = False
            return self._previous_record.message
        self._index += 1
        try:
            record = self._records[self._index]
        except IndexError:
            _logger.info("Raw Log Reader - Index out of range: %d" % self._index)
            raise ValueError
        delta = (record.timestamp - self._t0).total_seconds()
        wait_time = delta - self._current_replay_time
        if wait_time > 0.0:
            time.sleep(wait_time)
        self._current_replay_time = time.time() - self._start_replay_time
        return record.message

    def get_current_log_date(self):
        return self._records[self._index].timestamp

    def move_forward(self, seconds: float):
        target_time = self.get_current_log_date() + datetime.timedelta(seconds=seconds)
        tick_index = round(target_time / datetime.timedelta(seconds=self._tick_interval))
        self._index = self._tick_index[tick_index]

    def move_to_date(self, target_date: datetime.datetime):
        delta = target_date - self._start_date
        tick_index = round(delta / datetime.timedelta(seconds=self._tick_interval))
        if tick_index < 0 or tick_index > self._nb_tick-1:
            raise ValueError
        self._index = self._tick_index[tick_index]

    def start_date(self):
        return self._t0

    def end_date(self):
        return self._tend

    def nb_records(self):
        return self._nb_record

    def duration(self):
        return self._duration.seconds





