import pdb
import re

from PIL import Image, ImageDraw, ImageFont

PEOPLE = {
    "p2": {
        "relative_height" : 1,
        "color" : "#e2c9cc",
        "font": "fonts/Merriweather/Merriweather-Regular.ttf",
	"font_bold": "fonts/Merriweather/Merriweather-Bold.ttf",
	"font_italic": "fonts/Merriweather/Merriweather-Italic.ttf",
        "font_bolditalic": "fonts/Merriweather/Merriweather-BoldItalic.ttf"
    },
    "p1": {
        "relative_height" : 1.5,
        "color" : "#e4b59a",
        "font": "fonts/Chivo/Chivo-Regular.ttf",
	"font_bold": "fonts/Chivo/Chivo-Bold.ttf",
	"font_italic": "fonts/Chivo/Chivo-Italic.ttf",
        "font_bolditalic": "fonts/Chivo/Chivo-BoldItalic.ttf"
    },
    "p3": {
        "relative_height" : 1,
        "color" : "#ffffff",
        "font": "fonts/Titillium/TitilliumWeb-Regular.ttf",
	"font_bold": "fonts/Titillium/TitilliumWeb-Bold.ttf",
	"font_italic": "fonts/Titillium/TitilliumWeb-Italic.ttf",
        "font_bolditalic": "fonts/Titillium/TitilliumWeb-BoldItalic.ttf"
    },
    "emoji" : {
        "relative_height" : 1.5,
        "color" : "#e4b59a",
        "font": "fonts/NotoEmoji/NotoEmoji-Bold.ttf",
	"font_bold": "fonts/NotoEmoji/NotoEmoji-Bold.ttf",
	"font_italic": "fonts/NotoEmoji/NotoEmoji-Regular.ttf",
        "font_bolditalic": "fonts/NotoEmoji/NotoEmoji-Bold.ttf"
    }
}

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

