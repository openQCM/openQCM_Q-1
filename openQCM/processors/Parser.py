"""
ParserProcess — fan-out object owning the queues that connect the
acquisition child process to the GUI Worker.

Each `add{1..6}` and `add_tracking` method puts a payload on the
corresponding queue; the GUI side drains them via the matching
`Worker.consume_queue*` methods. The class inherits from
`multiprocessing.Process` only so that callers can pass it through
multiprocessing primitives — it does not run any code itself
(no `run()` is needed).

Queue assignments:
    queue1 — raw amplitude trace
    queue2 — raw phase trace
    queue3 — smoothed resonance frequency [(timestamp_us, value)]
    queue4 — smoothed dissipation         [(timestamp_us, value)]
    queue5 — smoothed temperature         [(timestamp_us, value)] /
             calibration completion flags
    queue6 — error / status flags
    queue_tracking — auto-tracking notifications
"""
import multiprocessing

from openQCM.common.logger import Logger as Log


TAG = ""  # set to "[Parser]" for verbose tagged prints


class ParserProcess(multiprocessing.Process):

    def __init__(self,
                 data_queue1,
                 data_queue2,
                 data_queue3,
                 data_queue4,
                 data_queue5,
                 data_queue6,
                 data_queue_tracking=None):
        """
        :param data_queue{1..6}:    multiprocessing.Queue per data channel
        :param data_queue_tracking: multiprocessing.Queue for auto-tracking events
        """
        multiprocessing.Process.__init__(self)
        self._exit = multiprocessing.Event()

        self._out_queue1 = data_queue1
        self._out_queue2 = data_queue2
        self._out_queue3 = data_queue3
        self._out_queue4 = data_queue4
        self._out_queue5 = data_queue5
        self._out_queue6 = data_queue6
        self._out_queue_tracking = data_queue_tracking

    # ---- Per-channel pushers ----
    def add1(self, data):
        """Push an amplitude trace on queue1."""
        self._out_queue1.put(data)

    def add2(self, data):
        """Push a phase trace on queue2."""
        self._out_queue2.put(data)

    def add3(self, data):
        """Push a (timestamp, resonance frequency) tuple on queue3."""
        self._out_queue3.put(data)

    def add4(self, data):
        """Push a (timestamp, dissipation) tuple on queue4."""
        self._out_queue4.put(data)

    def add5(self, data):
        """Push a (timestamp, temperature) tuple on queue5."""
        self._out_queue5.put(data)

    def add6(self, data):
        """Push a status / error tuple on queue6."""
        self._out_queue6.put(data)

    def add_tracking(self, data):
        """
        Push an auto-tracking notification.

        :param data: list of the form
            [activated, start_freq, stop_freq, ref_freq, count, disabled_by_errors?]
        """
        if self._out_queue_tracking is not None:
            self._out_queue_tracking.put(data)

    def stop(self):
        """Signal the process to stop (no-op here, kept for API symmetry)."""
        self._exit.set()
