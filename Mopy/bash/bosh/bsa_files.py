# -*- coding: utf-8 -*-
#
# GPL License and Copyright Notice ============================================
#  This file is part of Wrye Bash.
#
#  Wrye Bash is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  Wrye Bash is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Wrye Bash; if not, write to the Free Software Foundation,
#  Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
#  Wrye Bash copyright (C) 2005-2009 Wrye, 2010-2019 Wrye Bash Team
#  https://github.com/wrye-bash
#
# =============================================================================

"""Bsa files.

For the file format see:
http://www.uesp.net/wiki/Tes4Mod:BSA_File_Format
http://www.uesp.net/wiki/Tes5Mod:Archive_File_Format
"""

__author__ = 'Utumno'

import collections
import errno
import os
import struct
import sys
from functools import partial
from itertools import groupby, imap
from operator import itemgetter
from . import AFile
from ..bolt import deprint, Progress, struct_pack, struct_unpack, \
    unpack_byte, unpack_string, unpack_int
from ..exception import BSAError, BSADecodingError, BSAFlagError, \
    BSANotImplemented

_bsa_encoding = 'cp1252' # rumor has it that's the files/folders names encoding
path_sep = u'\\'

# Exceptions ------------------------------------------------------------------

def _decode_path(string_path):
    try:
        return unicode(string_path, encoding=_bsa_encoding)
    except UnicodeDecodeError:
        raise BSADecodingError(string_path)

# Headers ---------------------------------------------------------------------
class _Header(object):
    __slots__ = ('file_id', 'version')
    formats = ['4s', 'I']
    formats = list((f, struct.calcsize(f)) for f in formats)
    bsa_magic = 'BSA\x00'
    bsa_version = int('0x67', 16)

    def load_header(self, ins):
        for fmt, attr in zip(_Header.formats, _Header.__slots__):
            self.__setattr__(attr, struct_unpack(fmt[0], ins.read(fmt[1]))[0])
        # error checking
        if self.file_id != self.__class__.bsa_magic:
            raise BSAError(u'Magic wrong: %r' % self.file_id)

class BsaHeader(_Header):
    __slots__ = ( # in the order encountered in the header
         'folder_records_offset', 'archive_flags', 'folder_count',
         'file_count', 'total_folder_name_length', 'total_file_name_length',
         'file_flags')
    formats = ['I'] * 8
    formats = list((f, struct.calcsize(f)) for f in formats)
    header_size = 36

    def load_header(self, ins):
        super(BsaHeader, self).load_header(ins)
        for fmt, attr in zip(BsaHeader.formats, BsaHeader.__slots__):
            self.__setattr__(attr, struct_unpack(fmt[0], ins.read(fmt[1]))[0])
        # error checking
        if self.folder_records_offset != self.__class__.header_size:
            raise BSAError(u'Header size wrong: %r. Should be %r' % (
                self.folder_records_offset, self.__class__.header_size))
        if not self.has_names_for_folders():
            raise BSAFlagError(u'Bsa has not names for folders', 1)
        if not self.has_names_for_files():
            raise BSAFlagError(u'Bsa has not filename block', 2)

    def has_names_for_folders(self): return self.archive_flags & 1
    def has_names_for_files(self): return self.archive_flags & 2
    def is_compressed(self): return self.archive_flags & 4
    def is_xbox(self): return self.archive_flags & 64

    def embed_filenames(self): return self.archive_flags & 0x100 # TODO Oblivion ?

class Ba2Header(_Header):
    __slots__ = ( # in the order encountered in the header
        'b2a_files_type', 'b2a_num_files', 'b2a_name_table_offset')
    formats = ['4s', 'I', 'Q']
    formats = list((f, struct.calcsize(f)) for f in formats)
    bsa_magic = 'BTDX'
    file_types = {'GNRL', 'DX10'} # GNRL=General, DX10=Textures
    bsa_version = int('0x01', 16)
    header_size = 24

    def load_header(self, ins):
        super(Ba2Header, self).load_header(ins)
        for fmt, attr in zip(Ba2Header.formats, Ba2Header.__slots__):
            self.__setattr__(attr, struct_unpack(fmt[0], ins.read(fmt[1]))[0])
        # error checking
        if not self.b2a_files_type in self.file_types:
            raise BSAError(u'Unrecognised file types: %r. Should be %s' % (
                self.b2a_files_type, u' or'.join(self.file_types)))

