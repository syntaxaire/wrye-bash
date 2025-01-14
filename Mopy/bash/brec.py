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

"""This module contains all of the basic types used to read ESP/ESM mod files.
"""
import StringIO
import cPickle
import copy
import os
import re
import struct
import zlib
from operator import attrgetter

import bolt
import exception
from bass import null1
from bolt import decode, encode, sio, GPath, struct_pack, struct_unpack

# Util Functions --------------------------------------------------------------
#--Type coercion
def _coerce(value, newtype, base=None, AllowNone=False):
    try:
        if newtype is float:
            #--Force standard precision
            return round(struct_unpack('f', struct_pack('f', float(value)))[0], 6)
        elif newtype is bool:
            if isinstance(value,basestring):
                retValue = value.strip().lower()
                if AllowNone and retValue == u'none': return None
                return retValue not in (u'',u'none',u'false',u'no',u'0',u'0.0')
            else: return bool(value)
        elif base: retValue = newtype(value, base)
        elif newtype is unicode: retValue = decode(value)
        else: retValue = newtype(value)
        if (AllowNone and
            (isinstance(retValue,str) and retValue.lower() == 'none') or
            (isinstance(retValue,unicode) and retValue.lower() == u'none')
            ):
            return None
        return retValue
    except (ValueError,TypeError):
        if newtype is int: return 0
        return None

#--Reference (fid)
def strFid(fid):
    """Returns a string representation of the fid."""
    if isinstance(fid,tuple):
        return u'(%s,0x%06X)' % (fid[0].s,fid[1])
    else:
        return u'%08X' % fid

def genFid(modIndex,objectIndex):
    """Generates a fid from modIndex and ObjectIndex."""
    return long(objectIndex) | (long(modIndex) << 24)

def getModIndex(fid):
    """Returns the modIndex portion of a fid."""
    return int(fid >> 24)

def getObjectIndex(fid):
    """Returns the objectIndex portion of a fid."""
    return int(fid & 0x00FFFFFFL)

def getFormIndices(fid):
    """Returns tuple of modIndex and ObjectIndex of fid."""
    return int(fid >> 24),int(fid & 0x00FFFFFFL)

# Mod I/O ---------------------------------------------------------------------
#------------------------------------------------------------------------------
class RecordHeader(object):
    """Pack or unpack the record's header."""
    rec_header_size = 24 # Record header size, 20 (Oblivion), 24 (other games)
    # Record pack format, 4sIIII (Oblivion), 4sIIIII (other games)
    # Given as a list here, where each string matches one subrecord in the
    # header. See rec_pack_format_str below as well.
    rec_pack_format = ['=4s', 'I', 'I', 'I', 'I', 'I']
    # rec_pack_format as a format string. Use for pack / unpack calls.
    rec_pack_format_str = ''.join(rec_pack_format)
    # http://en.uesp.net/wiki/Tes5Mod:Mod_File_Format#Groups
    pack_formats = {0: '=4sI4s3I'} # Top Type
    pack_formats.update({x: '=4s5I' for x in {1, 6, 7, 8, 9, 10}}) # Children
    pack_formats.update({x: '=4sIi3I' for x in {2, 3}})  # Interior Cell Blocks
    pack_formats.update({x: '=4sIhh3I' for x in {4, 5}}) # Exterior Cell Blocks

    #--Top types in order of the main ESM
    topTypes = []
    #--Record Types: all recognized record types (not just the top types)
    recordTypes = set()
    #--Plugin form version, we must pack this in the TES4 header
    plugin_form_version = 0

    def __init__(self, recType='TES4', size=0, arg1=0, arg2=0, arg3=0, arg4=0):
        """RecordHeader defining different sets of attributes based on recType
        is a huge smell and must be fixed. The fact that Oblivion has different
        unpack formats than other games adds to complexity - we need a proper
        class or better add __slots__ and iterate over them in pack. Both
        issues should be fixed at once.
        :param recType: signature of record
                      : For GRUP this is always GRUP
                      : For Records this will be TES4, GMST, KYWD, etc
        :param size : size of current record, not entire file
        :param arg1 : For GRUP type of records to follow, GMST, KYWD, etc
                    : For Records this is the record flags
        :param arg2 : For GRUP Group Type 0 to 10 see UESP Wiki
                    : Record FormID, TES4 records have FormID of 0
        :param arg3 : For GRUP 2h, possible time stamp, unknown
                    : Record possible version control in CK
        :param arg4 : For GRUP 0 for known mods (2h, form_version, unknown ?)
                    : For Records 2h, form_version, unknown
        """
        self.recType = recType
        self.size = size
        if self.recType == 'GRUP':
            self.label = arg1
            self.groupType = arg2
            self.stamp = arg3
        else:
            self.flags1 = arg1
            self.fid = arg2
            self.flags2 = arg3
        self.extra = arg4

    @staticmethod
    def unpack(ins):
        """Return a RecordHeader object by reading the input stream.
        Format must be either '=4s4I' 20 bytes for Oblivion or '=4s5I' 24
        bytes for rest of games."""
        # args = rec_type, size, uint0, uint1, uint2[, uint3]
        args = ins.unpack(RecordHeader.rec_pack_format_str,
                          RecordHeader.rec_header_size, 'REC_HEADER')
        #--Bad type?
        rec_type = args[0]
        if rec_type not in RecordHeader.recordTypes:
            raise exception.ModError(ins.inName,
                                     u'Bad header type: ' + repr(rec_type))
        #--Record
        if rec_type != 'GRUP':
            pass
        #--Top Group
        elif args[3] == 0: #groupType == 0 (Top Type)
            args = list(args)
            str0 = struct_pack('I', args[2])
            if str0 in RecordHeader.topTypes:
                args[2] = str0
            else:
                raise exception.ModError(ins.inName,
                                         u'Bad Top GRUP type: ' + repr(str0))
        return RecordHeader(*args)

    def pack(self):
        """Return the record header packed into a bitstream to be written to
        file. We decide what kind of GRUP we have based on the type of
        label, hacky but to redo this we must revisit records code."""
        if self.recType == 'GRUP':
            if isinstance(self.label, str):
                pack_args = [RecordHeader.pack_formats[0], self.recType,
                             self.size, self.label, self.groupType, self.stamp]
            elif isinstance(self.label, tuple):
                pack_args = [RecordHeader.pack_formats[4], self.recType,
                             self.size, self.label[0], self.label[1],
                             self.groupType, self.stamp]
            else:
                pack_args = [RecordHeader.pack_formats[1], self.recType,
                             self.size, self.label, self.groupType, self.stamp]
            if RecordHeader.plugin_form_version:
                pack_args.append(self.extra)
        else:
            pack_args = [RecordHeader.rec_pack_format_str, self.recType,
                         self.size, self.flags1, self.fid, self.flags2]
            if RecordHeader.plugin_form_version:
                extra1, extra2 = struct_unpack('=2h',
                                               struct_pack('=I', self.extra))
                extra1 = RecordHeader.plugin_form_version
                self.extra = \
                    struct_unpack('=I', struct_pack('=2h', extra1, extra2))[0]
                pack_args.append(self.extra)
        return struct_pack(*pack_args)

    @property
    def form_version(self):
        if self.plugin_form_version == 0 : return 0
        return struct_unpack('=2h', struct_pack('=I', self.extra))[0]

#------------------------------------------------------------------------------
class ModReader:
    """Wrapper around a TES4 file in read mode.
    Will throw a ModReaderror if read operation fails to return correct size.

    **ModReader.recHeader must be set to the game's specific RecordHeader
      class type, for ModReader to use.**
    """
    recHeader = RecordHeader

    def __init__(self,inName,ins):
        """Initialize."""
        self.inName = inName
        self.ins = ins
        #--Get ins size
        curPos = ins.tell()
        ins.seek(0,os.SEEK_END)
        self.size = ins.tell()
        ins.seek(curPos)
        self.strings = {}
        self.hasStrings = False

    # with statement
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_value, exc_traceback): self.ins.close()

    def setStringTable(self,table={}):
        if table is None:
            self.hasStrings = False
            self.strings = {}
        else:
            self.hasStrings = True
            self.strings = table

    #--I/O Stream -----------------------------------------
    def seek(self,offset,whence=os.SEEK_SET,recType='----'):
        """File seek."""
        if whence == os.SEEK_CUR:
            newPos = self.ins.tell() + offset
        elif whence == os.SEEK_END:
            newPos = self.size + offset
        else:
            newPos = offset
        if newPos < 0 or newPos > self.size:
            raise exception.ModReadError(self.inName, recType, newPos, self.size)
        self.ins.seek(offset,whence)

    def tell(self):
        """File tell."""
        return self.ins.tell()

    def close(self):
        """Close file."""
        self.ins.close()

    def atEnd(self,endPos=-1,recType='----'):
        """Return True if current read position is at EOF."""
        filePos = self.ins.tell()
        if endPos == -1:
            return filePos == self.size
        elif filePos > endPos:
            raise exception.ModError(self.inName, u'Exceeded limit of: ' + recType)
        else:
            return filePos == endPos

    #--Read/Unpack ----------------------------------------
    def read(self,size,recType='----'):
        """Read from file."""
        endPos = self.ins.tell() + size
        if endPos > self.size:
            raise exception.ModSizeError(self.inName, recType, endPos, self.size)
        return self.ins.read(size)

    def readLString(self,size,recType='----'):
        """Read translatible string.  If the mod has STRINGS file, this is a
        uint32 to lookup the string in the string table.  Otherwise, this is a
        zero-terminated string."""
        if self.hasStrings:
            if size != 4:
                endPos = self.ins.tell() + size
                raise exception.ModReadError(self.inName, recType, endPos, self.size)
            id_, = self.unpack('I',4,recType)
            if id_ == 0: return u''
            else: return self.strings.get(id_,u'LOOKUP FAILED!') #--Same as Skyrim
        else:
            return self.readString(size,recType)

    def readString16(self, recType='----'):
        """Read wide pascal string: uint16 is used to indicate length."""
        strLen, = self.unpack('H',2,recType)
        return self.readString(strLen,recType)

    def readString32(self, recType='----'):
        """Read wide pascal string: uint32 is used to indicate length."""
        strLen, = self.unpack('I',4,recType)
        return self.readString(strLen,recType)

    def readString(self,size,recType='----'):
        """Read string from file, stripping zero terminator."""
        return u'\n'.join(decode(x,bolt.pluginEncoding,avoidEncodings=('utf8','utf-8')) for x in
                          bolt.cstrip(self.read(size,recType)).split('\n'))

    def readStrings(self,size,recType='----'):
        """Read strings from file, stripping zero terminator."""
        return [decode(x,bolt.pluginEncoding,avoidEncodings=('utf8','utf-8')) for x in
                self.read(size,recType).rstrip(null1).split(null1)]

    def unpack(self,format,size,recType='----'):
        """Read file and unpack according to struct format."""
        endPos = self.ins.tell() + size
        if endPos > self.size:
            raise exception.ModReadError(self.inName, recType, endPos, self.size)
        return struct_unpack(format, self.ins.read(size))

    def unpackRef(self):
        """Read a ref (fid)."""
        return self.unpack('I',4)[0]

    def unpackRecHeader(self): return ModReader.recHeader.unpack(self)

    def unpackSubHeader(self,recType='----',expType=None,expSize=0):
        """Unpack a subrecord header.  Optionally checks for match with expected
        type and size."""
        selfUnpack = self.unpack
        (rec_type, size) = selfUnpack('4sH', 6, recType + '.SUB_HEAD')
        #--Extended storage?
        while rec_type == 'XXXX':
            size = selfUnpack('I',4,recType+'.XXXX.SIZE.')[0]
            rec_type = selfUnpack('4sH', 6, recType + '.XXXX.TYPE')[0] #--Throw away size (always == 0)
        #--Match expected name?
        if expType and expType != rec_type:
            raise exception.ModError(self.inName, u'%s: Expected %s subrecord, but '
                           u'found %s instead.' % (recType, expType, rec_type))
        #--Match expected size?
        if expSize and expSize != size:
            raise exception.ModSizeError(self.inName, recType + '.' + rec_type, size,
                                         expSize, True)
        return rec_type,size

    #--Find data ------------------------------------------
    def findSubRecord(self,subType,recType='----'):
        """Finds subrecord with specified type."""
        atEnd = self.atEnd
        self_unpack = self.unpack
        seek = self.seek
        while not atEnd():
            (sub_type_,sub_rec_size) = self_unpack('4sH',6,recType+'.SUB_HEAD')
            if sub_type_ == subType:
                return self.read(sub_rec_size,recType+'.'+subType)
            else:
                seek(sub_rec_size,1,recType+'.'+sub_type_)
        #--Didn't find it?
        else:
            return None

