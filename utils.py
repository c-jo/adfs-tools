from objects import Map, DiscRecord, BOOT_BLOCK_ADDRESS


def find_map(disc):
    disc_record = DiscRecord.from_bytes(disc.read_at(BOOT_BLOCK_ADDRESS + 0x1c0, 60))

    map_address = ((disc_record.nzones // 2)*(8*disc_record.secsize-disc_record.zone_spare)-480)*disc_record.bpmb;
    map_length  = disc_record.secsize * disc_record.nzones
    #map_start    = map_address+64;
    #print("Map Address: 0x%08x, Length %x" % (map_address, map_length))

    return map_address, map_length

def get_map(disc, validate=False):
    disc_record = DiscRecord.from_bytes(disc.read_at(BOOT_BLOCK_ADDRESS + 0x1c0, 60))

    if not (disc_record.big_flag & 1):
        raise RuntimeError(
            "Disc is not a large-format disc (big_flag=0x{:02x}); "
            "only big-directory new-map discs are supported".format(disc_record.big_flag))
    if disc_record.format_version != 1:
        raise RuntimeError(
            "Unsupported format_version {}; only format_version 1 "
            "(extended/big directories) is supported".format(disc_record.format_version))

    map_address, map_length = find_map(disc)

    return Map(disc.read_at(map_address, map_length), validate=validate)

