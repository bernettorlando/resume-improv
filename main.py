import streamlit as st
import google.generativeai as genai
import os
from pathlib import Path
import time
import tempfile
import subprocess
import shutil
# Import Google API exceptions
from google.api_core import exceptions as google_exceptions

# Initialize session state variables
if 'improved_tex_code' not in st.session_state:
    st.session_state.improved_tex_code = None
if 'pdf_bytes' not in st.session_state:
    st.session_state.pdf_bytes = None
if 'retry_count' not in st.session_state:
    st.session_state.retry_count = 0
# New session state variables for API key management
if 'api_key' not in st.session_state:
    st.session_state.api_key = None
if 'api_source' not in st.session_state: # 'env', 'user', None
    st.session_state.api_source = None
if 'show_api_input' not in st.session_state:
    st.session_state.show_api_input = False

# --- Configuration ---
st.set_page_config(page_title="Resume Improver with Gemini", layout="wide")
st.title("📄✨ Resume Improver using Gemini 2.5 Pro")
st.markdown("""
Paste your **current resume's LaTeX (.tex) code** below and upload a **PDF report** containing instructions or feedback for improvement.
Gemini 2.5 Pro will analyze both and generate an improved LaTeX version.
""")

# --- Load Default Resume Content ---
default_resume_content = ""
try:
    with open("default_resume.txt", "r") as f:
        default_resume_content = f.read()
except FileNotFoundError:
    st.warning("⚠️ default_resume.txt not found. Unable to load default content.")

# --- API Key Handling ---
# Try environment variable first
env_api_key = os.getenv("GOOGLE_API_KEY")

# Determine initial API key state only once or if reset
if st.session_state.api_source is None:
    if env_api_key:
        st.session_state.api_key = env_api_key
        st.session_state.api_source = 'env'
        st.session_state.show_api_input = False
        st.info("🔑 Using API key from environment variable.", icon="🔒")
    else:
        st.session_state.show_api_input = True # No env key, need user input

# Display API key input field if needed
user_entered_key = None
if st.session_state.show_api_input:
    user_entered_key = st.text_input("Enter your Google AI API Key:", type="password", key="api_key_input")
    if user_entered_key:
        # If user provides a key, use it and update state
        st.session_state.api_key = user_entered_key
        st.session_state.api_source = 'user'

