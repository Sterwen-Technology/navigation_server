#-------------------------------------------------------------------------------
# Name:        nav_threading
# Purpose:     Specific module for threads and timer including profiling
#
# Author:      Laurent Carré
#
# Created:     23/07/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import threading
import cProfile
import pstats
import logging
from navigation_server.router_common.global_variables import MessageServerGlobals

_logger = logging.getLogger("ShipDataServer."+__name__)


class NavThread(threading.Thread):
    """
    A threading-based class designed for navigation purposes with optional profiling.

    This class extends threading.Thread and provides functionality for thread management
    and optional profiling. It requires subclasses to implement the `nrun` method
    to define their specific run logic. The class also integrates with a global
    thread controller and profiling system to enhance thread life cycle management
    and performance tracking when profiling is enabled.

    Attributes:
        _name (str): The name assigned to the thread.
        _profile: The profiler object for the thread, if any.
    """
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
        _logger.debug("NavThreading => Thread %s starts" % self._name)
        MessageServerGlobals.thread_controller.record_start(self)
        try:
            self.nrun()
        except Exception as err:
            _logger.error(f"NavThreading => {__name__}|Fatal error in thread: {self._name} class{err.__class__.__name__}:{err} - stopped")
        MessageServerGlobals.thread_controller.record_stop(self)
        _logger.debug("NavThreading => Thread %s stops" % self._name)

    def _run_profiling(self):
        _logger.debug("NavThreading => Thread %s start with profiling" % self._name)
        self._profile.enable()
        self.nrun()
        self._profile.disable()
        self._profile.create_stats()
        _logger.debug("NavThreading => Thread %s stopped with profiling" % self._name)

    def nrun(self) -> None:
        raise NotImplementedError


class NavThreadingController:
    """
    Controller for managing threads in navigation processes.

    This class is responsible for managing the lifecycle of threads in a navigation-related context.
    It allows for the registration of threads, tracking their start and stop operations, and provides
    tools to query currently running threads. The class ensures that thread operations are appropriately
    logged and any issues such as duplicate registrations are flagged.

    Attributes:
        _active_threads (dict): Tracks all registered threads by their names.
        _running_thread (dict): Tracks currently running threads by their names.
    """
    def __init__(self):
        self._active_threads = {}
        self._running_thread = {}

    def register(self, thread: NavThread):
        _logger.debug("NavThreading => Registering thread %s" % thread.name)
        try:
            thr = self._active_threads[thread.name]
            _logger.error("NavThreading => Duplicate thread name: %s" % thread.name)
            return
        except KeyError:
            self._active_threads[thread.name] = thread

    def record_start(self, thread: NavThread):
        _logger.debug("NavThreading => Recording Starting thread %s" % thread.name)
        self._running_thread[thread.name] = thread

    def record_stop(self, thread: NavThread):
        _logger.debug("NavThreading => Recording Thread %s stops" % thread.name)
        try:
            del self._running_thread[thread.name]
            del self._active_threads[thread.name]
        except KeyError:
            _logger.error("NavThreading => Attempt to stop non running thread %s" % thread.name)

    def running_threads(self):
        for thread in self._running_thread.values():
            yield thread


class NavProfilingController:
    """
    Represents a controller for managing profiling configurations and operations.

    The NavProfilingController class provides mechanisms to configure profiling for specific
    components or classes in an application, manage profiling sessions, and output profiling
    statistics. It supports enabling or disabling profiling globally, restricting profiling
    to particular classes, and profiling the main execution flow when required.

    Attributes:
        _profiles (dict): Stores profiling objects for different threads.
        _enable (bool): Indicates whether profiling is enabled globally.
        _enabled_classes (Any): Specific classes allowed for profiling if restrictions are set;
            otherwise, None indicates no restrictions.
        _profile_main (bool): Determines whether profiling is active for the application's main
            execution flow.
    """
    def __init__(self):
        """
        Represents a configuration for profiling features in an application.
        This class maintains state and configuration related to profiling,
        which can include enabling or disabling profiling, tracking profiles of
        specific components, and providing options for profiling the main
        execution flow.

        Attributes:
            _profiles (dict): A dictionary to store profiles for various
                components or classes.
            _enable (bool): A flag indicating whether profiling is globally
                enabled or disabled.
            _enabled_classes (Any): Stores specific classes or components
                for which profiling is enabled, if applicable.
            _profile_main (bool): A flag to indicate whether profiling is enabled
                for the main execution flow of the application.
        """
        self._profiles = {}
        self._enable = False
        self._enabled_classes = None
        self._profile_main = False

    def configure(self, conf, profiling_conf: dict):
        """
        Configures the profiling settings based on the given configuration. This includes enabling profiling,
        validating the symbol list, and checking if the specified symbols meet the required conditions
        such as being subclasses of NavThread.

        Parameters:
            conf (Any): The configuration object used to retrieve classes based on the symbols.
            profiling_conf (dict): A dictionary containing profiling configuration. Expected keys are:
                                   - 'enable' (bool): Indicates whether profiling should be enabled.
                                   - 'symbols' (list): A list of class symbols to be validated and processed.

        Raises:
            KeyError: If a symbol in the 'symbols' list does not correspond to a valid class in the
                      provided configuration object.

        """
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
        """
        Get or create a profiling object for a given thread instance.

        This method manages the creation of a cProfile.Profile object for a specific
        thread, depending on whether profiling is enabled and the thread class is
        allowed.

        Parameters:
        instance (NavThread): The thread instance for which the profiling object
        needs to be retrieved or created.

        Returns:
        cProfile.Profile or None: A profiling object if profiling is enabled and
        allowed for the thread's class; otherwise, None.

        Raises:
        KeyError: If the thread's class is not listed in the enabled classes, and
        profiling is restricted to specific classes.
        """
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
        """
        Provides functionality to stop a profiling session and output the results for each thread. If
        profiling is not enabled, the method immediately returns. For each thread, profiling statistics
        are printed to the console. In case of a TypeError, the error is logged and no statistics are
        printed for that thread.

        Errors during the profiling statistics output are handled gracefully, ensuring the process
        continues for all threads.

        Raises:
            TypeError: If the profile object for a thread is incorrectly formatted or does not support
            the print_stats method. Logged as an error and processing continues for other threads.
        """
        if not self._enable:
            return
        for name, profile in self._profiles.items():
            try:
                print(f"Profiling results for thread:{name}\n")
                profile.print_stats()
            except TypeError:
                _logger.error("Error in profile %s" % name)