class OblivionBsaHeader(BsaHeader):
    __slots__ = ()

    def embed_filenames(self): return False

class SkyrimBsaHeader(BsaHeader):
    __slots__ = ()
    bsa_version = int('0x68', 16)

class SkyrimSeBsaHeader(BsaHeader):
    __slots__ = ()
    bsa_version = int('0x69', 16)

# Records ---------------------------------------------------------------------
class _HashedRecord(object):
    __slots__ = ('record_hash',)
    formats = [('Q', struct.calcsize('Q'))]

    def load_record(self, ins):
        fmt, fmt_siz = _HashedRecord.formats[0]
        self.record_hash, = struct_unpack(fmt, ins.read(fmt_siz))

    def load_record_from_buffer(self, memview, start):
        fmt, fmt_siz = _HashedRecord.formats[0]
        self.record_hash, = struct.unpack_from(fmt, memview, start)
        return start + fmt_siz

    @classmethod
    def total_record_size(cls):
        return _HashedRecord.formats[0][1]

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.record_hash == other.record_hash
        return NotImplemented
    def __ne__(self, other): return not (self == other)
    def __hash__(self): return self.record_hash
    def __lt__(self, other):
        if isinstance(other, self.__class__):
            return self.record_hash < other.record_hash
        return NotImplemented
    def __ge__(self, other): return not (self < other)
    def __gt__(self, other):
        if isinstance(other, self.__class__):
            return self.record_hash > other.record_hash
        return NotImplemented
    def __le__(self, other): return not (self > other)

    def __repr__(self): return repr(hex(self.record_hash))

# BSAs
class _BsaHashedRecord(_HashedRecord):
    __slots__ = ()

    def load_record(self, ins):
        super(_BsaHashedRecord, self).load_record(ins)
        for fmt, attr in zip(self.__class__.formats, self.__class__.__slots__):
            self.__setattr__(attr, struct_unpack(fmt[0], ins.read(fmt[1]))[0])

    def load_record_from_buffer(self, memview, start):
        start = super(_BsaHashedRecord, self).load_record_from_buffer(memview,
                                                                      start)
        for fmt, attr in zip(self.__class__.formats, self.__class__.__slots__):
            self.__setattr__(attr,
                             struct.unpack_from(fmt[0], memview, start)[0])
            start += fmt[1]
        return start

    @classmethod
    def total_record_size(cls):
        return super(_BsaHashedRecord, cls).total_record_size() + sum(
            f[1] for f in cls.formats)

class BSAFolderRecord(_BsaHashedRecord):
    __slots__ = ('files_count', 'file_records_offset')
    formats = ['I', 'I']
    formats = list((f, struct.calcsize(f)) for f in formats)

class BSASkyrimSEFolderRecord(_BsaHashedRecord):
    __slots__ = ('files_count', 'unknown_int', 'file_records_offset')
    formats = ['I', 'I', 'Q']
    formats = list((f, struct.calcsize(f)) for f in formats)

class BSAFileRecord(_BsaHashedRecord):
    __slots__ = ('file_size_flags', 'raw_file_data_offset')
    formats = ['I', 'I']
    formats = list((f, struct.calcsize(f)) for f in formats)

    def compression_toggle(self): return self.file_size_flags & 0x40000000

    def raw_data_size(self):
        if self.compression_toggle():
            return self.file_size_flags & (~0xC0000000) # negate all flags
        return self.file_size_flags

class BSAOblivionFileRecord(_BsaHashedRecord):
    # Note: Here, we (ab)use the usage of zip() in _BsaHashedRecord.load_record
    # to make sure that the last slot, file_pos, is not read from the BSA - we
    # fill it manually in our load_record override. This is necessary to find
    # the positions of hashes for undo_alterations().
    __slots__ = ('file_size_flags', 'raw_file_data_offset', 'file_pos')
    formats = ['I', 'I']
    formats = list((f, struct.calcsize(f)) for f in formats)

    def load_record(self, ins):
        self.file_pos = ins.tell()
        super(BSAOblivionFileRecord, self).load_record(ins)

    def compression_toggle(self): return self.file_size_flags & 0x40000000

    def raw_data_size(self):
        if self.compression_toggle():
            return self.file_size_flags & (~0xC0000000)  # negate all flags
        return self.file_size_flags

