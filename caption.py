from functools import partial
import toml
from numbers import Number
from pathlib import Path
import pdb
import re
import sys

from PIL import Image, ImageDraw, ImageFont

ceil = lambda i : int(i) if int(i) == i else int(i + 1)

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

class UserSpec:
    rgbaRe = re.compile("#([0-9A-F][0-9A-F])([0-9A-F][0-9A-F])"
                        "([0-9A-F][0-9A-F])([0-9A-F][0-9A-F])",
                         re.IGNORECASE)
    rgbRe = re.compile("#([0-9A-F][0-9A-F])([0-9A-F][0-9A-F])([0-9A-F][0-9A-F])",
                         re.IGNORECASE)

    def __init__(self, fileName):
        def checkKeys(actualKeys, validKeys, requiredKeys, internalColl={}):
            for actualKey in actualKeys:
                assert actualKey in validKeys, \
                    f"Unexpected option '{actualKey}', expected one of '{validKeys}'"
                internalColl[actualKey] = {}
                internalColl[actualKey]["default"] = False
                # Will be set to an actual value in a "validate*()" functions
                internalColl[actualKey]["value"] = None
            for requiredKey in requiredKeys:
                assert requiredKey in actualKeys, \
                    f"Required option '{requiredKey}' not included"
            for defaultKey in (validKeys - internalColl.keys()):
                internalColl[defaultKey] = {}
                internalColl[defaultKey]["default"] = True
                # Will be set to an actual value in a "validate*()" function, or at a
                # later stage in the program after the text has been parsed.
                internalColl[defaultKey]["value"] = None

        assert Path(fileName).is_file(), f"File '{fileName}' does not exist"
        with open(fileName, "r", encoding="utf-8") as f:
            spec = toml.load(f)

        topLevelKeys = ["image", "text", "output", "characters"]
        checkKeys(spec.keys(), topLevelKeys, topLevelKeys)

        self.image = {}
        self.imageValidKeys = ["art", "image_height", "bg_color"]
        imageRequiredKeys = ["bg_color"]
        checkKeys(spec["image"], self.imageValidKeys, imageRequiredKeys, self.image)
        self.validateAndSetImage(spec["image"])

        self.text = {}
        self.textValidKeys = ["text", "base_font_height", "padding", "line_spacing",
                              "text_width", "text_box_pos", "alignment", "credits",
                              "credits_pos"]
        textRequiredKeys = ["text", "text_box_pos"]
        checkKeys(spec["text"], self.textValidKeys, textRequiredKeys, self.text)
        self.validateAndSetText(spec["text"])

        self.output = {}
        self.outputValidKeys = ["outputs", "output_directory", "output_img_format",
                                "output_img_quality", "base_filename"]
        outputRequiredKeys = ["base_filename"]
        checkKeys(spec["output"], self.outputValidKeys, outputRequiredKeys, self.output)
        self.validateAndSetOutput(spec["output"])

        self.characters = []
        self.characterValidKeys = ["name", "color", "relative_height", "font",
                                   "font_bold", "font_italic", "font_bolditalic"]
        characterRequiredKeys = ["name", "color", "font"]
        assert len(spec["characters"]) > 0, "Must specify at least one character"
        for i, character in enumerate(spec["characters"]):
            currChar = {}
            checkKeys(character, self.characterValidKeys, characterRequiredKeys, currChar)
            self.validateAndSetChar(character, currChar)
            self.characters.append(currChar)

        imgHeightGiven = not self.image["image_height"]["default"]
        txtHeightGiven = not self.text["base_font_height"]["default"]
        assert not (imgHeightGiven and txtHeightGiven), \
            f"Cannot specify image_height and base_font_height together"

        characterNames = [char["name"]["value"] for char in self.characters]
        for name in list(characterNames):
            characterNames.pop(0)
            assert name not in characterNames, "Found multiple characters named " \
                f"'{name}', cannot use the same name for multiple characters"

        artNotGiven = self.image["art"]["default"]
        if artNotGiven:
            outputs = self.output["outputs"]["value"]
            assert outputs == "parts", "Cannot generate caption without art. " \
                "Either specify 'art' under [image], or set 'outputs' to something " \
                "other than 'parts' under [output]"

    @staticmethod
    def checkFileRe(coll, key):
        fileName = coll[key]
        assert Path(fileName).is_file(), f"File '{fileName}' does not exist"
        return fileName

    @staticmethod
    def checkTypeAndMinValRe(expType, minVal, cond, coll, key):
        value = coll[key]
        assert isinstance(value, expType), \
            f"Expected {key} to be {expType}, got {type(value)}"

        assert cond in ["gt", "gte"]
        if cond == "gt":
            assert value > minVal, f"{key} must be greater than {minVal}, got {value}"
        elif cond == "gte":
            assert value >= minVal, \
                f"{key} must be greater than or equal to {minVal}, got {value}"
        return value

    @staticmethod
    def checkColor(coll, key):
        value = coll[key]
        if UserSpec.rgbaRe.fullmatch(value):
            pass
        elif UserSpec.rgbRe.fullmatch(value):
            value += "FF"
        else:
            assert False, f"Invalid hex color {value}"
        return value

    @staticmethod
    def valueInListRe(expList, coll, key):
        value = coll[key]
        assert value in expList, \
            f"Invalid {key}, expected one of {expList}, got {value}"
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
                "check" : UserSpec.checkFileRe
            },
            "image_height" : {
                "check" : partial(UserSpec.checkTypeAndMinValRe, int, 0, "gt")
            },
            "bg_color" : {
                "check" : UserSpec.checkColor
            }
        }
        UserSpec.validateAndFillSpec(inImage, self.image, checkImage)

    def validateAndSetText(self, inText):
        def checkCredits(coll, key):
            capCredits = coll[key]
            assert isinstance(capCredits, list), \
                f"Expected {capCredits} to be {list}, got {type(capCredits)}"
            for line in capCredits:
                assert isinstance(line, str), \
                    f"Expected line '{line}' to be {str}, got {type(line)}"
            return capCredits

        checkText = {
            "text" : {
                "check" : UserSpec.checkFileRe
            },
            "base_font_height" : {
                "check" : partial(UserSpec.checkTypeAndMinValRe, int, 0, "gt"),
                "default" : 16
            },
            "padding" : {
                "check" : partial(UserSpec.checkTypeAndMinValRe, Number, 0, "gte"),
                "default" : 1
            },
            "line_spacing" : {
                "check" : partial(UserSpec.checkTypeAndMinValRe, Number, 0, "gte"),
                "default" : 0.2
            },
            "text_width" : {
                "check" : partial(UserSpec.checkTypeAndMinValRe, Number, 0, "gt"),
            },
            "text_box_pos" : {
                "check" : partial(UserSpec.valueInListRe, ["left", "right", "split"])
            },
            "alignment" : {
                "check" : partial(UserSpec.valueInListRe, ["left", "right", "center"]),
                "default" : "center"
            },
            "credits" : {
                "check" : checkCredits,
                "default" : []
            },
            "credits_pos" : {
                "check" : partial(UserSpec.valueInListRe, ["tl", "tr", "bl", "br"]),
                "default" : "tl"
            }
        }
        UserSpec.validateAndFillSpec(inText, self.text, checkText)

    def validateAndSetOutput(self, inOutput):
        def valueIsIntInRange(minVal, maxVal, coll, key):
            value = coll[key]
            assert isinstance(value, int), \
                f"Expected {key} to be {int}, got {type(value)}"
            assert minVal <= value <= maxVal, \
                f"{key} not in range [{minVal}, {maxVal}]"
            return value

        def checkDirectory(coll, key):
            directory = coll[key]
            assert Path(directory).is_dir(), \
                f"Directory '{directory}' does not exist"
            return directory

        checkOutput = {
            "outputs" : {
                "check" : partial(UserSpec.valueInListRe, ["caption", "parts", "all"]),
                "default" : "caption"
            },
            "output_directory" : {
                "check" : checkDirectory,
                "default" : ""
            },
            "output_img_format" : {
                "check" : partial(UserSpec.valueInListRe, ["png", "jpg", "jpeg"]),
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
                assert char not in name, \
                    f"Special character '{char}' not allowed in name '{name}'"
            return name

        checkChar = {
            "name" : {
                "check" : verifyNoSpecialChars
            },
            "relative_height" : {
                "check" : partial(UserSpec.checkTypeAndMinValRe, Number, 0, "gt"),
                "default" : 1
            },
            "color" : {
                "check" : UserSpec.checkColor
            },
            "font" : {
                "check" : UserSpec.checkFileRe
            },
            "font_bold" : {
                "check" : UserSpec.checkFileRe,
                "default" : inChar["font"]
            },
            "font_italic" : {
                "check" : UserSpec.checkFileRe,
                "default" : inChar["font"]
            },
            "font_bolditalic" : {
                "check" : UserSpec.checkFileRe,
                "default" : inChar["font"]
            }
        }
        UserSpec.validateAndFillSpec(inChar, storedChar, checkChar)

    def outputFilledSpec(self):
        specFilename = (self.output["output_directory"]["value"] + "/" +
                        self.output["base_filename"]["value"] + "_spec.toml")
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
    def __init__(self, path, height, color):
        self.font = ImageFont.truetype(path, height)
        self.height = height
        self.spaceLen = self.font.getlength(" ")
        matches = UserSpec.rgbaRe.fullmatch(color)
        self.rgba = (int(matches[1], 16), int(matches[2], 16),
                    int(matches[3], 16), int(matches[4], 16))

    def getLength(self, text):
        return self.font.getlength(text)

    def rescale(self, scale):
        self.height = int(self.height * scale)
        self.font = self.font.font_variant(size=self.height)

    def imgDrawKwargs(self):
        return {
            "font" : self.font,
            "fill" : self.rgba,
        }

class FmtUnit:
    def __init__(self, txt, fmtState):
        self.txt = txt
        self.font = fmtState.font
        self.length = self.font.getLength(txt)

    def rescale(self, scale):
        self.length *= scale

    def drawUnit(self, d, x, y):
        d.text((x, y), self.txt, anchor="rs", **self.font.imgDrawKwargs())

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

    def rescale(self, scale):
        self._maxHeight = int(self._maxHeight * scale)
        self.actualLength *= scale
        self.spaceLength *= scale
        for unit in self.fmtUnits:
            unit.rescale(scale)

    def drawWord(self, d, x, y):
        for unit in reversed(self.fmtUnits):
            unit.drawUnit(d, x, y)
            x -= unit.length

def loadFonts(charSpecs, baseHeight):
    fonts = {}
    for charSpec in charSpecs:
        charFonts = {}
        for font in ["font", "font_bold", "font_italic", "font_bolditalic"]:
            height = int(baseHeight * charSpec["relative_height"]["value"])
            if height < 1:
                height = 1
            charFonts[font] = Font(
                charSpec[font]["value"], height, charSpec["color"]["value"])
        fonts[charSpec["name"]["value"]] = charFonts
    return fonts

def parse_text(text):
    font = "arial.ttf"
    style = ""
    curUnit = ""
    units = []

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
    bracePairs = [pair for pair in zip(specialChars["["]["indices"],
                                       specialChars["]"]["indices"])]
    assert len(bracePairs) == len(specialChars["["]["indices"])  # Prevents "[]["
    assert len(bracePairs) == len(specialChars["]"]["indices"])  # Prevents "[]]"
    prevRBrace = -1
    for lBrace, rBrace in bracePairs:
        assert lBrace > prevRBrace  # Prevents "[[]]"
        assert lBrace < rBrace      # Prevents "]["

        person = text[lBrace+1:rBrace]
        assert person in FONTS, f"Unexpected character '{person}' in text file"
        specialChars["["]["people"].append(person)
        prevRBrace = rBrace

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
            fmtState.fmtUnits.append(FmtUnit(currRegionText, fmtState))

        fmtState.updateState(
            nxtSpecialChar, endIndx, specialChars, text)

    currRegionText = text[fmtState.startIndx:]
    if currRegionText != "":
        fmtState.fmtUnits.append(FmtUnit(currRegionText, fmtState))
        fmtState.fmtWords.append(FmtWord(fmtState.fmtUnits))

    return fmtState.fmtWords

class FormattedLine:
    def __init__(self, length, fmtWords, maxHeight=0):
        self.length = length
        self.fmtWords = fmtWords
        self.maxHeight = maxHeight

    def rescale(self, scale):
        self.length *= scale
        self.maxHeight = int(self.maxHeight * scale)
        for word in self.fmtWords:
            word.rescale(scale)

    def drawLine(self, d, x, y):
        for word in self.fmtWords:
            x += word.actualLength + word.spaceLength
            word.drawWord(d, x, y)

    def isNewline(self):
        return not self.fmtWords

def wrapRegions(fmtWords, width):
    # TODO: Error if we're building a new line, and it's impossible to fit it into the current
    # line length
    formattedLines = []
    currLine = FormattedLine(0, [])
    for i, fmtWord in enumerate(fmtWords):
        if fmtWord.isNewline():
            formattedLines.append(currLine)
            currLine = FormattedLine(0, [], fmtWord.maxHeight())
            continue

        if currLine.length == 0:
            currLine.fmtWords.append(fmtWord)
            currLine.length = fmtWord.actualLength
            continue

        prevWordSpaceLen = fmtWords[i-1].fmtUnits[-1].font.spaceLen
        currWordSpaceLen = fmtWord.fmtUnits[-1].font.spaceLen
        fmtWord.spaceLength = min(prevWordSpaceLen, currWordSpaceLen)

        newLen = fmtWord.actualLength + fmtWord.spaceLength + currLine.length
        if newLen > width:
            formattedLines.append(currLine)
            fmtWord.spaceLen = 0
            currLine = FormattedLine(fmtWord.actualLength, [fmtWord])
            continue

        currLine.fmtWords.append(fmtWord)
        currLine.length = newLen

    if currLine.fmtWords:
        formattedLines.append(currLine)

    for line in formattedLines:
        if not line.fmtWords:
            continue
        line.maxHeight = max([word.maxHeight() for word in line.fmtWords])

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

        self.maxLineLen = int(self.maxLineLen * scale)
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
                x += int((self.maxLineLen - fmtLine.length)/2)
            elif alignment == self.Align.RIGHT:
                x += int(self.maxLineLen - fmtLine.length)

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
    textScaleHeight = max([textBox.height for textBox in textBoxes])

    if imgHeight is None:
        imgHeight = textScaleHeight if art is None else max(textScaleHeight, art.height)
        imgHeight = 3000 if imgHeight > 3000 else imgHeight

    for textBox in textBoxes:
        textBox.rescale(imgHeight/textScaleHeight)

    SPEC.text["base_font_height"]["value"] = int(
        SPEC.text["base_font_height"]["value"] * (imgHeight/textScaleHeight))
    fontTypes = ["font", "font_bold", "font_italic", "font_bolditalic"]
    for person, configs in FONTS.items():
        fonts = {fontName:font for (fontName, font) in configs.items()
                 if fontName in fontTypes}
        for font in fonts.values():
            font.rescale(imgHeight/textScaleHeight)

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
    textAlignment = SPEC.text["alignment"]["value"]
    textBoxPos = SPEC.text["text_box_pos"]["value"]
    capCredits = "\n".join(SPEC.text["credits"]["value"])
    creditsPos = SPEC.text["credits_pos"]["value"]

    matches = SPEC.rgbaRe.fullmatch(SPEC.image["bg_color"]["value"])
    bgColor = (int(matches[1], 16), int(matches[2], 16),
               int(matches[3], 16), int(matches[4], 16))

    imgQuality = SPEC.output["output_img_quality"]["value"]
    baseFilename = SPEC.output["base_filename"]["value"]
    # TODO: Will "/" cause Windows problems...? (probably)
    directory = SPEC.output["output_directory"]["value"] + "/"
    outputFmt = SPEC.output["output_img_format"]["value"]

    SPEC.outputFilledSpec()

    if SPEC.output["outputs"]["value"] in ["all", "caption"]:
        capFile = directory + baseFilename + "_cap." + outputFmt
        generateCaption(textBoxes, textBoxPos, textAlignment,
                        capCredits, creditsPos, art, capFile, bgColor)

    colorMode = "RGBA" if outputFmt == "png" else "RGB"
    if SPEC.output["outputs"]["value"] in ["all", "parts"]:
        for i, box in enumerate(textBoxes):
            renderedTextFile = directory + baseFilename + f"_text{i}." + outputFmt
            img = Image.new(colorMode, (box.width, box.height), bgColor)
            box.drawText(ImageDraw.Draw(img), textAlignment)
            img.save(renderedTextFile, optimize=True, quality=imgQuality)

        artFile = directory + baseFilename + "_art." + outputFmt
        img = Image.new(colorMode, (art.width, art.height), bgColor)
        img.paste(art, (0, 0))
        img.save(artFile, optimize=True, quality=imgQuality)

        if SPEC.text["credits"]["value"] == []:
            return

        creditsFile = directory + baseFilename + "_credits." + outputFmt
        img = Image.new(colorMode, (art.width, art.height), bgColor)
        drawCredits(ImageDraw.Draw(img), capCredits, creditsPos, 0, 0,
                    art.width, art.height)
        img.save(creditsFile, optimize=True, quality=imgQuality)

def main():
    baseFontHeight = SPEC.text["base_font_height"]["value"]

    with open(SPEC.text["text"]["value"],"r",encoding="utf-8") as f:
        text = f.read()
    fmtWords = parse_text(text)

    textBoxPos = SPEC.text["text_box_pos"]["value"]
    if SPEC.text["text_width"]["default"]:
        baseTextWidth = autoWidth(baseFontHeight, fmtWords, textBoxPos)
        SPEC.text["text_width"]["value"] = round(baseTextWidth / baseFontHeight, 2)
    else:
        baseTextWidth = SPEC.text["text_width"]["value"] * baseFontHeight
    textBoxes = [TextBox(wrapRegions(fmtWords, baseTextWidth), baseFontHeight,
                         SPEC.text["line_spacing"]["value"] * baseFontHeight,
                         SPEC.text["padding"]["value"] * baseFontHeight)]

    artFilename = SPEC.image["art"]["value"]
    art = Image.open(artFilename) if artFilename is not None else None

    if textBoxPos == TextBoxPos.SPLIT:
        textBoxes = textBoxes[0].split()

    if not SPEC.text["base_font_height"]["default"]:
        baseImgHeight = max([textBox.height for textBox in textBoxes])
    elif not SPEC.image["image_height"]["default"]:
        baseImgHeight = SPEC.image["image_height"]["value"]
    else:
        baseImgHeight = None
    art = autoRescale(textBoxes, art, baseImgHeight)

    generateImages(textBoxes, art)

if __name__ == "__main__":
    assert len(sys.argv) == 2, "Must specify exactly one parameter: the specification " \
        "file for your caption"
    SPEC = UserSpec(sys.argv[1])
    FONTS = loadFonts(SPEC.characters, SPEC.text["base_font_height"]["value"])
    main()
