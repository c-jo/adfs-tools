class DiscImage:
    """Abstracts disc access operations on a file-like object."""

    def __init__(self, fd):
        self._fd = fd

    def read_at(self, address, length):
        self._fd.seek(address)
        return self._fd.read(length)

    def write_at(self, address, data):
        self._fd.seek(address)
        self._fd.write(data)

    def size(self):
        self._fd.seek(0, 2)
        return self._fd.tell()


class HDFImage:
    """Abstracts disc access operations on a HDF file."""

    def __init__(self, fd):
        self._fd = fd

    def read_at(self, address, length):
        self._fd.seek(address+0x200)
        return self._fd.read(length)

    def write_at(self, address, data):
        self._fd.seek(address+0x200)
        self._fd.write(data)

    def size(self):
        self._fd.seek(0, 2)
        return self._fd.tell()-0x200


class TestDevice:
    """A test device that records all written data for inspection."""

    def __init__(self, num_sectors, sector_size):
        self._num_sectors = num_sectors
        self._sector_size = sector_size
        self._writes = []

    def read_at(self, address, length):
        return bytes(length)

    def write_at(self, address, data):
        self._writes.append((address, bytes(data)))

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
