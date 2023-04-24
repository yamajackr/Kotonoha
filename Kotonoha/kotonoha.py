# Kotonoha Anki Add-on
# Kotonoha - Automatically add the pronunciation, definition etc. of the word in the editor
#
# https://github.com/yamamotoryo/Kotonoha                      Licensed under GPL v3

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

# Which dictionary to use for 1st button? Available options are COLLEGIATE, LEARNERS, ELEMENTARY and MEDICAL.
PRIMARY_DICT = "LEARNERS"

# Get your unique API key by signing up at http://www.dictionaryapi.com/
PRIMARY_API_KEY = "YOUR_KEY_HERE"

# Index of field to insert definitions into (use -1 to turn off)
DEFINITION_FIELD = 1

# Index of field to insert Japanese into (use -1 to turn off)
JAPANESE_FIELD = 1

# Ignore archaic/obsolete definitions?
IGNORE_ARCHAIC = True

# Open a browser tab with an image search for the same word?
OPEN_IMAGES_IN_BROWSER = True

# Additional word for search in web browser
ADDITIONAL_SEARCH_WORD = ""

# Index of field to insert pronunciations into (use -1 to turn off)
PRONUNCIATION_FIELD = 0

# Which dictionary to use for 2nd button? Available options are COLLEGIATE, LEARNERS, ELEMENTARY and MEDICAL.
SECONDARY_DICT = ""

# Get your unique API key by signing up at http://www.dictionaryapi.com/
SECONDARY_API_KEY = "YOUR_KEY_HERE"

# Which dictionary to use for 3rd button? Available options are COLLEGIATE, LEARNERS, ELEMENTARY and MEDICAL.
TERTIARY_DICT = ""

# Get your unique API key by signing up at http://www.dictionaryapi.com/
TERTIARY_API_KEY = "YOUR_KEY_HERE"

# Which dictionary to use for 3rd button? Available options are COLLEGIATE, LEARNERS, ELEMENTARY and MEDICAL.
QUATERNARY_DICT = ""

# Get your unique API key by signing up at http://www.dictionaryapi.com/
QUATERNARY_API_KEY = "YOUR_KEY_HERE"


# Which dictionary to use for thesaurus button? Available options are COLLEGIATE_THESAURUS, and INTERMEDIATE_THESAURUS.
THESAURUS_DICT = ""

# Get your unique API key by signing up at http://www.dictionaryapi.com/
THESAURUS_API_KEY = "YOUR_KEY_HERE"


PRIMARY_SHORTCUT = "ctrl+shift+f"

SECONDARY_SHORTCUT = "ctrl+shift+d"

TERTIARY_SHORTCUT = "ctrl+shift+s"

QUATERNARY_SHORTCUT = "ctrl+shift+a"

THESAURUS_SHORTCUT = "ctrl+shift+e"

JAPANESE_SHORTCUT = "ctrl+alt+w"

FL_ABBREVIATION = {"verb": "v.", "noun": "n.", "adverb": "adv.", "adjective": "adj."}


def get_definition(editor,
                   button='primary'):
    editor.saveNow(lambda: _get_definition(editor, button))


def get_definition_force_pronunciation(editor):
    get_definition(editor, force_pronounce=True)

def get_definition_secondary(editor):
    get_definition(editor, button='secondary')

def get_definition_tertiary(editor):
    get_definition(editor, button='tertiary')

def get_definition_quaternary(editor):
    get_definition(editor, button='quaternary')


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
    if DICT == "COLLEGIATE_THESAURUS":
        url = "https://www.dictionaryapi.com/api/v3/references/thesaurus/json/" + \
                    urllib.parse.quote(word) + "?key=" + API_KEY
        return (url)
    if DICT == "INTERMEDIATE_THESAURUS":
        url = "https://www.dictionaryapi.com/api/v3/references/ithesaurus/json/" + \
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
    elif button=='quaternary':
        DICT = QUATERNARY_DICT
        API_KEY = QUATERNARY_API_KEY
        URL = choose_url(word, DICT, API_KEY)
        if API_KEY == '':
            showInfo("QUATERNARY_API_KEY is blank. Get the API key")
            all_entries = []
        else:
            all_entries = get_entries_from_api_j(url=URL)
        valid_dic_name.append(DICT)
        return all_entries

    elif button=='thesaurus':
        DICT = THESAURUS_DICT
        API_KEY = THESAURUS_API_KEY
        URL = choose_url(word, DICT, API_KEY)
        if API_KEY == '':
            showInfo("THESAURUS_API_KEY is blank. Get the API key")
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
    if str.isascii(word):
        return word
    else:
        showInfo("Kotonoha has detected a word with non-ASCII characters, which it is unable to recognize. \
        By default, Kotonoha detects all the text in the front note. \
        When you select a part of the text, Kotonoha searches for its definition. \
        To avoid errors, ensure that the text you select does not contain any non-ASCII characters.")
        return ''

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

