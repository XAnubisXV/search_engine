import urllib.parse as up
import streamlit as st
from tantivy import Query, Index, SchemaBuilder, Occur

# --- CONFIG ---
TMDB_PATH_BIG = "https://image.tmdb.org/t/p/original"
TMDB_PATH_SMALL = "https://image.tmdb.org/t/p/w300"
INDEX_PATH = "serien_300"

st.set_page_config(page_title="StreamFlix", page_icon="📺", layout="wide")

# --- CSS LADEN ---
try:
    with open("styles.html", "r") as f:
        st.markdown(f.read(), unsafe_allow_html=True)
except FileNotFoundError:
    st.error("Bitte stelle sicher, dass 'styles.html' im Ordner liegt.")

# --- SCHEMA DEFINIEREN (Muss identisch zu indexing.py sein) ---
schema_builder = SchemaBuilder()
schema_builder.add_text_field("wikidata", stored=True)
schema_builder.add_text_field("url", stored=True)
schema_builder.add_text_field("title", stored=True, tokenizer_name='en_stem')
schema_builder.add_text_field("description", stored=True, tokenizer_name='en_stem')
schema_builder.add_text_field("image", stored=True)
schema_builder.add_text_field("locations", stored=True)
schema_builder.add_text_field("countries", stored=True)
schema_builder.add_text_field("genres", stored=True)
schema_builder.add_text_field("tmdb_overview", stored=True, tokenizer_name='en_stem')
schema_builder.add_text_field("tmdb_poster_path", stored=True)
schema_builder.add_text_field("trailer", stored=True)
# Neue Filter Felder
schema_builder.add_text_field("actors", stored=True, tokenizer_name='en_stem')
schema_builder.add_text_field("writers", stored=True, tokenizer_name='en_stem')
# Integer & Floats
schema_builder.add_integer_field("id", stored=True, indexed=True)
schema_builder.add_integer_field("follower", stored=True, fast=True)
schema_builder.add_integer_field("score", stored=True, fast=True)
schema_builder.add_integer_field("start", stored=True, fast=True)
schema_builder.add_integer_field("tmdb_genre_ids", stored=True, indexed=True)
schema_builder.add_integer_field("tmdb_vote_count", stored=True, fast=True)
schema_builder.add_integer_field("is_based_on_book", stored=True, indexed=True)
schema_builder.add_integer_field("is_true_story", stored=True, indexed=True)
schema_builder.add_float_field("tmdb_popularity", stored=True, fast=True)
schema_builder.add_float_field("tmdb_vote_average", stored=True, fast=True)
# Facetten
schema_builder.add_facet_field("facet_locations")
schema_builder.add_facet_field("facet_countries")
schema_builder.add_facet_field("facet_genres")

schema = schema_builder.build()
index = Index(schema, path=str(INDEX_PATH))
searcher = index.searcher()

# --- SESSION STATE ---
if 'watchlist' not in st.session_state:
    st.session_state.watchlist = []
if 'show_filters' not in st.session_state:
    st.session_state.show_filters = False


def get_qp(): return getattr(st, "query_params", {})


qp = get_qp()
view = qp.get("view", "grid")
q_param = qp.get("q", "")

# --- HEADER BEREICH ---
col1, col2, col3 = st.columns([1, 5, 2])
with col1:
    st.markdown("<h2 style='color: #e50914; margin:0;'>STREAMFLIX</h2>", unsafe_allow_html=True)

with col3:
    # Navigation oben rechts
    b1, b2 = st.columns(2)
    if b1.button("🏠 Home"):
        st.query_params.clear()
        st.rerun()
    if b2.button(f"❤️ Liste ({len(st.session_state.watchlist)})"):
        st.query_params.update({"view": "mylist"})
        st.rerun()

