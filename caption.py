import argparse
import colorama
from functools import partial
from termcolor import cprint
import time
import toml
from numbers import Number
import os
from pathlib import Path
import pdb
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ceil = lambda i : int(i) if int(i) == i else int(i + 1)

# TODOs:
#    - write up a guide
#    - split program into multiple files
#    - fix credits

# Debug printers
def printFormatWords(fmtWords):
    for word in fmtWords:
        print(f"word len: {word.actualLength:6.2f} | ", end="")
        unitsLen = 0
        for unit in word.fmtUnits:
            unitsLen += unit.length
        print(f"units len: {unitsLen:6.2f} | ", end="")
        for unit in word.fmtUnits:
            print(f"{unit.txt}|", end="")
        print()

def printFormattedLines(fmtLines):
    for i, line in enumerate(fmtLines):
        print(f"{i:03} | height: {line.maxHeight:4} | ", end="")
        for word in line.fmtWords:
            for unit in word.fmtUnits:
                print(f"{unit.txt}:", end="")
            print(" ", end="")
        print()

class UserError(Exception):
    def __init__(self, message):
        self.message = message

    @staticmethod
    def uassert(cond, message):
        if not cond:
            raise UserError(message)

class Logging:
    width = 80
    baseUsable = width - 4
    tab = 8

    @staticmethod
    def divider():
        print(f"+{'':->{Logging.width-2}}+")

    @staticmethod
    def header(text):
        Logging.divider()
        cprint(f"| {text:<{Logging.baseUsable}} |", attrs=["bold"])

    @staticmethod
    def subSection(text, levels=1, color="cyan"):
        print("| ", end="")
        usable = Logging.baseUsable - (Logging.tab * levels)
        cprint(f"{'': >{Logging.tab * levels}}{text:<{usable}}", color, end="")
        print(" |")

    @staticmethod
    def table(table, levels=1):
        assert len(table) > 0, "Expected log table to have at least one element"
        colls = len(table[0])
        tableStrs = []

        for row in table:
            strRow = []
            for coll in row:
                strRow.append(str(coll))
            tableStrs.append(strRow)

        collLens = []
        for collI in range(colls):
            currMaxLen = 0
            for row in tableStrs:
                currMaxLen = max(len(row[collI]), currMaxLen)
            collLens.append(currMaxLen + 2)

        tableEdge = "+"
        for length in collLens:
            tableEdge += f"{'':->{length}}+"
        usable = Logging.baseUsable - (Logging.tab * levels)

        print(f"| {'': >{Logging.baseUsable}} |")
        print(f"| {'': >{Logging.tab * levels}}{tableEdge:<{usable}} |")
        for row in tableStrs:
            rowStr = "| "
            for i, (coll, collLen) in enumerate(zip(row, collLens)):
                align = "<" if i == 0 else ">"
                rowStr += f"{coll:{align}{collLen-2}} | "
            print(f"| {'': >{Logging.tab * levels}}{rowStr:<{usable}} |")
        print(f"| {'': >{Logging.tab * levels}}{tableEdge:<{usable}} |")

    @staticmethod
    def filesizeStr(filename):
        sizeBytes = Path(filename).stat().st_size
        units = ["B", "KB", "MB", "GB", "TB"]
        for unit in units:
            if sizeBytes >= 1024:
                sizeBytes = sizeBytes / 1024
            else:
                return f"{sizeBytes:.2f} {unit:>2}"

    @staticmethod
    def dimensionsStr(imgname):
        img = Image.open(imgname)
        return f"{img.width}x{img.height} px"

