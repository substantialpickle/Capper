from math import ceil

from pretty_logging import Logging, UserError

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

def parseText(text, fonts, firstChar):
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
                self.font = fonts[self.person]["font_bolditalic"]
            elif self.bold:
                self.font = fonts[self.person]["font_bold"]
            elif self.italic:
                self.font = fonts[self.person]["font_italic"]
            else:
                self.font = fonts[self.person]["font"]

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
        list(fonts.keys()))

    specialChars["["]["end_indices"] = specialChars["]"]["indices"]
    del specialChars["]"]

    # Block out contiguous regions of text with unique formatting. Prune whitespace
    # immediately after character specifier.
    fmtState = FmtState(fonts[firstChar]["font"], False, False, firstChar)
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
