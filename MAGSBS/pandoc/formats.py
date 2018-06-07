"""Output format formatters, currently only HTML."""
# vim: set expandtab sts=4 ts=4 sw=4:
# This is free software, licensed under the LGPL v3. See the file "COPYING" for
# details.
#
# (c) 2017-2018 Sebastian Humenda <shumenda |at| gmx |dot| de>

import enum
import json
import os
import re
import shutil
import subprocess
import tempfile
import pandocfilters
from ..config import MetaInfo
from . import contentfilter
from .. import config, common, datastructures, errors, mparser


HTML_template = """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml"$if(lang)$ lang="$lang$" xml:lang="$lang$"$endif$>
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
  <meta name="author" content="{SourceAuthor}" />
$if(date-meta)$
  <meta name="date" content="$date-meta$" />
$endif$
  <title>$if(title-prefix)$$title-prefix$ - $endif$$pagetitle$</title>
  <style type="text/css">
    code {{ white-space: pre; }}
    .underline {{ text-decoration: underline }}
    .annotation {{ border:2px solid #000000; background-color: #FCFCFC; }}
    .annotation:before {{ content: "{annotation}: "; }}
    table, th, td {{ border:1px solid #000000; }}
    /* frames with their colours */
    .frame {{ border:1px solid #000000; }}
    .box {{ border:2px dotted #000000; }}
    {frames}
    {boxes}
    div.frame span.title:before {{ content: "\\A{title}: "; white-space:pre; }}
    div.frame span.title:after {{ content: "\\A"; white-space:pre; }}
    div.box span.title:before {{ content: "\\A{title}: "; white-space:pre; }}
    div.box span.title:after {{ content: "\\A"; white-space:pre; }}

$if(highlighting-css)$
$highlighting-css$
$endif$
  </style>
$if(math)$
  $math$
$endif$
$for(header-includes)$
  $header-includes$
$endfor$
  <!-- agsbs-specific -->
  <meta name='Einrichtung' content='{Institution}' />
  <meta href='Arbeitsgruppe' content='{WorkingGroup}' />
  <meta name='Vorlagedokument' content='{Source}' />
  <meta name='Lehrgebiet' content='{LectureTitle}' />
  <meta name='Semester der Bearbeitung' content='{SemesterOfEdit}' />
  <meta name='Bearbeiter' content='{Editor}' />
</head>
<body lang="{Language}">
$for(include-before)$
$include-before$
$endfor$
$if(toc)$
<div id="$idprefix$TOC">
$toc$
</div>
$endif$
$body$
$for(include-after)$
$include-after$
$endfor$
</body>
</html>
"""

class ConversionProfile(enum.Enum):
    """Defines the enums for the conversion depending on the the impairment."""
    Blind = 'blind'
    VisuallyImpairedDefault = 'vid'

    @staticmethod
    def from_string(string):
        for profile in ConversionProfile:
            if profile.value == string:
                return profile
        known = ', '.join(x.value for x in ConversionProfile)
        raise ValueError("Unknown profile, known profiles: " + known)

class OutputGenerator():
    """Base class for document output generators. The actual conversion doesn't
take place in this class. The conversion method receives a Pandoc (JSON) AST and
transforms it, as required. The transformed AST is returned.
Each child should have constants called FILE_EXTENSION and PANDOC_FORMAT_NAME
(used for the file extension and the -t pandoc command line flag).

General usage:
>>> gen = MyGenerator(a_dictionary, language)
# method for children to implement (optional) things like template creation
>>> gen.setup() # needs to be called anyway
# convert json of document and write it to basefilename + '.' + format; may
# raises SubprocessError; the json is the Pandoc AST (intermediate file format)
>>> if gen.needs_update(path):
'''    ast = gen.convert(ast, path)
# clean up, e.g. deletion of templates. Should be executed even if gen.convert()
# threw an error
gen.cleanup()."""
    FILE_EXTENSION = 'None'
    PANDOC_FORMAT_NAME = 'plain'
    # json content filters:
    CONTENT_FILTERS = [contentfilter.page_number_extractor,
                    contentfilter.suppress_captions]
    # recognize chapter prefixes in paths, e.g. "anh01" for appendix chapter one
    IS_CHAPTER = re.compile(r'^%s\d+\.md$' % '|'.join(common.VALID_FILE_BGN))

    def __init__(self, meta, language):
        self.__meta = meta
        self.__language = language
        self.__conversion_profile = ConversionProfile.Blind

    def get_language(self):
        return self.__language

    def set_meta_data(self, meta):
        self.__meta = meta

    def get_meta_data(self):
        return self.__meta

    def setup(self):
        """Set up converter."""
        pass

    def convert(self, files, **kwargs):
        """Read from JSON and return JSON, too.
        files: files to be converted
        kwargs: filter specific arguments"""
        pass

    def cleanup(self):
        pass

    def needs_update(self, path):
        """Returns True, if the given file needs to be converted again. If i.e.
        the output file is newer than the input (MarkDown) file, no conversion
        is necessary."""
        raise NotImplementedError()

    def set_profile(self, profile):
        self.__conversion_profile = profile

    def get_profile(self):
        return self.__conversion_profile

    @staticmethod
    def load_json(document):
        """Load JSon input from ''inputf`` and return a reference to the loaded
        json document tree."""
        return contentfilter.text2json_ast(document)

