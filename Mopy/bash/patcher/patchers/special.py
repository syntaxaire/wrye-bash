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
import collections
import copy
import string
from operator import itemgetter, attrgetter
# Internal
from .base import Patcher, CBash_Patcher, SpecialPatcher, ListPatcher, \
    CBash_ListPatcher, AListPatcher
from ... import bosh, load_order  # for modInfos
from ... import bush
from ...bolt import GPath, SubProgress
from ...cint import FormID

# Patchers: 40 ----------------------------------------------------------------
class _AListsMerger(SpecialPatcher, AListPatcher):
    """Merged leveled lists mod file."""
    scanOrder = 45
    editOrder = 45
    name = _(u'Leveled Lists')
    text = (_(
        u"Merges changes to leveled lists from ACTIVE/MERGED MODS ONLY.") +
            u'\n\n' + _(
        u'Advanced users may override Relev/Delev tags for any mod (active '
        u'or inactive) using the list below.'))
    tip = _(u"Merges changes to leveled lists from all active mods.")
    autoKey = {u'Delev', u'Relev'}
    iiMode = True

class ListsMerger(_AListsMerger, ListPatcher):

    #--Patch Phase ------------------------------------------------------------
    def initPatchFile(self, patchFile):
        super(ListsMerger, self).initPatchFile(patchFile)
        self.srcs_ordered = self.srcs
        self.srcs = set(self.srcs) & patchFile.loadSet
        self.listTypes = bush.game.listTypes
        self.type_list = dict([(type,{}) for type in self.listTypes])
        self.masterItems = {}
        self.mastersScanned = set()
        self.levelers = None #--Will initialize later
        self.empties = set()
        OverhaulCompat = False
        OOOMods = {GPath(u"Oscuro's_Oblivion_Overhaul.esm"),
                   GPath(u"Oscuro's_Oblivion_Overhaul.esp")}
        FransMods = {GPath(u"Francesco's Leveled Creatures-Items Mod.esm"),
                     GPath(u"Francesco.esp")}
        WCMods = {GPath(u"Oblivion Warcry.esp"),
                  GPath(u"Oblivion Warcry EV.esp")}
        TIEMods = {GPath(u"TIE.esp")}
        if GPath(u"Unofficial Oblivion Patch.esp") in self.srcs:
            if (OOOMods|WCMods) & self.srcs:
                OverhaulCompat = True
            elif FransMods & self.srcs:
                if TIEMods & self.srcs:
                    pass
                else:
                    OverhaulCompat = True
        if OverhaulCompat:
            self.OverhaulUOPSkips = set([
                (GPath(u'Oblivion.esm'),x) for x in [
                    0x03AB5D,   # VendorWeaponBlunt
                    0x03C7F1,   # LL0LootWeapon0Magic4Dwarven100
                    0x03C7F2,   # LL0LootWeapon0Magic7Ebony100
                    0x03C7F3,   # LL0LootWeapon0Magic5Elven100
                    0x03C7F4,   # LL0LootWeapon0Magic6Glass100
                    0x03C7F5,   # LL0LootWeapon0Magic3Silver100
                    0x03C7F7,   # LL0LootWeapon0Magic2Steel100
                    0x03E4D2,   # LL0NPCWeapon0MagicClaymore100
                    0x03E4D3,   # LL0NPCWeapon0MagicClaymoreLvl100
                    0x03E4DA,   # LL0NPCWeapon0MagicWaraxe100
                    0x03E4DB,   # LL0NPCWeapon0MagicWaraxeLvl100
                    0x03E4DC,   # LL0NPCWeapon0MagicWarhammer100
                    0x03E4DD,   # LL0NPCWeapon0MagicWarhammerLvl100
                    0x0733EA,   # ArenaLeveledHeavyShield,
                    0x0C7615,   # FGNPCWeapon0MagicClaymoreLvl100
                    0x181C66,   # SQ02LL0NPCWeapon0MagicClaymoreLvl100
                    0x053877,   # LL0NPCArmor0MagicLightGauntlets100
                    0x053878,   # LL0NPCArmor0MagicLightBoots100
                    0x05387A,   # LL0NPCArmor0MagicLightCuirass100
                    0x053892,   # LL0NPCArmor0MagicLightBootsLvl100
                    0x053893,   # LL0NPCArmor0MagicLightCuirassLvl100
                    0x053894,   # LL0NPCArmor0MagicLightGauntletsLvl100
                    0x053D82,   # LL0LootArmor0MagicLight5Elven100
                    0x053D83,   # LL0LootArmor0MagicLight6Glass100
                    0x052D89,   # LL0LootArmor0MagicLight4Mithril100
                    ]
                ])
        else:
            self.OverhaulUOPSkips = set()

    def getReadClasses(self):
        """Returns load factory classes needed for reading."""
        return self.listTypes

    def getWriteClasses(self):
        """Returns load factory classes needed for writing."""
        return self.listTypes

    def scanModFile(self, modFile, progress):
        """Add lists from modFile."""
        #--Level Masters (complete initialization)
        if self.levelers is None:
            self.levelers = [leveler for leveler in self.srcs_ordered if
                             leveler in self.patchFile.allSet]
            self.delevMasters = set()
            for leveler in self.levelers:
                self.delevMasters.update(bosh.modInfos[leveler].get_masters())
        #--Begin regular scan
        modName = modFile.fileInfo.name
        modFile.convertToLongFids(self.listTypes)
        #--PreScan for later Relevs/Delevs?
        if modName in self.delevMasters:
            for list_type in self.listTypes:
                for levList in getattr(modFile,list_type).getActiveRecords():
                    masterItems = self.masterItems.setdefault(levList.fid,{})
                    masterItems[modName] = set(
                        [entry.listId for entry in levList.entries])
            self.mastersScanned.add(modName)
        #--Relev/Delev setup
        configChoice = self.configChoices.get(modName,tuple())
        isRelev = (u'Relev' in configChoice)
        isDelev = (u'Delev' in configChoice)
        #--Scan
        for list_type in self.listTypes:
            levLists = self.type_list[list_type]
            newLevLists = getattr(modFile,list_type)
            for newLevList in newLevLists.getActiveRecords():
                listId = newLevList.fid
                if listId in self.OverhaulUOPSkips and modName == \
                        u'Unofficial Oblivion Patch.esp':
                    levLists[listId].mergeOverLast = True
                    continue
                isListOwner = (listId[0] == modName)
                #--Items, delevs and relevs sets
                newLevList.items = items = set(
                    [entry.listId for entry in newLevList.entries])
                if not isListOwner:
                    #--Relevs
                    newLevList.relevs = items.copy() if isRelev else set()
                    #--Delevs: all items in masters minus current items
                    newLevList.delevs = delevs = set()
                    if isDelev:
                        id_masterItems = self.masterItems.get(listId)
                        if id_masterItems:
                            for mastername in modFile.tes4.masters:
                                if mastername in id_masterItems:
                                    delevs |= id_masterItems[mastername]
                            delevs -= items
                            newLevList.items |= delevs
                #--Cache/Merge
                if isListOwner:
                    levList = copy.deepcopy(newLevList)
                    levList.mergeSources = []
                    levLists[listId] = levList
                elif listId not in levLists:
                    levList = copy.deepcopy(newLevList)
                    levList.mergeSources = [modName]
                    levLists[listId] = levList
                else:
                    levLists[listId].mergeWith(newLevList,modName)

    def buildPatch(self,log,progress):
        """Adds merged lists to patchfile."""
        keep = self.patchFile.getKeeper()
        #--Relevs/Delevs List
        log.setHeader(u'= '+self.__class__.name,True)
        log.setHeader(u'=== '+_(u'Delevelers/Relevelers'))
        for leveler in (self.levelers or []):
            log(u'* '+self.getItemLabel(leveler))
        #--Save to patch file
        for label, type in ((_(u'Creature'), 'LVLC'), (_(u'Actor'), 'LVLN'),
                (_(u'Item'), 'LVLI'), (_(u'Spell'), 'LVSP')):
            if type not in self.listTypes: continue
            log.setHeader(u'=== '+_(u'Merged %s Lists') % label)
            patchBlock = getattr(self.patchFile,type)
            levLists = self.type_list[type]
            for record in sorted(levLists.values(),key=attrgetter('eid')):
                if not record.mergeOverLast: continue
                fid = keep(record.fid)
                patchBlock.setRecord(levLists[fid])
                log(u'* '+record.eid)
                for mod in record.mergeSources:
                    log(u'  * ' + self.getItemLabel(mod))
        #--Discard empty sublists
        for label, type in ((_(u'Creature'), 'LVLC'), (_(u'Actor'), 'LVLN'),
                (_(u'Item'), 'LVLI'), (_(u'Spell'), 'LVSP')):
            if type not in self.listTypes: continue
            patchBlock = getattr(self.patchFile,type)
            levLists = self.type_list[type]
            #--Empty lists
            empties = []
            sub_supers = dict((x,[]) for x in levLists.keys())
            for record in sorted(levLists.values()):
                listId = record.fid
                if not record.items:
                    empties.append(listId)
                else:
                    subLists = [x for x in record.items if x in sub_supers]
                    for subList in subLists:
                        sub_supers[subList].append(listId)
            #--Clear empties
            removed = set()
            cleaned = set()
            while empties:
                empty = empties.pop()
                if empty not in sub_supers: continue
                for super in sub_supers[empty]:
                    record = levLists[super]
                    record.entries = [x for x in record.entries if
                                      x.listId != empty]
                    record.items.remove(empty)
                    patchBlock.setRecord(record)
                    if not record.items:
                        empties.append(super)
                    cleaned.add(record.eid)
                    removed.add(levLists[empty].eid)
                    keep(super)
            log.setHeader(u'=== '+_(u'Empty %s Sublists') % label)
            for eid in sorted(removed,key=string.lower):
                log(u'* '+eid)
            log.setHeader(u'=== '+_(u'Empty %s Sublists Removed') % label)
            for eid in sorted(cleaned,key=string.lower):
                log(u'* '+eid)

