"""
Fixed-size circular buffer backed by a NumPy array.

Index 0 always points to the most recently appended sample, so
`get_all()` returns elements ordered from newest (left) to oldest (right).
While the buffer fills up, the unused slots hold the `default_value`
(NaN by default — convenient for plotting since pyqtgraph skips NaNs).
Once `size_max` elements have been pushed, the instance switches its
`__class__` to `RingBufferFull` so that subsequent appends skip the
size-tracking branch.

References:
    http://code.activestate.com/recipes/68429-ring-buffer/
    http://stackoverflow.com/questions/4151320/efficient-circular-buffer
"""
import warnings

import numpy as np


# Suppress the numpy "all-NaN slice" warnings emitted by callers that operate
# on freshly-allocated buffers (this is expected and harmless).
warnings.filterwarnings("ignore", category=RuntimeWarning)


class RingBuffer(object):
    """Fixed-size circular buffer (newest item at index 0)."""

    def __init__(self, size_max, default_value=np.nan, dtype=float):
        self.size_max = size_max
        self._data = np.empty(size_max, dtype=dtype)
        self._data.fill(default_value)
        self.size = 0

    def append(self, value):
        """Append `value` at index 0; once full, switch to `RingBufferFull`."""
        self._data = np.roll(self._data, 1)
        self._data[0] = value
        self.size += 1
        if self.size == self.size_max:
            self.__class__ = RingBufferFull

    def get_all(self):
        """Return the underlying buffer (newest first; unused slots are NaN)."""
        return self._data

    def get_partial(self):
        """Return only the slots that have been filled so far."""
        return self.get_all()[0:self.size]

    def __getitem__(self, key):
        return self._data[key]

    def __repr__(self):
        s = self._data.__repr__()
        s += '\t' + str(self.size)
        s += '\t' + self.get_all()[::-1].__repr__()
        s += '\t' + self.get_partial()[::-1].__repr__()
        return s


class RingBufferFull(RingBuffer):
    """RingBuffer specialisation used after the buffer reaches `size_max`."""

    def append(self, value):
        self._data = np.roll(self._data, 1)
        self._data[0] = value
