# This is free software, licensed under the LGPL v3. See the file "COPYING" for
# details.
#
# (c) 2018 Sebastian Humenda <shumenda |at|gmx |dot| de>
#   Jaromir Plhak <xplhak |at| gmail |dot| com>

"""
Link checker for MarkDown documents.

When linking to another file, the link has to use the target format extension
(i.e. .html) and hence that has to be considered when looking for broken links.
This link checker is hence tailored to MarkDown.

This link checker also checks for broken image references.

This link checker does not touch the file system. It requires a list of files
(as produced by os.walk()) and all links and images. Helper function extract
those for the link checker.
"""

import os
from .. import mparser

"""
Issue #20

A common source of error are broken links. Normal link checkers won't work,
since they are working on HTML files. It is hence necessary to parse all
MarkDown links and implement the destination checks manually (to the
resulting HTML files). As a plus, references within the document could be
checked as well.

For checking IDs, it is a good idea to generate IDs of the target document.
Headings get automatic IDs, which can be generated using datastructures.gen_id.
Furthermore, the user may create own anchors with <span id="foo"/> or the
div equivalent.

Checking links in the markdown document
- a) parse the links
- b) test if they are correctly structured
- c) check internal links (no need to be online, files should be on the disk)
    - ca) check the structure of the link
    - ca) check if files are generated
    - cb) if they are - check all links given by markdown
"""


class LinkExtractor:
    """ The purpose of this class is to extract all links that has to
    be checked.
    Note: This class assumes that markdown links are correctly structured
    according to the rules specified by pandoc manual, available at
    https://pandoc.org/MANUAL.html#links """
    def __init__(self):
        self.__errors = []  # generated errors
        self.links_list = []  # dicts of links generated in the examined files

    def get_list_of_md_files(self, file_tree):
        """ This method creates list of paths to .md files which links should
        be tested. It also returns the name of the file. """
        md_file_list = []
        for directory_name, _, file_list in file_tree:
            for file in file_list:
                if file.endswith(".md"):  # only .md files will be inspected
                    file_path = os.path.join(directory_name, file)
                    # check if file exists
                    if os.path.isfile(file_path):
                        # whole path for generation, filename for feedback
                        md_file_list.append((file_path, file))
        return md_file_list

    def parse_all_links_in_md_files(self, file_tree):
        """ Parses all links in the .md files and stores them in the dictionary
        that has the following structure:
        "file": name of the file, where the link is stored
        "link_type": type of the link - this should be as follows:
            "inline": basic inline link in square brackets, syntax
            "footnote": link to the footnote that is referenced somewhere else
                in the document
            "standalone": link in square brackets referenced somewhere
                else in the document
            "reference": reference to the footnote and standalone_links types.
                References with titles are not detected as they are not
                relevant to the link testing
            "angle_brackets": link given by square brackets
        "line_no": number of line where regular expression
        "is_picture": 'True' if the link is a picture, 'False' otherwise
        "link": explored link
        "link_text": contains link text, if exists
        "link_title": title of the link, if exists """
        for file_path, file_name in self.get_list_of_md_files(file_tree):
            # encoding of the file should be already checked
            with open(file_path, encoding="utf-8") as file_data:
                # call the function for finding links
                data = mparser.find_links_in_markdown(file_data.read())
                for link_dict in data:
                    self.links_list.append(self.create_dct(
                        file_name, link_dict[0], link_dict[1], link_dict[2]))
        print(self.links_list)  # TODO: remove this testing string

    def create_dct(self, file_name, line_no, link_type, link):
        """ This method generates the dictionary that contains all the
        important data for the link. """
        link_dict = dict()
        link_dict["file"] = file_name
        link_dict["link_type"] = link_type
        link_dict["line_no"] = line_no + 1
        if isinstance(link, str):  # angle_brackets and text_link_itself
            link_dict["link"] = link
        if isinstance(link, tuple) and len(link) > 2:
            link_dict["is_image"] = True if link[0] == "!" else False
            link_dict["link_text"] = link[1]
            link_dict["link"] = link[2]  # link itself

        return link_dict


class LinkParser:
    # ToDo: document: files must be relative to document being checked
    # ToDo: how to thread ..? just check with os.path.exists()? needs base
    # directory
    def __init__(self, links, images, files):
        pass

    def target_exists(self, target_file_name):
        pass


class LinkStructureChecker():
    """ Structure of the link should follow the basic rules of creating
    links. """
    pass


class LinkDefinitionShouldBeLinkedToReferenceLink():
    """ When FOOTNOTE_LINK_TEXT or TEXT_LINK_ITSELF is used, it should be
    connected to the reference link with []: syntax. Otherwise it should not
    be paired together.
    Note: Links are not case sensitive """


class NoSpaceBetweenRoundAndSquareBrackets():
    """ When the inline link or footnote link is used, it is not allowed by
    pandoc to have a space/spaces between square and round brackets."""
    pass


class TitleInLinkIsCorrect():
    # check if it is correctly build using " or ' (the last
    # char should be the there at least twice - and first one
    # is the end of the link
    pass


class TitleInLinkCannotContainFormatting():
    """ When using INLINE_LINK_WITH_TITLE, it is not allowed to have
    formatting information within link title. """
    pass


class DetectCorrectEmail():
    """ When 'mailto:' is used, the structure of the email address should
    be detected. """

    def detect_email_address(self, link):
        """ Detecting, if the link is email address. It only checks, if the
        'mailto' is the starting substring of the link. """
        return link.find("mailto:") == 0


class TitleIsTooLong():
    """ Title should be 'reasonably' long. Long text lowers the readability
    and they also can be caused by a incorrect syntax of link. """
    pass


class IncorrectImageFormattingUsingAngleBrackets():
    """It is not allowed to enter image using angle brackets."""
    pass

# TODO: Detect images
# TODO: link within picture description
# value = d.get(key)