#------------------------------------------------------------------------------
class ModWriter:
    """Wrapper around a TES4 output stream.  Adds utility functions."""
    def __init__(self,out):
        """Initialize."""
        self.out = out

    # with statement
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_value, exc_traceback): self.out.close()

    #--Stream Wrapping ------------------------------------
    def write(self,data): self.out.write(data)
    def tell(self): return self.out.tell()
    def seek(self,offset,whence=os.SEEK_SET): return self.out.seek(offset,whence)
    def getvalue(self): return self.out.getvalue()
    def close(self): self.out.close()

    #--Additional functions -------------------------------
    def pack(self,format,*data):
        self.out.write(struct_pack(format, *data))

    def packSub(self, sub_rec_type, data, *values):
        """Write subrecord header and data to output stream.
        Call using either packSub(sub_rec_type,data) or
        packSub(sub_rec_type,format,values).
        Will automatically add a prefacing XXXX size subrecord to handle data
        with size > 0xFFFF."""
        try:
            if data is None: return
            if values: data = struct_pack(data, *values)
            outWrite = self.out.write
            lenData = len(data)
            if lenData <= 0xFFFF:
                outWrite(struct_pack('=4sH', sub_rec_type, lenData))
            else:
                outWrite(struct_pack('=4sHI', 'XXXX', 4, lenData))
                outWrite(struct_pack('=4sH', sub_rec_type, 0))
            outWrite(data)
        except Exception as e:
            print e
            print self,sub_rec_type,data,values

    def packSub0(self, sub_rec_type, data):
        """Write subrecord header plus zero terminated string to output
        stream."""
        if data is None: return
        elif isinstance(data,unicode):
            data = encode(data,firstEncoding=bolt.pluginEncoding)
        lenData = len(data) + 1
        outWrite = self.out.write
        if lenData < 0xFFFF:
            outWrite(struct_pack('=4sH', sub_rec_type, lenData))
        else:
            outWrite(struct_pack('=4sHI', 'XXXX', 4, lenData))
            outWrite(struct_pack('=4sH', sub_rec_type, 0))
        outWrite(data)
        outWrite('\x00')

    def packRef(self, sub_rec_type, fid):
        """Write subrecord header and fid reference."""
        if fid is not None:
            self.out.write(struct_pack('=4sHI', sub_rec_type, 4, fid))

    def writeGroup(self,size,label,groupType,stamp):
        if type(label) is str:
            self.pack('=4sI4sII','GRUP',size,label,groupType,stamp)
        elif type(label) is tuple:
            self.pack('=4sIhhII','GRUP',size,label[1],label[0],groupType,stamp)
        else:
            self.pack('=4s4I','GRUP',size,label,groupType,stamp)

    def write_string(self, sub_type, string_val, max_size=0,
                     preferred_encoding=None):
        """Writes out a string subrecord, properly encoding it beforehand and
        respecting max_size and preferred_encoding if they are set."""
        preferred_encoding = preferred_encoding or bolt.pluginEncoding
        if max_size:
            string_val = bolt.winNewLines(string_val.rstrip())
            truncated_size = min(max_size, len(string_val))
            test, tested_encoding = encode(string_val,
                                           firstEncoding=preferred_encoding,
                                           returnEncoding=True)
            extra_encoded = len(test) - max_size
            if extra_encoded > 0:
                total = 0
                i = -1
                while total < extra_encoded:
                    total += len(string_val[i].encode(tested_encoding))
                    i -= 1
                truncated_size += i + 1
                string_val = string_val[:truncated_size]
                string_val = encode(string_val, firstEncoding=tested_encoding)
            else:
                string_val = test
        else:
            string_val = encode(string_val, firstEncoding=preferred_encoding)
        self.packSub0(sub_type, string_val)

# Mod Record Elements ---------------------------------------------------------
#------------------------------------------------------------------------------
# Constants
FID = 'FID' #--Used by MelStruct classes to indicate fid elements.

#------------------------------------------------------------------------------
class MelObject(object):
    """An empty class used by group and structure elements for data storage."""
    def __eq__(self,other):
        """Operator: =="""
        return isinstance(other,MelObject) and self.__dict__ == other.__dict__

    def __ne__(self,other):
        """Operator: !="""
        return not isinstance(other,MelObject) or self.__dict__ != other.__dict__

#-----------------------------------------------------------------------------
class MelBase:
    """Represents a mod record raw element. Typically used for unknown elements.
    Also used as parent class for other element types."""

    def __init__(self, subType, attr, default=None):
        """Initialize."""
        self.subType, self.attr, self.default = subType, attr, default
        self._debug = False

    def debug(self,on=True):
        """Sets debug flag on self."""
        self._debug = on
        return self

    def getSlotsUsed(self):
        return self.attr,

    @staticmethod
    def parseElements(*elements):
        """Parses elements and returns attrs,defaults,actions,formAttrs where:
        * attrs is tuple of attributes (names)
        * formAttrs is tuple of attributes that have fids,
        * defaults is tuple of default values for attributes
        * actions is tuple of callables to be used when loading data
        Note that each element of defaults and actions matches corresponding attr element.
        Used by struct subclasses.

        Example call:
        parseElements('level', ('unused1', null2), (FID, 'listId', None),
                      ('count', 1), ('unused2', null2))
        """
        formAttrs = []
        lenEls = len(elements)
        attrs,defaults,actions = [0]*lenEls,[0]*lenEls,[0]*lenEls
        formAttrsAppend = formAttrs.append
        for index,element in enumerate(elements):
            if not isinstance(element,tuple): element = (element,)
            el_0 = element[0]
            attrIndex = el_0 == 0
            if el_0 == FID:
                formAttrsAppend(element[1])
                attrIndex = 1
            elif callable(el_0):
                actions[index] = el_0
                attrIndex = 1
            attrs[index] = element[attrIndex]
            if len(element) - attrIndex == 2:
                defaults[index] = element[-1] # else leave to 0
        return map(tuple,(attrs,defaults,actions,formAttrs))

    def getDefaulters(self,defaulters,base):
        """Registers self as a getDefault(attr) provider."""
        pass

    def getLoaders(self,loaders):
        """Adds self as loader for type."""
        loaders[self.subType] = self

    def hasFids(self,formElements):
        """Include self if has fids."""
        pass

    def setDefault(self,record):
        """Sets default value for record instance."""
        record.__setattr__(self.attr,self.default)

    def loadData(self, record, ins, sub_type, size_, readId):
        """Reads data from ins into record attribute."""
        record.__setattr__(self.attr, ins.read(size_, readId))
        if self._debug: print u'%s' % record.__getattribute__(self.attr)

    def dumpData(self,record,out):
        """Dumps data from record to outstream."""
        value = record.__getattribute__(self.attr)
        if value is not None: out.packSub(self.subType,value)

    def mapFids(self,record,function,save=False):
        """Applies function to fids. If save is True, then fid is set
        to result of function."""
        raise exception.AbstractError

#------------------------------------------------------------------------------
class MelFid(MelBase):
    """Represents a mod record fid element."""

    def hasFids(self,formElements):
        """Include self if has fids."""
        formElements.add(self)

    def loadData(self, record, ins, sub_type, size_, readId):
        """Reads data from ins into record attribute."""
        record.__setattr__(self.attr,ins.unpackRef())
        if self._debug: print u'  %08X' % (record.__getattribute__(self.attr),)

    def dumpData(self,record,out):
        """Dumps data from record to outstream."""
        try:
            value = record.__getattribute__(self.attr)
        except AttributeError:
            value = None
        if value is not None: out.packRef(self.subType,value)

    def mapFids(self,record,function,save=False):
        """Applies function to fids. If save is true, then fid is set
        to result of function."""
        attr = self.attr
        try:
            fid = record.__getattribute__(attr)
        except AttributeError:
            fid = None
        result = function(fid)
        if save: record.__setattr__(attr,result)

#------------------------------------------------------------------------------
class MelFids(MelBase):
    """Represents a mod record fid elements."""

    def hasFids(self,formElements):
        """Include self if has fids."""
        formElements.add(self)

    def setDefault(self,record):
        """Sets default value for record instance."""
        record.__setattr__(self.attr,[])

    def loadData(self, record, ins, sub_type, size_, readId):
        """Reads data from ins into record attribute."""
        fid = ins.unpackRef()
        record.__getattribute__(self.attr).append(fid)
        if self._debug: print u' ',hex(fid)

    def dumpData(self,record,out):
        """Dumps data from record to outstream."""
        type = self.subType
        outPackRef = out.packRef
        for fid in record.__getattribute__(self.attr):
            outPackRef(type,fid)

    def mapFids(self,record,function,save=False):
        """Applies function to fids. If save is true, then fid is set
        to result of function."""
        fids = record.__getattribute__(self.attr)
        for index,fid in enumerate(fids):
            result = function(fid)
            if save: fids[index] = result

#------------------------------------------------------------------------------
class MelNull(MelBase):
    """Represents an obsolete record. Reads bytes from instream, but then
    discards them and is otherwise inactive."""

    def __init__(self, subType):
        """Initialize."""
        self.subType = subType
        self._debug = False

    def getSlotsUsed(self):
        return ()

    def setDefault(self,record):
        """Sets default value for record instance."""
        pass

    def loadData(self, record, ins, sub_type, size_, readId):
        """Reads data from ins into record attribute."""
        junk = ins.read(size_, readId)
        if self._debug: print u' ',record.fid,unicode(junk)

    def dumpData(self,record,out):
        """Dumps data from record to outstream."""
        pass

#------------------------------------------------------------------------------
class MelCountedFids(MelFids):
    """Handle writing out a preceding 'count' subrecord for Fid subrecords.
       For example, SPCT holds an int telling how  many SPLO subrecord there
       are."""

    # Used to ignore the count record on loading.  Writing is handled by dumpData
    # In the SPCT/SPLO example, the NullLoader will handle "reading" the SPCT
    # subrecord, where "reading" = ignoring
    NullLoader = MelNull('ANY')

    def __init__(self, countedType, attr, counterType, counterFormat='<I', default=None):
        # In the SPCT/SPLO example, countedType is SPLO, counterType is SPCT
        MelFids.__init__(self, countedType, attr, default)
        self.counterType = counterType
        self.counterFormat = counterFormat

    def getLoaders(self, loaders):
        """Register loaders for both the counted and counter subrecords"""
        # Counted
        MelFids.getLoaders(self, loaders)
        # Counter
        loaders[self.counterType] = MelCountedFids.NullLoader

    def dumpData(self, record, out):
        value = record.__getattribute__(self.attr)
        if value:
            out.packSub(self.counterType, self.counterFormat, len(value))
            MelFids.dumpData(self, record, out)

#------------------------------------------------------------------------------
class MelFidList(MelFids):
    """Represents a listmod record fid elements. The only difference from
    MelFids is how the data is stored. For MelFidList, the data is stored
    as a single subrecord rather than as separate subrecords."""

    def loadData(self, record, ins, sub_type, size_, readId):
        """Reads data from ins into record attribute."""
        if not size_: return
        fids = ins.unpack(`size_ / 4` + 'I', size_, readId)
        record.__setattr__(self.attr,list(fids))
        if self._debug:
            for fid in fids:
                print u'  %08X' % fid

    def dumpData(self,record,out):
        """Dumps data from record to outstream."""
        fids = record.__getattribute__(self.attr)
        if not fids: return
        out.packSub(self.subType,`len(fids)`+'I',*fids)

