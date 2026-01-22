import urllib.parse as up
from typing import Any
import streamlit as st
from tantivy import Query, Index, SchemaBuilder, Occur

import utils

# Konstanten
TMDB_PATH = "https://image.tmdb.org/t/p/original"
TMDB_PATH_SMALL = "https://image.tmdb.org/t/p/w200"
INDEX_PATH = "serien_300"  # bestehendes Tantivy-Index-Verzeichnis
TOP_K = 20          # wie viele Ergebnisse angezeigt werden sollen
CARDS_PER_PAGE = 3 # Cards, die in der zufälligen Anzeige auftauchen

schema_builder = SchemaBuilder()
# Text-Felder
schema_builder.add_text_field("wikidata", stored=True)
schema_builder.add_text_field("url", stored=True)
schema_builder.add_text_field("title", stored=True, tokenizer_name='en_stem')
schema_builder.add_text_field("description", stored=True, tokenizer_name='en_stem')  # Multi-valued text field
schema_builder.add_text_field("image", stored=True)
schema_builder.add_text_field("locations", stored=True)
schema_builder.add_text_field("countries", stored=True)
schema_builder.add_text_field("genres", stored=True)
schema_builder.add_text_field("tmdb_overview", stored=True, tokenizer_name='en_stem')
schema_builder.add_text_field("tmdb_poster_path", stored=True)
schema_builder.add_text_field("trailer", stored=True)

# Integer-Felder
schema_builder.add_integer_field("id", stored=True, indexed=True)
schema_builder.add_integer_field("follower", stored=True, fast=True)
schema_builder.add_integer_field("score", stored=True, fast=True)
schema_builder.add_integer_field("start", stored=True, fast=True)
schema_builder.add_integer_field("tmdb_genre_ids", stored=True, indexed=True)
schema_builder.add_integer_field("tmdb_vote_count", stored=True, fast=True)

# Float-Felder
schema_builder.add_float_field("tmdb_popularity", stored=True, fast=True)
schema_builder.add_float_field("tmdb_vote_average", stored=True, fast=True)

# Facettenfelder
schema_builder.add_facet_field("facet_locations")
schema_builder.add_facet_field("facet_countries")
schema_builder.add_facet_field("facet_genres")

schema = schema_builder.build()
index = Index(schema, path=str(INDEX_PATH))
#index.reload()
searcher = index.searcher()


with open("styles.html", "r") as f:
    css = f.read()

st.markdown(css, unsafe_allow_html=True)

full_star = '<i class="fa-solid fa-star"></i>'
half_star = '<i class="fa-solid fa-star-half-stroke"></i>'
empty_star = '<i class="fa-regular fa-star"></i>'


# Hilfsfunktion für Seitenrouting mit Anfrageparametern.
# Gibt die Query-Parameter der aktuellen Seite als Dictionary zurück.
# Falls `st.query_params` nicht verfügbar ist, wird ein leeres Dictionary zurückgegeben.
def get_qp() -> dict[str, Any]:
    return getattr(st, "query_params", {})


qp = get_qp()
view = qp.get("view")
selected_id = qp.get("id")
q = qp.get("q", "")  # <-- keep the query in the URL

# Detail View
if view == "detail" and selected_id:
    q_t = index.parse_query(selected_id, ["id"])
    detail_hits = searcher.search(q_t, 1).hits
    detail_score, detail_address = detail_hits[0]
    detail_doc = searcher.doc(detail_address)
    detail_title = detail_doc["title"][0]
    detail_overview_src = detail_doc["tmdb_overview"] or detail_doc["description"]
    detail_overview = detail_overview_src[0]
    detail_poster = detail_doc["tmdb_poster_path"]
    detail_poster_url = (TMDB_PATH_SMALL + detail_poster[0]) if detail_poster else ""
    trailer = detail_doc["trailer"]
    video_key = detail_doc["trailer"][0] if trailer else ""
    st.title(detail_title)
    genres = detail_doc["genres"]
    tags_html = "<div>"
    if genres is not None:
        for tag in genres:
            tags_html += f'<span class="tag">{tag}</span>'
        tags_html += "</div>"
    st.markdown(tags_html, unsafe_allow_html=True)
    if video_key != "":
        st.video(f"https://www.youtube.com/watch?v={video_key}")
    st.write(detail_overview)

    if st.button("← Zurück zur Übersicht"):
        st.query_params.update({"view": "grid"})
        st.query_params.pop("id", None)
        st.rerun()
    st.stop()

# Hauptseite
st.title("TV-Serien")

# items = [10,25,33,42,102,111,124,298]
# random_cards_html = []
# for item in items:
#     q_t = index.parse_query(str(item), ["id"])
#     random_hits = searcher.search(q_t, 1).hits
#     if random_hits:
#         random_score, random_address = random_hits[0]
#         random_doc = searcher.doc(random_address)
#         random_title = random_doc["title"][0]
#         random_poster = random_doc["tmdb_poster_path"]
#         if random_poster:
#             random_href = f"?view=detail&id={str(item)}&q={up.quote(q, safe='')}"
#             random_img_url = TMDB_PATH + random_poster[0]
#             random_img_tag = f'<img src="{random_img_url}" loading="lazy" alt="poster">'
#             random_cards_html.append(
#             f"""<a class="card" href="{random_href}" target="_self">{random_img_tag}<div class="t">{random_title}</div></a>""")
# utils.display_random_items(random_cards_html)

# Verarbeitet die aktuelle Anfrage (Query);
query_text = st.text_input("Suchbegriff eingeben", value=q, placeholder="z. B. Breaking Bad, Dark, etc. ...")
if st.button("Suchen", type="primary"):
    if not query_text:
        st.info("Bitte gib einen Suchbegriff ein.")
    else:
        # Speichert die Anfrageparameter und lädt die Seite erneut
        st.query_params.update({"q": up.quote(query_text, safe=''), "view": "grid"})
        st.rerun()

# Raster (Grid) darstellen, wenn q existiert
if q:
    unquoted_q = up.unquote(q).lower()
    query = unquoted_q.strip()
    terms = query.split()
    boolean_parts = []
    for term in terms:
        u_q = index.parse_query(term, ["title"])  # uses en_stem for "title"
        boolean_parts.append((Occur.Must, u_q))
    boolean_query = Query.boolean_query(boolean_parts)
    hits = searcher.search(boolean_query, 7000).hits

    if not hits:
        st.warning("Keine Ergebnisse gefunden.")
    else:
        st.subheader("Ergebnisse")
        # Erstelle das Grid mit klickbaren Thumbnails
        cards_html = ['<div class="grid">']

        for score, addr in hits:
            doc = searcher.doc(addr)
            doc_id = doc["id"][0]
            title = doc["title"][0]
            start = doc["start"][0] if doc["start"] else ""
            poster = doc["tmdb_poster_path"]
            poster_url = (TMDB_PATH_SMALL + poster[0]) if poster else ""
            href = f"?view=detail&id={doc_id}&q={up.quote(q, safe='')}"
            img_tag = f'<img src="{poster_url}" loading="lazy" alt="poster">' if poster_url else ""
            cards_html.append(f"""<a class="card" href="{href}" target="_self">{img_tag}<div class="t">{title}</div></a>""")
            #cards_html.append(
            #    f"""<div class="card"><a href="{href}">{img_tag}<div class="t">{title}</div></a><div class="m">{start}</div></div>""")
        cards_html.append("</div>")
        st.markdown("".join(cards_html), unsafe_allow_html=True)
else:
    st.info("Gib einen Suchbegriff ein und klicke auf **Suchen** (oder drücke Enter).")
