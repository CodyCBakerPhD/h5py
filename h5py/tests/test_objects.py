# This file is part of h5py, a Python interface to the HDF5 library.
#
# http://www.h5py.org
#
# Copyright 2008-2013 Andrew Collette and contributors
#
# License:  Standard 3-clause BSD; see "license.txt" for full license terms
#           and contributor agreement.
import os
import threading
import time

import pytest

from h5py import _objects as o
from h5py import h5f
from .common import TestCase


class TestObjects(TestCase):

    def test_invalid(self):
        # Check for segfault on close
        oid = o.ObjectID(0)
        del oid
        oid = o.ObjectID(1)
        del oid

    def test_equality(self):
        # Identifier-based equality
        oid1 = o.ObjectID(42)
        oid2 = o.ObjectID(42)
        oid3 = o.ObjectID(43)

        self.assertEqual(oid1, oid2)
        self.assertNotEqual(oid1, oid3)

    def test_hash(self):
        # Default objects are not hashable
        oid = o.ObjectID(42)
        with self.assertRaises(TypeError):
            hash(oid)

    @pytest.mark.thread_unsafe(reason="fork() from a thread may deadlock")
    @pytest.mark.filterwarnings(
        # https://github.com/python/cpython/pull/100229
        r"ignore:.*use of fork\(\) may lead to deadlocks:DeprecationWarning"
    )
    @pytest.mark.skipif(not hasattr(os, "fork"), reason="fork() not available")
    def test_phil_fork_with_threads(self):
        """Test that handling of the phil Lock after fork is correct.

        h5py uses os.register_at_fork() to cause os.fork() to acquire the phil lock
        before forking and release it afterwards, so that the global state of libhdf5
        cannot be cloned in a corrupted state.
        """
        thread_acquired_phil_event = threading.Event()

        def f():
            # Simulate another thread holding the phil lock while it updates
            # the libhdf5 global state
            with o.phil:
                thread_acquired_phil_event.set()
                time.sleep(1)

        thread = threading.Thread(target=f)
        thread.start()
        thread_acquired_phil_event.wait()

        try:
            # Now fork the current (main) thread while the other thread holds the lock.
            # os.fork() acquires the phil lock, so this will block until the other
            # thread releases it.
            pid = os.fork()
            if pid == 0:
                # Child process
                # If we handle the phil lock correctly, this should not deadlock, and we
                # should be able to acquire the lock here.
                if o.phil.acquire(blocking=False):
                    o.phil.release()
                    os._exit(0)
                else:
                    os._exit(1)
            else:
                # Parent process
                assert o.phil.acquire(blocking=False)
                o.phil.release()
                # Wait for the child process to finish
                _, status = os.waitpid(pid, 0)
                assert os.WIFEXITED(status)
                assert os.WEXITSTATUS(status) == 0
        finally:
            thread.join()


@pytest.mark.thread_unsafe(reason="holds the global lock while another thread runs")
def test_dealloc_while_locked_in_other_thread(writable_file):
    """An object deallocated while another thread holds the lock (e.g., by a
    garbage collection in a thread serving the reads of a Python file object)
    does not wait for the lock, which could deadlock: its identifier is
    released the next time the lock is acquired."""
    writable_file["x"] = [1, 2, 3]
    ids = [writable_file["x"].id]

    def open_datasets():
        return h5f.get_obj_count(writable_file.id, h5f.OBJ_DATASET)

    assert open_datasets() == 1
    deallocated = threading.Event()

    def deallocate():
        ids.clear()
        deallocated.set()

    with o.phil:
        thread = threading.Thread(target=deallocate)
        thread.start()
        assert deallocated.wait(10)
    thread.join()
    o.ObjectID(0)  # Acquires the lock
    assert open_datasets() == 0