class CBash_ListsMerger(_AListsMerger, CBash_ListPatcher):
    allowUnloaded = False
    scanRequiresChecked = False
    applyRequiresChecked = False

    #--Patch Phase -----------------------------------------------------------
    def initPatchFile(self, patchFile):
        super(CBash_ListsMerger, self).initPatchFile(patchFile)
        self.isActive = True
        self.id_delevs = {}
        self.id_list = {}
        self.id_attrs = {}
        self.empties = set()
        importMods = set(self.srcs) & patchFile.loadSet
        OverhaulCompat = False
        OOOMods = {GPath(u"Oscuro's_Oblivion_Overhaul.esm"),
                   GPath(u"Oscuro's_Oblivion_Overhaul.esp")}
        FransMods = {GPath(u"Francesco's Leveled Creatures-Items Mod.esm"),
                     GPath(u"Francesco.esp")}
        WCMods = {GPath(u"Oblivion Warcry.esp"),
                  GPath(u"Oblivion Warcry EV.esp")}
        TIEMods = {GPath(u"TIE.esp")}
        if GPath(u"Unofficial Oblivion Patch.esp") in importMods:
            if (OOOMods|WCMods) & importMods:
                OverhaulCompat = True
            elif FransMods & importMods:
                if TIEMods & importMods:
                    pass
                else:
                    OverhaulCompat = True
        if OverhaulCompat:
            self.OverhaulUOPSkips = set([
                FormID(GPath(u'Oblivion.esm'),x) for x in [
                    0x03AB5D,   # VendorWeaponBlunt
                    0x03C7F1,   # LL0LootWeapon0Magic4Dwarven100
                    0x03C7F2,   # LL0LootWeapon0Magic7Ebony100
                    0x03C7F3,   # LL0LootWeapon0Magic5Elven100
                    0x03C7F4,   # LL0LootWeapon0Magic6Glass100
                    0x03C7F5,   # LL0LootWeapon0Magic3Silver100
                    0x03C7F7,   # LL0LootWeapon0Magic2Steel100
                    0x03E4D2,   # LL0NPCWeapon0MagicClaymore100
                    0x03E4D3,   # LL0NPCWeapon0MagicClaymoreLvl100
                    0x03E4DA,   # LL0NPCWeapon0MagicWaraxe100
                    0x03E4DB,   # LL0NPCWeapon0MagicWaraxeLvl100
                    0x03E4DC,   # LL0NPCWeapon0MagicWarhammer100
                    0x03E4DD,   # LL0NPCWeapon0MagicWarhammerLvl100
                    0x0733EA,   # ArenaLeveledHeavyShield,
                    0x0C7615,   # FGNPCWeapon0MagicClaymoreLvl100
                    0x181C66,   # SQ02LL0NPCWeapon0MagicClaymoreLvl100
                    0x053877,   # LL0NPCArmor0MagicLightGauntlets100
                    0x053878,   # LL0NPCArmor0MagicLightBoots100
                    0x05387A,   # LL0NPCArmor0MagicLightCuirass100
                    0x053892,   # LL0NPCArmor0MagicLightBootsLvl100
                    0x053893,   # LL0NPCArmor0MagicLightCuirassLvl100
                    0x053894,   # LL0NPCArmor0MagicLightGauntletsLvl100
                    0x053D82,   # LL0LootArmor0MagicLight5Elven100
                    0x053D83,   # LL0LootArmor0MagicLight6Glass100
                    0x052D89,   # LL0LootArmor0MagicLight4Mithril100
                    ]
                ])
        else:
            self.OverhaulUOPSkips = set()

    def getTypes(self):
        return ['LVLC','LVLI','LVSP']

    #--Patch Phase ------------------------------------------------------------
    def scan(self,modFile,record,bashTags):
        """Records information needed to apply the patch."""
        recordId = record.fid
        if recordId in self.OverhaulUOPSkips and modFile.GName == GPath(
                'Unofficial Oblivion Patch.esp'):
            return
        script = record.script
        if script and not script.ValidateFormID(self.patchFile):
            script = None
        template = record.template
        if template and not template.ValidateFormID(self.patchFile):
            template = None
        curList = [(level, listId, count) for level, listId, count in
                   record.entries_list if
                   listId.ValidateFormID(self.patchFile)]
        if recordId not in self.id_list:
            #['level', 'listId', 'count']
            self.id_list[recordId] = curList
            self.id_attrs[recordId] = [record.chanceNone, script, template,
                                       (record.flags or 0)]
        else:
            mergedList = self.id_list[recordId]
            configChoice = self.configChoices.get(modFile.GName,tuple())
            isRelev = u'Relev' in configChoice
            isDelev = u'Delev' in configChoice
            delevs = self.id_delevs.setdefault(recordId, set())
            curItems = set([listId for level, listId, count in curList])
            if isRelev:
                # Can add and set the level/count of items, but not delete
                # items
                #Ironically, the first step is to delete items that the list
                #  will add right back
                #This is an easier way to update level/count than actually
                # checking if they need changing

                #Filter out any records that may have their level/count updated
                mergedList = [entry for entry in mergedList if
                              entry[1] not in curItems]  # entry[1] = listId
                #Add any new records as well as any that were filtered out
                mergedList += curList
                #Remove the added items from the deleveled list
                delevs -= curItems
                self.id_attrs[recordId] = [record.chanceNone, script, template,
                                           (record.flags or 0)]
            else:
                #Can add new items, but can't change existing ones
                items = set([entry[1] for entry in mergedList])  # entry[1]
                # = listId
                mergedList += [(level, listId, count) for level, listId, count
                               in curList if listId not in items]
                mergedAttrs = self.id_attrs[recordId]
                self.id_attrs[recordId] =[record.chanceNone or mergedAttrs[0],
                                         script or mergedAttrs[1],
                                         template or mergedAttrs[2],
                                         (record.flags or 0) | mergedAttrs[3]]
            #--Delevs: all items in masters minus current items
            if isDelev:
                deletedItems = set([listId for master in record.History() for
                                    level, listId, count in master.entries_list
                                    if listId.ValidateFormID(
                        self.patchFile)]) - curItems
                delevs |= deletedItems

            #Remove any items that were deleveled
            mergedList = [entry for entry in mergedList if
                          entry[1] not in delevs]  # entry[1] = listId
            self.id_list[recordId] = mergedList
            self.id_delevs[recordId] = delevs

    def apply(self,modFile,record,bashTags):
        """Edits patch file as desired."""
        recordId = record.fid
        merged_ = recordId in self.id_list
        if merged_:
            self.scan(modFile,record,bashTags)
            mergedList = self.id_list[recordId]
            mergedAttrs = self.id_attrs[recordId]
            newList = [(level, listId, count) for level, listId, count in
                       record.entries_list if
                       listId.ValidateFormID(self.patchFile)]
            script = record.script
            if script and not script.ValidateFormID(self.patchFile):
                script = None
            template = record.template
            if template and not template.ValidateFormID(self.patchFile):
                template = None
            newAttrs = [record.chanceNone, script, template,
                        (record.flags or 0)]
        # Can't tell if any sublists are actually empty until they've all
        # been processed/merged
        #So every level list gets copied into the patch, so that they can be
        #  checked after the regular patch process
        #They'll get deleted from the patch there as needed.
        override = record.CopyAsOverride(self.patchFile)
        if override:
            if merged_ and (newAttrs != mergedAttrs or sorted(newList,
                key=itemgetter(1)) != sorted(mergedList, key=itemgetter(1))):
                override.chanceNone, override.script, override.template, \
                override.flags = mergedAttrs
                override.entries_list = mergedList
                self.mod_count[modFile.GName] += 1
            record.UnloadRecord()
            record._RecordID = override._RecordID

    def finishPatch(self,patchFile, progress):
        """Edits the bashed patch file directly."""
        if self.empties is None: return
        subProgress = SubProgress(progress)
        subProgress.setFull(len(self.getTypes()))
        pstate = 0
        #Clean up any empty sublists
        empties = self.empties
        emptiesAdd = empties.add
        emptiesDiscard = empties.discard
        for type in self.getTypes():
            subProgress(pstate,
                        _(u'Looking for empty %s sublists...') % type + u'\n')
            #Remove any empty sublists
            madeChanges = True
            while madeChanges:
                madeChanges = False
                oldEmpties = empties.copy()
                for record in getattr(patchFile,type):
                    recordId = record.fid
                    items = set([entry.listId for entry in record.entries])
                    if items:
                        emptiesDiscard(recordId)
                    else:
                        emptiesAdd(recordId)
                    toRemove = empties & items
                    if toRemove:
                        madeChanges = True
                        cleanedEntries = [entry for entry in record.entries if
                                          entry.listId not in toRemove]
                        record.entries = cleanedEntries
                        if cleanedEntries:
                            emptiesDiscard(recordId)
                        else:
                            emptiesAdd(recordId)
                if oldEmpties != empties:
                    oldEmpties = empties.copy()
                    madeChanges = True

            # Remove any identical to winning lists, except those that were
            # merged into the patch
            for record in getattr(patchFile,type):
                conflicts = record.Conflicts()
                numConflicts = len(conflicts)
                if numConflicts:
                    curConflict = 1  # Conflict at 0 will be the patchfile.
                    # No sense comparing it to itself.
                    #Find the first conflicting record that wasn't merged
                    while curConflict < numConflicts:
                        prevRecord = conflicts[curConflict]
                        if prevRecord.GetParentMod().GName not in \
                                patchFile.mergeSet:
                            break
                        curConflict += 1
                    else:
                        continue
                    # If the record in the patchfile matches the previous
                    # non-merged record, delete it.
                    #Ordering doesn't matter, hence the conversion to sets
                    if set(prevRecord.entries_list) == set(
                            record.entries_list) and [record.chanceNone,
                                                      record.script,
                                                      record.template,
                                                      record.flags] == [
                        prevRecord.chanceNone, prevRecord.script,
                        prevRecord.template, prevRecord.flags]:
                        record.DeleteRecord()
            pstate += 1
        self.empties = None

    def buildPatchLog(self,log):
        """Will write to log."""
        #--Log
        mod_count = self.mod_count
        log.setHeader(u'= ' +self.__class__.name)
        log(u'* '+_(u'Modified LVL') + u': %d' % (sum(mod_count.values()),))
        for srcMod in load_order.get_ordered(mod_count.keys()):
            log(u'  * %s: %d' % (srcMod.s,mod_count[srcMod]))
        self.mod_count = collections.defaultdict(int)

