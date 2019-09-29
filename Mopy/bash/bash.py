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

"""This module starts the Wrye Bash application in console mode. Basically,
it runs some initialization functions and then starts the main application
loop."""

# Imports ---------------------------------------------------------------------
import atexit
import codecs
import os
import platform
import shutil
import sys
import traceback
from ConfigParser import ConfigParser
# Local
import bass
import exception
# NO OTHER LOCAL IMPORTS HERE (apart from the ones above) !
basher = balt = bolt = initialization = None
_wx = None
is_standalone = hasattr(sys, 'frozen')

def _import_bolt(opts):
    """Import bolt or show a tkinter error and exit if unsuccessful.

    :param opts: command line arguments"""
    global bolt
    try:
        # First of all set the language, set on importing bolt
        bass.language = opts.language
        import bolt  # bass.language must be set
    except Exception as e:
        but_kwargs = {'text': u"QUIT", 'fg': 'red'}  # foreground button color
        msg = u'\n'.join([dump_environment(), u'', u'Unable to load bolt:',
                          traceback.format_exc(e), u'Exiting.'])
        _tkinter_error_dial(msg, but_kwargs)
        sys.exit(1)

def _import_wx():
    """Import wxpython or show a tkinter error and exit if unsuccessful."""
    global _wx
    try:
        import wx as _wx
        # Hacky fix for loading older settings that pickled classes from
        # moved/deleted wx modules
        from wx import _core
        sys.modules['wx._gdi'] = _core
    except Exception as e:
        but_kwargs = {'text': _(u"QUIT"),
                      'fg': 'red'}  # foreground button color
        msg = u'\n'.join([dump_environment(), u'', u'Unable to load wx:',
                          traceback.format_exc(e), u'Exiting.'])
        _tkinter_error_dial(msg, but_kwargs)
        sys.exit(1)

#------------------------------------------------------------------------------
def assure_single_instance(instance):
    """Ascertain that only one instance of Wrye Bash is running.

    If this is the second instance running, then display an error message and
    exit. 'instance' must stay alive for the whole execution of the program.
    See: https://wxpython.org/Phoenix/docs/html/wx.SingleInstanceChecker.html

    :type instance: wx.SingleInstanceChecker"""
    if instance.IsAnotherRunning():
        bolt.deprint(u'Only one instance of Wrye Bash can run. Exiting.')
        msg = _(u'Only one instance of Wrye Bash can run.')
        _app = _wx.App(False)
        with _wx.MessageDialog(None, msg, u'Wrye Bash', _wx.OK) as dialog:
            dialog.ShowModal()
        sys.exit(1)

_bugdump_handle = None
def exit_cleanup():
    # Cleanup temp installers directory
    import tempfile
    tmpDir = bolt.GPath(tempfile.tempdir)
    for file_ in tmpDir.list():
        if file_.cs.startswith(u'wryebash_'):
            file_ = tmpDir.join(file_)
            try:
                if file_.isdir():
                    file_.rmtree(safety=file_.stail)
                else:
                    file_.remove()
            except:
                pass
    # make sure to flush the BashBugDump.log
    if _bugdump_handle is not None:
        _bugdump_handle.close()
    if bass.is_restarting:
        cli = cmd_line = bass.sys_argv # list of cli args
        try:
            if '--uac' in bass.sys_argv: ##: mostly untested - needs revamp
                import win32api
                if is_standalone:
                    exe = cli[0]
                    cli = cli[1:]
                else:
                    exe = sys.executable
                exe = [u'%s', u'"%s"'][u' ' in exe] % exe
                cli = u' '.join([u'%s', u'"%s"'][u' ' in x] % x for x in cli)
                cmd_line = u'%s %s' % (exe, cli)
                win32api.ShellExecute(0, 'runas', exe, cli, None, True)
                return
            else:
                import subprocess
                cmd_line = (is_standalone and cli) or [sys.executable] + cli
                subprocess.Popen(cmd_line, # a list, no need to escape spaces
                                 close_fds=True)
        except Exception as error:
            print error
            print u'Error Attempting to Restart Wrye Bash!'
            print u'cmd line: %s' % (cmd_line, )
            print
            raise

