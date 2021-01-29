#!/usr/bin/env python3

from typing import Dict, List, Tuple
import warnings
import html5lib
from html5lib.constants import DataLossWarning
import html5lib.filters.whitespace
from lxml import etree
from lxml.html import html5parser
import pandas as pd
import re
from cjwmodule import i18n

# ---- Xpath ----

# Custom exception class used to pass a problem with a particular column
class ColumnExtractionError(Exception):
    def __init__(self, column_name, error):
        self.column_name = column_name
        self.error = error

    @property
    def i18n_message(self):
        return i18n.trans(
            "ColumnExtractionError.message",
            'XPath error for column "{column_name}": {error}',
            {"column_name": self.column_name, "error": self.error},
        )


# GLOBALLY ignore the warnings that (hopefully) only this module will emit. The
# warnings all have to do with "invalid" HTML, but that HTML is often good
# enough for our users so it isn't worth dumping anything to stderr.
warnings.filterwarnings(
    "ignore", category=DataLossWarning, module=r"html5lib\._ihatexml"
)


def xpath(s: str) -> etree.XPath:
    """
    Parse an XPath selector, or raise etree.XPathSyntaxError.

    A word on namespaces: this module parses HTML without a namespace.
    It parses embedded SVGs in the "svg" namespace. So your XPath
    selectors can look like:

    xpath('//p')           # all <p> tags (in HTML)
    xpath('//order/@id')   # all <order> id attributes (in XML)
    xpath('//svg:path/@d') # all <path> tags (in SVG embedded within HTML)
    """
    return etree.XPath(
        s,
        smart_strings=True,  # so result strings don't ref XML doc
        namespaces={
            "svg": "http://www.w3.org/2000/svg",
        },
    )


def parse_document(text: str, is_html: bool) -> etree._Element:
    """Build a etree root node from `text`.

    Throws TODO what errors?
    """
    if is_html:
        parser = html5parser.HTMLParser(namespaceHTMLElements=False)
        document = html5parser.fromstring(text, parser=parser)
        return document
    else:
        parser = etree.XMLParser(
            encoding="utf-8",
            # Disable as much as we can, for security
            load_dtd=False,
            collect_ids=False,
            resolve_entities=False,
        )
        return etree.fromstring(text.encode("utf-8"), parser)


# `etree` second argument is as suggested at
# https://github.com/html5lib/html5lib-python/issues/338#issuecomment-298789202
#
# Solves walking over comments (bug #166144899)
TreeWalker = html5lib.getTreeWalker("etree", etree)
WhitespaceFilter = html5lib.filters.whitespace.Filter


def _item_to_string(item) -> str:
    """Convert an XPath-returned item to a string.

    Rules:
    text node => text contents
    """
    if hasattr(item, "itertext"):
        # This is an Element.
        #
        # We need to strip insignificant whitespace but preserve _significant_
        # whitespace. For instance, "<p>a <b> b</b></p>" becomes "a  b" (two
        # spaces); "<p>a  <b>b</b>" becomes one.
        #
        # Many websites have stylesheets that hide _significant_ whitespace --
        # using font-size:0, negative margins, or some-such. We don't use the
        # stylesheet, so we don't get that.
        #
        # Finally, we strip the output. That's what IMPORTXML() does, and the
        # user probably wants it.
        texts = [
            token["data"]
            for token in WhitespaceFilter(TreeWalker(item))
            if token["type"] in ("Characters", "SpaceCharacters")
        ]
        return "".join(texts).strip()
    else:
        # item.is_attribute
        # item.is_text
        # item.is_tail
        return str(item)


def select(tree: etree._Element, selector: etree.XPath) -> List[str]:
    """
    Run an xpath expression on `tree` and convert results to strings.

    Raise XPathEvalError on error.
    """
    # TODO avoid DoS. xpath selectors can take enormous amounts of CPU/memory
    result = selector(tree)
    if hasattr(result, "__iter__") and not isinstance(result, str):
        return list(_item_to_string(item) for item in result)
    elif isinstance(result, bool):
        # boolean(//a) => bool. Return list of str. (Workbench does not support
        # bool.)
        return [str(result)]
    else:
        # count(//a) => float. Return list of float.
        return [result]