class HtmlConverter(OutputGenerator):
    """HTML output format generator. For documentation see super class;."""
    PANDOC_FORMAT_NAME = 'html'
    FILE_EXTENSION = 'html'

    def __init__(self, meta, language):
        super().__init__(meta, language)
        self.template_path = None
        self.template_copy = HTML_template[:] # in-memory copy of current template to be written when required

    def setup(self):
        """Set up the HtmlConverter. Prepare the template for later use."""
        self.template_path = tempfile.mktemp() + '.html'
        self.template_copy = self.get_template()
        with open(self.template_path, "w", encoding="utf-8") as file:
            file.write(self.template_copy)

    def get_template(self):
        """Construct template."""
        start_with_caps = lambda content: content[0].upper() + content[1:]
        data = HTML_template[:]
        meta = self.get_meta_data()
        if 'title' in meta:
            meta.pop('title') # title should not be replaced

        # get translator object to translate certain phrases according to
        # configured language
        trans = config.Translate()
        trans.set_language(super().get_language())
        annotation = start_with_caps(trans.get_translation('note of editor'))
        frames = ['.frame:before { content: "%s: "; }' % \
                    start_with_caps(trans.get_translation("frame")),
                '.frame:after { content: "\\A %s"; }' % start_with_caps(trans \
                    .get_translation("end of frame"))]
        boxes = ['.box:before { content: "%s: "; }' % \
                    trans.get_translation("box"),
                '.box:after { content: "\\A %s"; }' % start_with_caps(trans \
            .get_translation("end of box"))]
        colours = {'black': '#000000;', 'blue': '#0000FF', 'brown': '#A52A2A',
            'grey': '#A9A9A9', 'green': '#006400', 'orange': '#FF8C00',
            'red': '#FF0000', 'violet': '#8A2BE2', 'yellow': '#FFFF00'}
        for name, rgb in colours.items():
            frames.append('.frame.%s { border-color: %s; }' % (name, rgb))
            frames.append('.frame.%s:before { content: "%s: "; }' % (name, \
                start_with_caps(trans.get_translation('%s frame' % name))))
            boxes.append('.box.%s { border-color: %s; }' % (name, rgb))
            boxes.append('.box.%s:before { content: "%s: "; }' % \
                (name, trans.get_translation('%s box' % name)))

        try:
            return data.format(annotation=annotation,
                    frames='\n    '.join(frames),
                    boxes='\n    '.join(boxes),
                    title=trans.get_translation("title"),
                    **meta)
        except KeyError as e:
            raise errors.ConfigurationError(("The key %s is missing in the "
                "configuration.") % e.args[0], meta['path'])

    def set_meta_data(self, meta):
        """Overwrite parent settr to re-generate template generation."""
        super().set_meta_data(meta)
        self.setup()

    def convert(self, files, **kwargs):
        """See super class documentation."""
        try:
            if not 'cache' in kwargs:
                raise ValueError('cache must be passed to converter')
            cache = kwargs['cache']
            c = config.ConfFactory()
            conf = None
            for file_name in files:
                # get correct configuration for each file
                newconf = c.get_conf_instance(os.path.dirname(file_name))
                # get new converter (and template) if config changes
                if not newconf is conf:
                    conf = newconf
                self.__convert_document(file_name, cache, conf)
        except errors.MAGSBS_error as e:
            # set path for error
            if not e.path:
                e.path = os.path.abspath(file_name)
            raise e
        finally:
            self.cleanup()

    def __convert_document(self, path, file_cache, conf):
        """Convert a document by a given path. It takes a converter which takes
        actual care of the underlying format. The filecache caches the list of
        files in the lecture. The list of files within a lecture is required to
        build navigation links.
        This function also inserts a page navigation bar to navigate between
        chapters and the table of contents."""
        # if output file name exists and is newer than the original, it doesn need to be converted again
        if not self.needs_update(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            document = f.read()
        if not document:
            return # skip empty documents
        if OutputGenerator.IS_CHAPTER.search(os.path.basename(path)):
            try:
                nav_start, nav_end = generate_page_navigation(path, file_cache,
                    mparser.extract_page_numbers_from_par(mparser.file2paragraphs(document)))
            except errors.FormattingError as e:
                e.path = path
                raise e
            document = '{}\n\n{}\n\n{}\n'.format(nav_start, document, nav_end)
        json_ast = OutputGenerator.load_json(document)
        # add MarkDown extensions with Pandoc filters
        try:
            filter = None
            for filter in OutputGenerator.CONTENT_FILTERS:
                json_ast = pandocfilters.walk(json_ast, filter,
                        conf[MetaInfo.Format], [])
            self.__apply_filter(json_ast, path)
        except KeyError as e: # API clash(?)
            raise errors.StructuralError(("Incompatible Pandoc API found, while "
                "applying filter %s (ABI clash?).\nKeyError: %s") % \
                        (filter.__name__, str(e)), path)

    def __apply_filter(self, json_ast, path):
        check_for_pandoc()
        dirname, filename = os.path.split(path)
        outputf = os.path.splitext(filename)[0] + '.' + self.FILE_EXTENSION
        pandoc_args = ['-s', '--template=%s' % self.template_path]
        # set title
        title = contentfilter.get_title(json_ast)
        if title: # if not None
            pandoc_args += ['-V', 'pagetitle:' + title, '-V', 'title:' + title]
        # instruct pandoc to enumerate headings
        try:
            pandoc_args += ['--number-sections', '--number-offset',
                str(datastructures.extract_chapter_number(path) - 1)]
        except errors.StructuralError:
            pass # no enumeration of headings if not chapter
        # check whether "Math" occurs and therefore if GladTeX needs to be run
        use_gladtex = True in contentfilter.json_ast_filter(json_ast,
                contentfilter.has_math)
        if use_gladtex and self.get_profile() is ConversionProfile.Blind:
            outputf = os.path.splitext(filename)[0] + '.htex'
            pandoc_args.append('--gladtex')
        if self.get_profile() is ConversionProfile.VisuallyImpairedDefault:
            pandoc_args.append('--mathjax')
        execute(['pandoc'] + pandoc_args + ['-t', self.PANDOC_FORMAT_NAME, '-f','json',
            '+RTS', '-K25000000', '-RTS', # increase stack size
            '-o', outputf], stdin=json.dumps(json_ast), cwd=dirname)
        if use_gladtex and self.get_profile() is ConversionProfile.Blind:
            try:
                execute(["gladtex", "-R", "-n", "-m", "-a", "-d", "bilder",
                    outputf], cwd=dirname)
            except errors.SubprocessError as e:
                raise __handle_gladtex_error(e, filename, dirname)
            else: # remove GladTeX .htex file
                remove_temp(os.path.join(dirname, outputf))
    def cleanup(self):
        remove_temp(self.template_path)

    def needs_update(self, path):
        # if file exists and input is newer than output, needs to be converted
        # again
        output = os.path.splitext(path)[0] + '.' + self.FILE_EXTENSION
        if not os.path.exists(output):
            return True
        # True if source file is newer:

        return os.path.getmtime(path) > os.path.getmtime(output)

def execute(args, stdin=None, cwd=None):
    """Convenience wrapper to subprocess.Popen). It'll append the process' stderr
    to the message from the raised exception. Returned is the unicode stdout
    output of the program. If stdin=some_value, a pipe to the child is opened
    and the argument passed."""
    text = None
    proc = None
    text = None
    cwd = (cwd if cwd else '.')
    text = ''
    try:
        if stdin:
            #pylint: disable=redefined-variable-type
            proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, stdin=subprocess.PIPE, cwd=cwd)
            text = proc.communicate(stdin.encode(datastructures.get_encoding()))
        else:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=cwd)
            text = proc.communicate()
    except FileNotFoundError as e:
        msg = '%s:_: %s %s ' %(args[0], str(e), text)
        raise errors.SubprocessError(args, msg)
    if not proc:
        raise ValueError("No subprocess handle exists, even though it " + \
                "should. That's a bug to be reported.")
    ret = proc.wait()
    if ret:
        msg = '\n'.join(map(datastructures.decode, text))
        raise errors.SubprocessError(args, msg)
    return datastructures.decode(text[0])

