# Kotonoha Anki Add-on
# Kotonoha - Automatically add the pronunciation, definition etc. of the word in the editor
#
# https://github.com/yamamotoryo/Kotonoha                      Licensed under GPL v3

import os
import sys
from collections import namedtuple
import time
import platform
import re
import traceback
import urllib.error
from urllib.error import URLError
import urllib.parse
import urllib.request

import requests

from bs4 import BeautifulSoup
from anki import version
from anki.hooks import addHook
from aqt import mw
from aqt.utils import showInfo, tooltip
import csv

from .libs import webbrowser

from anki.hooks import addHook
from aqt import mw
from aqt.qt import *
from aqt.utils import showInfo, showWarning, tooltip
from bs4 import BeautifulSoup
from PyQt5.QtGui import QIcon
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication, QDialog

from . import form, lang

addon_dir = os.path.dirname(os.path.realpath(__file__))
libs_dir = os.path.join(addon_dir, "libs")
sys.path.append(libs_dir)

import deepl


class Kotonoha_dialog(QDialog):
    def __init__(self, context, nids=None) -> None:
        if nids is None:
            self.editor = context
            self.browser = None
            self.parentWindow = self.editor.parentWindow
            self.note = self.editor.note
            self.nids = [None]
        else:
            self.editor = None
            self.browser = context
            self.parentWindow = self.browser
            self.note = None
            self.nids = nids
        self.total_count = 0
        self.exception = None
        self.translator = None

        QDialog.__init__(self, self.parentWindow)

        self.form = form.Ui_Dialog()
        self.form.setupUi(self)

        self.sourceLanguages = {}
        for x in lang.source_languages:
            assert x["name"] not in self.sourceLanguages, x["name"]
            self.sourceLanguages[x["name"]] = x["code"]

        self.targetLanguages = {}
        for x in lang.target_languages:
            assert x["name"] not in self.targetLanguages, x["name"]
            self.targetLanguages[x["name"]] = x["code"]

        self.form.sourceLang.addItems(self.sourceLanguages)

        self.form.targetLang.addItems(self.targetLanguages)
        self.form.targetLang.setCurrentIndex(
            list(self.targetLanguages).index("English (American)")
        )

        self.form.sourceLang.addItems(self.sourceLanguages)

        def getLangCode(combobox, languages):
            text = combobox.currentText()
            if not text:
                return "##"
            return languages[text]

        def updateTargetLang():
            self.sourceLangCode = getLangCode(
                self.form.sourceLang, self.sourceLanguages
            )
            self.targetLangCode = getLangCode(
                self.form.targetLang, self.targetLanguages
            )
            if self.targetLangCode.startswith(self.sourceLangCode):
                self.form.targetLang.blockSignals(True)
                self.form.targetLang.setCurrentIndex(-1)
                self.form.targetLang.blockSignals(False)

        def updateSourceLang():
            self.sourceLangCode = getLangCode(
                self.form.sourceLang, self.sourceLanguages
            )
            self.targetLangCode = getLangCode(
                self.form.targetLang, self.targetLanguages
            )
            if self.targetLangCode.startswith(self.sourceLangCode):
                self.form.sourceLang.blockSignals(True)
                self.form.sourceLang.setCurrentIndex(0)
                self.form.sourceLang.blockSignals(False)

        self.form.sourceLang.currentIndexChanged.connect(updateTargetLang)
        self.form.targetLang.currentIndexChanged.connect(updateSourceLang)

        if not self.note:
            self.note = mw.col.getNote(nids[0])
        fields = list(self.note.keys())
        fields.append('Off')

        self.form.sourceField.addItems(fields)
        self.form.sourceField.setCurrentIndex(0)

        self.form.targetField.addItems(fields)
        self.form.targetField.setCurrentIndex(1)

        self.form.PronField.addItems(fields)
        self.form.PronField.setCurrentIndex(0)

        self.form.DefField.addItems(fields)
        self.form.DefField.setCurrentIndex(1)

        self.form.JapField.addItems(fields)
        self.form.JapField.setCurrentIndex(1)

        self.form.ImgField.addItems(fields)
        self.form.ImgField.setCurrentIndex(1)

        self.form.DicField.addItems(fields)
        self.form.DicField.setCurrentIndex(1)

        # get config
        self.config = mw.addonManager.getConfig(__name__)

        import random
        self.ImgPath = self.config['Dialog Image Path']
        # Create a pixmap from the image file
        path = os.path.join(os.path.dirname(__file__), "images", self.ImgPath)
        if os.path.isdir(path):
            files = []
            for f in os.listdir(path=path):
                if not f.startswith('.'):
                    files.append(f)
            final_path = os.path.join(path, files[random.randint(0, len(files) - 1)])
        else:
            final_path = path

        pixmap = QPixmap(final_path)
        # Scale the pixmap to the desired size
        scaled_pixmap = pixmap.scaledToWidth(200)

        self.form.imglabel.setPixmap(scaled_pixmap)
        ##image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        ##image_label.setScaledContents(True)

        # Center the image within the label
        self.form.imglabel.setAlignment(Qt.AlignCenter)

        # set dictionaries from config
        self.dictionaries = self.config['Dictionaries']
        self.form.dic_box.addItems(list(self.dictionaries.values()))

        self.boxformat = self.config['BOX_FORMAT']

        for fld, cb in [
            ("Source Field", self.form.sourceField),
            ("DeepL Field", self.form.targetField),
            ("Pronunciation Field", self.form.PronField),
            ("Definition Field", self.form.DefField),
            ("Japanese Field", self.form.JapField),
            ("Image Field", self.form.ImgField),
            ("Dictionary Field", self.form.DicField)
        ]:
            if self.config['Fields'][fld] and self.config['Fields'][fld] in fields:
                cb.setCurrentIndex(fields.index(self.config['Fields'][fld]))

        for key, cb in [
            ("Source Language", self.form.sourceLang),
            ("Target Language", self.form.targetLang),
            ("Dictionary", self.form.dic_box),
            ("Mode", self.form.mode_box)
        ]:
            if self.config[key]:
                cb.setCurrentIndex(cb.findText(self.config[key]))
        self.form.searchWord.setText(self.config['Additional Search Word'])

        if self.config["Strip HTML"]:
            self.form.formatText.setChecked(True)
        else:
            self.form.formatHTML.setChecked(True)

        self.form.checkBoxOverwrite.setChecked(self.config["Overwrite"])
        self.form.OpenWeb.setChecked(self.config["Open Web Browser"])

        self.learners_api_key = self.config["API keys"]["LEARNERS_API_KEY"]
        self.elementary_api_key = self.config["API keys"]["ELEMENTARY_API_KEY"]
        self.medical_api_key = self.config["API keys"]["MEDICAL_API_KEY"]
        self.collegiate_api_key = self.config["API keys"]["COLLEGIATE_API_KEY"]
        self.thesaurus_api_key = self.config["API keys"]["THESAURUS_API_KEY"]
        self.deepl_api_key = self.config["API keys"]["DeepL API Key"]

        self.form.LearnersApiKey.setText(self.learners_api_key)
        self.form.ElementaryApiKey.setText(self.elementary_api_key)
        self.form.MedicalApiKey.setText(self.medical_api_key)
        self.form.CollegiateApiKey.setText(self.collegiate_api_key)
        self.form.DeeplApiKey.setText(self.deepl_api_key)

        self.usage = None

        if self.learners_api_key or self.elementary_api_key or self.medical_api_key or self.collegiate_api_key:
            try:
                self.form.MerriamKeyBox.hide()
                self.adjustSize()
            except Exception as e:
                pass

        if self.deepl_api_key:
            try:
                self.form.apiKeyBox.hide()
                self.adjustSize()
                self.translator = deepl.Translator(self.deepl_api_key, skip_language_check=True)
                if self.browser:
                    self.usage = self.translator.get_usage()
            except Exception as e:
                pass

        self.icon = os.path.join(os.path.dirname(__file__), "leaf_orange.png")
        self.setWindowIcon(QIcon(self.icon))

        if self.usage:
            self.usage.character.limit_exceeded
            self.form.usage.setText(
                "Usage: {}/{}".format(
                    self.usage.character.count, self.usage.character.limit
                )
            )
        else:
            self.form.usage.setText("")

        self.show()

    def sleep(self, seconds):
        start = time.time()
        while time.time() - start < seconds:
            time.sleep(0.01)
            QApplication.instance().processEvents()

    def escape_clozes(self, match):
        self.cloze_id += 1
        cloze_number = match.group('number')
        cloze_text = match.group('text')
        cloze_hint = match.group('hint')
        self.cloze_deletions[self.cloze_id] = {
            'number': cloze_number,
            'hint': cloze_hint
        }
        return ' <c{0}>{1}</c{0}> '.format(self.cloze_id, cloze_text)

    def unescape_clozes(self, match):
        cloze = self.cloze_deletions[int(match.group('id'))]
        txt = '{{'
        txt += 'c{}::{}'.format(cloze['number'], match.group('text'))
        if cloze['hint']:
            txt += '::{}'.format(cloze['hint'])
        txt += '}}'
        return txt

    def accept(self):
        self.sourceField = self.form.sourceField.currentText()
        self.targetField = self.form.targetField.currentText()
        self.PronField = self.form.PronField.currentText()
        self.DefField = self.form.DefField.currentText()
        self.JapField = self.form.JapField.currentText()
        self.ImgField = self.form.ImgField.currentText()
        self.DicField = self.form.DicField.currentText()

        self.config['Fields']["Source Field"] = self.sourceField
        self.config['Fields']["DeepL Field"] = self.targetField
        self.config['Fields']["Pronunciation Field"] = self.PronField
        self.config['Fields']["Definition Field"] = self.DefField
        self.config['Fields']["Japanese Field"] = self.JapField
        self.config['Fields']["Image Field"] = self.ImgField
        self.config['Fields']["Dictionary Field"] = self.DicField

        fields = self.note.keys()
        fields.append('Off')
        sourceIndex = fields.index(self.sourceField)
        if self.PronField=='Off':
            PronIndex = -1
        else:
            PronIndex = fields.index(self.PronField)
        if self.DefField=='Off':
            DefIndex = -1
        else:
            DefIndex = fields.index(self.DefField)
        if self.JapField=='Off':
            JapIndex = -1
        else:
            JapIndex = fields.index(self.JapField)
        if self.ImgField=='Off':
            ImgIndex = -1
        else:
            ImgIndex = fields.index(self.ImgField)
        if self.DicField=='Off':
            DicIndex = -1
        else:
            DicIndex = fields.index(self.DicField)


        self.sourceLang = self.form.sourceLang.currentText()
        self.targetLang = self.form.targetLang.currentText()

        self.dictionary = self.form.dic_box.currentText()
        self.mode = self.form.mode_box.currentText()

        self.learners_api_key = self.form.LearnersApiKey.text().strip()
        self.elementary_api_key = self.form.ElementaryApiKey.text().strip()
        self.medical_api_key = self.form.MedicalApiKey.text().strip()
        self.collegiate_api_key = self.form.CollegiateApiKey.text().strip()
        self.config["API keys"]["LEARNERS_API_KEY"] = self.learners_api_key
        self.config["API keys"]["ELEMENTARY_API_KEY"] = self.elementary_api_key
        self.config["API keys"]["MEDICAL_API_KEY"] = self.medical_api_key
        self.config["API keys"]["COLLEGIATE_API_KEY"] = self.collegiate_api_key

        self.deepl_api_key = self.form.DeeplApiKey.text().strip()

        if not self.targetLang:
            return showWarning("Select target language")

        if not self.learners_api_key and not self.elementary_api_key and \
                not self.medical_api_key and not self.collegiate_api_key:
            message = "Kotonoha requires Merriam-Webster's Dictionary with Audio API. " \
                      "To get functionality working:\n" \
                      "1. Go to www.dictionaryapi.com and sign up for an account, requesting access to " \
                      "the dictionary. \n" \
                      "2. In Anki, go to Tools > Add-Ons. Select Kotonoha, click \"Config\" on the right-hand side " \
                      "and replace YOUR_KEY_HERE with your unique API key.\n"
            showWarning(message)
            webbrowser.open("https://www.dictionaryapi.com/", 0, False)

        # if not self.deepl_api_key:
        #     return showWarning(
        #         "To use the add-on and translate up to 500,000 characters/month for free, "
        #         "you'll need an API authentication key. "
        #         'To get a key, <a href="https://www.deepl.com/pro#developer">create an account with the DeepL API Free plan here</a>.',
        #         title="Kotonoha",
        #     )

        # try:
        #     self.translator = deepl.Translator(self.deepl_api_key, skip_language_check=True)
        #     self.translator.get_usage()
        #     self.config["API keys"]["DeepL API Key"] = self.deepl_api_key
        # except deepl.exceptions.AuthorizationException:
        #     showWarning(
        #         "Authorization failed, check your authentication key.",
        #         title="Kotonoha",
        #     )
        #     self.form.apiKeyBox.show()
        #     return
        # except:
        #     raise

        QDialog.accept(self)

        self.config["Source Language"] = self.sourceLang
        self.config["Target Language"] = self.targetLang
        self.config["Strip HTML"] = self.form.formatText.isChecked()
        self.config["Overwrite"] = self.form.checkBoxOverwrite.isChecked()
        self.config["Open Web Browser"] = self.form.OpenWeb.isChecked()
        self.config["Additional Search Word"] = self.form.searchWord.text()
        self.config["Mode"] = self.mode
        self.config["Dictionary"] = self.dictionary

        mw.addonManager.writeConfig(__name__, self.config)

        self.sourceLangCode = self.sourceLanguages[self.sourceLang]
        self.targetLangCode = self.targetLanguages[self.targetLang]

        if self.browser:
            self.browser.mw.progress.start(parent=self.browser)
            self.browser.mw.progress._win.setWindowIcon(QIcon(self.icon))
            self.browser.mw.progress._win.setWindowTitle("Kotonoha Dialog")

        progress = 0

        exception = None
        try:
            for nid in self.nids:
                if self.editor:
                    note = self.note
                else:
                    note = mw.col.getNote(nid)

                if not note[self.sourceField]:
                    continue
                if self.sourceField not in note:
                    continue

                word = note[self.sourceField]
                # get the first line
                word = word.split('<br>')[0]
                if self.config["Strip HTML"]:
                    soup = BeautifulSoup(word, "html.parser")
                    word = soup.get_text()
                else:
                    word = word.replace('&nbsp;', ' ')
                    word = re.sub(r' +(</[^>]+>)', r'\1 ', word)
                word = re.sub(r'\s+', ' ', word)
                word = word.strip()

                if not word:
                    continue

                self.cloze_id = 0
                self.cloze_deletions = {}
                word = re.sub(r"{{c(?P<number>\d+)::(?P<text>.*?)(::(?P<hint>.*?))?}}", self.escape_clozes, word, flags=re.I)
                self.cloze_hints = [c['hint'] for c in self.cloze_deletions.values() if c['hint']]

                time_to_sleep = 1

                self.total_count += len(word)

                # Find the key for dictionary button
                Dict = self.dictionary.lower()

                if self.mode == "Default":
                    if self.editor:
                        editor = self.editor
                    else:
                        editor = self.browser.editor
                    get_definition_b(self, editor, note,
                                     sourceField=sourceIndex,
                                     button=Dict,
                                     overwrite=self.config["Overwrite"],
                                     openweb=self.config["Open Web Browser"],
                                     searchWord=self.config["Additional Search Word"],
                                     target_lang_code=self.targetLangCode,
                                     PronField=PronIndex,
                                     DefField=DefIndex,
                                     JapField=JapIndex,
                                     ImgField=ImgIndex,
                                     DicField=DicIndex,
                                     cloze=False)
                elif self.mode == "Cloze_sentence":
                    if self.editor:
                        editor = self.editor
                    else:
                        editor = self.browser.editor
                    get_definition_b(self, editor, note,
                                     sourceField=sourceIndex,
                                     button=Dict,
                                     overwrite=self.config["Overwrite"],
                                     openweb=self.config["Open Web Browser"],
                                     searchWord=self.config["Additional Search Word"],
                                     target_lang_code =self.targetLangCode,
                                     PronField=PronIndex,
                                     DefField=DefIndex,
                                     JapField=JapIndex,
                                     ImgField=ImgIndex,
                                     DicField=DicIndex,
                                     cloze=True)

                elif self.mode=='DeepL':
                    translated_results = {}
                    for key, data in [("text", word), ("hints", self.cloze_hints)]:
                        if key == "hints" and len(self.cloze_hints) == 0:
                            break
                        while True:
                            if self.browser and self.browser.mw.progress._win.wantCancel:
                                break
                            try:
                                if self.sourceLangCode != "AUTO":
                                    source_lang = self.sourceLangCode
                                else:
                                    source_lang = None
                                target_lang = self.targetLangCode
                                if not self.config["Strip HTML"]:
                                    tag_handling = "xml"
                                else:
                                    tag_handling = None
                                result = self.translator.translate_text(
                                    data,
                                    source_lang=source_lang,
                                    target_lang=target_lang,
                                    tag_handling=tag_handling,
                                    split_sentences="nonewlines",
                                    outline_detection=True,
                                    ignore_tags=["sub", "sup"],
                                )
                                translated_results[key] = result
                                break
                            except deepl.exceptions.TooManyRequestsException:
                                if self.browser:
                                    self.browser.mw.progress.update(
                                        "Too many requests. Sleeping for {} seconds.".format(
                                            time_to_sleep
                                        )
                                    )
                                    self.sleep(time_to_sleep)
                                    # https://support.deepl.com/hc/en-us/articles/360020710619-Error-code-429
                                    time_to_sleep *= 2
                                else:
                                    showWarning(
                                        "Too many requests. Please wait and resend your request.",
                                        parent=self.parentWindow,
                                    )

                    if self.cloze_hints:
                        cloze_hints_translated = [tr.text for tr in translated_results["hints"]]
                        assert len(self.cloze_hints) == len(cloze_hints_translated)
                        hint_idx = 0
                        for c in self.cloze_deletions.values():
                            if c['hint']:
                                c['hint'] = cloze_hints_translated[hint_idx]
                                hint_idx += 1

                    text = translated_results["text"].text

                    text = re.sub(r' (<c\d+>) ', r' \1', text)
                    text = re.sub(r' (</c\d+>) ', r'\1 ', text)
                    text = re.sub(r'<c(?P<id>\d+)>(?P<text>.*?)</c(?P=id)>', self.unescape_clozes, text)
                    text = re.sub(r' , ', ', ', text)


                    note[self.targetField] += text

                elif self.mode == 'Pokemon':
                    if self.editor:
                        editor = self.editor
                    else:
                        editor = self.browser.editor
                    get_pokemon(editor, note,
                                     sourceField=sourceIndex,
                                     openweb=self.config["Open Web Browser"],
                                     searchWord=self.config["Additional Search Word"],
                                     DefField=DefIndex,
                                     ImgField=ImgIndex,
                                     JapField=JapIndex
                                     )



                if self.editor:
                    self.editor.setNote(note)
                else:
                    note.flush()

                progress += 1

               #if self.browser:
                #    self.browser.mw.progress.update(
                 #       "Processed {}/{} notes...".format(progress, len(self.nids))
                  #  )
                   # QApplication.instance().processEvents()
        except Exception as e:
            exception = e
        finally:
            if self.browser:
                self.browser.mw.progress.finish()
                self.browser.mw.reset()
                mw.col.save()

        if exception:
            try:
                raise exception
            except deepl.exceptions.QuotaExceededException:
                showWarning(
                    "Quota for this billing period has been exceeded.",
                    parent=self.parentWindow,
                )
        else:
            if self.browser:
                tooltip(
                    "Processed {} notes.".format(len(self.nids)),
                    parent=self.browser,
                )


