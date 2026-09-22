# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3>=1.43", "streamlit"]
# ///
"""Paste a support ticket, read the drafted reply and the tickets it used.

Usage: uv run demo/app.py

Needs the same environment as demo/draft_reply.py. Re-launches itself under
`streamlit run` when started as a plain script.
"""

import os
import sys

import streamlit as st
import streamlit.runtime

if not streamlit.runtime.exists():
    os.execvp(sys.executable, [sys.executable, "-m", "streamlit", "run", __file__])

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from botocore.exceptions import ClientError  # noqa: E402
from draft_reply import draft  # noqa: E402

st.title("MLC support draft")
tenant = st.sidebar.text_input("Tenant (empty = all)")
variant = st.sidebar.selectbox("Variant", ["full", "customer"])
n = st.sidebar.slider("Past tickets", 1, 10, 5)
model_arn = st.sidebar.text_input("Model ARN", os.environ.get("ModelArn", ""))
question = st.text_area("New ticket", height=200)

if st.button("Draft reply") and question.strip():
    try:
        out = draft(question, tenant or None, variant, n, model_arn or None)
    except ClientError as e:
        st.error(str(e))
    else:
        st.subheader(f"Label: {out['label']}")
        st.markdown(out["draft"])
        for s in out["sources"]:
            with st.expander(f"{s['ticketId']} · {s['tenant']} · {s['variant']} · {s['score']:.2f}"):
                st.text(s["text"])
