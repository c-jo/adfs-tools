import struct
import array
import ctypes
import random

from functools import reduce

def dir_check_words(data, count, dircheck):
    for word in struct.unpack("{0}I".format(count), data):
        dircheck = word ^ ( ((dircheck >> 13) & 0xffffffff) | ((dircheck << 19) & 0xffffffff) )
    return dircheck

def dir_check_bytes(data, count, dircheck):
    for byte in struct.unpack("{0}B".format(count), data):
        dircheck = byte ^ ( ((dircheck >> 13) & 0xffffffff) | ((dircheck << 19) & 0xffffffff) )
    return dircheck

class DiscRecord(ctypes.Structure):
    _fields_ = [
        ('log2secsize', ctypes.c_uint8),
        ('secspertrack', ctypes.c_uint8),
        ('heads', ctypes.c_uint8),
        ('density', ctypes.c_uint8),
        ('idlen', ctypes.c_uint8),
        ('log2bpmb', ctypes.c_uint8),
        ('skew', ctypes.c_uint8),
        ('bootoption', ctypes.c_uint8),
        ('lowsector', ctypes.c_uint8),
        ('nzones_1', ctypes.c_uint8),
        ('zone_spare', ctypes.c_uint16),
        ('root', ctypes.c_uint32),
        ('disc_size_1', ctypes.c_uint32),
        ('disc_id', ctypes.c_uint16),
        ('disc_name', ctypes.c_char*10),
        ('disctype', ctypes.c_uint32),
        ('disc_size_2', ctypes.c_uint32),
        ('log2share', ctypes.c_uint8),
        ('big_flag', ctypes.c_uint8),
        ('nzones_2', ctypes.c_uint8),
        ('reserved_1', ctypes.c_byte),
        ('format_version', ctypes.c_uint32),
        ('root_size', ctypes.c_uint32),
        ('reserved_2', ctypes.c_byte*8),
        ]

    def __init__(self):
        self.density = 0
        self.skew = 0
        self.lowsector = 1
        self.big_flag = 1
        self.format_version = 1

    @staticmethod
    def from_bytes(data):
        return DiscRecord.from_buffer_copy(data)

    @property
    def bpmb(self):
        return 1 << self.log2bpmb

    @property
    def secsize(self):
        return 1 << self.log2secsize

    @property
    def share_size(self):
        return 1 << self.log2share;

    @property
    def nzones(self):
        return (self.nzones_2 << 8) + self.nzones_1

    @nzones.setter
    def nzones(self, new_zones):
        self.nzones_2 = new_zones >> 8
        self.nzones_1 = new_zones

    @property
    def disc_size(self):
        return (self.disc_size_2 << 32) + self.disc_size_1

    @disc_size.setter
    def disc_size(self, new_size):
        self.disc_size_2 = new_size >> 32
        self.disc_size_1 = new_size

    def show(self):
        print("Disc Record:")
        print("  Sector size: %d" % self.secsize)
        print("  Bytes per map bit: %d" % self.bpmb)
        print("  ID Length: %d" % self.idlen)
        print("  Skew: %d" % self.skew)
        print("  Low Sector: %d" % self.lowsector)
        print("  Number of zones: %d" % self.nzones)
        print("  Zone spare: %d" % self.zone_spare)
        print("  Share size: {}".format(self.share_size))
        print("  Disc Size: %d (MB)" % (self.disc_size // 1024 // 1024))
        print("  Root: {:x} ({} bytes)".format(self.root, self.root_size))

    def map_info(self):
        return (
            self.nzones // 2,
            ((self.nzones // 2)*(8*self.secsize-self.zone_spare)-480)*self.bpmb,
            self.secsize * self.nzones
          )

class Map(object):
    class Zone(object):
        def __init__(self, disc_record):
            self.disc_record = disc_record
            self.data = array.array('B', [0]*disc_record.secsize)


    def __init__(self, data):
        self.data = array.array('B')
        self.data.frombytes(data)
        self.disc_record = DiscRecord.from_bytes(data[4:64])

    @property
    def disc_record(self):
        return DiscRecord.from_bytes(self.data[4:64])

    @disc_record.setter
    def disc_record(self, disc_record):
        dr = bytearray(disc_record)
        for i in range(0,60):
            self.data[i+4] = dr[i]

    @property
    def nzones(self):
        return self.disc_record.nzones

    @property
    def id_per_zone(self):
        return ((self.disc_record.secsize*8) - self.disc_record.zone_spare) // (self.disc_record.idlen+1)

    def clear(self):
        cross_checks = random.randbytes(self.disc_record.nzones-1)
        cross_checks = cross_checks + int.to_bytes(0xff ^ reduce(lambda a,b:a^b, cross_checks), 1, "little")

        for zone in range(self.nzones):
            zone_start = zone * self.disc_record.secsize
            for n in range(64 if zone == 0 else 4, self.disc_record.secsize):
                self.data[zone_start+n] = 0x00

            last_bit = self.disc_record.secsize*8-self.disc_record.zone_spare-1
            self.set_bit(zone, last_bit, 1)

            if zone == 0:
                start_bit = 0x18+480+self.disc_record.idlen+1
                self.data[zone_start+1] = start_bit & 0xff
                self.data[zone_start+2] = (start_bit | 0x8000) >> 8
            else:
                self.data[zone_start+1] = 0x18
                self.data[zone_start+2] = 0x80

            self.data[zone_start+3] = cross_checks[zone]
            self.data[zone_start+0] = self.calc_zone_check(zone)

    def cross_check(self):
        cross_check = 0
        for zone in range(self.nzones):
            zone_start = zone * self.disc_record.secsize
            cross_check = cross_check ^ self.data[zone_start+3]

        return cross_check

    def show(self, unused=True):
        for zone in range(self.nzones):
            self.show_zone(zone,unused)

    def zone_range(self, zone):
        return (\
             ((self.disc_record.secsize*8-self.disc_record.zone_spare)*zone)  - (480 if zone > 0 else 0),
             ((self.disc_record.secsize*8-self.disc_record.zone_spare)*(zone+1)) - 480 - 1)

    def zone_header(self, zone):
        zone_start  = zone * self.disc_record.secsize
        return self.data[zone_start:zone_start+4]

    def get_bit(self, zone, bit):
        byte = (bit // 8) + (64 if zone == 0 else 4) # Zone 0 has the disc record
        shift = bit % 8
        data = self.data[byte+zone*self.disc_record.secsize]
        val = data & 1 << shift
        return 1 if val > 0 else 0

    def set_bit(self, zone, bit, val):
        byte = (bit // 8) + (64 if zone == 0 else 4) # Zone 0 has the disc record
        shift = bit % 8
        old_data = self.data[byte+zone*self.disc_record.secsize]
        new_data = old_data & ( 0xff ^ 1<<shift) | ((1<<shift) if val else 0)
        self.data[byte+zone*self.disc_record.secsize] = new_data

    def disc_to_map(self, disc_address):
        # how many bits into the map are we?
        bit_in_map = disc_address >>  self.disc_record.log2bpmb

        # which zone is it on?
        for zone in range(0, self.nzones):
            start, end = self.zone_range(zone)
            if start <= bit_in_map <= end:
                return (zone, bit_in_map-start)

    def calc_zone_check(self, zone):
        sum_vector0 = 0
        sum_vector1 = 0
        sum_vector2 = 0
        sum_vector3 = 0
        zone_start  = zone * self.disc_record.secsize
        rover = ((zone+1)*self.disc_record.secsize)-4
        while rover > zone_start:
            sum_vector0 += self.data[rover+0] + (sum_vector3>>8)
            sum_vector3 &= 0xff
            sum_vector1 += self.data[rover+1] + (sum_vector0>>8)
            sum_vector0 &= 0xff
            sum_vector2 += self.data[rover+2] + (sum_vector1>>8)
            sum_vector1 &= 0xff
            sum_vector3 += self.data[rover+3] + (sum_vector2>>8)
            sum_vector2 &= 0xff
            rover -= 4

        # Don't add the check byte when calculating its value
        sum_vector0 += (sum_vector3>>8)
        sum_vector1 += self.data[rover+1] + (sum_vector0>>8)
        sum_vector2 += self.data[rover+2] + (sum_vector1>>8)
        sum_vector3 += self.data[rover+3] + (sum_vector2>>8)

        return (sum_vector0^sum_vector1^sum_vector2^sum_vector3) & 0xff

    def allocate(self, zone, frag_id, from_bit, to_bit):
        if to_bit - from_bit < self.disc_record.idlen:
            raise RuntimeError("allocation too small")

        free_link = ( (self.data[zone*self.disc_record.secsize+1] << 0) +
                      (self.data[zone*self.disc_record.secsize+2] << 8) ) & 0x7fff

        print("allocate zone {} {} to {} - FreeLink {:x}".format(zone, from_bit, to_bit, free_link))

        free_offset = free_link - 0x18

        bit = from_bit
        for i in range(self.disc_record.idlen):
           self.set_bit(zone, bit, frag_id & (1<<i))
           bit += 1

        while bit < to_bit:
           self.set_bit(zone, bit, 0)
           bit += 1

        self.set_bit(zone, bit, 1)

        #bits_before = ((self.disc_record.secsize*8-self.disc_record.zone_spare)*zone) - (480 if zone > 0 else 0)
        #last_bit    = ((self.disc_record.secsize*8-self.disc_record.zone_spare)*(zone+1)) -480

        last_bit = (self.disc_record.secsize*8-self.disc_record.zone_spare) - (481 if zone == 0 else 1)

        if from_bit == free_offset - (480 if zone == 0 else 0):
            new_free_link = 0x8000 if bit == last_bit else 0x8001 + bit + (63*8 if zone == 0 else 3*8)
            self.data[zone * self.disc_record.secsize+1] = (new_free_link >> 0) & 0xff
            self.data[zone * self.disc_record.secsize+2] = (new_free_link >> 8) & 0xff
        else:
            self.set_bit(zone, from_bit-1, 1)
            print("Zone {}: from bit ({}) isn't start of free space in zone ({})".format(zone, from_bit, free_offset))

        self.data[zone * self.disc_record.secsize+0] = self.calc_zone_check(zone)

    def show_zone(self, zone, show_unused):
        zone_start  = zone * self.disc_record.secsize
        bits_before = ((self.disc_record.secsize*8-self.disc_record.zone_spare)*zone) - (480 if zone > 0 else 0)
        last_bit    = ((self.disc_record.secsize*8-self.disc_record.zone_spare)*(zone+1)) -480
        free_link   = (self.data[zone_start+2])*256+(self.data[zone_start+1])

        if free_link == 0x8000:
            free_offset = None
        else:
            free_offset = (free_link & 0x7fff) - (63*8 if zone == 0 else 3*8)

        if free_offset is not None:
            print(("Zone %d (FreeLink = %x - %d bits)" % (zone, free_link, free_offset)))
        else:
            print(("Zone %d (FreeLink = %x - No free space)" % (zone, free_link)))

        bit = 0
        while True:
           frag_id = 0
           start   = bit

           for i in range(self.disc_record.idlen):
              frag_id |= self.get_bit(zone, bit) << i
              bit += 1

           while (self.get_bit(zone, bit) == 0):
               if bit > last_bit:
                   print("** Stop bit not found before end of zone.")
                   break
               bit += 1

           disc_start = (start+bits_before)*self.disc_record.bpmb
           disc_end   = (bit  +bits_before)*self.disc_record.bpmb

           print(("  Fragment ID: %x map bits %d to %d, disc address %d to %d (%d)" %
               (frag_id, start, bit, disc_start, disc_end-1, disc_end-disc_start)))

           bit += 1
           if bit+bits_before >= last_bit:
               break

    def find_in_zone(self, search_id, zone):
        zone_start  = zone * self.disc_record.secsize
        bits_before = ((self.disc_record.secsize*8-self.disc_record.zone_spare)*zone) - (480 if zone > 0 else 0)
        free_link   =  (self.data[zone_start+2])*256+(self.data[zone_start+1])

        rv = []

        bit = 0
        while True:
           frag_id = 0
           start   = bit

           for i in range(self.disc_record.idlen):
              frag_id |= self.get_bit(zone, bit) << i
              bit += 1

           while (self.get_bit(zone, bit) == 0):
               bit += 1

           bit += 1
           disc_start = (start+bits_before)*self.disc_record.bpmb
           disc_end   = (bit  +bits_before)*self.disc_record.bpmb

           if frag_id == search_id:
               rv.append((disc_start, disc_end))

           if bit+bits_before >= ((self.disc_record.secsize*8-self.disc_record.zone_spare)*(zone+1)) -480:
               break

        return rv

    def find_fragment(self, fragment_id, length = None):
        addresses = [] # List of (start,end) disc addresses

        start_zone = fragment_id // self.id_per_zone
        zone = start_zone

        while True:
           in_this = self.find_in_zone(fragment_id, zone)
           if len(in_this) > 0:
               addresses += in_this

           if length:
              count = 0
              for (start,end) in addresses:
                  count += end-start

              if count >= length:
                  break

           zone += 1

           if zone >= self.disc_record.nzones:
               zone = 0

           if zone == start_zone:
               break

        return addresses

class BigDir(object):
    class Entry(object):
        def __init__(self, name, loadaddr, execaddr, length, attribs, ind_disc_addr):
            self.name     = name
            self.loadaddr = loadaddr
            self.execaddr = execaddr
            self.length   = length
            self.attribs  = attribs
            self.ind_disc_addr = ind_disc_addr

        @staticmethod
        def from_dir(data, name_heap):
            loadaddr, execaddr, length, ind_disc_addr, attribs,\
            name_len, name_ptr = struct.unpack("IIIIIII",data)
            name = name_heap[name_ptr:name_ptr+name_len]
            return BigDir.Entry(name, loadaddr, execaddr, length, attribs, ind_disc_addr)

        def is_directory(self):
            return self.attribs & 1<<3

        def attr_str(self):
            s = ''
            s += "R" if self.attribs & 1<<0 else "-"
            s += "W" if self.attribs & 1<<1 else "-"
            s += "L" if self.attribs & 1<<2 else "-"
            s += "D" if self.attribs & 1<<3 else "-"
            s += "r" if self.attribs & 1<<4 else "-"
            s += "w" if self.attribs & 1<<5 else "-"
            return s

        def show(self):
            print('{0:<15} {1:08x} {2:08x} {3:12} {4} {5:x}'.format(\
                  self.name.decode('latin-1'), self.loadaddr, self.execaddr,
                  self.length, self.attr_str(), self.ind_disc_addr))

    def __init__(self, data=None):
        if data is None:
            self.sequence = 1
            self.size = 2048
            self.name = b'$'
            self.entries = []
            return

        self.sequence, sbpr, name_len, self.size, \
        entries, names_size, self.parent_id = struct.unpack("Bxxx4sIIIII",data[0:0x1c])

        if sbpr != b'SBPr':
            raise RuntimeError("Invalid directory start marker ({0})".format(sbpr))

        self.name = data[0x1c:0x1c+name_len]

        heap_start = (entries*0x1c) + ((0x1c+name_len+4)//4)*4
        heap_end   = heap_start+names_size
        heap_data  = data[heap_start:heap_end]

        self.entries = []
        data_start = ((0x1C+name_len+4)//4)*4

        for entry in range(0,entries):
            start = data_start + (entry*0x1C)
            self.entries.append(\
                BigDir.Entry.from_dir(data[start:start+0x1c], heap_data))

        oven, end_seq, check = struct.unpack("4sBxxB",data[-8:])

        if oven != b'oven':
            raise RuntimeError("Invalid directory end marker ({0})".format(oven))

        tail = data[-8:]
        calc = dir_check_words(data[0:heap_end], heap_end//4, 0)
        calc = dir_check_words(tail[0:4], 1, calc)
        calc = dir_check_bytes(tail[4:7], 3, calc)
        calc = (calc << 0 & 0xff) ^ (calc >> 8 & 0xff) ^ (calc >> 16 & 0xff) ^ (calc >> 24 & 0xff)

        if calc != check:
            raise RuntimeError("Directory check-byte failed.")

    def data(self):
        # TODO: Currently only handles 2048 byte directories.
        data = b''

        name_heap = b''
        heap_lookup = {}
        for entry in self.entries:
           heap_lookup[self.entries.index(entry)] = len(name_heap)
           name_heap += entry.name+b'\x0d'

        # Word-justify it
        while len(name_heap) % 4 != 0:
            name_heap += b'\x00'

        seq = self.sequence

        data = struct.pack('BBBB4sIIIII',seq,0,0,0,b'SBPr',
            len(self.name),2048,len(self.entries),len(name_heap),self.parent_id)

        dir_name = self.name+b'\x0d'
        while len(dir_name) % 4 != 0:
            dir_name += b'\x00'

        data += dir_name

        for entry in self.entries:
            data += struct.pack("IIIIIII",
                               entry.loadaddr, entry.execaddr, entry.length,
                               entry.ind_disc_addr, entry.attribs,
                               len(entry.name),
                               heap_lookup[self.entries.index(entry)])

            #check = dir_check_words(data, 7, check)

        data += name_heap

        check = dir_check_words(data, len(data)//4, 0)

        tail = struct.pack('4sBBB',b'oven',seq,0,0)

        check = dir_check_words(tail[0:4], 1, check)
        check = dir_check_bytes(tail[4:7], 3, check)

        check = (check << 0 & 0xff) ^ (check >> 8 & 0xff) ^ (check >> 16 & 0xff) ^ (check >> 24 & 0xff)

        while len(data) < 2040:
            data += b'\x00'

        data += tail + bytes([check])
        return data

    def show(self):
        print(("Directory: {0} ({1})".format(self.name.decode('latin-1'),self.sequence)))
        for entry in self.entries:
            entry.show()

    def add(self, name, loadaddr, execaddr, length, attribs, ind_disc_addr):
        self.entries.append(BigDir.Entry(name, loadaddr, execaddr, length, attribs, ind_disc_addr))

    def __getitem__(self, name):
        for entry in self.entries:
            if entry.name == name:
                return entry

    def delete(self, name):
        for entry in self.entries:
            if entry.name == name:
                self.entries.remove(entry)
                return True

    def find(self, name):
        for entry in self.entries:
            if entry.name.lower() == name.lower():
                return entry

class BootBlock(ctypes.Structure):
    _fields_ = [
        ('defects', ctypes.c_uint32*112),
        ('disc_record',DiscRecord),
        ('non_adfs',ctypes.c_uint8*3),
        ('checksum',ctypes.c_uint8) ]

    def __init__(self, disc_record):
        self.defects[0] = 0x20000000
        self.defects[1] = 0x40000000
        self.disc_record = disc_record
        self.checksum = self.calculate_checksum()

    def calculate_checksum(self):
        checksum = 0
        carry = 0
        for b in bytes(self)[:-1]:
            checksum += b + carry
            carry = 0
            if checksum > 0xff:
                checksum &= 0xff
                carry = 1

        return checksum