# --- FILTER & SUCHE LEISTE ---
# Zeige Filter nur auf der Grid-Ansicht (nicht im Detail oder Liste)
if view != "detail" and view != "mylist":
    with st.expander("🔍 Suche & Filter", expanded=st.session_state.show_filters):

        # 1. Zeile: Textsuche
        search_query = st.text_input("Titel, Schauspieler, Beschreibung...", value=q_param)

        # 2. Zeile: Filter
        c1, c2, c3 = st.columns(3)

        genres_list = ["Drama", "Comedy", "Crime", "Sci-Fi", "Action", "Thriller", "Animation", "Documentary"]
        providers_list = ["Netflix", "Amazon Prime Video", "Disney Plus", "Hulu", "Apple TV"]

        # Multiselects lesen aus URL oder Default
        def_g = qp.get("genres", "").split(",") if qp.get("genres") else []
        def_p = qp.get("providers", "").split(",") if qp.get("providers") else []

        sel_genres = c1.multiselect("Genre", genres_list, default=def_g)
        sel_provs = c2.multiselect("Plattform", providers_list, default=def_p)

        # Checkboxen
        st.write("Spezialfilter:")
        cc1, cc2 = st.columns(2)
        is_true = cc1.checkbox("Wahre Geschichte", value=True if qp.get("true_story") == "1" else False)
        is_book = cc2.checkbox("Basiert auf Buch", value=True if qp.get("book") == "1" else False)

        sort_opt = st.selectbox("Sortieren nach", ["Beliebtheit", "Bewertung", "Neuerscheinungen"])

        # Anwenden Button
        if st.button("Ergebnisse anzeigen", type="primary"):
            p = {"view": "grid"}
            if search_query: p["q"] = search_query
            if sel_genres: p["genres"] = ",".join(sel_genres)
            if sel_provs: p["providers"] = ",".join(sel_provs)
            if is_true: p["true_story"] = "1"
            if is_book: p["book"] = "1"
            p["sort"] = sort_opt

            st.query_params.clear()
            st.query_params.update(p)
            st.rerun()

# --- ANSICHTEN LOGIK ---

# 1. DETAIL ANSICHT
if view == "detail":
    sid = qp.get("id")
    if sid:
        hits = searcher.search(index.parse_query(sid, ["id"]), 1).hits
        if hits:
            _, addr = hits[0]
            doc = searcher.doc(addr)

            d_id = doc["id"][0]
            c1, c2 = st.columns([1, 2])

            with c1:
                img = doc["tmdb_poster_path"][0] if doc["tmdb_poster_path"] else ""
                url = TMDB_PATH_BIG + img if img else "https://via.placeholder.com/500"
                st.image(url, use_container_width=True)

                # Merkliste Toggle
                if d_id in st.session_state.watchlist:
                    if st.button("❌ Von Liste entfernen"):
                        st.session_state.watchlist.remove(d_id)
                        st.rerun()
                else:
                    if st.button("➕ Zu meiner Liste"):
                        st.session_state.watchlist.append(d_id)
                        st.rerun()

            with c2:
                st.title(doc["title"][0])
                rate = doc["tmdb_vote_average"][0] if doc["tmdb_vote_average"] else 0
                st.markdown(f"⭐ **{rate:.1f}/10** | 📅 {doc['start'][0] if doc['start'] else ''}")

                st.markdown("### Verfügbar bei:")
                if doc["locations"]:
                    for l in doc["locations"]:
                        st.markdown(f'<span class="tag" style="background:#e50914;">{l}</span>', unsafe_allow_html=True)
                else:
                    st.write("Keine Info.")

                st.markdown("### Handlung")
                desc = doc["tmdb_overview"][0] if doc["tmdb_overview"] else doc["description"][0]
                st.write(desc)

                if doc["actors"]:
                    st.markdown(f"**Cast:** {', '.join(doc['actors'])}")

                if doc["trailer"]:
                    st.markdown("### Trailer")
                    st.video(f"https://www.youtube.com/watch?v={doc['trailer'][0]}")

                if st.button("← Zurück"):
                    st.query_params.update({"view": "grid"})
                    st.query_params.pop("id", None)
                    st.rerun()

