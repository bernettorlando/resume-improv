import streamlit as st
import google.generativeai as genai
import os
from pathlib import Path
import time
import tempfile
import subprocess
import shutil

# Initialize session state variables
if 'improved_tex_code' not in st.session_state:
    st.session_state.improved_tex_code = None
if 'pdf_bytes' not in st.session_state:
    st.session_state.pdf_bytes = None
if 'retry_count' not in st.session_state:
    st.session_state.retry_count = 0

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

# Clear previous output when generate button is clicked
if submit_button:
    # Clear session state
    st.session_state.improved_tex_code = None
    st.session_state.pdf_bytes = None
    st.session_state.retry_count = 0
    # Clear output area
    output_area.empty()

# Display stored LaTeX code if it exists
if st.session_state.improved_tex_code:
    with st.expander("📝 View Generated LaTeX Code", expanded=False):
        st.code(st.session_state.improved_tex_code, language='latex')
    st.success("✅ Improved LaTeX code generated successfully!")
    
    # Display download button if PDF exists
    if st.session_state.pdf_bytes:
        st.download_button(
            label="📥 Download PDF",
            data=st.session_state.pdf_bytes,
            file_name="improved_resume.pdf",
            mime="application/pdf"
        )
        st.success("✅ PDF generated successfully!")

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

    # Reset retry count when starting new generation
    st.session_state.retry_count = 0

    # --- Initialize variables for cleanup ---
    temp_pdf_path = None
    uploaded_gemini_file = None
    temp_dir = None

    while st.session_state.retry_count < 3:  # Maximum 3 retries
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

            # --- Construct the Prompt ---
            prompt_parts = [
                "You are an expert LaTeX resume editor.",
                "You will be given the current LaTeX code for a resume and a PDF file containing instructions, feedback, or suggestions for improving that resume.",
                "\n**Task:** Analyze the instructions in the provided PDF file and apply them to the given LaTeX code to generate a new, complete, and improved version of the resume's LaTeX code.",
                "\n**Input Resume LaTeX Code:**\n```latex\n",
                current_tex_code,
                "\n```\n",
                "\n**Input Instructions PDF:**\n",
                uploaded_gemini_file,
                "\n**Output Requirements:**",
                "- Output ONLY the complete, modified LaTeX code for the improved resume.",
                "- Ensure the output is valid LaTeX that can be compiled directly.",
                "- Do NOT include any conversational text, explanations, or introductions/conclusions outside of the LaTeX code itself.",
                "- You may add comments within the LaTeX code (e.g., `% Gemini: Applied suggestion X from PDF`) if helpful, but the primary output must be the code.",
                "- Base your modifications strictly on the instructions found within the PDF document.",
            ]

            # Add error context if this is a retry
            if st.session_state.retry_count > 0:
                prompt_parts.extend([
                    "\n**Previous Attempt Error:**",
                    "The previous LaTeX code failed to compile. Here are the error logs:",
                    "```text",
                    st.session_state.last_error,
                    "```",
                    "\nPlease fix the LaTeX code to address these compilation errors.",
                ])

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

                # --- Create temporary directory for LaTeX compilation ---
                temp_dir = tempfile.mkdtemp()
                tex_file_path = os.path.join(temp_dir, "resume.tex")
                pdf_file_path = os.path.join(temp_dir, "resume.pdf")

                # --- Write the LaTeX code to a file ---
                with open(tex_file_path, "w") as f:
                    f.write(improved_tex_code)

                # --- Compile LaTeX to PDF ---
                try:
                    # Run pdflatex and capture output
                    result = subprocess.run(
                        ["pdflatex", "-interaction=nonstopmode", "-output-directory", temp_dir, tex_file_path],
                        capture_output=True,
                        text=True,
                        check=False  # Don't raise exception immediately
                    )
                    
                    # --- Check if PDF was generated ---
                    if os.path.exists(pdf_file_path):
                        # --- Read the PDF file ---
                        with open(pdf_file_path, "rb") as pdf_file:
                            pdf_bytes = pdf_file.read()
                        
                        # Store the improved LaTeX code and PDF in session state
                        st.session_state.improved_tex_code = improved_tex_code
                        st.session_state.pdf_bytes = pdf_bytes
                        
                        # Display the results
                        with st.expander("📝 View Generated LaTeX Code", expanded=False):
                            st.code(improved_tex_code, language='latex')
                        st.success("✅ Improved LaTeX code generated successfully!")
                        st.toast("Generation Complete!", icon="🎉")
                        
                        # Create download button
                        st.download_button(
                            label="📥 Download PDF",
                            data=pdf_bytes,
                            file_name="improved_resume.pdf",
                            mime="application/pdf"
                        )
                        st.success("✅ PDF generated successfully!")
                        
                        # Break the retry loop on success
                        break
                    else:
                        # Store error information for retry
                        error_msg = "LaTeX Compilation Errors:\n"
                        if result.stdout:
                            error_msg += f"Output:\n{result.stdout}\n"
                        if result.stderr:
                            error_msg += f"Errors:\n{result.stderr}\n"
                        if result.returncode != 0:
                            error_msg += f"Return code: {result.returncode}"
                        st.session_state.last_error = error_msg
                        
                        # Increment retry count
                        st.session_state.retry_count += 1
                        
                        if st.session_state.retry_count < 3:
                            st.warning(f"⚠️ LaTeX compilation failed. Retrying with error context... (Attempt {st.session_state.retry_count}/3)")
                            time.sleep(2)  # Brief pause before retry
                        else:
                            st.error("❌ Maximum retries reached. Please check the LaTeX code for errors.")
                            st.text("LaTeX Compilation Output:")
                            st.code(result.stdout, language="text")
                            st.text("LaTeX Compilation Errors:")
                            st.code(result.stderr, language="text")
                            if result.returncode != 0:
                                st.error(f"❌ LaTeX compilation failed with return code {result.returncode}")
                except Exception as e:
                    st.error(f"❌ Error generating PDF: {e}")
                    break

            else:
                # Check for safety ratings or other issues if text is empty
                try:
                     output_area.error(f"❌ Gemini did not return text content. Finish reason: {response.prompt_feedback}")
                except Exception:
                     output_area.error("❌ Gemini did not return text content. Response or text attribute might be missing.")
                break

        except Exception as e:
            st.error(f"An error occurred: {e}")
            output_area.error(f"❌ Failed to generate response. Error: {e}")
            break

        finally:
            # --- Clean up the LOCAL temporary file ---
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                try:
                    os.remove(temp_pdf_path)
                except Exception as e:
                    st.warning(f"⚠️ Could not delete the local temporary file '{temp_pdf_path}': {e}")

            # --- Clean up the file uploaded to GEMINI ---
            if uploaded_gemini_file:
                try:
                    st.info(f"Cleaning up file '{uploaded_gemini_file.display_name}' on Gemini...")
                    genai.delete_file(uploaded_gemini_file.name)
                    st.info("✅ Gemini file cleanup complete.")
                    st.toast("Gemini file cleanup done.", icon="🗑️")
                except Exception as cleanup_err:
                    st.warning(f"⚠️ Could not delete the file from Gemini: {cleanup_err}")

            # --- Clean up temporary directory ---
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    st.warning(f"⚠️ Could not delete temporary directory '{temp_dir}': {e}")

# --- Footer/Info ---
st.markdown("---")
st.caption("Powered by Google Gemini 2.5 Pro | Be mindful of API usage costs.")

# Test