# BA2s
class _B2aFileRecordCommon(_HashedRecord):
    __slots__ = ('file_extension', 'dir_hash', )
    formats = ['4s', 'I']
    formats = list((f, struct.calcsize(f)) for f in formats)

    def load_record(self, ins):
        self.record_hash = unpack_int(ins) # record_hash is I not Q !
        for fmt, attr in zip(_B2aFileRecordCommon.formats,
                             _B2aFileRecordCommon.__slots__):
            self.__setattr__(attr, struct_unpack(fmt[0], ins.read(fmt[1]))[0])

    def load_record_from_buffer(self, memview, start):
        start = super(_B2aFileRecordCommon, self).load_record_from_buffer(
            memview, start)
        for fmt, attr in zip(_B2aFileRecordCommon.formats,
                             _B2aFileRecordCommon.__slots__):
            self.__setattr__(attr,
                             struct.unpack_from(fmt[0], memview, start)[0])
            start += fmt[1]
        return start

    @classmethod
    def total_record_size(cls): # unused !
        return super(_B2aFileRecordCommon, cls).total_record_size()  + sum(
            f[1] for f in _B2aFileRecordCommon.formats) + sum(
            f[1] for f in cls.formats)

class B2aFileRecordGeneral(_B2aFileRecordCommon):
    __slots__ = ('unk0C', 'offset', 'packed_size', 'unpacked_size', 'unk20')
    formats = ['I', 'Q'] + ['I'] * 3
    formats = list((f, struct.calcsize(f)) for f in formats)

    def load_record(self, ins):
        super(B2aFileRecordGeneral, self).load_record(ins)
        for fmt, attr in zip(B2aFileRecordGeneral.formats,
                             B2aFileRecordGeneral.__slots__):
            self.__setattr__(attr, struct_unpack(fmt[0], ins.read(fmt[1]))[0])

class B2aFileRecordTexture(_B2aFileRecordCommon):
    __slots__ = ('unk0C', 'num_of_chunks', 'chunk_header_size', 'height',
                 'width', 'num_mips', 'format', 'unk16')
    formats = ['B'] + ['B'] + ['H'] * 3 + ['B'] + ['B'] + ['H']#TODO(ut) verify
    formats = list((f, struct.calcsize(f)) for f in formats)

    def load_record(self, ins):
        super(B2aFileRecordTexture, self).load_record(ins)
        for fmt, attr in zip(B2aFileRecordTexture.formats,
                             B2aFileRecordTexture.__slots__):
            self.__setattr__(attr, struct_unpack(fmt[0], ins.read(fmt[1]))[0])

# Bsa content abstraction -----------------------------------------------------
class BSAFolder(object):
    """:type folder_assets: collections.OrderedDict[unicode, BSAFileRecord]"""

    def __init__(self, folder_record):
        self.folder_record = folder_record
        self.folder_assets = collections.OrderedDict() # keep files order

class Ba2Folder(object):

    def __init__(self):
        self.folder_assets = collections.OrderedDict() # keep files order

# Files -----------------------------------------------------------------------
def _makedirs_exists_ok(target_dir):
    try:
        os.makedirs(target_dir)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