class UserSpec:
    rgbaRe = re.compile("#([0-9A-F][0-9A-F])([0-9A-F][0-9A-F])"
                        "([0-9A-F][0-9A-F])([0-9A-F][0-9A-F])",
                         re.IGNORECASE)
    rgbRe = re.compile("#([0-9A-F][0-9A-F])([0-9A-F][0-9A-F])([0-9A-F][0-9A-F])",
                         re.IGNORECASE)

    def __init__(self, fileName):
        def checkKeys(actualKeys, validKeys, requiredKeys, internalColl={}):
            for actualKey in actualKeys:
                UserError.uassert( actualKey in validKeys,
                    f"Unexpected option '{actualKey}', expected one of '{validKeys}'" )
                internalColl[actualKey] = {}
                internalColl[actualKey]["default"] = False
                # Will be set to an actual value in a "validate*()" functions
                internalColl[actualKey]["value"] = None
            for requiredKey in requiredKeys:
                UserError.uassert(requiredKey in actualKeys,
                    f"Required option '{requiredKey}' not included")
            for defaultKey in (validKeys - internalColl.keys()):
                internalColl[defaultKey] = {}
                internalColl[defaultKey]["default"] = True
                # Will be set to an actual value in a "validate*()" function, or at a
                # later stage in the program after the text has been parsed.
                internalColl[defaultKey]["value"] = None

        Logging.header(f"Verifying specification file '{fileName}'")
        UserError.uassert( Path(fileName).is_file(), f"File '{fileName}' does not exist" )
        with open(fileName, "r", encoding="utf-8") as f:
            spec = toml.load(f)

        Logging.subSection("Checking top level headers...")
        topLevelKeys = ["image", "text", "output", "characters"]
        checkKeys(spec.keys(), topLevelKeys, topLevelKeys)

        Logging.subSection("Checking [image]...")
        self.image = {}
        self.imageValidKeys = ["art", "image_height", "bg_color"]
        imageRequiredKeys = ["bg_color"]
        checkKeys(spec["image"], self.imageValidKeys, imageRequiredKeys, self.image)
        self.validateAndSetImage(spec["image"])

        Logging.subSection("Checking [text]...")
        self.text = {}
        self.textValidKeys = ["text", "base_font_height", "padding", "line_spacing",
                              "text_width", "text_box_pos", "alignment", "credits",
                              "credits_pos"]
        textRequiredKeys = ["text", "text_box_pos"]
        checkKeys(spec["text"], self.textValidKeys, textRequiredKeys, self.text)
        self.validateAndSetText(spec["text"])

        Logging.subSection("Checking [output]...")
        self.output = {}
        self.outputValidKeys = ["outputs", "output_directory", "output_img_format",
                                "output_img_quality", "base_filename"]
        outputRequiredKeys = ["base_filename"]
        checkKeys(spec["output"], self.outputValidKeys, outputRequiredKeys, self.output)
        self.validateAndSetOutput(spec["output"])

        Logging.subSection("Checking [[characters]]...")
        self.characters = []
        self.characterValidKeys = ["name", "color", "relative_height", "stroke_width",
                                   "stroke_color", "font", "font_bold", "font_italic",
                                   "font_bolditalic"]
        characterRequiredKeys = ["name", "color", "font"]
        for i, character in enumerate(spec["characters"]):
            Logging.subSection(f"Checking character #{i+1}...", 2)
            currChar = {}
            checkKeys(character, self.characterValidKeys, characterRequiredKeys, currChar)
            self.validateAndSetChar(character, currChar)
            self.characters.append(currChar)

        characterNames = [char["name"]["value"] for char in self.characters]
        for name in list(characterNames):
            characterNames.pop(0)
            UserError.uassert(name not in characterNames, "Found multiple characters named " \
                f"'{name}', cannot use the same name for multiple characters")

        Logging.subSection("Checking conflicts between headers...")
        imgHeightGiven = not self.image["image_height"]["default"]
        txtHeightGiven = not self.text["base_font_height"]["default"]
        UserError.uassert(not (imgHeightGiven and txtHeightGiven),
                          f"Cannot specify image_height and base_font_height together")

        artNotGiven = self.image["art"]["default"]
        if artNotGiven:
            outputs = self.output["outputs"]["value"]
            UserError.uassert(outputs == "parts", "Cannot generate caption without art. " \
                "Either specify 'art' under [image], or set 'outputs' to 'parts' " \
                "under [output]")

        Logging.subSection("Specification file is valid!", 1, "green")

    @staticmethod
    def checkFile(coll, key):
        fileName = coll[key]
        UserError.uassert(Path(fileName).is_file(), f"File '{fileName}' does not exist")
        return fileName

    @staticmethod
    def checkTypeAndMinVal(expType, minVal, cond, coll, key):
        value = coll[key]
        UserError.uassert(isinstance(value, expType), \
            f"Expected {key} to be {expType}, got {type(value)}")

        assert cond in ["gt", "gte"]
        if cond == "gt":
            UserError.uassert(
                value > minVal, f"{key} must be greater than {minVal}, got {value}")
        elif cond == "gte":
            UserError.uassert(
                value >= minVal, f"{key} must be greater than or equal to {minVal}, got {value}")
        return value

    @staticmethod
    def checkColor(coll, key):
        value = coll[key]
        if UserSpec.rgbaRe.fullmatch(value):
            pass
        elif UserSpec.rgbRe.fullmatch(value):
            value += "FF"
        else:
            UserError.uassert(False, f"Invalid hex color {value}")
        return value

    @staticmethod
    def valueInList(expList, coll, key):
        value = coll[key]
        UserError.uassert(value in expList,
            f"Invalid '{key}', expected one of {expList}, got '{value}'")
        return value

    @staticmethod
    def validateAndFillSpec(inSpec, outSpec, checkSpec):
        for key in checkSpec:
            if outSpec[key]["default"] == False:
                outSpec[key]["value"] = checkSpec[key]["check"](inSpec, key)
            else:
                if "default" in checkSpec[key]:
                    outSpec[key]["value"] = checkSpec[key]["default"]
                else:
                    outSpec[key]["value"] = None

    def validateAndSetImage(self, inImage):
        checkImage = {
            "art" : {
                "check" : UserSpec.checkFile
            },
            "image_height" : {
                "check" : partial(UserSpec.checkTypeAndMinVal, int, 0, "gt")
            },
            "bg_color" : {
                "check" : UserSpec.checkColor
            }
        }
        UserSpec.validateAndFillSpec(inImage, self.image, checkImage)

    def validateAndSetText(self, inText):
        def checkCredits(coll, key):
            capCredits = coll[key]
            UserError.uassert(isinstance(capCredits, list),
                f"Expected {capCredits} to be {list}, got {type(capCredits)}")
            for line in capCredits:
                UserError.uassert(isinstance(line, str),
                    f"Expected line {line} in credits to be {str}, got {type(line)}")
            return capCredits

        checkText = {
            "text" : {
                "check" : UserSpec.checkFile
            },
            "base_font_height" : {
                "check" : partial(UserSpec.checkTypeAndMinVal, int, 0, "gt"),
                "default" : 16
            },
            "padding" : {
                "check" : partial(UserSpec.checkTypeAndMinVal, Number, 0, "gte"),
                "default" : 1
            },
            "line_spacing" : {
                "check" : partial(UserSpec.checkTypeAndMinVal, Number, 0, "gte"),
                "default" : 0.2
            },
            "text_width" : {
                "check" : partial(UserSpec.checkTypeAndMinVal, Number, 0, "gt"),
            },
            "text_box_pos" : {
                "check" : partial(UserSpec.valueInList, ["left", "right", "split"])
            },
            "alignment" : {
                "check" : partial(UserSpec.valueInList, ["left", "right", "center"]),
                "default" : "center"
            },
            "credits" : {
                "check" : checkCredits,
                "default" : []
            },
            "credits_pos" : {
                "check" : partial(UserSpec.valueInList, ["tl", "tr", "bl", "br"]),
                "default" : "tl"
            }
        }
        UserSpec.validateAndFillSpec(inText, self.text, checkText)

    def validateAndSetOutput(self, inOutput):
        def valueIsIntInRange(minVal, maxVal, coll, key):
            value = coll[key]
            UserError.uassert(isinstance(value, int),
                f"Expected {key} to be {int}, got {type(value)}")
            UserError.uassert(minVal <= value <= maxVal,
                f"Value {value} for {key} not in range [{minVal}, {maxVal}]")
            return value

        def checkDirectory(coll, key):
            directory = coll[key]
            UserError.uassert(Path(directory).is_dir(),
                f"Directory '{directory}' does not exist")
            return directory

        checkOutput = {
            "outputs" : {
                "check" : partial(UserSpec.valueInList, ["caption", "parts", "all"]),
                "default" : "caption"
            },
            "output_directory" : {
                "check" : checkDirectory,
                "default" : ""
            },
            "output_img_format" : {
                "check" : partial(UserSpec.valueInList, ["png", "jpg", "jpeg"]),
                "default" : "png"
            },
            "output_img_quality" : {
                "check" : partial(valueIsIntInRange, 0, 100),
                "default" : 100
            },
            "base_filename" : {
                "check" : lambda coll, key : str(coll[key]),
            }
        }
        UserSpec.validateAndFillSpec(inOutput, self.output, checkOutput)

    def validateAndSetChar(self, inChar, storedChar):
        def verifyNoSpecialChars(coll, key):
            name = coll[key]
            specialChars = ["[", "]", "*", "_", " ", "\n"]
            for char in specialChars:
                UserError.uassert(char not in name,
                    f"Special character '{char}' not allowed in name '{name}'")
            return name

        checkChar = {
            "name" : {
                "check" : verifyNoSpecialChars
            },
            "relative_height" : {
                "check" : partial(UserSpec.checkTypeAndMinVal, Number, 0, "gt"),
                "default" : 1
            },
            "color" : {
                "check" : UserSpec.checkColor
            },
            "stroke_width" : {
                "check" : partial(UserSpec.checkTypeAndMinVal, Number, 0, "gte"),
                "default" : 0
            },
            "stroke_color" : {
                "check" : UserSpec.checkColor,
                "default" : "#000000FF"
            },
            "font" : {
                "check" : UserSpec.checkFile
            },
            "font_bold" : {
                "check" : UserSpec.checkFile,
                "default" : inChar["font"]
            },
            "font_italic" : {
                "check" : UserSpec.checkFile,
                "default" : inChar["font"]
            },
            "font_bolditalic" : {
                "check" : UserSpec.checkFile,
                "default" : inChar["font"]
            }
        }
        UserSpec.validateAndFillSpec(inChar, storedChar, checkChar)

    def outputFilledSpec(self, specFilename):
        def writeSection(f, data, orderedKeys):
            for key in orderedKeys:
                if data[key]["default"] == False:
                    if isinstance(data[key]["value"], str):
                        f.write(f"{key} = \"{data[key]['value']}\"\n")
                    else:
                        f.write(f"{key} = {data[key]['value']}\n")
            for key in orderedKeys:
                if data[key]["default"] == True:
                    if isinstance(data[key]["value"], str):
                        f.write(f"# {key} = \"{data[key]['value']}\"\n")
                    else:
                        f.write(f"# {key} = {data[key]['value']}\n")

        with open(specFilename, "w") as f:
            f.write("[image]\n")
            writeSection(f, self.image, self.imageValidKeys)
            f.write("\n[text]\n")
            writeSection(f, self.text, self.textValidKeys)
            f.write("\n[output]\n")
            writeSection(f, self.output, self.outputValidKeys)
            f.write("\n")
            for char in self.characters:
                f.write("[[characters]]\n")
                writeSection(f, char, self.characterValidKeys)
                f.write("\n")