def dump_environment():
    import locale
    fse = sys.getfilesystemencoding()
    msg = u'\n'.join([
        u'Wrye Bash starting',
        u'Using Wrye Bash Version %s%s' % (bass.AppVersion,
            u' (Standalone)' if is_standalone else u''),
        u'OS info: %s' % platform.platform(),
        u'Python version: %d.%d.%d' % (
            sys.version_info[0], sys.version_info[1], sys.version_info[2]
        ),
        u'wxPython version: %s' % _wx.version() if _wx is not None else \
            u'wxPython not found',
        # Standalone: stdout will actually be pointing to stderr, which has no
        # 'encoding' attribute
        u'input encoding: %s; output encoding: %s; default locale: %s' % (
            sys.stdin.encoding, getattr(sys.stdout, 'encoding', None),
            locale.getdefaultlocale()
        ),
        u'filesystem encoding: %s%s' % (fse,
            (u' - using %s' % bolt.Path.sys_fs_enc) if bolt is not None
                                                       and not fse else u''),
        u'command line: %s' % sys.argv
    ])
    if bolt.scandir is not None:
        msg += u'\nUsing scandir ' + bolt.scandir.__version__
    print msg
    return msg

def _bash_ini_parser(bash_ini_path):
    bash_ini_parser = None
    if bash_ini_path is not None and os.path.exists(bash_ini_path):
        bash_ini_parser = ConfigParser()
        bash_ini_parser.read(bash_ini_path)
    return bash_ini_parser

# Main ------------------------------------------------------------------------
def main(opts):
    """Run the Wrye Bash main loop.

    :param opts: command line arguments
    :type opts: Namespace"""
    # First import bolt, needed for localization of error messages
    _import_bolt(opts)
    # Then import wx so we can set locale
    _import_wx()
    try:
        _main(opts)
    except Exception as e:
        msg = u'\n'.join([
            _(u'Wrye Bash encountered an error.'),
            _(u'Please post the information below to the official thread at'),
            _(u'https://afkmods.com/index.php?/topic/4966-wrye-bash-all-games'),
            _(u'or to the Wrye Bash Discord at'),
            _(u'https://discord.gg/NwWvAFR'),
            u'',
            traceback.format_exc(e)
        ])
        _close_dialog_windows()
        _show_wx_error(msg)
        sys.exit(1)

