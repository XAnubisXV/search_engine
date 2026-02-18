import json
import os
import urllib.parse as up
import streamlit as st
from tantivy import Query, Index, SchemaBuilder, Occur

# --- 1. SETUP ---
st.set_page_config(page_title="PathFinder", page_icon="🧭", layout="wide")

# Static-Ordner fuer Hintergrundbild erstellen
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)
FRAME_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Frame.png")
FRAME_DST = os.path.join(STATIC_DIR, "Frame.png")
if os.path.exists(FRAME_SRC) and not os.path.exists(FRAME_DST):
    import shutil
    shutil.copy2(FRAME_SRC, FRAME_DST)

WATCHLIST_FILE = "watchlist.json"


def load_watchlist():
    """Watchlist aus JSON-Datei laden (persistent)."""
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []


def save_watchlist(wl):
    """Watchlist in JSON-Datei speichern (persistent)."""
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(wl, f)


if 'watchlist' not in st.session_state:
    st.session_state.watchlist = load_watchlist()
if 'show_search' not in st.session_state:
    st.session_state.show_search = False

qp = st.query_params
view = qp.get("view", "grid")
q_param = qp.get("q", "")
scroll_pos = qp.get("scroll", "0")

# --- 2. CONFIG ---
TMDB_PATH_BIG = "https://image.tmdb.org/t/p/original"
TMDB_PATH_SMALL = "https://image.tmdb.org/t/p/w300"
INDEX_PATH = "serien_db"

try:
    with open("styles.html", "r") as f:
        st.markdown(f.read(), unsafe_allow_html=True)
except:
    pass

# --- SCROLL-POSITION WIEDERHERSTELLEN ---
# JavaScript das die Scroll-Position wiederherstellt wenn scroll-Parameter vorhanden
if scroll_pos and scroll_pos != "0":
    st.markdown(f"""
    <script>
    window.addEventListener('load', function() {{
        setTimeout(function() {{
            window.scrollTo(0, {scroll_pos});
        }}, 100);
    }});
    </script>
    """, unsafe_allow_html=True)

# --- SCROLL-POSITION SPEICHERN (fuer Card-Links) ---
# JavaScript das bei jedem Klick auf eine Card die aktuelle Scroll-Position in den Link einbaut
st.markdown("""
<script>
document.addEventListener('click', function(e) {
    var card = e.target.closest('.card');
    if (card) {
        e.preventDefault();
        var href = card.getAttribute('href');
        var scrollY = Math.round(window.scrollY);
        var sep = href.includes('?') ? '&' : '?';
        window.location.href = href + sep + 'scroll=' + scrollY;
    }
});
</script>
""", unsafe_allow_html=True)

# --- 3. INDEX ---
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
    st.error(f"FEHLER: {e}")
    st.stop()


@st.cache_data
def get_filter_options(field_name):
    try:
        # Limit auf 7000 erhöht für Filter
        hits = searcher.search(index.parse_query("*", ["title"]), 7000).hits
        found = set()
        for _, addr in hits:
            doc = searcher.doc(addr)
            vals = doc.get(field_name, [])
            for v in vals:
                parts = v.split(",") if "," in v else [v]
                for p in parts:
                    if p.strip():
                        found.add(p.strip())
        return sorted(list(found))
    except:
        return []


# --- 4. HEADER ---
header = st.container()

with header:
    _, c_logo, c_search, c_list, _ = st.columns([3, 1.2, 1.5, 1.2, 3])

    with c_logo:
        st.markdown(
            '<a href="?view=grid" class="logo-style" target="_self">PATHFINDER</a>',
            unsafe_allow_html=True
        )

    with c_search:
        if st.button("SUCHE & FILTER", key="btn_search", use_container_width=True):
            st.session_state.show_search = not st.session_state.show_search
            # KEIN st.rerun() - verhindert Scroll nach oben

    with c_list:
        count = len(st.session_state.watchlist)
        btn_label_list = f"LISTE ({count})"
        if st.button(btn_label_list, key="btn_list", use_container_width=True):
            st.query_params["view"] = "mylist"
            st.rerun()