class Font:
    pattern = re.compile("#([0-9A-F][0-9A-F])([0-9A-F][0-9A-F])([0-9A-F][0-9A-F])",
                         re.IGNORECASE)

    def __init__(self, path, height, color):
        self.font = ImageFont.truetype(path, height)
        self.height = height
        self.spaceLen = self.font.getlength(" ")
        matches = self.pattern.fullmatch(color)
        self.rgb = (int(matches[1], 16), int(matches[2], 16), int(matches[3], 16))

    def getLength(self, text):
        return self.font.getlength(text)

    def rescale(self, scale):
        self.height = int(self.height * scale)
        self.font = self.font.font_variant(size=self.height)

    def imgDrawKwargs(self):
        return {
            "font" : self.font,
            "fill" : self.rgb,
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
        self.renderLength = 0
        for unit in fmtUnits:
            self.actualLength += unit.length
            self.renderLength += unit.length

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
        self.renderLength *= scale
        for unit in self.fmtUnits:
            unit.rescale(scale)

    def drawWord(self, d, x, y):
        for unit in reversed(self.fmtUnits):
            unit.drawUnit(d, x, y)
            x -= unit.length

def loadFonts(people, baseHeight):
    for person, fonts in people.items():
        people[person]['height'] = \
            int(baseHeight * people[person]['relative_height'])
        for font in ["font", "font_bold", "font_italic", "font_bolditalic"]:
            people[person][font] = Font(
                people[person][font], people[person]['height'], people[person]['color'])

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
                self.font = PEOPLE[self.person]["font_bolditalic"]
            elif self.bold:
                self.font = PEOPLE[self.person]["font_bold"]
            elif self.italic:
                self.font = PEOPLE[self.person]["font_italic"]
            else:
                self.font = PEOPLE[self.person]["font"]

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
        assert person in PEOPLE
        specialChars["["]["people"].append(person)
        prevRBrace = rBrace

    specialChars["["]["end_indices"] = specialChars["]"]["indices"]
    del specialChars["]"]

    # Block out contiguous regions of text with unique formatting. Prune whitespace
    # immediately after character specifier.
    fmtState = FmtState("arial.ttf", False, False, "p1")
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
            x += word.renderLength
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
            currLine.length = fmtWord.renderLength
            continue

        prevWordSpaceLen = fmtWords[i-1].fmtUnits[-1].font.spaceLen
        currWordSpaceLen = fmtWord.fmtUnits[-1].font.spaceLen
        fmtWord.renderLength += max(prevWordSpaceLen, currWordSpaceLen)

        newLen = fmtWord.renderLength + currLine.length
        if newLen > width:
            formattedLines.append(currLine)
            fmtWord.renderLength = fmtWord.actualLength
            currLine = FormattedLine(fmtWord.renderLength, [fmtWord])
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
        LEFT = 0
        RIGHT = 1
        CENTER = 2

    def __init__(self, fmtLines, baseHeight, lineSpacing=None, padding=None):
        self.fmtLines = fmtLines
        self.baseHeight = baseHeight
        self.lineSpacing = int(baseHeight * 0.34) if lineSpacing is None else lineSpacing
        self.padding = baseHeight if padding is None else padding

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

    def drawText(self, img, alignment, startX=0, startY=0):
        d = ImageDraw.Draw(img)

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
        # TODO: Add some "sane" scaling. If there's not a lot of text, don't make it
        # giant. If the image is giant, scale it down.
        imgHeight = max(textScaleHeight, art.height)

    for textBox in textBoxes:
        textBox.rescale(imgHeight/textScaleHeight)

    fontTypes = ["font", "font_bold", "font_italic", "font_bolditalic"]
    for person, configs in PEOPLE.items():
        fonts = {fontName:font for (fontName, font) in configs.items()
                 if fontName in fontTypes}
        for font in fonts.values():
            font.rescale(imgHeight/textScaleHeight)

    artScale = imgHeight / art.height
    resizedArt = art.resize((int(art.width * artScale), int(art.height * artScale)))
    return resizedArt

class TextBoxPos:
    LEFT = 0
    RIGHT = 1
    SPLIT = 2

def generateCaption(textBoxes, art, fileName, textBoxPos):
    if textBoxPos == TextBoxPos.SPLIT:
        assert len(textBoxes) == 2
        maxTextBoxWidth = max(textBoxes[0].width, textBoxes[1].width)
        dimensions = (art.width + (maxTextBoxWidth * 2), art.height)
    else:
        assert len(textBoxes) == 1
        textBox = textBoxes[0]
        dimensions = (art.width + textBox.width, art.height)

    img = Image.new("RGB", dimensions, (35, 34, 52))

    if textBoxPos == TextBoxPos.LEFT:
        img.paste(art, (textBox.width, 0))
        textBox.drawText(img, TextBox.Align.CENTER, startX=0,
                         startY=int((art.height - textBox.height)/2))

    elif textBoxPos == TextBoxPos.RIGHT:
        img.paste(art, (0, 0))
        textBox.drawText(img, TextBox.Align.CENTER, startX=art.width,
                         startY=int((art.height - textBox.height)/2))

    elif textBoxPos == TextBoxPos.SPLIT:
        img.paste(art, (maxTextBoxWidth, 0))
        textBoxes[0].drawText(img, TextBox.Align.CENTER,
                              startX=int((maxTextBoxWidth - textBoxes[0].width)/2),
                              startY=int((art.height - textBoxes[0].height)/2))
        textBoxes[1].drawText(img, TextBox.Align.CENTER,
                              startX=maxTextBoxWidth + art.width +
                              int((maxTextBoxWidth - textBoxes[1].width)/2),
                              startY=int((art.height - textBoxes[1].height)/2))

    img.save(fileName)

def main():
    baseHeight = 24
    textBoxPos = TextBoxPos.SPLIT

    with open("capfmt.txt","r",encoding="utf-8") as f:
        text = f.read()

    loadFonts(PEOPLE, baseHeight)
    fmtWords = parse_text(text)
    baseTextWidth = autoWidth(baseHeight, fmtWords, textBoxPos)
    textBoxes = [TextBox(wrapRegions(fmtWords, baseTextWidth), baseHeight)]

    art = Image.open("9104645.jpg")

    if textBoxPos is TextBoxPos.SPLIT:
        textBoxes = textBoxes[0].split()

    art = autoRescale(textBoxes, art)
    generateCaption(textBoxes, art, "caption.png", textBoxPos)

if __name__ == "__main__":
    main()