def onKotonohaDialog(browser):
    nids = browser.selectedNotes()

    if not nids:
        return tooltip("No cards selected.")

    Kotonoha_dialog(browser, nids)

if getattr(mw.addonManager, "getConfig", None):
    config = mw.addonManager.getConfig(__name__)
    D_SHORT = config['shortcuts']['DIALOG_SHORTCUT']
    B_SHORT = config['shortcuts']['BROWSER_SHORTCUT']


def setupMenu(browser):
    a = QAction("Kotonoha Dialog", browser)
    a.triggered.connect(lambda: onKotonohaDialog(browser))
    browser.form.menuEdit.addSeparator()

    a.setShortcut(QKeySequence(B_SHORT))
    browser.form.menuEdit.addAction(a)


addHook("browser.setupMenus", setupMenu)


def onEditorButton(editor):
    Kotonoha_dialog(editor)
    return None


def onSetupEditorButtons(buttons, editor):
    icon = os.path.join(os.path.dirname(__file__), 'images',"leaf_green.png")
    b = editor.addButton(
        icon,
        "Kotonoha dialog",
        lambda e=editor: onEditorButton(e),
        keys=D_SHORT,
        tip="Kotonoha dialog: (%s)" %(D_SHORT)
    )
    buttons.append(b)
    return buttons