def remove_temp(fn):
    if fn is None:
        return
    if os.path.exists(fn):
        try:
            os.remove(fn)
        except OSError:
            common.WarningRegistry().register_warning(
            "Couldn't remove tempfile", path=fn)

def check_for_pandoc():
    if not shutil.which('pandoc'):
        raise errors.SubprocessError(['pandoc'],
            _('You need to have Pandoc installed.'))

def __handle_gladtex_error(error, file_path, dirname):
    """Retrieve formula position from GladTeX' error output, match it
    against the formula of the Markdown document and report it to the
    user.
    Note: file_path is relative to dirname, so both is required."""
    file_path = os.path.join(dirname, file_path) # full path is better
    try:
        details = dict(line.split(': ', 1) for line in error.message.split('\n')
            if ': ' in line)
    except ValueError as e:
        # output was not formatted as expected, report that
        msg = "couldn't parse GladTeX output: %s\noutput: %s" % \
            (str(e), error.message)
        return errors.SubprocessError(error.command, msg, path=dirname)
    if details and 'Number' in details and 'Message' in details:
        number = int(details['Number'])
        with open(file_path, 'r', encoding='utf-8') as f:
            paragraphs = mparser.rm_codeblocks(mparser.file2paragraphs(
                f.read().split('\n')))
            formulas = mparser.parse_formulas(paragraphs)
        try:
            pos = list(formulas.keys())[number-1]
        except IndexError:
            # if improperly closed maths environments eixst, formulas cannot
            # be counted; although there's somewhere a LaTeX error which
            # we're trying to report, the improper maths environments HAVE
            # to reported and fixed first
            raise errors.SubprocessError(error.command, _(
                    "LaTeX reported an error while converting a fomrula. "
                    "Unfortunately, improperly closed formula environments "
                    "exist, therefore it cannot be determined which formula "
                    "was errorneous. Please re-read the document and fix "
                    "any unclosed formula environments."), file_path)

        # get LaTeX error output
        msg = details['Message'].rstrip().lstrip()
        msg = 'formula: {}\n{}'.format(list(formulas.values())[number-1], msg)
        e = errors.SubprocessError(error.command, msg, path=file_path)
        e.line = '{}, {}'.format(*pos)
        return e
    return error

