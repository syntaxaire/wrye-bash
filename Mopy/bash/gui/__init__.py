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
#  Wrye Bash copyright (C) 2005-2009 Wrye, 2010-2015 Wrye Bash Team
#  https://github.com/wrye-bash
#
# =============================================================================
import wx as _wx

# Utilities -------------------------------------------------------------------
class Color(object):
    """A simple RGB(A) color class used to avoid having to return wx.Colour
    objects."""
    def __init__(self, red, green, blue, alpha=255): # type: (int, int, int, int) -> None
        """Creates a new color object with the specified color properties.
        Note that all color components must be in the range [0-255] (inclusive
        on both ends), otherwise a RuntimeException is raised.

        :param red: The amount of red in this color: [0-255].
        :param green: The amount of green in this color: [0-255].
        :param blue: The amount of blue in this color: [0-255].
        :param alpha: The amount of alpha in this color: [0-255]. Defaults to
                      255."""
        for color in (red, green, blue, alpha):
            if color < 0 or color > 255:
                raise RuntimeError(u'All color components must be in range '
                                   u'0-255.')
        self.red, self.green, self.blue, self.alpha = red, green, blue, alpha

    def _to_wx(self): # type: () -> _wx.Colour
        """Converts this Color object back into a wx.Colour object.

        :return: A wx.Colour object representing the same color as this one."""
        return _wx.Colour(self.red, self.green, self.blue, self.alpha)

    @staticmethod
    def _from_wx(color): # type: (_wx.Colour) -> Color
        """Creates a new Color object by copying the color properties from the
        specified wx.Colour object.

        :param color: The wx.Colour object to copy.
        :return: A Color object representing the same color."""
        return Color(color.red, color.green, color.blue, color.alpha)

# Base elements ---------------------------------------------------------------
class _AWidget(object):
    """Abstract base class for all GUI items. Holds a reference to the native
    wx widget that we abstract over."""
    def __init__(self):
        """Creates a new _AWidget instance. This initializes _native_widget to
        None, which will later receive a proper value inside the __init__
        methods of _AWidget's subclasses."""
        self._native_widget = None  # type: _wx.Window

    @property
    def widget_name(self): # type: () -> unicode
        """Returns the name of this widget.

        :return: This widget's name."""
        return self._native_widget.GetName()

    @widget_name.setter
    def widget_name(self, new_name): # type: (unicode) -> None
        """Sets the name of this widget to the specified name.

        :param new_name: The string to change this widget's name to."""
        self._native_widget.SetName(new_name)

    @property
    def visible(self): # type: () -> bool
        """Returns True if this widget is currently visible, i.e. if the user
        can see it in the GUI.

        :return: True if this widget is currently visible."""
        return self._native_widget.IsShown()

    @visible.setter
    def visible(self, is_visible): # type: (bool) -> None
        """Shows or hides this widget based on the specified parameter.

        :param is_visible: Whether or not to show this widget."""
        self._native_widget.Show(is_visible)

    @property
    def enabled(self): # type: () -> bool
        """Returns True if this widget is currently enabled, i.e. if the user
        can interact with it. Disabled widgets are typically styled in some way
        to indicate this fact to the user (e.g. greyed out).

        :return: True if this widget is currently enabled."""
        return self._native_widget.IsEnabled()

    @enabled.setter
    def enabled(self, enabled): # type: (bool) -> None
        """Enables or disables this widget based on the specified parameter.

        :param enabled: Whether or not to enable this widget."""
        self._native_widget.Enable(enabled)

    @property
    def tooltip(self): # type: () -> unicode
        """Returns the current contents of this widget's tooltip. If no tooltip
        is set, returns an empty string.

        :return: This widget's tooltip."""
        return self._native_widget.GetToolTipString() or u''

    @tooltip.setter
    def tooltip(self, new_tooltip): # type: (unicode) -> None
        """Sets the tooltip of this widget to the specified string. If the
        string is empty or None, the tooltip is simply removed.

        :param new_tooltip: The string to change the tooltip to."""
        if not new_tooltip:
            self._native_widget.UnsetToolTip()
        else:
            # TODO(inf) textwrap.fill(text, 50)
            self._native_widget.SetToolTipString(new_tooltip)

    # TODO: use a custom color class here
    @property
    def background_color(self): # type: () -> _wx.Colour
        """Returns the background color of this widget as a wx.Colour
        object.

        :return: The background color of this widget."""
        return self._native_widget.GetBackgroundColour()

    @background_color.setter
    def background_color(self, new_color): # type: (_wx.Colour) -> None
        """Changes the background color of this widget to the color represented
        by the specified wx.Colour object.

        :param new_color: The color to change the background color to."""
        self._native_widget.SetBackgroundColour(new_color)
        self._native_widget.Refresh()

    # TODO: trash this for better event handling
    def bind(self, event, callback):
        pass
        # self._native_widget.

