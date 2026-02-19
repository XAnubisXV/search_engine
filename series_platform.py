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

# --- SCROLL-POSITION SPEICHERN (fuer Card-Links) ---
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
        hits = searcher.search(index.parse_query("*", ["title"]), 7000).hits
        found = set()
        for _, addr in hits:
            doc = searcher.doc(addr)
            vals = doc[field_name] if doc[field_name] else []
            for v in vals:
                parts = v.split(",") if "," in v else [v]
                for p in parts:
                    if p.strip():
                        found.add(p.strip())
        return sorted(list(found))
    except:
        return []


# Genre-Synonyme: Welche DB-Genres gehoeren zu welchem Anzeige-Genre
GENRE_SYNONYME = {
    "Gezeichnet": ["animation", "zeichentrick", "anime", "animiert", "animated", "cartoon"],
    "Animiert": ["animation", "zeichentrick", "anime", "animiert", "animated", "cartoon"],
    "Krimi": ["krimi", "crime", "police", "detective"],
    "Science-Fiction": ["science-fiction", "sci-fi", "science fiction", "sci fi"],
    "Historisch": ["historisch", "history", "krieg", "war", "historical"],
    "Stand-Up": ["stand-up", "talk", "comedy", "komödie"],
    "Dokumentation": ["dokumentation", "documentary", "doku"],
    "Horror": ["horror"],
    "Mystery": ["mystery", "mysterie"],
    "Fantasy": ["fantasy", "sci-fi & fantasy", "sci fi"],
    "Action": ["action"],
    "Abenteuer": ["abenteuer", "adventure"],
    "Drama": ["drama"],
    "Thriller": ["thriller", "suspense"],
    "Romantik": ["romantik", "romance", "romantic"],
    "Komödie": ["komödie", "comedy"],
}

# Kategorien fuer die Startseite (Reihenfolge wie angezeigt)
HOMEPAGE_KATEGORIEN = [
    "Action",
    "Drama",
    "Komödie",
    "Krimi",
    "Science-Fiction",
    "Fantasy",
    "Horror",
    "Mystery",
    "Dokumentation",
    "Historisch",
    "Gezeichnet",
    "Romantik",
    "Abenteuer",
    "Thriller",
]


@st.cache_data
def get_all_series():
    """Alle Serien aus dem Index laden und als Liste zurueckgeben."""
    hits = searcher.search(index.parse_query("*", ["title"]), 7000).hits
    all_series = []
    for _, addr in hits:
        doc = searcher.doc(addr)
        all_series.append({
            "id": doc["id"][0],
            "title": doc["title"][0],
            "poster": doc["tmdb_poster_path"][0] if doc["tmdb_poster_path"] else "",
            "genres": doc["genres"] if doc["genres"] else [],
            "providers": doc["providers"] if doc["providers"] else [],
            "pop": doc["tmdb_popularity"][0] if doc["tmdb_popularity"] else 0.0,
            "rate": doc["tmdb_vote_average"][0] if doc["tmdb_vote_average"] else 0.0,
            "count": doc["tmdb_vote_count"][0] if doc["tmdb_vote_count"] else 0,
            "score": doc["score"][0] if doc["score"] else 0,
            "date": doc["start"][0] if doc["start"] else 0,
        })
    return all_series


def get_series_for_genre(all_series, genre_name, max_count=8):
    """Filtere Serien fuer ein bestimmtes Genre und sortiere nach Bewertung.
    Benutzt Teilstring-Match: 'action' findet auch 'Action & Adventure'."""
    synonyme = GENRE_SYNONYME.get(genre_name, [genre_name.lower()])
    matching = []
    for s in all_series:
        # Alle Genres der Serie als einen langen lowercase String zusammenfuegen
        genre_text = " | ".join(s["genres"]).lower()
        # Pruefen ob eines der Synonyme als Teilstring vorkommt
        found = False
        for syn in synonyme:
            if syn in genre_text:
                found = True
                break
        if found:
            matching.append(s)
    # Sortiere nach Bewertung (Serien ohne genug Stimmen bekommen Score 0)
    matching.sort(key=lambda x: x["rate"] if x["count"] >= 5 else 0, reverse=True)
    return matching[:max_count]


# --- 4. HEADER ---
header = st.container()

