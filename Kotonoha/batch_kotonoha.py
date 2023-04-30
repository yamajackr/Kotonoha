# -*- coding: utf-8 -*-

# Kotonoha Add-on for Anki
#
# <https://github.com/yamajackr>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version, with the additions
# listed at the end of the license file that accompanied this program.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# NOTE: This program is subject to certain additional terms pursuant to
# Section 7 of the GNU Affero General Public License.  You should have
# received a copy of these additional terms immediately following the
# terms and conditions of the GNU Affero General Public License that
# accompanied this program.
#
# If not, please request a copy through one of the means of contact
# listed here: <https://glutanimate.com/contact/>.
#
# Any modifications to this file must keep this entire header intact.

"""
Initializes add-on components.
"""

from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

import tempfile

from anki import version as anki_version
from anki.hooks import addHook
from anki.lang import _
from aqt.qt import *
from aqt.utils import tooltip, askUser, getFile

from .gui import initializeQtResources
from .kotonoha import *

ANKI20 = anki_version.startswith("2.0")
unicode = str if not ANKI20 else unicode

initializeQtResources()


class BatchEditDialog(QDialog):
    """Browser batch editing dialog"""

    def __init__(self, browser, nids):
        QDialog.__init__(self, parent=browser)
        self.browser = browser
        self.nids = nids
        self._setupUi()

    def _setupUi(self):
        tlabel = QLabel("Choose Kotonoha you want to run")
        top_hbox = QHBoxLayout()
        top_hbox.addWidget(tlabel)
        top_hbox.insertStretch(1, stretch=1)

        # Create a pixmap from the image file
        pixmap = QPixmap(os.path.join(os.path.dirname(__file__), "images", "leaf_green.png"))
        # Scale the pixmap to the desired size
        scaled_pixmap = pixmap.scaledToWidth(400)
        # Create a QLabel and set the pixmap as the label's image
        image_label = QLabel()
        image_label.setPixmap(scaled_pixmap)
        ##image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        ##image_label.setScaledContents(True)

        # Center the image within the label
        image_label.setAlignment(Qt.AlignCenter)

        self.cb_overwrite = QCheckBox(self)
        self.cb_overwrite.setText("Overwrite")
        self.cb_overwrite.setChecked(False)
        s = QShortcut(QKeySequence(_("Alt+H")),
                      self, activated=lambda: self.cb_overwrite.setChecked(True))

        button_box = QDialogButtonBox(Qt.Horizontal, self)
        kotonoha1_btn = button_box.addButton(PRIMARY_DICT,
                                        QDialogButtonBox.ActionRole)
        kotonoha2_btn = button_box.addButton(SECONDARY_DICT,
                                        QDialogButtonBox.ActionRole)
        kotonoha_thes_btn = button_box.addButton(THESAURUS_DICT,
                                             QDialogButtonBox.ActionRole)
        close_btn = button_box.addButton("&Cancel",
                                         QDialogButtonBox.RejectRole)
        kotonoha1_btn.setToolTip("Run Kotonoha")
        kotonoha2_btn.setToolTip("Run Kotonoha")
        kotonoha_thes_btn.setToolTip("Run Kotonoha Thesaurus")
        kotonoha1_btn.clicked.connect(lambda state, x="kotonoha1": self.onConfirm(x))
        kotonoha2_btn.clicked.connect(lambda state, x="kotonoha2": self.onConfirm(x))
        kotonoha_thes_btn.clicked.connect(lambda state, x="kotonoha_thes": self.onConfirm(x))
        close_btn.clicked.connect(self.close)

        bottom_hbox = QHBoxLayout()
        bottom_hbox.addWidget(self.cb_overwrite)
        bottom_hbox.addWidget(button_box)


        vbox_main = QVBoxLayout()
        vbox_main.addWidget(image_label)
        vbox_main.addLayout(bottom_hbox)
        self.setLayout(vbox_main)
        self.setMinimumWidth(540)
        self.setMinimumHeight(300)
        self.setWindowTitle("Batch Kotonoha for Selected Notes")

    def _getFields(self):
        nid = self.nids[0]
        mw = self.browser.mw
        model = mw.col.getNote(nid).model()
        fields = mw.col.models.fieldNames(model)
        return fields

    def onConfirm(self, mode):
        browser = self.browser
        nids = self.nids
        isOVERWRITE = self.cb_overwrite.isChecked()
        batchEditNotes(browser, mode, nids, isOVERWRITE=isOVERWRITE)
        self.close()


def batchEditNotes(browser, mode, nids, isOVERWRITE=False):
    mw = browser.mw
    mw.checkpoint("batch edit")
    mw.progress.start()
    browser.model.beginReset()
    cnt = 0
    for nid in nids:
        note = mw.col.getNote(nid)
        if mode == "kotonoha1":
            editor = browser.editor
            get_definition_b(editor, note, button='primary', overwrite=isOVERWRITE)
        elif mode == "kotonoha2":
            editor=browser.editor
            get_definition_b(editor, note, button='secondary', overwrite=isOVERWRITE)
        elif mode == "kotonoha_thes":
            editor=browser.editor
            get_definition_b(editor, note, button='secondary', overwrite=isOVERWRITE)
        cnt += 1
        note.flush()
    browser.model.endReset()
    mw.requireReset()
    mw.progress.finish()
    mw.reset()
    tooltip("<b>Updated</b> {0} notes.".format(cnt), parent=browser)


def onBatchEdit(browser):
    nids = browser.selectedNotes()
    if not nids:
        tooltip("No cards selected.")
        return
    dialog = BatchEditDialog(browser, nids)
    dialog.exec_()


def setupMenu(browser):
    menu = browser.form.menuEdit
    menu.addSeparator()
    a = menu.addAction('Batch Kotonoha...')
    a.setShortcut(QKeySequence("Ctrl+Alt+B"))
    a.triggered.connect(lambda _, b=browser: onBatchEdit(b))


addHook("browser.setupMenus", setupMenu)
