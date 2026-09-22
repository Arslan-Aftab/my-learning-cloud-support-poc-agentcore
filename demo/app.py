# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3>=1.43", "streamlit"]
# ///
"""Paste a customer query, watch the search and the draft, edit and copy the reply.

Usage: uv run demo/app.py

Needs the same environment as demo/draft_reply.py. Re-launches itself under
`streamlit run` when started as a plain script.
"""

import json
import os
import sys

import streamlit as st
import streamlit.runtime

if not streamlit.runtime.exists():
    os.execvp(sys.executable, [sys.executable, "-m", "streamlit", "run", __file__])

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from botocore.exceptions import ClientError  # noqa: E402
from draft_reply import generate, retrieve  # noqa: E402

VARIANTS = {"Full ticket": "full", "Customer messages only": "customer"}
# ponytail: the three tenants of the README ingest step, not a live list from the Knowledge Base.
TENANTS = ["All tenants", "spf", "optalis", "stjudescare"]

st.title("MLC support draft")
missing = [k for k in ("KnowledgeBaseId", "GuardrailId", "GuardrailVersion", "SonnetModelArn", "HaikuModelArn") if k not in os.environ]
if missing:
    st.error(f"Missing in the environment: {', '.join(missing)}. Run `set -a; source .env; set +a` and restart.")
    st.stop()
model = st.sidebar.selectbox("Model", ["Sonnet", "Haiku"])
variant = VARIANTS[st.sidebar.selectbox("Ticket contents", list(VARIANTS))]
tenant = st.sidebar.selectbox("Tenant", TENANTS)
n = st.sidebar.slider("Past tickets to search", 1, 10, 5)
question = st.text_area("Paste the customer query", height=200, placeholder="The customer's message, as written.")

if "out" in st.session_state:
    st.warning("Draft reply clears the current draft and starts again.")

if st.button("Draft reply", type="primary") and question.strip():
    st.session_state.pop("out", None)
    try:
        with st.status("Searching past tickets…", expanded=True) as status:
            sources = retrieve(question, None if tenant == TENANTS[0] else tenant, variant, n)
            st.write(f"Found {len(sources)} past tickets. Generating the draft with {model}…")
            out = generate(question, sources, model)
            status.update(label="Draft ready", state="complete", expanded=False)
    except ClientError as e:
        st.error(str(e))
    else:
        st.session_state["out"] = {**out, "sources": sources}

if out := st.session_state.get("out"):
    if out["blocked"]:
        st.error("The Guardrail blocked the draft. Scores below the threshold are the cause.")
    st.subheader(f"Query type: {out['label']}")
    if out["notes"]:
        st.info(out["notes"])
    if out["grounding"]:
        st.caption("Guardrail grounding check  " + "  ·  ".join(
            f"{k.lower()} {v['score']:.2f} (threshold {v['threshold']:.2f}, {v['action'].lower()})"
            for k, v in out["grounding"].items()))
    text = st.text_area("Reply to the customer (edit before you copy)", out["draft"], height=300)
    # ponytail: JSON in a script tag, not an attribute, so quotes in the reply survive.
    st.iframe(
        f"<script>const reply = {json.dumps(text).replace('<', '\\u003c')};</script>"
        '<button onclick="navigator.clipboard.writeText(reply)">Copy reply</button>',
        height=40,
    )
    st.subheader("Past tickets used")
    for s in out["sources"]:
        with st.expander(f"{s['ticketId']} · {s['subject']} · {s['tenant']} · {s['variant']} · {s['score']:.2f}"):
            st.text(s["text"])