from aqt.gui_hooks import editor_did_init_buttons

editor_did_init_buttons.append(onSetupEditorButtons)



def choose_url(word, DICT, API_KEY):
    if DICT == "LEARNERS":
        url = "https://www.dictionaryapi.com/api/v3/references/learners/json/" + \
                    urllib.parse.quote(word) + "?key=" + API_KEY
        return(url)
    if DICT == "ELEMENTARY":
        url = "https://www.dictionaryapi.com/api/v3/references/sd2/json/" + \
                    urllib.parse.quote(word) + "?key=" + API_KEY
        return(url)
    if DICT == "MEDICAL":
        url = "https://www.dictionaryapi.com/api/v3/references/medical/json/" + \
                    urllib.parse.quote(word) + "?key=" + API_KEY
        return(url)
    if DICT == "COLLEGIATE":
        url = "https://www.dictionaryapi.com/api/v3/references/collegiate/json/" + \
                    urllib.parse.quote(word) + "?key=" + API_KEY
        return(url)
    if DICT == "COLLEGIATE_THESAURUS":
        url = "https://www.dictionaryapi.com/api/v3/references/thesaurus/json/" + \
                    urllib.parse.quote(word) + "?key=" + API_KEY
        return (url)
    if DICT == "INTERMEDIATE_THESAURUS":
        url = "https://www.dictionaryapi.com/api/v3/references/ithesaurus/json/" + \
                    urllib.parse.quote(word) + "?key=" + API_KEY
        return(url)
