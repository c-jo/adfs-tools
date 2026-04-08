from objects import Map, DiscRecord, BOOT_BLOCK_ADDRESS
from device import DiscImage, HDFImage


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

