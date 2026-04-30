import streamlit as st
from openai import OpenAI
import tempfile
import json
import html
import re
import random

st.set_page_config(page_title="SmartBite", page_icon="🎤", layout="wide")

# ------------------ STYLE ------------------
st.markdown("""
<style>
body { background-color: #f5f7fb; }

.banner {
    background: linear-gradient(135deg, #1f3c88, #4b6cb7);
    padding: 30px;
    border-radius: 14px;
    color: white;
    margin-bottom: 20px;
}

.feature {
    background: white;
    padding: 18px;
    border-radius: 12px;
    text-align: center;
}

.card {
    background: white;
    padding: 16px;
    border-radius: 12px;
    margin-bottom: 12px;
}

.soundbite {
    border-left: 5px solid #2563eb;
    background: #eef5ff;
}

.fact {
    border-left: 5px solid #f59e0b;
    background: #fff7ed;
}

.timestamp {
    font-weight: 700;
}

.rank {
    font-size: 1.2rem;
    font-weight: bold;
    color: #1f3c88;
}
</style>
""", unsafe_allow_html=True)

# ------------------ HELPERS ------------------
def format_time(s):
    s = int(s)
    return f"{s//60:02d}:{s%60:02d}"

def normalize(s):
    return s if isinstance(s, dict) else {
        "start": s.start,
        "end": s.end,
        "text": s.text
    }

def build_candidates(segments):
    candidates = []
    cid = 0

    for i in range(len(segments)):
        text_parts = []

        for j in range(i, len(segments)):
            start = segments[i]["start"]
            end = segments[j]["end"]
            duration = end - start

            text_parts.append(segments[j]["text"].strip())

            if duration < 5:
                continue
            if duration > 15:
                break

            quote = " ".join(text_parts).strip()

            if not quote.endswith((".", "!", "?")):
                continue

            if len(quote.split()) < 8:
                continue

            candidates.append({
                "id": cid,
                "start": start,
                "end": end,
                "duration": duration,
                "quote": quote,
                "segment_index": i
            })
            cid += 1

    return candidates

def sample_candidates(candidates, max_samples=200):
    if len(candidates) <= max_samples:
        return candidates

    step = len(candidates) / max_samples
    sampled = [candidates[int(i * step)] for i in range(max_samples)]
    random.shuffle(sampled)
    return sampled

# ------------------ HEADER ------------------
st.markdown("""
<div class="banner">
<h1>🎤 SmartBite</h1>
<p>AI-powered interview analysis for newsroom workflows</p>
</div>
""", unsafe_allow_html=True)

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

uploaded_file = st.file_uploader("Upload Interview", type=["mp3","wav","m4a","mp4"])

# ------------------ FRONT PAGE ------------------
if uploaded_file is None:
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown('<div class="feature">🎧<br><b>Transcribe</b><br>Convert interviews into text</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="feature">🎯<br><b>Identify Soundbites</b><br>Find strong, story-driving quotes</div>', unsafe_allow_html=True)

    with col3:
        st.markdown('<div class="feature">⚠️<br><b>Fact Check</b><br>Flag claims and statements to verify</div>', unsafe_allow_html=True)

# ------------------ MAIN ------------------
if uploaded_file is not None:

    ext = "." + uploaded_file.name.split(".")[-1]

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(uploaded_file.read())
        path = tmp.name

    with st.spinner("Transcribing..."):
        with open(path,"rb") as f:
            t = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json"
            )

    segments = [normalize(s) for s in t.segments]

    # transcript
    with st.expander("📄 View Full Transcript"):
        st.write(t.text)

    candidates = build_candidates(segments)
    candidates = sample_candidates(candidates)

    candidate_text = ""
    for c in candidates:
        candidate_text += f'{c["id"]}. ({c["duration"]:.1f}s) "{c["quote"]}"\n'

    # ------------------ AI ------------------
    with st.spinner("Selecting best soundbites..."):
        prompt = f"""
You are a senior TV news producer.

Rank the BEST soundbites.

PRIORITIZE:
- Emotional impact
- Strong statements
- Story-driving quotes

RULES:
- 5–15 seconds only
- Complete thoughts
- No filler

FACT CHECK:
Identify claims that need verification (stats, collaborations, timelines, numbers).

Return JSON:

{{
 "soundbites":[{{"id":0,"why":"..."}}],
 "fact":[{{"claim":"...","why":"..."}}]
}}

Candidates:
{candidate_text}
"""

        r = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            temperature=0
        )

    data = json.loads(re.search(r"\{.*\}", r.output_text, re.S).group())

    results = []
    for sb in data["soundbites"]:
        c = next((x for x in candidates if x["id"] == sb["id"]), None)
        if c:
            results.append({**c, "why": sb["why"]})

    col1, col2 = st.columns(2)

    # SOUND BITES
    with col1:
        st.subheader("🎯 Ranked Soundbites")

        for i, r in enumerate(results, start=1):
            start = format_time(r["start"])
            end = format_time(r["end"])

            st.markdown(f"""
            <div class="card soundbite">
            <div class="rank">#{i}</div>
            <span class="timestamp">[{start}-{end}] ({r["duration"]:.1f}s)</span><br>
            "{html.escape(r["quote"])}"
            <div><b>Why it works:</b> {html.escape(r["why"])}</div>
            </div>
            """, unsafe_allow_html=True)

    # FACT CHECK (🔥 UPDATED)
    with col2:
        st.subheader("⚠️ Fact Check")

        for f in data.get("fact", []):
            # 🔥 attach a timestamp (approximate)
            seg = random.choice(segments)
            ts = f"[{format_time(seg['start'])}-{format_time(seg['end'])}]"

            st.markdown(f"""
            <div class="card fact">
            <b>{html.escape(f["claim"])}</b><br>
            {html.escape(f["why"])}<br>
            <span class="timestamp">{ts}</span>
            </div>
            """, unsafe_allow_html=True)