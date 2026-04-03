from objects import Map, DiscRecord, BOOT_BLOCK_ADDRESS


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


def find_map(disc):
    disc_record = DiscRecord.from_bytes(disc.read_at(BOOT_BLOCK_ADDRESS + 0x1c0, 60))

    map_address = ((disc_record.nzones // 2)*(8*disc_record.secsize-disc_record.zone_spare)-480)*disc_record.bpmb;
    map_length  = disc_record.secsize * disc_record.nzones
    #map_start    = map_address+64;
    #print("Map Address: 0x%08x, Length %x" % (map_address, map_length))

    return map_address, map_length

def get_map(disc):
    map_address, map_length = find_map(disc)
    # print("Map is at {}, length {}".format(map_address, map_length))

    return Map(disc.read_at(map_address, map_length))

