#!/usr/bin/env python3
"""Builds the unsigned "Crate Add Songs" shortcut as a property list.

Apple only imports signed shortcuts, so sign the output on a Mac:
    shortcuts sign --mode anyone --input crate-add-songs-unsigned.shortcut --output "Crate Add Songs.shortcut"
The imported shortcut takes its name from the signed file's name.

It mirrors the steps in site/shortcut-setup.html: read Crate's JSON (playlist, songs[title, artist, album,
index], and "create" only when the playlist must be made), create the playlist if asked, add each song found by Find Music, and output
"missing:<indexes>" for the songs it couldn't find.
"""
import plistlib
import sys
import uuid

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

def if_start(group, subject, condition):
    # Only presence tests are used: Shortcuts won't offer "is" for an untyped dictionary value, so a text
    # comparison imports with its text blank. Crate omits "create" unless the playlist must be made.
    add("is.workflow.actions.conditional", GroupingIdentifier=group, WFControlFlowMode=0, WFCondition=condition,
        WFInput={"Type": "Variable", "Variable": subject})

def if_otherwise(group):
    add("is.workflow.actions.conditional", GroupingIdentifier=group, WFControlFlowMode=1)

def if_end(group):
    add("is.workflow.actions.conditional", GroupingIdentifier=group, WFControlFlowMode=2, UUID=new_id())

IS, HAS_ANY_VALUE = 4, 100  # Shortcuts' condition codes (IS is used by Find Music's filters)

# Part 1: read what Crate sends
dict_id = new_id()
add("is.workflow.actions.detect.dictionary", UUID=dict_id, WFInput=SHORTCUT_INPUT)
dictionary = output_of(dict_id, "Dictionary")
set_variable("Playlist Name", get_value("playlist", dictionary))

# Part 2: create the playlist if Crate asks
create = get_value("create", dictionary)
g = new_id()
if_start(g, create, HAS_ANY_VALUE)
add("is.workflow.actions.createplaylist", UUID=new_id(), WFPlaylistName=text("", named("Playlist Name")))
# A playlist created moments ago can't yet be found by name, so Add to Playlist would silently add nowhere.
add("is.workflow.actions.delay", WFDelayTime=3)
if_otherwise(g)
if_end(g)

# Part 3: go through the songs
songs = get_value("songs", dictionary)
loop = new_id()
add("is.workflow.actions.repeat.each", GroupingIdentifier=loop, WFControlFlowMode=0, WFInput=songs)
item = named("Repeat Item")
set_variable("Title", get_value("title", item))
set_variable("Artist", get_value("artist", item))
set_variable("Album", get_value("album", item))

def music_filter(prop, var):
    return {"Operator": IS, "Property": prop, "Removable": True,
            "Values": {"String": text("", named(var)), "Unit": 4}}
find_id = new_id()
add("is.workflow.actions.filter.music", UUID=find_id,
    WFContentItemFilter={"Value": {"WFActionParameterFilterPrefix": 1, "WFContentPredicateBoundedDate": False,
                                   "WFActionParameterFilterTemplates": [music_filter("Title", "Title"),
                                                                        music_filter("Artist", "Artist"),
                                                                        music_filter("Album", "Album")]},
                         "WFSerializationType": "WFContentPredicateTableTemplate"},
    WFContentItemLimitEnabled=True, WFContentItemLimitNumber=1)
music = output_of(find_id, "Music")

found = new_id()
if_start(found, music, HAS_ANY_VALUE)
add("is.workflow.actions.addtoplaylist", WFInput=music, WFPlaylistName=text("", named("Playlist Name")))
if_otherwise(found)
add("is.workflow.actions.appendvariable", WFVariableName="Missing", WFInput=get_value("index", item))
if_end(found)
add("is.workflow.actions.repeat.each", GroupingIdentifier=loop, WFControlFlowMode=2, UUID=new_id())

# Part 4: report back to Crate
combine_id = new_id()
add("is.workflow.actions.text.combine", UUID=combine_id, WFTextSeparator="Custom", WFTextCustomSeparator=text(","),
    text=named("Missing"))
text_id = new_id()
add("is.workflow.actions.gettext", UUID=text_id, WFTextActionText=text("missing:", output_of(combine_id, "Combined Text")))
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
