import streamlit as st
import os

st.set_page_config(page_title="Final Deployment Test", layout="wide")

st.title("🚦 Streamlit Cloud Final Test")
st.write("This page tests if the server can see the configuration files.")
st.markdown("---")

# ===============================================================
# Test: Inspecting the file system on the server
# ===============================================================
st.header("File System Inspection")
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
            st.write("Contents of `config.toml`:")
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
