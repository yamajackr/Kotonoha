# Kotonoha Anki Add-on
# Kotonoha - Automatically add the pronunciation, definition etc. of the word in the editor
#
# Copyright (c) 2014 - 2019 Robert Sanek    robertsanek.com    rsanek@gmail.com
# https://github.com/z1lc/AutoDefine                      Licensed under GPL v2

import os
from collections import namedtuple

import platform
import re
import traceback
import urllib.error
import urllib.parse
import urllib.request
from bs4 import BeautifulSoup
from anki import version
from anki.hooks import addHook
from aqt import mw
from aqt.utils import showInfo, tooltip
from http.client import RemoteDisconnected
from urllib.error import URLError
from xml.etree import ElementTree as ET

from .libs import webbrowser

import requests
# --------------------------------- SETTINGS ---------------------------------

# Get your unique API key by signing up at http://www.dictionaryapi.com/
PRIMARY_API_KEY = "YOUR_KEY_HERE"

# Index of field to insert definitions into (use -1 to turn off)
DEFINITION_FIELD = 1

# Index of field to insert Japanese into (use -1 to turn off)
JAPANESE_FIELD = 1

# Ignore archaic/obsolete definitions?
IGNORE_ARCHAIC = True

# Get your unique API key by signing up at http://www.dictionaryapi.com/
SECONDARY_API_KEY = "YOUR_KEY_HERE"

# Get your unique API key by signing up at http://www.dictionaryapi.com/
TERTIARY_API_KEY = "YOUR_KEY_HERE"

# Open a browser tab with an image search for the same word?
OPEN_IMAGES_IN_BROWSER = False

# Which dictionary to use for 1st button? Available options are COLLEGIATE, LEARNERS, ELEMENTARY and MEDICAL.
PRIMARY_DICT = "LEARNERS"

# Which dictionary to use for 1st button? Available options are COLLEGIATE, LEARNERS, ELEMENTARY and MEDICAL.
SECONDARY_DICT = ""

# Which dictionary to use for 1st button? Available options are COLLEGIATE, LEARNERS, ELEMENTARY and MEDICAL.
TERTIARY_DICT = ""

# Index of field to insert pronunciations into (use -1 to turn off)
PRONUNCIATION_FIELD = 0

# Index of field to insert phonetic transcription into (use -1 to turn off)
PHONETIC_TRANSCRIPTION_FIELD = -1

# Index of field to insert pronunciations into (use -1 to turn off)
DEDICATED_INDIVIDUAL_BUTTONS = False

PRIMARY_SHORTCUT = "ctrl+alt+f"

SECONDARY_SHORTCUT = "ctrl+alt+s"

TERTIARY_SHORTCUT = "ctrl+alt+t"

JAPANESE_SHORTCUT = "ctrl+alt+j"

FL_ABBREVIATION = {"verb": "v.", "noun": "n.", "adverb": "adv.", "adjective": "adj."}


def get_definition(editor,
                   force_pronounce=False,
                   force_definition=False,
                   force_phonetic_transcription=False,
                   button='primary'):
    editor.saveNow(lambda: _get_definition(editor, force_pronounce, force_definition,
                                           force_phonetic_transcription, button))


def get_definition_force_pronunciation(editor):
    get_definition(editor, force_pronounce=True)



def get_definition_secondary(editor):
    get_definition(editor, button='secondary')

def get_definition_tertiary(editor):
    get_definition(editor, button='tertiary')

def get_definition_force_definition(editor):
    get_definition(editor, force_definition=True)

def get_definition_medical(editor):
    get_definition(editor, force_definition=True)


def get_definition_force_phonetic_transcription(editor):
    get_definition(editor, force_phonetic_transcription=True)


def validate_settings():
    # ideally, we wouldn't have to force people to individually register, but the API limit is just 1000 calls/day.

    if PRIMARY_DICT not in ["COLLEGIATE", "MEDICAL", "LEARNERS", "ELEMENTARY"]:
        message = "Setting PRIMARY_DICTIONARY must be set to either COLLEGIATE, MEDICAL, LEARNERS, or ELEMENTARY. Current setting: '%s'" \
                  % PRIMARY_DICT
        showInfo(message)
        return

    if PRIMARY_API_KEY == "YOUR_KEY_HERE":
        message = "Kotonoha requires Merriam-Webster's Dictionary with Audio API. " \
                  "To get functionality working:\n" \
                  "1. Go to www.dictionaryapi.com and sign up for an account, requesting access to " \
                  "the dictionary. \n" \
                  "2. In Anki, go to Tools > Add-Ons. Select Kotonoha, click \"Config\" on the right-hand side " \
                  "and replace YOUR_KEY_HERE with your unique API key.\n"
        showInfo(message)
        webbrowser.open("https://www.dictionaryapi.com/", 0, False)
        return