class Font:
    def __init__(self, path, height, color, stroke, strokeColor):
        self.font = ImageFont.truetype(path, height)
        self.height = height
        self.spaceLen = self.font.getlength(" ")

        fontColorMatches = UserSpec.rgbaRe.fullmatch(color)
        self.rgba = (int(fontColorMatches[1], 16),
                     int(fontColorMatches[2], 16),
                     int(fontColorMatches[3], 16),
                     int(fontColorMatches[4], 16))

        self.stroke = stroke
        strokeColorMatches = UserSpec.rgbaRe.fullmatch(strokeColor)
        self.strokeRgba = (int(strokeColorMatches[1], 16),
                           int(strokeColorMatches[2], 16),
                           int(strokeColorMatches[3], 16),
                           int(strokeColorMatches[4], 16))

    def getLength(self, text):
        return self.font.getlength(text)

    def rescale(self, scale):
        self.height = int(self.height * scale)
        self.font = self.font.font_variant(size=self.height)

    def imgDrawKwargs(self):
        return {
            "font" : self.font,
            "fill" : self.rgba,
            "stroke_width" : self.stroke,
            "stroke_fill" : self.strokeRgba
        }

class FmtUnit:
    def __init__(self, txt, font):
        self.txt = txt
        self.font = font
        self.length = 0
        self.setLength()

    def setLength(self):
        self.length = self.font.getLength(self.txt)

    def drawUnit(self, d, x, y):
        d.text((x, y), self.txt, anchor="ls", **self.font.imgDrawKwargs())