#------------------------------------------------------------------------------
class FidListsMerger(_AListsMerger,ListPatcher):
    """Merged FormID lists mod file."""
    scanOrder = 46
    editOrder = 46
    name = _(u'FormID Lists')
    text = (_(u'Merges changes to formid lists from ACTIVE/MERGED MODS ONLY.') +
            u"\n\n" +
            _(u'Advanced users may override Deflst tags for any mod (active or inactive) using the list below.'))
    tip = _(u"Merges changes to formid lists from all active mods.")
    autoKey = {u'Deflst'}
    iiMode = True

    #--Patch Phase ------------------------------------------------------------
    def initPatchFile(self, patchFile):
        """Prepare to handle specified patch mod. All functions are called
        after this."""
        super(FidListsMerger, self).initPatchFile(patchFile)
        self.srcMods = set(self.getConfigChecked()) & patchFile.loadSet
        self.listTypes = ('FLST',)
        self.type_list = dict([(type,{}) for type in self.listTypes])
        self.masterItems = {}
        self.mastersScanned = set()
        self.levelers = None #--Will initialize later

    def getReadClasses(self):
        """Returns load factory classes needed for reading."""
        return self.listTypes

    def getWriteClasses(self):
        """Returns load factory classes needed for writing."""
        return self.listTypes

    def scanModFile(self, modFile, progress):
        """Add lists from modFile."""
        #--Level Masters (complete initialization)
        if self.levelers is None:
            self.levelers = [leveler for leveler in self.getConfigChecked() if
                             leveler in self.patchFile.allSet]
            self.deflstMasters = set()
            for leveler in self.levelers:
                self.deflstMasters.update(bosh.modInfos[leveler].get_masters())
        #--Begin regular scan
        modName = modFile.fileInfo.name
        modFile.convertToLongFids(self.listTypes)
        #--PreScan for later Deflsts?
        if modName in self.deflstMasters:
            for list_type in self.listTypes:
                for levList in getattr(modFile,list_type).getActiveRecords():
                    masterItems = self.masterItems.setdefault(levList.fid,{})
                    # masterItems[modName] = set([entry.listId for entry in levList.entries])
                    masterItems[modName] = set(levList.formIDInList)
            self.mastersScanned.add(modName)
        #--Deflst setup
        configChoice = self.configChoices.get(modName,tuple())
        isDeflst = (u'Deflst' in configChoice)
        #--Scan
        for list_type in self.listTypes:
            levLists = self.type_list[list_type]
            newLevLists = getattr(modFile,list_type)
            for newLevList in newLevLists.getActiveRecords():
                listId = newLevList.fid
                isListOwner = (listId[0] == modName)
                #--Items, deflsts sets
                # newLevList.items = items = set([entry.listId for entry in newLevList.entries])
                newLevList.items = items = set(newLevList.formIDInList)
                if not isListOwner:
                    #--Deflsts: all items in masters minus current items
                    newLevList.deflsts = deflsts = set()
                    if isDeflst:
                        id_masterItems = self.masterItems.get(listId)
                        if id_masterItems:
                            for mastername in modFile.tes4.masters:
                                if mastername in id_masterItems:
                                    deflsts |= id_masterItems[mastername]
                            deflsts -= items
                            newLevList.items |= deflsts
                #--Cache/Merge
                if isListOwner:
                    levList = copy.deepcopy(newLevList)
                    levList.mergeSources = []
                    levLists[listId] = levList
                elif listId not in levLists:
                    levList = copy.deepcopy(newLevList)
                    levList.mergeSources = [modName]
                    levLists[listId] = levList
                else:
                    levLists[listId].mergeWith(newLevList,modName)

    def buildPatch(self,log,progress):
        """Adds merged lists to patchfile."""
        keep = self.patchFile.getKeeper()
        #--Deflsts List
        log.setHeader(u'= '+self.__class__.name,True)
        log.setHeader(u'=== '+_(u'Deflsters'))
        for leveler in (self.levelers or []):
            log(u'* '+self.getItemLabel(leveler))
        #--Save to patch file
        type = u'FLST'
        log.setHeader(u'=== '+_(u'Merged %s Lists') % u'FormID')
        patchBlock = getattr(self.patchFile,type)
        levLists = self.type_list[type]
        for record in sorted(levLists.values(),key=attrgetter('eid')):
            if not record.mergeOverLast: continue
            fid = keep(record.fid)
            patchBlock.setRecord(levLists[fid])
            log(u'* '+record.eid)
            for mod in record.mergeSources:
                log(u'  * ' + self.getItemLabel(mod))

