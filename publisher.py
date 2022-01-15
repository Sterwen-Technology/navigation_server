
import threading
import time
import queue
import logging
import datetime

from configuration import NavigationConfiguration

_logger = logging.getLogger("ShipDataServer")

#######################################################################
#
#    Publisher classes => send messages to clients
#
########################################################################


class Publisher(threading.Thread):
    '''
    Super class for all publishers
    '''
    def __init__(self, opts):
        name = opts['name']
        self._opts = opts
        super().__init__(name=name)
        self._name = name
        inst_list = opts['instruments']
        self._instruments = []
        for inst_name in inst_list:
            self._instruments.append(self.resolve_ref(inst_name))
        for inst in self._instruments:
            # print("Registering %s on %s" % (self._name, inst.name()))
            inst.register(self)
        self._queue = queue.Queue(20)
        self._stopflag = False
        self._nb_msg_lost = 0

    def publish(self, msg):
        # print("Publisher %s publish msg:%s" % (self._name, msg.decode().strip('\n\r')))
        try:
            self._queue.put(msg, block=False)
            self._nb_msg_lost = 0
        except queue.Full:
            # need to empty the queue
            self._nb_msg_lost += 1
            _logger.warning("Overflow on connection %s total message lost %d" % (self._name, self._nb_msg_lost))

    def deregister(self):
        for inst in self._instruments:
            inst.deregister(self)

    def add_instrument(self, instrument):
        self._instruments.append(instrument)
        instrument.register(self)

    def stop(self):
        _logger.info("Stop received for %s" % self._name)
        self._stopflag = True
        self.deregister()

    def run(self) -> None:
        while not self._stopflag:
            try:
                msg = self._queue.get(timeout=1.0)
            except queue.Empty:
                if self._stopflag:
                    break
                else:
                    continue
            # print("message get in Publisher %s" % msg.decode()[:6])
            if not self.process_msg(msg):
                break
        self.last_action()

        _logger.info("Stopping publisher thread %s" % self._name)

    def last_action(self):
        pass

    def process_msg(self, msg):
        _logger.critical("No message processing handler in publisher")
        return False

    def name(self):
        return self._name

    def descr(self):
        return "Publisher %s" % self._name

    @staticmethod
    def resolve_ref(name):
        return NavigationConfiguration.get_conf().get_object(name)


class LogPublisher(Publisher):
    def __init__(self, opts):
        super().__init__(opts)
        self._filename = opts['filename']
        try:
            self._fd = open(filename, "w")
        except IOError as e:
            _logger.error("Error opening logfile %s: %s" % (filename, str(e)))
            raise
        self._start = time.time()
        self._fd.write("NMEA LOG START TIME:%9.3f\n" % self._start)
        self._fd.flush()

    def process_msg(self, msg):
        delta_t = time.time() - self._start
        self._fd.write("%9.3f|" % delta_t)
        if type(msg) == bytes:
            self._fd.write(msg.decode())
        else:
            # need to serialize first
            self._fd.write(msg.serialize())
            self._fd.write('\n')
        self._fd.flush()
        return True

    def last_action(self):
        self._fd.close()

    def descr(self):
        return "Log File "+self._filename


class Injector(Publisher):

    def __init__(self, opts):
        super().__init__(opts)
        self._target = self.resolve_ref(opts['target'])

    def process_msg(self, msg):
        self._target.send_cmd(msg)
        return True

    def descr(self):
        return "Injector %s" % self._name


class SendPublisher(Publisher):

    def __init__(self, opts):
        super().__init__(opts)
        self._sender = self.resolve_ref(opts['sender'])
        self._filename = opts['filename']
        self._sender.add_publisher(self)
        try:
            self._fd = open(self._filename, "w")
        except IOError as e:
            _logger.error("Error opening logfile %s: %s" % (self._filename, str(e)))
            raise
        self._start = time.time()
        self._fd.write("NMEA LOG START TIME:%9.3f\n" % self._start)
        self._fd.flush()

    def process_msg(self, msg):
        time_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f|")
        self._fd.write(time_str)
        if type(msg) == bytes:
            self._fd.write(msg.decode())
        else:
            # need to serialize first
            self._fd.write(msg.serialize())
            self._fd.write('\n')
        self._fd.flush()
        return True

    def last_action(self):
        self._fd.close()

    def descr(self):
        return "Log File "+self._filename