class FmtWord:
    def __init__(self, fmtUnits, maxHeight=None):
        self.fmtUnits = fmtUnits
        self._maxHeight = maxHeight

        self.actualLength = 0
        for unit in fmtUnits:
            self.actualLength += unit.length
        self.spaceLength = 0

    def isNewline(self):
        return self.fmtUnits == []

    def maxHeight(self):
        if self._maxHeight is not None:
           return self._maxHeight

        self._maxHeight = 0
        for unit in self.fmtUnits:
            self._maxHeight = max(unit.font.height, self._maxHeight)
        return self._maxHeight

def loadFonts(charSpecs, baseHeight):
    fonts = {}
    for charSpec in charSpecs:
        charFonts = {}
        for font in ["font", "font_bold", "font_italic", "font_bolditalic"]:
            height = max(1, int(baseHeight * charSpec["relative_height"]["value"]))
            stroke = int(baseHeight * charSpec["stroke_width"]["value"])
            charFonts[font] = Font(
                charSpec[font]["value"], height, charSpec["color"]["value"],
                stroke, charSpec["stroke_color"]["value"])
        fonts[charSpec["name"]["value"]] = charFonts
    return fonts

def gatherPeople(text, lBraces, rBraces, validPeople):
    strRange = 10
    (lBraces, rBraces) = (list(lBraces), list(rBraces))
    people = []

    while lBraces or rBraces:
        if not lBraces:
            val = rBraces[0]
            strWindow = text[max(0,val-strRange):val+strRange]
            UserError.uassert(
                False, f"Unmatched ']' around \n'''\n...{strWindow}...\n'''")
        if not rBraces:
            val = lBraces[0]
            strWindow = text[max(0,val-strRange):val+strRange]
            UserError.uassert(
                False, f"Unmatched '[' around \n'''\n...{strWindow}...\n'''")

        (currL, currR) = (lBraces.pop(0), rBraces.pop(0))
        if currL > currR:
            valR = currR
            strWindowR = text[max(0,valR-strRange):valR+strRange]
            valL = currL
            strWindowL = text[max(0,valL-strRange):valL+strRange]
            UserError.uassert(
                False, f"']' around \n'''\n...{strWindowR}...\n'''\n appeared before " \
                f"'[' around \n'''\n...{strWindowL}...\n'''")

        person = text[currL+1:currR]
        UserError.uassert(person in validPeople, f"Unexpected character '{person}' " \
                          f"in text file, expected one of {validPeople}")
        people.append(person)
    return people

def parse_text(text):
    class FmtState:
        def __init__(self, font, bold, italic, person):
            self.font = font
            self.bold = bold
            self.italic = italic
            self.person = person
            self.startIndx = 0

            self.fmtWords = []
            self.fmtUnits = []

        def updateState(self, currChar, currIndx, specialColl, text):
            if currChar == "[":
                self.updatePerson(specialColl["["], text)
            elif currChar == "*":
                self.toggleBold(currIndx)
            elif currChar == "_":
                self.toggleItalic(currIndx)
            elif currChar == "\n":
                self.updateNewline(currIndx)
            elif currChar == " ":
                self.updateSpace(currIndx)
            else:
                assert False, f"`updateState()` called with invalid char '{currChar}'"

        def setFont(self):
            if self.bold and self.italic:
                self.font = FONTS[self.person]["font_bolditalic"]
            elif self.bold:
                self.font = FONTS[self.person]["font_bold"]
            elif self.italic:
                self.font = FONTS[self.person]["font_italic"]
            else:
                self.font = FONTS[self.person]["font"]

        def updatePerson(self, lBraceDict, text):
            i = lBraceDict["end_indices"].pop(0) + 1
            for char in text[i:]:
                if char == " " or char == "\n":
                    i += 1
                else:
                    break
            self.startIndx = i
            self.person = lBraceDict["people"].pop(0)
            self.setFont()

        def toggleBold(self, currIndx):
            self.startIndx = currIndx + 1
            self.bold = not self.bold
            self.setFont()

        def toggleItalic(self, currIndx):
            self.startIndx = currIndx + 1
            self.italic = not self.italic
            self.setFont()

        def updateNewline(self, currIndx):
            if self.fmtUnits:
                self.fmtWords.append(FmtWord(self.fmtUnits))
                self.fmtUnits = []

            self.fmtWords.append(FmtWord([], self.font.height))
            self.startIndx = currIndx + 1

        def updateSpace(self, currIndx):
            if self.fmtUnits:
                self.fmtWords.append(FmtWord(self.fmtUnits))
                self.fmtUnits = []

            self.startIndx = currIndx + 1

    Logging.subSection(f"Parsing text file")
    specialChars = {
        "["  : {
            "indices" : [],
            "end_indices": [],
            "people" : [],
        },
        "]"  : { "indices" : [] },
        "*"  : { "indices" : [] },
        "_"  : { "indices" : [] },
        "\n" : { "indices" : [] },
        " "  : { "indices" : [] }
    }
    originalSpecialChars = list(specialChars.keys())

    lastCharSlash = False
    # Collect all braces/asterisks/underscores. Prune out the markers preceded by a '\'
    for i, char in enumerate(text):
        if char in specialChars and not lastCharSlash:
            specialChars[char]["indices"].append(i)
        else:
            lastCharSlash = (char == "\\")

    # Assert that people specifers are valid and collect people
    specialChars["["]["people"] = gatherPeople(
        text, specialChars["["]["indices"], specialChars["]"]["indices"],
        list(FONTS.keys()))

    specialChars["["]["end_indices"] = specialChars["]"]["indices"]
    del specialChars["]"]

    # Block out contiguous regions of text with unique formatting. Prune whitespace
    # immediately after character specifier.
    firstPerson = SPEC.characters[0]["name"]["value"]
    fmtState = FmtState(FONTS[firstPerson]["font"], False, False, firstPerson)
    while True:
        endIndx = float('inf')
        empty = 0
        for char in specialChars:
            if not specialChars[char]["indices"]:
                empty += 1
                continue
            if specialChars[char]["indices"][0] < endIndx:
                nxtSpecialChar = char
                endIndx = specialChars[char]["indices"][0]
        if empty == len(specialChars):
            break

        specialChars[nxtSpecialChar]["indices"].pop(0)

        currRegionText = text[fmtState.startIndx : endIndx]

        for specialChar in originalSpecialChars:
            currRegionText = currRegionText.replace(f"\\{specialChar}", specialChar)

        if currRegionText != "":
            fmtState.fmtUnits.append(FmtUnit(currRegionText, fmtState.font))

        fmtState.updateState(
            nxtSpecialChar, endIndx, specialChars, text)

    currRegionText = text[fmtState.startIndx:]
    if currRegionText != "":
        fmtState.fmtUnits.append(FmtUnit(currRegionText, fmtState.font))
        fmtState.fmtWords.append(FmtWord(fmtState.fmtUnits))

    return fmtState.fmtWords