class ABsa(AFile):
    """:type bsa_folders: collections.OrderedDict[unicode, BSAFolder]"""
    header_type = BsaHeader
    _assets = frozenset()

    def __init__(self, fullpath, load_cache=False, names_only=True):
        super(ABsa, self).__init__(fullpath)
        self.bsa_header = self.__class__.header_type()
        self.bsa_folders = collections.OrderedDict() # keep folder order
        self._filenames = []
        self.total_names_length = 0 # reported wrongly at times - calculate it
        if load_cache: self.__load(names_only)

    def __load(self, names_only):
        try:
            if not names_only:
                self._load_bsa()
            else:
                self._load_bsa_light()
        except struct.error as e:
            raise BSAError, e.message, sys.exc_info()[2]

    @staticmethod
    def _map_files_to_folders(asset_paths): # lowercase keys and values
        folder_file = []
        for a in asset_paths:
            split = a.rsplit(path_sep, 1)
            if len(split) == 1:
                split = [u'', split[0]]
            folder_file.append(split)
        # group files by folder
        folder_files_dict = {}
        folder_file.sort(key=itemgetter(0)) # sort first then group
        for key, val in groupby(folder_file, key=itemgetter(0)):
            folder_files_dict[key.lower()] = set(dest.lower() for _key, dest in val)
        return folder_files_dict

    def extract_assets(self, asset_paths, dest_folder):
        folder_files_dict = self._map_files_to_folders(
            imap(unicode.lower, asset_paths))
        del asset_paths # forget about this
        # load the bsa - this should be reworked to load only needed records
        self._load_bsa()
        folder_to_assets = self._map_assets_to_folders(folder_files_dict)
        # unload the bsa
        self.bsa_folders.clear()
        # get the data from the file
        global_compression = self.bsa_header.is_compressed()
        with open(u'%s' % self.abs_path, 'rb') as bsa_file:
            for folder, file_records in folder_to_assets.iteritems():
                target_dir = os.path.join(dest_folder, folder)
                _makedirs_exists_ok(target_dir)
                for filename, record in file_records:
                    if global_compression ^ record.compression_toggle():
                        raise BSANotImplemented(
                            u'Compressed records are not yet supported (%s)' %
                            self.abs_path)
                    data_size = record.raw_data_size()
                    bsa_file.seek(record.raw_file_data_offset)
                    if self.bsa_header.embed_filenames(): # use len(filename) ?
                        filename_len = unpack_byte(bsa_file)
                        bsa_file.read(filename_len) # discard filename
                        data_size -= filename_len + 1
                    # get the data!
                    raw_data = bsa_file.read(data_size)
                    with open(os.path.join(target_dir, filename), 'wb') as out:
                        out.write(raw_data)

    def _map_assets_to_folders(self, folder_files_dict):
        folder_to_assets = collections.OrderedDict()
        for folder_path, bsa_folder in self.bsa_folders.iteritems():
            if folder_path.lower() not in folder_files_dict: continue
            # Has assets we need to extract. Keep order to avoid seeking
            # back and forth in the file
            folder_to_assets[folder_path] = file_records = []
            filenames = folder_files_dict[folder_path.lower()]
            for filename, filerecord in bsa_folder.folder_assets.iteritems():
                if filename.lower() not in filenames: continue
                file_records.append((filename, filerecord))
        return folder_to_assets

    # Abstract
    def _load_bsa(self): raise NotImplementedError
    def _load_bsa_light(self): raise NotImplementedError

    # API - delegates to abstract methods above
    def has_assets(self, asset_paths):
        return set(a.cs for a in asset_paths) & self.assets

    @property
    def assets(self):
        """Set of full paths in the bsa in lowercase.
        :rtype: frozenset[unicode]
        """
        if self._assets is self.__class__._assets:
            self.__load(names_only=True)
            self._assets = frozenset(imap(os.path.normcase, self._filenames))
            del self._filenames
        return self._assets

class BSA(ABsa):
    """Bsa file. Notes:
    - We assume that has_names_for_files() is True, although we allow for
    has_names_for_folders() to be False (untested).
    - consider using the filenames from data block in load_light, if they
    are embedded."""
    file_record_type = BSAFileRecord
    folder_record_type = BSAFolderRecord

    def _load_bsa(self):
        folder_records = [] # we need those to parse the folder names
        self.bsa_folders.clear()
        file_records = []
        read_file_record = partial(self._read_file_records, file_records,
                                   folders=self.bsa_folders)
        file_names = self._read_bsa_file(folder_records, read_file_record)
        names_record_index = file_records_index = 0
        for folder_path, bsa_folder in self.bsa_folders.iteritems():
            for __ in xrange(bsa_folder.folder_record.files_count):
                rec = file_records[file_records_index]
                file_records_index += 1
                filename = _decode_path(file_names[names_record_index])
                names_record_index += 1
                bsa_folder.folder_assets[filename] = rec

    @classmethod
    def _read_file_records(cls, file_records, bsa_file, folder_path,
                           folder_record, folders=None):
        folders[folder_path] = BSAFolder(folder_record)
        for __ in xrange(folder_record.files_count):
            rec = cls.file_record_type()
            rec.load_record(bsa_file)
            file_records.append(rec)

    def _load_bsa_light(self):
        folder_records = [] # we need those to parse the folder names
        _filenames = []
        path_folder_record = collections.OrderedDict()
        read_file_record = partial(self._discard_file_records,
                                   folders=path_folder_record)
        file_names = self._read_bsa_file(folder_records, read_file_record)
        names_record_index = 0
        for folder_path, folder_record in path_folder_record.iteritems():
            for __ in xrange(folder_record.files_count):
                filename = _decode_path(file_names[names_record_index])
                _filenames.append(path_sep.join((folder_path, filename)))
                names_record_index += 1
        self._filenames = _filenames

    def _read_bsa_file(self, folder_records, read_file_records):
        total_names_length = 0
        with open(u'%s' % self.abs_path, 'rb') as bsa_file: # accept string or Path
            # load the header from input stream
            self.bsa_header.load_header(bsa_file)
            # load the folder records from input stream
            for __ in xrange(self.bsa_header.folder_count):
                rec = self.__class__.folder_record_type()
                rec.load_record(bsa_file)
                folder_records.append(rec)
            # load the file record block
            for folder_record in folder_records:
                folder_path = u'?%d' % folder_record.record_hash # hack - untested
                if self.bsa_header.has_names_for_folders():
                    name_size = unpack_byte(bsa_file)
                    folder_path = _decode_path(
                        unpack_string(bsa_file, name_size - 1))
                    total_names_length += name_size
                    bsa_file.read(1) # discard null terminator
                read_file_records(bsa_file, folder_path, folder_record)
            if total_names_length != self.bsa_header.total_folder_name_length:
                deprint(u'%s reports wrong folder names length %d'
                    u' - actual: %d (number of folders is %d)' % (
                    self.abs_path, self.bsa_header.total_folder_name_length,
                    total_names_length, self.bsa_header.folder_count))
            self.total_names_length = total_names_length
            file_names = bsa_file.read( # has an empty string at the end
                self.bsa_header.total_file_name_length).split('\00')
            # close the file
        return file_names

    def _discard_file_records(self, bsa_file, folder_path, folder_record,
                              folders=None):
        bsa_file.read(folder_record.files_count *
            self.file_record_type.total_record_size())
        folders[folder_path] = folder_record