def get_preferred_valid_entries_j(self, word, valid_dic_name, button):
    if button=='learners':
        DICT = 'LEARNERS'
        API_KEY = self.learners_api_key
        URL = choose_url(word, DICT, API_KEY)
        if API_KEY == '':
            showInfo("LEARNERS_API_KEY is blank. Get the API key")
            all_entries = []
        else:
            all_entries = get_entries_from_api_j(url=URL, word=word)
        valid_dic_name.append(DICT)
        return all_entries

    elif button=='elementary':
        DICT = 'ELEMENTARY'
        API_KEY = self.elementary_api_key
        URL = choose_url(word, DICT, API_KEY)
        if API_KEY == '':
            showInfo("ELEMENTARY_API_KEY is blank. Get the API key")
            all_entries = []
        else:
            all_entries = get_entries_from_api_j(url=URL, word=word)
        valid_dic_name.append(DICT)
        return all_entries

    elif button=='collegiate':
        DICT = 'COLLEGIATE'
        API_KEY = self.collegiate_api_key
        URL = choose_url(word, DICT, API_KEY)
        if API_KEY == '':
            showInfo("COLLEGIATE_API_KEY is blank. Get the API key")
            all_entries = []
        else:
            all_entries = get_entries_from_api_j(url=URL, word=word)
        valid_dic_name.append(DICT)
        return all_entries
    elif button=='medical':
        DICT = 'MEDICAL'
        API_KEY = self.medical_api_key
        URL = choose_url(word, DICT, API_KEY)
        if API_KEY == '':
            showInfo("MEDICAL_API_KEY is blank. Get the API key")
            all_entries = []
        else:
            all_entries = get_entries_from_api_j(url=URL, word=word)
        valid_dic_name.append(DICT)
        return all_entries

    elif button=='collegiate_thesaurus':
        DICT = 'COLLEGIATE_THESAURUS'
        API_KEY = self.thesaurus_api_key
        URL = choose_url(word, DICT, API_KEY)
        if API_KEY == '':
            showInfo("THESAURUS_API_KEY is blank. Get the API key")
            all_entries = []
        else:
            all_entries = get_entries_from_api_j(url=URL, word=word)
        valid_dic_name.append(DICT)
        return all_entries

