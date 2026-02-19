import json
import os
import urllib.parse as up
import streamlit as st
from tantivy import Query, Index, SchemaBuilder, Occur

# --- 1. SETUP ---
st.set_page_config(page_title="PathFinder", page_icon="🧭", layout="wide")

# Static-Ordner für Hintergrundbild erstellen
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
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []


def save_watchlist(wl):
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(wl, f)


if 'watchlist' not in st.session_state:
    st.session_state.watchlist = load_watchlist()
if 'show_search' not in st.session_state:
    st.session_state.show_search = False

qp = st.query_params
view = qp.get("view", "home")
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

# --- SCROLL-POSITION SPEICHERN (für Card-Links) ---
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


# --- ALLE SERIEN LADEN (einmalig gecached) ---
@st.cache_data
def get_all_series():
    """Alle Serien aus dem Index laden, deduplizieren und als Liste zurückgeben."""
    hits = searcher.search(index.parse_query("*", ["title"]), 7000).hits
    all_series = []
    seen_titles = set()
    for _, addr in hits:
        doc = searcher.doc(addr)
        title = doc["title"][0]
        # Doppelte Serien anhand des Titels entfernen
        title_lower = title.strip().lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)
        all_series.append({
            "id": doc["id"][0],
            "title": title,
            "poster": doc["tmdb_poster_path"][0] if doc["tmdb_poster_path"] else "",
            "genres": doc["genres"] if doc["genres"] else [],
            "providers": doc["providers"] if doc["providers"] else [],
            "pop": doc["tmdb_popularity"][0] if doc["tmdb_popularity"] else 0.0,
            "rate": doc["tmdb_vote_average"][0] if doc["tmdb_vote_average"] else 0.0,
            "count": doc["tmdb_vote_count"][0] if doc["tmdb_vote_count"] else 0,
            "score": doc["score"][0] if doc["score"] else 0,
            "date": doc["start"][0] if doc["start"] else 0,
            "is_true_story": doc["is_true_story"][0] if doc["is_true_story"] else 0,
            "is_based_on_book": doc["is_based_on_book"][0] if doc["is_based_on_book"] else 0,
        })
    return all_series


# --- GENRE-SYNONYME ---
GENRE_SYNONYME = {
    "Action & Abenteuer": ["action", "abenteuer", "adventure", "action & adventure"],
    "Sitcom": ["sitcom", "comedy", "komödie"],
    "Animation": ["animation", "zeichentrick", "anime", "animiert", "animated", "cartoon"],
    "Dokumentation": ["dokumentation", "documentary", "doku"],
    "Drama": ["drama"],
    "Fantasy": ["fantasy", "sci-fi & fantasy"],
    "Historisch": ["historisch", "history", "krieg", "war", "historical"],
    "Horror": ["horror"],
    "Komödie": ["komödie", "comedy", "komoedie"],
    "Krimi": ["krimi", "crime", "police", "detective"],
    "Mystery": ["mystery", "mysterie"],
    "Romantik": ["romantik", "romance", "romantic"],
    "Science-Fiction": ["science-fiction", "sci-fi", "science fiction", "sci fi"],
    "Stand-Up": ["stand-up", "talk"],
    "Thriller": ["thriller", "suspense"],
}

# Feste Genre-Liste für den Filter (nur diese!)
FILTER_GENRES = [
    "Action & Abenteuer",
    "Animation",
    "Dokumentation",
    "Drama",
    "Fantasy",
    "Historisch",
    "Horror",
    "Komödie",
    "Krimi",
    "Mystery",
    "Romantik",
    "Science-Fiction",
    "Sitcom",
    "Stand-Up",
    "Thriller",
]

# Feste Plattform-Liste für den Filter (nur diese!)
FILTER_PROVIDERS = [
    "Amazon Prime",
    "Disney+",
    "HBO Max",
    "Joyn",
    "Netflix",
    "RTL+",
]

# Kategorien für die Startseite (Reihenfolge wie angezeigt)
HOMEPAGE_KATEGORIEN = [
    "Action & Abenteuer",
    "Drama",
    "Komödie",
    "Krimi",
    "Science-Fiction",
    "Fantasy",
    "Horror",
    "Mystery",
    "Dokumentation",
    "Historisch",
    "Animation",
    "Romantik",
    "Thriller",
    "Sitcom",
]


