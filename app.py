import re
import time
import io

import pandas as pd
import streamlit as st
from ddgs import DDGS


# ============================================================
# ROLE CATEGORIES
# ============================================================

ROLE_GROUPS = {
    "Corporate Communications": [
        "Corporate Communications", "Corporate Communication", "Communications",
        "Communication", "External Communications", "Internal Communications",
        "Executive Communications",
    ],
    "PR / Media": [
        "Public Relations", "PR", "Media Relations", "Media", "Press",
        "Press Relations", "Public Affairs",
    ],
    "Marketing": [
        "Marketing", "Marketing Head", "Head of Marketing", "VP Marketing",
        "Director Marketing", "Brand Marketing", "Growth Marketing", "CMO",
        "Chief Marketing Officer",
    ],
    "Founder's / CEO Office": [
        "Founder's Office", "Founders Office", "Founder Office", "CEO Office",
        "Office of the CEO", "Chief of Staff", "Executive Office",
        "Executive Assistant to CEO", "Assistant to CEO",
    ],
    "Partnerships / Business Development": [
        "Partnerships", "Strategic Partnerships", "Business Development",
        "Business Development Head", "Head of Partnerships", "Partnerships Head",
        "Strategic Relations", "Alliances",
    ],
    "Corporate Affairs": [
        "Corporate Affairs", "Government Relations", "Government Affairs",
        "External Affairs", "Institutional Relations", "Public Policy", "Policy",
    ],
    "Leadership": [
        "Founder", "Co-Founder", "CEO", "Chief Executive Officer",
        "Managing Director", "MD", "President", "Chairman", "Chairperson",
    ],
    "Investor / Corporate Relations": [
        "Investor Relations", "Corporate Relations", "Corporate Development",
        "Investor Communication", "Corporate Strategy", "Strategy",
    ],
    "Events / Community": [
        "Events", "Event Marketing", "Community", "Community Manager",
        "Community Lead", "Experiential Marketing", "Events Marketing",
    ],
}

ROLE_PRIORITY = {
    "Founder": 100, "Co-Founder": 100, "CEO": 95, "Chief Executive Officer": 95,
    "Chairman": 90, "Chairperson": 90, "Managing Director": 88, "MD": 85,
    "Chief of Staff": 90, "Founder's Office": 92, "Founders Office": 92,
    "Founder Office": 92, "CEO Office": 92, "Office of the CEO": 92,
    "Executive Office": 88, "Corporate Communications": 90,
    "Corporate Communication": 90, "Executive Communications": 88,
    "External Communications": 88, "Communications": 82,
    "Public Relations": 88, "PR": 85, "Media Relations": 88,
    "Press Relations": 86, "Public Affairs": 82, "Corporate Affairs": 85,
    "Government Relations": 80, "Government Affairs": 80,
    "External Affairs": 80, "Public Policy": 78, "Partnerships": 78,
    "Strategic Partnerships": 82, "Head of Partnerships": 85,
    "Partnerships Head": 85, "Business Development": 75,
    "Strategic Relations": 78, "CMO": 88, "Chief Marketing Officer": 88,
    "Head of Marketing": 85, "Marketing Head": 85, "VP Marketing": 82,
    "Director Marketing": 78, "Marketing": 70, "Investor Relations": 75,
    "Corporate Relations": 78, "Corporate Development": 75,
    "Corporate Strategy": 70, "Events": 60, "Event Marketing": 65,
    "Community": 55, "Community Manager": 60,
}


# ============================================================
# HELPERS (unchanged logic from the original script)
# ============================================================

def clean_url(url):
    if not url:
        return ""
    url = url.split("?")[0]
    return url.rstrip("/")


def normalize_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def extract_name(title):
    if not title:
        return ""
    title = normalize_text(title)
    title = re.sub(r"\s*\|\s*LinkedIn.*$", "", title, flags=re.IGNORECASE)
    if " - " in title:
        return title.split(" - ", 1)[0].strip()
    return title.strip()


def extract_title(title):
    if not title:
        return ""
    title = normalize_text(title)
    title = re.sub(r"\s*\|\s*LinkedIn.*$", "", title, flags=re.IGNORECASE)
    if " - " in title:
        parts = title.split(" - ", 1)
        if len(parts) == 2:
            return parts[1].strip()
    return ""


def classify_person(text):
    text = text.lower()
    best_category, best_role, best_priority = "", "", 0
    for category, roles in ROLE_GROUPS.items():
        for role in roles:
            if role.lower() in text:
                priority = ROLE_PRIORITY.get(role, 50)
                if priority > best_priority:
                    best_priority = priority
                    best_category = category
                    best_role = role
    return best_category, best_role, best_priority


def company_relevance(company, title, body):
    company_lower = company.lower()
    title_lower = (title or "").lower()
    body_lower = (body or "").lower()
    score = 0
    if company_lower in title_lower:
        score += 35
    if company_lower in body_lower:
        score += 15
    if "linkedin.com/in/" in title_lower:
        score += 5
    return score


# ============================================================
# SEARCH
# ============================================================