ValidAndPotentialEntries = namedtuple('Entries', ['valid', 'potential'])


def _focus_zero_field(editor):
    # no idea why, but sometimes web seems to be unavailable
    if editor.web:
        editor.web.eval("focusField(%d);" % 0)

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
def get_preferred_valid_entries_j(word, valid_dic_name, button):
    if button=='primary':
        DICT = PRIMARY_DICT
        API_KEY = PRIMARY_API_KEY
        URL = choose_url(word, DICT, API_KEY)
        if API_KEY == '':
            showInfo("PRIMARY_API_KEY is blank. Get the API key")
            all_entries = []
        else:
            all_entries = get_entries_from_api_j(url=URL)
        valid_dic_name.append(DICT)
        return all_entries

    elif button=='secondary':
        DICT = SECONDARY_DICT
        API_KEY = SECONDARY_API_KEY
        URL = choose_url(word, DICT, API_KEY)
        if API_KEY == '':
            showInfo("SECONDARY_API_KEY is blank. Get the API key")
            all_entries = []
        else:
            all_entries = get_entries_from_api_j(url=URL)
        valid_dic_name.append(DICT)
        return all_entries

    elif button=='tertiary':
        DICT = TERTIARY_DICT
        API_KEY = TERTIARY_API_KEY
        URL = choose_url(word, DICT, API_KEY)
        if API_KEY == '':
            showInfo("TERTIARY_API_KEY is blank. Get the API key")
            all_entries = []
        else:
            all_entries = get_entries_from_api_j(url=URL)
        valid_dic_name.append(DICT)
        return all_entries

def filter_entries_lower_and_potential(word, all_entries):
    valid_entries = extract_valid_entries(word, all_entries)
    maybe_entries = set()
    if not valid_entries:
        valid_entries = extract_valid_entries(word, all_entries, True)
        if not valid_entries:
            for entry in all_entries:
                maybe_entries.add(re.sub(r'\[\d+\]$', "", entry.attrib["id"]))
    return ValidAndPotentialEntries(valid_entries, maybe_entries)


def extract_valid_entries(word, all_entries, lower=False):
    valid_entries = []
    for entry in all_entries:
        if lower:
            if entry.attrib["id"][:len(word) + 1].lower() == word.lower() + "[" \
                    or entry.attrib["id"].lower() == word.lower():
                valid_entries.append(entry)
        else:
            if entry.attrib["id"][:len(word) + 1] == word + "[" \
                    or entry.attrib["id"] == word:
                valid_entries.append(entry)
    return valid_entries

def get_entries_from_api_j(url):
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
            json_data = response.json()
            return json_data
    except URLError:
        return []


def _get_word(editor):
    word = ""
    maybe_web = editor.web
    if maybe_web:
        word = maybe_web.selectedText()

    if word is None or word == "":
        maybe_note = editor.note
        if maybe_note:
            word = maybe_note.fields[0]

    word = clean_html(word).strip()
    return word

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

def _abbreviate_fl(fl):
    if fl in FL_ABBREVIATION.keys():
        fl = FL_ABBREVIATION[fl]
    return fl