#------------------------------------------------------------------------------
class _AContentsChecker(SpecialPatcher):
    """Checks contents of leveled lists, inventories and containers for
    correct content types."""
    scanOrder = 50
    editOrder = 50
    name = _(u'Contents Checker')
    text = _(u"Checks contents of leveled lists, inventories and containers"
             u" for correct types.")
    contType_entryTypes = {
        'LVSP': {'LVSP', 'SPEL'},
        'LVLC': {'LVLC', 'NPC_', 'CREA'},
        #--LVLI will also be applied for containers.
        'LVLI': {'LVLI', 'ALCH', 'AMMO', 'APPA', 'ARMO', 'BOOK', 'CLOT',
                 'INGR', 'KEYM', 'LIGH', 'MISC', 'SGST', 'SLGM', 'WEAP'},
    }
    contType_entryTypes['CONT'] = contType_entryTypes['CREA'] = \
    contType_entryTypes['NPC_'] = contType_entryTypes['LVLI']
    #--Types
    contTypes = set(contType_entryTypes)
    entryTypes = reduce(set.union, contType_entryTypes.itervalues())

class ContentsChecker(_AContentsChecker,Patcher):

    #--Patch Phase ------------------------------------------------------------
    def initPatchFile(self, patchFile):
        super(ContentsChecker, self).initPatchFile(patchFile)
        self.id_type = {}
        self.id_eid = {}

    def getReadClasses(self):
        """Returns load factory classes needed for reading."""
        return tuple(self.contTypes | self.entryTypes) if self.isActive else ()

    def getWriteClasses(self):
        """Returns load factory classes needed for writing."""
        return tuple(self.contTypes) if self.isActive else ()

    def scanModFile(self, modFile, progress):
        """Scan modFile."""
        if not self.isActive: return
        mapper = modFile.getLongMapper()
        #--Remember types (only when first defined)
        id_type = self.id_type
        for entry_type in self.entryTypes:
            if entry_type not in modFile.tops: continue
            for record in modFile.tops[entry_type].getActiveRecords():
                fid = record.fid
                if not record.longFids: fid = mapper(fid)
                if fid not in id_type:
                    id_type[fid] = entry_type