def genre_matches(series_genres, genre_name):
    """Prüft ob eine Serie zu einem Genre passt (Teilstring-Match)."""
    synonyme = GENRE_SYNONYME.get(genre_name, [genre_name.lower()])
    genre_text = " | ".join(series_genres).lower()
    for syn in synonyme:
        if syn in genre_text:
            return True
    return False


def provider_matches(series_providers, selected_providers):
    """Prüft ob eine Serie bei mindestens einem der gewählten Anbieter verfügbar ist."""
    if not selected_providers:
        return True
    prov_text = " | ".join(series_providers).lower()
    for sel in selected_providers:
        sel_lower = sel.lower()
        # Spezielle Mappings
        if sel == "Amazon Prime":
            if "amazon" in prov_text or "paramount" in prov_text or "apple tv" in prov_text or "apple" in prov_text:
                return True
        elif sel == "HBO Max":
            if "hbo max" in prov_text or "hbo" in prov_text or "max" in prov_text:
                return True
        else:
            if sel_lower in prov_text:
                return True
    return False


def get_series_for_genre(all_series, genre_name, max_count=15):
    """Filtere Serien für ein bestimmtes Genre und sortiere nach Bewertung."""
    matching = [s for s in all_series if genre_matches(s["genres"], genre_name)]
    matching.sort(key=lambda x: x["rate"] if x["count"] >= 5 else 0, reverse=True)
    return matching[:max_count]


def filter_series(all_series, query="", genres=None, providers=None,
                  true_story=False, book=False, sort_by="Beliebtheit"):
    """Filtere und sortiere Serien basierend auf allen Suchkriterien."""
    results = []
    for s in all_series:
        # Textsuche
        if query:
            q_lower = query.lower()
            title_match = q_lower in s["title"].lower()
            genre_match = any(q_lower in g.lower() for g in s["genres"])
            if not title_match and not genre_match:
                continue

        # Genre-Filter
        if genres:
            genre_found = False
            for g in genres:
                if genre_matches(s["genres"], g):
                    genre_found = True
                    break
            if not genre_found:
                continue

        # Plattform-Filter
        if providers:
            if not provider_matches(s["providers"], providers):
                continue

        # Wahre Geschichte
        if true_story and s["is_true_story"] != 1:
            continue

        # Basiert auf Buch
        if book and s["is_based_on_book"] != 1:
            continue

        results.append(s)

    # Sortierung
    if sort_by == "Beliebtheit":
        results.sort(key=lambda x: x["pop"], reverse=True)
    elif sort_by == "Bewertung (Top Rated)":
        results.sort(key=lambda x: x["rate"] if x["count"] >= 50 else 0, reverse=True)
    elif sort_by == "Kritiker-Score":
        results.sort(key=lambda x: x["score"], reverse=True)
    elif sort_by == "Neuerscheinungen":
        results.sort(key=lambda x: x["date"], reverse=True)

    return results


# --- 4. HEADER ---
header = st.container()

with header:
    if view == "detail":
        st.markdown(
            '<div style="text-align:center;"><a href="?view=home" class="logo-style" target="_self">PATHFINDER</a></div>',
            unsafe_allow_html=True
        )
    else:
        _, c_logo, c_search, c_list, _ = st.columns([3, 1.2, 1.5, 1.2, 3])

        with c_logo:
            st.markdown(
                '<a href="?view=home" class="logo-style" target="_self">PATHFINDER</a>',
                unsafe_allow_html=True
            )

        with c_search:
            if st.button("SUCHE & FILTER", key="btn_search", use_container_width=True):
                st.session_state.show_search = not st.session_state.show_search

        with c_list:
            count = len(st.session_state.watchlist)
            btn_label_list = f"LISTE ({count})"
            if st.button(btn_label_list, key="btn_list", use_container_width=True):
                st.query_params["view"] = "mylist"
                st.rerun()

