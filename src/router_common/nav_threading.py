#-------------------------------------------------------------------------------
# Name:        nav_threading
# Purpose:     Specific module for threads and timer including profiling
#
# Author:      Laurent Carré
#
# Created:     23/07/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import threading
import cProfile
import pstats
import logging
from .global_variables import MessageServerGlobals

_logger = logging.getLogger("ShipDataServer."+__name__)


class NavThread(threading.Thread):

    def __init__(self, name: str, daemon=False):
        self._name = name
        self._profile = MessageServerGlobals.profiling_controller.get_profile(self)
        MessageServerGlobals.thread_controller.register(self)
        if self._profile is None:
            target = self._run
        else:
            target = self._run_profiling
        super().__init__(name=name, daemon=daemon, target=target)

    @property
    def name(self):
        return self._name

    def _run(self):
        _logger.debug("Thread %s starts" % self._name)
        MessageServerGlobals.thread_controller.record_start(self)
        try:
            self.nrun()
        except Exception as err:
            _logger.error(f"{__name__}|Fatal error in thread: {self._name}:{err} - stopped")
        MessageServerGlobals.thread_controller.record_stop(self)
        _logger.debug("Thread %s stops" % self._name)

    def _run_profiling(self):
        _logger.debug("Thread %s start with profiling" % self._name)
        self._profile.enable()
        self.nrun()
        self._profile.disable()
        self._profile.create_stats()
        _logger.debug("Thread %s stopped with profiling" % self._name)

    def nrun(self) -> None:
        raise NotImplementedError


class NavThreadingController:

    def __init__(self):
        self._active_threads = {}
        self._running_thread = {}

    def register(self, thread: NavThread):
        _logger.debug("Registering thread %s" % thread.name)
        try:
            thr = self._active_threads[thread.name]
            _logger.error("Duplicate thread name: %s" % thread.name)
            return
        except KeyError:
            self._active_threads[thread.name] = thread

    def record_start(self, thread: NavThread):
        _logger.debug("Recording Starting thread %s" % thread.name)
        self._running_thread[thread.name] = thread

    def record_stop(self, thread: NavThread):
        _logger.debug("Recording Thread %s stops" % thread.name)
        try:
            del self._running_thread[thread.name]
        except KeyError:
            _logger.error("Attempt to stop non running thread %s" % thread.name)

    def running_threads(self):
        for thread in self._running_thread.values():
            yield thread


class NavProfilingController:

    def __init__(self):
        self._profiles = {}
        self._enable = False
        self._enabled_classes = None
        self._profile_main = False

    def configure(self, conf, profiling_conf: dict):
        self._enable = profiling_conf.get('enable', False)
        if self._enable:
            _logger.debug("Profiling enabled")
            symbols = profiling_conf.get('symbols', None)
            if symbols is None:
                return
            elif type(symbols) is not list:
                _logger.error("Profiling symbol list syntax error")
                return
            for sym in symbols:
                try:
                    class_sym = conf.get_class(sym)
                except KeyError:
                    _logger.error("Profiling configuration no class for:%s" % sym)
                    continue
                if not issubclass(class_sym, NavThread):
                    _logger.error("Profiling class %s is not a subclass of NavThread" % class_sym.__name__)
                    continue
                if self._enabled_classes is None:
                    self._enabled_classes = {}
                # Ok, we have a class that we can profile
                _logger.debug("Profiling adding class %s" % class_sym.__name__)
                self._enabled_classes[class_sym.__name__] = class_sym

    def get_profile(self, instance: NavThread):
        if not self._enable:
            return None
        _logger.debug("Creating profile for thread %s" % instance.name)
        def create_profile():
            profile = cProfile.Profile()
            self._profiles[instance.name] = profile
            return profile

        if self._enabled_classes is None:
            return create_profile()

        class_name = instance.__class__.__name__
        try:
            sym = self._enabled_classes[class_name]
            return create_profile()
        except KeyError:
            return None

    def stop_and_output(self):
        if not self._enable:
            return
        for name, profile in self._profiles.items():
            try:
                print(f"Profiling results for thread:{name}\n")
                profile.print_stats()
            except TypeError:
                _logger.error("Error in profile %s" % name)