class FormattedLine:
    def __init__(self, fmtWords, maxHeight):
        self.maxHeight = maxHeight
        self.accumUnits = []
        self.spaceLens = []
        self.length = 0

        if not fmtWords:
            return

        currFont = fmtWords[0].fmtUnits[0].font
        currTxt = ""

        # Accumulate contiguous FmtUnits which are formatted in the same way into a
        # a single FmtUnit. Rendering the space between words (especially on Windows)
        # behaves better when space is encoded in the text to render, rather than
        # manually specifying the coordinates that each word should be printed at.
        for word in fmtWords:
            firstUnit = word.fmtUnits[0]
            if firstUnit.font == currFont:
                if currTxt != "":
                    currTxt += " "
                currTxt += firstUnit.txt
            else:
                tmpUnit = FmtUnit(currTxt, currFont)
                self.accumUnits.append(tmpUnit)
                self.spaceLens.append(word.spaceLength)

                currTxt = firstUnit.txt
                currFont = firstUnit.font

            for unit in word.fmtUnits[1:]:
                if unit.font == currFont:
                    currTxt += unit.txt
                else:
                    tmpUnit = FmtUnit(currTxt, currFont)
                    self.accumUnits.append(tmpUnit)
                    self.spaceLens.append(0)

                    currTxt = unit.txt
                    currFont = unit.font
        if currTxt != "":
            tmpUnit = FmtUnit(currTxt, currFont)
            self.accumUnits.append(tmpUnit)
            self.spaceLens.append(0)

        self.length = (sum([unit.length for unit in self.accumUnits]) +
                       sum(self.spaceLens))

    def rescale(self, scale):
        self.maxHeight = int(self.maxHeight * scale)
        self.spaceLens = [length * scale for length in self.spaceLens]
        for unit in self.accumUnits:
            unit.setLength()
        self.length = (sum([unit.length for unit in self.accumUnits]) +
                       sum(self.spaceLens))

    def drawLine(self, d, x, y):
        for (spaceLen, unit) in zip(self.spaceLens, self.accumUnits):
            unit.drawUnit(d, x, y)
            x += unit.length + spaceLen

    def isNewline(self):
        return self.length == 0

def wrapRegions(fmtWords, width):
    Logging.subSection("Wrapping parsed text")
    formattedLines = []
    currLen = 0
    currWords = []
    currMaxHeight = 0

    for i, fmtWord in enumerate(fmtWords):
        if fmtWord.isNewline():
            currLine = FormattedLine(currWords, currMaxHeight)
            formattedLines.append(currLine)

            currLen = 0
            currWords = []
            currMaxHeight = fmtWord.maxHeight()
            continue

        if currLen == 0:
            currWords.append(fmtWord)
            currLen += fmtWord.actualLength
            currMaxHeight = max(fmtWord.maxHeight(), currMaxHeight)
            continue

        prevWordSpaceLen = fmtWords[i-1].fmtUnits[-1].font.spaceLen
        currWordSpaceLen = fmtWord.fmtUnits[-1].font.spaceLen
        fmtWord.spaceLength = min(prevWordSpaceLen, currWordSpaceLen)

        newLen = fmtWord.actualLength + fmtWord.spaceLength + currLen
        if newLen > width:
            currLine = FormattedLine(currWords, currMaxHeight)
            formattedLines.append(currLine)
            fmtWord.spaceLength = 0

            currLen = fmtWord.actualLength
            currWords = [fmtWord]
            currMaxHeight = fmtWord.maxHeight()
            continue

        currWords.append(fmtWord)
        currLen = newLen
        currMaxHeight = max(fmtWord.maxHeight(), currMaxHeight)

    if currWords:
        currLine = FormattedLine(currWords, currMaxHeight)
        formattedLines.append(currLine)

    return formattedLines