def _main(opts):
    """Run the Wrye Bash main loop.

    This function is marked private because it should be inside a try-except
    block. Call main() from the outside.

    :param opts: command line arguments
    """
    import barg
    bass.sys_argv = barg.convert_to_long_options(sys.argv)
    import env # env imports bolt (this needs fixing)
    bolt.deprintOn = opts.debug
    # useful for understanding context of bug reports
    if opts.debug or is_standalone:
        # Standalone stdout is NUL no matter what.   Redirect it to stderr.
        # Also, setup stdout/stderr to the debug log if debug mode /
        # standalone before wxPython is up
        global _bugdump_handle
        # _bugdump_handle = io.open(os.path.join(os.getcwdu(),u'BashBugDump.log'),'w',encoding='utf-8')
        _bugdump_handle = codecs.getwriter('utf-8')(
            open(os.path.join(os.getcwdu(), u'BashBugDump.log'), 'w'))
        sys.stdout = _bugdump_handle
        sys.stderr = _bugdump_handle
        old_stderr = _bugdump_handle

    if opts.debug:
        dump_environment()

    # Check if there are other instances of Wrye Bash running
    instance = _wx.SingleInstanceChecker('Wrye Bash') # must stay alive !
    assure_single_instance(instance)

    global initialization
    import initialization
    #--Bash installation directories, set on boot, not likely to change
    initialization.init_dirs_mopy_and_cd(is_standalone)

    # if HTML file generation was requested, just do it and quit
    if opts.genHtml is not None:
        msg1 = _(u"generating HTML file from: '%s'") % opts.genHtml
        msg2 = _(u'done')
        try: print msg1
        except UnicodeError: print msg1.encode(bolt.Path.sys_fs_enc)
        import belt # this imports bosh which imports wx (DUH)
        bolt.WryeText.genHtml(opts.genHtml)
        try: print msg2
        except UnicodeError: print msg2.encode(bolt.Path.sys_fs_enc)
        return

    # We need the Mopy dirs to initialize restore settings instance
    bash_ini_path, restore_ = u'bash.ini', None
    # import barb that does not import from bosh/balt/bush
    import barb
    if opts.restore:
        try:
            restore_ = barb.RestoreSettings(opts.filename)
            restore_.extract_backup()
            # get the bash.ini from the backup, or None - use in _detect_game
            bash_ini_path = restore_.backup_ini_path()
        except (exception.BoltError, exception.StateError, OSError, IOError):
            bolt.deprint(u'Failed to restore backup', traceback=True)
            restore_ = None
    # The rest of backup/restore functionality depends on setting the game
    try:
        bashIni, bush_game, game_ini_path = _detect_game(opts, bash_ini_path)
        if not bush_game: return
        if restore_:
            try:
                restore_.restore_settings(bush_game.fsName)
                # we currently disallow backup and restore on the same boot
                if opts.quietquit: return
            except (exception.BoltError, OSError, shutil.Error):
                bolt.deprint(u'Failed to restore backup', traceback=True)
                restore_.restore_ini()
                # reset the game and ini
                import bush
                bush.reset_bush_globals()
                bashIni, bush_game, game_ini_path = _detect_game(opts, u'bash.ini')
        import bosh # this imports balt (DUH) which imports wx
        bosh.initBosh(bashIni, game_ini_path)
        env.isUAC = env.testUAC(bush_game.gamePath.join(u'Data'))
        global basher, balt
        import basher, balt
    except (exception.BoltError, ImportError, OSError, IOError) as e:
        msg = u'\n'.join([_(u'Error! Unable to start Wrye Bash.'), u'\n', _(
            u'Please ensure Wrye Bash is correctly installed.'), u'\n',
                          traceback.format_exc(e)])
        _close_dialog_windows()
        _show_wx_error(msg)
        return

    atexit.register(exit_cleanup)
    basher.InitSettings()
    basher.InitLinks()
    basher.InitImages()
    #--Start application
    if opts.debug:
        if is_standalone:
            # Special case for py2exe version
            app = basher.BashApp()
            # Regain control of stdout/stderr from wxPython
            sys.stdout = old_stderr
            sys.stderr = old_stderr
        else:
            app = basher.BashApp(False)
    else:
        app = basher.BashApp()

    if bass.language:
        lang_info = _wx.Locale.FindLanguageInfo(bass.language)
        # Use setlocale with lang_info.GetLocaleName()?
        target_locale = _wx.Locale(lang_info.Language)
    else:
        target_locale = _wx.Locale(_wx.LANGUAGE_DEFAULT)
    app.locale = target_locale

    if not is_standalone and (
        not _rightWxVersion() or not _rightPythonVersion()): return
    if env.isUAC:
        uacRestart = opts.uac
        if not opts.noUac and not opts.uac:
            # Show a prompt asking if we should restart in Admin Mode
            message = _(
                u"Wrye Bash needs Administrator Privileges to make changes "
                u"to the %(gameName)s directory.  If you do not start Wrye "
                u"Bash with elevated privileges, you will be prompted at "
                u"each operation that requires elevated privileges.") % {
                          'gameName': bush_game.displayName}
            uacRestart = balt.ask_uac_restart(message,
                                              title=_(u'UAC Protection'),
                                              mopy=bass.dirs['mopy'])
            if uacRestart: bass.update_sys_argv(['--uac'])
        if uacRestart:
            bass.is_restarting = True
            return
    # Backup the Bash settings - we need settings being initialized to get
    # the previous version - we should read this from a file so we can move
    # backup higher up in the boot sequence.
    previous_bash_version = bass.settings['bash.version']
    # backup settings if app version has changed or on user request
    if opts.backup or barb.BackupSettings.new_bash_version_prompt_backup(
            balt, previous_bash_version):
        frame = None # balt.Link.Frame, not defined yet, no harm done
        base_dir = bass.settings['bash.backupPath'] or bass.dirs['modsBash']
        settings_file = (opts.backup and opts.filename) or None
        if not settings_file:
            settings_file = balt.askSave(frame,
                                         title=_(u'Backup Bash Settings'),
                                         defaultDir=base_dir,
                                         wildcard=u'*.7z',
                                         defaultFile=barb.BackupSettings.
                                         backup_filename(bush_game.fsName))
        if settings_file:
            with balt.BusyCursor():
                backup = barb.BackupSettings(settings_file,
                                             bush_game.fsName)
            try:
                with balt.BusyCursor():
                    backup.backup_settings(balt)
            except exception.StateError:
                if balt.askYes(frame, u'\n'.join([
                    _(u'There was an error while trying to backup the '
                      u'Bash settings!'),
                    _(u'If you continue, your current settings may be '
                        u'overwritten.'),
                    _(u'Do you want to quit Wrye Bash now?')]),
                                 title=_(u'Unable to create backup!')):
                    return  # Quit

    app.Init() # Link.Frame is set here !
    app.MainLoop()