##                if fid[0] == modName:
##                    id_type[fid] = entry_type
        #--Save container types
        modFile.convertToLongFids(self.contTypes)
        for cont_type in self.contTypes:
            if cont_type not in modFile.tops: continue
            patchBlock = getattr(self.patchFile, cont_type)
            id_records = patchBlock.id_records
            for record in modFile.tops[cont_type].getActiveRecords():
                if record.fid not in id_records:
                    patchBlock.setRecord(record.getTypeCopy(mapper))

    def buildPatch(self,log,progress):
        """Make changes to patchfile."""
        if not self.isActive: return
        modFile = self.patchFile
        keep = self.patchFile.getKeeper()
        id_type = self.id_type
        id_eid = self.id_eid
        log.setHeader('= '+self.__class__.name)
        #--Lists
        for cAttr,eAttr,types in (
            ('entries','listId',('LVSP','LVLI','LVLC')),
            ('items','item',('CONT','CREA','NPC_')),
            ):
            for rec_type in types:
                if rec_type not in modFile.tops: continue
                entryTypes = set(self.contType_entryTypes[rec_type])
                id_removed = {}
                for record in modFile.tops[rec_type].records:
                    newEntries = []
                    oldEntries = getattr(record,cAttr)
                    for entry in oldEntries:
                        entryId = getattr(entry,eAttr)
                        if id_type.get(entryId) in entryTypes:
                            newEntries.append(entry)
                        else:
                            removed = id_removed.setdefault(record.fid,[])
                            removed.append(entryId)
                            id_eid[record.fid] = record.eid
                    if len(newEntries) != len(oldEntries):
                        setattr(record,cAttr,newEntries)
                        keep(record.fid)
                #--Log it
                if id_removed:
                    log(u"\n=== " + rec_type)
                    for contId in sorted(id_removed):
                        log(u'* ' + id_eid[contId])
                        for removedId in sorted(id_removed[contId]):
                            mod,index = removedId
                            log(u'  . %s: %06X' % (mod.s,index))

