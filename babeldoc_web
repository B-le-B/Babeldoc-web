import streamlit as st
import os

st.set_page_config(page_title="Final Deployment Test", layout="wide")

st.title("🚦 Streamlit Cloud Final Test")
st.write("This page tests the two most critical functions: File System Access and Static File Serving.")
st.markdown("---")

# ===============================================================
# Test 1: Displaying an image from the /static/ directory
# ===============================================================
st.header("Test 1: Static File Serving")
st.write("Attempting to display `test_image.png` from the `static` folder...")

image_url = "/static/test_image.png"

try:
    st.image(image_url, caption="If you see this image, static file serving is WORKING.", width=200)
    st.success("✅ `st.image()` seems to have rendered without a backend error.")
except Exception as e:
    st.error(f"❌ `st.image()` crashed with a Python error: {e}")

st.write("You can also try to access the image directly at this link:")
st.markdown(f"[{image_url}]({image_url})")


st.markdown("---")

# ===============================================================
# Test 2: Inspecting the file system on the server
# ===============================================================
st.header("Test 2: File System Inspection")
try:
    cwd = os.getcwd()
    st.write(f"**Current Working Directory:** `{cwd}`")

    st.subheader("Contents of Current Directory (`.`):")
    root_contents = os.listdir(cwd)
    st.code("\n".join(sorted(root_contents)), language="text")

    # Check for .streamlit directory
    st.subheader("`.streamlit` Directory Check:")
    streamlit_dir_path = os.path.join(cwd, ".streamlit")
    if os.path.isdir(streamlit_dir_path):
        st.success("✅ Found `.streamlit` directory.")
        config_path = os.path.join(streamlit_dir_path, "config.toml")
        if os.path.exists(config_path):
            st.success("✅ Found `config.toml` inside.")
            with open(config_path, 'r') as f:
                st.code(f.read(), language='toml')
        else:
            st.error("❌ `config.toml` NOT FOUND inside `.streamlit`.")
    else:
        st.error("❌ Directory `.streamlit` NOT FOUND.")

    # Check for static directory
    st.subheader("`static` Directory Check:")
    static_dir_path = os.path.join(cwd, "static")
    if os.path.isdir(static_dir_path):
        st.success("✅ Found `static` directory.")
        st.write("Contents:")
        static_contents = os.listdir(static_dir_path)
        st.code("\n".join(sorted(static_contents)), language="text")
    else:
        st.error("❌ Directory `static` NOT FOUND.")

except Exception as e:
    st.error(f"A critical error occurred: {e}")