def _add_pronunciation(insert_queue, editor, word, valid_entries, PRONUNCIATION_FIELD):
    all_sounds = []
    for e in valid_entries:
        if json_extract_dict(obj=json_extract_dict(obj=e, key='hwi'), key='prs'):
            if 'fl' in e:
                FL = (_abbreviate_fl(e['fl']))
            else:
                FL = ''
            for prs in json_extract_dict(obj=json_extract_dict(obj=e, key='hwi'), key='prs'):
                if (not json_extract_dict(prs, 'ipa') and not json_extract_dict(prs, 'mw')) or\
                        not json_extract_dict(prs,'audio'):
                    continue
                else:
                    if json_extract_dict(prs, key='ipa'):
                        phoneme = json_extract_dict(prs, key='ipa')[0]
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
    return (all_sounds)
    final_pronounce_index = PRONUNCIATION_FIELD
    fields = mw.col.models.fieldNames(editor.note.model())
    for field in fields:
        if '🔊' in field:
            final_pronounce_index = fields.index(field)
            break
    to_print = '<br>' + '<br>'.join(all_sounds)
    _add_to_insert_queue(insert_queue, to_print, final_pronounce_index)


def _get_definition(editor,
                    button='primary'):
    validate_settings()
    word = _get_word(editor)
    if word == "":
        tooltip("Kotonoha: No text found in note fields.")
        return
    valid_dic_name=[]
    valid_entries = get_preferred_valid_entries_j(word, valid_dic_name=valid_dic_name,button=button)

    insert_queue = {}

    # Add Vocal Pronunciation
    if PRONUNCIATION_FIELD > -1:
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

        final_pronounce_index = PRONUNCIATION_FIELD
        fields = mw.col.models.fieldNames(editor.note.model())
        for field in fields:
            if '🔊' in field:
                final_pronounce_index = fields.index(field)
                break

        to_print = '<br>'+'<br>'.join(all_sounds)

        _add_to_insert_queue(insert_queue, to_print, final_pronounce_index)
    # Add Definition json

    if DEFINITION_FIELD > -1:
        check_response = all(isinstance(element, str) for element in valid_entries)
        if check_response:
            showInfo('Possible words are: '+','.join(valid_entries))
            def_list = []
        else:
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
            # add shortdef, example, thesaurus
            def_list = ['@'+''.join(valid_dic_name)]
            for FL in fl_list:
                g = grouped[FL]
                def_list.append(FL)
                for i in range(len(g)):
                    entry = g[i]
                    if len(json_extract_dict(obj=entry, key='shortdef')) > 0:
                        for j in range(len(json_extract_dict(obj=entry, key='shortdef')[0])):
                            shortdef = json_extract_dict(obj=entry, key='shortdef')[0][j]
                            sseq = json_extract_dict(obj=entry, key='sseq')[0]
                            if len(sseq)>j:
                                vis = json_extract_dict(obj=sseq[j], key='t')  # as list
                            else:
                                vis=[]
                            def_list.append(str(i + 1) + '-' + str(j + 1) + '. ' + shortdef)
                            if len(vis) > 0:
                                def_list.append('(Example) ' + re.sub(pattern=r"{[^}]*}", repl='', string=vis[0]))

    for x in def_list:
        _add_to_insert_queue(insert_queue=insert_queue,
                             to_print=x,
                             field_index=DEFINITION_FIELD)

    # Insert each queue into the considered field
    for field_index in insert_queue.keys():
        insert_into_field(editor, insert_queue[field_index], field_index)


    if OPEN_IMAGES_IN_BROWSER:
        if not ADDITIONAL_SEARCH_WORD=='':
            webbrowser.open("https://www.google.com/search?q= " + word + "+" + ADDITIONAL_SEARCH_WORD + "&safe=off&tbm=isch&tbs=isz:lt,islt:xga", 0,
                            False)
        else:
            webbrowser.open("https://www.google.com/search?q= " + word + "&safe=off&tbm=isch&tbs=isz:lt,islt:xga", 0, False)

    _focus_zero_field(editor)