# Buttons ---------------------------------------------------------------------
class _AButton(_AWidget):
    """Abstract base class for all buttons."""
    # TODO(inf) This will be expanded, don't remove

class Button(_AButton):
    """Represents a generic button that can be pressed, triggering an action.
    You probably want one of the more specialized versions of this class
    (e.g. OkButton or CancelButton)."""
    # The ID that will be passed to wx. Controls some OS-specific behavior,
    # e.g. when pressing Tab
    _id = _wx.ID_ANY
    # The label to use when no label was explicitly specified. Set per class.
    default_label = u''

    def __init__(self, parent, label=u'', on_click=None, tooltip=None,
                 default=False):
        """Creates a new Button with the specified properties.

        :param parent: The object that the button belongs to.
        :param label: The text shown on the button.
        :param on_click: A callback to execute when the button isclicked. Takes
                         no parameters.
        :param tooltip: A tooltip to show when the user hovers over the button.
        :param default: If set to True, this button will be the 'default',
                        meaning that if a user selects nothing else and hits
                        Enter, this button will activate."""
        super(Button, self).__init__()
        if not label and self.__class__.default_label:
            label = self.__class__.default_label
        self._native_widget = _wx.Button(parent, self.__class__._id,
                                         label=label, name=u'button')
        if on_click:
            self._native_widget.Bind(_wx.EVT_BUTTON, lambda __evt: on_click)
        if default:
            self._native_widget.SetDefault()
        if tooltip:
            self.tooltip = tooltip

class OkButton(Button):
    """A button with the label 'OK'. Applies pending changes and closes the
    dialog or shows that the user consented to something."""
    _id = _wx.ID_OK
    default_label = _(u'OK')

class CancelButton(Button):
    """A button with the label 'Cancel'. Rejects pending changes or aborts a
    running process."""
    _id = _wx.ID_CANCEL
    default_label = _(u'Cancel')

class SaveButton(Button):
    """A button with the label 'Save'. Saves pending changes or edits by the
    user."""
    _id = _wx.ID_SAVE
    default_label = _(u'Save')

class SaveAsButton(Button):
    """A button with the label 'Save As'. Behaves like the 'Save' button above,
    but shows some type of prompt first, asking the user where to save."""
    _id = _wx.ID_SAVEAS
    default_label = _(u'Save As...')

class RevertButton(Button):
    """A button with the label 'Revert'. Resets pending changes back to the
    default state or undoes any alterations made by the user."""
    _id = _wx.ID_REVERT
    default_label = _(u'Revert')

class RevertToSavedButton(Button):
    """A button with the label 'Revert to Saved'. Resets pending changes back
    to the previous state or undoes one or more alterations made by the
    user."""
    _id = _wx.ID_REVERT_TO_SAVED
    default_label = _(u'Revert to Saved')

class OpenButton(Button):
    """A button with the label 'Open'. Opens a file in an editor or displays
    some other GUI component (i.e. 'open a window')."""
    _id = _wx.ID_OPEN
    default_label = _(u'Open')