#------------------------------------------------------------------------------
class MelCountedFidList(MelFidList):
    """Handle writing out a preceding 'count' subrecord for Fid subrecords.
       For example, KSIZ holds an int telling how many KWDA elements there
       are."""

    # Used to ignore the count record on loading.  Writing is handled by dumpData
    # In the KSIZ/KWDA example, the NullLoader will handle "reading" the KSIZ
    # subrecord, where "reading" = ignoring
    NullLoader = MelNull('ANY')

    def __init__(self, countedType, attr, counterType, counterFormat='<I', default=None):
        # In the KSIZ/KWDA example, countedType is KWDA, counterType is KSIZ
        MelFids.__init__(self, countedType, attr, default)
        self.counterType = counterType
        self.counterFormat = counterFormat

    def getLoaders(self, loaders):
        """Register loaders for both the counted and counter subrecords"""
        # Counted
        MelFidList.getLoaders(self, loaders)
        # Counter
        loaders[self.counterType] = MelCountedFids.NullLoader

    def dumpData(self, record, out):
        fids = record.__getattribute__(self.attr)
        if not fids: return
        out.packSub(self.counterType, self.counterFormat, len(fids))
        MelFidList.dumpData(self, record, out)

#------------------------------------------------------------------------------
class MelSortedFidList(MelFidList):
    """MelFidList that sorts the order of the Fids before writing them.  They are not sorted after modification, only just prior to writing."""

    def __init__(self, subType, attr, sortKeyFn=lambda x: x, default=None):
        """sortKeyFn - function to pass to list.sort(key = ____) to sort the FidList
           just prior to writing.  Since the FidList will already be converted to short Fids
           at this point we're sorting 4-byte values,  not (FileName, 3-Byte) tuples."""
        MelFidList.__init__(self, subType, attr, default)
        self.sortKeyFn = sortKeyFn

    def dumpData(self, record, out):
        fids = record.__getattribute__(self.attr)
        if not fids: return
        fids.sort(key=self.sortKeyFn)
        # NOTE: fids.sort sorts from lowest to highest, so lowest values FormID will sort first
        #       if it should be opposite, use this instead:
        #  fids.sort(key=self.sortKeyFn, reverse=True)
        out.packSub(self.subType, `len(fids)` + 'I', *fids)

#------------------------------------------------------------------------------
class MelGroup(MelBase):
    """Represents a group record."""

    def __init__(self,attr,*elements):
        """Initialize."""
        self.attr,self.elements,self.formElements,self.loaders = attr,elements,set(),{}

    def debug(self,on=True):
        """Sets debug flag on self."""
        for element in self.elements: element.debug(on)
        return self

    def getDefaulters(self,defaulters,base):
        """Registers self as a getDefault(attr) provider."""
        defaulters[base+self.attr] = self
        for element in self.elements:
            element.getDefaulters(defaulters,base+self.attr+'.')

    def getLoaders(self,loaders):
        """Adds self as loader for subelements."""
        for element in self.elements:
            element.getLoaders(self.loaders)
        for type in self.loaders:
            loaders[type] = self

    def hasFids(self,formElements):
        """Include self if has fids."""
        for element in self.elements:
            element.hasFids(self.formElements)
        if self.formElements: formElements.add(self)

    def setDefault(self,record):
        """Sets default value for record instance."""
        record.__setattr__(self.attr,None)

    def getDefault(self):
        """Returns a default copy of object."""
        target = MelObject()
        for element in self.elements:
            element.setDefault(target)
        return target

    def loadData(self, record, ins, sub_type, size_, readId):
        """Reads data from ins into record attribute."""
        target = record.__getattribute__(self.attr)
        if target is None:
            target = self.getDefault()
            record.__setattr__(self.attr,target)
        target.__slots__ = [s for element in self.elements for s in
                            element.getSlotsUsed()]
        self.loaders[sub_type].loadData(target, ins, sub_type, size_, readId)

    def dumpData(self,record,out):
        """Dumps data from record to outstream."""
        target = record.__getattribute__(self.attr)
        if not target: return
        for element in self.elements:
            element.dumpData(target,out)

    def mapFids(self,record,function,save=False):
        """Applies function to fids. If save is true, then fid is set
        to result of function."""
        target = record.__getattribute__(self.attr)
        if not target: return
        for element in self.formElements:
            element.mapFids(target,function,save)

#------------------------------------------------------------------------------
class MelGroups(MelGroup):
    """Represents an array of group record."""

    def __init__(self,attr,*elements):
        """Initialize. Must have at least one element."""
        MelGroup.__init__(self,attr,*elements)
        self.type0 = self.elements[0].subType

    def setDefault(self,record):
        """Sets default value for record instance."""
        record.__setattr__(self.attr,[])

    def loadData(self, record, ins, sub_type, size_, readId):
        """Reads data from ins into record attribute."""
        if sub_type == self.type0:
            target = self.getDefault()
            record.__getattribute__(self.attr).append(target)
        else:
            target = record.__getattribute__(self.attr)[-1]
        target.__slots__ = [s for element in self.elements for s in
                            element.getSlotsUsed()]
        self.loaders[sub_type].loadData(target, ins, sub_type, size_, readId)

    def dumpData(self,record,out):
        """Dumps data from record to outstream."""
        elements = self.elements
        for target in record.__getattribute__(self.attr):
            for element in elements:
                element.dumpData(target,out)

    def mapFids(self,record,function,save=False):
        """Applies function to fids. If save is true, then fid is set
        to result of function."""
        formElements = self.formElements
        for target in record.__getattribute__(self.attr):
            for element in formElements:
                element.mapFids(target,function,save)

#------------------------------------------------------------------------------
class MelXpci(MelNull):
    """Handler for obsolete MelXpci record. Bascially just discards it."""
    def loadData(self, record, ins, sub_type, size_, readId):
        """Reads data from ins into record attribute."""
        xpci = ins.unpackRef()
        #--Read ahead and get associated full as well.
        pos = ins.tell()
        (sub_type_, size_) = ins.unpack('4sH', 6, readId + '.FULL')
        if sub_type_ == 'FULL':
            full = ins.read(size_, readId)
        else:
            full = None
            ins.seek(pos)
        if self._debug: print u' ',strFid(record.fid),strFid(xpci),full

#------------------------------------------------------------------------------
class MelString(MelBase):
    """Represents a mod record string element."""

    def __init__(self, subType, attr, default=None, maxSize=0):
        """Initialize."""
        MelBase.__init__(self, subType, attr, default)
        self.maxSize = maxSize

    def loadData(self, record, ins, sub_type, size_, readId):
        """Reads data from ins into record attribute."""
        value = ins.readString(size_, readId)
        record.__setattr__(self.attr,value)
        if self._debug: print u' ',record.__getattribute__(self.attr)

    def dumpData(self,record,out):
        """Dumps data from record to outstream."""
        string_val = record.__getattribute__(self.attr)
        if string_val is not None:
            out.write_string(self.subType, string_val, max_size=self.maxSize)

#------------------------------------------------------------------------------
class MelUnicode(MelString):
    """Like MelString, but instead of using bolt.pluginEncoding to read the
       string, it tries the encoding specified in the constructor instead"""
    def __init__(self, subType, attr, default=None, maxSize=0, encoding=None):
        MelString.__init__(self, subType, attr, default, maxSize)
        self.encoding = encoding # None == automatic detection

    def loadData(self, record, ins, sub_type, size_, readId):
        """Reads data from ins into record attribute"""
        value = u'\n'.join(decode(x,self.encoding,avoidEncodings=('utf8','utf-8'))
                           for x in bolt.cstrip(ins.read(size_, readId)).split('\n'))
        record.__setattr__(self.attr,value)

    def dumpData(self,record,out):
        string_val = record.__getattribute__(self.attr)
        if string_val is not None:
            out.write_string(self.subType, string_val, max_size=self.maxSize,
                             preferred_encoding=self.encoding)

#------------------------------------------------------------------------------
class MelLString(MelString):
    """Represents a mod record localized string."""
    def loadData(self, record, ins, sub_type, size_, readId):
        value = ins.readLString(size_, readId)
        record.__setattr__(self.attr,value)
        if self._debug: print u' ',record.__getattribute__(self.attr)

#------------------------------------------------------------------------------
class MelStrings(MelString):
    """Represents array of strings."""

    def setDefault(self,record):
        """Sets default value for record instance."""
        record.__setattr__(self.attr,[])

    def getDefault(self):
        """Returns a default copy of object."""
        return []

    def loadData(self, record, ins, sub_type, size_, readId):
        """Reads data from ins into record attribute."""
        value = ins.readStrings(size_, readId)
        record.__setattr__(self.attr,value)
        if self._debug: print u' ',value

    def dumpData(self,record,out):
        """Dumps data from record to outstream."""
        strings = record.__getattribute__(self.attr)
        if strings:
            out.packSub0(self.subType,null1.join(encode(x,firstEncoding=bolt.pluginEncoding) for x in strings)+null1)

#------------------------------------------------------------------------------
class MelStruct(MelBase):
    """Represents a structure record."""

    def __init__(self, subType, format, *elements, **kwdargs):
        """Initialize."""
        dumpExtra = kwdargs.get('dumpExtra', None)
        self.subType, self.format = subType, format
        self.attrs,self.defaults,self.actions,self.formAttrs = MelBase.parseElements(*elements)
        self._debug = False
        if dumpExtra:
            self.attrs += (dumpExtra,)
            self.defaults += ('',)
            self.actions += (None,)
            self.formatLen = struct.calcsize(format)
        else:
            self.formatLen = -1

    def getSlotsUsed(self):
        return self.attrs

    def hasFids(self,formElements):
        """Include self if has fids."""
        if self.formAttrs: formElements.add(self)

    def setDefault(self,record):
        """Sets default value for record instance."""
        setter = record.__setattr__
        for attr,value,action in zip(self.attrs, self.defaults, self.actions):
            if action: value = action(value)
            setter(attr,value)

    def loadData(self, record, ins, sub_type, size_, readId):
        """Reads data from ins into record attribute."""
        readsize = self.formatLen if self.formatLen >= 0 else size_
        unpacked = ins.unpack(self.format,readsize,readId)
        setter = record.__setattr__
        for attr,value,action in zip(self.attrs,unpacked,self.actions):
            if action: value = action(value)
            setter(attr, value)
        if self.formatLen >= 0:
            # Dump remaining subrecord data into an attribute
            setter(self.attrs[-1], ins.read(size_ - self.formatLen))
        if self._debug:
            print u' ',zip(self.attrs,unpacked)
            if len(unpacked) != len(self.attrs):
                print u' ',unpacked

    def dumpData(self,record,out):
        """Dumps data from record to outstream."""
        values = []
        valuesAppend = values.append
        getter = record.__getattribute__
        for attr,action in zip(self.attrs,self.actions):
            value = getter(attr)
            if action: value = value.dump()
            valuesAppend(value)
        if self.formatLen >= 0:
            extraLen = len(values[-1])
            format = self.format + `extraLen` + 's'
        else:
            format = self.format
        try:
            out.packSub(self.subType,format,*values)
        except struct.error:
            print self.subType,self.format,values
            raise

    def mapFids(self,record,function,save=False):
        """Applies function to fids. If save is true, then fid is set
        to result of function."""
        getter = record.__getattribute__
        setter = record.__setattr__
        for attr in self.formAttrs:
            result = function(getter(attr))
            if save: setter(attr,result)