def _detect_game(opts, backup_bash_ini):
    # Read the bash.ini file either from Mopy or from the backup location
    bashIni = _bash_ini_parser(backup_bash_ini)
    # if uArg is None, then get the UserPath from the ini file
    user_path = opts.userPath or None  ##: not sure why this must be set first
    if user_path is None:
        ini_user_path = bass.get_ini_option(bashIni, u'sUserPath')
        if ini_user_path and not ini_user_path == u'.':
            user_path = ini_user_path
    if user_path:
        drive, path = os.path.splitdrive(user_path)
        os.environ['HOMEDRIVE'] = drive
        os.environ['HOMEPATH'] = path
    # Detect the game we're running for ---------------------------------------
    bush_game = _import_bush_and_set_game(opts, bashIni)
    if not bush_game:
        return None, None, None
    #--Initialize Directories to perform backup/restore operations
    #--They depend on setting the bash.ini and the game
    game_ini_path = initialization.init_dirs(bashIni, opts.personalPath,
                                             opts.localAppDataPath, bush_game)
    return bashIni, bush_game, game_ini_path

def _import_bush_and_set_game(opts, bashIni):
    import bush
    bolt.deprint(u'Searching for game to manage:')
    ret, game_icons = bush.detect_and_set_game(opts.oblivionPath, bashIni)
    if ret is not None:  # None == success
        if len(ret) == 0:
            msgtext = _(
                u"Wrye Bash could not find a game to manage. Please use\n"
                u"the -o command line argument to specify the game path.")
        else:
            msgtext = _(
                u"Wrye Bash could not determine which game to manage.\n"
                u"The following games have been detected, please select "
                u"one to manage.")
            msgtext += u'\n\n'
            msgtext += _(
                u'To prevent this message in the future, use the -o command\n'
                u'line argument or the bash.ini to specify the game path.')
        retCode = _wxSelectGame(ret, game_icons, msgtext)
        if retCode is None:
            bolt.deprint(u'No games were found or selected. Aborting.')
            return None
        # Add the game to the command line, so we use it if we restart
        bass.update_sys_argv(['--oblivionPath', bush.game_path(retCode).s])
        bush.detect_and_set_game(opts.oblivionPath, bashIni, retCode)
    # Force Python mode if CBash can't work with this game
    bolt.CBash = opts.mode if bush.game.esp.canCBash else 1 #1 = python mode...
    return bush.game

def _show_wx_error(msg):
    """Shows an error message in a wx window."""
    try:
        class MessageBox(_wx.Dialog):
            def __init__(self, msg):
                _wx.Dialog.__init__(self, None, -1, title=_('Wrye Bash Error'),
                                    size=(400, 300),
                                    style=_wx.DEFAULT_DIALOG_STYLE |
                                          _wx.STAY_ON_TOP |
                                          _wx.DIALOG_NO_PARENT |
                                          _wx.RESIZE_BORDER)
                sizer = _wx.BoxSizer(_wx.VERTICAL)
                text_ctrl = _wx.TextCtrl(self,
                                    style=_wx.TE_MULTILINE | _wx.TE_BESTWRAP |
                                          _wx.TE_READONLY | _wx.BORDER_NONE)
                text_ctrl.SetValue(msg)
                text_ctrl.SetBackgroundColour(_wx.SystemSettings.GetColour(4))
                sizer.Add(text_ctrl, proportion=1, flag=_wx.EXPAND | _wx.ALL,
                          border=5)
                button = _wx.Button(self, _wx.ID_CANCEL, _(u'Quit'))
                button.SetDefault()
                sizer.Add(button, proportion=0,
                          flag=_wx.ALIGN_CENTER | _wx.ALL, border=5)
                self.SetSizer(sizer)
                # sizer.Fit(self)
                self.ShowModal()
                self.Destroy()

        print(msg) # Print msg into error log.
        app = _wx.GetApp() # wx.App is a singleton, get it if it exists.
        if app:
            MessageBox(msg)
            app.Exit()
        else:
            app = _wx.App(False) # wx.App is not instantiated, do so now .
            if app:
                MessageBox(msg)
                app.Exit()
            else:
                # Instantiating wx.App failed, fallback to tkinter.
                but_kwargs = {'text': _(u"QUIT"),
                              'fg': 'red'}  # foreground button color
                _tkinter_error_dial(msg, but_kwargs)

    except StandardError as e:
        print u'Wrye Bash encountered an error but could not display it.'
        print u'The following is the error that occurred when displaying the '\
              u'first error:'
        try:
            print traceback.format_exc(e)
        except Exception:
            print u'   An error occurred while displaying the second error.'