def get_entries_from_api_j(url, word):
    if "YOUR_KEY_HERE" in url:
        return []
    try:
        response = requests.get(url)
        if 'Invalid API key' in response.text:
            showInfo("API key '%s' is invalid. Please double-check you are using the pair of key and dictionary. "
                     "A web browser with the web page that lists your keys will open." % url.split("?key=")[1])
            webbrowser.open("https://www.dictionaryapi.com/account/my-keys.htm")
            return []
        else:
            # Extract the JSON data from the response
            potential_entries = response.json()
            # check response
            check_response = all(isinstance(element, str) for element in potential_entries)
            if check_response:
                valid_entries = potential_entries
            else:
                valid_entries = []
                for e in potential_entries:
                    Id = json_extract_dict(obj=e, key='id')
                    if word==''.join(Id) or re.search(pattern=word+':', string=''.join(Id)):
                        valid_entries.append(e)
            return valid_entries
    except URLError:
        return []

def _get_word_b(editor, note, sourceField=0):
    fields = list(note.keys())
    word=''
    maybe_web = editor.web
    if maybe_web:
        word = maybe_web.selectedText()
    if word is None or word == "":
        word = note[fields[sourceField]]
    # use the first line
    word = word.split('<br>')[0]
    word = clean_html(word).strip()

    if str.isascii(word):
        return word
    else:
        tooltip("Kotonoha has detected a word with non-ASCII characters, which it is unable to recognize. \
        By default, Kotonoha detects all the text in the front note. \
        When you select a part of the text, Kotonoha searches for its definition. \
        To avoid errors, ensure that the text you select does not contain any non-ASCII characters.")
        return word