#------------------------------------------------------------------------------
class MelStructs(MelStruct):
    """Represents array of structured records."""

    def __init__(self, subType, format, attr, *elements, **kwdargs):
        """Initialize."""
        MelStruct.__init__(self, subType, format, *elements, **kwdargs)
        self.attr = attr

    def getSlotsUsed(self):
        return self.attr,

    def getDefaulters(self,defaulters,base):
        """Registers self as a getDefault(attr) provider."""
        defaulters[base+self.attr] = self

    def setDefault(self,record):
        """Sets default value for record instance."""
        record.__setattr__(self.attr,[])

    def getDefault(self):
        """Returns a default copy of object."""
        target = MelObject()
        setter = target.__setattr__
        for attr,value,action in zip(self.attrs, self.defaults, self.actions):
            if callable(action): value = action(value)
            setter(attr,value)
        return target

    def loadData(self, record, ins, sub_type, size_, readId):
        """Reads data from ins into record attribute."""
        target = MelObject()
        record.__getattribute__(self.attr).append(target)
        target.__slots__ = self.attrs
        MelStruct.loadData(self, target, ins, sub_type, size_, readId)

    def dumpData(self,record,out):
        """Dumps data from record to outstream."""
        melDump = MelStruct.dumpData
        for target in record.__getattribute__(self.attr):
            melDump(self,target,out)

    def mapFids(self,record,function,save=False):
        """Applies function to fids. If save is true, then fid is set
        to result of function."""
        melMap = MelStruct.mapFids
        if not record.__getattribute__(self.attr): return
        for target in record.__getattribute__(self.attr):
            melMap(self,target,function,save)

#------------------------------------------------------------------------------
class MelStructA(MelStructs):
    """Represents a record with an array of fixed size repeating structured elements."""
    def loadData(self, record, ins, sub_type, size_, readId):
        """Reads data from ins into record attribute."""
        if size_ == 0:
            setattr(record, self.attr, None)
            return
        selfDefault = self.getDefault
        recordAppend = record.__getattribute__(self.attr).append
        selfAttrs = self.attrs
        itemSize = struct.calcsize(self.format)
        melLoadData = MelStruct.loadData
        # Note for py3: we want integer division here!
        for x in xrange(size_/itemSize):
            target = selfDefault()
            recordAppend(target)
            target.__slots__ = selfAttrs
            melLoadData(self, target, ins, sub_type, itemSize, readId)

    def dumpData(self,record,out):
        if record.__getattribute__(self.attr) is not None:
            data = ''
            attrs = self.attrs
            format = self.format
            for x in record.__getattribute__(self.attr):
                data += struct_pack(format, *[getattr(x, item) for item in attrs])
            out.packSub(self.subType,data)

    def mapFids(self,record,function,save=False):
        """Applies function to fids. If save is true, then fid is set
        to result of function."""
        if record.__getattribute__(self.attr) is not None:
            melMap = MelStruct.mapFids
            for target in record.__getattribute__(self.attr):
                melMap(self,target,function,save)

class MelColorInterpolator(MelStructA):
    """Wrapper around MelStructA that defines a time interpolator - an array
    of two floats, where each entry in the array describes a point on a curve,
    with 'time' as the X axis and 'red', 'green', 'blue' and 'alpha' as the Y
    axis."""
    def __init__(self, sub_type, attr):
        MelStructA.__init__(self, sub_type, '5f', attr, 'time', 'red', 'green',
                            'blue', 'alpha',)

# xEdit calls this 'time interpolator', but that name doesn't really make sense
# Both this class and the color interpolator above interpolate over time
class MelValueInterpolator(MelStructA):
    """Wrapper around MelStructA that defines a value interpolator - an array
    of two floats, where each entry in the array describes a point on a curve,
    with 'time' as the X axis and 'value' as the Y axis."""
    def __init__(self, sub_type, attr):
        MelStructA.__init__(self, sub_type, '2f', attr, 'time', 'value')

#------------------------------------------------------------------------------
class MelTuple(MelBase):
    """Represents a fixed length array that maps to a single subrecord.
    (E.g., the stats array for NPC_ which maps to the DATA subrecord.)"""

    def __init__(self, subType, format, attr, defaults):
        """Initialize."""
        self.subType, self.format, self.attr, self.defaults = subType, format, attr, defaults
        self._debug = False

    def setDefault(self,record):
        """Sets default value for record instance."""
        record.__setattr__(self.attr,self.defaults[:])

    def loadData(self, record, ins, sub_type, size_, readId):
        """Reads data from ins into record attribute."""
        unpacked = ins.unpack(self.format, size_, readId)
        record.__setattr__(self.attr,list(unpacked))
        if self._debug: print record.__getattribute__(self.attr)

    def dumpData(self,record,out):
        """Dumps data from record to outstream."""
        #print self.subType,self.format,self.attr,record.__getattribute__(self.attr)
        out.packSub(self.subType,self.format,*record.__getattribute__(self.attr))

#------------------------------------------------------------------------------
#-- Common/Special Elements
class MelFull0(MelString):
    """Represents the main full. Use this only when there are additional FULLs
    Which means when record has magic effects."""

    def __init__(self):
        """Initialize."""
        MelString.__init__(self,'FULL','full')

#------------------------------------------------------------------------------
# Hack for allowing record imports from parent games - set per game
MelModel = None # type: type
#------------------------------------------------------------------------------
class MelOptStruct(MelStruct):
    """Represents an optional structure, where if values are null, is skipped."""

    def dumpData(self,record,out):
        """Dumps data from record to outstream."""
        # TODO: Unfortunately, checking if the attribute is None is not
        # really effective.  Checking it to be 0,empty,etc isn't effective either.
        # It really just needs to check it against the default.
        recordGetAttr = record.__getattribute__
        for attr,default in zip(self.attrs,self.defaults):
            oldValue=recordGetAttr(attr)
            if oldValue is not None and oldValue != default:
                MelStruct.dumpData(self,record,out)
                break

#------------------------------------------------------------------------------
# Mod Element Sets ------------------------------------------------------------
#------------------------------------------------------------------------------
class MelSet:
    """Set of mod record elments."""

    def __init__(self,*elements):
        """Initialize."""
        self._debug = False
        self.elements = elements
        self.defaulters = {}
        self.loaders = {}
        self.formElements = set()
        self.firstFull = None
        self.full0 = None
        for element in self.elements:
            element.getDefaulters(self.defaulters,'')
            element.getLoaders(self.loaders)
            element.hasFids(self.formElements)
            if isinstance(element,MelFull0):
                self.full0 = element

    def debug(self,on=True):
        """Sets debug flag on self."""
        self._debug = on
        return self

    def getSlotsUsed(self):
        """This function returns all of the attributes used in record instances that use this instance."""
        return [s for element in self.elements for s in element.getSlotsUsed()]

    def initRecord(self, record, header, ins, do_unpack):
        """Initialize record, setting its attributes based on its elements."""
        for element in self.elements:
            element.setDefault(record)
        MreRecord.__init__(record, header, ins, do_unpack)

    def getDefault(self,attr):
        """Returns default instance of specified instance. Only useful for
        MelGroup, MelGroups and MelStructs."""
        return self.defaulters[attr].getDefault()

    def loadData(self,record,ins,endPos):
        """Loads data from input stream. Called by load()."""
        doFullTest = (self.full0 is not None)
        recType = record.recType
        loaders = self.loaders
        _debug = self._debug
        #--Read Records
        if _debug: print u'\n>>>> %08X' % record.fid
        insAtEnd = ins.atEnd
        insSubHeader = ins.unpackSubHeader
        # fullLoad = self.full0.loadData
        while not insAtEnd(endPos,recType):
            (Type,size) = insSubHeader(recType)
            if _debug: print Type,size
            readId = recType + '.' + Type
            try:
                if Type not in loaders:
                    raise exception.ModError(ins.inName, u'Unexpected subrecord: ' + repr(readId))
                #--Hack to handle the fact that there can be two types of FULL in spell/ench/ingr records.
                elif doFullTest and Type == 'FULL':
                    self.full0.loadData(record, ins, Type, size, readId)
                else:
                    loaders[Type].loadData(record, ins, Type, size, readId)
                doFullTest = doFullTest and (Type != 'EFID')
            except Exception as error:
                print error
                eid = getattr(record,'eid',u'<<NO EID>>')
                if not eid: eid = u'<<NO EID>>'
                print u'Error loading %s record and/or subrecord: %08X\n  eid = %s\n  subrecord = %s\n  subrecord size = %d\n  file pos = %d' % (repr(record.recType),record.fid,repr(eid),repr(Type),size,ins.tell())
                raise
        if _debug: print u'<<<<',getattr(record,'eid',u'[NO EID]')

    def dumpData(self,record, out):
        """Dumps state into out. Called by getSize()."""
        for element in self.elements:
            try:
                element.dumpData(record,out)
            except:
                bolt.deprint('error dumping data:',traceback=True)
                print u'Dumping:',getattr(record,'eid',u'<<NO EID>>'),record.fid,element
                for attr in record.__slots__:
                    if hasattr(record,attr):
                        print u"> %s: %s" % (attr,repr(getattr(record,attr)))
                raise

    def mapFids(self,record,mapper,save=False):
        """Maps fids of subelements."""
        for element in self.formElements:
            element.mapFids(record,mapper,save)

    def convertFids(self,record, mapper,toLong):
        """Converts fids between formats according to mapper.
        toLong should be True if converting to long format or False if converting to short format."""
        if record.longFids == toLong: return
        record.fid = mapper(record.fid)
        for element in self.formElements:
            element.mapFids(record,mapper,True)
        record.longFids = toLong
        record.setChanged()

    def updateMasters(self,record,masters):
        """Updates set of master names according to masters actually used."""
        if not record.longFids: raise exception.StateError("Fids not in long format")
        def updater(fid):
            masters.add(fid)
        updater(record.fid)
        for element in self.formElements:
            element.mapFids(record,updater)

    def getReport(self):
        """Returns a report of structure."""
        buff = StringIO.StringIO()
        for element in self.elements:
            element.report(None,buff,u'')
        ret = buff.getvalue()
        buff.close()
        return ret

# Mod Records -----------------------------------------------------------------
#------------------------------------------------------------------------------
class MreSubrecord:
    """Generic Subrecord."""
    def __init__(self,type,size,ins=None):
        self.changed = False
        self.subType = type
        self.size = size
        self.data = None
        self.inName = ins and ins.inName
        if ins: self.load(ins)

    def load(self,ins):
        self.data = ins.read(self.size,'----.'+self.subType)

    def setChanged(self,value=True):
        """Sets changed attribute to value. [Default = True.]"""
        self.changed = value

    def setData(self,data):
        """Sets data and size."""
        self.data = data
        self.size = len(data)

    def getSize(self):
        """Return size of self.data, after, if necessary, packing it."""
        if not self.changed: return self.size
        #--StringIO Object
        with ModWriter(sio()) as out:
            self.dumpData(out)
            #--Done
            self.data = out.getvalue()
        self.size = len(self.data)
        self.setChanged(False)
        return self.size

    def dumpData(self,out):
        """Dumps state into out. Called by getSize()."""
        raise exception.AbstractError

    def dump(self,out):
        if self.changed: raise exception.StateError(u'Data changed: ' + self.subType)
        if not self.data: raise exception.StateError(u'Data undefined: ' + self.subType)
        out.packSub(self.subType,self.data)