class SelectAllButton(Button):
    """A button with the label 'Select All'. Checks all elements in a
    multi-element selection component."""
    _id = _wx.ID_SELECTALL
    default_label = _(u'Select All')

class DeselectAllButton(Button):
    """A button with the label 'Deselect All'. Unchecks all elements in a
    multi-element selection component."""
    _id = _wx.ID_SELECTALL
    default_label = _(u'Deselect All')

class ApplyButton(Button):
    """A button with the label 'Apply'. Applies pending changes without closing
    the dialog."""
    _id = _wx.ID_APPLY
    default_label = _(u'Apply')

class ToggleButton(_AButton):
    """Represents a button that can be toggled on or off."""
    def __init__(self, parent, label=u'', on_toggle=None, tooltip=None):
        """Creates a new ToggleButton with the specified properties.

        :param parent: The object that the button belongs to.
        :param label: The text shown on the button.
        :param on_toggle: A callback to execute when the button is clicked.
                          Takes a single parameter, a boolean that is True if
                          the button is on.
        :param tooltip: A tooltip to show when the user hovers over the
                        button."""
        super(ToggleButton, self).__init__()
        self._native_widget = _wx.ToggleButton(parent, _wx.ID_ANY,
                                               label=label, name=u'button')
        if on_toggle:
            def _toggle_callback(_event): # type: (_wx.Event) -> None
                on_toggle(self._native_widget.GetValue())
            self._native_widget.Bind(_wx.EVT_TOGGLEBUTTON, _toggle_callback)
        if tooltip:
            self.tooltip = tooltip

    @property
    def toggled(self): # type: () -> bool
        """Returns True if this button is toggled on.

        :return: True if this button is toggled on."""
        return self._native_widget.GetValue()

    @toggled.setter
    def toggled(self, value): # type: (bool) -> None
        """Toggles this button on if the specified parameter is True.

        :param value: Whether to toggle this button on or off."""
        self._native_widget.SetValue(value)

class CheckBox(_AButton):
    """Represents a simple two-state checkbox."""
    def __init__(self, parent, label=u'', on_toggle=None, tooltip=None,
                 checked=False):
        """Creates a new CheckBox with the specified properties.

        :param parent: The object that the checkbox belongs to.
        :param label: The text shown on the checkbox.
        :param on_toggle: A callback to execute when the button is clicked.
                          Takes a single parameter, a boolean that is True if
                          the checkbox is checked.
        :param tooltip: A tooltip to show when the user hovers over the
                        checkbox.
        :param checked: The initial state of the checkbox."""
        super(CheckBox, self).__init__()
        self._native_widget = _wx.CheckBox(parent, _wx.ID_ANY,
                                           label=label, name=u'checkBox')
        if on_toggle:
            def _toggle_callback(_event): # type: (_wx.Event) -> None
                on_toggle(self._native_widget.GetValue())
            self._native_widget.Bind(_wx.EVT_CHECKBOX, _toggle_callback)
        if tooltip:
            self.tooltip = tooltip
        self.checked = checked

    @property
    def checked(self): # type: () -> bool
        """Returns True if this checkbox is checked.

        :return: True if this checkbox is checked."""
        return self._native_widget.GetValue()

    @checked.setter
    def checked(self, value): # type: (bool) -> None
        """Checks or unchecks this checkbox depending on the specified
        parameter.

        :param value: Whether to check or uncheck this checkbox."""
        self._native_widget.SetValue(value)