def _tkinter_error_dial(msg, but_kwargs):
    import Tkinter
    root_widget = Tkinter.Tk()
    frame = Tkinter.Frame(root_widget)
    frame.pack()
    button = Tkinter.Button(frame, command=root_widget.destroy, pady=15,
                            borderwidth=5, relief=Tkinter.GROOVE, **but_kwargs)
    button.pack(fill=Tkinter.BOTH, expand=1, side=Tkinter.BOTTOM)
    w = Tkinter.Text(frame)
    w.insert(Tkinter.END, msg)
    w.config(state=Tkinter.DISABLED)
    w.pack()
    root_widget.mainloop()

def _close_dialog_windows():
    """Close any additional windows opened by wrye bash (e.g Splash, Dialogs).

    This will not close the main bash window (BashFrame) because closing that
    results in virtual function call exceptions."""
    for window in _wx.GetTopLevelWindows():
        if basher is None or not isinstance(window, basher.BashFrame):
            if isinstance(window, _wx.Dialog):
                window.Destroy()
            window.Close()

class _AppReturnCode(object):
    def __init__(self): self.value = None
    def get(self): return self.value
    def set(self, value): self.value = value

def _wxSelectGame(ret, game_icons, msgtext):

    class GameSelect(_wx.Frame):
        def __init__(self, game_names, game_icons, callback):
            _wx.Frame.__init__(self, None, title=u'Wrye Bash')
            self.callback = callback
            # Setup the size - we give each button 42 pixels, 32 for the image
            # plus 10 for the borders. However, we limit the total size of the
            # display list at 600 pixels, where the scrollbar takes over
            self.SetSizeHints(420, 200)
            self.SetSize((420, min(600, 200 + len(game_names) * 42)))
            # Construct the window and add the static text, setup the
            # scrollbars if needed
            panel = _wx.ScrolledWindow(self, style=_wx.TAB_TRAVERSAL)
            panel.SetScrollbars(0, 20, 0, 50)
            sizer = _wx.BoxSizer(_wx.VERTICAL)
            sizer.Add(_wx.StaticText(panel, label=msgtext,
                                     style=_wx.ALIGN_CENTER_HORIZONTAL),
                      0, _wx.EXPAND | _wx.ALL, 5)
            # Add the game buttons to the window
            for game_name in game_names:
                game_btn = _wx.Button(panel, label=game_name)
                game_btn.SetBitmap(_wx.Bitmap(game_icons[game_name]))
                sizer.Add(game_btn, 0, _wx.EXPAND | _wx.ALL ^ _wx.BOTTOM, 5)
            # Finally, append the 'Quit' button
            quit_button = _wx.Button(panel, _wx.ID_CANCEL, _(u'Quit'))
            quit_button.SetBitmap(_wx.ArtProvider.GetBitmap(
                _wx.ART_ERROR, _wx.ART_HELP_BROWSER, (32, 32)))
            quit_button.SetDefault()
            sizer.Add(quit_button, 0, _wx.EXPAND | _wx.ALL ^ _wx.BOTTOM, 5)
            self.Bind(_wx.EVT_BUTTON, self.OnButton)
            panel.SetSizer(sizer)

        def OnButton(self, event):
            if event.GetId() != _wx.ID_CANCEL:
                self.callback(self.FindWindowById(event.GetId()).GetLabel())
            self.Close(True)

    _app = _wx.App(False)
    _app.locale = _wx.Locale(_wx.LANGUAGE_DEFAULT)
    retCode = _AppReturnCode()
    # Sort before we pass these on - this is purely visual
    ret.sort()
    frame = GameSelect(ret, game_icons, retCode.set)
    frame.Show()
    frame.Center()
    _app.MainLoop()
    del _app
    return retCode.get()

# Version checks --------------------------------------------------------------
def _rightWxVersion():
    wxver = _wx.version()
    if wxver != '3.0.2.0 msw (classic)':
        return balt.askYes(
            None, 'Warning: you appear to be using a non-supported version '
            'of wxPython (%s).  This will cause problems!  It is highly '
            'recommended you use either version 3.0.2.0 msw (classic) or, '
            'at your discretion, a later version (untested). Do you still '
            'want to run Wrye Bash?' % wxver,
            'Warning: Non-Supported wxPython detected', )
    return True

def _rightPythonVersion():
    sysVersion = sys.version_info[:3]
    if sysVersion < (2, 7) or sysVersion >= (3,):
        balt.showError(None, _(u"Only Python 2.7 and newer is supported "
            u"(%s.%s.%s detected). If you know what you're doing install the "
            u"WB python version and edit this warning out. "
            u"Wrye Bash will exit.") % sysVersion,
            title=_(u"Incompatible Python version detected"))
        return False
    return True
