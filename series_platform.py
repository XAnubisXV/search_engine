import urllib.parse as up
import streamlit as st
from tantivy import Query, Index, SchemaBuilder, Occur

TMDB_PATH_BIG = "https://image.tmdb.org/t/p/original"
TMDB_PATH_SMALL = "https://image.tmdb.org/t/p/w300"
INDEX_PATH = "serien_db"

st.set_page_config(page_title="StreamFlix", page_icon="📺", layout="wide")
try:
    with open("styles.html", "r") as f:
        st.markdown(f.read(), unsafe_allow_html=True)
except:
    pass

# SCHEMA
schema_builder = SchemaBuilder()
schema_builder.add_text_field("wikidata", stored=True)
schema_builder.add_text_field("url", stored=True)
schema_builder.add_text_field("title", stored=True, tokenizer_name='de_stem')
schema_builder.add_text_field("description", stored=True, tokenizer_name='de_stem')
schema_builder.add_text_field("image", stored=True)
schema_builder.add_text_field("genres", stored=True)
schema_builder.add_text_field("providers", stored=True)
schema_builder.add_text_field("countries", stored=True)
schema_builder.add_text_field("tmdb_overview", stored=True, tokenizer_name='de_stem')
schema_builder.add_text_field("tmdb_poster_path", stored=True)
schema_builder.add_text_field("trailer", stored=True)
schema_builder.add_text_field("actors", stored=True, tokenizer_name='en_stem')
schema_builder.add_text_field("writers", stored=True, tokenizer_name='en_stem')
schema_builder.add_integer_field("id", stored=True, indexed=True)
schema_builder.add_integer_field("score", stored=True, fast=True)
schema_builder.add_integer_field("start", stored=True, fast=True)
schema_builder.add_integer_field("tmdb_vote_count", stored=True, fast=True)
schema_builder.add_integer_field("is_based_on_book", stored=True, indexed=True)
schema_builder.add_integer_field("is_true_story", stored=True, indexed=True)
schema_builder.add_float_field("tmdb_popularity", stored=True, fast=True)
schema_builder.add_float_field("tmdb_vote_average", stored=True, fast=True)
schema_builder.add_facet_field("facet_genres")
schema_builder.add_facet_field("facet_providers")
schema = schema_builder.build()

try:
    index = Index(schema, path=str(INDEX_PATH))
    searcher = index.searcher()
except Exception as e:
    st.error(f"⚠️ FEHLER: {e}");
    st.stop()

if 'watchlist' not in st.session_state: st.session_state.watchlist = []
if 'show_filters' not in st.session_state: st.session_state.show_filters = False
qp = getattr(st, "query_params", {})
view = qp.get("view", "grid");
q_param = qp.get("q", "")


@st.cache_data
def get_filter_options(field_name):
    try:
        hits = searcher.search(index.parse_query("*", ["title"]), 5000).hits
        found = set()
        for _, addr in hits:
            doc = searcher.doc(addr)
            vals = doc.get(field_name, [])
            for v in vals:
                parts = v.split(",") if "," in v else [v]
                for p in parts:
                    if p.strip(): found.add(p.strip())
        return sorted(list(found))
    except:
        return []


col1, col2, col3 = st.columns([1, 5, 2])
with col1: st.markdown("<h2 style='color: #e50914; margin:0; font-weight:900;'>STREAMFLIX</h2>", unsafe_allow_html=True)
with col3:
    b1, b2 = st.columns(2)
    if b1.button("HOME"): st.query_params.clear(); st.rerun()
    if b2.button(f"LISTE ({len(st.session_state.watchlist)})"): st.query_params.update({"view": "mylist"}); st.rerun()

