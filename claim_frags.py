#! /usr/bin/python

import sys
from objects import Map
from utils import find_map

fd = open("Loader", "r")
fd.seek(0,2)
loader_len = fd.tell()
fd.close()

print("Loader is {0} bytes long.".format(loader_len))

if len(sys.argv) != 2:
    print("Usage: claim_frags <device>")
    exit(1)

fd = open(sys.argv[1], "r+b")
map_address, map_length = find_map(fd)
fd.seek(map_address)
fs_map = Map(fd.read(map_length))

loader_start = (fs_map.disc_record.idlen+1) * fs_map.disc_record.bpmb

bits_needed = loader_len   // fs_map.disc_record.bpmb
start_bit   = loader_start // fs_map.disc_record.bpmb
last_bit    = start_bit + bits_needed

while start_bit * fs_map.disc_record.bpmb < loader_start:
    start_bit += 1

while bits_needed * fs_map.disc_record.bpmb < loader_len:
    bits_needed += 1

print("{0} map bits required for loader, from bit {1} to {2}.".format(bits_needed,start_bit,last_bit))

zone = 0

while True:
    zone_start, zone_end = fs_map.zone_range(zone)

    first_in_zone = zone_start
    last_in_zone  = zone_end

    if zone_start < start_bit:
        first_in_zone = start_bit

    if last_bit < last_in_zone:
        last_in_zone = last_bit

    #note = ""
    #if first_in_zone > zone_start:
    #   note = " ** {0} bits not used at start of zone".format(first_in_zone-zone_start)

    #if last_in_zone < zone_end:
    #   note = " ** {0} bits not used at end of zone".format(zone_end-last_in_zone)

    #print "Zone {0} - bits {1} to {2}{3}".format(zone,first_in_zone,last_in_zone,note)
    #print zone_start

    fs_map.allocate(zone, 3, first_in_zone-zone_start, last_in_zone-zone_start)

    if zone_end > last_bit:
        break

    zone += 1

fd.seek(map_address)
fd.write(fs_map.data.tobytes())