# --- Input Fields ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Paste Current Resume LaTeX Code")
    # Use the loaded content as the default value
    current_tex_code = st.text_area(
        "Enter .tex code here:",
        value=default_resume_content, # Set default value here
        height=400,
        key="tex_input"
    )

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
    # Check if we have a valid API key to use
    if not st.session_state.api_key:
        st.warning("Please provide a Google AI API Key.")
        st.stop()
    if not current_tex_code:
        st.warning("Please paste your current resume's LaTeX code.")
        st.stop()
    if not uploaded_pdf:
        st.warning("Please upload the PDF instructions file.")
        st.stop()

    # Reset retry count for the main generation process
    st.session_state.retry_count = 0 # Reset for initial generation

    # --- Initialize variables for cleanup ---
    temp_pdf_path = None
    uploaded_gemini_file = None
    temp_dir = None

    # Flag to check if API key needs verification/change
    api_key_valid = True

    while st.session_state.retry_count < 3:  # Maximum 3 retries for LaTeX compilation
        try:
            # --- Configure Gemini ---
            # Configure with the key we have (either env or user)
            genai.configure(api_key=st.session_state.api_key)

            # --- Save Uploaded PDF to a Temporary File ---
            # Check if PDF needs uploading (only first time or if changed)
            # This part needs careful handling if uploaded_pdf can change between retries
            # Assuming it doesn't change within the retry loop for now.
            if st.session_state.retry_count == 0: # Only upload on first attempt
                output_area.info("Preparing PDF for upload...")
                pdf_bytes_val = uploaded_pdf.getvalue() # Use a different variable name

                # Create a temporary file to store the PDF bytes
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_f:
                    temp_f.write(pdf_bytes_val)
                    temp_pdf_path = temp_f.name # Get the path to the temporary file

                # --- Upload PDF to Gemini using the temporary file path ---
                if temp_pdf_path:
                    output_area.info(f"Uploading '{uploaded_pdf.name}' from temporary path...")
                    # Test API connection early with a simple call if possible,
                    # otherwise, the first generate_content call will test it.
                    # For now, we proceed to upload.
                    uploaded_gemini_file = genai.upload_file(
                        path=temp_pdf_path, # Pass the file PATH here
                        display_name=uploaded_pdf.name,
                        mime_type='application/pdf'
                    )
                    output_area.info(f"✅ PDF '{uploaded_pdf.name}' uploaded successfully to Gemini.")
                    st.toast("PDF Uploaded!", icon="📄")
                else:
                    st.error("❌ Failed to create a temporary file for the PDF.")
                    st.stop() # Stop if PDF upload fails critically

            # --- Prepare for Gemini API Call ---
            model = genai.GenerativeModel('gemini-2.5-pro-exp-03-25') # Consider making model instantiation outside loop if safe

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

            output_area.info(f"Attempt {st.session_state.retry_count + 1}: Generating improved LaTeX code...")
            with st.spinner("🧠 Gemini is thinking..."):
                # --- Call Gemini API ---
                response = model.generate_content(prompt_parts, stream=False)

            # --- Process Response ---
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
                        
                        # Break the retry loop on successful LaTeX compilation
                        api_key_valid = True # Key worked for this generation
                        break # Exit the while loop for retries
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

            # --- Handle potential empty response from Gemini ---
            elif not response or not response.text:
                 # Check for safety ratings or other issues if text is empty
                 try:
                      # Log feedback if available
                      feedback_info = f"Finish reason: {response.prompt_feedback}" if response else "No response object."
                      output_area.error(f"❌ Gemini did not return text content. {feedback_info}")
                 except Exception as feedback_err:
                      output_area.error(f"❌ Gemini did not return text content. Error accessing feedback: {feedback_err}")
                 api_key_valid = False # Treat no response as potential key issue too
                 break # Exit retry loop if Gemini gives no content

        # --- Handle API specific errors ---
        except (google_exceptions.PermissionDenied, google_exceptions.ResourceExhausted) as api_error:
            st.error(f"API Error: {api_error}")
            api_key_valid = False # Mark key as invalid
            if st.session_state.api_source == 'env':
                st.warning("⚠️ The default API key failed (Permission Denied or Rate Limit Exceeded). Please enter your own key below.")
                st.session_state.show_api_input = True
                st.session_state.api_key = None # Clear the invalid env key
                st.session_state.api_source = None # Reset source
                st.experimental_rerun() # Rerun to show input and stop current execution
            else: # Error occurred with user-provided key
                st.error("❌ Your provided API key failed. Please check it and try again.")
                # Optionally clear the key input or leave it for user correction
                st.session_state.api_key = None # Clear the invalid user key
                st.session_state.api_source = None
                st.session_state.show_api_input = True # Make sure input is shown
                st.experimental_rerun() # Rerun to ensure UI updates
            break # Exit retry loop on API error

        # --- Handle other general exceptions ---
        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")
            output_area.error(f"❌ Failed during generation. Error: {e}")
            api_key_valid = False # Unsure about key validity, but stop
            break # Exit retry loop on general error

        finally:
            # --- Clean up ---
            # Clean up local temp PDF regardless of success/failure inside the loop
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                try:
                    os.remove(temp_pdf_path)
                    temp_pdf_path = None # Reset path after deletion
                except Exception as e:
                    st.warning(f"⚠️ Could not delete the local temporary file: {e}")

            # Clean up Gemini file only if generation was attempted and failed,
            # or after successful completion outside the loop.
            # Deleting it here might cause issues on retry if needed.
            # Let's move Gemini file cleanup outside the loop.

            # Clean up LaTeX temp dir if it exists
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    temp_dir = None # Reset path
                except Exception as e:
                    st.warning(f"⚠️ Could not delete temporary LaTeX directory: {e}")

    # --- After the retry loop ---
    # Clean up the file uploaded to GEMINI only after the loop finishes (success or max retries)
    if uploaded_gemini_file:
        try:
            st.info(f"Cleaning up file '{uploaded_gemini_file.display_name}' on Gemini...")
            genai.delete_file(uploaded_gemini_file.name)
            st.info("✅ Gemini file cleanup complete.")
            st.toast("Gemini file cleanup done.", icon="🗑️")
        except Exception as cleanup_err:
            st.warning(f"⚠️ Could not delete the file from Gemini: {cleanup_err}")

# --- Footer/Info ---
st.markdown("---")
st.caption("Powered by Google Gemini 2.5 Pro | Be mindful of API usage costs.")

# Test