if view != "detail" and view != "mylist":
    with st.expander("🔍 SUCHE & FILTER", expanded=st.session_state.show_filters):
        search_query = st.text_input("Titel, Schauspieler, Handlung...", value=q_param)
        c1, c2, c3 = st.columns(3)

        db_genres = get_filter_options("genres")
        db_providers = get_filter_options("providers")

        # HIER IST DIE RIESIGE NOTFALL-LISTE
        if len(db_genres) < 5:
            db_genres = ["Drama", "Komödie", "Action", "Thriller", "Krimi", "Dokumentation", "Science-Fiction",
                         "Horror", "Abenteuer", "Familie", "Fantasy", "Animation", "Romantik", "Western", "Musik",
                         "Reality-TV"]
        if len(db_providers) < 2:
            db_providers = ["Netflix", "Amazon Prime", "Disney+", "Hulu", "Apple TV+", "Sky/Wow", "RTL+"]

        sel_genres = c1.multiselect("Genre", db_genres,
                                    default=qp.get("genres", "").split(",") if qp.get("genres") else [])
        sel_provs = c2.multiselect("Plattform", db_providers,
                                   default=qp.get("providers", "").split(",") if qp.get("providers") else [])
        sort_opt = c3.selectbox("Sortieren nach",
                                ["Beliebtheit", "Bewertung (Top Rated)", "Kritiker-Score", "Neuerscheinungen"])
        st.write("Spezialfilter:")
        cc1, cc2 = st.columns(2)
        is_true = cc1.checkbox("Wahre Geschichte", value=True if qp.get("true_story") == "1" else False)
        is_book = cc2.checkbox("Basiert auf Buch", value=True if qp.get("book") == "1" else False)

        if st.button("ERGEBNISSE ANZEIGEN"):
            p = {"view": "grid"}
            if search_query: p["q"] = search_query
            if sel_genres: p["genres"] = ",".join(sel_genres)
            if sel_provs: p["providers"] = ",".join(sel_provs)
            if is_true: p["true_story"] = "1";
            if is_book: p["book"] = "1"
            p["sort"] = sort_opt
            st.query_params.clear();
            st.query_params.update(p);
            st.rerun()

if view == "detail":
    sid = qp.get("id")
    if sid:
        hits = searcher.search(index.parse_query(sid, ["id"]), 1).hits
        if hits:
            _, addr = hits[0];
            doc = searcher.doc(addr);
            d_id = doc["id"][0]
            c1, c2 = st.columns([1, 2])
            with c1:
                img = doc["tmdb_poster_path"][0] if doc["tmdb_poster_path"] else ""
                url = TMDB_PATH_BIG + img if img else "https://via.placeholder.com/500x750?text=Kein+Bild"
                st.image(url, use_container_width=True)
                st.markdown("##### 📺 Verfügbar bei:")
                if doc["providers"]:
                    for p in doc["providers"]: st.markdown(f'<span class="tag" style="background:#e50914;">{p}</span>',
                                                           unsafe_allow_html=True)
                if d_id in st.session_state.watchlist:
                    if st.button("❌ ENTFERNEN"): st.session_state.watchlist.remove(d_id); st.rerun()
                else:
                    if st.button("➕ MERKEN"): st.session_state.watchlist.append(d_id); st.rerun()
            with c2:
                st.markdown(f"# {doc['title'][0]}")
                rate = doc["tmdb_vote_average"][0] if doc["tmdb_vote_average"] else 0
                count = doc["tmdb_vote_count"][0] if doc["tmdb_vote_count"] else 0
                score = doc["score"][0] if doc["score"] else 0
                if count > 0:
                    st.markdown(f"#### ⭐ **{rate:.1f}** / 10 _({count} Stimmen)_")
                else:
                    st.markdown("#### ⭐ _Keine Bewertung_")
                if score > 0:
                    color = "green" if score >= 60 else "orange" if score >= 40 else "red"
                    st.markdown(f"**Kritiker-Score:** <span style='color:{color}; font-weight:bold;'>{score}</span>",
                                unsafe_allow_html=True)
                if doc["genres"]: st.markdown(f"**Genre:** {', '.join(doc['genres'])}")
                st.markdown("---")
                desc = doc["tmdb_overview"][0] if doc["tmdb_overview"] else doc["description"][0]
                st.write(desc if desc else "Keine Beschreibung.")
                if doc["actors"]: st.markdown(f"**Cast:** {', '.join(doc['actors'])}")
                if doc["trailer"]:
                    st.markdown("### Trailer");
                    st.video(f"https://www.youtube.com/watch?v={doc['trailer'][0]}")
                if st.button("← ZURÜCK"): st.query_params.update({"view": "grid"}); st.query_params.pop("id",
                                                                                                        None); st.rerun()