#pylint: disable=redefined-variable-type,too-many-locals
def generate_page_navigation(file_path, file_cache, page_numbers, conf=None):
    """generate_page_navigation(path, file_cache, page_numbers, conf=None)
    Generate the page navigation for a page. The file path must be relative to
    the lecture root. The file cache must be the datastructures.FileCache, the
    page numbers must have the format of mparser.extract_page_numbers_from.
    `conf=` should not be used, it is intended for testing purposes.
    Returned is a tuple with the start and the end navigation bar. The
    navigation bar itself is a string.
    """
    if not os.path.exists(file_path):
        raise errors.StructuralError("File doesn't exist", file_path)
    if not file_cache:
        raise ValueError("Cache with values may not be None")
    if not conf:
        conf = config.ConfFactory().get_conf_instance(os.path.split(file_path)[0])
    trans = config.Translate()
    trans.set_language(conf[MetaInfo.Language])
    relative_path = os.sep.join(file_path.rsplit(os.sep)[-2:])
    previous, next = file_cache.get_neighbours_for(relative_path)
    make_path = lambda path: '../{}/{}'.format(path[0], path[1].replace('.md',
        '.' + conf[MetaInfo.Format]))
    if previous:
        previous = '[{}]({})'.format(trans.get_translation('previous').title(),
                make_path(previous))
    if next:
        next = '[{}]({})'.format(trans.get_translation('next').title(), make_path(next))
    navbar = []
    page_numbers = [pnum for pnum in page_numbers
        if (pnum.number % conf[MetaInfo.PageNumberingGap]) == 0] # take each pnumgapth element
    if page_numbers:
        navbar.append(trans.get_translation('pages').title() + ': ')
        navbar.extend('[[{0}]](#p{0}), '.format(num) for num in page_numbers)
        navbar[-1] = navbar[-1][:-2] # strip ", " from last chunk
    navbar = ''.join(navbar)
    chapternav = '[{}](../inhalt.{})'.format(trans.get_translation(
            'table of contents').title(), conf[MetaInfo.Format])

    if previous:
        chapternav = previous + '  ' + chapternav
    if next:
        chapternav += "  " + next
    # navigation at start of page
    nav_start = '{0}\n\n{1}\n\n* * * *\n\n\n'.format(chapternav, navbar)
    # navigation bar at end of page
    nav_end = '\n\n* * * *\n\n{0}\n\n{1}\n'.format(navbar, chapternav)
    return (nav_start, nav_end)