# 2. MEINE LISTE ANSICHT
elif view == "mylist":
    st.subheader("Meine Liste")
    if not st.session_state.watchlist:
        st.info("Deine Liste ist leer.")
    else:
        # Query für alle IDs in der Liste
        q_str = " OR ".join([f"id:{wid}" for wid in st.session_state.watchlist])
        hits = searcher.search(index.parse_query(q_str, ["id"]), 100).hits

        html = ['<div class="grid">']
        for _, addr in hits:
            doc = searcher.doc(addr)
            img = doc["tmdb_poster_path"][0] if doc["tmdb_poster_path"] else ""
            url = TMDB_PATH_SMALL + img if img else "https://via.placeholder.com/200"

            html.append(f"""
            <a class="card" href="?view=detail&id={doc['id'][0]}" target="_self">
                <img src="{url}" loading="lazy">
                <div class="t">{doc['title'][0]}</div>
                <div class="meta">❤️</div>
            </a>""")
        html.append("</div>")
        st.markdown("".join(html), unsafe_allow_html=True)

# 3. GRID / SUCHERGEBNISSE ANSICHT
else:
    parts = []

    # Text Suche (Titel, Actors, Beschreibung)
    if q_param:
        parts.append((Occur.Must, index.parse_query(q_param, ["title", "actors", "description", "tmdb_overview"])))

    # Genre Filter
    if qp.get("genres"):
        for g in qp.get("genres").split(","):
            parts.append((Occur.Must, index.parse_query(g, ["genres"])))

    # Provider Filter (OR Verknüpfung)
    if qp.get("providers"):
        provs = " OR ".join([f'"{p}"' for p in qp.get("providers").split(",")])
        parts.append((Occur.Must, index.parse_query(provs, ["locations"])))

    # Spezialfilter
    if qp.get("true_story") == "1":
        parts.append((Occur.Must, index.parse_query("1", ["is_true_story"])))
    if qp.get("book") == "1":
        parts.append((Occur.Must, index.parse_query("1", ["is_based_on_book"])))

    # Query Bauen
    query = Query.boolean_query(parts) if parts else index.parse_query("*", ["title"])

    # Suche Ausführen
    hits = searcher.search(query, 300).hits

    # Ergebnisse sammeln
    results = []
    for _, addr in hits:
        doc = searcher.doc(addr)
        results.append({
            "id": doc["id"][0],
            "title": doc["title"][0],
            "poster": doc["tmdb_poster_path"][0] if doc["tmdb_poster_path"] else "",
            "pop": doc["tmdb_popularity"][0] if doc["tmdb_popularity"] else 0,
            "rate": doc["tmdb_vote_average"][0] if doc["tmdb_vote_average"] else 0,
            "date": doc["start"][0] if doc["start"] else 0
        })

    # Sortierung anwenden
    sort_k = qp.get("sort", "Beliebtheit")
    if sort_k == "Beliebtheit":
        results.sort(key=lambda x: x["pop"], reverse=True)
    elif sort_k == "Bewertung":
        results.sort(key=lambda x: x["rate"], reverse=True)
    elif sort_k == "Neuerscheinungen":
        results.sort(key=lambda x: x["date"], reverse=True)

    # Grid Rendern
    if not results:
        st.warning("Keine Ergebnisse für deine Suche.")
    else:
        html = ['<div class="grid">']
        for r in results:
            img = TMDB_PATH_SMALL + r["poster"] if r["poster"] else "https://via.placeholder.com/200"
            href = f"?view=detail&id={r['id']}&q={up.quote(q_param, safe='')}"

            html.append(f"""
            <a class="card" href="{href}" target="_self">
                <img src="{img}" loading="lazy">
                <div class="t">{r['title']}</div>
                <div class="meta">⭐ {r['rate']:.1f}</div>
            </a>""")
        html.append("</div>")
        st.markdown("".join(html), unsafe_allow_html=True)