def extract_dataframe_by_zip(
    html: str, columns_to_parse: Dict[str, etree.XPath]
) -> Tuple[pd.DataFrame, bool]:
    """
    Extract columns separately, then zip them together.

    This essentially Google Sheets' IMPORTXML() function.

    Returns (dataframe, should_warn); should_warn is True when the columns have
    different lengths.
    """
    tree = parse_document(html, True)  # is_html=true

    # data: {name: Series of text values per selector}, in order.
    # The series may be of different length.
    data = {}
    for name, selector in columns_to_parse.items():
        try:
            data[name] = pd.Series(select(tree, selector), dtype=str)
        except etree.XPathEvalError as err:
            raise ColumnExtractionError(name, str(err))

    # Pad all column lists to the same length
    # DataFrame constructor will automatically do this if given Series
    table = pd.DataFrame(data)

    # If they're not all the same length, this may mean extraction failed.
    # Let the user see the data, and give them a warning
    #
    # We detect by checking if any value in the last row is null.
    should_warn = len(table) and table.iloc[-1].isnull().any()

    return (table, should_warn)


# Extract with one xpath selector per column
def extract_xpath(table, params):
    # load params
    # dict of { name: str -> etree.XPath } -- ordered as the input is ordered.
    columns_to_parse = {}
    for c in params["colselectors"]:
        colname = c["colname"]
        colxpath = c["colxpath"]
        if not colname:
            return i18n.trans("badParam.colname.missing", "Missing column name")
        if colname in columns_to_parse:
            return i18n.trans(
                "badParam.colname.duplicate",
                'Duplicate column name "{column_name}"',
                {"column_name": colname},
            )
        if not colxpath:
            return i18n.trans("badParam.colxpath.missing", "Missing column selector")
        try:
            selector = xpath(c["colxpath"])
        except etree.XPathSyntaxError as err:
            return i18n.trans(
                "badParam.colxpath.invalid",
                'Invalid XPath syntax for column "{column_name}": {error}',
                {"column_name": colname, "error": str(err)},
            )
        columns_to_parse[colname] = selector

    if not columns_to_parse:
        # User hasn't input anything. Return input, as is our convention.
        return table

    # Loop over rows of input html column, each of which is a complete html document
    # Concatenate rows extracted from each document.
    result_tables = []
    input_row_with_warning = None
    for index, html in table["html"].iteritems():
        if html is None:
            continue
        try:
            one_result, warn = extract_dataframe_by_zip(html, columns_to_parse)
        except ColumnExtractionError as err:
            return err.i18n_message
        result_tables.append(one_result)
        # track the first row where the extracted columns are not all the same
        # length
        if warn and input_row_with_warning is None:
            input_row_with_warning = index

    if result_tables:
        outtable = pd.concat(result_tables, ignore_index=True)
    else:
        # Empty table
        outtable = pd.DataFrame(
            {colname: [] for colname in columns_to_parse.keys()}, dtype=str
        )

    if input_row_with_warning is not None:
        return (
            outtable,
            i18n.trans(
                "warning.extractedDifferentLengths",
                "Extracted columns of differing lengths from HTML on row {row}",
                {"row": input_row_with_warning + 1},
            ),
        )
    else:
        return outtable


# ---- Ripped from server/utils.py ----
# Sigh. This is absurd. Either the host should do fixup of column names and types,
# or we should have a module "standard library"/callbacks provided by server.


