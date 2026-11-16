#!/usr/bin/env python3
"""Builds the unsigned "Crate Add Songs" shortcut as a property list.

Apple only imports signed shortcuts, so sign the output on a Mac:
    shortcuts sign --mode anyone --input crate-add-songs-unsigned.shortcut --output "Crate Add Songs.shortcut"
The imported shortcut takes its name from the signed file's name.

It mirrors the steps in site/shortcut-setup.html: read Crate's JSON, a flat list of songs (index, playlist,
title, artist, album, and "create" on the first song of a playlist that must be made), and for each song create
its playlist if asked, find it with Find Music and add it, then output "v<VERSION> missing:<indexes>" for songs
not found. Crate reads the version and asks people to reinstall when theirs is older than SHORTCUT_VERSION in
site/index.html, so bump both together (and the step-15 text in site/shortcut-setup.html and Crate's Help) whenever
the shortcut changes in a way Crate depends on.
"""
import plistlib
import sys
import uuid

VERSION = 4

def new_id():
    return str(uuid.uuid4()).upper()

def output_of(action_uuid, name):
    """A reference to an earlier action's result (a "magic variable")."""
    return {"Value": {"Type": "ActionOutput", "OutputUUID": action_uuid, "OutputName": name},
            "WFSerializationType": "WFTextTokenAttachment"}

def named(var):
    return {"Value": {"Type": "Variable", "VariableName": var}, "WFSerializationType": "WFTextTokenAttachment"}

SHORTCUT_INPUT = {"Value": {"Type": "ExtensionInput"}, "WFSerializationType": "WFTextTokenAttachment"}

def text(before, ref=None, after=""):
    """A text field, optionally with one variable inserted after `before`."""
    if ref is None:
        return {"Value": {"string": before + after, "attachmentsByRange": {}}, "WFSerializationType": "WFTextTokenString"}
    return {"Value": {"string": before + "￼" + after,
                      "attachmentsByRange": {"{%d, 1}" % len(before): ref["Value"]}},
            "WFSerializationType": "WFTextTokenString"}

def text_parts(*parts):
    """A text field mixing literal strings and variables, e.g. text_parts(ref1, "|", ref2)."""
    string, attachments = "", {}
    for part in parts:
        if isinstance(part, str):
            string += part
        else:
            attachments["{%d, 1}" % len(string)] = part["Value"]
            string += "￼"
    return {"Value": {"string": string, "attachmentsByRange": attachments}, "WFSerializationType": "WFTextTokenString"}

actions = []
def add(identifier, **params):
    actions.append({"WFWorkflowActionIdentifier": identifier, "WFWorkflowActionParameters": params})

def get_value(key, source):
    u = new_id()
    add("is.workflow.actions.getvalueforkey", UUID=u, WFGetDictionaryValueType="Value",
        WFDictionaryKey=text(key), WFInput=source)
    return output_of(u, "Dictionary Value")

def set_variable(name, value):
    add("is.workflow.actions.setvariable", WFVariableName=name, WFInput=value)

def if_start(group, subject, condition, compare_to=None):
    # Dictionary values are only tested for presence: Shortcuts won't offer "is" for an untyped dictionary value,
    # so a text comparison imports with its text blank. Crate omits "create" unless the playlist must be made.
    # "is" is used only on the output of Change Case, which is plain text.
    extra = {"WFConditionalActionString": compare_to} if compare_to else {}
    add("is.workflow.actions.conditional", GroupingIdentifier=group, WFControlFlowMode=0, WFCondition=condition,
        WFInput={"Type": "Variable", "Variable": subject}, **extra)

def if_otherwise(group):
    add("is.workflow.actions.conditional", GroupingIdentifier=group, WFControlFlowMode=1)

def if_end(group):
    add("is.workflow.actions.conditional", GroupingIdentifier=group, WFControlFlowMode=2, UUID=new_id())

IS, HAS_ANY_VALUE, HAS_NO_VALUE = 4, 100, 101  # Shortcuts' condition codes

def lowercase(value):
    u = new_id()
    add("is.workflow.actions.text.changecase", UUID=u, WFCaseType="lowercase", text=value)
    return output_of(u, "Updated Text")

def detail(prop, source):
    u = new_id()
    add("is.workflow.actions.properties.music", UUID=u, WFContentItemPropertyName=prop, WFInput=source)
    return output_of(u, prop)

# Part 1: read what Crate sends
dict_id = new_id()
add("is.workflow.actions.detect.dictionary", UUID=dict_id, WFInput=SHORTCUT_INPUT)
dictionary = output_of(dict_id, "Dictionary")
# Stop before adding anything if Crate needs a newer shortcut: Crate sends "need_v2" … "need_vN" for the version
# N it needs, so this copy is too old exactly when "need_v<VERSION+1>" is present.
too_old = new_id()
if_start(too_old, get_value(f"need_v{VERSION + 1}", dictionary), HAS_ANY_VALUE)
stop_id = new_id()
add("is.workflow.actions.gettext", UUID=stop_id, WFTextActionText=text(f"v{VERSION} outdated"))
add("is.workflow.actions.output", WFOutput=text("", output_of(stop_id, "Text")), WFNoOutputSurfaceBehavior="Do Nothing")
if_otherwise(too_old)
if_end(too_old)
songs = get_value("songs", dictionary)