#------------------------------------------------------------------------------
class MreRecord(object):
    """Generic Record. flags1 are game specific see comments."""
    subtype_attr = {'EDID':'eid','FULL':'full','MODL':'model'}
    flags1_ = bolt.Flags(0L, bolt.Flags.getNames(
        # {Sky}, {FNV} 0x00000000 ACTI: Collision Geometry (default)
        ( 0,'esm'), # {0x00000001}
        # {Sky}, {FNV} 0x00000004 ARMO: Not playable
        ( 2,'isNotPlayable'), # {0x00000004}
        # {FNV} 0x00000010 ????: Form initialized (Runtime only)
        ( 4,'formInitialized'), # {0x00000010}
        ( 5,'deleted'), # {0x00000020}
        # {Sky}, {FNV} 0x00000040 ACTI: Has Tree LOD
        # {Sky}, {FNV} 0x00000040 REGN: Border Region
        # {Sky}, {FNV} 0x00000040 STAT: Has Tree LOD
        # {Sky}, {FNV} 0x00000040 REFR: Hidden From Local Map
        # {TES4} 0x00000040 ????:  Actor Value
        # Constant HiddenFromLocalMap BorderRegion HasTreeLOD ActorValue
        ( 6,'borderRegion'), # {0x00000040}
        # {Sky} 0x00000080 TES4: Localized
        # {Sky}, {FNV} 0x00000080 PHZD: Turn Off Fire
        # {Sky} 0x00000080 SHOU: Treat Spells as Powers
        # {Sky}, {FNV} 0x00000080 STAT: Add-on LOD Object
        # {TES4} 0x00000080 ????:  Actor Value
        # Localized IsPerch AddOnLODObject TurnOffFire TreatSpellsAsPowers  ActorValue
        ( 7,'turnFireOff'), # {0x00000080}
        ( 7,'hasStrings'), # {0x00000080}
        # {Sky}, {FNV} 0x00000100 ACTI: Must Update Anims
        # {Sky}, {FNV} 0x00000100 REFR: Inaccessible
        # {Sky}, {FNV} 0x00000100 REFR for LIGH: Doesn't light water
        # MustUpdateAnims Inaccessible DoesntLightWater
        ( 8,'inaccessible'), # {0x00000100}
        # {Sky}, {FNV} 0x00000200 ACTI: Local Map - Turns Flag Off, therefore it is Hidden
        # {Sky}, {FNV} 0x00000200 REFR: MotionBlurCastsShadows
        # HiddenFromLocalMap StartsDead MotionBlur CastsShadows
        ( 9,'castsShadows'), # {0x00000200}
        # New Flag for FO4 and SSE used in .esl files
        ( 9, 'eslFile'), # {0x00000200}
        # {Sky}, {FNV} 0x00000400 LSCR: Displays in Main Menu
        # PersistentReference QuestItem DisplaysInMainMenu
        (10,'questItem'), # {0x00000400}
        (10,'persistent'), # {0x00000400}
        (11,'initiallyDisabled'), # {0x00000800}
        (12,'ignored'), # {0x00001000}
        # {FNV} 0x00002000 ????: No Voice Filter
        (13,'noVoiceFilter'), # {0x00002000}
        # {FNV} 0x00004000 STAT: Cannot Save (Runtime only) Ignore VC info
        (14,'cannotSave'), # {0x00004000}
        # {Sky}, {FNV} 0x00008000 STAT: Has Distant LOD
        (15,'visibleWhenDistant'), # {0x00008000}
        # {Sky}, {FNV} 0x00010000 ACTI: Random Animation Start
        # {Sky}, {FNV} 0x00010000 REFR light: Never fades
        # {FNV} 0x00010000 REFR High Priority LOD
        # RandomAnimationStart NeverFades HighPriorityLOD
        (16,'randomAnimationStart'), # {0x00010000}
        # {Sky}, {FNV} 0x00020000 ACTI: Dangerous
        # {Sky}, {FNV} 0x00020000 REFR light: Doesn't light landscape
        # {Sky} 0x00020000 SLGM: Can hold NPC's soul
        # {Sky}, {FNV} 0x00020000 STAT: Use High-Detail LOD Texture
        # {FNV} 0x00020000 STAT: Radio Station (Talking Activator)
        # {FNV} 0x00020000 STAT: Off limits (Interior cell)
        # Dangerous OffLimits DoesntLightLandscape HighDetailLOD CanHoldNPC RadioStation
        (17,'dangerous'), # {0x00020000}
        (18,'compressed'), # {0x00040000}
        # {Sky}, {FNV} 0x00080000 STAT: Has Currents
        # {FNV} 0x00080000 STAT: Platform Specific Texture
        # {FNV} 0x00080000 STAT: Dead
        # CantWait HasCurrents PlatformSpecificTexture Dead
        (19,'cantWait'), # {0x00080000}
        # {Sky}, {FNV} 0x00100000 ACTI: Ignore Object Interaction
        (20,'ignoreObjectInteraction'), # {0x00100000}
        # {???} 0x00200000 ????: Used in Memory Changed Form
        # {Sky}, {FNV} 0x00800000 ACTI: Is Marker
        (23,'isMarker'), # {0x00800000}
        # {FNV} 0x01000000 ????: Destructible (Runtime only)
        (24,'destructible'), # {0x01000000} {FNV}
        # {Sky}, {FNV} 0x02000000 ACTI: Obstacle
        # {Sky}, {FNV} 0x02000000 REFR: No AI Acquire
        (25,'obstacle'), # {0x02000000}
        # {Sky}, {FNV} 0x04000000 ACTI: Filter
        (26,'navMeshFilter'), # {0x04000000}
        # {Sky}, {FNV} 0x08000000 ACTI: Bounding Box
        # NavMesh BoundingBox
        (27,'boundingBox'), # {0x08000000}
        # {Sky}, {FNV} 0x10000000 STAT: Show in World Map
        # {FNV} 0x10000000 STAT: Reflected by Auto Water
        # {FNV} 0x10000000 STAT: Non-Pipboy
        # MustExitToTalk ShowInWorldMap NonPipboy',
        (28,'nonPipboy'), # {0x10000000}
        # {Sky}, {FNV} 0x20000000 ACTI: Child Can Use
        # {Sky}, {FNV} 0x20000000 REFR: Don't Havok Settle
        # {FNV} 0x20000000 REFR: Refracted by Auto Water
        # ChildCanUse DontHavokSettle RefractedbyAutoWater
        (29,'refractedbyAutoWater'), # {0x20000000}
        # {Sky}, {FNV} 0x40000000 ACTI: GROUND
        # {Sky}, {FNV} 0x40000000 REFR: NoRespawn
        # NavMeshGround NoRespawn
        (30,'noRespawn'), # {0x40000000}
        # {Sky}, {FNV} 0x80000000 REFR: MultiBound
        # MultiBound
        (31,'multiBound'), # {0x80000000}
        ))
    __slots__ = ['header','recType','fid','flags1','size','flags2','changed','subrecords','data','inName','longFids',]
    #--Set at end of class data definitions.
    type_class = None
    simpleTypes = None
    isKeyedByEid = False

    def __init__(self, header, ins=None, do_unpack=False):
        self.header = header
        self.recType = header.recType
        self.fid = header.fid
        self.flags1 = MreRecord.flags1_(header.flags1)
        self.size = header.size
        self.flags2 = header.flags2
        self.longFids = False #--False: Short (numeric); True: Long (espname,objectindex)
        self.changed = False
        self.subrecords = None
        self.data = ''
        self.inName = ins and ins.inName
        if ins: self.load(ins, do_unpack)

    def __repr__(self):
        if hasattr(self,'eid') and self.eid is not None:
            eid=u' '+self.eid
        else:
            eid=u''
        return u'<%s object: %s (%s)%s>' % (unicode(type(self)).split(u"'")[1], self.recType, strFid(self.fid), eid)

    def getHeader(self):
        """Returns header tuple."""
        return self.header

    def getBaseCopy(self):
        """Returns an MreRecord version of self."""
        baseCopy = MreRecord(self.getHeader())
        baseCopy.data = self.data
        return baseCopy

    def getTypeCopy(self,mapper=None):
        """Returns a type class copy of self, optionaly mapping fids to long."""
        if self.__class__ == MreRecord:
            fullClass = MreRecord.type_class[self.recType]
            myCopy = fullClass(self.getHeader())
            myCopy.data = self.data
            myCopy.load(do_unpack=True)
        else:
            myCopy = copy.deepcopy(self)
        if mapper and not myCopy.longFids:
            myCopy.convertFids(mapper,True)
        myCopy.changed = True
        myCopy.data = None
        return myCopy

    def mergeFilter(self,modSet):
        """This method is called by the bashed patch mod merger. The intention is
        to allow a record to be filtered according to the specified modSet. E.g.
        for a list record, items coming from mods not in the modSet could be
        removed from the list."""
        pass

    def getDecompressed(self):
        """Return self.data, first decompressing it if necessary."""
        if not self.flags1.compressed: return self.data
        size, = struct_unpack('I', self.data[:4])
        decomp = zlib.decompress(self.data[4:])
        if len(decomp) != size:
            raise exception.ModError(self.inName,
                u'Mis-sized compressed data. Expected %d, got %d.'
                                     % (size,len(decomp)))
        return decomp

    def load(self, ins=None, do_unpack=False):
        """Load data from ins stream or internal data buffer."""
        type = self.recType
        #--Read, but don't analyze.
        if not do_unpack:
            self.data = ins.read(self.size,type)
        #--Unbuffered analysis?
        elif ins and not self.flags1.compressed:
            inPos = ins.tell()
            self.data = ins.read(self.size,type)
            ins.seek(inPos,0,type+'_REWIND') # type+'_REWIND' is just for debug
            self.loadData(ins,inPos+self.size)
        #--Buffered analysis (subclasses only)
        else:
            if ins:
                self.data = ins.read(self.size,type)
            if not self.__class__ == MreRecord:
                with self.getReader() as reader:
                    # Check This
                    if ins and ins.hasStrings: reader.setStringTable(ins.strings)
                    self.loadData(reader,reader.size)
        #--Discard raw data?
        if do_unpack == 2:
            self.data = None
            self.changed = True

    def loadData(self,ins,endPos):
        """Loads data from input stream. Called by load().

        Subclasses should actually read the data, but MreRecord just skips over
        it (assuming that the raw data has already been read to itself. To force
        reading data into an array of subrecords, use loadSubrecords()."""
        ins.seek(endPos)

    def loadSubrecords(self):
        """This is for MreRecord only. It reads data into an array of subrecords,
        so that it can be handled in a simplistic way."""
        self.subrecords = []
        if not self.data: return
        with self.getReader() as reader:
            recType = self.recType
            readAtEnd = reader.atEnd
            readSubHeader = reader.unpackSubHeader
            subAppend = self.subrecords.append
            while not readAtEnd(reader.size,recType):
                (type,size) = readSubHeader(recType)
                subAppend(MreSubrecord(type,size,reader))

    def convertFids(self,mapper,toLong):
        """Converts fids between formats according to mapper.
        toLong should be True if converting to long format or False if converting to short format."""
        raise exception.AbstractError(self.recType)

    def updateMasters(self,masters):
        """Updates set of master names according to masters actually used."""
        raise exception.AbstractError(self.recType)

    def setChanged(self,value=True):
        """Sets changed attribute to value. [Default = True.]"""
        self.changed = value

    def setData(self,data):
        """Sets data and size."""
        self.data = data
        self.size = len(data)
        self.changed = False

    def getSize(self):
        """Return size of self.data, after, if necessary, packing it."""
        if not self.changed: return self.size
        if self.longFids: raise exception.StateError(
            u'Packing Error: %s %s: Fids in long format.'
            % (self.recType,self.fid))
        #--Pack data and return size.
        with ModWriter(sio()) as out:
            self.dumpData(out)
            self.data = out.getvalue()
        if self.flags1.compressed:
            dataLen = len(self.data)
            comp = zlib.compress(self.data,6)
            self.data = struct_pack('=I', dataLen) + comp
        self.size = len(self.data)
        self.setChanged(False)
        return self.size

    def dumpData(self,out):
        """Dumps state into data. Called by getSize(). This default version
        just calls subrecords to dump to out."""
        if self.subrecords is None:
            raise exception.StateError(u'Subrecords not unpacked. [%s: %s %08X]' %
                                       (self.inName, self.recType, self.fid))
        for subrecord in self.subrecords:
            subrecord.dump(out)

    def dump(self,out):
        """Dumps all data to output stream."""
        if self.changed: raise exception.StateError(u'Data changed: ' + self.recType)
        if not self.data and not self.flags1.deleted and self.size > 0:
            raise exception.StateError(u'Data undefined: ' + self.recType + u' ' + hex(self.fid))
        #--Update the header so it 'packs' correctly
        self.header.size = self.size
        if self.recType != 'GRUP':
            self.header.flags1 = self.flags1
            self.header.fid = self.fid
        out.write(self.header.pack())
        if self.size > 0: out.write(self.data)

    def getReader(self):
        """Returns a ModReader wrapped around (decompressed) self.data."""
        return ModReader(self.inName,sio(self.getDecompressed()))

    #--Accessing subrecords ---------------------------------------------------
    def getSubString(self,subType):
        """Returns the (stripped) string for a zero-terminated string record."""
        #--Common subtype expanded in self?
        attr = MreRecord.subtype_attr.get(subType)
        value = None #--default
        #--If not MreRecord, then will have info in data.
        if self.__class__ != MreRecord:
            if attr not in self.__slots__: return value
            return self.__getattribute__(attr)
        #--Subrecords available?
        if self.subrecords is not None:
            for subrecord in self.subrecords:
                if subrecord.subType == subType:
                    value = bolt.cstrip(subrecord.data)
                    break
        #--No subrecords, but have data.
        elif self.data:
            with self.getReader() as reader:
                recType = self.recType
                readAtEnd = reader.atEnd
                readSubHeader = reader.unpackSubHeader
                readSeek = reader.seek
                readRead = reader.read
                while not readAtEnd(reader.size,recType):
                    (type,size) = readSubHeader(recType)
                    if type != subType:
                        readSeek(size,1)
                    else:
                        value = bolt.cstrip(readRead(size))
                        break
        #--Return it
        return decode(value)

    def loadInfos(self,ins,endPos,infoClass):
        """Load infos from ins. Called from MobDials."""
        pass