def _get_thesaurus(editor):
    validate_settings()
    word = _get_word(editor)
    if word == "":
        tooltip("Kotonoha: No text found in note fields.")
        return
    valid_dic_name=[]
    button='thesaurus'
    valid_entries = get_preferred_valid_entries_j(word, valid_dic_name=valid_dic_name,button=button)
    valid_dic_name_sound = []
    valid_entries_sound = get_preferred_valid_entries_j(word, valid_dic_name=valid_dic_name_sound,
                                                        button='primary')

    insert_queue = {}

    # Add Vocal Pronunciation
    if PRONUNCIATION_FIELD > -1:
        # Parse all unique pronunciations, and convert them to URLs as per http://goo.gl/nL0vte
        all_sounds = []

        for e in valid_entries_sound:
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

        final_pronounce_index = PRONUNCIATION_FIELD
        fields = mw.col.models.fieldNames(editor.note.model())
        for field in fields:
            if '🔊' in field:
                final_pronounce_index = fields.index(field)
                break

        to_print = '<br>'+'<br>'.join(all_sounds)

        _add_to_insert_queue(insert_queue, to_print, final_pronounce_index)

    # Add Thesaurus json

    if DEFINITION_FIELD > -1:
        check_response = all(isinstance(element, str) for element in valid_entries)
        if check_response:
            showInfo('Possible words are: '+','.join(valid_entries))
            thes_list = []
        else:
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
            # add shortdef, example, thesaurus
            thes_list = ['@'+''.join(valid_dic_name)]
            for FL in fl_list:
                g = grouped[FL]
                thes_list.append(FL)
                for i in range(len(g)):
                    entry = g[i]
                    if len(json_extract_dict(obj=entry, key='shortdef')) > 0:
                        for j in range(len(json_extract_dict(obj=entry, key='shortdef')[0])):
                            shortdef = json_extract_dict(obj=entry, key='shortdef')[0][j]
                            sseq = json_extract_dict(obj=entry, key='sseq')[0]
                            if len(sseq)>0:
                                vis = json_extract_dict(obj=sseq[j], key='t')  # as list
                                syn_list = json_extract_dict(obj=json_extract_dict(obj=sseq[j], key='syn_list'),
                                                             key='wd')  # as list
                                ant_list = json_extract_dict(obj=json_extract_dict(obj=sseq[j], key='ant_list'),
                                                             key='wd')  # as list
                            else:
                                vis=[]
                                syn_list=[]
                                ant_list=[]
                            thes_list.append(str(i + 1) + '-' + str(j + 1) + '. ' + shortdef)
                            if len(vis) > 0:
                                thes_list.append('(Example) ' + re.sub(pattern=r"{[^}]*}", repl='', string=vis[0]))
                            if len(syn_list) > 0:
                                thes_list.append('(Synonym) ' + ', '.join(syn_list))
                            if len(ant_list) > 0:
                                thes_list.append('(Antonym) ' + ', '.join(ant_list))

    for x in thes_list:
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

