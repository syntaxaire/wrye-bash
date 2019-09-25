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
"""GameInfo class encapsulating static info for active game. Avoid adding
state and methods. game.GameInfo#init classmethod is used to import rest of
active game package as needed (currently the record and constants modules)
and to set some brec.RecordHeader/MreRecord class variables."""
import importlib

from .. import brec

class GameInfo(object):
    # Main game info - should be overridden -----------------------------------
    # Name of the game to use in UI.
    displayName = u'' ## Example: u'Skyrim'
    # Name of the game's filesystem folder.
    fsName = u'' ## Example: u'Skyrim'
    # Alternate display name of Wrye Bash when managing this game
    altName = u'' ## Example: u'Wrye Smash'
    # Name of game's default ini file.
    defaultIniFile = u''
    # The exe to use when launching the game (without xSE present)
    launch_exe = u'' ## Example: u'TESV.exe'
    # Path to a file to look for to see if this is the right game. Given as a
    # list of strings that will be joined with the -o parameter. Must be unique
    # among all games. As a rule of thumb, use the file you specified in
    # launch_exe, unless that file is shared by multiple games, in which case
    # you MUST find unique files - see Skyrim and Enderal, which share TESV.exe
    game_detect_file = []
    # Path to a file to pass to env.get_file_version to determine the game's
    # version. Usually the same as launch_exe, but some games need different
    # ones here (e.g. Enderal, which has Skyrim's version in the launch_exe,
    # and therefore needs a different file here).
    version_detect_file = []
    # The main plugin Wrye Bash should look for
    masterFiles = []
    # INI files that should show up in the INI Edits tab
    #  Example: [u'Oblivion.ini']
    iniFiles = []
    # The pickle file for this game.  Holds encoded GMST IDs from the big list
    # below
    pklfile = u'bash\\db\\*GAMENAME*_ids.pkl'
    # The directory containing the masterlist for this game, relative to
    # 'Mopy/Bash Patches'
    masterlist_dir = u''
    # Registry keys to read to find the install location
    # These are relative to:
    #  HKLM\Software
    #  HKLM\Software\Wow6432Node
    #  HKCU\Software
    #  HKCU\Software\Wow6432Node
    # Example: (u'Bethesda Softworks\\Oblivion', u'Installed Path')
    regInstallKeys = ()
    # URL to the Nexus site for this game
    nexusUrl = u''   # URL
    nexusName = u''  # Long Name
    nexusKey = u''   # Key for the "always ask this question" setting in
                     # settings.dat

    # Additional game info - override as needed -------------------------------
    # URL to download patches for the main game.
    patchURL = u''
    # Tooltip to display over the URL when displayed
    patchTip = u'Update via Steam'
    # Bsa info
    allow_reset_bsa_timestamps = False
    bsa_extension = u'bsa'
    # Whether or not the Archive.exe tool for this game creates BSL files
    has_bsl = False
    supports_mod_inis = True  # this game supports mod ini files aka ini
                              # fragments
    vanilla_string_bsas = {}
    resource_archives_keys = ()
    # plugin extensions
    espm_extensions = {u'.esp', u'.esm'}
    # Extensions for external script files. Empty if this game doesn't have any
    script_extensions = {}
    # Load order info
    using_txt_file = True
    # bethesda net export files
    has_achlist = False
    # check if a plugin is convertible to a light master instead of checking
    # mergeability
    check_esl = False
    # Whether or not this game has standalone .pluggy cosaves
    has_standalone_pluggy = False

    def __init__(self, gamePath):
        self.gamePath = gamePath # absolute bolt Path to the game directory
        self.has_esl = u'.esl' in self.espm_extensions

    # Construction Set information
    class cs(object):
        cs_abbrev = u''   # Abbreviated name
        long_name = u''   # Full name
        exe = u'*DNE*'    # Executable to run
        se_args = u''     # Argument to pass to the SE to load the CS
        image_name = u''  # Image name template for the status bar

    # Script Extender information
    class se(object):
        se_abbrev = u''   # Abbreviated name. If this is empty, it signals that
                          # no xSE is available for this game. Note that this
                          # should NEVER be used to program other xSE
                          # behavior - create new variables like plugin_dir and
                          # cosave_ext instead.
        long_name = u''   # Full name
        exe = u''         # Exe to run
        steam_exe = u''   # Exe to run if a steam install
        plugin_dir = u''  # One level above the directory in which xSE plugins
                          # should be placed (e.g. when plugins should be in
                          # Data\OBSE\Plugins, this should be u'OBSE')
        cosave_tag = u''  # The magic tag that the cosaves use (e.g. u'SKSE').
                          # If this is empty, it signals that this script
                          # extender has no cosaves.
        cosave_ext = u''  # The extension that the cosaves use (e.g. u'.skse')
        url = u''         # URL to download from
        url_tip = u''     # Tooltip for mouse over the URL

    # Script Dragon
    class sd(object):
        sd_abbrev = u''   # Abbreviated name. If this is empty, it signals that
                          # no Script Dragon is available for this game.
        long_name = u''   # Full name
        install_dir = u'' # The directory, relative to the Data folder, into
                          # which Script Dragon plugins will be installed.

    # SkyProc Patchers
    class sp(object):
        sp_abbrev = u''   # Abbreviated name. If this is empty, it signals that
                          # this game does not support SkyProc patchers.
        long_name = u''   # Full name
        install_dir = u'' # The directory, relative to the Data folder, into
                          # which SkyProc patchers will be installed.

    # Graphics Extender information
    class ge(object):
        ge_abbrev = u'' # Abbreviated name. If this is empty, it signals
                        # that no graphics extender is available for this game.
        long_name = u'' # Full name
        # exe is treated specially here.  If it is a string, then it should
        # be the path relative to the root directory of the game, if it is
        # a list, each list element should be an iterable to pass to Path.join
        # relative to the root directory of the game.  In this case,
        # each filename will be tested in reverse order.  This was required
        # for Oblivion, as the newer OBGE has a different filename than the
        # older OBGE
        exe = u''
        url = u''       # URL to download from
        url_tip = u''   # Tooltip for mouse over the URL

    # 4gb Launcher
    class laa(object):
        name = u''          # Display name of the launcher
        exe = u'*DNE*'      # Executable to run
        launchesSE = False  # Whether the launcher will automatically launch
                            # the SE

    # Some stuff dealing with INI files
    class ini(object):
        # True means new lines are allowed to be added via INI tweaks
        #  (by default)
        allowNewLines = False
        # INI Entry to enable BSA Redirection
        bsaRedirection = (u'Archive', u'sArchiveList')

    # Save Game format stuff
    class ess(object):
        # Save file capabilities
        canReadBasic = True # Can read the info needed for the Save Tab display
        canEditMore = False # Advanced editing
        ext = u'.ess'       # Save file extension

    # Information about Plugin-Name-specific Directories supported by this game
    # Some examples are sound\voices\PLUGIN_NAME.esp, or the facegendata ones.
    # All paths are given as lists for future cross-platform support.
    # An empty list means that the game does not have such a directory.
    class pnd(object):
        # The path to the first plugin-name-specific directory for facegen.
        # Meshes in newer games, textures in older ones.
        facegen_dir_1 = []
        # The path to the second plugin-name-specific directory for facegen.
        # Always contains textures.
        facegen_dir_2 = []
        # The path to the plugin-name-specific directory for voice files
        # This is the same for every game released thus far (sound\\voice\\%s)
        voice_dir = [u'sound', u'voice']

    # INI setting used to setup Save Profiles
    #  (section,key)
    saveProfilesKey = (u'General', u'SLocalSavePath')
    save_prefix = u'Saves' # base dir for save files

    # BAIN:
    #  These are the allowed default data directories that BAIN can install to
    dataDirs = {u'meshes', u'music', u'sound', u'textures', u'video'}
    #  These are additional special directories that BAIN can install to
    dataDirsPlus = set()
    # Files BAIN shouldn't skip
    dontSkip = ()
    # Directories where specific file extensions should not be skipped by BAIN
    dontSkipDirs = {}
    # Folders BAIN should never CRC check in the Data directory
    SkipBAINRefresh = set((
        # Use lowercase names
    ))
    # Files to exclude from clean data
    wryeBashDataFiles = {u'Docs\\Bash Readme Template.html',
                         u'Docs\\wtxt_sand_small.css', u'Docs\\wtxt_teal.css',
                         u'Docs\\Bash Readme Template.txt'}
    wryeBashDataDirs = {u'Bash Patches', u'INI Tweaks'}
    ignoreDataFiles = set()
    ignoreDataFilePrefixes = set()
    ignoreDataDirs = set()

    # Plugin format stuff
    class esp(object):
        # Wrye Bash capabilities
        canBash = False         # Can create Bashed Patches
        canCBash = False        # CBash can handle this game's records
        canEditHeader = False   # Can edit basic info in the TES4 record
        # Valid ESM/ESP header versions
        #  These are the valid 'version' numbers for the game file headers
        validHeaderVersions = tuple()
        # used to locate string translation files
        stringsFiles = [
            ((u'Strings',), u'%(body)s_%(language)s.STRINGS'),
            ((u'Strings',), u'%(body)s_%(language)s.DLSTRINGS'),
            ((u'Strings',), u'%(body)s_%(language)s.ILSTRINGS'),
        ]

    # Bash Tags supported by this game
    allTags = set()

    # Patcher available when building a Bashed Patch (referenced by class name)
    patchers = ()

    # CBash patchers available when building a Bashed Patch
    CBash_patchers = ()

    # Magic Info
    weaponTypes = ()

    # Race Info, used in faces.py
    raceNames = {}
    raceShortNames = {}
    raceHairMale = {}
    raceHairFemale = {}

    # Record information - set in cls.init ------------------------------------
    # Mergeable record types
    mergeClasses = ()
    # Extra read classes: these record types will always be loaded, even if
    # patchers don't need them directly (for example, for MGEF info)
    readClasses = ()
    writeClasses = ()

    # Class attributes moved to constants module, set dynamically at init
    #--Game ESM/ESP/BSA files
    ## These are all of the ESM,ESP,and BSA data files that belong to the game
    ## These filenames need to be in lowercase,
    bethDataFiles = set()  # initialize with literal

    #--Every file in the Data directory from Bethsoft
    allBethFiles = set()  # initialize with literal

    # Function Info -----------------------------------------------------------
    conditionFunctionData = (  #--0: no param; 1: int param; 2: formid param
    )
    allConditions = set(entry[0] for entry in conditionFunctionData)
    fid1Conditions = set(
        entry[0] for entry in conditionFunctionData if entry[2] == 2)
    fid2Conditions = set(
        entry[0] for entry in conditionFunctionData if entry[3] == 2)
    # Skip 3 and 4 because it needs to be set per runOn
    fid5Conditions = set(
        entry[0] for entry in conditionFunctionData if entry[4] == 2)

    # Known record types - maps integers from the save format to human-readable
    # names for the record types. Used in save editing code.
    save_rec_types = {}

    #--List of GMST's in the main plugin (Oblivion.esm) that have 0x00000000
    #  as the form id.  Any GMST as such needs it Editor Id listed here.
    gmstEids = []

    """
    GLOB record tweaks used by patcher.patchers.multitweak_settings.GmstTweaker

    Each entry is a tuple in the following format:
      (DisplayText, MouseoverText, GLOB EditorID, Option1, Option2, ...,
      OptionN)
      -EditorID can be a plain string, or a tuple of multiple Editor IDs.
      If it's a tuple, then Value (below) must be a tuple of equal length,
      providing values for each GLOB
    Each Option is a tuple:
      (DisplayText, Value)
      - If you enclose DisplayText in brackets like this: _(u'[Default]'),
      then the patcher will treat this option as the default value.
      - If you use _(u'Custom') as the entry, the patcher will bring up a
      number input dialog

    To make a tweak Enabled by Default, enclose the tuple entry for the
    tweak in a list, and make a dictionary as the second list item with {
    'defaultEnabled ':True}. See the UOP Vampire face fix for an example of
    this (in the GMST Tweaks)
    """
    GlobalsTweaks = []

    """
    GMST record tweaks used by patcher.patchers.multitweak_settings.GmstTweaker

    Each entry is a tuple in the following format:
      (DisplayText, MouseoverText, GMST EditorID, Option1, Option2, ...,
      OptionN)
      - EditorID can be a plain string, or a tuple of multiple Editor IDs.
      If it's a tuple, then Value (below) must be a tuple of equal length,
      providing values for each GMST
    Each Option is a tuple:
      (DisplayText, Value)
      - If you enclose DisplayText in brackets like this: _(u'[Default]'),
      then the patcher will treat this option as the default value.
      - If you use _(u'Custom') as the entry, the patcher will bring up a
      number input dialog

    To make a tweak Enabled by Default, enclose the tuple entry for the
    tweak in a list, and make a dictionary as the second list item with {
    'defaultEnabled ':True}. See the UOP Vampire facefix for an example of
    this (in the GMST Tweaks)
    """
    GmstTweaks = []

    #--------------------------------------------------------------------------
    # ListsMerger patcher (leveled list patcher)
    #--------------------------------------------------------------------------
    listTypes = ()
    #--------------------------------------------------------------------------
    # NamesPatcher
    #--------------------------------------------------------------------------
    namesTypes = set()  # initialize with literal
    #--------------------------------------------------------------------------
    # ItemPrices Patcher
    #--------------------------------------------------------------------------
    pricesTypes = {}
    #--------------------------------------------------------------------------
    # StatsImporter
    #--------------------------------------------------------------------------
    statsTypes = {}
    statsHeaders = ()
    #--------------------------------------------------------------------------
    # SoundPatcher
    #--------------------------------------------------------------------------
    # Needs longs in SoundPatcher
    soundsLongsTypes = set()  # initialize with literal
    soundsTypes = {}
    #--------------------------------------------------------------------------
    # CellImporter
    #--------------------------------------------------------------------------
    cellAutoKeys = set()  # use a set literal
    cellRecAttrs = {}
    cellRecFlags = {}
    #--------------------------------------------------------------------------
    # GraphicsPatcher
    #--------------------------------------------------------------------------
    graphicsLongsTypes = set()  # initialize with literal
    graphicsTypes = {}
    graphicsFidTypes = {}
    graphicsModelAttrs = ()
    #--------------------------------------------------------------------------
    # Inventory Patcher
    #--------------------------------------------------------------------------
    inventoryTypes = ()

    #--------------------------------------------------------------------------
    # Race Patcher
    #--------------------------------------------------------------------------
    default_eyes = {}

    #--------------------------------------------------------------------------
    # Keywords Patcher
    #--------------------------------------------------------------------------
    keywords_types = ()

    # Record type to name dictionary
    record_type_name = {}

    # xEdit menu string and key for expert setting
    xEdit_expert = ()

    # Set in game/*/default_tweaks.py, this is a dictionary mapping names for
    # 'default' INI tweaks (i.e. ones that we ship with WB and that can't be
    # deleted) to OrderedDicts that implement the actual tweaks. See
    # DefaultIniFile.__init__ for how the tweaks are parsed.
    default_tweaks = {}

    @classmethod
    def init(cls):
        # Setting RecordHeader class variables --------------------------------
        # Top types in order of the main ESM
        brec.RecordHeader.topTypes = []
        brec.RecordHeader.recordTypes = set(
            brec.RecordHeader.topTypes + ['GRUP', 'TES4'])
        # Record Types
        brec.MreRecord.type_class = dict((x.classType,x) for x in  (
                ))
        # Simple records
        brec.MreRecord.simpleTypes = (
                set(brec.MreRecord.type_class) - {'TES4'})
    # Import from the constants module ----------------------------------------
    # Class attributes moved to constants module, set dynamically at init
    _constants_members = {
        'GlobalsTweaks', 'GmstTweaks', 'allBethFiles', 'allConditions',
        'bethDataFiles', 'cellAutoKeys', 'cellRecAttrs', 'cellRecFlags',
        'conditionFunctionData', 'default_eyes', 'fid1Conditions',
        'fid2Conditions', 'fid5Conditions', 'gmstEids', 'graphicsFidTypes',
        'graphicsLongsTypes', 'graphicsModelAttrs', 'graphicsTypes',
        'inventoryTypes', 'keywords_types', 'listTypes', 'namesTypes',
        'pricesTypes', 'record_type_name', 'save_rec_types',
        'soundsLongsTypes', 'soundsTypes', 'statsHeaders', 'statsTypes',
        'xEdit_expert',
    }
    @classmethod
    def _dynamic_import_modules(cls, package_name):
        """Dynamically import package modules to avoid importing them for every
        game. We need to pass the package name in for importlib to work.
        Currently populates the GameInfo namespace with the members defined in
        the relevant constants.py and imports default_tweaks."""
        constants = importlib.import_module('.constants', package=package_name)
        for k in dir(constants):
            if k.startswith('_'): continue
            if k not in cls._constants_members:
                raise RuntimeError(u'Unexpected game constant %s' % k)
            setattr(cls, k, getattr(constants, k))
        tweaks_module = importlib.import_module('.default_tweaks',
                                                package=package_name)
        cls.default_tweaks = tweaks_module.default_tweaks

GAME_TYPE = None
