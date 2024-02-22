from objects import Map, DiscRecord

def find_map(fd):
    fd.seek(0xc00 + 0x1c0)
    disc_record = DiscRecord.from_bytes(fd.read(60))

    map_address = ((disc_record.nzones // 2)*(8*disc_record.secsize-disc_record.zone_spare)-480)*disc_record.bpmb;
    map_length  = disc_record.secsize * disc_record.nzones
    #map_start    = map_address+64;
    #print("Map Address: 0x%08x, Length %x" % (map_address, map_length))

    return map_address, map_length

def get_map(fd):
    map_address, map_length = find_map(fd)
    # print("Map is at {}, length {}".format(map_address, map_length))

    fd.seek(map_address)
    return Map(fd.read(map_length))