elif view == "mylist":
    st.subheader("Meine Liste")
    if not st.session_state.watchlist:
        st.info("Leer.")
    else:
        q_str = " OR ".join([f"id:{wid}" for wid in st.session_state.watchlist])
        hits = searcher.search(index.parse_query(q_str, ["id"]), 100).hits
        html = ['<div class="grid">']
        for _, addr in hits:
            doc = searcher.doc(addr)
            img = doc["tmdb_poster_path"][0] if doc["tmdb_poster_path"] else ""
            url = TMDB_PATH_SMALL + img if img else "https://via.placeholder.com/200x300?text=Kein+Bild"
            html.append(
                f"""<a class="card" href="?view=detail&id={doc['id'][0]}" target="_self"><img src="{url}" loading="lazy"><div class="t">{doc['title'][0]}</div><div class="meta">❤️</div></a>""")
        html.append("</div>");
        st.markdown("".join(html), unsafe_allow_html=True)

else:
    parts = []
    if q_param: parts.append(
        (Occur.Must, index.parse_query(q_param, ["title", "actors", "description", "tmdb_overview"])))
    if qp.get("genres"):
        sub = []
        for g in qp.get("genres").split(","): sub.append((Occur.Should, index.parse_query(f'"{g}"', ["genres"])))
        parts.append((Occur.Must, Query.boolean_query(sub)))
    if qp.get("providers"):
        sub = []
        for p in qp.get("providers").split(","): sub.append((Occur.Should, index.parse_query(f'"{p}"', ["providers"])))
        parts.append((Occur.Must, Query.boolean_query(sub)))
    if qp.get("true_story") == "1": parts.append((Occur.Must, index.parse_query("1", ["is_true_story"])))
    if qp.get("book") == "1": parts.append((Occur.Must, index.parse_query("1", ["is_based_on_book"])))

    query = Query.boolean_query(parts) if parts else index.parse_query("*", ["title"])
    hits = searcher.search(query, 300).hits
    results = []
    for _, addr in hits:
        doc = searcher.doc(addr)
        pop = doc["tmdb_popularity"][0] if doc["tmdb_popularity"] else 0.0
        rate = doc["tmdb_vote_average"][0] if doc["tmdb_vote_average"] else 0.0
        count = doc["tmdb_vote_count"][0] if doc["tmdb_vote_count"] else 0
        score = doc["score"][0] if doc["score"] else 0
        date = doc["start"][0] if doc["start"] else 0
        results.append({"id": doc["id"][0], "title": doc["title"][0],
                        "poster": doc["tmdb_poster_path"][0] if doc["tmdb_poster_path"] else "", "pop": pop,
                        "rate": rate, "count": count, "score": score, "date": date})

    sort_k = qp.get("sort", "Beliebtheit")
    if sort_k == "Beliebtheit":
        results.sort(key=lambda x: x["pop"], reverse=True)
    elif sort_k == "Bewertung (Top Rated)":
        results.sort(key=lambda x: x["rate"] if x["count"] >= 50 else 0, reverse=True)
    elif sort_k == "Kritiker-Score":
        results.sort(key=lambda x: x["score"], reverse=True)
    elif sort_k == "Neuerscheinungen":
        results.sort(key=lambda x: x["date"], reverse=True)

    if not results:
        st.warning("Keine Treffer.")
    else:
        html = ['<div class="grid">']
        for r in results:
            img = TMDB_PATH_SMALL + r["poster"] if r["poster"] else "https://via.placeholder.com/200x300"
            href = f"?view=detail&id={r['id']}&q={up.quote(q_param, safe='')}"
            label = f"Score: {r['score']}" if sort_k == "Kritiker-Score" and r["score"] > 0 else f"⭐ {r['rate']:.1f}"
            html.append(
                f"""<a class="card" href="{href}" target="_self"><img src="{img}" loading="lazy"><div class="t">{r['title']}</div><div class="meta">{label}</div></a>""")
        html.append("</div>");
        st.markdown("".join(html), unsafe_allow_html=True)