def get_thesaurus(editor):
    editor.saveNow(lambda: _get_thesaurus(editor))


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
                                   tip="Kotonoha: %s dictionary (%s)" %
                                       (PRIMARY_DICT,"no shortcut" if PRIMARY_SHORTCUT == "" else PRIMARY_SHORTCUT),
                                   toggleable=False,
                                   label="",
                                   keys=PRIMARY_SHORTCUT,
                                   disables=False)
    secondary_button = editor.addButton(icon=os.path.join(os.path.dirname(__file__), "images", "leaf_pink.png"),
                                     cmd="D",
                                     func=get_definition_secondary,
                                     tip="Kotonoha: %s dictionary (%s)" %
                                         (SECONDARY_DICT,"no shortcut" if SECONDARY_SHORTCUT == "" else SECONDARY_SHORTCUT),
                                     toggleable=False,
                                     label="",
                                     keys=SECONDARY_SHORTCUT,
                                     disables=False)
    tertiary_button = editor.addButton(icon=os.path.join(os.path.dirname(__file__), "images", "leaf_violet.png"),
                                       cmd="S",
                                       func=get_definition_tertiary,
                                       tip="Kotonoha: %s dictionary (%s)" %
                                           (TERTIARY_DICT,"no shortcut" if TERTIARY_SHORTCUT == "" else TERTIARY_SHORTCUT),
                                       toggleable=False,
                                       label="",
                                       keys=TERTIARY_SHORTCUT,
                                       disables=False)
    quaternary_button = editor.addButton(icon=os.path.join(os.path.dirname(__file__), "images", "leaf_black.png"),
                                       cmd="Q",
                                       func=get_definition_quaternary,
                                       tip="Kotonoha: %s dictionary (%s)" %
                                           (QUATERNARY_DICT,"no shortcut" if QUATERNARY_SHORTCUT == "" else QUATERNARY_SHORTCUT),
                                       toggleable=False,
                                       label="",
                                       keys=QUATERNARY_SHORTCUT,
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
    thesaurus_button = editor.addButton(icon=os.path.join(os.path.dirname(__file__), "images", "leaf_emerald.png"),
                                       cmd="T",
                                       func=get_thesaurus,
                                       tip="Kotonoha: %s dictionary (%s)" %
                                           (THESAURUS_DICT,"no shortcut" if THESAURUS_SHORTCUT == "" else THESAURUS_SHORTCUT),
                                       toggleable=False,
                                       label="",
                                       keys=THESAURUS_SHORTCUT,
                                       disables=False)

    buttons.append(primary_button)
    if not SECONDARY_DICT == '':
        buttons.append(secondary_button)
    if not TERTIARY_DICT == '':
        buttons.append(tertiary_button)
    if not QUATERNARY_DICT == '':
        buttons.append(quaternary_button)
    if not THESAURUS_DICT == '':
        buttons.append(thesaurus_button)
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
        if 'DEFINITION_FIELD' in extra:
            DEFINITION_FIELD = extra['DEFINITION_FIELD']
        if 'JAPANESE_FIELD' in extra:
            JAPANESE_FIELD = extra['JAPANESE_FIELD']
        if 'IGNORE_ARCHAIC' in extra:
            IGNORE_ARCHAIC = extra['IGNORE_ARCHAIC']
        if 'OPEN_IMAGES_IN_BROWSER' in extra:
            OPEN_IMAGES_IN_BROWSER = extra['OPEN_IMAGES_IN_BROWSER']
        if 'ADDITIONAL_SEARCH_WORD' in extra:
            ADDITIONAL_SEARCH_WORD = extra['ADDITIONAL_SEARCH_WORD']
        if 'PRONUNCIATION_FIELD' in extra:
            PRONUNCIATION_FIELD = extra['PRONUNCIATION_FIELD']
        if 'SECONDARY_DICT' in extra:
            SECONDARY_DICT = extra['SECONDARY_DICT']
        if 'SECONDARY_API_KEY' in extra:
            SECONDARY_API_KEY = extra['SECONDARY_API_KEY']
        if 'TERTIARY_DICT' in extra:
            TERTIARY_DICT = extra['TERTIARY_DICT']
        if 'TERTIARY_API_KEY' in extra:
            TERTIARY_API_KEY = extra['TERTIARY_API_KEY']
        if 'QUATERNARY_DICT' in extra:
            QUATERNARY_DICT = extra['QUATERNARY_DICT']
        if 'QUATERNARY_API_KEY' in extra:
            QUATERNARY_API_KEY = extra['QUATERNARY_API_KEY']
        if 'THESAURUS_DICT' in extra:
            THESAURUS_DICT = extra['THESAURUS_DICT']
        if 'THESAURUS_API_KEY' in extra:
            THESAURUS_API_KEY = extra['THESAURUS_API_KEY']


    if '3 shortcuts' in config:
        shortcuts = config['3 shortcuts']
        if '1 PRIMARY_SHORTCUT' in shortcuts:
            PRIMARY_SHORTCUT = shortcuts['1 PRIMARY_SHORTCUT']
        if '2 SECONDARY_SHORTCUT' in shortcuts:
            SECONDARY_SHORTCUT = shortcuts['2 SECONDARY_SHORTCUT']
        if '3 TERTIARY_SHORTCUT' in shortcuts:
            TERTIARY_SHORTCUT = shortcuts['3 TERTIARY_SHORTCUT']
        if '4 QUATERNARY_SHORTCUT' in shortcuts:
            QUATERNARY_SHORTCUT = shortcuts['4 QUATERNARY_SHORTCUT']
        if '5 THESAURUS_SHORTCUT' in shortcuts:
            THESAURUS_SHORTCUT = shortcuts['5 THESAURUS_SHORTCUT']
        if '6 JAPANESE_SHORTCUT' in shortcuts:
            JAPANESE_SHORTCUT = shortcuts['6 JAPANESE_SHORTCUT']