# Text input ------------------------------------------------------------------
class _ATextInput(_AWidget):
    """Abstract base class for all text input classes."""
    # TODO: consider on_lose_focus
    # TODO: style and/or (fixed) font
    def __init__(self, parent, text=None, multiline=True, editable=True,
                 on_text_change=None, auto_tooltip=True, max_length=None,
                 no_border=False, style=0):
        """Creates a new _ATextInput instance with the specified properties.

        :param parent: The object that this text input belongs to.
        :param text: The initial text in this text input.
        :param multiline: True if this text input allows multiple lines.
        :param editable: True if the user may edit text in this text input.
        :param on_text_change: A callback to call whenever the text in this
                               text input changes. Takes a single parameter,
                               the wx event that occurred. TODO(inf) de-wx!
        :param auto_tooltip: Whether or not to automatically show a tooltip
                             when the entered text exceeds the length of this
                             text input.
        :param max_length: The maximum number of characters that can be
                           entered into this text input. None if you don't
                           want a limit.
        :param no_border: True if the borders of this text input should be
                          hidden.
        :param style: Internal parameter used to allow subclasses to wrap style
                      flags on their own."""
        super(_ATextInput, self).__init__()
        if multiline: style |= _wx.TE_MULTILINE
        if not editable: style |= _wx.TE_READONLY
        if no_border: style |= _wx.BORDER_NONE
        self._native_widget = _wx.TextCtrl(parent, style=style)
        if text: self._native_widget.SetValue(text)
        if on_text_change:
            self._native_widget.Bind(_wx.EVT_TEXT, on_text_change)
        if auto_tooltip:
            self._native_widget.Bind(_wx.EVT_SIZE, self.__on_size_change)
            self._native_widget.Bind(_wx.EVT_TEXT, self.__on_text_change)
        if max_length:
            self._native_widget.SetMaxLength(max_length)

    def __update_tooltip(self, text): # type: (unicode) -> None
        """Internal method that shows or hides the tooltip depending on the
        length of the currently entered text and the size of this text input.

        :param text: The text inside this text input."""
        w = self._native_widget
        self.tooltip = (text if w.GetClientSize()[0] < w.GetTextExtent(text)[0]
                        else None)

    def __on_text_change(self, event):
        """Internal callback that updates the tooltip when the text changes.

        :param event: The wx event that occurred."""
        self.__update_tooltip(event.GetString())
        event.Skip()

    def __on_size_change(self, event):
        """Internal callback that updates the tooltip when the size changes.

        :param event: The wx event that occurred."""
        self.__update_tooltip(self._native_widget.GetValue())
        event.Skip()

    @property
    def editable(self): # type: () -> bool
        """Returns True if this text input can be edited by the user.

        :return: True if this text input is editable."""
        return self._native_widget.IsEditable()

    @editable.setter
    def editable(self, is_editable): # type: (bool) -> None
        """Enables or disables user input to this text input based on the
        specified parameter.

        :param is_editable: Whether to enable or disable user input."""
        self._native_widget.SetEditable(is_editable)

    @property
    def text_content(self): # type: () -> unicode
        """Returns the text that is currently inside this text input.

        :return: The entered text."""
        return self._native_widget.GetValue()

    @text_content.setter
    def text_content(self, new_text): # type: (unicode) -> None
        """Changes the text inside this text input to the specified string.

        :param new_text: What to change this text input's text to."""
        self._native_widget.SetValue(new_text)

    @property
    def modified(self): # type: () -> bool
        """Returns True if the user has modified the text inside this text
        input.

        :return: True if this text input has been modified."""
        return self._native_widget.IsModified()

    @modified.setter
    def modified(self, is_modified):
        """Changes whether or not this text input is modified based on the
        specified parameter.

        :param is_modified: True if this text input should be marked as
                            modified."""
        self._native_widget.SetModified(is_modified)