#------------------------------------------------------------------------------
class MelRecord(MreRecord):
    """Mod record built from mod record elements."""
    melSet = None #--Subclasses must define as MelSet(*mels)
    __slots__ = []

    def __init__(self, header, ins=None, do_unpack=False):
        """Initialize."""
        self.__class__.melSet.initRecord(self, header, ins, do_unpack)

    def getDefault(self,attr):
        """Returns default instance of specified instance. Only useful for
        MelGroup, MelGroups and MelStructs."""
        return self.__class__.melSet.getDefault(attr)

    def loadData(self,ins,endPos):
        """Loads data from input stream. Called by load()."""
        self.__class__.melSet.loadData(self, ins, endPos)

    def dumpData(self,out):
        """Dumps state into out. Called by getSize()."""
        self.__class__.melSet.dumpData(self,out)

    def mapFids(self,mapper,save):
        """Applies mapper to fids of sub-elements. Will replace fid with mapped value if save == True."""
        self.__class__.melSet.mapFids(self,mapper,save)

    def convertFids(self,mapper,toLong):
        """Converts fids between formats according to mapper.
        toLong should be True if converting to long format or False if converting to short format."""
        self.__class__.melSet.convertFids(self,mapper,toLong)

    def updateMasters(self,masters):
        """Updates set of master names according to masters actually used."""
        self.__class__.melSet.updateMasters(self,masters)

#------------------------------------------------------------------------------
#-- Common Records
#------------------------------------------------------------------------------
class MreHeaderBase(MelRecord):
    """File header.  Base class for all 'TES4' like records"""
    #--Masters array element
    class MelMasterName(MelBase):
        def setDefault(self,record): record.masters = []
        def loadData(self, record, ins, sub_type, size_, readId):
            # Don't use ins.readString, because it will try to use bolt.pluginEncoding
            # for the filename.  This is one case where we want to use Automatic
            # encoding detection
            name = decode(bolt.cstrip(ins.read(size_, readId)), avoidEncodings=('utf8', 'utf-8'))
            name = GPath(name)
            record.masters.append(name)
        def dumpData(self,record,out):
            pack1 = out.packSub0
            pack2 = out.packSub
            for name in record.masters:
                pack1('MAST', encode(name.s, firstEncoding='cp1252'))
                pack2('DATA','Q',0)

    def getNextObject(self):
        """Gets next object index and increments it for next time."""
        self.changed = True
        self.nextObject += 1
        return self.nextObject -1

    __slots__ = []

#------------------------------------------------------------------------------
class MreGlob(MelRecord):
    """Global record.  Rather stupidly all values, despite their designation
       (short,long,float), are stored as floats -- which means that very large
       integers lose precision."""
    classType = 'GLOB'
    melSet = MelSet(
        MelString('EDID','eid'),
        MelStruct('FNAM','s',('format','s')),
        MelStruct('FLTV','f','value'),
        )
    __slots__ = melSet.getSlotsUsed()

#------------------------------------------------------------------------------
class MreGmstBase(MelRecord):
    """Game Setting record.  Base class, each game should derive from this
    class."""
    Ids = None
    classType = 'GMST'
    class MelGmstValue(MelBase):
        def loadData(self, record, ins, sub_type, size_, readId):
            # Possibles values: s|i|f|b; If empty, default to int
            gmst_type = encode(record.eid[0]) if record.eid else u'I'
            if gmst_type == u's':
                record.value = ins.readLString(size_, readId)
                return
            elif gmst_type == u'b':
                gmst_type = u'I'
            record.value, = ins.unpack(gmst_type, size_, readId)
        def dumpData(self,record,out):
            # Possibles values: s|i|f|b; If empty, default to int
            gmst_type = encode(record.eid[0]) if record.eid else u'I'
            if gmst_type == u's':
                out.packSub0(self.subType, record.value)
                return
            elif gmst_type == u'b':
                gmst_type = u'I'
            out.packSub(self.subType,gmst_type, record.value)
    melSet = MelSet(
        MelString('EDID','eid'),
        MelGmstValue('DATA','value'),
        )
    __slots__ = melSet.getSlotsUsed()

    def getGMSTFid(self):
        """Returns <Oblivion/Skyrim/etc>.esm fid in long format for specified
           eid."""
        cls = self.__class__
        import bosh # Late import to avoid circular imports
        if not cls.Ids:
            import bush
            fname = bush.game.pklfile
            try:
                with open(fname) as pkl_file:
                    cls.Ids = cPickle.load(pkl_file)[cls.classType]
            except:
                old = bolt.deprintOn
                bolt.deprintOn = True
                bolt.deprint(u'Error loading %s:' % fname, traceback=True)
                bolt.deprintOn = old
                raise
        return bosh.modInfos.masterName,cls.Ids[self.eid]

#------------------------------------------------------------------------------
# WARNING: This is implemented and (should be) functional, but we do not import
# it! The reason is that LAND records are numerous and very big, so importing
# and adding this to mergeClasses would slow us down quite a bit.
class MreLand(MelRecord):
    """Land structure. Part of exterior cells."""
    classType = 'LAND'

    class MelLandLayers(MelBase):
        """The ATXT/BTXT/VTXT subrecords of land occur in a group, but only as
        either BTXT or both ATXT and VTXT. So we must manually handle this.
        Additionally, this class is optimized for loading and memory
        performance, since LAND records are numerous and big."""

        def __init__(self):
            self.attr = 'layers'
            self.btxt = MelStruct('BTXT', 'IBsh', (FID, 'blTexture'),
                                  'blQuadrant', 'blUnknown', 'blLayer')
            self.atxt = MelStruct('ATXT', 'IBsh', (FID, 'alTexture'),
                                  'alQuadrant', 'alUnknown', 'alLayer')
            self.vtxt = MelBase('VTXT', 'alphaLayerData')

        def loadData(self, record, ins, sub_type, size_, readId):
            # Optimized for performance, that's why some code is copy-pasted
            layer = MelObject()
            record.layers.append(layer)
            if sub_type == 'BTXT': # read only BTXT
                layer.use_btxt = True
                layer.__slots__ = self.btxt.getSlotsUsed()
                self.btxt.loadData(layer, ins, sub_type, size_, readId)
            else: # sub_type == 'ATXT': read both ATXT and VTXT
                layer.use_btxt = False
                layer.__slots__ = self.atxt.getSlotsUsed() + \
                                  self.vtxt.getSlotsUsed()
                self.atxt.loadData(layer, ins, sub_type, size_, readId)
                self.vtxt.loadData(layer, ins, sub_type, size_, readId)
            layer.__slots__ += ('use_btxt',)

        def dumpData(self, record, out):
            for layer in record.layers:
                if layer.use_btxt:
                    self.btxt.dumpData(layer, out)
                else:
                    self.atxt.dumpData(layer, out)
                    self.vtxt.dumpData(layer, out)

        def getLoaders(self, loaders):
            for loader_type in ('ATXT', 'BTXT', 'VTXT'):
                loaders[loader_type] = self

        def hasFids(self, formElements):
            formElements.add(self)

        def mapFids(self, record, function, save=False):
            for layer in record.layers:
                map_target = self.btxt if layer.use_btxt else self.atxt
                map_target.mapFids(layer, function, save)

    melSet = MelSet(
        MelBase('DATA', 'unknown1'),
        MelBase('VNML', 'vertexNormals'),
        MelBase('VHGT', 'vertexHeightMap'),
        MelBase('VCLR', 'vertexColors'),
        MelLandLayers(),
        MelFidList('VTEX', 'vertexTextures'),
    )
    __slots__ = melSet.getSlotsUsed()

#------------------------------------------------------------------------------
class MreLeveledListBase(MelRecord):
    """Base type for leveled item/creature/npc/spells.
       it requires the base class to use the following:
       classAttributes:
          copyAttrs -> List of attributes to modify by copying when merging
       instanceAttributes:
          entries -> List of items, with the following attributes:
              listId
              level
              count
          chanceNone
          flags
    """
    _flags = bolt.Flags(0L,bolt.Flags.getNames(
        (0, 'calcFromAllLevels'),
        (1, 'calcForEachItem'),
        (2, 'useAllSpells'),
        (3, 'specialLoot'),
        ))
    copyAttrs = ()
    __slots__ = ['mergeOverLast', 'mergeSources', 'items', 'delevs', 'relevs']

    def __init__(self, header, ins=None, do_unpack=False):
        """Initialize"""
        MelRecord.__init__(self, header, ins, do_unpack)
        self.mergeOverLast = False #--Merge overrides last mod merged
        self.mergeSources = None #--Set to list by other functions
        self.items  = None #--Set of items included in list
        self.delevs = None #--Set of items deleted by list (Delev and Relev mods)
        self.relevs = None #--Set of items relevelled by list (Relev mods)

    def mergeFilter(self,modSet):
        """Filter out items that don't come from specified modSet."""
        if not self.longFids: raise exception.StateError(u'Fids not in long format')
        self.entries = [entry for entry in self.entries if entry.listId[0] in modSet]

    def mergeWith(self,other,otherMod):
        """Merges newLevl settings and entries with self.
        Requires that: self.items, other.delevs and other.relevs be defined."""
        if not self.longFids or not other.longFids:
            raise exception.StateError(u'Fids not in long format')
        #--Relevel or not?
        if other.relevs:
            for attr in self.__class__.copyAttrs:
                self.__setattr__(attr,other.__getattribute__(attr))
            self.flags = other.flags()
        else:
            for attr in self.__class__.copyAttrs:
                otherAttr = other.__getattribute__(attr)
                if otherAttr is not None:
                    self.__setattr__(attr, otherAttr)
            self.flags |= other.flags
        #--Remove items based on other.removes
        if other.delevs or other.relevs:
            removeItems = self.items & (other.delevs | other.relevs)
            self.entries = [entry for entry in self.entries if entry.listId not in removeItems]
            self.items = (self.items | other.delevs) - other.relevs
        hasOldItems = bool(self.items)
        #--Add new items from other
        newItems = set()
        entriesAppend = self.entries.append
        newItemsAdd = newItems.add
        for entry in other.entries:
            if entry.listId not in self.items:
                entriesAppend(entry)
                newItemsAdd(entry.listId)
        if newItems:
            self.items |= newItems
            self.entries.sort(key=attrgetter('listId','level','count'))
        #--Is merged list different from other? (And thus written to patch.)
        if ((len(self.entries) != len(other.entries)) or
            (self.flags != other.flags)
            ):
            self.mergeOverLast = True
        else:
            for attr in self.__class__.copyAttrs:
                if self.__getattribute__(attr) != other.__getattribute__(attr):
                    self.mergeOverLast = True
                    break
            else:
                otherlist = other.entries
                otherlist.sort(key=attrgetter('listId','level','count'))
                for selfEntry,otherEntry in zip(self.entries,otherlist):
                    if (selfEntry.listId != otherEntry.listId or
                        selfEntry.level != otherEntry.level or
                        selfEntry.count != otherEntry.count):
                        self.mergeOverLast = True
                        break
                else:
                    self.mergeOverLast = False
        if self.mergeOverLast:
            self.mergeSources.append(otherMod)
        else:
            self.mergeSources = [otherMod]
        #--Done
        self.setChanged(self.mergeOverLast)