def get_definition_b(self, editor, note, sourceField=0, button='learners', overwrite=False,
                     openweb=False, searchWord='',
                     cloze=False, DicName=True,
                     PronField=0,DicField=1,DefField=1,JapField=1,ImgField=2, target_lang_code='JA',
                     from_editor=False):
    if from_editor:
        config = mw.addonManager.getConfig(__name__)
        overwrite = config["Overwrite"]
        openweb = config["Open Web Browser"]
        searchWord = config["Additional Search Word"]
        fields = note.keys()
        fields.append('Off')
        sourceField = fields.index(config['Fields']['Source Field'])
        PronField = config['Fields']['Pronunciation Field']
        if PronField=='Off':
            PronField = -1
        else:
            PronField = fields.index(PronField)
        DefField = config['Fields']['Definition Field']
        if DefField == 'Off':
            DefField = -1
        else:
            DefField = fields.index(DefField)
        JapField = config['Fields']['Japanese Field']
        if JapField == 'Off':
            JapField = -1
        else:
            JapField = fields.index(JapField)
        ImgField = config['Fields']['Image Field']
        if ImgField == 'Off':
            ImgField = -1
        else:
            ImgField = fields.index(ImgField)
        DicField = config['Fields']['Dictionary Field']
        if DicField == 'Off':
            DicField = -1
        else:
            DicField = fields.index(DicField)

    fields=list(note.keys())
    word = _get_word_b(editor=editor, note=note, sourceField=sourceField)

    if word == "":
        tooltip("Kotonoha: No text found in note fields.")
        return
    valid_dic_name=[]
    valid_entries = get_preferred_valid_entries_j(self, word, valid_dic_name=valid_dic_name,button=button)
    check_response = all(isinstance(element, str) for element in valid_entries)
    insert_queue = {}
    if overwrite:
        _add_to_insert_queue(insert_queue,word,field_index=sourceField)
    if check_response:
        tooltip('Possible words are: ' + ','.join(valid_entries))
        return
    else:
        def_list = []
        # Add Vocal Pronunciation
        if PronField > -1:
            # Parse all unique pronunciations, and convert them to URLs as per http://goo.gl/nL0vte
            all_sounds = []

            for e in valid_entries:
                if json_extract_dict(obj=json_extract_dict(obj=e, key='hwi'), key='prs'):
                    if 'fl' in e:
                        FL = (_abbreviate_fl(e['fl']))
                    else:
                        FL = ''
                    for prs in json_extract_dict(obj=json_extract_dict(obj=e, key='hwi'), key='prs'):
                        if (not json_extract_dict(prs, 'ipa') and not json_extract_dict(prs, 'mw')) or not json_extract_dict(prs, 'audio'):
                            continue
                        else:
                            if json_extract_dict(prs, key='ipa'):
                                phoneme=json_extract_dict(prs, key='ipa')[0]
                            else:
                                phoneme = json_extract_dict(prs, key='mw')[0]
                            audio = json_extract_dict(prs, key='audio')[0]
                            # select audio includes the first 3 letters of the word
                            # to remove unrelated sound files
                            if word[:3] in audio:
                                if audio[:3] == "bix":
                                    subdir = "bix"
                                elif audio[:2] == "gg":
                                    subdir = "gg"
                                elif audio[:1].isdigit():
                                    subdir = "number"
                                else:
                                    subdir = audio[:1]
                                mp3_url = 'https://media.merriam-webster.com/audio/prons/en/us/mp3/' + subdir + '/' + \
                                          audio + '.mp3'
                                all_sounds.append(FL + ' [' + phoneme + '] ' + editor.urlToLink(mp3_url).strip())
                else:
                    continue
            # We want to make this a non-duplicate list, so that we only get unique sound files.
            all_sounds = list(dict.fromkeys(all_sounds))
            if cloze:
                to_print='<br>'.join(all_sounds)
                _add_to_insert_queue(insert_queue, to_print, 1)
            else:
                for x in all_sounds:
                    _add_to_insert_queue(insert_queue, x, PronField)
        # Add Definition json


        fl_list = []
        for entry in valid_entries:
            if 'fl' not in entry:
                continue
            fl = entry['fl']
            fl_list.append(fl)
        # unique fl list
        fl_list = list(set(fl_list))
        # group by fl
        grouped = {}
        for x in fl_list:
            grouped[x] = []
        for e in valid_entries:
            if 'fl' in e:
                category=e['fl']
                grouped[category].append(e)

        if DicField > -1:
            # add inflection
            dic_list = []
            for e in valid_entries:
                if 'ins' in e:
                    category = (_abbreviate_fl(e['fl']))
                    dic_list.append(category + 'inf: ' + ', '.join(json_extract_dict(obj=e, key='if')))
            # add cross-references
            for e in valid_entries:
                if 'cxs' in e:
                    dic_list.append(
                        json_extract_dict(obj=e, key='cxl')[0] + ' ' + json_extract_dict(obj=e, key='cxt')[0])
            dic_list = list(set(dic_list))
            if DicName:
                Dic_html = '<div class ="dic_box" >' + \
                           '<span class ="box-title">' + '@' + ''.join(valid_dic_name) + '</span>' + \
                           '<p>' + '<br>'.join(dic_list) + '</p>' + \
                           '</div>'
            else:
                Dic_html = '<div class ="dic_box" >' + \
                           '<span class ="box-title">' + '</span>' + \
                           '<p>' + '<br>'.join(dic_list) + '</p>' + \
                           '</div>'

            _add_to_insert_queue(insert_queue, Dic_html, DicField)


            # add shortdef, example, thesaurus
        if DefField > -1:
            vis_list=[]
            for FL in fl_list:
                g = grouped[FL]
                for i in range(len(g)):
                    entry = g[i]
                    if 'def' in entry:
                        sseq = json_extract_dict(obj=entry['def'], key='sseq')
                        for a in sseq:
                            for b in a:
                                suffix = ''.join(json_extract_dict(extract_text(b, 'sen'), 'sn'))
                                c = extract_text(b, 'sense')
                                for d in c:
                                    sn = suffix+''.join(json_extract_dict(d, 'sn'))
                                    dt = extract_text(d, 'text')[0][1]
                                    vis = json_extract_dict(obj=d, key='t')
                                    syn = json_extract_dict(obj=json_extract_dict(obj=d, key='syn_list'),
                                                                 key='wd')  # as list
                                    ant = json_extract_dict(obj=json_extract_dict(obj=d, key='ant_list'),
                                                                 key='wd')  # as list
                                    _make_def_vis_format(def_list, vis_list, FL, sn, dt, vis, syn, ant,
                                                         BOX_FORMAT=self.boxformat)

                    Syns = json_extract_dict(obj=json_extract_dict(obj=entry, key='syns'),
                                             key='pt')  # as list
                    Ants = json_extract_dict(obj=json_extract_dict(obj=entry, key='ants'),
                                             key='pt')  # as list
                    if self.boxformat:
                        if len(Syns) > 0:
                            Syn = Syns[0][0][1].split('.')[0].strip().replace("{sc}",
                                                                              "<span class=\"text_highlight\">").replace(
                                "{/sc}", "</span>,")
                            Syn_html = '<div class ="syn_box" >' + \
                                       '<span class ="box-title"> Synonym </span>' + \
                                       '<p>' + Syn + '</p>' + \
                                       '</div>'
                        else:
                            Syn_html = ''
                        def_list.append(Syn_html)
                    else:
                        if len(Syns) > 0:
                            Syn = Syns[0][0][1].split('.')[0].strip()
                            def_list.append(Syn)
            if cloze:
                for v in vis_list:
                    v = re.sub("\{.....\}", "\"", v)
                    txt = re.sub("\{..\}", "", v)
                    txt = re.sub("\{...\}", "", txt)
                    txt = re.sub("\{phrase\}", "", txt)
                    txt = re.sub("\{.phrase\}", "", txt)
                    cloze_txt = re.sub("\{..\}", "{{c1::", v)
                    cloze_txt = re.sub("\{phrase\}", "{{c1::", cloze_txt)
                    cloze_txt = re.sub("\{...\}", "}}", cloze_txt)
                    cloze_txt = re.sub("\{.phrase\}", "}}", cloze_txt)
                    translator = deepl.Translator(self.deepl_api_key)
                    result = translator.translate_text(txt, target_lang=target_lang_code)
                    translated_text = result.text
                    to_print=cloze_txt+'<br>'+translated_text
                    Cloze_html='<div class ="cloze_box">' + \
                    '<p>' + to_print + '</p>' + \
                    '</div>'
                    _add_to_insert_queue(insert_queue, Cloze_html, 0)


            for x in def_list:
                _add_to_insert_queue(insert_queue, x, DefField)

    if ImgField > -1:
        # extract img html tag and move to the ImgField
        html_text = '<br>'.join(list(note.values()))
        # Create a Parse Tree object using BeautifulSoup()
        soup = BeautifulSoup(html_text, 'html.parser')
        # Extract all <img> tags in the HTML document
        img_tags = soup.find_all('img')
        img_list=[]
        for img_tag in img_tags:
            img_list.append(str(img_tag))
        # Add artwork
        for e in valid_entries:
            if 'art' in e:
                artid = ''.join(json_extract_dict(obj=e, key='artid'))
                art_url = 'https://www.merriam-webster.com/assets/mw/static/art/dict/' + artid + '.gif'
                img_list.append(editor.urlToLink(art_url).strip())
                if len(re.findall(":", json_extract_dict(obj=e, key='capt')[0]))>0:
                    capt = json_extract_dict(obj=e, key='capt')[0].split(":")[1].strip()
                else:
                    capt = json_extract_dict(obj=e, key='capt')[0]
                img_list.append(re.sub(pattern=r"{[^}]*}", repl='', string=capt))

        for x in img_list:
            _add_to_insert_queue(insert_queue, x, ImgField)



    if JapField > -1:
        jap_list=[]
        response = requests.get('https://ejje.weblio.jp/content/' + urllib.parse.quote_plus(word))
        soup = BeautifulSoup(response.text, 'html.parser')
        if not soup.find(class_='content-explanation ej'):
            tooltip("No Japanese definition was found. Check the word!")
            return
        else:
            japanese = soup.find(class_='content-explanation ej').get_text().strip()
            Jap_html = '<div class ="jap_box" >' + \
                       '<span class ="box-title"> Japanese </span>' + \
                       '<p>' + japanese + '</p>' + \
                       '</div>'
            jap_list.append(Jap_html)
            for x in jap_list:
                _add_to_insert_queue(insert_queue, x, JapField)


    for queue_key in insert_queue.keys():
        if overwrite:
            note[fields[queue_key]] = insert_queue[queue_key]
        else:
            note[fields[queue_key]] += insert_queue[queue_key]
    if from_editor:
        # Insert each queue into the considered field
        for field_index in insert_queue.keys():
            insert_into_field(editor, insert_queue[field_index], field_index, overwrite=overwrite)

    if openweb:
        if not searchWord == '':
            webbrowser.open(
                "https://www.google.com/search?q= " + word + "+" + searchWord + "&safe=off&tbm=isch&tbs=isz:lt,islt:xga",
                0,
                False)
        else:
            webbrowser.open("https://www.google.com/search?q= " + word + "&safe=off&tbm=isch&tbs=isz:lt,islt:xga",
                            0, False)


