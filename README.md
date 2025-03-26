# Resume Improver with Gemini AI

A powerful Streamlit application that uses Google's Gemini 2.5 Pro AI to improve your LaTeX resume based on feedback and instructions.

## Features

- **LaTeX Resume Enhancement**: Upload your existing LaTeX resume code and receive AI-powered improvements
- **PDF Feedback Integration**: Upload PDF documents containing feedback or instructions for resume improvement
- **Smart Analysis**: Gemini AI analyzes both your resume and feedback to generate optimized LaTeX code
- **User-Friendly Interface**: Clean, intuitive Streamlit interface for easy interaction
- **Secure API Key Management**: Safe handling of Google AI API keys

## Prerequisites

- Python 3.8 or higher
- Google AI API Key (for Gemini 2.5 Pro)
- LaTeX distribution installed on your system

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd resume-improv
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

3. Install required packages:
```bash
pip install -r requirements.txt
```

## Usage

1. Start the application:
```bash
streamlit run main.py
```

2. Open your web browser and navigate to the provided local URL (typically http://localhost:8501)

3. In the application:
   - Enter your Google AI API Key
   - Paste your current resume's LaTeX code in the text area
   - Upload a PDF file containing improvement suggestions or feedback
   - Click "Generate Improved Resume LaTeX" to get the enhanced version

4. The improved LaTeX code will be displayed in the output area

## Important Notes

- Keep your API key secure and never share it publicly
- The application requires an active internet connection for Gemini AI functionality
- Make sure your LaTeX code is valid before submitting
- The PDF feedback should be clear and specific for best results

## Dependencies

- streamlit
- google-generativeai
- pathlib
- tempfile
- os