class MreDial(MelRecord):
    """Dialog record."""
    classType = 'DIAL'
    __slots__ = ['infoStamp', 'infoStamp2', 'infos']

    def __init__(self, header, ins=None, do_unpack=False):
        """Initialize."""
        MelRecord.__init__(self, header, ins, do_unpack)
        self.infoStamp = 0 #--Stamp for info GRUP
        self.infoStamp2 = 0 #--Stamp for info GRUP
        self.infos = []

    def loadInfos(self, ins, endPos, infoClass):
        """Load infos from ins. Called from MobDials."""
        read_header = ins.unpackRecHeader
        ins_at_end = ins.atEnd
        append_info = self.infos.append
        while not ins_at_end(endPos, 'INFO Block'):
            #--Get record info and handle it
            header = read_header()
            if header.recType == 'INFO':
                append_info(infoClass(header, ins, True))
            else:
                raise exception.ModError(ins.inName,
                  _(u'Unexpected %s record in %s group.') % (
                                             header.recType, u'INFO'))

    def dump(self,out):
        """Dumps self., then group header and then records."""
        MreRecord.dump(self,out)
        if not self.infos: return
        header_size = RecordHeader.rec_header_size
        dial_size = header_size + sum([header_size + info.getSize()
                                       for info in self.infos])
        # Not all pack targets may be needed - limit the unpacked amount to the
        # number of specified GRUP format entries
        pack_targets = ['GRUP', dial_size, self.fid, 7, self.infoStamp,
                        self.infoStamp2]
        out.pack(RecordHeader.rec_pack_format_str,
                 *pack_targets[:len(RecordHeader.rec_pack_format)])
        for info in self.infos: info.dump(out)

    def updateMasters(self,masters):
        """Updates set of master names according to masters actually used."""
        MelRecord.updateMasters(self,masters)
        for info in self.infos:
            info.updateMasters(masters)

    def convertFids(self,mapper,toLong):
        """Converts fids between formats according to mapper.
        toLong should be True if converting to long format or False if
        converting to short format."""
        MelRecord.convertFids(self,mapper,toLong)
        for info in self.infos:
            info.convertFids(mapper,toLong)

#------------------------------------------------------------------------------
# Skyrim and Fallout ----------------------------------------------------------
#------------------------------------------------------------------------------
class MelMODS(MelBase):
    """MODS/MO2S/etc/DMDS subrecord"""
    def hasFids(self,formElements):
        """Include self if has fids."""
        formElements.add(self)

    def setDefault(self,record):
        """Sets default value for record instance."""
        record.__setattr__(self.attr,None)

    def loadData(self, record, ins, sub_type, size_, readId):
        """Reads data from ins into record attribute."""
        insUnpack = ins.unpack
        insRead32 = ins.readString32
        count, = insUnpack('I',4,readId)
        data = []
        dataAppend = data.append
        for x in xrange(count):
            string = insRead32(readId)
            fid = ins.unpackRef()
            index, = insUnpack('I',4,readId)
            dataAppend((string,fid,index))
        record.__setattr__(self.attr,data)

    def dumpData(self,record,out):
        """Dumps data from record to outstream."""
        data = record.__getattribute__(self.attr)
        if data is not None:
            data = record.__getattribute__(self.attr)
            outData = struct_pack('I', len(data))
            for (string,fid,index) in data:
                outData += struct_pack('I', len(string))
                outData += encode(string)
                outData += struct_pack('=2I', fid, index)
            out.packSub(self.subType,outData)

    def mapFids(self,record,function,save=False):
        """Applies function to fids.  If save is true, then fid is set
           to result of function."""
        attr = self.attr
        data = record.__getattribute__(attr)
        if data is not None:
            data = [(string,function(fid),index) for (string,fid,index) in record.__getattribute__(attr)]
            if save: record.__setattr__(attr,data)

##: Ripped from bush.py may belong to game/
# Magic Info ------------------------------------------------------------------
_magicEffects = {
    'ABAT': [5,_(u'Absorb Attribute'),0.95],
    'ABFA': [5,_(u'Absorb Fatigue'),6],
    'ABHE': [5,_(u'Absorb Health'),16],
    'ABSK': [5,_(u'Absorb Skill'),2.1],
    'ABSP': [5,_(u'Absorb Magicka'),7.5],
    'BA01': [1,_(u'Bound Armor Extra 01'),0],#--Formid == 0
    'BA02': [1,_(u'Bound Armor Extra 02'),0],#--Formid == 0
    'BA03': [1,_(u'Bound Armor Extra 03'),0],#--Formid == 0
    'BA04': [1,_(u'Bound Armor Extra 04'),0],#--Formid == 0
    'BA05': [1,_(u'Bound Armor Extra 05'),0],#--Formid == 0
    'BA06': [1,_(u'Bound Armor Extra 06'),0],#--Formid == 0
    'BA07': [1,_(u'Bound Armor Extra 07'),0],#--Formid == 0
    'BA08': [1,_(u'Bound Armor Extra 08'),0],#--Formid == 0
    'BA09': [1,_(u'Bound Armor Extra 09'),0],#--Formid == 0
    'BA10': [1,_(u'Bound Armor Extra 10'),0],#--Formid == 0
    'BABO': [1,_(u'Bound Boots'),12],
    'BACU': [1,_(u'Bound Cuirass'),12],
    'BAGA': [1,_(u'Bound Gauntlets'),8],
    'BAGR': [1,_(u'Bound Greaves'),12],
    'BAHE': [1,_(u'Bound Helmet'),12],
    'BASH': [1,_(u'Bound Shield'),12],
    'BRDN': [0,_(u'Burden'),0.21],
    'BW01': [1,_(u'Bound Order Weapon 1'),1],
    'BW02': [1,_(u'Bound Order Weapon 2'),1],
    'BW03': [1,_(u'Bound Order Weapon 3'),1],
    'BW04': [1,_(u'Bound Order Weapon 4'),1],
    'BW05': [1,_(u'Bound Order Weapon 5'),1],
    'BW06': [1,_(u'Bound Order Weapon 6'),1],
    'BW07': [1,_(u'Summon Staff of Sheogorath'),1],
    'BW08': [1,_(u'Bound Priest Dagger'),1],
    'BW09': [1,_(u'Bound Weapon Extra 09'),0],#--Formid == 0
    'BW10': [1,_(u'Bound Weapon Extra 10'),0],#--Formid == 0
    'BWAX': [1,_(u'Bound Axe'),39],
    'BWBO': [1,_(u'Bound Bow'),95],
    'BWDA': [1,_(u'Bound Dagger'),14],
    'BWMA': [1,_(u'Bound Mace'),91],
    'BWSW': [1,_(u'Bound Sword'),235],
    'CALM': [3,_(u'Calm'),0.47],
    'CHML': [3,_(u'Chameleon'),0.63],
    'CHRM': [3,_(u'Charm'),0.2],
    'COCR': [3,_(u'Command Creature'),0.6],
    'COHU': [3,_(u'Command Humanoid'),0.75],
    'CUDI': [5,_(u'Cure Disease'),1400],
    'CUPA': [5,_(u'Cure Paralysis'),500],
    'CUPO': [5,_(u'Cure Poison'),600],
    'DARK': [3,_(u'DO NOT USE - Darkness'),0],
    'DEMO': [3,_(u'Demoralize'),0.49],
    'DGAT': [2,_(u'Damage Attribute'),100],
    'DGFA': [2,_(u'Damage Fatigue'),4.4],
    'DGHE': [2,_(u'Damage Health'),12],
    'DGSP': [2,_(u'Damage Magicka'),2.45],
    'DIAR': [2,_(u'Disintegrate Armor'),6.2],
    'DISE': [2,_(u'Disease Info'),0], #--Formid == 0
    'DIWE': [2,_(u'Disintegrate Weapon'),6.2],
    'DRAT': [2,_(u'Drain Attribute'),0.7],
    'DRFA': [2,_(u'Drain Fatigue'),0.18],
    'DRHE': [2,_(u'Drain Health'),0.9],
    'DRSK': [2,_(u'Drain Skill'),0.65],
    'DRSP': [2,_(u'Drain Magicka'),0.18],
    'DSPL': [4,_(u'Dispel'),3.6],
    'DTCT': [4,_(u'Detect Life'),0.08],
    'DUMY': [2,_(u'Mehrunes Dagon'),0], #--Formid == 0
    'FIDG': [2,_(u'Fire Damage'),7.5],
    'FISH': [0,_(u'Fire Shield'),0.95],
    'FOAT': [5,_(u'Fortify Attribute'),0.6],
    'FOFA': [5,_(u'Fortify Fatigue'),0.04],
    'FOHE': [5,_(u'Fortify Health'),0.14],
    'FOMM': [5,_(u'Fortify Magicka Multiplier'),0.04],
    'FOSK': [5,_(u'Fortify Skill'),0.6],
    'FOSP': [5,_(u'Fortify Magicka'),0.15],
    'FRDG': [2,_(u'Frost Damage'),7.4],
    'FRNZ': [3,_(u'Frenzy'),0.04],
    'FRSH': [0,_(u'Frost Shield'),0.95],
    'FTHR': [0,_(u'Feather'),0.1],
    'INVI': [3,_(u'Invisibility'),40],
    'LGHT': [3,_(u'Light'),0.051],
    'LISH': [0,_(u'Shock Shield'),0.95],
    'LOCK': [0,_(u'DO NOT USE - Lock'),30],
    'MYHL': [1,_(u'Summon Mythic Dawn Helm'),110],
    'MYTH': [1,_(u'Summon Mythic Dawn Armor'),120],
    'NEYE': [3,_(u'Night-Eye'),22],
    'OPEN': [0,_(u'Open'),4.3],
    'PARA': [3,_(u'Paralyze'),475],
    'POSN': [2,_(u'Poison Info'),0],
    'RALY': [3,_(u'Rally'),0.03],
    'REAN': [1,_(u'Reanimate'),10],
    'REAT': [5,_(u'Restore Attribute'),38],
    'REDG': [4,_(u'Reflect Damage'),2.5],
    'REFA': [5,_(u'Restore Fatigue'),2],
    'REHE': [5,_(u'Restore Health'),10],
    'RESP': [5,_(u'Restore Magicka'),2.5],
    'RFLC': [4,_(u'Reflect Spell'),3.5],
    'RSDI': [5,_(u'Resist Disease'),0.5],
    'RSFI': [5,_(u'Resist Fire'),0.5],
    'RSFR': [5,_(u'Resist Frost'),0.5],
    'RSMA': [5,_(u'Resist Magic'),2],
    'RSNW': [5,_(u'Resist Normal Weapons'),1.5],
    'RSPA': [5,_(u'Resist Paralysis'),0.75],
    'RSPO': [5,_(u'Resist Poison'),0.5],
    'RSSH': [5,_(u'Resist Shock'),0.5],
    'RSWD': [5,_(u'Resist Water Damage'),0], #--Formid == 0
    'SABS': [4,_(u'Spell Absorption'),3],
    'SEFF': [0,_(u'Script Effect'),0],
    'SHDG': [2,_(u'Shock Damage'),7.8],
    'SHLD': [0,_(u'Shield'),0.45],
    'SLNC': [3,_(u'Silence'),60],
    'STMA': [2,_(u'Stunted Magicka'),0],
    'STRP': [4,_(u'Soul Trap'),30],
    'SUDG': [2,_(u'Sun Damage'),9],
    'TELE': [4,_(u'Telekinesis'),0.49],
    'TURN': [1,_(u'Turn Undead'),0.083],
    'VAMP': [2,_(u'Vampirism'),0],
    'WABR': [0,_(u'Water Breathing'),14.5],
    'WAWA': [0,_(u'Water Walking'),13],
    'WKDI': [2,_(u'Weakness to Disease'),0.12],
    'WKFI': [2,_(u'Weakness to Fire'),0.1],
    'WKFR': [2,_(u'Weakness to Frost'),0.1],
    'WKMA': [2,_(u'Weakness to Magic'),0.25],
    'WKNW': [2,_(u'Weakness to Normal Weapons'),0.25],
    'WKPO': [2,_(u'Weakness to Poison'),0.1],
    'WKSH': [2,_(u'Weakness to Shock'),0.1],
    'Z001': [1,_(u'Summon Rufio\'s Ghost'),13],
    'Z002': [1,_(u'Summon Ancestor Guardian'),33.3],
    'Z003': [1,_(u'Summon Spiderling'),45],
    'Z004': [1,_(u'Summon Flesh Atronach'),1],
    'Z005': [1,_(u'Summon Bear'),47.3],
    'Z006': [1,_(u'Summon Gluttonous Hunger'),61],
    'Z007': [1,_(u'Summon Ravenous Hunger'),123.33],
    'Z008': [1,_(u'Summon Voracious Hunger'),175],
    'Z009': [1,_(u'Summon Dark Seducer'),1],
    'Z010': [1,_(u'Summon Golden Saint'),1],
    'Z011': [1,_(u'Wabba Summon'),0],
    'Z012': [1,_(u'Summon Decrepit Shambles'),45],
    'Z013': [1,_(u'Summon Shambles'),87.5],
    'Z014': [1,_(u'Summon Replete Shambles'),150],
    'Z015': [1,_(u'Summon Hunger'),22],
    'Z016': [1,_(u'Summon Mangled Flesh Atronach'),22],
    'Z017': [1,_(u'Summon Torn Flesh Atronach'),32.5],
    'Z018': [1,_(u'Summon Stitched Flesh Atronach'),75.5],
    'Z019': [1,_(u'Summon Sewn Flesh Atronach'),195],
    'Z020': [1,_(u'Extra Summon 20'),0],
    'ZCLA': [1,_(u'Summon Clannfear'),75.56],
    'ZDAE': [1,_(u'Summon Daedroth'),123.33],
    'ZDRE': [1,_(u'Summon Dremora'),72.5],
    'ZDRL': [1,_(u'Summon Dremora Lord'),157.14],
    'ZFIA': [1,_(u'Summon Flame Atronach'),45],
    'ZFRA': [1,_(u'Summon Frost Atronach'),102.86],
    'ZGHO': [1,_(u'Summon Ghost'),22],
    'ZHDZ': [1,_(u'Summon Headless Zombie'),56],
    'ZLIC': [1,_(u'Summon Lich'),350],
    'ZSCA': [1,_(u'Summon Scamp'),30],
    'ZSKA': [1,_(u'Summon Skeleton Guardian'),32.5],
    'ZSKC': [1,_(u'Summon Skeleton Champion'),152],
    'ZSKE': [1,_(u'Summon Skeleton'),11.25],
    'ZSKH': [1,_(u'Summon Skeleton Hero'),66],
    'ZSPD': [1,_(u'Summon Spider Daedra'),195],
    'ZSTA': [1,_(u'Summon Storm Atronach'),125],
    'ZWRA': [1,_(u'Summon Faded Wraith'),87.5],
    'ZWRL': [1,_(u'Summon Gloom Wraith'),260],
    'ZXIV': [1,_(u'Summon Xivilai'),200],
    'ZZOM': [1,_(u'Summon Zombie'),16.67],
    }