class TextArea(_ATextInput):
    """A multi-line text edit widget."""
    def __init__(self, parent, text=None, editable=True, on_text_change=None,
                 auto_tooltip=True, max_length=None, no_border=False,
                 wrap=True):
        """Creates a new TextArea instance with the specified properties.

        :param parent: The object that this text input belongs to.
        :param text: The initial text in this text input.
        :param editable: True if the user may edit text in this text input.
        :param on_text_change: A callback to call whenever the text in this
                               text input changes. Takes a single parameter,
                               the wx event that occurred. TODO(inf) de-wx!
        :param auto_tooltip: Whether or not to automatically show a tooltip
                             when the entered text exceeds the length of this
                             text input.
        :param max_length: The maximum number of characters that can be
                           entered into this text input. None if you don't
                           want a limit.
        :param no_border: True if the borders of this text input should be
                          hidden.
        :param wrap: Whether or not to wrap text inside this text input."""
        wrap_style = _wx.TE_DONTWRAP if not wrap else 0
        super(TextArea, self).__init__(parent, text=text, editable=editable,
                                       on_text_change=on_text_change,
                                       auto_tooltip=auto_tooltip,
                                       max_length=max_length,
                                       no_border=no_border, style=wrap_style)

class TextField(_ATextInput):
    """A single-line text edit widget."""
    def __init__(self, parent, text=None, editable=True, on_text_change=None,
                 auto_tooltip=True, max_length=None, no_border=False):
        """Creates a new TextField instance with the specified properties.

        :param parent: The object that this text input belongs to.
        :param text: The initial text in this text input.
        :param editable: True if the user may edit text in this text input.
        :param on_text_change: A callback to call whenever the text in this
                               text input changes. Takes a single parameter,
                               the wx event that occurred. TODO(inf) de-wx!
        :param auto_tooltip: Whether or not to automatically show a tooltip
                             when the entered text exceeds the length of this
                             text input.
        :param max_length: The maximum number of characters that can be
                           entered into this text input. None if you don't
                           want a limit.
        :param no_border: True if the borders of this text input should be
                          hidden."""
        super(TextField, self).__init__(parent, text=text, multiline=False,
                                        editable=editable,
                                        on_text_change=on_text_change,
                                        auto_tooltip=auto_tooltip,
                                        max_length=max_length,
                                        no_border=no_border)

# Labels ----------------------------------------------------------------------
class _ALabel(_AWidget):
    """Abstract base class for labels."""
    @property
    def label_text(self): # type: () -> unicode
        """Returns the text of this label as a string.

        :return: The text of this label."""
        return self._native_widget.GetLabel()

    @label_text.setter
    def label_text(self, new_text): # type: (unicode) -> None
        """Changes the text of this label to the specified string.

        :param new_text: The new text to use."""
        self._native_widget.SetLabel(new_text)

class Label(_ALabel):
    """A static text element. Doesn't have a border and the text can't be
    interacted with by the user."""
    def __init__(self, parent, text):
        """Creates a new Label with the specified parent and text.

        :param parent: The object that this label belongs to.
        :param text: The text of this label."""
        super(Label, self).__init__()
        self._native_widget = _wx.StaticText(parent, _wx.ID_ANY, text)

    def wrap(self, max_length): # type: (int) -> None
        """Wraps this label's text so that each line is at most max_length
        pixels long.

        :param max_length: The maximum number of pixels a line may be long."""
        self._native_widget.Wrap(max_length)

class HyperlinkLabel(_ALabel):
    """A label that opens a URL when clicked, imitating a hyperlink in a
    browser. Typically styled blue."""
    def __init__(self, parent, text, url, always_unvisited=False):
        """Creates a new HyperlinkLabel with the specified parent, text and
        URL.

        :param parent: The object that this hyperlink label belongs to.
        :param text: The text of this hyperlink label.
        :param url: The URL to open when this hyperlink label is clicked on.
        :param always_unvisited: If set to True, this link will always appear
                                 as if it hasn't been clicked on (i.e. blue -
                                 it will never turn purple)."""
        super(HyperlinkLabel, self).__init__()
        self._native_widget = _wx.HyperlinkCtrl(parent, _wx.ID_ANY, text, url)
        if always_unvisited:
            self._native_widget.SetVisitedColour(
                self._native_widget.GetNormalColour())