class CBash_ContentsChecker(_AContentsChecker,CBash_Patcher):
    srcs = []  # so as not to fail screaming when determining load mods - but
    # with the least processing required.

    #--Config Phase -----------------------------------------------------------
    def initPatchFile(self, patchFile):
        super(CBash_ContentsChecker, self).initPatchFile(patchFile)
        self.isActive = True
        self.listTypes = {'LVSP', 'LVLC', 'LVLI'}
        self.containerTypes = {'CONT', 'CREA', 'NPC_'}
        self.mod_type_id_badEntries = {}
        self.knownGood = set()

    def getTypes(self):
        """Returns the group types that this patcher checks"""
        return ['CONT','CREA','NPC_','LVLI','LVLC','LVSP']

    #--Patch Phase ------------------------------------------------------------
    def apply(self,modFile,record,bashTags):
        """Edits patch file as desired."""
        rec_type = record._Type
        Current = self.patchFile.Current
        badEntries = set()
        goodEntries = []
        knownGood = self.knownGood
        knownGoodAdd = knownGood.add
        goodAppend = goodEntries.append
        badAdd = badEntries.add
        validEntries = self.contType_entryTypes[rec_type]
        if rec_type in self.listTypes:
            topattr, subattr = ('entries','listId')
        else: #Is a container type
            topattr, subattr = ('items','item')

        for entry in getattr(record,topattr):
            entryId = getattr(entry,subattr)
            #Cache known good entries to decrease execution time
            if entryId in knownGood:
                goodAppend(entry)
            else:
                if entryId.ValidateFormID(self.patchFile):
                    entryRecords = Current.LookupRecords(entryId)
                else:
                    entryRecords = None
                if not entryRecords:
                    badAdd((_(u'NONE'),entryId,None,_(u'NONE')))
                else:
                    entryRecord = entryRecords[0]
                    if entryRecord.recType in validEntries:
                        knownGoodAdd(entryId)
                        goodAppend(entry)
                    else:
                        badAdd((entryRecord.eid, entryId,
                                entryRecord.GetParentMod().GName,
                                entryRecord.recType))
                        entryRecord.UnloadRecord()

        if badEntries:
            override = record.CopyAsOverride(self.patchFile)
            if override:
                setattr(override, topattr, goodEntries)
                type_id_badEntries = self.mod_type_id_badEntries.setdefault(
                    modFile.GName, {})
                id_badEntries = type_id_badEntries.setdefault(rec_type, {})
                id_badEntries[record.eid] = badEntries.copy()
                record.UnloadRecord()
                record._RecordID = override._RecordID

    def buildPatchLog(self,log):
        """Will write to log."""
        if not self.isActive: return
        #--Log
        mod_type_id_badEntries = self.mod_type_id_badEntries
        log.setHeader(u'= ' +self.__class__.name)
        for mod, type_id_badEntries in mod_type_id_badEntries.iteritems():
            log(u'\n=== %s' % mod.s)
            for type,id_badEntries in type_id_badEntries.iteritems():
                log(u'  * '+_(u'Cleaned %s: %d') % (type,len(id_badEntries)))
                for id, badEntries in id_badEntries.iteritems():
                    log(u'    * %s : %d' % (id,len(badEntries)))
                    for entry in sorted(badEntries, key=itemgetter(0)):
                        longId = entry[1]
                        if entry[2]:
                            modName = entry[2].s
                        else:
                            try:
                                modName = longId[0].s
                            except:
                                log(u'        . ' + _(
                                    u'Unloaded Object or Undefined Reference'))
                                continue
                        log(u'        . ' + _(
                            u'Editor ID: "%s", Object ID %06X: Defined in '
                            u'mod "%s" as %s') % (
                                entry[0], longId[1], modName, entry[3]))
        self.mod_type_id_badEntries = {}