class TextBox:
    class Align:
        LEFT = "left"
        RIGHT = "right"
        CENTER = "center"

    def __init__(self, fmtLines, baseHeight, lineSpacing, padding):
        self.fmtLines = fmtLines
        self.baseHeight = baseHeight
        self.lineSpacing = lineSpacing
        self.padding = padding

        if fmtLines:
            self.maxLineLen = max([line.length for line in fmtLines])
            self.averageFontHeight = int(sum([line.maxHeight for line in fmtLines])/len(fmtLines))
        else:
            self.maxLineLen = 0
            self.averageFontHeight = 0

        self.computeDimensions()

    def computeDimensions(self):
        self.width = ceil(self.maxLineLen + (self.padding * 2))

        self.height = self.padding * 2
        for line in self.fmtLines:
            self.height += self.lineSpacing + line.maxHeight

    def split(self):
        def reversedList(reversedIt):
            return list(reversed(reversedIt))

        def splitForward(lFmtLines, rFmtLines):
            for line in list(rFmtLines):
                if line.isNewline():
                    rFmtLines.pop(0)
                    break
                lFmtLines.append(rFmtLines.pop(0))
            return [lFmtLines, rFmtLines]

        Logging.subSection("Splitting wrapped text")
        splitA = splitForward(self.fmtLines[:int(len(self.fmtLines)/2)],
                              self.fmtLines[int(len(self.fmtLines)/2):])
        splitB = splitForward(reversedList(self.fmtLines[int(len(self.fmtLines)/2):]),
                              reversedList(self.fmtLines[:int(len(self.fmtLines)/2)]))
        splitB = [reversedList(fmtLines) for fmtLines in reversed(splitB)]

        splitADiff = abs(len(splitA[0]) - len(splitA[1]))
        splitBDiff = abs(len(splitB[0]) - len(splitB[1]))
        splitToUse = splitA if splitADiff <= splitBDiff else splitB

        return [TextBox(splitToUse[0], self.baseHeight, self.lineSpacing, self.padding),
                TextBox(splitToUse[1], self.baseHeight, self.lineSpacing, self.padding)]

    def rescale(self, scale):
        for fmtLine in self.fmtLines:
            fmtLine.rescale(scale)

        if self.fmtLines:
            self.maxLineLen = max([line.length for line in self.fmtLines])
        self.lineSpacing = int(self.lineSpacing * scale)
        self.padding = int(self.padding * scale)
        self.computeDimensions()

        if self.fmtLines:
            self.averageFontHeight = \
                int(sum([line.maxHeight for line in self.fmtLines])/len(self.fmtLines))

    def drawText(self, d, alignment, startX=0, startY=0):
        (x, y) = (startX + self.padding,
                  startY + self.padding - int(0.2 * self.averageFontHeight))
        for fmtLine in self.fmtLines:
            y += fmtLine.maxHeight
            if alignment == self.Align.CENTER:
                x += (self.maxLineLen - fmtLine.length)/2
            elif alignment == self.Align.RIGHT:
                x += self.maxLineLen - fmtLine.length

            fmtLine.drawLine(d, x, y)
            (x, y) = (startX + self.padding, y + self.lineSpacing)

def drawCredits(d, capCredits, creditsPos, artX, artY, artWidth, artHeight):
    padding = int(SPEC.text["padding"]["value"] *
                  SPEC.text["base_font_height"]["value"])

    if "credits" in FONTS:
        font = FONTS["credits"]["font"]
    else:
        firstPerson = SPEC.characters[0]["name"]["value"]
        font = FONTS[firstPerson]["font"]

    fontKwargs = font.imgDrawKwargs()
    fontKwargs.pop("fill")
    fontKwargs.pop("stroke_fill")

    (_, _, creditsWidth, creditsHeight) = \
        d.multiline_textbbox((0, 0), capCredits, **fontKwargs)
    # When creating a bounding box at (0, 0), PIL doesn't put the top left corner at
    # exactly (0, 0). Manually correct this by adding an offset.
    creditsWidth += 1
    creditsHeight += 3
    if creditsPos == "tl":
        topLeft = (artX + padding, artY + padding)
        d.multiline_text(topLeft, capCredits, align="left", **font.imgDrawKwargs())
    elif creditsPos == "tr":
        topLeft = (artX + artWidth - (creditsWidth + padding), artY + padding)
        d.multiline_text(topLeft, capCredits, align="right", **font.imgDrawKwargs())
    elif creditsPos == "bl":
        topLeft = (artX + padding, artY + artHeight - (creditsHeight + padding))
        d.multiline_text(topLeft, capCredits, align="left", **font.imgDrawKwargs())
    elif creditsPos == "br":
        topLeft = (artX + artWidth - (creditsWidth + padding),
                   artY + artHeight - (creditsHeight + padding))
        d.multiline_text(topLeft, capCredits, align="right", **font.imgDrawKwargs())

def autoWidth(textHeight, fmtWords, textBoxPos):
    charCount = 0
    for word in fmtWords:
        for unit in word.fmtUnits:
            charCount += len(unit.txt)

    # The "magic" equation below was found using data from two column captions.
    # Thus, adjust the character count for non-split captions accorindgly.
    if textBoxPos != TextBoxPos.SPLIT:
        charCount /= 1.25

    # These are "magic" numbers based off of data gathered from existing captions. As
    # the character count of a caption increases, the number of characters per line
    # tends to increase with the following linear curve.
    optimalCharsPerLine = (0.00449057 * charCount) + 46.35

    totalTextLen = 0
    for word in fmtWords:
        totalTextLen += word.actualLength
    averageCharLenPx = totalTextLen/charCount
    return optimalCharsPerLine * averageCharLenPx

