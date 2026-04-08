#! /usr/bin/python

import sys
import struct
from device import DiscImage

SECSIZE = 512

if len(sys.argv) != 3:
    print("Usage: get_loader <device> <loader file>")
    exit(1)

disc = DiscImage(open(sys.argv[1], "rb"))

part_table = disc.read_at(0, 512)

p1 = part_table[0x1be:0x1be+16]
p2 = part_table[0x1ce:0x1ce+16]
p3 = part_table[0x1de:0x1de+16]
p4 = part_table[0x1ee:0x1ee+16]

p1_data = struct.unpack("BBBBBBBBII",p1)

start_sec  = p1_data[8]
length_sec = p1_data[9]

start  = start_sec * SECSIZE
length = length_sec * SECSIZE

print("Loader starts at sector {0} and is {1} sector ({2} bytes) long.".format(start_sec,length_sec,length))

data = disc.read_at(start, length)

print("Saving 'Loader' file to",sys.argv[2])
fd = open(sys.argv[2],"wb")
fd.write(data)
fd.close()

