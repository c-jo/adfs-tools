#! /usr/bin/python
from itertools import product

from array import array
from objects import DiscRecord, Map, BigDir, BootBlock
import struct
import ctypes

ZONE0BITS = 60*8 # Bits used in Zone 0
IDLEN_MAX = 21
MAPSIZE_MAX = 128*1024*1024

"""
#define LOG2SECTORSIZE 10
#define LOG2BPMB_MIN  (7)
#define LOG2BPMB_MAX  (12)
#define ZONESPARE_MIN (32)
#define ZONESPARE_MAX (64)
#define ZONES_MIN     (1)
#define ZONES_MAX     (127)
#define IDLEN_MIN     (LOG2SECTORSIZE + 3)
#define IDLEN_MAX   (19)

#define NEWDIR_SIZE 0x800
"""

####
#disc_sectors = 234441648
#log2_secsize = 9
####
disc_sectors = 1953525168>>3 # Convert to 4K
log2_secsize = 12
####

def make_shape(sectors):
    """Generate a CHS shape for a given number of sectors."""
    best_wasted = 0xffffffff
    best = None
    for secs,heads in product(range(63,15,-1), range(255,15,-1)):
        cyls = sectors / (secs*heads)
        if cyls > 65535:
            continue
        wasted = sectors % (secs*heads)
        if (wasted < best_wasted):
            best_wasted = wasted
            best = (secs,heads,sectors//(secs*heads))
    return best

def check_alloc(sectors, log2ss, zones, zonespare, log2bpmb, idlen):
    """Checks if the given allocation is valid."""
    disc_allocs = (sectors << log2ss) // (1 << log2bpmb)
    bpzm = 8 * (1 << log2ss) - zonespare # Bits per zone map
    map_allocs = (bpzm * zones) - ZONE0BITS
    idpz = bpzm / (idlen+1) # IDs per Zone

    if map_allocs < disc_allocs:
        return False # Map doens't cover disc

    if (1 << idlen) < idpz * zones:
        return False # Not enough IDs

    excess_allocs = map_allocs - disc_allocs
    if 0 < excess_allocs <= idlen:
        return False # Can't make excess into a fragment

    lz_allocs = disc_allocs - (map_allocs - bpzm)
    if lz_allocs <= idlen:
        return False # Can't make last bit of last zone into a fragment

    return True

def find_alloc(sectors, log2ss, zones, log2bpmb):
    """Find an allocation for the given zones/log2bpmb, or 
       None if one cannot be found."""
    for zonespare in range(32,64): # 32 to ZoneBits%-Zone0Bits%-8*8
        for idlen in range(log2_secsize, IDLEN_MAX+1):
            if check_alloc(sectors, log2ss, zones, zonespare, log2bpmb, idlen):
                return (zones, zonespare, log2bpmb, idlen)



## Start
print("Disc has {} sectors of {} bytes - Capacity {:.1f} GB".format(
    disc_sectors, 1<<log2_secsize,
    (disc_sectors << log2_secsize)/1000/1000/1000))

dr = DiscRecord()
dr.log2secsize = log2_secsize
dr.disc_size = disc_sectors << log2_secsize
dr.secspertrack, dr.heads, cylinders = make_shape(disc_sectors)

print("Using shape {} sectors, {} heads, {} cylinders.".format(
    dr.secspertrack, dr.heads, cylinders))

allocs = {} # LFAU -> Shape

# Find what log2 bpmb / zones combinations we can use
for log2bpmb in range(7,26):
    # Roughly how many zones we need
    map_bits_needed = (disc_sectors << log2_secsize) // (1 << log2bpmb)
    zones_guess = map_bits_needed // (1 << log2_secsize) // 8
    if zones_guess << log2_secsize > MAPSIZE_MAX:
        continue

    for zones in range(zones_guess, zones_guess + 10 + zones_guess // 20): 
        alloc = find_alloc(disc_sectors, log2_secsize, zones, log2bpmb)
        if alloc:
            allocs[1<<log2bpmb] = alloc
            break

alloc = allocs[32*1024]

if not alloc:
    for lfau, alloc in allocs.items():
         print("LFAU: {}K, map size: {}K ({} zones)".format(
             lfau/1024, (alloc[0]<<log2_secsize)/1024, alloc[0]))
    alloc = allocs[1024*int(input("LFAU (in K): "))]

dr.nzones, dr.zone_spare, dr.log2bpmb, dr.idlen = alloc
dr.sharesize = 0 ## TODO: calculate thie
dr.disc_name = b"Filecore00"

dr.show()
map_zone, map_address, map_size = dr.map_info()
print("Map zone: {}, address: {}, size: {} ({} map bits)".format(
    map_zone, map_address, map_size, map_size / dr.bpmb))

map = Map(b'\0'*map_size)
map.disc_record = dr
map.clear()

map_start = map.disc_to_map(map_address)
map_end   = map.disc_to_map(map_address+(map_size*2)-1) # Two copies

if map_start[0] != map_end[0]:
    print("Map spans multiple zones.")
    exit(2)

print("Map is {} sectors map bits {} to {}"
    .format(map_size/dr.secsize, map_start[1], map_end[1]))


# The root goes after the maps
root_address = map_address + (map_size*2)
# Make sure it's sector aligned
while root_address % dr.secsize != 0 or map.disc_to_map(root_address)[1] <= map_end[1]:
    root_address += 1

print("Root address: {}".format(root_address))

root_zone, root_offset = map.disc_to_map(root_address)

ids_per_zone = (dr.secsize * 8 - dr.zone_spare) // (dr.idlen + 1)
root_frag_id = root_zone * ids_per_zone

root_map_bits = max(dr.idlen+1, 2048 // dr.bpmb)

print("Root is in zone {} offset {}, fragment id {:x}".format(
    root_zone, root_offset,root_frag_id))

dr.root = (root_frag_id << 8) + 1
dr.root_size = 2048
map.disc_record = dr

map.allocate(0, 2, 0, dr.idlen)
map.allocate(map_zone, 2, map_start[1], map_end[1])

print("Root takes {} map bits.".format(root_map_bits))
map.allocate(root_zone, root_frag_id, root_offset, root_offset+root_map_bits)

last_zone, overhang_start = map.disc_to_map(dr.disc_size)
map.allocate(last_zone, 1, overhang_start, dr.secsize*8-dr.zone_spare-1)

root = BigDir()
root.parent_id = dr.root

map.show_zone(root_zone, True)
print("Map crosscheck: {:x}".format(map.cross_check()))

bootrec = BootBlock(dr)
print(hex(ctypes.sizeof(bootrec)))

with open("/dev/sdb", "w+b") as f:
    f.seek(0xc00)
    f.write(bootrec)
    f.seek(map_address)
    f.write(map.data)
    f.write(map.data)
    f.seek(root_address)
    f.write(root.data())
    