def _make_def_vis_format(def_list, vis_list, FL, sn, dt, vis, syn, ant, BOX_FORMAT=True):
    dt = re.sub("\{bc\}", "", dt)
    if BOX_FORMAT:
        if len(vis) > 0:
            vis_list.append(vis[0])
            txt = re.sub("\{..\}", "<span class=\"text_highlight\">", vis[0])
            txt = re.sub("\{phrase\}", "<span class=\"text_highlight\">", txt)
            txt = re.sub("\{...\}", "</span>", txt)
            txt = re.sub("\{.phrase\}", "</span>", txt)
            Vis = re.sub("\{.....\}", "\"", txt)
            Vis_html = '<div class ="vis_box" >' + \
                       '<span class ="box-title"> Example </span>' + \
                       '<p>' + Vis + '</p>' + \
                       '</div>'
        else:
            Vis_html = ''
        dt_html = re.sub("{sx\|", ': <span class=\"text_highlight\">', dt)
        dt_html = re.sub("\|\|\d*}", "</span>", dt_html)

        if len(syn) > 0:
            Syn = ', '.join(syn)
            Syn_html = '<div class ="syn_box" >' + \
                       '<span class ="box-title"> Synonym </span>' + \
                       '<p>' + Syn + '</p>' + \
                       '</div>'
        else:
            Syn_html = ''
        if len(ant) > 0:
            Ant = ', '.join(ant)
            Ant_html = '<div class ="ant_box" >' + \
                       '<span class ="box-title"> Antonym </span>' + \
                       '<p>' + Ant + '</p>' + \
                       '</div>'
        else:
            Ant_html = ''

        def replace_words(text, pattern):
            replacement = r"\2"  # Replace with the second captured word
            result = re.sub(pattern, replacement, text)
            return result
        dt_html=replace_words(text=dt_html, pattern = r"{([\w\.-]+)\|([^{}|]+)\|([^{}|]+)\|}") # replace {dtx|WORD|WORD|}
        dt_html = replace_words(text=dt_html, pattern=r"{([\w\.-]+)\|([^{}|]+)\|([^{}|]+)}")  # replace {d_link|WORD|WORD}
        dt_html=replace_words(text=dt_html, pattern=r"{([\w\.-]+)\|([^|]+)\}") # replace {a_link|WORD}
        dt_html=re.sub("\{dx\}", ': <span class=\"text_highlight\">', dt_html)
        dt_html=re.sub("{/dx}", "</span>", dt_html)
        dt_html=re.sub("\{it\}", ': <span class=\"text_highlight\">', dt_html)
        dt_html=re.sub("{/it}", "</span>", dt_html)

        Def_html = '<div class ="def_box" >' + \
                   '<span class ="box-title">' + FL + ' ' + sn + '</span>' + \
                   '<p>' + dt_html + '</p>' + \
                   '</div>' + \
                   Vis_html + \
                   Syn_html + \
                   Ant_html

        def_list.append(Def_html)

    else:
        def_list.append(FL + ' ' + sn + '. ' + dt)
        if len(vis) > 0:
            vis_list.append(vis[0])
            def_list.append(
                '(Example) ' + re.sub(pattern=r"{[^}]*}", repl='', string=vis[0]))
        if len(syn) > 0:
            def_list.append('(Synonym) ' + ', '.join(syn))
        if len(ant) > 0:
            def_list.append('(Antonym) ' + ', '.join(ant))



