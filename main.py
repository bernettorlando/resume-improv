import streamlit as st
import google.generativeai as genai
import os
from pathlib import Path
import time
import tempfile # Import the tempfile module

# --- Configuration ---
st.set_page_config(page_title="Resume Improver with Gemini", layout="wide")
st.title("📄✨ Resume Improver using Gemini 2.5 Pro")
st.markdown("""
Paste your **current resume's LaTeX (.tex) code** below and upload a **PDF report** containing instructions or feedback for improvement.
Gemini 2.5 Pro will analyze both and generate an improved LaTeX version.
""")

# --- API Key Input ---
api_key = st.text_input("Enter your Google AI API Key:", type="password")

# --- Input Fields ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Paste Current Resume LaTeX Code")
    current_tex_code = st.text_area("Enter .tex code here:", height=400, key="tex_input")

with col2:
    st.subheader("2. Upload Instructions PDF")
    uploaded_pdf = st.file_uploader("Upload PDF report with improvement suggestions:", type="pdf", key="pdf_upload")

# --- Processing Button ---
st.divider()
submit_button = st.button("🚀 Generate Improved Resume LaTeX")

# --- Output Area ---
st.subheader("✨ Generated Improved LaTeX Code ✨")
output_area = st.empty() # Placeholder for the output

# --- Logic ---
if submit_button:
    if not api_key:
        st.warning("Please enter your Google AI API Key.")
        st.stop()
    if not current_tex_code:
        st.warning("Please paste your current resume's LaTeX code.")
        st.stop()
    if not uploaded_pdf:
        st.warning("Please upload the PDF instructions file.")
        st.stop()

    # --- Initialize variables for cleanup ---
    temp_pdf_path = None
    uploaded_gemini_file = None

    try:
        # --- Configure Gemini ---
        genai.configure(api_key=api_key)

        # --- Save Uploaded PDF to a Temporary File ---
        output_area.info("Preparing PDF for upload...")
        pdf_bytes = uploaded_pdf.getvalue()

        # Create a temporary file to store the PDF bytes
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_f:
            temp_f.write(pdf_bytes)
            temp_pdf_path = temp_f.name # Get the path to the temporary file

        # --- Upload PDF to Gemini using the temporary file path ---
        if temp_pdf_path:
            output_area.info(f"Uploading '{uploaded_pdf.name}' from temporary path...")
            uploaded_gemini_file = genai.upload_file(
                path=temp_pdf_path, # Pass the file PATH here
                display_name=uploaded_pdf.name,
                mime_type='application/pdf'
            )
            output_area.info(f"✅ PDF '{uploaded_pdf.name}' uploaded successfully to Gemini.")
            st.toast("PDF Uploaded!", icon="📄")
        else:
            st.error("❌ Failed to create a temporary file for the PDF.")
            st.stop()

        # --- Prepare for Gemini API Call ---
        model = genai.GenerativeModel('gemini-2.5-pro-exp-03-25')

        # --- Construct the Prompt (remains the same) ---
        prompt_parts = [
            "You are an expert LaTeX resume editor.",
            "You will be given the current LaTeX code for a resume and a PDF file containing instructions, feedback, or suggestions for improving that resume.",
            "\n**Task:** Analyze the instructions in the provided PDF file and apply them to the given LaTeX code to generate a new, complete, and improved version of the resume's LaTeX code.",
            "\n**Input Resume LaTeX Code:**\n```latex\n",
            current_tex_code,
            "\n```\n",
            "\n**Input Instructions PDF:**\n",
            uploaded_gemini_file, # Pass the handle to the uploaded file
            "\n**Output Requirements:**",
            "- Output ONLY the complete, modified LaTeX code for the improved resume.",
            "- Ensure the output is valid LaTeX that can be compiled directly.",
            "- Do NOT include any conversational text, explanations, or introductions/conclusions outside of the LaTeX code itself.",
            "- You may add comments within the LaTeX code (e.g., `% Gemini: Applied suggestion X from PDF`) if helpful, but the primary output must be the code.",
            "- Base your modifications strictly on the instructions found within the PDF document.",
        ]

        output_area.info("Generating improved LaTeX code with Gemini 2.5 Pro... This might take a moment.")
        with st.spinner("🧠 Gemini is thinking..."):
            # --- Call Gemini API ---
            response = model.generate_content(prompt_parts, stream=False)

        # --- Display Output ---
        if response and response.text:
            improved_tex_code = response.text
            # Clean potential markdown code block formatting
            if improved_tex_code.startswith("```latex"):
                 improved_tex_code = improved_tex_code[len("```latex"):].strip()
            if improved_tex_code.endswith("```"):
                improved_tex_code = improved_tex_code[:-len("```")].strip()

            output_area.code(improved_tex_code, language='latex')
            st.success("✅ Improved LaTeX code generated successfully!")
            st.toast("Generation Complete!", icon="🎉")
        else:
            # Check for safety ratings or other issues if text is empty
            try:
                 output_area.error(f"❌ Gemini did not return text content. Finish reason: {response.prompt_feedback}")
            except Exception:
                 output_area.error("❌ Gemini did not return text content. Response or text attribute might be missing.")
            # st.write("Full Gemini Response:", response) # Uncomment for debugging

    except Exception as e:
        st.error(f"An error occurred: {e}")
        output_area.error(f"❌ Failed to generate response. Error: {e}")

    finally:
        # --- Clean up the LOCAL temporary file ---
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            try:
                os.remove(temp_pdf_path)
                # output_area.info("Cleaned up local temporary PDF file.") # Optional
            except Exception as e:
                st.warning(f"⚠️ Could not delete the local temporary file '{temp_pdf_path}': {e}")

        # --- Clean up the file uploaded to GEMINI ---
        # --- Clean up the file uploaded to GEMINI ---
        if uploaded_gemini_file:
            try:
                # Use st.info for status messages that shouldn't overwrite the main output
                st.info(f"Cleaning up file '{uploaded_gemini_file.display_name}' on Gemini...")
                genai.delete_file(uploaded_gemini_file.name)
                # Use st.info here too!
                st.info("✅ Gemini file cleanup complete.")
                st.toast("Gemini file cleanup done.", icon="🗑️")
            except Exception as cleanup_err:
                st.warning(f"⚠️ Could not delete the file from Gemini: {cleanup_err}")


# --- Footer/Info ---
st.markdown("---")
st.caption("Powered by Google Gemini 2.5 Pro | Be mindful of API usage costs.")
