class Device:
    """Abstract base class for disc devices.

    Subclasses must implement read() and write(), which operate in sectors.
    read_at() and write_at() are provided as byte-addressed helpers that
    delegate to read() and write() using self._sector_size.
    """

    # Reads count sectors at lba, returning count * sector_size bytes.
    def read(self, lba, count):
        raise NotImplementedError

    # Writes data to count sectors at lba.
    # len(data) must equal count * sector_size.
    def write(self, lba, count, data):
        raise NotImplementedError

    def read_at(self, address, length):
        start_lba = address // self._sector_size
        offset = address % self._sector_size
        end_lba = (address + length - 1) // self._sector_size if length > 0 else start_lba
        count = end_lba - start_lba + 1
        return self.read(start_lba, count)[offset:offset + length]

    def write_at(self, address, data):
        start_lba = address // self._sector_size
        offset = address % self._sector_size
        length = len(data)
        end_lba = (address + length - 1) // self._sector_size if length > 0 else start_lba
        count = end_lba - start_lba + 1
        if offset == 0 and length == count * self._sector_size:
            self.write(start_lba, count, data)
        else:
            buf = bytearray(self.read(start_lba, count))
            buf[offset:offset + length] = data
            self.write(start_lba, count, bytes(buf))


class DiscImage(Device):
    """Abstracts disc access operations on a disc image file."""

    def __init__(self, filename, mode='r+b', sector_size=512):
        # TODO: sector size is unknown here without reading the disc record first
        import os
        if isinstance(filename, (str, os.PathLike)):
            self._fd = open(filename, mode)
        else:
            self._fd = filename
        self._sector_size = sector_size

    def read(self, lba, count):
        self._fd.seek(lba * self._sector_size)
        return self._fd.read(count * self._sector_size)

    def write(self, lba, count, data):
        assert len(data) == count * self._sector_size
        self._fd.seek(lba * self._sector_size)
        self._fd.write(data)

    def size(self):
        self._fd.seek(0, 2)
        return self._fd.tell()


class HDFImage(Device):
    """Abstracts disc access operations on a HDF file."""

    def __init__(self, filename, mode='rb', sector_size=512):
        # TODO: sector size is unknown here without reading the disc record first
        import os
        if isinstance(filename, (str, os.PathLike)):
            self._fd = open(filename, mode)
        else:
            self._fd = filename
        self._sector_size = sector_size

    def read(self, lba, count):
        self._fd.seek(lba * self._sector_size + 0x200)
        return self._fd.read(count * self._sector_size)

    def write(self, lba, count, data):
        assert len(data) == count * self._sector_size
        self._fd.seek(lba * self._sector_size + 0x200)
        self._fd.write(data)

    def size(self):
        self._fd.seek(0, 2)
        return self._fd.tell() - 0x200


class TestDevice(Device):
    """A test device that records all written data for inspection."""

    def __init__(self, num_sectors, sector_size):
        self._num_sectors = num_sectors
        self._sector_size = sector_size
        self._writes = []

    def read(self, lba, count):
        return bytes(count * self._sector_size)

    def write(self, lba, count, data):
        assert len(data) == count * self._sector_size
        self._writes.append((lba * self._sector_size, bytes(data)))

    def size(self):
        return self._num_sectors * self._sector_size

    def save(self, filename):
        """Save all written data to a text file.

        Each line is formatted as:
            lba+offset : hh hh hh ...
        where lba is the sector number (16 hex digits), offset is the
        byte offset within that sector (4 hex digits), and each byte is
        printed as two hex digits, 16 bytes per line.
        """
        with open(filename, 'w') as f:
            for address, data in self._writes:
                lba = address // self._sector_size
                base_offset = address % self._sector_size
                for i in range(0, len(data), 16):
                    chunk = data[i:i+16]
                    hex_bytes = ' '.join('{:02x}'.format(b) for b in chunk)
                    f.write('{:016x}+{:04x} : {}\n'.format(lba, base_offset + i, hex_bytes))
