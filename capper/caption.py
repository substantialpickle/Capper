import argparse
import colorama
import time
from math import ceil
import os
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont

from pretty_logging import Logging, UserError
from spec_parse import UserSpec
from text import parseText, wrapRegions, TextBox

# TODOs:
#    - write up a guide

class Font:
    def __init__(self, path, height, color, stroke, strokeColor):
        self.path = path
        self.font = ImageFont.truetype(path, height)
        self.height = height
        self.spaceLen = self.font.getlength(" ")

        fontColorMatches = UserSpec.rgbaRe.fullmatch(color)
        self.color = color
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

def drawCredits(d, capCredits, creditsPos, artX, artY, artWidth, artHeight):
    if capCredits == "":
        return

    if "credits" in FONTS:
        font = FONTS["credits"]["font"]
    else:
        baseFont = FONTS[SPEC.characters[0]["name"]["value"]]["font"]
        font = Font(baseFont.path, ceil(artHeight * 0.02), baseFont.color, 0, "#00000000")
        FONTS["credits"] = {}
        FONTS["credits"]["font"] = font
        creditsChar = {}
        creditsCharSpec = {
            "name" : "credits",
            "color" : baseFont.color,
            "font" : baseFont.path,
            "relative_height" : font.height/SPEC.text["base_font_height"]["value"]
        }
        UserSpec.checkKeys(creditsCharSpec,
                           SPEC.characterValidKeys,
                           SPEC.characterRequiredKeys,
                           creditsChar)
        SPEC.validateAndSetChar(creditsCharSpec, creditsChar)
        SPEC.characters.append(creditsChar)

    padding = font.height

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

    # Generate caption
    if outputs in ["all", "caption"] and SPEC.image["art"]["value"] is not None:
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

        if SPEC.image["art"]["value"] is not None:
            artFile = directory + baseFilename + "_art." + outputFmt
            Logging.subSection(f"Generating rescaled art '{artFile}'")
            img = Image.new(colorMode, (art.width, art.height), bgColor)
            img.paste(art, (0, 0))
            img.save(artFile, optimize=True, quality=imgQuality)
            fileSizeTable.append((artFile,
                                  Logging.filesizeStr(artFile),
                                  Logging.dimensionsStr(artFile)))

        if capCredits != '' and SPEC.image["art"]["value"] is not None:
            creditsFile = directory + baseFilename + "_credits." + outputFmt
            Logging.subSection(f"Generating credits '{creditsFile}'")
            img = Image.new(colorMode, (art.width, art.height), bgColor)
            drawCredits(ImageDraw.Draw(img), capCredits, creditsPos, 0, 0,
                        art.width, art.height)
            img.save(creditsFile, optimize=True, quality=imgQuality)
            fileSizeTable.append((creditsFile,
                                  Logging.filesizeStr(creditsFile),
                                  Logging.dimensionsStr(creditsFile)))

    # Generate filled in TOML file
    specFilename = directory + baseFilename + "_autospec.toml"
    Logging.subSection(f"Generating filled-in specification '{specFilename}'")
    SPEC.outputFilledSpec(specFilename)
    fileSizeTable.append((specFilename, Logging.filesizeStr(specFilename), ""))

    Logging.subSection("Successfully generated all images!", 1, "green")
    Logging.table(fileSizeTable)

def main():
    textInfoTable = []
    baseFontHeight = SPEC.text["base_font_height"]["value"]

    Logging.header(f"Reading and fitting text from '{SPEC.text['text']['value']}'")
    with open(SPEC.text["text"]["value"], "r",encoding="utf-8") as f:
        text = f.read()

    firstChar = SPEC.characters[0]["name"]["value"]
    fmtWords = parseText(text, FONTS, firstChar)

    textInfoTable.append(
        ("Word Count", sum([1 for word in fmtWords if word.fmtUnits != []])))

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
