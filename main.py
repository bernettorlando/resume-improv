import streamlit as st
import google.generativeai as genai
import os
from pathlib import Path
import time
import tempfile
import subprocess
import shutil
import base64
import fitz # PyMuPDF for image preview
import io   # For handling image bytes
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
if 'change_summary' not in st.session_state:
    st.session_state.change_summary = None
if 'request_summary' not in st.session_state: # Track checkbox state
    st.session_state.request_summary = False

# --- Configuration ---
st.set_page_config(page_title="Resume Improver with Gemini", layout="wide")
st.title("📄✨ Resume Improver using Gemini 2.5 Pro")
st.markdown("""
Paste your **current resume's LaTeX (.tex) code** below. Optionally upload a **PDF report** with improvement suggestions or provide a job description.
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
    st.subheader("2. (Optional) Upload Instructions PDF")
    uploaded_pdf = st.file_uploader("Upload PDF report with improvement suggestions (optional):", type="pdf", key="pdf_upload")

    st.subheader("3. Paste Job Description")
    job_description = st.text_area(
        "Paste the target job description here for tailored improvements:",
        height=200,
        key="job_desc_input"
    )

# --- Options --- (Moved checkbox here)
st.subheader("Options")
st.session_state.request_summary = st.checkbox("Include summary of changes?", value=st.session_state.request_summary, key="summary_checkbox")

# --- Processing Button ---
st.divider()
submit_button = st.button("🚀 Generate Improved Resume LaTeX")

# --- Output Area ---
st.subheader("✨ Generated Improved LaTeX Code ✨")
output_area = st.empty() # Placeholder for the output
summary_area = st.empty() # Placeholder for the summary

# Clear previous output when generate button is clicked
if submit_button:
    # Clear session state
    st.session_state.improved_tex_code = None
    st.session_state.pdf_bytes = None
    st.session_state.retry_count = 0
    st.session_state.change_summary = None # Clear summary
    # Clear output areas
    output_area.empty()
    summary_area.empty()

# Display stored LaTeX code and summary if they exist
if st.session_state.get('improved_tex_code'): # Use .get for safety
    with st.expander("📝 View Generated LaTeX Code", expanded=False):
        st.code(st.session_state.improved_tex_code, language='latex')
    st.success("✅ Improved LaTeX code generated successfully!")

    # Display the summary ONLY if it exists (i.e., was requested and generated)
    if st.session_state.get('change_summary'):
        with st.expander("📊 Summary of Changes", expanded=True):
             st.markdown(st.session_state.change_summary)

    # Display PDF preview and download button if PDF exists
    if st.session_state.get('pdf_bytes'):
        st.success("✅ PDF generated successfully!")

        # --- PDF Preview Expander ---
        with st.expander("📄 Preview Generated PDF (All Pages)", expanded=False):
            try:
                pdf_doc = fitz.open(stream=st.session_state.pdf_bytes, filetype="pdf")
                if pdf_doc.page_count > 0:
                    for page_num in range(pdf_doc.page_count):
                        # Render the current page
                        page = pdf_doc.load_page(page_num)
                        # Increase DPI for better quality
                        pix = page.get_pixmap(dpi=300)
                        img_bytes = pix.tobytes("png") # Convert pixmap to PNG bytes
                        # Display the image
                        st.image(io.BytesIO(img_bytes),
                                 caption=f"Page {page_num + 1} of {pdf_doc.page_count}",
                                 use_container_width=True)
                else:
                    st.warning("PDF is empty, cannot generate preview.")
                pdf_doc.close()
            except Exception as e:
                st.error(f"Error generating PDF preview: {e}")

        # --- Download Button ---
        st.download_button(
            label="📥 Download PDF",
            data=st.session_state.pdf_bytes,
            file_name="improved_resume.pdf",
            mime="application/pdf"
        )

# --- Logic ---
if submit_button:
    # Check if we have a valid API key to use
    if not st.session_state.api_key:
        st.warning("Please provide a Google AI API Key.")
        st.stop()
    if not current_tex_code:
        st.warning("Please paste your current resume's LaTeX code.")
        st.stop()
    if not job_description:
        st.warning("Please provide a job description for tailored improvements.")
        st.stop()

    # Reset retry count for the main generation process
    st.session_state.retry_count = 0 # Reset for initial generation

    # --- Initialize variables for cleanup ---
    temp_pdf_path = None
    uploaded_gemini_file = None
    temp_dir = None

    # Flag to check if API key needs verification/change
    api_key_valid = True

    # Get the checkbox state at the time of submission
    summary_requested = st.session_state.request_summary

    while st.session_state.retry_count < 3:  # Maximum 3 retries for LaTeX compilation
        try:
            # --- Configure Gemini ---
            # Configure with the key we have (either env or user)
            genai.configure(api_key=st.session_state.api_key)

            # --- Save Uploaded PDF to a Temporary File ---
            # Only process PDF if it was uploaded
            if uploaded_pdf and st.session_state.retry_count == 0: # Only upload on first attempt
                output_area.info("Preparing PDF for upload...")
                pdf_bytes_val = uploaded_pdf.getvalue()

                # Create a temporary file to store the PDF bytes
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_f:
                    temp_f.write(pdf_bytes_val)
                    temp_pdf_path = temp_f.name

                # --- Upload PDF to Gemini using the temporary file path ---
                if temp_pdf_path:
                    output_area.info(f"Uploading '{uploaded_pdf.name}' from temporary path...")
                    uploaded_gemini_file = genai.upload_file(
                        path=temp_pdf_path,
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

            # --- Construct the Prompt --- (Conditionally add summary instructions)
            if uploaded_pdf:
                # Use PDF-based prompt
                prompt_parts = [
                    "You are an expert LaTeX resume editor specializing in ATS-friendly resumes tailored for specific job descriptions.",
                    "You will be given the current LaTeX code for a resume, a PDF file with improvement feedback, and a target job description.",
                    "\n**Task:** Analyze the instructions in the PDF and the requirements in the job description. Apply relevant improvements to the given LaTeX code to create an optimized, ATS-friendly version tailored for the target role.",
                    "\n**Input Resume LaTeX Code:**\n```latex\n",
                    current_tex_code,
                    "\n```\n",
                    "\n**Input Instructions PDF:**\n",
                    uploaded_gemini_file,
                ]
            else:
                # Use general instructions prompt
                prompt_parts = [
                    "You are an expert resume optimizer specializing in tailoring resumes to pass Applicant Tracking Systems (ATS) and appeal to recruiters.",
                    "Your task is to revise the provided resume based on the job description. Follow these instructions precisely:",
                    "\n**Input Resume LaTeX Code:**\n```latex\n",
                    current_tex_code,
                    "\n```\n",
                    "\n**Target Job Description:**\n```text\n",
                    job_description,
                    "\n```\n",
                    "\n**Instructions:**",
                    "1. ATS Compliance & Searchability:",
                    "- Ensure contact information is easily parsable (Name, Phone, Email, LinkedIn URL if available).",
                    "- Find and incorporate the exact job title from the job description.",
                    "- Include a concise summary/objective section highlighting relevant qualifications.",
                    "- Verify presence of standard sections (Work Experience, Education) with clear headings.",
                    "- Match education requirements if specified in the job description.",
                    "- Use consistent date formatting (MM/YYYY or Month YYYY).",
                    "2. Skills Integration:",
                    "- Identify and incorporate hard skills from the job description using exact wording.",
                    "- Weave soft skills naturally into work experience and summary.",
                    "3. Content & Recruiter Appeal:",
                    "- Include quantifiable achievements and results in bullet points.",
                    "- Maintain professional, positive, and action-oriented language.",
                    "- Keep content concise and under 1000 words for non-executive roles.",
                    "- Ensure experience level matches job requirements.",
                    "4. Formatting:",
                    "- Avoid columns, tables, or images that can confuse ATS.",
                    "- Keep bullet points and paragraphs concise (under 40 words).",
                    "- Use standard, readable fonts.",
                    "- Avoid information in headers/footers.",
                ]

            # Define Output Requirements based on checkbox
            output_reqs = [
                "\n**Output Requirements:**",
                "- Output ONLY the complete, modified LaTeX code for the improved resume.",
                "- Ensure the LaTeX output is valid and compilable.",
                "- Tailor content/keywords to the job description.",
                "- Do NOT include any conversational text, explanations, or introductions/conclusions outside the LaTeX code itself.",
                "- Use comments within LaTeX (e.g., `% Gemini: Applied suggestion X / Tailored for JD keyword Y`) if helpful.",
            ]
            if summary_requested:
                output_reqs.insert(2, "1a. After the LaTeX code block, add a separator line exactly like this: `--- SUMMARY ---`")
                output_reqs.insert(3, "1b. After the separator, provide a brief bulleted list summarizing the key changes made based on the feedback PDF and job description (if provided). Mention specific keywords tailored if applicable.")
                # Adjust numbering/phrasing if needed, but main point is conditional inclusion
                output_reqs[-2] = "- Do NOT include any conversational text, explanations, or introductions/conclusions outside the LaTeX code itself OR the summary section."

            formatting_reqs = [
                "\n**Formatting Requirements:**",
                "- Maintain ATS compatibility (standard commands, avoid complex formatting).",
                "- Ensure excellent readability with appropriate vertical spacing (`\\vspace`, `\\itemsep`, etc.).",
                "- Use standard fonts and maintain clear document hierarchy.",
            ]

            prompt_parts.extend(output_reqs)
            prompt_parts.extend(formatting_reqs)

            # Add error context if this is a retry (Conditionally mention summary)
            if st.session_state.retry_count > 0:
                error_prompt_addition = [
                    "\n**Previous Attempt Error:**",
                    "The previous LaTeX code failed to compile. Here are the error logs:",
                    "```text",
                    st.session_state.last_error,
                    "```",
                ]
                if summary_requested:
                    error_prompt_addition[-1] += " Remember to output the corrected LaTeX code followed by `--- SUMMARY ---` and a summary of changes."
                prompt_parts.extend(error_prompt_addition)

            output_area.info(f"Attempt {st.session_state.retry_count + 1}: Generating improved LaTeX code{' and summary' if summary_requested else ''}...")
            with st.spinner("🧠 Gemini is thinking..."):
                response = model.generate_content(prompt_parts, stream=False)

            # --- Process Response --- (Updated for conditional summary)
            if response and response.text:
                full_response_text = response.text
                separator = "--- SUMMARY ---"
                change_summary = None # Default to no summary
                improved_tex_code = full_response_text # Assume full response is LaTeX initially

                if summary_requested:
                    if separator in full_response_text:
                        parts = full_response_text.split(separator, 1)
                        improved_tex_code = parts[0].strip()
                        change_summary = parts[1].strip()
                    else:
                        # Summary was requested but separator not found
                        st.warning("⚠️ Summary was requested, but Gemini did not provide a summary separator. Displaying full response as LaTeX.")
                        # Keep improved_tex_code as the full response
                        change_summary = None # Ensure summary is None
                else:
                    # Summary was not requested, ensure change_summary is None
                    change_summary = None
                    # improved_tex_code is already the full response

                # Clean potential markdown code block formatting from LaTeX part
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
                        
                        # Store results in session state (conditionally includes summary)
                        st.session_state.improved_tex_code = improved_tex_code
                        st.session_state.pdf_bytes = pdf_bytes
                        st.session_state.change_summary = change_summary # Store None if no summary
                        
                        # Display the results
                        with st.expander("📝 View Generated LaTeX Code", expanded=False):
                            st.code(improved_tex_code, language='latex')
                        st.success("✅ Improved LaTeX code generated successfully!")

                        # Display the summary
                        if st.session_state.get('change_summary'):
                            with st.expander("📊 Summary of Changes", expanded=True):
                                 st.markdown(st.session_state.change_summary)
                        summary_area.empty() # Clear placeholder if successful

                        st.toast("Generation Complete!", icon="🎉")

                        # --- PDF Preview Expander (Success Case) ---
                        st.success("✅ PDF generated successfully!")
                        with st.expander("📄 Preview Generated PDF (All Pages)", expanded=False):
                            try:
                                pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                                if pdf_doc.page_count > 0:
                                    for page_num in range(pdf_doc.page_count):
                                        # Render the current page
                                        page = pdf_doc.load_page(page_num)
                                        # Increase DPI for better quality
                                        pix = page.get_pixmap(dpi=300)
                                        img_bytes = pix.tobytes("png") # Convert pixmap to PNG bytes
                                        # Display the image
                                        st.image(io.BytesIO(img_bytes),
                                                 caption=f"Page {page_num + 1} of {pdf_doc.page_count}",
                                                 use_container_width=True)
                                else:
                                    st.warning("PDF is empty, cannot generate preview.")
                                pdf_doc.close()
                            except Exception as e:
                                st.error(f"Error generating PDF preview: {e}")

                        # Create download button
                        st.download_button(
                            label="📥 Download PDF",
                            data=pdf_bytes,
                            file_name="improved_resume.pdf",
                            mime="application/pdf"
                        )
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

            # Clean up LaTeX temp dir if it exists
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    temp_dir = None # Reset path
                except Exception as e:
                    st.warning(f"⚠️ Could not delete temporary LaTeX directory: {e}")

    # --- After the retry loop ---
    # Clean up the file uploaded to GEMINI only if one was uploaded
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