def get_pokemon(editor, note, sourceField=0, overwrite=False,
                     openweb=False, searchWord='',
                     DefField=1,ImgField=2,JapField=1,
                     from_editor=False):

    fields = list(note.keys())
    if from_editor:
        config = mw.addonManager.getConfig(__name__)
        overwrite = config["Overwrite"]
        openweb = config["Open Web Browser"]
        searchWord = config["Additional Search Word"]
        fields.append('Off')
        sourceField = fields.index(config['Fields']['Source Field'])
        PronField = config['Fields']['Pronunciation Field']
        if PronField=='Off':
            PronField = -1
        else:
            PronField = fields.index(PronField)
        DefField = config['Fields']['Definition Field']
        if DefField=='Off':
            DefField = -1
        else:
            DefField = fields.index(DefField)
        JapField = config['Fields']['Japanese Field']
        if JapField == 'Off':
            JapField = -1
        else:
            JapField = fields.index(JapField)

        ImgField = config['Fields']['Image Field']
        if ImgField=='Off':
            ImgField = -1
        else:
            ImgField = fields.index(ImgField)

    insert_queue = {}

    word = _get_word_b(editor=editor, note=note, sourceField=sourceField)
    word = re.sub('Name', '', word)
    word = re.sub(':', '', word)
    # word = re.sub("\'", '', word) # Farfetch'd
    word = re.sub("\"", '', word).strip()
    poke_name = word
    ref_name = word.lower()
    ref_name = re.sub(". ", '-', ref_name)
    if ref_name == "":
        tooltip("Kotonoha: No text found in note fields.")
        return

    # change the quiz to cloze sentence
    cloze_note=note[fields[0]]
    repl = '{{c1::' + poke_name + '}}'
    cloze_note=cloze_note.replace(poke_name, repl)
    _add_to_insert_queue(insert_queue=insert_queue,
                         to_print=cloze_note,
                         field_index=0)

    new_note=[]
    # Name
    name_html = '<div class ="poke_box" >' + \
                '<span class ="box-title">' + 'Name' + '</span>' + \
                '<p>' + poke_name + '</p>' + \
                '</div>'
    new_note.append(name_html)

    tsv_path=os.path.join(os.path.dirname(os.path.realpath(__file__)),'pokemon_all_generation_2023May23.tsv')
    with open(tsv_path, 'r', newline='', encoding='utf-8') as file:
        reader = csv.reader(file, delimiter="\t")
        for line in reader:
            if line[1] == poke_name:
                row = line

    try:
        row
    except NameError:
        row = None

    if row is None:
        tooltip('The pokemon name was not found in the reference table. Check the Name')
        return
    # National No
    No_html = '<div class ="poke_box" >' + \
                '<span class ="box-title">' + 'National No' + '</span>' + \
                '<p>' + row[0] + '</p>' + \
                '</div>'
    new_note.append(No_html)
    # Type
    type_html = '<div class ="poke_box" >' + \
              '<span class ="box-title">' + 'Type' + '</span>' + \
              '<p>' + row[2] + '</p>' + \
              '</div>'
    new_note.append(type_html)
    # IPA
    IPA_html = '<div class ="poke_box" >' + \
                '<span class ="box-title">' + 'IPA' + '</span>' + \
                '<p>' + row[4] + '[sound:' + poke_name + '.mp3]</p>' + \
                '</div>'
    new_note.append(IPA_html)

    # Japanese
    jap_html = '<div class ="poke_box" >' + \
               '<span class ="box-title">' + 'Japanese Name' + '</span>' + \
               '<p>' + row[5] + '</p>' + \
               '</div>'




    source_note = note[fields[sourceField]]
    text = source_note.replace('\"', '')
    rows = text.split('<br>')
    for row in rows:
        if 'Possible moves' in row:
            sp=row.split(': ')
            moves_html = '<div class ="poke_box" >' + \
                       '<span class ="box-title">' + 'Possible moves' + '</span>' + \
                       '<p>' + sp[1] +'</p>' + \
                       '</div>'
            new_note.append(moves_html)

    ref_name=ref_name.replace("♀","-f")
    ref_name=ref_name.replace("♂","-m")
    response = requests.get('https://pokemondb.net/pokedex/' + urllib.parse.quote_plus(ref_name))
    soup = BeautifulSoup(response.text, 'html.parser')
    # insert name origin
    if not soup.find(class_='etymology'):
        tooltip("No name origin was found. Check the word!")
    else:
        name_origin = soup.find(class_='etymology').get_text().strip()
        txt = name_origin.split('\n')
        if len(txt) == 2:
            new_name_origin = '<b>' + txt[0] + '</b>: ' + txt[1]
        elif len(txt) == 4:
            new_name_origin = '<b>' + txt[0] + '</b>: ' + txt[1] + '<br>' + '<b>' + txt[2] + '</b>: ' + txt[3]
        elif len(txt) == 6:
            new_name_origin = '<b>' + txt[0] + '</b>: ' + txt[1] + '<br>' + \
                              '<b>' + txt[2] + '</b>: ' + txt[3] + '<br>' + \
                              '<b>' + txt[4] + '</b>: ' + txt[5]
        origin_html = '<br>' + '<div class ="poke_box" >' + \
                      '<span class ="box-title"> Name Origin </span>' + \
                      '<p>' + new_name_origin + '</p>' + \
                      '</div>'
        new_note.append(origin_html)

    for x in new_note:
        _add_to_insert_queue(insert_queue=insert_queue,
                             to_print=x,
                             field_index=DefField)
    # add Japanese
    _add_to_insert_queue(insert_queue=insert_queue,
                         to_print=jap_html,
                         field_index=JapField)

    # add image
    if not '<img' in note[fields[ImgField]]:
        img_word = ref_name.replace("\'","")
        if len(re.findall('mega ', img_word)) > 0:
            sp = img_word.split(' ')
            if len(sp) > 2:
                img_word = sp[1] + '-mega-' + sp[2]
            else:
                img_word = sp[1] + '-mega'
        poke_img_url = 'https://img.pokemondb.net/artwork/large/' + img_word + '.jpg'
        if is_valid_url(poke_img_url):
            poke_img = editor.urlToLink(poke_img_url).strip()
            _add_to_insert_queue(insert_queue=insert_queue,
                                 to_print=poke_img,
                                 field_index=ImgField)
        else:
            tooltip("The img URL is not valid.")



    for queue_key in insert_queue.keys():
        note[fields[queue_key]] = insert_queue[queue_key]

    if from_editor:
        # Insert each queue into the considered field
        for field_index in insert_queue.keys():
            insert_into_field(editor, insert_queue[field_index], field_index, overwrite=True)



def is_valid_url(url):
    try:
        response = requests.head(url)
        return response.status_code == requests.codes.ok
    except requests.exceptions.RequestException:
        return False


def _add_to_insert_queue(insert_queue, to_print, field_index):
    if field_index not in insert_queue.keys():
        insert_queue[field_index] = to_print
    else:
        insert_queue[field_index] += "<br>" + to_print


def insert_into_field(editor, text, field_id, overwrite=False):
    if len(editor.note.fields) <= field_id:
        tooltip("Kotonoha: Tried to insert '%s' into user-configured field number %d (0-indexed), but note type only "
                "has %d fields. Use a different note type with %d or more fields, or change the index in the "
                "Add-on configuration." % (text, field_id, len(editor.note.fields), field_id + 1), period=10000)
        return
    if overwrite:
        editor.note.fields[field_id] = text
    else:
        editor.note.fields[field_id] += text
    editor.loadNote()


# via https://stackoverflow.com/a/12982689
def clean_html(raw_html):
    return re.sub(re.compile('<.*?>'), '', raw_html).replace("&nbsp;", " ")


# extract a list from nested json
def extract_text(json_data, text):
    result_list = []
    if isinstance(json_data, dict):
        for k, v in json_data.items():
            result_list.extend(extract_text(v, text))
    elif isinstance(json_data, list):
        if text in json_data:
            result_list.append(json_data)
        for item in json_data:
            result_list.extend(extract_text(item, text))
    return result_list


# extract value from nested json
def json_extract_dict(obj, key):
    """Recursively fetch values from nested JSON."""
    arr = []

    def extract(obj, arr, key):
        """Recursively search for values of key in JSON tree."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == key:
                    arr.append({k:v})
                if isinstance(v, (dict, list)):
                    extract(v, arr, key)
        elif isinstance(obj, list):
            for item in obj:
                extract(item, arr, key)
        return arr

    values = extract(obj, arr, key)
    final_result = []
    for element in values:
        final_result.append(element[key])
    return final_result


FL_ABBREVIATION = {"verb": "v.", "noun": "n.", "adverb": "adv.", "adjective": "adj."}

def _abbreviate_fl(fl):
    if fl in FL_ABBREVIATION.keys():
        fl = FL_ABBREVIATION[fl]
    return fl