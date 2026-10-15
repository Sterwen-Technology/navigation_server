#-------------------------------------------------------------------------------
# Name:        pdf_to_md
# Purpose:     translate pdf files in markdown - used to analyse specifications for code generation
#
# Author:      Laurent Carré
#
# Created:     15/10/2026
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import pymupdf4llm, pathlib
import sys, os

def translate(pdf_filename, target_dir):
    md = pymupdf4llm.to_markdown(pdf_filename)
    md_filename = pdf_filename.replace('.pdf', '.md')
    pathlib.Path(target_dir, md_filename).write_text(md, encoding='utf-8')
    return md_filename


if __name__ == '__main__':
    pdf_file = sys.argv[1]
    target_dir = pathlib.Path(os.getenv('NAVIGATION_HOME'), 'reference_documentation')
    print(f"Processing {pdf_file} to {target_dir}")
    md_file = translate(pdf_file, target_dir)
    print(f"Generated {md_file}")