def uniquize_colnames(colnames):
    """
    Yield colnames in one pass, renaming so no two names are alike.

    The algorithm: Match each colname against "Column Name 2": everything up to
    ending digits is the 'key' and the ending digits are the 'number'. Maintain
    a blacklist of numbers, for each key; when a key+number have been seen,
    find the first _free_ number with that key to construct a new column name.

    This algorithm is ... generic. It's useful if we know nothing at all about
    the columns and no column names are "important" or "to-keep-unchanged".
    """
    blacklist = {}  # key => set of numbers
    regex = re.compile(r"\A(.*?) (\d+)\Z")
    for colname in colnames:
        # Find key and num
        match = regex.fullmatch(colname)
        if match:
            key = match.group(1)
            num = int(match.group(2))
        else:
            key = colname
            num = 1

        used_nums = blacklist.setdefault(key, set())
        if num in used_nums:
            # Theoretically this could raise StopIteration ... but what
            # _should_ we do when we have so many columns?
            num = next(n for n in range(1, 9999999) if n not in used_nums)
        used_nums.add(num)

        if not match and num == 1:
            # Common case: yield the original name
            yield key
        else:
            # Yield a unique name
            # The original colname had a number; the one we _output_ must also
            # have a number.
            yield key + " " + str(num)


def autocast_series_dtype(series: pd.Series):
    """
    Cast any sane Series to str/category[str]/number/datetime.

    This is appropriate when parsing CSV data or Excel data. It _seems_
    appropriate when a search-and-replace produces numeric columns like
    '$1.32' => '1.32' ... but perhaps that's only appropriate in very-specific
    cases.

    The input must be "sane": if the dtype is object or category, se assume
    _every value_ is str (or null).

    If the series is all-null, do nothing.

    Avoid spurious calls to this function: it's expensive.

    TODO handle dates and maybe booleans.
    """
    if series.dtype == object:
        nulls = series.isnull()
        if (nulls | (series == "")).all():
            return series
        try:
            # If it all looks like numbers (like in a CSV), cast to number.
            return pd.to_numeric(series)
        except (ValueError, TypeError):
            # Otherwise, we want all-string. Is that what we already have?
            #
            # TODO assert that we already have all-string, and nix this
            # spurious conversion.
            array = series[~nulls].array
            if any(type(x) != str for x in array):
                series = series.astype(str)
                series[nulls] = None
            return series
    elif hasattr(series, "cat"):
        # Categorical series. Try to infer type of series.
        #
        # Assume categories are all str: after all, we're assuming the input is
        # "sane" and "sane" means only str categories are valid.
        if (series.isnull() | (series == "")).all():
            return series
        try:
            return pd.to_numeric(series)
        except (ValueError, TypeError):
            # We don't cast categories to str here -- because we have no
            # callers that would create categories that aren't all-str. If we
            # ever do, this is where we should do the casting.
            return series
    else:
        assert is_numeric_dtype(series) or is_datetime64_dtype(series)
        return series


def autocast_dtypes_in_place(table: pd.DataFrame) -> None:
    """
    Cast str/object columns to numeric, if possible.

    This is appropriate when parsing CSV data, or maybe Excel data. It is
    probably not appropriate to call this method elsewhere, since it destroys
    data types all over the table.

    The input must be _sane_ data only!

    TODO handle dates and maybe booleans.
    """
    for colname in table:
        column = table[colname]
        table[colname] = autocast_series_dtype(column)


def merge_colspan_headers_in_place(table) -> None:
    """
    Turn tuple colnames into strings.

    Pandas `read_html()` returns tuples for column names when scraping tables
    with colspan. Collapse duplicate entries and reformats to be human
    readable. E.g. ('year', 'year') -> 'year' and
    ('year', 'month') -> 'year - month'

    Alter the table in place, no return value.
    """
    newcols = []
    for c in table.columns:
        if isinstance(c, tuple):
            # collapse all runs of duplicate values:
            # 'a','a','b','c','c','c' -> 'a','b','c'
            vals = list(c)
            idx = 0
            while idx < len(vals) - 1:
                if vals[idx] == vals[idx + 1]:
                    vals.pop(idx)
                else:
                    idx += 1
            # put dashes between all remaining header values
            newcols.append(" - ".join(vals))
        elif isinstance(c, int):
            # If first row isn't header and there's no <thead>, table.columns
            # will be an integer index.
            newcols.append("Column %d" % (c + 1))
        else:
            newcols.append(c)
    # newcols can contain duplicates. Rename them.
    table.columns = list(uniquize_colnames(newcols))


# ---- Tables ----

