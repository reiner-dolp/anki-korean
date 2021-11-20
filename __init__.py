from aqt.qt import *
from aqt.utils import showInfo
from anki.hooks import addHook
from aqt import mw

# VENDOR DEPENDENCIES
import os
import sys

parent_dir = os.path.abspath(os.path.dirname(__file__))
vendor_dir = os.path.join(parent_dir, 'vendor2', 'Lib', 'site-packages')

sys.path.append(vendor_dir)
# ------

from lxml import etree
import requests

import re
import hashlib

NOTE_TYPE = ["korean", "korean from memrise"]
FIELD_HANGUL = "Hangul"
FIELD_TRANSLATION = "Translation"
FIELD_TRANSLATION_EN = "Translation (en)"
FIELD_PHONETIC_NOTATION = "Phonetic Notation"
FIELD_SOUND = "Sound"
FIELD_NOTE = "Note"
FIELD_IS_SENTENCE = "Is Sentence"
FIELD_HAS_DICT = "Has Dict"

FIELD_VALUE_FALSE = ""
FIELD_VALUE_TRUE = "YES"

TAG_SENTENCE = "sentence"

def get_url(hangul):
    return "https://krdict.korean.go.kr/eng/smallDic/searchResult?nation=eng&nationCode=6&ParaWordNo=&mainSearchWord="+hangul

def cleanup_text(xpathtext):
    as_string = [str(v) if not isinstance(v, str) else v for v in xpathtext]
    nowhitespace = [v.strip() for v in as_string]
    return ''.join(nowhitespace)

def cleanup_reading(xpathtext):
    return cleanup_text(cleanup_text(xpathtext).strip("[]"))

def extract_soundfile_url(xpathtext):
    as_string = str(xpathtext) if not isinstance(xpathtext, str) else xpathtext
    urls = re.findall("fnSoundPlay\('(.*?)'\)", as_string)
    return urls[0]

def scrape_korean_dict(hangul):

    # the encoding is incorrectly guessed without this explicit
    # specification as the HTML does not contain a charset meta tag
    utf8htmlparser = etree.HTMLParser(encoding="utf-8")
    page = requests.get(get_url(hangul))
    tree = etree.HTML(page.content, parser=utf8htmlparser)

    hangul = tree.xpath('//div[@class="search_result "][1]/dl[1]/dt[1]/a[1]/span[1]/text()')
    reading = tree.xpath('//div[@class="search_result "][1]/dl[1]/dt[1]/span[@class="search_sub"][1]/span[@class="search_sub"][1]/text()')
    translation = tree.xpath('//div[@class="search_result "][1]/dl[1]/dd[@class="manyLang6 "][1]/text()')
    sound = tree.xpath('//div[@class="search_result "][1]//a[@class="sound"][1]/@href')

    if len(sound):
        return cleanup_text(hangul), cleanup_reading(reading), cleanup_text(translation), extract_soundfile_url(sound[0])
    else:
        return cleanup_text(hangul), cleanup_reading(reading), cleanup_text(translation), None

def download_sound_file(media, word, url):
    file_contents = requests.get(url).content
    digest = hashlib.sha224(file_contents).hexdigest()[:12]
    filename = media.stripIllegal("korean-" + word.replace(" ", "_") + "-" + digest + ".mp3")
    media.writeData(str(filename), file_contents)
    return filename

def normalize_hangul(hangul_html):
    if hangul_html is None or hangul_html == "":
        return ""

    utf8htmlparser = etree.HTMLParser(encoding="utf-8")
    tree = etree.HTML(hangul_html, parser=utf8htmlparser)
    hangul_text_list = tree.xpath('//text()')
    hangul_text_str = " ".join(hangul_text_list)
    single_space = re.sub('\s+',' ', hangul_text_str)
    return single_space.strip().replace(" .", ".").replace(" ?", "?").replace(" !", "!")