def _get_definition(editor,
                    force_pronounce=False,
                    force_definition=False,
                    force_phonetic_transcription=False,
                    button='primary'):
    validate_settings()
    word = _get_word(editor)
    if word == "":
        tooltip("Kotonoha: No text found in note fields.")
        return
    valid_dic_name=[]
    valid_entries_j = get_preferred_valid_entries_j(word, valid_dic_name=valid_dic_name,button=button)

    insert_queue = {}

    # Add Vocal Pronunciation
    if (not force_definition and not force_phonetic_transcription and PRONUNCIATION_FIELD > -1) or force_pronounce:
        # Parse all unique pronunciations, and convert them to URLs as per http://goo.gl/nL0vte
        all_sounds = []

        for e in valid_entries_j:
            if json_extract_dict(obj=json_extract_dict(obj=e, key='hwi'), key='prs'):
                FL = (_abbreviate_fl(e['fl']))
                for prs in json_extract_dict(obj=json_extract_dict(obj=e, key='hwi'), key='prs'):
                    if json_extract_dict(prs, key='ipa'):
                        phoneme=json_extract_dict(prs, key='ipa')[0]
                    else:
                        phoneme = json_extract_dict(prs, key='mw')[0]
                    audio = json_extract_dict(prs, key='audio')[0]
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

        final_pronounce_index = PRONUNCIATION_FIELD
        fields = mw.col.models.fieldNames(editor.note.model())
        for field in fields:
            if '🔊' in field:
                final_pronounce_index = fields.index(field)
                break

        to_print = '<br>'+'<br>'.join(all_sounds)

        _add_to_insert_queue(insert_queue, to_print, final_pronounce_index)


    # Add Definition json
    definition_j_list = []
    if (not force_pronounce and not force_phonetic_transcription and DEFINITION_FIELD > -1) or force_definition:
        check_response = all(isinstance(element, str) for element in valid_entries_j)
        if check_response:
            showInfo('Possible words are: '+valid_entries_j)
            final_list = []
        else:
            for entry in valid_entries_j:
                definition = entry['shortdef']
                definition_j_list.append(definition)

            # add functional label and definition
            fl_list = []
            definition_j_list = []
            for entry in valid_entries_j:
                if 'fl' not in entry:
                    continue
                fl = entry['fl']
                fl_list.append(fl)

            for entry in valid_entries_j:
                if 'fl' not in entry:
                    continue
                fl = entry['fl']
                definition_j_list.append(fl)
                # add short definition
                if not entry['shortdef']:
                    continue
                shortdef = entry['shortdef']
                definition_j_list.append(shortdef)
                # add example sentence
                if not json_extract_dict(entry, 't'):
                    continue
                vis = json_extract_dict(entry, 't')
                definition_j_list.append(re.sub(pattern=r"{[^}]*}", repl='', string=vis[0]))
            # unique fl
            fl_list = list(set(fl_list))
            # group by fl
            grouped = {}
            for x in fl_list:
                grouped[x] = []
            for i in range(len(definition_j_list)):
                if definition_j_list[i] in fl_list:
                    category = definition_j_list[i]
                    grouped[category].append(definition_j_list[i + 1])
                    if i + 2 >= len(definition_j_list):
                        break
                    else:
                        if definition_j_list[i + 2] not in fl_list:
                            grouped[category].append(definition_j_list[i + 2])

            final_list = [''.join(valid_dic_name)]
            for key in grouped.keys():
                final_list.append(key)
                for i in range(len(grouped[key])):
                    if isinstance(grouped[key][i], list):
                        for j in range(len(grouped[key][i])):
                            final_list.append(str(i + 1) + '-' + str(j + 1) + '. ' + grouped[key][i][j])
                    else:
                        final_list.append('e.g. ' + grouped[key][i])

    for x in final_list:
        _add_to_insert_queue(insert_queue=insert_queue,
                             to_print=x,
                             field_index=DEFINITION_FIELD)

    # Insert each queue into the considered field
    for field_index in insert_queue.keys():
        insert_into_field(editor, insert_queue[field_index], field_index)

    if OPEN_IMAGES_IN_BROWSER:
        webbrowser.open("https://www.google.com/search?q= " + word + "&safe=off&tbm=isch&tbs=isz:lt,islt:xga", 0, False)

    _focus_zero_field(editor)

def _search_japanese(editor,japanese_field_index=JAPANESE_FIELD):
    validate_settings()
    word = _get_word(editor)
    if word == "":
        tooltip("Kotonoha: No text found in note fields.")
        return
    response = requests.get('https://ejje.weblio.jp/content/'+urllib.parse.quote_plus(word))
    soup = BeautifulSoup(response.text, 'html.parser')
    if not soup.find(class_='content-explanation ej'):
        tooltip("No Japanese definition was found. Check the word!")
        return
    else:
        japanese='<br>'+soup.find(class_='content-explanation ej').get_text().strip()
        insert_into_field(editor, japanese, japanese_field_index)

def search_japanese(editor, japanese_field_index=JAPANESE_FIELD):
    editor.saveNow(lambda: _search_japanese(editor, japanese_field_index))

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


def setup_buttons(buttons, editor):
    primary_button = editor.addButton(icon=os.path.join(os.path.dirname(__file__), "images", "leaf_green.png"),
                                   cmd="AD",
                                   func=get_definition,
                                   tip="Kotonoha: 1st dictionary (%s)" %
                                       ("no shortcut" if PRIMARY_SHORTCUT == "" else PRIMARY_SHORTCUT),
                                   toggleable=False,
                                   label="",
                                   keys=PRIMARY_SHORTCUT,
                                   disables=False)
    secondary_button = editor.addButton(icon=os.path.join(os.path.dirname(__file__), "images", "leaf_black.png"),
                                     cmd="D",
                                     func=get_definition_secondary,
                                     tip="Kotonoha: 2nd dictionary (%s)" %
                                         ("no shortcut" if SECONDARY_SHORTCUT == "" else SECONDARY_SHORTCUT),
                                     toggleable=False,
                                     label="",
                                     keys=SECONDARY_SHORTCUT,
                                     disables=False)
    tertiary_button = editor.addButton(icon=os.path.join(os.path.dirname(__file__), "images", "leaf_violet.png"),
                                       cmd="ə",
                                       func=get_definition_tertiary,
                                       tip="Kotonoha: 3rd dictionary (%s)" %
                                           ("no shortcut" if TERTIARY_SHORTCUT == "" else TERTIARY_SHORTCUT),
                                       toggleable=False,
                                       label="",
                                       keys=TERTIARY_SHORTCUT,
                                       disables=False)
    japanese_button = editor.addButton(icon=os.path.join(os.path.dirname(__file__), "images", "leaf_red.png"),
                                        cmd="P",
                                        func=search_japanese,
                                        tip="Kotonoha: Japanese meaning from Weblio (%s)" %
                                            ("no shortcut" if JAPANESE_SHORTCUT == "" else JAPANESE_SHORTCUT),
                                        toggleable=False,
                                        label="",
                                        keys=JAPANESE_SHORTCUT,
                                        disables=False)

    buttons.append(primary_button)
    if not SECONDARY_DICT == '':
        buttons.append(secondary_button)
    if not TERTIARY_DICT == '':
        buttons.append(tertiary_button)
    buttons.append(japanese_button)
    return buttons