# --- 5. SUCH-POPUP (als Overlay gestyled per CSS) ---
if st.session_state.show_search and view != "detail" and view != "mylist":

    # Overlay-Hintergrund
    st.markdown('<div class="popup-overlay"></div>', unsafe_allow_html=True)

    # Popup-Container oeffnen
    st.markdown('<div class="popup-box">', unsafe_allow_html=True)
    st.markdown('<div class="popup-title">SUCHE & FILTER</div>', unsafe_allow_html=True)

    with st.form("search_form"):

        # Titelsuche
        search_query = st.text_input(
            "Wonach suchst du?",
            value=q_param,
            placeholder="z.B. Breaking Bad, Action, ein Schauspieler..."
        )

        # Filteroptionen laden
        db_genres = get_filter_options("genres")
        db_providers = get_filter_options("providers")
        if len(db_genres) < 5:
            db_genres = ["Drama", "Komoedie", "Action", "Thriller", "Krimi", "Science-Fiction", "Fantasy", "Animiert", "Gezeichnet"]
        # Sicherstellen dass Fantasy, Animiert und Gezeichnet immer in der Liste sind
        for extra_genre in ["Fantasy", "Animiert", "Gezeichnet"]:
            if extra_genre not in db_genres:
                db_genres.append(extra_genre)
        db_genres = sorted(db_genres)

        if len(db_providers) < 2:
            # HIER WURDE DIE LISTE BEREINIGT
            db_providers = [
                "Netflix", "Disney+", "Apple TV+", "Sky", "WOW", "RTL+", "Hulu"
            ]

        # Genre + Plattform + Sortierung (3 Spalten)
        c1, c2, c3 = st.columns(3)

        sel_genres = c1.multiselect(
            "Genre",
            db_genres,
            default=qp.get("genres", "").split(",") if qp.get("genres") else []
        )
        sel_provs = c2.multiselect(
            "Plattform",
            db_providers,
            default=qp.get("providers", "").split(",") if qp.get("providers") else []
        )
        sort_opt = c3.selectbox(
            "Sortieren nach",
            ["Beliebtheit", "Bewertung (Top Rated)", "Kritiker-Score", "Neuerscheinungen"]
        )

        # Spezialfilter
        cc1, cc2 = st.columns(2)
        is_true = cc1.checkbox(
            "Wahre Geschichte",
            value=True if qp.get("true_story") == "1" else False
        )
        is_book = cc2.checkbox(
            "Basiert auf Buch",
            value=True if qp.get("book") == "1" else False
        )

        # Button
        submitted = st.form_submit_button("ERGEBNISSE ANZEIGEN", use_container_width=True)

        if submitted:
            p = {"view": "grid"}
            if search_query:
                p["q"] = search_query
            if sel_genres:
                p["genres"] = ",".join(sel_genres)
            if sel_provs:
                p["providers"] = ",".join(sel_provs)
            if is_true:
                p["true_story"] = "1"
            if is_book:
                p["book"] = "1"
            p["sort"] = sort_opt
            st.session_state.show_search = False
            st.query_params.clear()
            st.query_params.update(p)
            st.rerun()

    # Popup-Container schliessen
    st.markdown('</div>', unsafe_allow_html=True)


# --- 6. INHALT ---

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
                url = TMDB_PATH_BIG + img if img else "https://via.placeholder.com/500x750?text=No+Image"
                st.image(url, use_container_width=True)
                st.markdown("<br>", unsafe_allow_html=True)
                if d_id in st.session_state.watchlist:
                    if st.button("VON LISTE ENTFERNEN"):
                        st.session_state.watchlist.remove(d_id)
                        save_watchlist(st.session_state.watchlist)
                        st.rerun()
                else:
                    if st.button("AUF DIE LISTE"):
                        st.session_state.watchlist.append(d_id)
                        save_watchlist(st.session_state.watchlist)
                        st.rerun()
            with c2:
                st.markdown(f"<h1>{doc['title'][0]}</h1>", unsafe_allow_html=True)
                rate = doc["tmdb_vote_average"][0] if doc["tmdb_vote_average"] else 0
                score = doc["score"][0] if doc["score"] else 0
                year = doc["start"][0] if doc["start"] else "N/A"
                meta_html = f"""
                <div style="display:flex;
                align-items:center; gap:15px; margin-bottom:20px;">
                    <span style="color:#00e5ff;
                font-weight:bold; font-size:1.2rem;">{rate:.1f}</span>
                    <span style="color:#aaa;">{year}</span>
                </div>"""
                st.markdown(meta_html, unsafe_allow_html=True)
                if doc["providers"]:
                    st.markdown("Verfuegbar bei:")
                    for p in doc["providers"]:
                        st.markdown(f'<span class="tag">{p}</span>', unsafe_allow_html=True)
                    st.markdown("<br>", unsafe_allow_html=True)
                desc = doc["tmdb_overview"][0] if doc["tmdb_overview"] else doc["description"][0]
                st.write(desc if desc else "Keine Beschreibung verfuegbar.")
                st.markdown("---")
                if doc["genres"]:
                    st.markdown(f"**Genre:** {', '.join(doc['genres'])}")
                if doc["actors"]:
                    st.markdown(f"**Cast:** {', '.join(doc['actors'][:5])}")
                if doc["trailer"]:
                    st.markdown("### Trailer")
                    st.video(f"https://www.youtube.com/watch?v={doc['trailer'][0]}")
                st.markdown("<br>", unsafe_allow_html=True)

                # Zurueck-Button: scroll-Position aus URL uebernehmen
                back_scroll = qp.get("scroll", "0")
                if st.button("ZURUECK ZUR UEBERSICHT"):
                    new_params = {"view": "grid", "scroll": back_scroll}
                    # Suchparameter beibehalten
                    if qp.get("q"):
                        new_params["q"] = qp.get("q")
                    if qp.get("genres"):
                        new_params["genres"] = qp.get("genres")
                    if qp.get("providers"):
                        new_params["providers"] = qp.get("providers")
                    if qp.get("sort"):
                        new_params["sort"] = qp.get("sort")
                    if qp.get("true_story"):
                        new_params["true_story"] = qp.get("true_story")
                    if qp.get("book"):
                        new_params["book"] = qp.get("book")
                    st.query_params.clear()
                    st.query_params.update(new_params)
                    st.rerun()