with header:
    if view == "detail":
        # Detail-Ansicht: Nur PATHFINDER zentriert, keine anderen Buttons
        st.markdown(
            '<div style="text-align:center;"><a href="?view=home" class="logo-style" target="_self">PATHFINDER</a></div>',
            unsafe_allow_html=True
        )
    else:
        # Normale Ansicht: PATHFINDER + SUCHE & FILTER + LISTE
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

        db_genres = get_filter_options("genres")
        PFLICHT_GENRES = [
            "Action", "Abenteuer", "Animation", "Animiert", "Dokumentation",
            "Drama", "Fantasy", "Gezeichnet", "Historisch", "Horror",
            "Komödie", "Krimi", "Mystery", "Romantik", "Science-Fiction",
            "Stand-Up", "Thriller"
        ]
        for extra_genre in PFLICHT_GENRES:
            if extra_genre not in db_genres:
                db_genres.append(extra_genre)
        db_genres = sorted(db_genres)

        db_providers = get_filter_options("providers")
        PFLICHT_PROVIDERS = [
            "Netflix", "Amazon Prime", "Disney+", "Apple TV+",
            "Paramount+", "Joyn", "Amazon Freevee", "HBO Max",
            "WOW", "RTL+", "Crunchyroll", "MagentaTV",
            "ARD Mediathek", "ZDF Mediathek"
        ]
        for extra_prov in PFLICHT_PROVIDERS:
            if extra_prov not in db_providers:
                db_providers.append(extra_prov)
        db_providers = sorted(db_providers)

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
            if search_query: p["q"] = search_query
            if sel_genres: p["genres"] = ",".join(sel_genres)
            if sel_provs: p["providers"] = ",".join(sel_provs)
            if is_true: p["true_story"] = "1"
            if is_book: p["book"] = "1"
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
                back_clicked = st.button("ZURUECK ZUR UEBERSICHT", key="btn_back", use_container_width=True)
            with btn_col2:
                if d_id in st.session_state.watchlist:
                    list_clicked = st.button("VON LISTE ENTFERNEN", key="btn_list_remove", use_container_width=True)
                else:
                    list_clicked = st.button("AUF DIE LISTE", key="btn_list_add", use_container_width=True)
            with btn_col3:
                pass  # Platzhalter fuer symmetrisches Layout

            if back_clicked:
                new_params = {"view": "home", "scroll": back_scroll}
                for k in ["q", "genres", "providers", "sort", "true_story", "book"]:
                    if qp.get(k): new_params[k] = qp.get(k)
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

elif view == "mylist":
    st.markdown("## Meine Liste")
    if not st.session_state.watchlist:
        st.info("Du hast noch keine Serien auf deiner Liste.")
    else:
        q_str = " OR ".join([f"id:{wid}" for wid in st.session_state.watchlist])
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

elif view == "grid":
    # --- Suchergebnisse-Ansicht (nach Filter) ---
    parts = []
    if q_param:
        parts.append(
            (Occur.Must, index.parse_query(q_param, ["title", "actors", "description", "tmdb_overview"]))
        )

    if qp.get("genres"):
        sub = []
        for g in qp.get("genres").split(","):
            clean_g = g.strip()
            synonyme = GENRE_SYNONYME.get(clean_g, [clean_g])
            for syn in synonyme:
                sub.append((Occur.Should, index.parse_query(f'"{syn}"', ["genres"])))
        parts.append((Occur.Must, Query.boolean_query(sub)))

    if qp.get("providers"):
        sub = []
        for p in qp.get("providers").split(","):
            clean_p = p.strip()
            if clean_p == "Amazon Prime":
                sub.append((Occur.Should, index.parse_query('"Amazon Prime"', ["providers"])))
                sub.append((Occur.Should, index.parse_query('"Amazon Prime Video"', ["providers"])))
            elif clean_p == "WOW":
                sub.append((Occur.Should, index.parse_query('"WOW"', ["providers"])))
                sub.append((Occur.Should, index.parse_query('"Sky"', ["providers"])))
            elif clean_p == "HBO Max":
                sub.append((Occur.Should, index.parse_query('"HBO Max"', ["providers"])))
                sub.append((Occur.Should, index.parse_query('"Max"', ["providers"])))
            else:
                sub.append((Occur.Should, index.parse_query(f'"{clean_p}"', ["providers"])))
        parts.append((Occur.Must, Query.boolean_query(sub)))

    if qp.get("true_story") == "1":
        parts.append((Occur.Must, index.parse_query("1", ["is_true_story"])))
    if qp.get("book") == "1":
        parts.append((Occur.Must, index.parse_query("1", ["is_based_on_book"])))

    query = Query.boolean_query(parts) if parts else index.parse_query("*", ["title"])
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
            for k in ["genres", "providers", "sort", "true_story", "book"]:
                if qp.get(k): href += f"&{k}={up.quote(qp.get(k), safe='')}"

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
    # --- STARTSEITE: Genre-Kategorien mit je 8 Serien ---
    all_series = get_all_series()

    for kategorie in HOMEPAGE_KATEGORIEN:
        serien = get_series_for_genre(all_series, kategorie, max_count=15)
        if not serien:
            continue

        # Kategorie-Titel
        st.markdown(
            f'<div class="genre-title">{kategorie}</div>',
            unsafe_allow_html=True
        )

        # Horizontale Reihe mit Serien-Cards
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