def autoRescale(textBoxes, art, imgHeight=None):
    logStr = "Automatically rescaling text"
    if art is not None:
        logStr += " and art"
    Logging.subSection(logStr)
    textScaleHeight = max([textBox.height for textBox in textBoxes])

    if imgHeight is None:
        imgHeight = textScaleHeight if art is None else max(textScaleHeight, art.height)
        imgHeight = min(imgHeight, 3000)

    SPEC.text["base_font_height"]["value"] = int(
        SPEC.text["base_font_height"]["value"] * (imgHeight/textScaleHeight))
    fontTypes = ["font", "font_bold", "font_italic", "font_bolditalic"]
    for person, configs in FONTS.items():
        fonts = {fontName:font for (fontName, font) in configs.items()
                 if fontName in fontTypes}
        for font in fonts.values():
            font.rescale(imgHeight/textScaleHeight)

    # Must perform this rescale *after* fonts have been rescaled so that text lengths
    # are recalculated properly.
    for textBox in textBoxes:
        textBox.rescale(imgHeight/textScaleHeight)

    # After rescaling the text to be as close as possible to the target height, there
    # may still large gaps above and below the text since PIL only allows for whole
    # number font heights. If this is the case, scale the art down to fit to the text.
    imgHeight = max([textBox.height for textBox in textBoxes])
    SPEC.image["image_height"]["value"] = imgHeight

    if art is None:
        return None

    artScale = imgHeight / art.height
    resizedArt = art.resize((int(art.width * artScale), int(art.height * artScale)))
    return resizedArt

class TextBoxPos:
    LEFT = "left"
    RIGHT = "right"
    SPLIT = "split"

def generateCaption(textBoxes, textBoxPos, textAlignment, capCredits,
                    creditsPos, art, fileName, bgColor):
    if textBoxPos == TextBoxPos.SPLIT:
        assert len(textBoxes) == 2
        maxTextBoxWidth = max(textBoxes[0].width, textBoxes[1].width)
        dimensions = (art.width + (maxTextBoxWidth * 2), art.height)
    else:
        assert len(textBoxes) == 1
        textBox = textBoxes[0]
        dimensions = (art.width + textBox.width, art.height)

    fileFmt = SPEC.output["output_img_format"]["value"]
    colorMode = "RGBA" if fileFmt == "png" else "RGB"
    img = Image.new(colorMode, dimensions, bgColor)
    d = ImageDraw.Draw(img)

    if textBoxPos == TextBoxPos.LEFT:
        img.paste(art, (textBox.width, 0))
        textBox.drawText(d, textAlignment, startX=0,
                         startY=int((art.height - textBox.height)/2))
        drawCredits(d, capCredits, creditsPos, textBox.width, 0,
                    art.width, art.height)

    elif textBoxPos == TextBoxPos.RIGHT:
        img.paste(art, (0, 0))
        textBox.drawText(d, textAlignment, startX=art.width,
                         startY=int((art.height - textBox.height)/2))
        drawCredits(d, capCredits, creditsPos, 0, 0, art.width, art.height)

    elif textBoxPos == TextBoxPos.SPLIT:
        img.paste(art, (maxTextBoxWidth, 0))
        textBoxes[0].drawText(d, textAlignment,
                              startX=int((maxTextBoxWidth - textBoxes[0].width)/2),
                              startY=int((art.height - textBoxes[0].height)/2))
        textBoxes[1].drawText(d, textAlignment,
                              startX=maxTextBoxWidth + art.width +
                              int((maxTextBoxWidth - textBoxes[1].width)/2),
                              startY=int((art.height - textBoxes[1].height)/2))
        drawCredits(d, capCredits, creditsPos, maxTextBoxWidth, 0,
                    art.width, art.height)

    img.save(fileName, optimize=True, quality=SPEC.output["output_img_quality"]["value"])