class BA2(ABsa):
    header_type = Ba2Header

    def extract_assets(self, asset_paths, dest_folder):
        # map files to folders
        folder_files_dict = self._map_files_to_folders(asset_paths)
        del asset_paths # forget about this
        # load the bsa - this should be reworked to load only needed records
        self._load_bsa()
        if self.bsa_header.b2a_files_type != 'GNRL':
            raise BSANotImplemented(
                u'Texture ba2 archives are not yet supported')
        folder_to_assets = self._map_assets_to_folders(folder_files_dict)
        # unload the bsa
        self.bsa_folders.clear()
        # get the data from the file
        with open(u'%s' % self.abs_path, 'rb') as bsa_file:
            for folder, file_records in folder_to_assets.iteritems():
                target_dir = os.path.join(dest_folder, folder)
                _makedirs_exists_ok(target_dir)
                for filename, record in file_records:
                    if record.packed_size: # seems to signify compression
                        raise BSANotImplemented(
                            u'Compressed records are not yet supported (%s)' %
                            self.abs_path)
                    data_size = record.unpacked_size
                    bsa_file.seek(record.offset)
                    # get the data!
                    raw_data = bsa_file.read(data_size)
                    with open(os.path.join(target_dir, filename), 'wb') as out:
                        out.write(raw_data)

    def _load_bsa(self):
        with open(u'%s' % self.abs_path, 'rb') as bsa_file:
            # load the header from input stream
            self.bsa_header.load_header(bsa_file)
            # load the folder records from input stream
            if self.bsa_header.b2a_files_type == 'GNRL':
                file_record_type = B2aFileRecordGeneral
            else:
                file_record_type = B2aFileRecordTexture
            file_records = []
            for __ in xrange(self.bsa_header.b2a_num_files):
                rec = file_record_type()
                rec.load_record(bsa_file)
                file_records.append(rec)
            # load the file names block
            bsa_file.seek(self.bsa_header.b2a_name_table_offset)
            file_names_block = memoryview(bsa_file.read())
            # close the file
        current_folder_name = current_folder = None
        for index in xrange(self.bsa_header.b2a_num_files):
            name_size = struct.unpack_from('H', file_names_block)[0]
            filename = _decode_path(
                file_names_block[2:name_size + 2].tobytes())
            file_names_block = file_names_block[name_size + 2:]
            folder_dex = filename.rfind(u'\\')
            if folder_dex == -1:
                folder_name = u''
            else:
                folder_name = filename[:folder_dex]
            if current_folder_name != folder_name:
                current_folder = self.bsa_folders.setdefault(folder_name,
                                                             Ba2Folder())
                current_folder_name = folder_name
            current_folder.folder_assets[filename[folder_dex + 1:]] = \
                file_records[index]

    def _load_bsa_light(self):
        with open(u'%s' % self.abs_path, 'rb') as bsa_file:
            # load the header from input stream
            self.bsa_header.load_header(bsa_file)
            # load the file names block
            bsa_file.seek(self.bsa_header.b2a_name_table_offset)
            file_names_block = memoryview(bsa_file.read())
            # close the file
        _filenames = []
        for index in xrange(self.bsa_header.b2a_num_files):
            name_size = struct.unpack_from('H', file_names_block)[0]
            filename = _decode_path(
                file_names_block[2:name_size + 2].tobytes())
            _filenames.append(filename)
            file_names_block = file_names_block[name_size + 2:]
        self._filenames = _filenames

