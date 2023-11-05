from PIL import Image, ImageDraw, ImageFont
from matplotlib import font_manager
import pdb

people = {
    "p1": {
        "font": "fonts/Merriweather/Merriweather-Regular.ttf",
	"font_bold": "fonts/Merriweather/Merriweather-Bold.ttf",
	"font_italic": "fonts/Merriweather/Merriweather-Italic.ttf"
    },
    "p2": {
        "font": "fonts/Playpen_Sans/PlaypenSans-Regular.ttf",
	"font_bold": "fonts/Playpen_Sans/PlaypenSans-Bold.ttf",
	"font_italic": "fonts/Playpen_Sans/PlaypenSans-Thin.ttf"
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

        def updatePerson(self, person):
            self.person = person
            if self.bold and self.italic:
                self.font = people[self.person]["font"] # Add bold+italic attr later
            elif self.bold:
                self.font = people[self.person]["font_bold"]
            elif self.italic:
                self.font = people[self.person]["font_italic"]
            else:
                self.font = people[self.person]["font"]

        def toggleBold(self):
            # Add bold + italic later
            self.bold = not self.bold
            if self.bold:
                self.font = people[self.person]["font_bold"]
            else:
                self.font = people[self.person]["font"]

        def toggleItalic(self):
            # Add bold + italic later
            self.italic = not self.italic
            if self.italic:
                self.font = people[self.person]["font_italic"]
            else:
                self.font = people[self.person]["font"]

    def braceUpdate(state, indx, specialColl, text, regions):
        i = specialColl["["]["end_indices"].pop(0) + 1
        for char in text[i:]:
            if char == " " or char == "\n":
                i += 1
            else:
                break
        state.startIndx = i
        state.updatePerson(specialColl["["]["people"].pop(0))

    def boldUpdate(state, indx, specialColl, text, regions):
        state.startIndx = indx + 1
        state.toggleBold()

    def italicUpdate(state, indx, specialColl, text, regions):
        state.startIndx = indx + 1
        state.toggleItalic()

    def newlineUpdate(state, indx, specialColl, text, regions):
        regions.append(FmtUnit("\n", state.font))
        state.startIndx = indx + 1

    def spaceUpdate(state, indx, specialColl, text, regions):
        state.startIndx = indx + 1

    specialChars = {
        "[" : {
            "indices" : [],
            "end_indices": [],
            "people" : [],
            "state_update" : braceUpdate
        },
        "]" : {
            "indices" : [],
        },
        "*" : {
            "indices" : [],
            "state_update" : boldUpdate
        },
        "_" : {
            "indices" : [],
            "state_update" : italicUpdate
        },
        "\n" : {
            "indices" : [],
            "state_update" : newlineUpdate
        },
        " " : {
            "indices" : [],
            "state_update" : spaceUpdate
        }
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
        assert person in people
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

        specialChars[nxtSpecialChar]["state_update"](
            fmtState, endIndx, specialChars, text, regions)

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
    punctuation = set(".!,?")
    for j, fmtWord in enumerate(fmtWords):
        if fmtWord.txt == "\n":
            formattedLines.append(currLine)
            currLine = FormattedLine(0, [])
            continue

        font = ImageFont.truetype(fmtWord.font, height)
        if currLine.length == 0:
            currLine.fmtUnits.append(fmtWord)
            fmtWord.length = font.getlength(fmtWord.txt)
            currLine.length = fmtWord.length
            continue

        isPunctuation = set(fmtWord.txt) <= punctuation
        newTxt = fmtWord.txt if isPunctuation else (" " + fmtWord.txt)
        fmtWord.length = font.getlength(newTxt)
        newLen = fmtWord.length + currLine.length
        if newLen > width:
            if isPunctuation:
                lastWord = currLine.fmtUnits.pop()
                lastWord.txt = lastWord.txt.strip()
                lastWord.length = ImageFont.truetype(lastWord.font, height).getlength(lastWord.txt)
                currLine.length -= lastWord.length
                formattedLines.append(currLine)
                currLine = FormattedLine(lastWord.length + fmtWord.length, [lastWord, fmtWord])

            else:
                fmtWord.length = font.getlength(fmtWord.txt)
                formattedLines.append(currLine)
                currLine = FormattedLine(fmtWord.length, [fmtWord])

            continue

        fmtWord.txt = newTxt
        currLine.fmtUnits.append(fmtWord)
        currLine.length = newLen

    return formattedLines

def writeText(fmtLines, textHeight, spacing):
    center = True
    pad = int(textHeight * 0.5)
    maxLineLen = max([line.length for line in fmtLines])
    imgWidth = maxLineLen + (pad * 2)
    imgHeight = (textHeight + spacing) * len(fmtLines) + (pad * 2)

    ceil = lambda i : int(i) if int(i) == i else int(i + 1)
    img = Image.new("RGB", (ceil(imgWidth), ceil(imgHeight)), "grey")
    d = ImageDraw.Draw(img)

    (x, y) = (pad, (textHeight + pad) - int(0.12 * textHeight))
    for fmtLine in fmtLines:
        if center:
            x += int((maxLineLen - fmtLine.length)/2)
        for fmtUnit in fmtLine.fmtUnits:
            font = ImageFont.truetype(fmtUnit.font, textHeight)
            d.text((x, y), fmtUnit.txt, font=font, anchor="ls")
            x += fmtUnit.length
        (x, y) = (pad, y + textHeight + spacing)

    img.save("real.png")
    return

if __name__ == "__main__":
    textWidth = 1000
    textHeight = 24
    spacing = int(textHeight * 0.34)
    with open("capfmt.txt","r") as f:
        text = f.read()

    fmtWords = parse_text(text)
    fmtLines = wrapRegions(fmtWords, textWidth, textHeight)
    writeText(fmtLines, textHeight, spacing)