def generateImages(textBoxes, art):
    Logging.header("Generating images")
    fileSizeTable = []

    # Collect global values to use as arguments for generating files
    textAlignment = SPEC.text["alignment"]["value"]
    textBoxPos = SPEC.text["text_box_pos"]["value"]
    capCredits = "\n".join(SPEC.text["credits"]["value"])
    creditsPos = SPEC.text["credits_pos"]["value"]

    matches = SPEC.rgbaRe.fullmatch(SPEC.image["bg_color"]["value"])
    bgColor = (int(matches[1], 16), int(matches[2], 16),
               int(matches[3], 16), int(matches[4], 16))

    outputs = SPEC.output["outputs"]["value"]
    imgQuality = SPEC.output["output_img_quality"]["value"]
    baseFilename = SPEC.output["base_filename"]["value"]
    directory = SPEC.output["output_directory"]["value"]
    if directory != "" and directory[-1] != "/" and directory[-1] != "\\":
        directory += "/"
    outputFmt = SPEC.output["output_img_format"]["value"]

    # Generate filled in TOML file
    specFilename = directory + baseFilename + "_autospec.toml"
    Logging.subSection(f"Generating filled-in specification '{specFilename}'")
    SPEC.outputFilledSpec(specFilename)
    fileSizeTable.append((specFilename, Logging.filesizeStr(specFilename), ""))

    # Generate caption
    if outputs in ["all", "caption"]:
        capFile = directory + baseFilename + "_cap." + outputFmt
        Logging.subSection(f"Generating caption '{capFile}'")
        generateCaption(textBoxes, textBoxPos, textAlignment,
                        capCredits, creditsPos, art, capFile, bgColor)
        fileSizeTable.append((capFile,
                              Logging.filesizeStr(capFile),
                              Logging.dimensionsStr(capFile)))
        if args.open_on_exit:
            imageViewerFromCommandLine = {'linux':'xdg-open',
                                          'win32':'explorer',
                                          'darwin':'open'}[sys.platform]
            subprocess.run([imageViewerFromCommandLine, os.path.abspath(capFile)])

    # Generate parts
    colorMode = "RGBA" if outputFmt == "png" else "RGB"
    if outputs in ["all", "parts"]:
        for i, box in enumerate(textBoxes):
            renderedTextFile = directory + baseFilename + f"_text{i}." + outputFmt
            Logging.subSection(f"Generating text-only image '{renderedTextFile}'")
            img = Image.new(colorMode, (box.width, box.height), bgColor)
            box.drawText(ImageDraw.Draw(img), textAlignment)
            img.save(renderedTextFile, optimize=True, quality=imgQuality)
            fileSizeTable.append((renderedTextFile,
                                  Logging.filesizeStr(renderedTextFile),
                                  Logging.dimensionsStr(renderedTextFile)))

        if outputs != "parts":
            artFile = directory + baseFilename + "_art." + outputFmt
            Logging.subSection(f"Generating rescaled art '{artFile}'")
            img = Image.new(colorMode, (art.width, art.height), bgColor)
            img.paste(art, (0, 0))
            img.save(artFile, optimize=True, quality=imgQuality)
            fileSizeTable.append((artFile,
                                  Logging.filesizeStr(artFile),
                                  Logging.dimensionsStr(artFile)))

        if capCredits == '':
            Logging.subSection("Successfully generated all images!", 1, "green")
            Logging.table(fileSizeTable)
            return

        creditsFile = directory + baseFilename + "_credits." + outputFmt
        Logging.subSection(f"Generating credits '{creditsFile}'")
        img = Image.new(colorMode, (art.width, art.height), bgColor)
        drawCredits(ImageDraw.Draw(img), capCredits, creditsPos, 0, 0,
                    art.width, art.height)
        img.save(creditsFile, optimize=True, quality=imgQuality)
        fileSizeTable.append((creditsFile,
                              Logging.filesizeStr(creditsFile),
                              Logging.dimensionsStr(creditsFile)))
    Logging.subSection("Successfully generated all images!", 1, "green")
    Logging.table(fileSizeTable)

def main():
    textInfoTable = []
    baseFontHeight = SPEC.text["base_font_height"]["value"]

    Logging.header(f"Reading and fitting text from '{SPEC.text['text']['value']}'")
    with open(SPEC.text["text"]["value"], "r",encoding="utf-8") as f:
        text = f.read()
    fmtWords = parse_text(text)
    textInfoTable.append(("Word Count", len(fmtWords)))

    textBoxPos = SPEC.text["text_box_pos"]["value"]
    if SPEC.text["text_width"]["default"]:
        baseTextWidth = autoWidth(baseFontHeight, fmtWords, textBoxPos)
        SPEC.text["text_width"]["value"] = round(baseTextWidth / baseFontHeight, 2)
    else:
        baseTextWidth = SPEC.text["text_width"]["value"] * baseFontHeight
    wrappedText = wrapRegions(fmtWords, baseTextWidth)
    textBoxes = [TextBox(wrappedText, baseFontHeight,
                 SPEC.text["line_spacing"]["value"] * baseFontHeight,
                 SPEC.text["padding"]["value"] * baseFontHeight)]

    artFilename = SPEC.image["art"]["value"]
    art = Image.open(artFilename) if artFilename is not None else None

    if textBoxPos == TextBoxPos.SPLIT:
        textBoxes = textBoxes[0].split()
        textInfoTable.append(("Line Count (left)", len(textBoxes[0].fmtLines)))
        textInfoTable.append(("Line Count (right)", len(textBoxes[1].fmtLines)))
    else:
        textInfoTable.append(("Line Count", len(textBoxes[0].fmtLines)))

    if not SPEC.text["base_font_height"]["default"]:
        baseImgHeight = max([textBox.height for textBox in textBoxes])
    elif not SPEC.image["image_height"]["default"]:
        baseImgHeight = SPEC.image["image_height"]["value"]
    else:
        baseImgHeight = None
    art = autoRescale(textBoxes, art, baseImgHeight)

    Logging.subSection("Successfully manipulated text!", 1, "green")
    Logging.table(textInfoTable)
    generateImages(textBoxes, art)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="CaptionGenerator",
        description="Generate a caption given a vaild .toml specification file",
        epilog="Have fun writing!")
    parser.add_argument("specification_file", help="The specification for your " \
                        "caption. See the GitHub page for a guide on how it must " \
                        "be formatted.")
    parser.add_argument("-o", "--open_on_exit", action="store_true", help="If a " \
                        "caption is generated, open it with your default image " \
                        "viewer.")
    args = parser.parse_args()

    colorama.init()
    START_TIME = time.time()
    try:
        SPEC = UserSpec(args.specification_file)
        FONTS = loadFonts(SPEC.characters, SPEC.text["base_font_height"]["value"])
        main()
        Logging.header(f"Program finished in {time.time()-START_TIME:.2f} seconds")
        Logging.divider()
    except UserError as e:
        Logging.divider()
        print(f"\nUserError: {e.message}")
