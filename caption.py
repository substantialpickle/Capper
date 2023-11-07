from PIL import Image, ImageDraw, ImageFont
from matplotlib import font_manager
import pdb

PEOPLE = {
    "p1": {
        "font": "fonts/Merriweather/Merriweather-Regular.ttf",
	"font_bold": "fonts/Merriweather/Merriweather-Bold.ttf",
	"font_italic": "fonts/Merriweather/Merriweather-Italic.ttf",
        "font_bolditalic": "fonts/Merriweather/Merriweather-BoldItalic.ttf"
    },
    "p2": {
        "font": "fonts/Chivo/Chivo-Regular.ttf",
	"font_bold": "fonts/Chivo/Chivo-Bold.ttf",
	"font_italic": "fonts/Chivo/Chivo-Italic.ttf",
        "font_bolditalic": "fonts/Chivo/Chivo-BoldItalic.ttf"
    }
}

# Debug printers
def printFormatUnits(regions):
    for i, region in enumerate(regions):
        fmtStr = region.txt.replace("\n", "\\n")
        print(f"{i:03d} : {fmtStr}")

def printFormattedLines(fmtLines):
    for i, line in enumerate(fmtLines):
        computedSum = 0
        for unit in line.fmtUnits:
            computedSum += unit.length
        print(f"{i:03} | actual: {line.length:8.2f} | computed: {computedSum:8.2f} | ", end="")
        for unit in line.fmtUnits:
            fmtStr = unit.txt.replace("\n", "\\n")
            fmtStr = fmtStr.replace(" ", "|")
            print(fmtStr, end="")
        print()

class FmtUnit:
    def __init__(self, txt, font):
        self.txt = txt
        self.font = font
        self.length = 0

def loadFonts(people, height):
    for person, fonts in people.items():
        for font in fonts:
            people[person][font] = ImageFont.truetype(people[person][font], height)

def parse_text(text):
    font = "arial.ttf"
    style = ""
    curUnit = ""
    units = []

    class FmtState:
        def __init__(self, font, bold, italic, person ):
            self.font = font
            self.bold = bold
            self.italic = italic
            self.person = person
            self.startIndx = 0

        def updateState(self, currChar, currIndx, specialColl, text, regions):
            if currChar == "[":
                self.updatePerson(specialColl["["], text)
            elif currChar == "*":
                self.toggleBold(currIndx)
            elif currChar == "_":
                self.toggleItalic(currIndx)
            elif currChar == "\n":
                self.updateNewline(regions, currIndx)
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

        def updateNewline(self, regions, currIndx):
            regions.append(FmtUnit("\n", self.font))
            self.startIndx = currIndx + 1

        def updateSpace(self, currIndx):
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

    lastCharSlash = False
    # Collect all braces/asterisks/underscores. Prune out the markers preceded by a '\'
    for i, char in enumerate(text):
        if char in specialChars and not lastCharSlash:
            specialChars[char]["indices"].append(i)
        else:
            lastCharSlash = (char == "\\")

    # Assert that people specifers are valid and collect people
    bracePairs = [pair for pair in zip(specialChars["["]["indices"], specialChars["]"]["indices"])]
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
    regions = []
    fmtState = FmtState("arial.ttf", False, False, "p1")
    while True:
        endIndx = 10000000 # do int max or something
        empty = 0
        for char in specialChars:
            if not specialChars[char]["indices"]:
                empty += 1
            if specialChars[char]["indices"] and \
               specialChars[char]["indices"][0] < endIndx:
                nxtSpecialChar = char
                endIndx = specialChars[char]["indices"][0]
        if empty == len(specialChars):
            break

        specialChars[nxtSpecialChar]["indices"].pop(0)

        currRegionText = text[fmtState.startIndx : endIndx]
        if currRegionText != "":
            regions.append(FmtUnit(currRegionText, fmtState.font))

        fmtState.updateState(
            nxtSpecialChar, endIndx, specialChars, text, regions)

    currRegionText = text[fmtState.startIndx:]
    if currRegionText != "":
        regions.append(FmtUnit(currRegionText, fmtState.font))

    return regions

class FormattedLine:
    def __init__(self, length, fmtUnits):
        self.length = length
        self.fmtUnits = fmtUnits