class OblivionBsa(BSA):
    header_type = OblivionBsaHeader
    file_record_type = BSAOblivionFileRecord
    # A dictionary mapping file extensions to hash components. Used by Oblivion
    # when hashing file names for its BSAs.
    _bsa_ext_lookup = collections.defaultdict(int)
    for ext, hash_part in [('.kf', 0x80), ('.nif', 0x8000), ('.dds', 0x8080),
                           ('.wav', 0x80000000)]:
        _bsa_ext_lookup[ext] = hash_part

    @staticmethod
    def calculate_hash(file_name):
        """Calculates the hash used by Oblivion BSAs for the provided file
        name.
        Based on Timeslips code with cleanup and pythonization.

        See here for more information:
        https://en.uesp.net/wiki/Tes4Mod:Hash_Calculation"""
        #--NOTE: fileName is NOT a Path object!
        root, ext = os.path.splitext(file_name.lower())
        chars = map(ord, root)
        hash_part_1 = chars[-1] | ((len(chars) > 2 and chars[-2]) or 0) << 8 \
                      | len(chars) << 16 | chars[0] << 24
        hash_part_1 |= OblivionBsa._bsa_ext_lookup[ext]
        uint_mask, hash_part_2, hash_part_3 = 0xFFFFFFFF, 0, 0
        for char in chars[1:-2]:
            hash_part_2 = ((hash_part_2 * 0x1003F) + char) & uint_mask
        for char in map(ord, ext):
            hash_part_3 = ((hash_part_3 * 0x1003F) + char) & uint_mask
        hash_part_2 = (hash_part_2 + hash_part_3) & uint_mask
        return (hash_part_2 << 32) + hash_part_1

    def undo_alterations(self, progress=Progress()):
        """Undoes any alterations that previously applied BSA Alteration may
        have done to this BSA by recalculating all mismatched hashes.

        NOTE: In order for this method to do anything, the BSA must be fully
        loaded - that means you must either pass load_cache=True and
        names_only=False to the constructor, or call _load_bsa() (NOT
        _load_bsa_light() !) before calling this method.

        See this link for an in-depth overview of BSA Alteration and the
        problem it tries to solve:
        http://devnull.sweetdanger.com/archiveinvalidation.html

        :param progress: The progress indicator to use for this process."""
        progress.setFull(self.bsa_header.folder_count)
        with open(self.abs_path.s, 'r+b') as bsa_file:
            reset_count = 0
            for folder_name, folder in self.bsa_folders.iteritems():
                for file_name, file_info in folder.folder_assets.iteritems():
                    rebuilt_hash = self.calculate_hash(file_name)
                    if file_info.record_hash != rebuilt_hash:
                        bsa_file.seek(file_info.file_pos)
                        bsa_file.write(struct_pack('Q', rebuilt_hash))
                        reset_count += 1
                progress(progress.state + 1, u'Rebuilding Hashes...\n' +
                         folder_name)
        return reset_count

class SkyrimBsa(BSA):
    header_type = SkyrimBsaHeader

class SkyrimSeBsa(BSA):
    header_type = SkyrimSeBsaHeader
    folder_record_type = BSASkyrimSEFolderRecord

class Fallout4Ba2(BA2): pass

# Factory
def get_bsa_type(game_fsName):
    """:rtype: type"""
    if game_fsName == u'Oblivion':
        return OblivionBsa
    elif game_fsName in (u'Enderal', u'Fallout3', u'FalloutNV', u'Skyrim'):
        return SkyrimBsa
    elif game_fsName in (u'Skyrim Special Edition', u'Skyrim VR'):
        return SkyrimSeBsa
    elif game_fsName in (u'Fallout4', u'Fallout4VR'):
        return Fallout4Ba2
