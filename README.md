# PDF to markdown

`convert_pdfs.py` reads each PDF and writes a markdown file with the same name. The markdown file keeps headings, lists, code, tables, and figures.

The script is written for the Standards PDFs in the parent folder. Those files use one page layout. A PDF with a different layout can lose headings, lists, or tables.

## Requirements

- Python 3.11 or later
- The packages in `requirements.txt`

## Install

1. Open a terminal in this folder.
2. Create a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install the packages.

```bash
pip install -r requirements.txt
```

## Convert a folder

Run the script from this folder. Pass the folder that contains the PDF files.

```bash
python convert_pdfs.py ..
```

The script reads each PDF in that folder. It does not open PDF files in subfolders.

## Convert one PDF

Pass the path of one PDF file.

```bash
python convert_pdfs.py "../STANDARD _ API Conventions.pdf"
```

## Output

The script writes each markdown file next to its PDF. The file name is the PDF name with `.md` in place of `.pdf`.

A PDF named `STANDARD _ API Conventions.pdf` produces `STANDARD _ API Conventions.md`.

When a markdown file with that name already exists, the script replaces it.

Figures are PNG files under `assets/<document-name>/`, next to the PDF. The markdown file links to those images.

Each markdown file starts with the document title. When the PDF footer contains a `docs.is.sa` link, the next line is `Source:` and that link.

## Run from another folder

Give the full path of the script and the full path of the PDF folder.

```bash
python /path/to/pdf-to-md/convert_pdfs.py /path/to/pdf-folder
```