def wrapRegions(fmtWords, width, height):
    # TODO: Error if we're building a new line, and it's impossible to fit it into the current
    # line length
    formattedLines = []
    currLine = FormattedLine(0, [])
    print()
    punctuation = set(".!,?\"")
    for j, fmtWord in enumerate(fmtWords):
        if fmtWord.txt == "\n":
            formattedLines.append(currLine)
            currLine = FormattedLine(0, [])
            continue

        if currLine.length == 0:
            currLine.fmtUnits.append(fmtWord)
            fmtWord.length = fmtWord.font.getlength(fmtWord.txt)
            currLine.length = fmtWord.length
            continue

        isPunctuation = set(fmtWord.txt) <= punctuation
        newTxt = fmtWord.txt if isPunctuation else (" " + fmtWord.txt)
        fmtWord.length = fmtWord.font.getlength(newTxt)
        newLen = fmtWord.length + currLine.length
        if newLen > width:
            if isPunctuation:
                lastWord = currLine.fmtUnits.pop()
                lastWord.txt = lastWord.txt.strip()
                lastWord.length = lastWord.font.getlength(lastWord.txt)
                currLine.length -= lastWord.length
                formattedLines.append(currLine)
                currLine = FormattedLine(lastWord.length + fmtWord.length, [lastWord, fmtWord])

            else:
                fmtWord.length = fmtWord.font.getlength(fmtWord.txt)
                formattedLines.append(currLine)
                currLine = FormattedLine(fmtWord.length, [fmtWord])

            continue

        fmtWord.txt = newTxt
        currLine.fmtUnits.append(fmtWord)
        currLine.length = newLen

    return formattedLines

def getTextInfo(fmtLines, lineHeight, spacing=None):
    spacing = int(lineHeight * 0.34) if spacing is None else spacing
    pad = int(lineHeight * 0.5)
    maxLineLen = max([line.length for line in fmtLines])
    ceil = lambda i : int(i) if int(i) == i else int(i + 1)
    textImgWidth = ceil(maxLineLen + (pad * 2))
    textImgHeight = ceil((lineHeight + spacing) * len(fmtLines) + (pad * 2))
    return (pad, maxLineLen, textImgWidth, textImgHeight, spacing)

def getTextImgWidthHeight(fmtLines, lineHeight, spacing=None):
    (_, _, textImgWidth, textImgHeight, _) = getTextInfo(fmtLines, lineHeight, spacing=None)
    return (textImgWidth, textImgHeight)

def writeText(fmtLines, textHeight):
    (pad, maxLineLen, textImgWidth, textImgHeight, spacing) = getTextInfo(fmtLines, lineHeight)
    center = True

    img = Image.new("RGB", (textImgWidth, textImgHeight), "grey")
    d = ImageDraw.Draw(img)

    (x, y) = (pad, (textHeight + pad) - int(0.12 * textHeight))
    for fmtLine in fmtLines:
        if center:
            x += int((maxLineLen - fmtLine.length)/2)
        for fmtUnit in fmtLine.fmtUnits:
            d.text((x, y), fmtUnit.txt, font=fmtUnit.font, anchor="ls")
            x += fmtUnit.length
        (x, y) = (pad, y + textHeight + spacing)

    img.save("real.png")
    return

def autoWidth(textHeight=24):
    # TODO: Determine optimal text width/height ratio based on heuristics that look
    # at character count.
    optimalWidthHeightRatio = 40
    textWidth = textHeight * optimalWidthHeightRatio
    return textWidth

def autoRescale(fmtLines, textImgHeight, lineHeight, art, imgHeight=None):
    if imgHeight is None:
        # TODO: Add some "sane" scaling. If there's not a lot of text, don't make it
        # giant. If the image is giant, scale it down.
        imgHeight = textImageHeight if textImgHeight > art.height else art.height

    scale = imgHeight / textImgHeight
    lineHeight = int(lineHeight * scale)

    currFonts = {fmtUnit.font:None for fmtLine in fmtLines for fmtUnit in fmtLine.fmtUnits}
    for font in currFonts:
        currFonts[font] = font.font_variant(size=lineHeight)

    for fmtLine in fmtLines:
        fmtLine.length *= scale
        for fmtUnit in fmtLine.fmtUnits:
            fmtUnit.font = currFonts[fmtUnit.font]
            fmtUnit.length *= scale

    artScale = imgHeight / art.height
    resizedArt = art.resize((int(art.width * artScale), int(art.height * artScale)))
    return lineHeight, resizedArt

if __name__ == "__main__":
    lineHeight = 24
    textWidth = autoWidth(lineHeight)
    with open("capfmt.txt","r") as f:
        text = f.read()

    loadFonts(PEOPLE, lineHeight)
    fmtWords = parse_text(text)
    fmtLines = wrapRegions(fmtWords, textWidth, lineHeight)

    art = Image.open("7625657.png")
    (_, textImgHeight) = getTextImgWidthHeight(fmtLines, lineHeight)

    # NOTE: textWidth gets outdated here
    (lineHeight, art) = autoRescale(fmtLines, textImgHeight, lineHeight, art)
    writeText(fmtLines, lineHeight)