addHook("setupEditorButtons", setup_buttons)

if getattr(mw.addonManager, "getConfig", None):
    config = mw.addonManager.getConfig(__name__)

    if '1 required' in config and all(x in config['1 required'] for x in ['PRIMARY_DICT', 'PRIMARY_API_KEY']):
        PRIMARY_DICT = config['1 required']['PRIMARY_DICT']
        PRIMARY_API_KEY = config['1 required']['PRIMARY_API_KEY']
    else:
        showInfo("Kotonoha: The schema of the configuration has changed in a backwards-incompatible way.\n"
                 "Please remove and re-download the Kotonoha Add-on.")

    if '2 extra' in config:
        extra = config['2 extra']
        if 'DEDICATED_INDIVIDUAL_BUTTONS' in extra:
            DEDICATED_INDIVIDUAL_BUTTONS = extra['DEDICATED_INDIVIDUAL_BUTTONS']
        if 'DEFINITION_FIELD' in extra:
            DEFINITION_FIELD = extra['DEFINITION_FIELD']
        if 'JAPANESE_FIELD' in extra:
            JAPANESE_FIELD = extra['JAPANESE_FIELD']
        if 'IGNORE_ARCHAIC' in extra:
            IGNORE_ARCHAIC = extra['IGNORE_ARCHAIC']
        if 'MERRIAM_WEBSTER_MEDICAL_API_KEY' in extra:
            MERRIAM_WEBSTER_MEDICAL_API_KEY = extra['MERRIAM_WEBSTER_MEDICAL_API_KEY']
        if 'MERRIAM_WEBSTER_LEARNERS_API_KEY' in extra:
            MERRIAM_WEBSTER_LEARNERS_API_KEY = extra['MERRIAM_WEBSTER_LEARNERS_API_KEY']
        if 'MERRIAM_WEBSTER_ELEMENTARY_API_KEY' in extra:
            MERRIAM_WEBSTER_ELEMENTARY_API_KEY = extra['MERRIAM_WEBSTER_ELEMENTARY_API_KEY']
        if 'OPEN_IMAGES_IN_BROWSER' in extra:
            OPEN_IMAGES_IN_BROWSER = extra['OPEN_IMAGES_IN_BROWSER']
        if 'SECONDARY_DICT' in extra:
            SECONDARY_DICT = extra['SECONDARY_DICT']
        if 'SECONDARY_API_KEY' in extra:
            SECONDARY_API_KEY = extra['SECONDARY_API_KEY']
        if 'TERTIARY_DICT' in extra:
            TERTIARY_DICT = extra['TERTIARY_DICT']
        if 'TERTIARY_API_KEY' in extra:
            TERTIARY_API_KEY = extra['TERTIARY_API_KEY']
        if 'PRONUNCIATION_FIELD' in extra:
            PRONUNCIATION_FIELD = extra['PRONUNCIATION_FIELD']
        if 'PHONETIC_TRANSCRIPTION_FIELD' in extra:
            PHONETIC_TRANSCRIPTION_FIELD = extra['PHONETIC_TRANSCRIPTION_FIELD']

    if '3 shortcuts' in config:
        shortcuts = config['3 shortcuts']
        if '1 PRIMARY_SHORTCUT' in shortcuts:
            PRIMARY_SHORTCUT = shortcuts['1 PRIMARY_SHORTCUT']
        if '2 SECONDARY_SHORTCUT' in shortcuts:
            SECONDARY_SHORTCUT = shortcuts['2 SECONDARY_SHORTCUT']
        if '3 JAPANESE_SHORTCUT' in shortcuts:
            JAPANESE_SHORTCUT = shortcuts['3 JAPANESE_SHORTCUT']
        if '4 TERTIARY_SHORTCUT' in shortcuts:
            TERTIARY_SHORTCUT = shortcuts['4 TERTIARY_SHORTCUT']