def cmd_normalize_hangul(browser):
    selected_note_ids = browser.selectedNotes()

    progress = 0
    skipped_wrong_notetype = 0
    changed = 0

    mw.progress.start(max=len(selected_note_ids))

    for note_id in selected_note_ids:
        note = mw.col.getNote(note_id)

        noteType = note.model()['name'].lower()

        if noteType not in NOTE_TYPE:
            # different note
            skipped_wrong_notetype += 1
            continue

        prev = note[FIELD_HANGUL]
        after = normalize_hangul(prev)

        if prev != after:
            changed += 1
            note[FIELD_HANGUL] = after
            note.flush()

        progress += 1
        mw.progress.update(value=progress)

    mw.progress.finish()
    mw.reset()

    cnt = len(selected_note_ids)
    showInfo("Out of %d selected cards, %d were hangul cards. %d cards were changed." % (cnt, cnt - skipped_wrong_notetype, changed), parent=browser)

def is_sentence(word):
    return "." in word or "?" in word

def set_sentence_field(note):
    if is_sentence(note[FIELD_HANGUL]):
        note[FIELD_IS_SENTENCE] = FIELD_VALUE_TRUE
        if not note.hasTag(TAG_SENTENCE):
            note.addTag(TAG_SENTENCE)
    else:
        note[FIELD_IS_SENTENCE] = FIELD_VALUE_FALSE
        if note.hasTag(TAG_SENTENCE):
            note.delTag(TAG_SENTENCE)

def cmd_check_sentence(browser):
    selected_note_ids = browser.selectedNotes()

    progress = 0
    skipped_wrong_notetype = 0

    mw.progress.start(max=len(selected_note_ids))

    for note_id in selected_note_ids:
        note = mw.col.getNote(note_id)

        noteType = note.model()['name'].lower()

        if noteType not in NOTE_TYPE:
            # different note
            skipped_wrong_notetype += 1
            continue

        set_sentence_field(note)

        note.flush()

        progress += 1
        mw.progress.update(value=progress)

    mw.progress.finish()
    mw.reset()

def cmd_change_sound_selected(browser, mode):
    selected_note_ids = browser.selectedNotes()

    progress = 0
    skipped_wrong_notetype = 0
    skipped_no_dict_entry = 0
    no_sound = 0

    mw.progress.start(max=len(selected_note_ids))

    for note_id in selected_note_ids:
        note = mw.col.getNote(note_id)

        noteType = note.model()['name'].lower()

        if noteType not in NOTE_TYPE:
            # different note
            skipped_wrong_notetype += 1
            continue

        hangul, reading, translation, sound_url = scrape_korean_dict(note[FIELD_HANGUL])

        # showInfo("""%s,%s,%s,%s,%s""" % (note[FIELD_HANGUL], hangul, reading, translation, sound_url))

        if hangul != note[FIELD_HANGUL]:
            # word not found in dictionary
            skipped_no_dict_entry += 1
            continue

        if sound_url is None:
            no_sound += 1
        else:
            sound = "[sound:"+download_sound_file(mw.col.media, translation, sound_url)+"]"

            if mode == "append":
                note[FIELD_SOUND] += sound
            elif mode == "prepend":
                note[FIELD_SOUND] = sound + note[FIELD_SOUND]
            else:
                note[FIELD_SOUND] = sound

        note.flush()

        progress += 1
        mw.progress.update(value=progress)

    mw.progress.finish()
    mw.reset()

    showInfo("""
Out of %d selected cards:
- %d were skipped because they were not korean cards
- %d were skipped because they had no entry in the dictionary
- %d were skipped because the dictionary entry did not have a sound file
            """ % (len(selected_note_ids), skipped_wrong_notetype, skipped_no_dict_entry, no_sound), parent=browser)