_strU = struct.Struct('I').unpack
mgef_school = dict((x, y) for x, [y, z, _num] in _magicEffects.items())
mgef_name = dict((x, z) for x, [y, z, __num] in _magicEffects.items())
_mgef_basevalue = dict((x, a) for x, [y, z, a] in _magicEffects.items())
mgef_school.update({_strU(x)[0]:y for x,[y,z,a] in _magicEffects.items()})
mgef_name.update({_strU(x)[0]:z for x,[y,z,a] in _magicEffects.items()})
_mgef_basevalue.update(
    {_strU(x)[0]: a for x, [y, z, a] in _magicEffects.items()})

#Doesn't list mgefs that use actor values, but rather mgefs that have a generic name
#Ex: Absorb Attribute becomes Absorb Magicka if the effect's actorValue field contains 9
#    But it is actually using an attribute rather than an actor value
#Ex: Burden uses an actual actor value (encumbrance) but it isn't listed since its name doesn't change
genericAVEffects = {
    'ABAT', #--Absorb Attribute (Use Attribute)
    'ABSK', #--Absorb Skill (Use Skill)
    'DGAT', #--Damage Attribute (Use Attribute)
    'DRAT', #--Drain Attribute (Use Attribute)
    'DRSK', #--Drain Skill (Use Skill)
    'FOAT', #--Fortify Attribute (Use Attribute)
    'FOSK', #--Fortify Skill (Use Skill)
    'REAT', #--Restore Attribute (Use Attribute)
    }
genericAVEffects |= set((_strU(x)[0] for x in genericAVEffects))

actorValues = [
    _(u'Strength'), #--00
    _(u'Intelligence'),
    _(u'Willpower'),
    _(u'Agility'),
    _(u'Speed'),
    _(u'Endurance'),
    _(u'Personality'),
    _(u'Luck'),
    _(u'Health'),
    _(u'Magicka'),

    _(u'Fatigue'), #--10
    _(u'Encumbrance'),
    _(u'Armorer'),
    _(u'Athletics'),
    _(u'Blade'),
    _(u'Block'),
    _(u'Blunt'),
    _(u'Hand To Hand'),
    _(u'Heavy Armor'),
    _(u'Alchemy'),

    _(u'Alteration'), #--20
    _(u'Conjuration'),
    _(u'Destruction'),
    _(u'Illusion'),
    _(u'Mysticism'),
    _(u'Restoration'),
    _(u'Acrobatics'),
    _(u'Light Armor'),
    _(u'Marksman'),
    _(u'Mercantile'),

    _(u'Security'), #--30
    _(u'Sneak'),
    _(u'Speechcraft'),
    u'Aggression',
    u'Confidence',
    u'Energy',
    u'Responsibility',
    u'Bounty',
    u'UNKNOWN 38',
    u'UNKNOWN 39',

    u'MagickaMultiplier', #--40
    u'NightEyeBonus',
    u'AttackBonus',
    u'DefendBonus',
    u'CastingPenalty',
    u'Blindness',
    u'Chameleon',
    u'Invisibility',
    u'Paralysis',
    u'Silence',

    u'Confusion', #--50
    u'DetectItemRange',
    u'SpellAbsorbChance',
    u'SpellReflectChance',
    u'SwimSpeedMultiplier',
    u'WaterBreathing',
    u'WaterWalking',
    u'StuntedMagicka',
    u'DetectLifeRange',
    u'ReflectDamage',

    u'Telekinesis', #--60
    u'ResistFire',
    u'ResistFrost',
    u'ResistDisease',
    u'ResistMagic',
    u'ResistNormalWeapons',
    u'ResistParalysis',
    u'ResistPoison',
    u'ResistShock',
    u'Vampirism',

    u'Darkness', #--70
    u'ResistWaterDamage',
    ]

#------------------------------------------------------------------------------
class MreHasEffects: #(object): # this alone doesn't break MreSpel
    """Mixin class for magic items."""
    ##: __slots__ = [] # MreSpel.flags should be renamed to _flags

    def getEffects(self):
        """Returns a summary of effects. Useful for alchemical catalog."""
        effects = []
        effectsAppend = effects.append
        for effect in self.effects:
            mgef, actorValue = effect.name, effect.actorValue
            if mgef not in genericAVEffects:
                actorValue = 0
            effectsAppend((mgef,actorValue))
        return effects

    def getSpellSchool(self):
        """Returns the school based on the highest cost spell effect."""
        spellSchool = [0,0]
        for effect in self.effects:
            school = mgef_school[effect.name]
            effectValue = _mgef_basevalue[effect.name]
            if effect.magnitude:
                effectValue *=  effect.magnitude
            if effect.area:
                effectValue *=  (effect.area/10)
            if effect.duration:
                effectValue *=  effect.duration
            if spellSchool[0] < effectValue:
                spellSchool = [effectValue,school]
        return spellSchool[1]

    def getEffectsSummary(self):
        """Return a text description of magic effects."""
        with sio() as buff:
            avEffects = genericAVEffects
            aValues = actorValues
            buffWrite = buff.write
            if self.effects:
                school = self.getSpellSchool()
                buffWrite(actorValues[20+school] + u'\n')
            for index,effect in enumerate(self.effects):
                if effect.scriptEffect:
                    effectName = effect.scriptEffect.full or u'Script Effect'
                else:
                    effectName = mgef_name[effect.name]
                    if effect.name in avEffects:
                        effectName = re.sub(_(u'(Attribute|Skill)'),aValues[effect.actorValue],effectName)
                buffWrite(u'o+*'[effect.recipient]+u' '+effectName)
                if effect.magnitude: buffWrite(u' %sm'%effect.magnitude)
                if effect.area: buffWrite(u' %sa'%effect.area)
                if effect.duration > 1: buffWrite(u' %sd'%effect.duration)
                buffWrite(u'\n')
            return buff.getvalue()

hostileEffects = {
    'ABAT', #--Absorb Attribute
    'ABFA', #--Absorb Fatigue
    'ABHE', #--Absorb Health
    'ABSK', #--Absorb Skill
    'ABSP', #--Absorb Magicka
    'BRDN', #--Burden
    'DEMO', #--Demoralize
    'DGAT', #--Damage Attribute
    'DGFA', #--Damage Fatigue
    'DGHE', #--Damage Health
    'DGSP', #--Damage Magicka
    'DIAR', #--Disintegrate Armor
    'DIWE', #--Disintegrate Weapon
    'DRAT', #--Drain Attribute
    'DRFA', #--Drain Fatigue
    'DRHE', #--Drain Health
    'DRSK', #--Drain Skill
    'DRSP', #--Drain Magicka
    'FIDG', #--Fire Damage
    'FRDG', #--Frost Damage
    'FRNZ', #--Frenzy
    'PARA', #--Paralyze
    'SHDG', #--Shock Damage
    'SLNC', #--Silence
    'STMA', #--Stunted Magicka
    'STRP', #--Soul Trap
    'SUDG', #--Sun Damage
    'TURN', #--Turn Undead
    'WKDI', #--Weakness to Disease
    'WKFI', #--Weakness to Fire
    'WKFR', #--Weakness to Frost
    'WKMA', #--Weakness to Magic
    'WKNW', #--Weakness to Normal Weapons
    'WKPO', #--Weakness to Poison
    'WKSH', #--Weakness to Shock
    }
hostileEffects |= set((_strU(x)[0] for x in hostileEffects))

#--Cleanup --------------------------------------------------------------------
#------------------------------------------------------------------------------
del _strU
