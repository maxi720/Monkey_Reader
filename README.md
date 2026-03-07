# PDF Quiz Extractor

A local web app that extracts multiple-choice questions from a PDF and exports them as a CSV file.

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

Then open [http://localhost:5000](http://localhost:5000) in your browser.

## CSV Format

Output is semicolon-delimited:

```
Question;OptionA;OptionB;OptionC;OptionD;CorrectAnswer
```

- Columns 2–5: answer options (empty if fewer than 4)
- Column 6: full text of the correct answer

## PDF Format Requirements

The app expects PDFs structured as follows:

- Questions numbered with `)`: `1)`, `2)`, etc.
- Answer options lettered with `)`: `a)`, `b)`, `c)`, optionally `d)`
- An answer key on the last page with pairs like `1 C`, `2 B`, etc.

Any introductory or preamble text is ignored automatically.