# This is applied to each row of our input
def extract_table_from_one_page(html, tablenum, rowname):
    error_no_table = i18n.trans(
        "error.noTable",
        "Did not find any <table> tags in {rowname}",
        {"rowname": rowname},
    )
    try:
        # pandas.read_html() does automatic type conversion, but we prefer
        # our own. Delve into its innards so we can pass all the conversion
        # kwargs we want.
        tables = pd.io.html._parse(
            # Positional arguments:
            flavor="html5lib",  # force algorithm, for reproducibility
            io=html,
            match=".+",
            attrs=None,
            encoding=None,  # html string is already decoded
            displayed_only=False,  # avoid dud feature: it ignores CSS
            # Required kwargs that pd.read_html() would set by default:
            header=None,
            skiprows=None,
            # Now the reason we used pd.io.html._parse() instead of
            # pd.read_html(): we get to pass whatever kwargs we want to
            # TextParser.
            #
            # kwargs we get to add as a result of this hack:
            na_filter=False,  # do not autoconvert
            dtype=str,  # do not autoconvert
        )
    except ValueError:
        return error_no_table
    except IndexError:
        # pandas.read_html() gives this unhelpful error message....
        return i18n.trans(
            "error.noColumn", "Table has no columns in {rowname}", {"rowname": rowname}
        )

    if not tables:
        return error_no_table

    if tablenum >= len(tables):
        return i18n.trans(
            "badParam.tableNum.tooBig",
            "The maximum table number is {len_tables} for {rowname}",
            {"n_tables": len(tables), "rowname": rowname},
        )

    table = tables[tablenum]

    # pd.read_html() guarantees unique colnames
    merge_colspan_headers_in_place(table)

    autocast_dtypes_in_place(table)
    if len(table) == 0:
        # read_html() produces an empty Index. We want a RangeIndex.
        table.reset_index(drop=True, inplace=True)
    return table


# Extract contents of <table> tag
def extract_table(table, params):
    # We delve into pd.read_html()'s innards, above. Part of that means some
    # first-use initialization.
    pd.io.html._importers()

    tablenum = params["tablenum"] - 1  # 1-based for user

    if tablenum < 0:
        return i18n.trans(
            "badParam.tablenum.negative", "Table number must be at least 1"
        )

    # Loop over rows of input html column, each of which is a complete html document
    # Concatenate rows extracted from each document.
    result_tables = []
    first_warning = None
    for index, html in table["html"].iteritems():
        if html is None:
            continue

        # Use url for "name" of row if available, for error messages
        if "url" in table.columns:
            rowname = table["url"].iloc[index]
        else:
            rowname = "input html row " + str(index + 1)

        one_result = extract_table_from_one_page(html, tablenum, rowname)

        if isinstance(one_result, i18n.I18nMessage):
            if not first_warning:
                first_warning = one_result
        else:
            result_tables.append(one_result)

    if result_tables:
        result = pd.concat(result_tables, ignore_index=True, sort=False)
        if first_warning:
            return (result, first_warning)
        else:
            return result
    else:
        if first_warning:
            return first_warning  # if nothing is extracted, warning becomes error
        else:
            return pd.DataFrame()


# ---- Main ----


def render(table, params):
    # Suggest quickfix of adding Scrape HTML if 'html' col not found
    inputcol = "html"
    if inputcol not in table.columns:
        return {
            "message": i18n.trans(
                "error.noHtml.error", "No 'html' column found. Do you need to scrape?"
            ),
            "quickFixes": [
                {
                    "text": i18n.trans(
                        "error.noHtml.quick_fix.text", "Add HTML scraper"
                    ),
                    "action": "prependModule",
                    "args": ["urlscraper", {}],
                }
            ],
        }

    method = params["method"]
    if method == "xpath":
        return extract_xpath(table, params)
    else:
        return extract_table(table, params)


def _migrate_v0_to_v1(params):
    return {**params, "method": "xpath", "tablenum": 1}  # v0 had only xpath method


def migrate_params(params):
    if "method" not in params:
        params = _migrate_v0_to_v1(params)
    params.pop(
        "first_row_is_header", None
    )  # remove defunct key from a few early test wf

    return params