def search_company(company, selected_categories, progress_cb=None):
    candidates = {}

    queries = []
    for category, roles in ROLE_GROUPS.items():
        if category not in selected_categories:
            continue
        selected_roles = roles[:5]
        role_string = " OR ".join(f'"{role}"' for role in selected_roles)
        query = f'site:linkedin.com/in/ "{company}" ({role_string})'
        queries.append((category, query))

    queries.extend([
        ("General", f'site:linkedin.com/in/ "{company}"'),
        ("General", f'site:linkedin.com/in/ "{company}" employee'),
        ("General", f'site:linkedin.com/in/ "{company}" leadership'),
    ])

    total = len(queries)
    for i, (category, query) in enumerate(queries, start=1):
        if progress_cb:
            progress_cb(i, total, category)

        try:
            with DDGS() as ddgs:
                results = ddgs.text(query, max_results=10, backend="auto")

            for result in results:
                url = clean_url(result.get("href", ""))
                if not url or "linkedin.com/in/" not in url.lower():
                    continue

                title = normalize_text(result.get("title", ""))
                body = normalize_text(result.get("body", ""))
                name = extract_name(title)
                if not name:
                    continue

                apparent_title = extract_title(title)
                combined_text = title + " " + body
                detected_category, detected_role, role_priority = classify_person(combined_text)
                relevance = company_relevance(company, title, body)

                if not detected_category:
                    detected_category = category
                    detected_role = ""
                    role_priority = 30

                score = relevance + role_priority

                if url not in candidates:
                    candidates[url] = {
                        "Company": company,
                        "Name": name,
                        "LinkedIn": url,
                        "Title": apparent_title,
                        "Role Category": detected_category,
                        "Detected Role": detected_role,
                        "Priority Score": score,
                    }
                else:
                    existing = candidates[url]
                    if score > existing["Priority Score"]:
                        existing["Priority Score"] = score
                        existing["Title"] = apparent_title
                        existing["Role Category"] = detected_category
                        existing["Detected Role"] = detected_role

        except Exception as e:
            st.warning(f"Search failed for '{category}' on {company}: {e}")

        time.sleep(1.2)

    return list(candidates.values())


def rank_people(candidates, limit):
    filtered = [p for p in candidates if p["Priority Score"] >= 40]
    filtered.sort(
        key=lambda x: (x["Priority Score"], ROLE_PRIORITY.get(x["Detected Role"], 0)),
        reverse=True,
    )
    return filtered[:limit]


# ============================================================
# STREAMLIT UI
# ============================================================

st.set_page_config(page_title="Company People Finder", page_icon="🔎", layout="wide")

st.title("🔎 Company People Finder")
st.caption(
    "Finds public LinkedIn profiles for comms, PR, marketing, partnerships, "
    "founder's-office and leadership people at the companies you list."
)

with st.sidebar:
    st.header("Search settings")

    companies_raw = st.text_area(
        "Companies (one per line)",
        placeholder="Acme Corp\nExample Inc\nNorthwind Traders",
        height=140,
    )

    people_per_company = st.slider("People per company", min_value=1, max_value=30, value=10)

    st.markdown("**Role categories to include**")
    all_categories = list(ROLE_GROUPS.keys())
    selected_categories = []
    select_all = st.checkbox("Select all", value=True)
    for cat in all_categories:
        checked = st.checkbox(cat, value=select_all, key=f"cat_{cat}")
        if checked:
            selected_categories.append(cat)

    run_button = st.button("Run search", type="primary", use_container_width=True)

if "results_df" not in st.session_state:
    st.session_state.results_df = pd.DataFrame()

if run_button:
    companies = [c.strip() for c in companies_raw.splitlines() if c.strip()]

    if not companies:
        st.error("Add at least one company name in the sidebar.")
    elif not selected_categories:
        st.error("Select at least one role category.")
    else:
        all_people = []
        overall_progress = st.progress(0, text="Starting...")

        for c_idx, company in enumerate(companies, start=1):
            status = st.empty()

            def progress_cb(i, total, category, company=company, c_idx=c_idx):
                status.text(f"[{company}] query {i}/{total}: {category}")

            candidates = search_company(company, selected_categories, progress_cb)
            people = rank_people(candidates, people_per_company)
            all_people.extend(people)

            status.empty()
            overall_progress.progress(
                c_idx / len(companies),
                text=f"Finished {company} ({c_idx}/{len(companies)})",
            )

        overall_progress.empty()
        st.session_state.results_df = pd.DataFrame(all_people)

if not st.session_state.results_df.empty:
    df = st.session_state.results_df
    st.success(f"Found {len(df)} people across {df['Company'].nunique()} compan{'y' if df['Company'].nunique() == 1 else 'ies'}.")
    st.dataframe(df, use_container_width=True, hide_index=True)

    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    st.download_button(
        "Download CSV",
        data=csv_buffer.getvalue(),
        file_name="people_database.csv",
        mime="text/csv",
        use_container_width=True,
    )
else:
    st.info("Add companies and role categories in the sidebar, then click **Run search**.")