# --- 5. SUCH-POPUP (als Overlay gestyled per CSS) ---
if st.session_state.show_search and view != "detail" and view != "mylist":

    st.markdown('<div class="popup-overlay"></div>', unsafe_allow_html=True)
    st.markdown('<div class="popup-box">', unsafe_allow_html=True)
    st.markdown('<div class="popup-title">SUCHE & FILTER</div>', unsafe_allow_html=True)

    with st.form("search_form"):

        search_query = st.text_input(
            "Wonach suchst du?",
            value=q_param,
            placeholder="z.B. Breaking Bad, Action, ein Schauspieler..."
        )

        c1, c2, c3 = st.columns(3)

        sel_genres = c1.multiselect(
            "Genre",
            FILTER_GENRES,
            default=qp.get("genres", "").split(",") if qp.get("genres") else []
        )
        sel_provs = c2.multiselect(
            "Plattform",
            FILTER_PROVIDERS,
            default=qp.get("providers", "").split(",") if qp.get("providers") else []
        )
        sort_opt = c3.selectbox(
            "Sortieren nach",
            ["Beliebtheit", "Bewertung (Top Rated)", "Kritiker-Score", "Neuerscheinungen"]
        )

        cc1, cc2 = st.columns(2)
        is_true = cc1.checkbox(
            "Wahre Geschichte",
            value=True if qp.get("true_story") == "1" else False
        )
        is_book = cc2.checkbox(
            "Basiert auf Buch",
            value=True if qp.get("book") == "1" else False
        )

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

            # --- BUTTONS OBEN (unter dem Header) ---
            back_scroll = qp.get("scroll", "0")
            btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1])
            with btn_col1:
                back_clicked = st.button("ZURÜCK ZUR ÜBERSICHT", key="btn_back", use_container_width=True)
            with btn_col2:
                if d_id in st.session_state.watchlist:
                    list_clicked = st.button("VON LISTE ENTFERNEN", key="btn_list_remove", use_container_width=True)
                else:
                    list_clicked = st.button("AUF DIE LISTE", key="btn_list_add", use_container_width=True)
            with btn_col3:
                pass

            if back_clicked:
                new_params = {"view": "home", "scroll": back_scroll}
                for k in ["q", "genres", "providers", "sort", "true_story", "book"]:
                    if qp.get(k):
                        new_params[k] = qp.get(k)
                st.query_params.clear()
                st.query_params.update(new_params)
                st.rerun()

            if d_id in st.session_state.watchlist and list_clicked:
                st.session_state.watchlist.remove(d_id)
                save_watchlist(st.session_state.watchlist)
                st.rerun()
            elif d_id not in st.session_state.watchlist and list_clicked:
                st.session_state.watchlist.append(d_id)
                save_watchlist(st.session_state.watchlist)
                st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)

            # --- SERIEN-DETAIL ---
            c1, c2 = st.columns([1, 2])
            with c1:
                img = doc["tmdb_poster_path"][0] if doc["tmdb_poster_path"] else ""
                url = TMDB_PATH_BIG + img if img else "https://via.placeholder.com/500x750?text=No+Image"
                st.image(url, use_container_width=True)
            with c2:
                st.markdown(f"<h1>{doc['title'][0]}</h1>", unsafe_allow_html=True)
                rate = doc["tmdb_vote_average"][0] if doc["tmdb_vote_average"] else 0
                score = doc["score"][0] if doc["score"] else 0
                year = doc["start"][0] if doc["start"] else "N/A"
                meta_html = f"""
                <div style="display:flex; align-items:center; gap:15px; margin-bottom:20px;">
                    <span style="color:#00e5ff; font-weight:bold; font-size:1.2rem;">{rate:.1f}</span>
                    <span style="color:#aaa;">{year}</span>
                </div>"""
                st.markdown(meta_html, unsafe_allow_html=True)
                if doc["providers"]:
                    st.markdown("Verfügbar bei:")
                    for p in doc["providers"]:
                        st.markdown(f'<span class="tag">{p}</span>', unsafe_allow_html=True)
                    st.markdown("<br>", unsafe_allow_html=True)
                desc = doc["tmdb_overview"][0] if doc["tmdb_overview"] else doc["description"][0]
                st.write(desc if desc else "Keine Beschreibung verfügbar.")
                st.markdown("---")
                if doc["genres"]:
                    st.markdown(f"**Genre:** {', '.join(doc['genres'])}")
                if doc["actors"]:
                    st.markdown(f"**Cast:** {', '.join(doc['actors'][:5])}")
                if doc["trailer"]:
                    st.markdown("### Trailer")
                    st.video(f"https://www.youtube.com/watch?v={doc['trailer'][0]}")