# Part 2: for each song, make its playlist if asked, then find the song and add it
loop = new_id()
add("is.workflow.actions.repeat.each", GroupingIdentifier=loop, WFControlFlowMode=0, WFInput=songs)
item = named("Repeat Item")
set_variable("Playlist Name", get_value("playlist", item))
create = get_value("create", item)
g = new_id()
if_start(g, create, HAS_ANY_VALUE)
add("is.workflow.actions.createplaylist", UUID=new_id(), WFPlaylistName=text("", named("Playlist Name")))
# A playlist created moments ago can't yet be found by name, so Add to Playlist would silently add nowhere.
add("is.workflow.actions.delay", WFDelayTime=3)
if_otherwise(g)
if_end(g)
set_variable("Title", get_value("title", item))
set_variable("Artist", get_value("artist", item))
set_variable("Album", get_value("album", item))

def music_filter(prop, var):
    return {"Operator": IS, "Property": prop, "Removable": True,
            "Values": {"String": text("", named(var)), "Unit": 4}}
def find_music(filters, limit=None):
    u = new_id()
    add("is.workflow.actions.filter.music", UUID=u,
        WFContentItemFilter={"Value": {"WFActionParameterFilterPrefix": 1, "WFContentPredicateBoundedDate": False,
                                       "WFActionParameterFilterTemplates": filters},
                             "WFSerializationType": "WFContentPredicateTableTemplate"},
        **({"WFContentItemLimitEnabled": True, "WFContentItemLimitNumber": limit} if limit else {}))
    return output_of(u, "Music")

# Exact match first.
set_variable("Song", find_music([music_filter("Title", "Title"), music_filter("Artist", "Artist"),
                                 music_filter("Album", "Album")], limit=1))
# Find Music's "is" minds capitals, and the phone can show an album or artist capitalised differently from the
# Mac's export ("The Lion the Beast the Beat" vs "The Lion The Beast The Beat"). So if nothing matched, look at
# every song with this title and take one whose artist and album match apart from capitals. Requiring both keeps
# it from picking a live or other version of the song.
retry = new_id()
if_start(retry, named("Song"), HAS_NO_VALUE)
set_variable("Key", lowercase(text_parts(named("Artist"), "|", named("Album"))))
candidates = find_music([music_filter("Title", "Title")])
inner = new_id()
add("is.workflow.actions.repeat.each", GroupingIdentifier=inner, WFControlFlowMode=0, WFInput=candidates)
cand = named("Repeat Item 2")
cand_key = lowercase(text_parts(detail("Artist", cand), "|", detail("Album", cand)))
same = new_id()
if_start(same, cand_key, IS, compare_to=text_parts(named("Key")))
set_variable("Song", cand)
if_otherwise(same)
if_end(same)
add("is.workflow.actions.repeat.each", GroupingIdentifier=inner, WFControlFlowMode=2, UUID=new_id())
if_otherwise(retry)
if_end(retry)

found = new_id()
if_start(found, named("Song"), HAS_ANY_VALUE)
add("is.workflow.actions.addtoplaylist", WFInput=named("Song"), WFPlaylistName=text("", named("Playlist Name")))
if_otherwise(found)
add("is.workflow.actions.appendvariable", WFVariableName="Missing", WFInput=get_value("index", item))
if_end(found)
add("is.workflow.actions.repeat.each", GroupingIdentifier=loop, WFControlFlowMode=2, UUID=new_id())

# Part 4: report back to Crate
combine_id = new_id()
add("is.workflow.actions.text.combine", UUID=combine_id, WFTextSeparator="Custom", WFTextCustomSeparator=text(","),
    text=named("Missing"))
text_id = new_id()
add("is.workflow.actions.gettext", UUID=text_id, WFTextActionText=text(f"v{VERSION} missing:", output_of(combine_id, "Combined Text")))
add("is.workflow.actions.output", WFOutput=text("", output_of(text_id, "Text")), WFNoOutputSurfaceBehavior="Do Nothing")

shortcut = {
    "WFWorkflowClientVersion": "2302.0.4",
    "WFWorkflowMinimumClientVersion": 900,
    "WFWorkflowMinimumClientVersionString": "900",
    "WFWorkflowIcon": {"WFWorkflowIconStartColor": 463140863, "WFWorkflowIconGlyphNumber": 59511},
    "WFWorkflowImportQuestions": [],
    "WFWorkflowTypes": [],
    "WFQuickActionSurfaces": [],
    "WFWorkflowHasShortcutInputVariables": True,
    "WFWorkflowInputContentItemClasses": ["WFStringContentItem", "WFDictionaryContentItem", "WFGenericFileContentItem"],
    "WFWorkflowOutputContentItemClasses": [],
    "WFWorkflowActions": actions,
}

out = sys.argv[1] if len(sys.argv) > 1 else "crate-add-songs-unsigned.shortcut"
with open(out, "wb") as f:
    plistlib.dump(shortcut, f, fmt=plistlib.FMT_BINARY)
print(f"wrote {out}: {len(actions)} actions")