elif view == "mylist":
    st.markdown("## Meine Liste")
    if not st.session_state.watchlist:
        st.info("Du hast noch keine Serien auf deiner Liste.")
    else:
        q_str = " OR ".join([f"id:{wid}" for wid in st.session_state.watchlist])
        # Limit für Watchlist auf 7000 erhöht
        hits = searcher.search(index.parse_query(q_str, ["id"]), 7000).hits
        html = ['<div class="grid">']
        for _, addr in hits:
            doc = searcher.doc(addr)
            img = doc["tmdb_poster_path"][0] if doc["tmdb_poster_path"] else ""
            url = TMDB_PATH_SMALL + img if img else "https://via.placeholder.com/200x300?text=No+Image"
            html.append(
                f"""<a class="card" href="?view=detail&id={doc['id'][0]}" target="_self">"""
                f"""<img src="{url}" loading="lazy">"""
                f"""<div class="t">{doc['title'][0]}</div>"""
                f"""<div class="meta"></div></a>"""
            )
        html.append("</div>")
        st.markdown("".join(html), unsafe_allow_html=True)

else:
    # --- Grid-Ansicht (Standard) ---
    parts = []
    if q_param:
        parts.append(
            (Occur.Must, index.parse_query(q_param, ["title", "actors", "description", "tmdb_overview"]))
        )
    if qp.get("genres"):
        sub = []
        for g in qp.get("genres").split(","):
            if g.strip() == "Gezeichnet":
                # Gezeichnet = Animation, Zeichentrick, Anime, Animiert
                sub.append((Occur.Should, index.parse_query('"Animation"', ["genres"])))
                sub.append((Occur.Should, index.parse_query('"Zeichentrick"', ["genres"])))
                sub.append((Occur.Should, index.parse_query('"Anime"', ["genres"])))
                sub.append((Occur.Should, index.parse_query('"Animiert"', ["genres"])))
                sub.append((Occur.Should, index.parse_query('"Animated"', ["genres"])))
            else:
                sub.append((Occur.Should, index.parse_query(f'"{ g}"', ["genres"])))
        parts.append((Occur.Must, Query.boolean_query(sub)))
    if qp.get("providers"):
        sub = []
        for p in qp.get("providers").split(","):
            sub.append((Occur.Should, index.parse_query(f'"{p}"', ["providers"])))
        parts.append((Occur.Must, Query.boolean_query(sub)))
    if qp.get("true_story") == "1":
        parts.append((Occur.Must, index.parse_query("1", ["is_true_story"])))
    if qp.get("book") == "1":
        parts.append((Occur.Must, index.parse_query("1", ["is_based_on_book"])))

    query = Query.boolean_query(parts) if parts else index.parse_query("*", ["title"])
    # Limit für Grid-Ansicht auf 7000 erhöht
    hits = searcher.search(query, 7000).hits
    results = []
    for _, addr in hits:
        doc = searcher.doc(addr)
        pop = doc["tmdb_popularity"][0] if doc["tmdb_popularity"] else 0.0
        rate = doc["tmdb_vote_average"][0] if doc["tmdb_vote_average"] else 0.0
        count = doc["tmdb_vote_count"][0] if doc["tmdb_vote_count"] else 0
        score = doc["score"][0] if doc["score"] else 0
        date = doc["start"][0] if doc["start"] else 0
        results.append({
            "id": doc["id"][0],
            "title": doc["title"][0],
            "poster": doc["tmdb_poster_path"][0] if doc["tmdb_poster_path"] else "",
            "pop": pop,
            "rate": rate,
            "count": count,
            "score": score,
            "date": date
        })

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
        st.info("Keine Ergebnisse gefunden.")
    else:
        html = ['<div class="grid">']
        for r in results:
            img = TMDB_PATH_SMALL + r["poster"] if r["poster"] else "https://via.placeholder.com/200x300"
            href = f"?view=detail&id={r['id']}&q={up.quote(q_param, safe='')}"
            # Suchparameter in Card-Links beibehalten
            if qp.get("genres"):
                href += f"&genres={up.quote(qp.get('genres'), safe='')}"
            if qp.get("providers"):
                href += f"&providers={up.quote(qp.get('providers'), safe='')}"
            if qp.get("sort"):
                href += f"&sort={up.quote(qp.get('sort'), safe='')}"
            if qp.get("true_story"):
                href += f"&true_story={qp.get('true_story')}"
            if qp.get("book"):
                href += f"&book={qp.get('book')}"
            label = f"Score: {r['score']}" if sort_k == "Kritiker-Score" and r["score"] > 0 else f"{r['rate']:.1f}"
            html.append(
                f"""<a class="card" href="{href}" target="_self">"""
                f"""<img src="{img}" loading="lazy">"""
                f"""<div class="t">{r['title']}</div>"""
                f"""<div class="meta">{label}</div></a>"""
            )
        html.append("</div>")
        st.markdown("".join(html), unsafe_allow_html=True)