elif view == "mylist":
    st.markdown("## Meine Liste")
    if not st.session_state.watchlist:
        st.info("Du hast noch keine Serien auf deiner Liste.")
    else:
        all_series = get_all_series()
        wl_set = set(st.session_state.watchlist)
        wl_series = [s for s in all_series if s["id"] in wl_set]
        html = ['<div class="grid">']
        for s in wl_series:
            img = TMDB_PATH_SMALL + s["poster"] if s["poster"] else "https://via.placeholder.com/200x300?text=No+Image"
            html.append(
                f"""<a class="card" href="?view=detail&id={s['id']}" target="_self">"""
                f"""<img src="{img}" loading="lazy">"""
                f"""<div class="t">{s['title']}</div>"""
                f"""<div class="meta">{s['rate']:.1f}</div></a>"""
            )
        html.append("</div>")
        st.markdown("".join(html), unsafe_allow_html=True)

elif view == "grid":
    # --- Suchergebnisse-Ansicht (nach Filter) ---
    all_series = get_all_series()

    sel_genres = qp.get("genres", "").split(",") if qp.get("genres") else []
    sel_provs = qp.get("providers", "").split(",") if qp.get("providers") else []
    true_story = qp.get("true_story") == "1"
    book = qp.get("book") == "1"
    sort_k = qp.get("sort", "Beliebtheit")

    results = filter_series(
        all_series,
        query=q_param,
        genres=sel_genres if sel_genres else None,
        providers=sel_provs if sel_provs else None,
        true_story=true_story,
        book=book,
        sort_by=sort_k
    )

    if not results:
        st.info("Keine Ergebnisse gefunden.")
    else:
        html = ['<div class="grid">']
        for r in results:
            img = TMDB_PATH_SMALL + r["poster"] if r["poster"] else "https://via.placeholder.com/200x300"
            href = f"?view=detail&id={r['id']}&q={up.quote(q_param, safe='')}"
            for k in ["genres", "providers", "sort", "true_story", "book"]:
                if qp.get(k):
                    href += f"&{k}={up.quote(qp.get(k), safe='')}"

            label = f"Score: {r['score']}" if sort_k == "Kritiker-Score" and r["score"] > 0 else f"{r['rate']:.1f}"
            html.append(
                f"""<a class="card" href="{href}" target="_self">"""
                f"""<img src="{img}" loading="lazy">"""
                f"""<div class="t">{r['title']}</div>"""
                f"""<div class="meta">{label}</div></a>"""
            )
        html.append("</div>")
        st.markdown("".join(html), unsafe_allow_html=True)

else:
    # --- STARTSEITE: Genre-Kategorien mit je 15 Serien ---
    all_series = get_all_series()

    for kategorie in HOMEPAGE_KATEGORIEN:
        serien = get_series_for_genre(all_series, kategorie, max_count=15)
        if not serien:
            continue

        st.markdown(
            f'<div class="genre-title">{kategorie}</div>',
            unsafe_allow_html=True
        )

        html = ['<div class="genre-row">']
        for s in serien:
            img = TMDB_PATH_SMALL + s["poster"] if s["poster"] else "https://via.placeholder.com/200x300"
            href = f"?view=detail&id={s['id']}"
            html.append(
                f"""<a class="card genre-card" href="{href}" target="_self">"""
                f"""<img src="{img}" loading="lazy">"""
                f"""<div class="t">{s['title']}</div>"""
                f"""<div class="meta">{s['rate']:.1f}</div></a>"""
            )
        html.append("</div>")
        st.markdown("".join(html), unsafe_allow_html=True)