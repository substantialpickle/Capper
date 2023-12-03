from pathlib import Path
from PIL import Image
from termcolor import cprint

class Logging:
    width = 5
    tab = 8

    @staticmethod
    def divider():
        print(f"+{'':->{Logging.width-2}}+")

    @staticmethod
    def header(text):
        Logging.divider()
        cprint(f"| {text}", attrs=["bold"])

    @staticmethod
    def subSection(text, levels=1, color="cyan"):
        print("| ", end="")
        cprint(f"{'': >{Logging.tab * levels}}{text}", color)

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

        print("|")
        print(f"| {'': >{Logging.tab * levels}}{tableEdge}")
        for row in tableStrs:
            rowStr = "| "
            for i, (coll, collLen) in enumerate(zip(row, collLens)):
                align = "<" if i == 0 else ">"
                rowStr += f"{coll:{align}{collLen-2}} | "
            print(f"| {'': >{Logging.tab * levels}}{rowStr}")
        print(f"| {'': >{Logging.tab * levels}}{tableEdge}")

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

class UserError(Exception):
    def __init__(self, message):
        self.message = message

    @staticmethod
    def uassert(cond, message):
        if not cond:
            raise UserError(message)