def cmd_autofill_selected(browser):
    selected_note_ids = browser.selectedNotes()
    # selected_notes = [
            # browser.mw.col.getNote(note_id)
            # for note_id in selected_node_ids
        # ]
    progress = 0
    skipped_wrong_notetype = 0
    skipped_sentence = 0
    skipped_no_dict_entry = 0
    skipped_translation_field = 0
    skipped_phonetic_field = 0
    skipped_sound_field = 0
    no_sound = 0

    mw.progress.start(max=len(selected_note_ids))

    for note_id in selected_note_ids:
        note = mw.col.getNote(note_id)

        noteType = note.model()['name'].lower()

        if noteType not in NOTE_TYPE:
            # different note
            skipped_wrong_notetype += 1
            continue

        set_sentence_field(note)

        if is_sentence(note[FIELD_HANGUL]):
            skipped_sentence += 1
            continue

        hangul, reading, translation, sound_url = scrape_korean_dict(note[FIELD_HANGUL])

        if hangul != note[FIELD_HANGUL]:
            # word not found in dictionary
            note[FIELD_HAS_DICT] = FIELD_VALUE_FALSE
            skipped_no_dict_entry += 1
            note.flush()
            continue
        else:
            note[FIELD_HAS_DICT] = FIELD_VALUE_TRUE

        if note[FIELD_TRANSLATION_EN]:
            # already contains data, skip
            skipped_translation_field += 1
        else:
            note[FIELD_TRANSLATION_EN] = translation

        if note[FIELD_PHONETIC_NOTATION]:
            # already contains data, skip
            skipped_phonetic_field += 1
        else:
            note[FIELD_PHONETIC_NOTATION] = reading


        if note[FIELD_SOUND]:
            # already contains data, skip
            skipped_sound_field += 1
        elif sound_url is None:
            no_sound += 1
        else:
            note[FIELD_SOUND] = "[sound:"+download_sound_file(mw.col.media, translation, sound_url)+"]"

        note.flush()

        progress += 1
        mw.progress.update(value=progress)

    mw.progress.finish()
    mw.reset()

    showInfo("""
Out of %d selected cards:
- %d were skipped because they were not korean cards
- %d were skipped because they were sentences
- %d were skipped because they had no entry in the dictionary
- %d non-empty translation fields were skipped
- %d non-empty phonetic fields were skipped
- %d non-empty sound fields were skipped
- %d cards did not have a sound file in the dictionary
            """ % (len(selected_note_ids), skipped_wrong_notetype, skipped_sentence, skipped_no_dict_entry, skipped_translation_field, skipped_phonetic_field, skipped_sound_field, no_sound), parent=browser)

def gui_browser_menus():
    """
    Gives user access to mass generator, MP3 stripper, and the hook that
    disables and enables it upon selection of items.
    """


    def on_setup_menus(browser):
        """Create a menu and add browser actions to it."""

        menu = QMenu("Reiner's Korean", browser.form.menubar)
        browser.form.menubar.addMenu(menu)
        browser.form.menuKorean = menu

        a = QAction("Auto-fill empty fields in selection", browser)
        a.triggered.connect(lambda: cmd_autofill_selected(browser))
        # menu.addSeparator()
        menu.addAction(a)

        menu.addSeparator()

        replace = QAction("Replace sound in selection", browser)
        replace.triggered.connect(lambda: cmd_change_sound_selected(browser, "replace"))
        menu.addAction(replace)

        prepend = QAction("Prepend sound to selection", browser)
        prepend.triggered.connect(lambda: cmd_change_sound_selected(browser, "prepend"))
        menu.addAction(prepend)

        append = QAction("Append sound to selection", browser)
        append.triggered.connect(lambda: cmd_change_sound_selected(browser, "append"))
        menu.addAction(append)

        menu.addSeparator()

        checkSentence = QAction("Check if card is sentence", browser)
        checkSentence.triggered.connect(lambda: cmd_check_sentence(browser))
        menu.addAction(checkSentence)

        menu.addSeparator()

        normalize = QAction("Clean up hangul", browser)
        normalize.triggered.connect(lambda: cmd_normalize_hangul(browser))
        menu.addAction(normalize)

    addHook(
        'browser.setupMenus',
        on_setup_menus,
    )

gui_browser_menus()
# print(scrape_korean_dict("증상"))
