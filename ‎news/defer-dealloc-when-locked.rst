Bug fixes
---------

* Deallocating an h5py object (e.g., in a garbage collection) while another
  thread holds h5py's global lock no longer waits for that lock, which could
  deadlock when the other thread was waiting for the deallocating one, e.g.,
  while reading a Python file object whose reads are served by another thread
  (as with fsspec): the HDF5 identifier is released once the lock is next
  acquired instead.
