import csv
import io
import re

import pdfplumber
from flask import Flask, jsonify, render_template, request, Response

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB limit

QUESTION_RE = re.compile(r"^\s*(\d{1,3})[.)]\s*(?!\d)(.+)$")
OPTION_RE = re.compile(r"^\s*([a-dA-D])[.)]\s*(.*)$")
ANSWER_KEY_RE = re.compile(r"(?<![.\d])(\d{1,3})\s+([A-Da-d])(?!\w)")
# Lines that look like page headers/footers — skip them during parsing
SKIP_RE = re.compile(
    r"(?i)(eurowings|ltd\.?\s*$"
    r"|\bfsm\b.*\bchapter\b|\bchapter\b.*\bfsm\b"
    r"|\bpage\s+\d+\b|\b\d+\s+page\b"
    r"|\brevision\s+\d+\b|\b\d+\s+revision\b)"
)


def detect_answer_key(pages):
    """
    Scan pages from the end to find the answer key page(s).
    Returns (answer_key_dict, set_of_answer_key_page_indices).
    answer_key_dict maps question number (int) -> correct letter (uppercase str).
    """
    answer_key = {}
    key_page_indices = set()

    # Scan last 2 pages for answer key pattern
    candidates = pages[-2:] if len(pages) >= 2 else pages
    start_index = len(pages) - len(candidates)

    for i, page in enumerate(candidates):
        text = page.extract_text() or ""
        matches = ANSWER_KEY_RE.findall(text)
        if len(matches) >= 3:
            for num_str, letter in matches:
                answer_key[int(num_str)] = letter.upper()
            key_page_indices.add(start_index + i)

    return answer_key, key_page_indices


def extract_lines(pages, skip_indices):
    """
    Extract all text lines from pages not in skip_indices.
    Returns a flat list of stripped lines.
    """
    lines = []
    for i, page in enumerate(pages):
        if i in skip_indices:
            continue
        text = page.extract_text() or ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
    return lines


def parse_questions(lines):
    """
    State machine parser. Returns list of dicts:
    {'num': int, 'text': str, 'options': {'a': str, 'b': str, ...}}
    """
    questions = []
    state = "IDLE"
    current_num = None
    current_text = []
    current_options = {}
    last_option_key = None

    def flush():
        if current_num is not None and current_text:
            questions.append({
                "num": current_num,
                "text": " ".join(current_text).strip(),
                "options": dict(current_options),
            })

    for line in lines:
        if SKIP_RE.search(line):
            continue
        q_match = QUESTION_RE.match(line)
        o_match = OPTION_RE.match(line)

        if state == "IDLE":
            if q_match:
                current_num = int(q_match.group(1))
                current_text = [q_match.group(2).strip()] if q_match.group(2) else []
                current_options = {}
                last_option_key = None
                state = "IN_QUESTION"

        elif state == "IN_QUESTION":
            if q_match:
                flush()
                current_num = int(q_match.group(1))
                current_text = [q_match.group(2).strip()] if q_match.group(2) else []
                current_options = {}
                last_option_key = None
            elif o_match:
                key = o_match.group(1).lower()
                text = o_match.group(2).strip()
                current_options[key] = text
                last_option_key = key
                state = "IN_OPTIONS"
            else:
                current_text.append(line)

        elif state == "IN_OPTIONS":
            if q_match:
                flush()
                current_num = int(q_match.group(1))
                current_text = [q_match.group(2).strip()] if q_match.group(2) else []
                current_options = {}
                last_option_key = None
                state = "IN_QUESTION"
            elif o_match:
                key = o_match.group(1).lower()
                text = o_match.group(2).strip()
                current_options[key] = text
                last_option_key = key
            else:
                # Continuation of last option (multi-line option text)
                if last_option_key and line:
                    current_options[last_option_key] += " " + line

    flush()
    return questions


def build_csv(questions, answer_key):
    """
    Build semicolon-delimited CSV string from parsed questions and answer key.
    Columns: Question;OptionA;OptionB;OptionC;OptionD;CorrectAnswer
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\n")

    for q in questions:
        num = q["num"]
        text = q["text"]
        options = q["options"]

        opt_a = options.get("a", "")
        opt_b = options.get("b", "")
        opt_c = options.get("c", "")
        opt_d = options.get("d", "")

        correct_letter = answer_key.get(num, "")
        correct_text = options.get(correct_letter.lower(), "") if correct_letter else ""

        writer.writerow([text, opt_a, opt_b, opt_c, opt_d, correct_text])

    return output.getvalue()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400

    file = request.files["pdf"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Please upload a PDF file."}), 400

    try:
        pdf_bytes = io.BytesIO(file.read())
        with pdfplumber.open(pdf_bytes) as pdf:
            pages = pdf.pages

            if not pages:
                return jsonify({"error": "The PDF appears to be empty."}), 422

            answer_key, key_page_indices = detect_answer_key(pages)
            lines = extract_lines(pages, key_page_indices)
            questions = parse_questions(lines)

        if not questions:
            return jsonify({"error": "No questions could be extracted from this PDF."}), 422

        if not answer_key:
            return jsonify({"error": "No answer key could be found in this PDF."}), 422

        csv_content = build_csv(questions, answer_key)

        return Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=quiz.csv"},
        )

    except Exception as e:
        return jsonify({"error": f"Failed to process PDF: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=8080)
