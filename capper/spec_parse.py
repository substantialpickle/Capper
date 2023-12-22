from functools import partial
import toml
from numbers import Number
from pathlib import Path
import re
import sys

from pretty_logging import Logging, UserError

class UserSpec:
    rgbaRe = re.compile("#([0-9A-F][0-9A-F])([0-9A-F][0-9A-F])"
                        "([0-9A-F][0-9A-F])([0-9A-F][0-9A-F])",
                         re.IGNORECASE)
    rgbRe = re.compile("#([0-9A-F][0-9A-F])([0-9A-F][0-9A-F])([0-9A-F][0-9A-F])",
                         re.IGNORECASE)
    @staticmethod
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

    def __init__(self, fileName):
        Logging.header(f"Verifying specification file '{fileName}'")
        UserError.uassert( Path(fileName).is_file(), f"File '{fileName}' does not exist" )
        with open(fileName, "r", encoding="utf-8") as f:
            spec = toml.load(f)

        Logging.subSection("Checking top level headers...")
        topLevelKeys = ["image", "text", "output", "characters"]
        self.checkKeys(spec.keys(), topLevelKeys, topLevelKeys)

        Logging.subSection("Checking [image]...")
        self.image = {}
        self.imageValidKeys = ["art", "image_height", "bg_color"]
        imageRequiredKeys = ["bg_color"]
        self.checkKeys(spec["image"], self.imageValidKeys, imageRequiredKeys, self.image)
        self.validateAndSetImage(spec["image"])

        Logging.subSection("Checking [text]...")
        self.text = {}
        self.textValidKeys = ["text", "base_font_height", "padding", "line_spacing",
                              "text_width", "text_box_pos", "alignment", "credits",
                              "credits_pos"]
        textRequiredKeys = ["text", "text_box_pos"]
        self.checkKeys(spec["text"], self.textValidKeys, textRequiredKeys, self.text)
        self.validateAndSetText(spec["text"])

        Logging.subSection("Checking [output]...")
        self.output = {}
        self.outputValidKeys = ["outputs", "output_directory", "output_img_format",
                                "output_img_quality", "base_filename"]
        outputRequiredKeys = ["base_filename"]
        self.checkKeys(spec["output"], self.outputValidKeys, outputRequiredKeys, self.output)
        self.validateAndSetOutput(spec["output"])

        Logging.subSection("Checking [[characters]]...")
        self.characters = []
        self.characterValidKeys = ["name", "color", "relative_height", "stroke_width",
                                   "stroke_color", "font", "font_bold", "font_italic",
                                   "font_bolditalic"]
        self.characterRequiredKeys = ["name", "color", "font"]
        for i, character in enumerate(spec["characters"]):
            Logging.subSection(f"Checking character #{i+1}...", 2)
            currChar = {}
            self.checkKeys(character, self.characterValidKeys, self.characterRequiredKeys, currChar)
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
        if artNotGiven and "caption" in outputs:
            UserError.uassert(outputs != "caption", "Cannot generate caption without art. " \
                "Either specify 'art' under [image], or remove 'caption' from list 'outputs'")

        if artNotGiven and "art" in outputs:
            UserError.uassert(outputs != "caption", "Cannot generate rescaled art " \
                "without art. Either specify 'art' under [image], or remove 'art' " \
                "from list 'outputs'")

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

        def checkOutputs(coll, key):
            outputs = coll[key]
            outputTypes = ["caption", "text", "autospec", "credits", "art"]
            UserError.uassert(isinstance(outputs, list),
                f"Expected {outputs} to be {list}, got {type(outputs)}")
            for output in outputs:
                UserError.uassert(isinstance(output, str),
                    f"Expected output {output} in 'outputs' to be {str}, got {type(output)}")
                UserError.uassert(output in outputTypes, "Expected the list 'outputs' to "
                                  f"contain one of {outputTypes}, got '{output}'")
            return outputs

        checkOutput = {
            "outputs" : {
                "check" : checkOutputs,
                "default" : ["caption"]
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

        def findFontFromDefault(default, fileSuffix):
            parentDir = Path(default).parent
            for f in parentDir.rglob("*"):
                fileName = f.as_posix()
                if fileName.lower()[len(fileName)-len(fileSuffix):] == fileSuffix.lower():
                    return fileName
            return default

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
                "default" : findFontFromDefault(inChar["font"], "-Bold.ttf")
            },
            "font_italic" : {
                "check" : UserSpec.checkFile,
                "default" : findFontFromDefault(inChar["font"], "-Italic.ttf")
            },
            "font_bolditalic" : {
                "check" : UserSpec.checkFile,
                "default" : findFontFromDefault(inChar["font"], "-BoldItalic.ttf")
            }
        }
        UserSpec.validateAndFillSpec(inChar, storedChar, checkChar)

    def outputFilledSpec(self, specFilename=None):
        def writeSection(f, data, orderedKeys):
            for key in orderedKeys:
                if data[key]["default"] == False:
                    if isinstance(data[key]["value"], str):
                        f.write(f"{key} = \"{data[key]['value']}\"\n")
                    elif isinstance(data[key]["value"], float):
                        f.write(f"{key} = {data[key]['value']:.3f}\n")
                    else:
                        f.write(f"{key} = {data[key]['value']}\n")
            for key in orderedKeys:
                if data[key]["default"] == True:
                    if isinstance(data[key]["value"], str):
                        f.write(f"# {key} = \"{data[key]['value']}\"\n")
                    elif isinstance(data[key]["value"], float):
                        f.write(f"# {key} = {data[key]['value']:.3f}\n")
                    else:
                        f.write(f"# {key} = {data[key]['value']}\n")

        f = sys.stdout if specFilename is None else open(specFilename, "w")
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

        if specFilename is not None:
            f.close()
